#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import concurrent.futures
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from pythonbuild.downloads import (
    DOWNLOADS,
)
from pythonbuild.utils import (
    create_tar_from_directory,
    download_entry,
    extract_tar_to_directory,
)

ROOT = pathlib.Path(os.path.abspath(__file__)).parent.parent
BUILD = ROOT / 'build'
SUPPORT = ROOT / 'cpython-windows'

LOG_PREFIX = [None]
LOG_FH = [None]

# Extensions that need to be converted from standalone to built-in.
# Key is name of VS project representing the standalone extension.
# Value is dict describing the extension.
CONVERT_TO_BUILTIN_EXTENSIONS = {
    '_asyncio': {
        # _asynciomodule.c is included in pythoncore for some reason.
        'allow_missing_preprocessor': True,
    },
     '_bz2': {},
    '_contextvars': {
        # _contextvars.c is included in pythoncore for some reason.
        'allow_missing_preprocessor': True,
    },
    '_ctypes': {},
    '_decimal': {},
    '_elementtree': {},
    '_hashlib': {},
    '_lzma': {
        'static_depends': ['liblzma'],
    },
    '_msi': {},
    '_overlapped': {},
    '_multiprocessing': {},
    '_socket': {},
    '_sqlite3': {
        'static_depends': ['sqlite3'],
    },
    # See the one-off calls to copy_link_to_lib() to make this work.
    # TODO build and a static OpenSSL and link to it.
    '_ssl': {},
    '_queue': {},
    'pyexpat': {},
    'select': {},
    'unicodedata': {},
    'winsound': {},
}


def log(msg):
    if isinstance(msg, bytes):
        msg_str = msg.decode('utf-8', 'replace')
        msg_bytes = msg
    else:
        msg_str = msg
        msg_bytes = msg.encode('utf-8', 'replace')

    print('%s> %s' % (LOG_PREFIX[0], msg_str))

    if LOG_FH[0]:
        LOG_FH[0].write(msg_bytes + b'\n')
        LOG_FH[0].flush()


def exec_and_log(args, cwd, env, exit_on_error=True):
    log('executing %s' % ' '.join(args))

    p = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        bufsize=1,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)

    for line in iter(p.stdout.readline, b''):
        log(line.rstrip())

    p.wait()

    log('process exited %d' % p.returncode)

    if p.returncode and exit_on_error:
        sys.exit(p.returncode)


def find_msbuild():
    vswhere = pathlib.Path(os.environ['ProgramFiles(x86)']) / 'Microsoft Visual Studio' / 'Installer' / 'vswhere.exe'

    if not vswhere.exists():
        print('%s does not exist' % vswhere)
        sys.exit(1)

    p = subprocess.check_output([str(vswhere), '-latest', '-property', 'installationPath'])

    # Strictly speaking the output may not be UTF-8.
    p = pathlib.Path(p.strip().decode('utf-8'))

    p = p / 'MSBuild' / '15.0' / 'Bin' / 'MSBuild.exe'

    if not p.exists():
        print('%s does not exist' % p)
        sys.exit(1)

    return p


def static_replace_in_file(p: pathlib.Path, search, replace):
    """Replace occurrences of a string in a file.

    The updated file contents are written out in place.
    """

    with p.open('rb') as fh:
        data = fh.read()

    # Build should be as deterministic as possible. Assert that wanted changes
    # actually occur.
    if search not in data:
        log('search string (%s) not in %s' % (search, p))
        sys.exit(1)

    log('replacing `%s` with `%s` in %s' % (search, replace, p))
    data = data.replace(search, replace)

    with p.open('wb') as fh:
        fh.write(data)


def add_to_config_c(source_path: pathlib.Path, extension: str, init_fn: str):
    """Add an extension to PC/config.c"""

    config_c_path = source_path / 'PC' / 'config.c'

    lines = []

    with config_c_path.open('r') as fh:
        for line in fh:
            line = line.rstrip()

            # Insert the init function declaration before the _inittab struct.
            if line.startswith('struct _inittab'):
                log('adding %s declaration to config.c' % init_fn)
                lines.append('extern PyObject* %s(void);' % init_fn)

            # Insert the extension in the _inittab struct.
            if line.lstrip().startswith('/* Sentinel */'):
                log('marking %s as a built-in extension module' % extension)
                lines.append('{"%s", %s},' % (extension, init_fn))

            lines.append(line)

    with config_c_path.open('w') as fh:
        fh.write('\n'.join(lines))


def remove_from_extension_modules(source_path: pathlib.Path, extension: str):
    """Remove an extension from the set of extension/external modules.

    Call this when an extension will be compiled into libpython instead of
    compiled as a standalone extension.
    """

    RE_EXTENSION_MODULES = re.compile('<(Extension|External)Modules Include="([^"]+)"')

    pcbuild_proj_path = source_path / 'PCbuild' / 'pcbuild.proj'

    lines = []

    with pcbuild_proj_path.open('r') as fh:
        for line in fh:
            line = line.rstrip()

            m = RE_EXTENSION_MODULES.search(line)

            if m:
                modules = [m for m in m.group(2).split(';') if m != extension]

                # Ignore line if new value is empty.
                if not modules:
                    continue

                line = line.replace(m.group(2), ';'.join(modules))

            lines.append(line)

    with pcbuild_proj_path.open('w') as fh:
        fh.write('\n'.join(lines))


def make_project_static_library(source_path: pathlib.Path, project: str):
    """Turn a project file into a static library."""

    proj_path = source_path / 'PCbuild' / ('%s.vcxproj' % project)
    lines = []

    found_config_type = False
    found_target_ext = False

    with proj_path.open('r') as fh:
        for line in fh:
            line = line.rstrip()

            # Change the project configuration to a static library.
            if '<ConfigurationType>DynamicLibrary</ConfigurationType>' in line:
                log('changing %s to a static library' % project)
                found_config_type = True
                line = line.replace('DynamicLibrary', 'StaticLibrary')

            elif '<ConfigurationType>StaticLibrary</ConfigurationType>' in line:
                log('%s is already a static library' % project)
                return

            # Change the output file name from .pyd to .lib because it is no
            # longer an extension.
            if '<TargetExt>.pyd</TargetExt>' in line:
                log('changing output of %s to a .lib' % project)
                found_target_ext = True
                line = line.replace('.pyd', '.lib')

            lines.append(line)

    if not found_config_type:
        log('failed to adjust config type for %s' % project)
        sys.exit(1)

    if not found_target_ext:
        log('failed to adjust target extension for %s' % project)
        sys.exit(1)

    with proj_path.open('w') as fh:
        fh.write('\n'.join(lines))


def convert_to_static_library(source_path: pathlib.Path, extension: str, entry: dict):
    """Converts an extension to a static library."""

    # Make the extension's project emit a static library so we can link
    # against libpython.
    make_project_static_library(source_path, extension)

    # And do the same thing for its dependencies.
    for project in entry.get('static_depends', []):
        make_project_static_library(source_path, project)

    proj_path = source_path / 'PCbuild' / ('%s.vcxproj' % extension)

    copy_link_to_lib(proj_path)

    lines = []

    RE_PREPROCESSOR_DEFINITIONS = re.compile('<PreprocessorDefinitions[^>]*>([^<]+)</PreprocessorDefinitions>')

    found_preprocessor = False
    itemgroup_line = None
    itemdefinitiongroup_line = None

    with proj_path.open('r') as fh:
        for i, line in enumerate(fh):
            line = line.rstrip()

            # Add Py_BUILD_CORE_BUILTIN to preprocessor definitions so linkage
            # data is correct.
            m = RE_PREPROCESSOR_DEFINITIONS.search(line)

            # But don't do it if it is an annotation for an individual source file.
            if m and '<ClCompile Include=' not in lines[i - 1]:
                log('adding Py_BUILD_CORE_BUILTIN to %s' % extension)
                found_preprocessor = True
                line = line.replace(m.group(1), 'Py_BUILD_CORE_BUILTIN;%s' % m.group(1))

            # Find the first <ItemGroup> entry.
            if '<ItemGroup>' in line and not itemgroup_line:
                itemgroup_line = i

            # Find the first <ItemDefinitionGroup> entry.
            if '<ItemDefinitionGroup>' in line and not itemdefinitiongroup_line:
                itemdefinitiongroup_line = i

            lines.append(line)

    if not found_preprocessor:
        if entry.get('allow_missing_preprocessor'):
            log('not adjusting preprocessor definitions for %s' % extension)
        else:
            log('introducing <PreprocessorDefinitions> to %s' % extension)
            lines[itemgroup_line:itemgroup_line] = [
                '  <ItemDefinitionGroup>',
                '    <ClCompile>',
                '      <PreprocessorDefinitions>Py_BUILD_CORE_BUILTIN;%(PreprocessorDefinitions)</PreprocessorDefinitions>',
                '    </ClCompile>',
                '  </ItemDefinitionGroup>',
            ]

            itemdefinitiongroup_line = itemgroup_line + 1

    if 'static_depends' in entry:
        if not itemdefinitiongroup_line:
            log('unable to find <ItemDefinitionGroup> for %s' % extension)
            sys.exit(1)

        log('changing %s to automatically link library dependencies' % extension)
        lines[itemdefinitiongroup_line + 1:itemdefinitiongroup_line + 1] = [
            '    <ProjectReference>',
            '      <LinkLibraryDependencies>true</LinkLibraryDependencies>',
            '    </ProjectReference>',
        ]

    # Ensure the extension project doesn't depend on pythoncore: as a built-in
    # extension, pythoncore will depend on it.

    # This logic is a bit hacky. Ideally we'd parse the file as XML and operate
    # in the XML domain. But that is more work. The goal here is to strip the
    # <ProjectReference>...</ProjectReference> containing the
    # <Project>{pythoncore ID}</Project>. This could leave an item <ItemGroup>.
    # That should be fine.
    start_line, end_line = None, None
    for i, line in enumerate(lines):
        if '<Project>{cf7ac3d1-e2df-41d2-bea6-1e2556cdea26}</Project>' in line:
            for j in range(i, 0, -1):
                if '<ProjectReference' in lines[j]:
                    start_line = j
                    break

            for j in range(i, len(lines) - 1):
                if '</ProjectReference>' in lines[j]:
                    end_line = j
                    break

            break

    if start_line is not None and end_line is not None:
        log('stripping pythoncore dependency from %s' % extension)
        for line in lines[start_line:end_line + 1]:
            log(line)

        lines = lines[:start_line] + lines[end_line + 1:]

    with proj_path.open('w') as fh:
        fh.write('\n'.join(lines))

    # Tell pythoncore to link against the static .lib.
    RE_ADDITIONAL_DEPENDENCIES = re.compile('<AdditionalDependencies>([^<]+)</AdditionalDependencies>')

    pythoncore_path = source_path / 'PCbuild' / 'pythoncore.vcxproj'
    lines = []

    with pythoncore_path.open('r') as fh:
        for line in fh:
            line = line.rstrip()

            m = RE_ADDITIONAL_DEPENDENCIES.search(line)

            if m:
                log('changing pythoncore to link against %s.lib' % extension)
                # TODO do we need this with static linking?
                line = line.replace(m.group(1), r'$(OutDir)%s.lib;%s' % (
                    extension, m.group(1)))

            lines.append(line)

    with pythoncore_path.open('w') as fh:
        fh.write('\n'.join(lines))

    # Change pythoncore to depend on the extension project.

    # pcbuild.proj is the file that matters for msbuild. And order within
    # matters. We remove the extension from the "ExtensionModules" set of
    # projects. Then we re-add the project to before "pythoncore."
    remove_from_extension_modules(source_path, extension)

    pcbuild_proj_path = source_path / 'PCbuild' / 'pcbuild.proj'

    with pcbuild_proj_path.open('r') as fh:
        data = fh.read()

    data = data.replace('<Projects Include="pythoncore.vcxproj">',
                        '    <Projects Include="%s.vcxproj" />\n    <Projects Include="pythoncore.vcxproj">' % extension)

    with pcbuild_proj_path.open('w') as fh:
        fh.write(data)

    # We don't technically need to modify the solution since msbuild doesn't
    # use it. But it enables debugging inside Visual Studio, which is
    # convenient.
    RE_PROJECT = re.compile('Project\("\{8BC9CEB8-8B4A-11D0-8D11-00A0C91BC942\}"\) = "([^"]+)", "[^"]+", "{([^\}]+)\}"')

    pcbuild_sln_path = source_path / 'PCbuild' / 'pcbuild.sln'
    lines = []

    extension_id = None
    pythoncore_line = None

    with pcbuild_sln_path.open('r') as fh:
        # First pass buffers the file, finds the ID of the extension project,
        # and finds where the pythoncore project is defined.
        for i, line in enumerate(fh):
            line = line.rstrip()

            m = RE_PROJECT.search(line)

            if m and m.group(1) == extension:
                extension_id = m.group(2)

            if m and m.group(1) == 'pythoncore':
                pythoncore_line = i

            lines.append(line)

    # Not all projects are in the solution(!!!). Since we don't use the
    # solution for building, that's fine to ignore.
    if not extension_id:
        log('failed to find project %s in solution' % extension)

    if not pythoncore_line:
        log('failed to find pythoncore project in solution')

    if extension_id and pythoncore_line:
        log('making pythoncore depend on %s' % extension)

        needs_section = not lines[pythoncore_line + 1].lstrip().startswith('ProjectSection')
        offset = 1 if needs_section else 2

        lines.insert(pythoncore_line + offset, '\t\t{%s} = {%s}' % (extension_id, extension_id))

        if needs_section:
            lines.insert(pythoncore_line + 1, '\tProjectSection(ProjectDependencies) = postProject')
            lines.insert(pythoncore_line + 3, '\tEndProjectSection')

        with pcbuild_sln_path.open('w') as fh:
            fh.write('\n'.join(lines))


def copy_link_to_lib(p: pathlib.Path):
    """Copy the contents of a <Link> section to a <Lib> section."""

    lines = []
    copy_lines = []
    copy_active = False

    with p.open('r') as fh:
        for line in fh:
            line = line.rstrip()

            lines.append(line)

            if '<Link>' in line:
                copy_active = True
                continue

            elif '</Link>' in line:
                copy_active = False

                log('duplicating <Link> section in %s' % p)
                lines.append('    <Lib>')
                lines.extend(copy_lines)
                lines.append('    </Lib>')

            if copy_active:
                copy_lines.append(line)

    with p.open('w') as fh:
        fh.write('\n'.join(lines))


def hack_props(td: pathlib.Path, pcbuild_path: pathlib.Path):
    # TODO can we pass props into msbuild.exe?

    # Our dependencies are in different directories from what CPython's
    # build system expects. Modify the config file appropriately.

    bzip2_version = DOWNLOADS['bzip2']['version']
    openssl_bin_version = DOWNLOADS['openssl-windows-bin']['version']
    sqlite_version = DOWNLOADS['sqlite']['version']
    xz_version = DOWNLOADS['xz']['version']
    zlib_version = DOWNLOADS['zlib']['version']
    tcltk_commit = DOWNLOADS['tk-windows-bin']['git_commit']

    sqlite_path = td / ('sqlite-autoconf-%s' % sqlite_version)
    bzip2_path = td / ('bzip2-%s' % bzip2_version)
    openssl_bin_path = td / ('cpython-bin-deps-openssl-bin-%s' % openssl_bin_version)
    tcltk_path = td / ('cpython-bin-deps-%s' % tcltk_commit)
    xz_path = td / ('xz-%s' % xz_version)
    zlib_path = td / ('zlib-%s' % zlib_version)

    python_props_path = pcbuild_path / 'python.props'
    lines = []

    with python_props_path.open('rb') as fh:
        for line in fh:
            line = line.rstrip()

            if b'<bz2Dir>' in line:
                line = b'<bz2Dir>%s\\</bz2Dir>' % bzip2_path

            elif b'<lzmaDir>' in line:
                line = b'<lzmaDir>%s\\</lzmaDir>' % xz_path

            # elif b'<opensslDir>' in line:
            #    line = b'<opensslDir>%s</opensslDir>' % openssl_bin_path,

            elif b'<opensslOutDir>' in line:
                line = b'<opensslOutDir>%s\\$(ArchName)\\</opensslOutDir>' % openssl_bin_path

            elif b'<sqlite3Dir>' in line:
                line = b'<sqlite3Dir>%s\\</sqlite3Dir>' % sqlite_path

            elif b'<zlibDir>' in line:
                line = b'<zlibDir>%s\\</zlibDir>' % zlib_path

            lines.append(line)

    with python_props_path.open('wb') as fh:
        fh.write(b'\n'.join(lines))

    tcltkprops_path = pcbuild_path / 'tcltk.props'

    static_replace_in_file(
        tcltkprops_path,
        br'<tcltkDir>$(ExternalsDir)tcltk-$(TclMajorVersion).$(TclMinorVersion).$(TclPatchLevel).$(TclRevision)\$(ArchName)\</tcltkDir>',
        br'<tcltkDir>%s\$(ArchName)\</tcltkDir>' % tcltk_path)


def hack_project_files(td: pathlib.Path, cpython_source_path: pathlib.Path):
    """Hacks Visual Studio project files to work with our build."""

    pcbuild_path = cpython_source_path / 'PCbuild'

    hack_props(td, pcbuild_path)

    # We need to copy linking settings for dynamic libraries to static libraries.
    copy_link_to_lib(pcbuild_path / 'openssl.props')

    # Our SQLite directory is named weirdly. This throws off version detection
    # in the project file. Replace the parsing logic with a static string.
    sqlite3_version = DOWNLOADS['sqlite']['actual_version'].encode('ascii')
    sqlite3_version_parts = sqlite3_version.split(b'.')
    sqlite3_path = pcbuild_path / 'sqlite3.vcxproj'
    static_replace_in_file(
        sqlite3_path,
        br'<_SqliteVersion>$([System.Text.RegularExpressions.Regex]::Match(`$(sqlite3Dir)`, `((\d+)\.(\d+)\.(\d+)\.(\d+))\\?$`).Groups)</_SqliteVersion>',
        br'<_SqliteVersion>%s</_SqliteVersion>' % sqlite3_version)
    static_replace_in_file(
        sqlite3_path,
        br'<SqliteVersion>$(_SqliteVersion.Split(`;`)[1])</SqliteVersion>',
        br'<SqliteVersion>%s</SqliteVersion>' % sqlite3_version)
    static_replace_in_file(
        sqlite3_path,
        br'<SqliteMajorVersion>$(_SqliteVersion.Split(`;`)[2])</SqliteMajorVersion>',
        br'<SqliteMajorVersion>%s</SqliteMajorVersion>' % sqlite3_version_parts[0])
    static_replace_in_file(
        sqlite3_path,
        br'<SqliteMinorVersion>$(_SqliteVersion.Split(`;`)[3])</SqliteMinorVersion>',
        br'<SqliteMinorVersion>%s</SqliteMinorVersion>' % sqlite3_version_parts[1])
    static_replace_in_file(
        sqlite3_path,
        br'<SqliteMicroVersion>$(_SqliteVersion.Split(`;`)[4])</SqliteMicroVersion>',
        br'<SqliteMicroVersion>%s</SqliteMicroVersion>' % sqlite3_version_parts[2])
    static_replace_in_file(
        sqlite3_path,
        br'<SqlitePatchVersion>$(_SqliteVersion.Split(`;`)[5])</SqlitePatchVersion>',
        br'<SqlitePatchVersion>%s</SqlitePatchVersion>' % sqlite3_version_parts[3])

    # Our version of the xz sources is newer than what's in cpython-source-deps
    # and the xz sources changed the path to config.h. Hack the project file
    # accordingly.
    liblzma_path = pcbuild_path / 'liblzma.vcxproj'
    static_replace_in_file(
        liblzma_path,
        br'$(lzmaDir)windows;$(lzmaDir)src/liblzma/common;',
        br'$(lzmaDir)windows\vs2017;$(lzmaDir)src/liblzma/common;')
    static_replace_in_file(
        liblzma_path,
        br'<ClInclude Include="$(lzmaDir)windows\config.h" />',
        br'<ClInclude Include="$(lzmaDir)windows\vs2017\config.h" />')

    for extension, entry in sorted(CONVERT_TO_BUILTIN_EXTENSIONS.items()):
        init_fn = entry.get('init', 'PyInit_%s' % extension)

        add_to_config_c(cpython_source_path, extension, init_fn)
        convert_to_static_library(cpython_source_path, extension, entry)

    # pythoncore.vcxproj produces libpython. Typically pythonXY.dll. We change
    # it to produce a static library.
    pythoncore_proj = pcbuild_path / 'pythoncore.vcxproj'

    # Need to replace Py_ENABLE_SHARED with Py_NO_ENABLE_SHARED so symbol
    # visibility is proper.

    # Replacing it in the global properties file has the most bang for our buck.
    pyproject_props = pcbuild_path / 'pyproject.props'
    static_replace_in_file(
        pyproject_props,
        b'<PreprocessorDefinitions>WIN32;',
        b'<PreprocessorDefinitions>Py_NO_ENABLE_SHARED;WIN32;')

    static_replace_in_file(pythoncore_proj, b'Py_ENABLE_SHARED', b'Py_NO_ENABLE_SHARED')

    # Make libpython a static library.
    static_replace_in_file(
        pythoncore_proj,
        b'<ConfigurationType>DynamicLibrary</ConfigurationType>',
        b'<ConfigurationType>StaticLibrary</ConfigurationType>')

    copy_link_to_lib(pythoncore_proj)

    # We don't need to produce pythonw.exe, python_uwp.exe, venvlauncher.exe,
    # and their *w variants. Cut them from the build to save time.

    pcbuild_proj = pcbuild_path / 'pcbuild.proj'

    static_replace_in_file(
        pcbuild_proj,
        b'<Projects2 Include="python.vcxproj;pythonw.vcxproj" />',
        b'<Projects2 Include="python.vcxproj" />'
    )
    static_replace_in_file(
        pcbuild_proj,
        b'<Projects2 Include="python_uwp.vcxproj;pythonw_uwp.vcxproj" Condition="$(IncludeUwp)" />',
        b'')
    static_replace_in_file(
        pcbuild_proj,
        b'<Projects2 Include="venvlauncher.vcxproj;venvwlauncher.vcxproj" />',
        b'')

    # Ditto for freeze_importlib, which isn't needed since we don't modify
    # the frozen importlib baked into the source distribution (
    # Python/importlib.h and Python/importlib_external.h).
    static_replace_in_file(
        pcbuild_proj,
        b'<Projects2 Include="_freeze_importlib.vcxproj" />',
        b'')

CTYPES_INIT_REPLACE = b'''
if _os.name == "nt":
    pythonapi = PyDLL("python dll", None, _sys.dllhandle)
elif _sys.platform == "cygwin":
    pythonapi = PyDLL("libpython%d.%d.dll" % _sys.version_info[:2])
else:
    pythonapi = PyDLL(None)
'''


def hack_source_files(source_path: pathlib.Path):
    """Apply source modifications to make things work."""

    # Modules/_winapi.c and Modules/overlapped.c both define an
    # ``OverlappedType`` symbol. We rename one to make the symbol conflict
    # go away.
    # TODO send this patch upstream.
    overlapped_c = source_path / 'Modules' / 'overlapped.c'
    static_replace_in_file(overlapped_c, b'OverlappedType', b'OOverlappedType')

    # Modules/ctypes/callbacks.c has lines like the following:
    # #ifndef Py_NO_ENABLE_SHARED
    # BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvRes)
    # We currently define Py_ENABLE_SHARED. And I /think/ this check should
    # also check against Py_BUILD_CORE_BUILTIN because Py_BUILD_CORE_BUILTIN
    # with Py_ENABLE_SHARED is theoretically a valid configuration.
    # TODO send this patch upstream.
    callbacks_c = source_path / 'Modules' / '_ctypes' / 'callbacks.c'
    static_replace_in_file(
        callbacks_c,
        b'#ifndef Py_NO_ENABLE_SHARED\nBOOL WINAPI DllMain(',
        b'#if !defined(Py_NO_ENABLE_SHARED) && !defined(Py_BUILD_CORE_BUILTIN)\nBOOL WINAPI DllMain(')

    # Lib/ctypes/__init__.py needs to populate the Python API version. On
    # Windows, it assumes a ``pythonXY`` is available. On Cygwin, a
    # ``libpythonXY`` DLL. The former assumes that ``sys.dllhandle`` is
    # available. And ``sys.dllhandle`` is only populated if ``MS_COREDLL``
    # (a deprecated symbol) is defined. And ``MS_COREDLL`` is not defined
    # if ``Py_NO_ENABLE_SHARED`` is defined. The gist of it is that ctypes
    # assumes that Python on Windows will use a Python DLL.
    #
    # The ``pythonapi`` handle obtained in ``ctypes/__init__.py`` needs to
    # expose a handle on the Python API. If we have a static library, that
    # handle should be the current binary. So all the fancy logic to find
    # the DLL can be simplified.
    #
    # But, ``PyDLL(None)`` doesn't work out of the box because this is
    # translated into a call to ``LoadLibrary(NULL)``. Unlike ``dlopen()``,
    # ``LoadLibrary()`` won't accept a NULL value. So, we need a way to
    # get an ``HMODULE`` for the current executable. Arguably the best way
    # to do this is with ``GetModuleHandleEx()`` using the following C code:
    #
    #   HMODULE hModule = NULL;
    #   GetModuleHandleEx(
    #     GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,
    #     (LPCSTR)SYMBOL_IN_CURRENT_MODULE,
    #     &hModule);
    #
    # The ``ctypes`` module has handles on function pointers in the current
    # binary. One would think we'd be able to use ``ctypes.cast()`` +
    # ``ctypes.addressof()`` to get a pointer to a symbol in the current
    # executable. But the addresses appear to be to heap allocated PyObject
    # instances, which won't work.
    #
    # An ideal solution would be to expose the ``HMODULE`` of the current
    # module. We /should/ be able to change the behavior of ``sys.dllhandle``
    # to facilitate this. But this is a bit more work. Our hack is to instead
    # use ``sys.executable`` with ``LoadLibrary()``. This should hopefully be
    # "good enough."
    #
    # TODO improve the logic upstream
    ctypes_init = source_path / 'Lib' / 'ctypes' / '__init__.py'
    static_replace_in_file(
        ctypes_init,
        CTYPES_INIT_REPLACE.strip(),
        b'pythonapi = PyDLL(_sys.executable)')

    # Producing statically linked binaries invalidates assumptions in the
    # layout tool. Update the tool accordingly.
    layout_main = source_path / 'PC' / 'layout' / 'main.py'

    # We no longer have a pythonXX.dll file.
    static_replace_in_file(
        layout_main,
        b'    yield from in_build(PYTHON_DLL_NAME)\n',
        b'')

    # We don't produce a pythonw.exe.
    static_replace_in_file(
        layout_main,
        b'        yield from in_build("pythonw.exe", new_name="pythonw")\n',
        b'')


def run_msbuild(msbuild: pathlib.Path, pcbuild_path: pathlib.Path,
                configuration: str):
    python_version = DOWNLOADS['cpython-3.7']['version']

    args = [
        str(msbuild),
        str(pcbuild_path / 'pcbuild.proj'),
        '/target:Build',
        '/property:Configuration=%s' % configuration,
        '/property:Platform=x64',
        '/maxcpucount',
        '/nologo',
        '/verbosity:minimal',
        '/property:IncludeExternals=true',
        '/property:IncludeSSL=true',
        # TODO support Tkinter
        '/property:IncludeTkinter=false',
        # TODO compile test extensions so we can get PGO benefits of tested code.
        '/property:IncludeTests=false',
        '/property:OverrideVersion=%s' % python_version,
    ]

    exec_and_log(args, str(pcbuild_path), os.environ)


def build_openssl_for_arch(perl_path, arch: str, openssl_archive, nasm_archive,
                           build_root: pathlib.Path):
    openssl_version = DOWNLOADS['openssl']['version']
    nasm_version = DOWNLOADS['nasm-windows-bin']['version']


    log('extracting %s to %s' % (openssl_archive, build_root))
    extract_tar_to_directory(openssl_archive, build_root)
    log('extracting %s to %s' % (nasm_archive, build_root))
    extract_tar_to_directory(nasm_archive, build_root)

    nasm_path = build_root / ('cpython-bin-deps-nasm-%s' % nasm_version)

    env = dict(os.environ)
    # Add Perl and nasm paths to front of PATH.
    env['PATH'] = '%s;%s;%s' % (
        perl_path.parent,
        nasm_path,
        env['PATH'],
    )

    source_root = build_root / ('openssl-%s' % openssl_version)

    if arch == 'x86':
        configure = 'VC-WIN32'
        prefix = '32'
    elif arch == 'amd64':
        configure = 'VC-WIN64A'
        prefix = '64'
    else:
        print('invalid architecture: %s' % arch)
        sys.exit(1)

    # The official CPython OpenSSL builds hack ms/uplink.c to change the
    # ``GetModuleHandle(NULL)`` invocation to load things from _ssl.pyd
    # instead. But since we statically link the _ssl extension, this hackery
    # is not required.

    # Set DESTDIR to affect install location.
    dest_dir = build_root / 'install'
    env['DESTDIR'] = str(dest_dir)
    install_root = dest_dir / prefix

    exec_and_log([str(perl_path), 'Configure', configure, 'no-idea', 'no-mdc2',
                  '--prefix=/%s' % prefix], source_root, env)
    exec_and_log(['nmake'], source_root, env)

    # We don't care about accessory files, docs, etc. So just run `install_sw`
    # target to get the main files.
    exec_and_log(['nmake', 'install_sw'], source_root, env)

    # Copy the _static libraries as well.
    for l in ('crypto', 'ssl'):
        basename = 'lib%s_static.lib' % l
        source = source_root / basename
        dest = install_root / 'lib' / basename
        log('copying %s to %s' % (source, dest))
        shutil.copyfile(source, dest)


def build_openssl(perl_path: pathlib.Path):
    """Build OpenSSL from sources using the Perl executable specified."""

    # First ensure the dependencies are in place.
    openssl_archive = download_entry('openssl', BUILD)
    nasm_archive = download_entry('nasm-windows-bin', BUILD)

    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)

        root_32 = td / 'x86'
        root_64 = td / 'x64'
        root_32.mkdir()
        root_64.mkdir()

        # Then build the 32 and 64 bit OpenSSL installs in parallel
        # (because nmake doesn't do parallel builds).
        # TODO we need to adjust the environment to pull in a x86 toolchain
        # in order for this to work.
        fs = []
        with concurrent.futures.ThreadPoolExecutor(2) as e:
            #fs.append(e.submit(build_openssl_for_arch, perl_path, 'x86',
            #                   openssl_archive, nasm_archive, root_32))
            fs.append(e.submit(build_openssl_for_arch, perl_path, 'amd64',
                               openssl_archive, nasm_archive, root_64))

        for f in fs:
            f.result()

        install = td / 'out'
        #shutil.copytree(root_32 / 'install' / '32', install / 'openssl' / 'win32')
        shutil.copytree(root_64 / 'install' / '64', install / 'openssl' / 'amd64')

        dest_archive = BUILD / 'openssl-windows.tar'
        with dest_archive.open('wb') as fh:
            create_tar_from_directory(fh, install)


def build_cpython(pgo=False):
    msbuild = find_msbuild()
    log('found MSBuild at %s' % msbuild)

    # The python.props file keys off MSBUILD, so it needs to be set.
    os.environ['MSBUILD'] = str(msbuild)

    activeperl_installer = download_entry('activeperl', BUILD)
    bzip2_archive = download_entry('bzip2', BUILD)
    #openssl_archive = download_entry('openssl', BUILD)
    openssl_bin_archive = download_entry('openssl-windows-bin', BUILD)
    sqlite_archive = download_entry('sqlite', BUILD)
    tk_bin_archive = download_entry('tk-windows-bin', BUILD, local_name='tk-windows-bin.tar.gz')
    xz_archive = download_entry('xz', BUILD)
    zlib_archive = download_entry('zlib', BUILD)

    python_archive = download_entry('cpython-3.7', BUILD)

    python_version = DOWNLOADS['cpython-3.7']['version']

    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)

        with concurrent.futures.ThreadPoolExecutor(7) as e:
            for a in (python_archive, bzip2_archive, openssl_bin_archive,
                      sqlite_archive, tk_bin_archive, xz_archive, zlib_archive):
                log('extracting %s to %s' % (a, td))
                e.submit(extract_tar_to_directory, a, td)

        cpython_source_path = td / ('Python-%s' % python_version)
        pcbuild_path = cpython_source_path / 'PCBuild'

        hack_project_files(td, cpython_source_path)
        hack_source_files(cpython_source_path)

        if pgo:
            run_msbuild(msbuild, pcbuild_path, configuration='PGInstrument')

            exec_and_log([
                str(cpython_source_path / 'python.bat'), '-m', 'test', '--pgo'],
                str(pcbuild_path),
                os.environ,
                exit_on_error=False)

            exec_and_log(
                [
                    str(msbuild), str(pcbuild_path / 'pythoncore.vcxproj'),
                    '/target:KillPython',
                    '/verbosity:minimal',
                    '/property:Configuration=PGInstrument',
                    '/property:Platform=x64',
                    '/property:KillPython=true',
                ],
                pcbuild_path,
                os.environ)

            run_msbuild(msbuild, pcbuild_path, configuration='PGUpdate')

        else:
            run_msbuild(msbuild, pcbuild_path, configuration='Release')

        out_dir = td / 'out'
        install_dir = out_dir / 'python' / 'install'

        # The PC/layout directory contains a script for copying files into
        # a release-like directory. Use that for assembling the standalone
        # build.

        # It doesn't clean up the temp directory it creates. So pass one to it
        # under our tempdir.
        layout_tmp = td / 'layouttmp'
        layout_tmp.mkdir()

        exec_and_log(
            [
                str(cpython_source_path / 'python.bat'),
                str(cpython_source_path / 'PC' / 'layout'),
                '--source', str(cpython_source_path),
                '--copy', str(install_dir),
                '--temp', str(layout_tmp),
                '--flat-dlls',
                '--include-dev',
                '--include-distutils',
            ],
            pcbuild_path,
            os.environ)

        dest_path = BUILD / 'cpython-windows.tar'

        with dest_path.open('wb') as fh:
            create_tar_from_directory(fh, td / 'out')


def main():
    BUILD.mkdir(exist_ok=True)

    log_path = BUILD / 'build.log'

    with log_path.open('wb') as log_fh:
        LOG_FH[0] = log_fh

        # TODO need better dependency checking.
        openssl_out = BUILD / 'openssl-windows.tar'
        if not openssl_out.exists():
            LOG_PREFIX[0] = 'openssl'
            build_openssl(pathlib.Path(os.environ['PERL']))

        LOG_PREFIX[0] = 'cpython'
        build_cpython()

if __name__ == '__main__':
    sys.exit(main())
