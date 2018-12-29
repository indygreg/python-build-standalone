#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import pathlib
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
        print('search string (%s) not in %s' % (search, p))
        sys.exit(1)

    data = data.replace(search, replace)

    with p.open('wb') as fh:
        fh.write(data)

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


def hack_project_files(td: pathlib.Path, pcbuild_path: pathlib.Path):
    """Hacks Visual Studio project files to work with our build."""

    hack_props(td, pcbuild_path)

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
        '/property:IncludeTkinter=true',
        '/property:OverrideVersion=%s' % python_version,
    ]

    exec_and_log(args, str(pcbuild_path), os.environ)


def build_cpython(pgo=False):
    msbuild = find_msbuild()
    log('found MSBuild at %s' % msbuild)

    # The python.props file keys off MSBUILD, so it needs to be set.
    os.environ['MSBUILD'] = str(msbuild)

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

        log('extracting CPython sources to %s' % td)
        extract_tar_to_directory(python_archive, td)

        for a in (bzip2_archive, openssl_bin_archive, sqlite_archive,
                  tk_bin_archive, xz_archive, zlib_archive):
            log('extracting %s to %s' % (a, td))
            extract_tar_to_directory(a, td)

        cpython_source_path = td / ('Python-%s' % python_version)
        pcbuild_path = cpython_source_path / 'PCBuild'

        hack_project_files(td, pcbuild_path)

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
        exec_and_log(
            [
                str(cpython_source_path / 'python.bat'),
                str(cpython_source_path / 'PC' / 'layout'),
                '--source', str(cpython_source_path),
                '--copy', str(install_dir),
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
    LOG_PREFIX[0] = 'cpython'

    with log_path.open('wb') as log_fh:
        LOG_FH[0] = log_fh

        build_cpython()

if __name__ == '__main__':
    sys.exit(main())
