#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import argparse
import concurrent.futures
import io
import json
import multiprocessing
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

from pythonbuild.cpython import (
    STDLIB_TEST_PACKAGES,
    meets_python_minimum_version,
    parse_config_c,
)
from pythonbuild.downloads import DOWNLOADS
from pythonbuild.utils import (
    compress_python_archive,
    create_tar_from_directory,
    download_entry,
    extract_tar_to_directory,
    extract_zip_to_directory,
    normalize_tar_archive,
    release_tag_from_git,
    validate_python_json,
)

ROOT = pathlib.Path(os.path.abspath(__file__)).parent.parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"
SUPPORT = ROOT / "cpython-windows"

LOG_PREFIX = [None]
LOG_FH = [None]

# Extensions that need to be converted from standalone to built-in.
# Key is name of VS project representing the standalone extension.
# Value is dict describing the extension.
CONVERT_TO_BUILTIN_EXTENSIONS = {
    "_asyncio": {
        # _asynciomodule.c is included in pythoncore for some reason.
        # This was fixed in Python 3.9. See hacky code for
        # `honor_allow_missing_preprocessor`.
        "allow_missing_preprocessor": True
    },
    "_bz2": {},
    "_ctypes": {
        "shared_depends": ["libffi-8"],
    },
    "_decimal": {},
    "_elementtree": {},
    "_hashlib": {
        "shared_depends_amd64": ["libcrypto-1_1-x64"],
        "shared_depends_win32": ["libcrypto-1_1"],
    },
    "_lzma": {
        "ignore_additional_depends": {"$(OutDir)liblzma$(PyDebugExt).lib"},
    },
    "_msi": {},
    "_overlapped": {},
    "_multiprocessing": {},
    "_socket": {},
    "_sqlite3": {"shared_depends": ["sqlite3"]},
    # See the one-off calls to copy_link_to_lib() and elsewhere to hack up
    # project files.
    "_ssl": {
        "shared_depends_amd64": ["libcrypto-1_1-x64", "libssl-1_1-x64"],
        "shared_depends_win32": ["libcrypto-1_1", "libssl-1_1"],
    },
    "_tkinter": {
        "shared_depends": ["tcl86t", "tk86t"],
    },
    "_queue": {},
    "_uuid": {"ignore_missing": True},
    "_wmi": {
        # Introduced in 3.12.
        "ignore_missing": True,
    },
    "_zoneinfo": {"ignore_missing": True},
    "pyexpat": {},
    "select": {},
    "unicodedata": {},
    "winsound": {},
}

REQUIRED_EXTENSIONS = {
    "_codecs",
    "_io",
    "_signal",
    "_thread",
    "_tracemalloc",
    "_weakref",
    "faulthandler",
}

# Used to annotate licenses.
EXTENSION_TO_LIBRARY_DOWNLOADS_ENTRY = {
    "_bz2": ["bzip2"],
    "_ctypes": ["libffi"],
    "_hashlib": ["openssl"],
    "_lzma": ["xz"],
    "_sqlite3": ["sqlite"],
    "_ssl": ["openssl"],
    "_tkinter": ["tcl", "tk", "tix"],
    "_uuid": ["uuid"],
    "zlib": ["zlib"],
}


# Tests to run during PGO profiling.
#
# This set was copied from test.libregrtest.pgo in the CPython source
# distribution.
PGO_TESTS = {
    "test_array",
    "test_base64",
    "test_binascii",
    "test_binop",
    "test_bisect",
    "test_bytes",
    "test_bz2",
    "test_cmath",
    "test_codecs",
    "test_collections",
    "test_complex",
    "test_dataclasses",
    "test_datetime",
    "test_decimal",
    "test_difflib",
    "test_embed",
    "test_float",
    "test_fstring",
    "test_functools",
    "test_generators",
    "test_hashlib",
    "test_heapq",
    "test_int",
    "test_itertools",
    "test_json",
    "test_long",
    "test_lzma",
    "test_math",
    "test_memoryview",
    "test_operator",
    "test_ordered_dict",
    "test_pickle",
    "test_pprint",
    "test_re",
    "test_set",
    # Renamed to test_sqlite3 in 3.11. We keep both names as we just look for
    # test presence in this set.
    "test_sqlite",
    "test_sqlite3",
    "test_statistics",
    "test_struct",
    "test_tabnanny",
    "test_time",
    "test_unicode",
    "test_xml_etree",
    "test_xml_etree_c",
}


def log(msg):
    if isinstance(msg, bytes):
        msg_str = msg.decode("utf-8", "replace")
        msg_bytes = msg
    else:
        msg_str = msg
        msg_bytes = msg.encode("utf-8", "replace")

    print("%s> %s" % (LOG_PREFIX[0], msg_str))

    if LOG_FH[0]:
        LOG_FH[0].write(msg_bytes + b"\n")
        LOG_FH[0].flush()


def exec_and_log(args, cwd, env, exit_on_error=True):
    log("executing %s" % " ".join(args))

    p = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        bufsize=1,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    for line in iter(p.stdout.readline, b""):
        log(line.rstrip())

    p.wait()

    log("process exited %d" % p.returncode)

    if p.returncode and exit_on_error:
        sys.exit(p.returncode)


def find_vswhere():
    vswhere = (
        pathlib.Path(os.environ["ProgramFiles(x86)"])
        / "Microsoft Visual Studio"
        / "Installer"
        / "vswhere.exe"
    )

    if not vswhere.exists():
        print("%s does not exist" % vswhere)
        sys.exit(1)

    return vswhere


def find_vs_path(path, msvc_version):
    vswhere = find_vswhere()

    if msvc_version == "2019":
        version = "[16,17)"
    elif msvc_version == "2022":
        version = "[17,18)"
    else:
        raise ValueError(f"unsupported Visual Studio version: {msvc_version}")

    p = subprocess.check_output(
        [
            str(vswhere),
            # Visual Studio 2019.
            "-version",
            version,
            "-property",
            "installationPath",
            "-products",
            "*",
        ]
    )

    # Strictly speaking the output may not be UTF-8.
    p = pathlib.Path(p.strip().decode("utf-8"))

    p = p / path

    if not p.exists():
        print("%s does not exist" % p)
        sys.exit(1)

    return p


def find_msbuild(msvc_version):
    return find_vs_path(
        pathlib.Path("MSBuild") / "Current" / "Bin" / "MSBuild.exe", msvc_version
    )


def find_vcvarsall_path(msvc_version):
    """Find path to vcvarsall.bat"""
    return find_vs_path(
        pathlib.Path("VC") / "Auxiliary" / "Build" / "vcvarsall.bat", msvc_version
    )


class NoSearchStringError(Exception):
    """Represents a missing search string when replacing content in a file."""


def static_replace_in_file(p: pathlib.Path, search, replace):
    """Replace occurrences of a string in a file.

    The updated file contents are written out in place.
    """

    with p.open("rb") as fh:
        data = fh.read()

    # Build should be as deterministic as possible. Assert that wanted changes
    # actually occur.
    if search not in data:
        raise NoSearchStringError("search string (%s) not in %s" % (search, p))

    log("replacing `%s` with `%s` in %s" % (search, replace, p))
    data = data.replace(search, replace)

    with p.open("wb") as fh:
        fh.write(data)


OPENSSL_PROPS_REMOVE_RULES_LEGACY = b"""
  <ItemGroup>
    <_SSLDLL Include="$(opensslOutDir)\libcrypto$(_DLLSuffix).dll" />
    <_SSLDLL Include="$(opensslOutDir)\libcrypto$(_DLLSuffix).pdb" />
    <_SSLDLL Include="$(opensslOutDir)\libssl$(_DLLSuffix).dll" />
    <_SSLDLL Include="$(opensslOutDir)\libssl$(_DLLSuffix).pdb" />
  </ItemGroup>
  <Target Name="_CopySSLDLL" Inputs="@(_SSLDLL)" Outputs="@(_SSLDLL->'$(OutDir)%(Filename)%(Extension)')" AfterTargets="Build">
    <Copy SourceFiles="@(_SSLDLL)" DestinationFolder="$(OutDir)" />
  </Target>
  <Target Name="_CleanSSLDLL" BeforeTargets="Clean">
    <Delete Files="@(_SSLDLL->'$(OutDir)%(Filename)%(Extension)')" TreatErrorsAsWarnings="true" />
  </Target>
"""

OPENSSL_PROPS_REMOVE_RULES = b"""
  <ItemGroup>
    <_SSLDLL Include="$(opensslOutDir)\libcrypto$(_DLLSuffix).dll" />
    <_SSLDLL Include="$(opensslOutDir)\libcrypto$(_DLLSuffix).pdb" />
    <_SSLDLL Include="$(opensslOutDir)\libssl$(_DLLSuffix).dll" />
    <_SSLDLL Include="$(opensslOutDir)\libssl$(_DLLSuffix).pdb" />
  </ItemGroup>
  <Target Name="_CopySSLDLL"
          Inputs="@(_SSLDLL)"
          Outputs="@(_SSLDLL->'$(OutDir)%(Filename)%(Extension)')"
          Condition="$(SkipCopySSLDLL) == ''"
          AfterTargets="Build">
    <Copy SourceFiles="@(_SSLDLL)" DestinationFolder="$(OutDir)" />
  </Target>
  <Target Name="_CleanSSLDLL" Condition="$(SkipCopySSLDLL) == ''" BeforeTargets="Clean">
    <Delete Files="@(_SSLDLL->'$(OutDir)%(Filename)%(Extension)')" TreatErrorsAsWarnings="true" />
  </Target>
"""

LIBFFI_PROPS_REMOVE_RULES = b"""
  <Target Name="_CopyLIBFFIDLL" Inputs="@(_LIBFFIDLL)" Outputs="@(_LIBFFIDLL->'$(OutDir)%(Filename)%(Extension)')" AfterTargets="Build">
    <Copy SourceFiles="@(_LIBFFIDLL)" DestinationFolder="$(OutDir)" />
  </Target>
"""


def hack_props(
    td: pathlib.Path,
    pcbuild_path: pathlib.Path,
    arch: str,
):
    # TODO can we pass props into msbuild.exe?

    # Our dependencies are in different directories from what CPython's
    # build system expects. Modify the config file appropriately.

    bzip2_version = DOWNLOADS["bzip2"]["version"]
    sqlite_version = DOWNLOADS["sqlite"]["version"]
    xz_version = DOWNLOADS["xz"]["version"]
    zlib_version = DOWNLOADS["zlib"]["version"]
    tcltk_commit = DOWNLOADS["tk-windows-bin"]["git_commit"]

    sqlite_path = td / ("sqlite-autoconf-%s" % sqlite_version)
    bzip2_path = td / ("bzip2-%s" % bzip2_version)
    libffi_path = td / "libffi"
    tcltk_path = td / ("cpython-bin-deps-%s" % tcltk_commit)
    xz_path = td / ("xz-%s" % xz_version)
    zlib_path = td / ("zlib-%s" % zlib_version)

    openssl_root = td / "openssl" / arch
    openssl_libs_path = openssl_root / "lib"
    openssl_include_path = openssl_root / "include"

    python_props_path = pcbuild_path / "python.props"
    lines = []

    with python_props_path.open("rb") as fh:
        for line in fh:
            line = line.rstrip()

            # The syntax of these lines changed in 3.10+. 3.10 backport commit
            # 3139ea33ed84190e079d6ff4859baccdad778dae. Once we drop support for
            # Python 3.9 we can pass these via properties instead of editing the
            # properties file.
            if b"<bz2Dir" in line:
                line = b"<bz2Dir>%s\\</bz2Dir>" % bzip2_path

            elif b"<libffiOutDir" in line:
                line = b"<libffiOutDir>%s\\</libffiOutDir>" % libffi_path

            elif b"<lzmaDir" in line:
                line = b"<lzmaDir>%s\\</lzmaDir>" % xz_path

            elif b"<opensslIncludeDir" in line:
                line = (
                    b"<opensslIncludeDir>%s</opensslIncludeDir>" % openssl_include_path
                )

            elif b"<opensslOutDir" in line:
                line = b"<opensslOutDir>%s\\</opensslOutDir>" % openssl_libs_path

            elif b"<sqlite3Dir" in line:
                line = b"<sqlite3Dir>%s\\</sqlite3Dir>" % sqlite_path

            elif b"<zlibDir" in line:
                line = b"<zlibDir>%s\\</zlibDir>" % zlib_path

            lines.append(line)

    with python_props_path.open("wb") as fh:
        fh.write(b"\n".join(lines))

    tcltkprops_path = pcbuild_path / "tcltk.props"

    # Later versions of 3.10 and 3.11 enabled support for defining paths via properties.
    # See CPython commit 3139ea33ed84190e079d6ff4859baccdad778dae.
    # Once we drop support for CPython 3.9 we can replace this with passing properties.
    try:
        static_replace_in_file(
            tcltkprops_path,
            rb"""<tcltkDir Condition="$(tcltkDir) == ''">$(ExternalsDir)tcltk-$(TclVersion)\$(ArchName)\</tcltkDir>""",
            rb"<tcltkDir>%s\$(ArchName)\</tcltkDir>" % tcltk_path,
        )
    except NoSearchStringError:
        static_replace_in_file(
            tcltkprops_path,
            rb"<tcltkDir>$(ExternalsDir)tcltk-$(TclMajorVersion).$(TclMinorVersion).$(TclPatchLevel).$(TclRevision)\$(ArchName)\</tcltkDir>",
            rb"<tcltkDir>%s\$(ArchName)\</tcltkDir>" % tcltk_path,
        )

    # We want to statically link against OpenSSL. This requires using our own
    # OpenSSL build. This requires some hacking of various files.
    openssl_props = pcbuild_path / "openssl.props"

    if arch == "amd64":
        suffix = b"-x64"
    elif arch == "win32":
        suffix = b""
    else:
        raise Exception("unhandled architecture: %s" % arch)

    try:
        # CPython 3.11+ builds with OpenSSL 3.0 by default.
        static_replace_in_file(
            openssl_props,
            b"<_DLLSuffix>-3</_DLLSuffix>",
            b"<_DLLSuffix>-3%s</_DLLSuffix>" % suffix,
        )
    except NoSearchStringError:
        static_replace_in_file(
            openssl_props,
            b"<_DLLSuffix>-1_1</_DLLSuffix>",
            b"<_DLLSuffix>-1_1%s</_DLLSuffix>" % suffix,
        )

    libffi_props = pcbuild_path / "libffi.props"

    # Always use libffi-8 / 3.4.2. (Python < 3.11 use libffi-7 by default.)
    try:
        static_replace_in_file(
            libffi_props,
            rb"""<_LIBFFIDLL Include="$(libffiOutDir)\libffi-7.dll" />""",
            rb"""<_LIBFFIDLL Include="$(libffiOutDir)\libffi-8.dll" />""",
        )
        static_replace_in_file(
            libffi_props,
            rb"<AdditionalDependencies>libffi-7.lib;%(AdditionalDependencies)</AdditionalDependencies>",
            rb"<AdditionalDependencies>libffi-8.lib;%(AdditionalDependencies)</AdditionalDependencies>",
        )
    except NoSearchStringError:
        pass


def hack_project_files(
    td: pathlib.Path,
    cpython_source_path: pathlib.Path,
    build_directory: str,
    python_version: str,
):
    """Hacks Visual Studio project files to work with our build."""

    pcbuild_path = cpython_source_path / "PCbuild"

    hack_props(
        td,
        pcbuild_path,
        build_directory,
    )

    # Our SQLite directory is named weirdly. This throws off version detection
    # in the project file. Replace the parsing logic with a static string.
    sqlite3_version = DOWNLOADS["sqlite"]["actual_version"].encode("ascii")
    sqlite3_version_parts = sqlite3_version.split(b".")
    sqlite3_path = pcbuild_path / "sqlite3.vcxproj"
    static_replace_in_file(
        sqlite3_path,
        rb"<_SqliteVersion>$([System.Text.RegularExpressions.Regex]::Match(`$(sqlite3Dir)`, `((\d+)\.(\d+)\.(\d+)\.(\d+))\\?$`).Groups)</_SqliteVersion>",
        rb"<_SqliteVersion>%s</_SqliteVersion>" % sqlite3_version,
    )
    static_replace_in_file(
        sqlite3_path,
        rb"<SqliteVersion>$(_SqliteVersion.Split(`;`)[1])</SqliteVersion>",
        rb"<SqliteVersion>%s</SqliteVersion>" % sqlite3_version,
    )
    static_replace_in_file(
        sqlite3_path,
        rb"<SqliteMajorVersion>$(_SqliteVersion.Split(`;`)[2])</SqliteMajorVersion>",
        rb"<SqliteMajorVersion>%s</SqliteMajorVersion>" % sqlite3_version_parts[0],
    )
    static_replace_in_file(
        sqlite3_path,
        rb"<SqliteMinorVersion>$(_SqliteVersion.Split(`;`)[3])</SqliteMinorVersion>",
        rb"<SqliteMinorVersion>%s</SqliteMinorVersion>" % sqlite3_version_parts[1],
    )
    static_replace_in_file(
        sqlite3_path,
        rb"<SqliteMicroVersion>$(_SqliteVersion.Split(`;`)[4])</SqliteMicroVersion>",
        rb"<SqliteMicroVersion>%s</SqliteMicroVersion>" % sqlite3_version_parts[2],
    )
    static_replace_in_file(
        sqlite3_path,
        rb"<SqlitePatchVersion>$(_SqliteVersion.Split(`;`)[5])</SqlitePatchVersion>",
        rb"<SqlitePatchVersion>%s</SqlitePatchVersion>" % sqlite3_version_parts[3],
    )

    # Our version of the xz sources is newer than what's in cpython-source-deps
    # and the xz sources changed the path to config.h. Hack the project file
    # accordingly.
    #
    # ... but CPython finally upgraded liblzma in 2022, so newer CPython releases
    # already have this patch. So we're phasing it out.
    try:
        liblzma_path = pcbuild_path / "liblzma.vcxproj"
        static_replace_in_file(
            liblzma_path,
            rb"$(lzmaDir)windows;$(lzmaDir)src/liblzma/common;",
            rb"$(lzmaDir)windows\vs2019;$(lzmaDir)src/liblzma/common;",
        )
        static_replace_in_file(
            liblzma_path,
            rb'<ClInclude Include="$(lzmaDir)windows\config.h" />',
            rb'<ClInclude Include="$(lzmaDir)windows\vs2019\config.h" />',
        )
    except NoSearchStringError:
        pass

    # Our logic for rewriting extension projects gets confused by _sqlite.vcxproj not
    # having a `<PreprocessorDefinitions>` line in 3.10+. So adjust that.
    try:
        static_replace_in_file(
            pcbuild_path / "_sqlite3.vcxproj",
            rb"<AdditionalIncludeDirectories>$(sqlite3Dir);%(AdditionalIncludeDirectories)</AdditionalIncludeDirectories>",
            b"<AdditionalIncludeDirectories>$(sqlite3Dir);%(AdditionalIncludeDirectories)</AdditionalIncludeDirectories>\r\n      <PreprocessorDefinitions>%(PreprocessorDefinitions)</PreprocessorDefinitions>",
        )
    except NoSearchStringError:
        pass

    # Our custom OpenSSL build has applink.c in a different location
    # from the binary OpenSSL distribution. Update it.
    ssl_proj = pcbuild_path / "_ssl.vcxproj"
    static_replace_in_file(
        ssl_proj,
        rb'<ClCompile Include="$(opensslIncludeDir)\applink.c">',
        rb'<ClCompile Include="$(opensslIncludeDir)\openssl\applink.c">',
    )

    # We're still on the pre-built tk-windows-bin 8.6.14 which doesn't have a
    # standalone zlib DLL. So remove references to it from 3.12+.
    if meets_python_minimum_version(python_version, "3.12"):
        static_replace_in_file(
            pcbuild_path / "_tkinter.vcxproj",
            rb'<_TclTkDLL Include="$(tcltkdir)\bin\$(tclZlibDllName)" />',
            rb"",
        )

    # We don't need to produce python_uwp.exe and its *w variant. Or the
    # python3.dll, pyshellext, or pylauncher.
    # Cut them from the build to save time and so their presence doesn't
    # interfere with packaging up the build artifacts.

    pcbuild_proj = pcbuild_path / "pcbuild.proj"

    static_replace_in_file(
        pcbuild_proj,
        b'<Projects2 Include="python_uwp.vcxproj;pythonw_uwp.vcxproj" Condition="$(IncludeUwp)" />',
        b"",
    )
    static_replace_in_file(
        pcbuild_proj,
        b'<Projects Include="pylauncher.vcxproj;pywlauncher.vcxproj" />',
        b"",
    )
    static_replace_in_file(
        pcbuild_proj, b'<Projects Include="pyshellext.vcxproj" />', b""
    )

    # Ditto for freeze_importlib, which isn't needed since we don't modify
    # the frozen importlib baked into the source distribution (
    # Python/importlib.h and Python/importlib_external.h).
    #
    # But Python 3.11 refactored the frozen module project handling and if
    # we attempt to disable this project there we get a build failure due to
    # a missing /Python/frozen_modules/getpath.h file. So we skip this on
    # newer Python.
    try:
        static_replace_in_file(
            pcbuild_proj,
            b"""<Projects2 Condition="$(Platform) != 'ARM' and $(Platform) != 'ARM64'" Include="_freeze_importlib.vcxproj" />""",
            b"",
        )
    except NoSearchStringError:
        pass


PYPORT_EXPORT_SEARCH_39 = b"""
#if defined(__CYGWIN__)
#       define HAVE_DECLSPEC_DLL
#endif

#include "exports.h"

/* only get special linkage if built as shared or platform is Cygwin */
#if defined(Py_ENABLE_SHARED) || defined(__CYGWIN__)
#       if defined(HAVE_DECLSPEC_DLL)
#               if defined(Py_BUILD_CORE) && !defined(Py_BUILD_CORE_MODULE)
#                       define PyAPI_FUNC(RTYPE) Py_EXPORTED_SYMBOL RTYPE
#                       define PyAPI_DATA(RTYPE) extern Py_EXPORTED_SYMBOL RTYPE
        /* module init functions inside the core need no external linkage */
        /* except for Cygwin to handle embedding */
#                       if defined(__CYGWIN__)
#                               define PyMODINIT_FUNC Py_EXPORTED_SYMBOL PyObject*
#                       else /* __CYGWIN__ */
#                               define PyMODINIT_FUNC PyObject*
#                       endif /* __CYGWIN__ */
#               else /* Py_BUILD_CORE */
        /* Building an extension module, or an embedded situation */
        /* public Python functions and data are imported */
        /* Under Cygwin, auto-import functions to prevent compilation */
        /* failures similar to those described at the bottom of 4.1: */
        /* http://docs.python.org/extending/windows.html#a-cookbook-approach */
#                       if !defined(__CYGWIN__)
#                               define PyAPI_FUNC(RTYPE) Py_IMPORTED_SYMBOL RTYPE
#                       endif /* !__CYGWIN__ */
#                       define PyAPI_DATA(RTYPE) extern Py_IMPORTED_SYMBOL RTYPE
        /* module init functions outside the core must be exported */
#                       if defined(__cplusplus)
#                               define PyMODINIT_FUNC extern "C" Py_EXPORTED_SYMBOL PyObject*
#                       else /* __cplusplus */
#                               define PyMODINIT_FUNC Py_EXPORTED_SYMBOL PyObject*
#                       endif /* __cplusplus */
#               endif /* Py_BUILD_CORE */
#       endif /* HAVE_DECLSPEC_DLL */
#endif /* Py_ENABLE_SHARED */

/* If no external linkage macros defined by now, create defaults */
#ifndef PyAPI_FUNC
#       define PyAPI_FUNC(RTYPE) Py_EXPORTED_SYMBOL RTYPE
#endif
#ifndef PyAPI_DATA
#       define PyAPI_DATA(RTYPE) extern Py_EXPORTED_SYMBOL RTYPE
#endif
#ifndef PyMODINIT_FUNC
#       if defined(__cplusplus)
#               define PyMODINIT_FUNC extern "C" Py_EXPORTED_SYMBOL PyObject*
#       else /* __cplusplus */
#               define PyMODINIT_FUNC Py_EXPORTED_SYMBOL PyObject*
#       endif /* __cplusplus */
#endif
"""

PYPORT_EXPORT_SEARCH_38 = b"""
#if defined(__CYGWIN__)
#       define HAVE_DECLSPEC_DLL
#endif

/* only get special linkage if built as shared or platform is Cygwin */
#if defined(Py_ENABLE_SHARED) || defined(__CYGWIN__)
#       if defined(HAVE_DECLSPEC_DLL)
#               if defined(Py_BUILD_CORE) && !defined(Py_BUILD_CORE_MODULE)
#                       define PyAPI_FUNC(RTYPE) __declspec(dllexport) RTYPE
#                       define PyAPI_DATA(RTYPE) extern __declspec(dllexport) RTYPE
        /* module init functions inside the core need no external linkage */
        /* except for Cygwin to handle embedding */
#                       if defined(__CYGWIN__)
#                               define PyMODINIT_FUNC __declspec(dllexport) PyObject*
#                       else /* __CYGWIN__ */
#                               define PyMODINIT_FUNC PyObject*
#                       endif /* __CYGWIN__ */
#               else /* Py_BUILD_CORE */
        /* Building an extension module, or an embedded situation */
        /* public Python functions and data are imported */
        /* Under Cygwin, auto-import functions to prevent compilation */
        /* failures similar to those described at the bottom of 4.1: */
        /* http://docs.python.org/extending/windows.html#a-cookbook-approach */
#                       if !defined(__CYGWIN__)
#                               define PyAPI_FUNC(RTYPE) __declspec(dllimport) RTYPE
#                       endif /* !__CYGWIN__ */
#                       define PyAPI_DATA(RTYPE) extern __declspec(dllimport) RTYPE
        /* module init functions outside the core must be exported */
#                       if defined(__cplusplus)
#                               define PyMODINIT_FUNC extern "C" __declspec(dllexport) PyObject*
#                       else /* __cplusplus */
#                               define PyMODINIT_FUNC __declspec(dllexport) PyObject*
#                       endif /* __cplusplus */
#               endif /* Py_BUILD_CORE */
#       endif /* HAVE_DECLSPEC_DLL */
#endif /* Py_ENABLE_SHARED */

/* If no external linkage macros defined by now, create defaults */
#ifndef PyAPI_FUNC
#       define PyAPI_FUNC(RTYPE) RTYPE
#endif
#ifndef PyAPI_DATA
#       define PyAPI_DATA(RTYPE) extern RTYPE
#endif
#ifndef PyMODINIT_FUNC
#       if defined(__cplusplus)
#               define PyMODINIT_FUNC extern "C" PyObject*
#       else /* __cplusplus */
#               define PyMODINIT_FUNC PyObject*
#       endif /* __cplusplus */
#endif
"""

PYPORT_EXPORT_SEARCH_37 = b"""
#if defined(__CYGWIN__)
#       define HAVE_DECLSPEC_DLL
#endif

/* only get special linkage if built as shared or platform is Cygwin */
#if defined(Py_ENABLE_SHARED) || defined(__CYGWIN__)
#       if defined(HAVE_DECLSPEC_DLL)
#               if defined(Py_BUILD_CORE) || defined(Py_BUILD_CORE_BUILTIN)
#                       define PyAPI_FUNC(RTYPE) __declspec(dllexport) RTYPE
#                       define PyAPI_DATA(RTYPE) extern __declspec(dllexport) RTYPE
        /* module init functions inside the core need no external linkage */
        /* except for Cygwin to handle embedding */
#                       if defined(__CYGWIN__)
#                               define PyMODINIT_FUNC __declspec(dllexport) PyObject*
#                       else /* __CYGWIN__ */
#                               define PyMODINIT_FUNC PyObject*
#                       endif /* __CYGWIN__ */
#               else /* Py_BUILD_CORE */
        /* Building an extension module, or an embedded situation */
        /* public Python functions and data are imported */
        /* Under Cygwin, auto-import functions to prevent compilation */
        /* failures similar to those described at the bottom of 4.1: */
        /* http://docs.python.org/extending/windows.html#a-cookbook-approach */
#                       if !defined(__CYGWIN__)
#                               define PyAPI_FUNC(RTYPE) __declspec(dllimport) RTYPE
#                       endif /* !__CYGWIN__ */
#                       define PyAPI_DATA(RTYPE) extern __declspec(dllimport) RTYPE
        /* module init functions outside the core must be exported */
#                       if defined(__cplusplus)
#                               define PyMODINIT_FUNC extern "C" __declspec(dllexport) PyObject*
#                       else /* __cplusplus */
#                               define PyMODINIT_FUNC __declspec(dllexport) PyObject*
#                       endif /* __cplusplus */
#               endif /* Py_BUILD_CORE */
#       endif /* HAVE_DECLSPEC_DLL */
#endif /* Py_ENABLE_SHARED */

/* If no external linkage macros defined by now, create defaults */
#ifndef PyAPI_FUNC
#       define PyAPI_FUNC(RTYPE) RTYPE
#endif
#ifndef PyAPI_DATA
#       define PyAPI_DATA(RTYPE) extern RTYPE
#endif
#ifndef PyMODINIT_FUNC
#       if defined(__cplusplus)
#               define PyMODINIT_FUNC extern "C" PyObject*
#       else /* __cplusplus */
#               define PyMODINIT_FUNC PyObject*
#       endif /* __cplusplus */
#endif
"""

PYPORT_EXPORT_REPLACE_NEW = b"""
#include "exports.h"
#define PyAPI_FUNC(RTYPE) __declspec(dllexport) RTYPE
#define PyAPI_DATA(RTYPE) extern __declspec(dllexport) RTYPE
#define PyMODINIT_FUNC __declspec(dllexport) PyObject*
"""

PYPORT_EXPORT_REPLACE_OLD = b"""
#define PyAPI_FUNC(RTYPE) __declspec(dllexport) RTYPE
#define PyAPI_DATA(RTYPE) extern __declspec(dllexport) RTYPE
#define PyMODINIT_FUNC __declspec(dllexport) PyObject*
"""

CTYPES_INIT_REPLACE = b"""
if _os.name == "nt":
    pythonapi = PyDLL("python dll", None, _sys.dllhandle)
elif _sys.platform == "cygwin":
    pythonapi = PyDLL("libpython%d.%d.dll" % _sys.version_info[:2])
else:
    pythonapi = PyDLL(None)
"""

SYSMODULE_WINVER_SEARCH = b"""
#ifdef MS_COREDLL
    SET_SYS("dllhandle", PyLong_FromVoidPtr(PyWin_DLLhModule));
    SET_SYS_FROM_STRING("winver", PyWin_DLLVersionString);
#endif
"""

SYSMODULE_WINVER_REPLACE = b"""
#ifdef MS_COREDLL
    SET_SYS("dllhandle", PyLong_FromVoidPtr(PyWin_DLLhModule));
    SET_SYS_FROM_STRING("winver", PyWin_DLLVersionString);
#else
    SET_SYS_FROM_STRING("winver", "%s");
#endif
"""

SYSMODULE_WINVER_SEARCH_38 = b"""
#ifdef MS_COREDLL
    SET_SYS_FROM_STRING("dllhandle",
                        PyLong_FromVoidPtr(PyWin_DLLhModule));
    SET_SYS_FROM_STRING("winver",
                        PyUnicode_FromString(PyWin_DLLVersionString));
#endif
"""


SYSMODULE_WINVER_REPLACE_38 = b"""
#ifdef MS_COREDLL
    SET_SYS_FROM_STRING("dllhandle",
                        PyLong_FromVoidPtr(PyWin_DLLhModule));
    SET_SYS_FROM_STRING("winver",
                        PyUnicode_FromString(PyWin_DLLVersionString));
#else
    SET_SYS_FROM_STRING("winver", PyUnicode_FromString("%s"));
#endif
"""


def run_msbuild(
    msbuild: pathlib.Path,
    pcbuild_path: pathlib.Path,
    configuration: str,
    platform: str,
    python_version: str,
    windows_sdk_version: str,
):
    args = [
        str(msbuild),
        str(pcbuild_path / "pcbuild.proj"),
        "/target:Build",
        "/property:Configuration=%s" % configuration,
        "/property:Platform=%s" % platform,
        "/maxcpucount",
        "/nologo",
        "/verbosity:normal",
        "/property:IncludeExternals=true",
        "/property:IncludeSSL=true",
        "/property:IncludeTkinter=true",
        "/property:IncludeTests=true",
        "/property:OverrideVersion=%s" % python_version,
        "/property:IncludeCTypes=true",
        # We pin the Windows 10 SDK version to make builds more deterministic.
        # This can also work around known incompatibilities with the Windows 11
        # SDK as of at least CPython 3.9.7.
        f"/property:DefaultWindowsSDKVersion={windows_sdk_version}",
    ]

    exec_and_log(args, str(pcbuild_path), os.environ)


def build_openssl_for_arch(
    perl_path,
    arch: str,
    openssl_archive,
    openssl_version: str,
    nasm_archive,
    build_root: pathlib.Path,
    profile: str,
    *,
    jom_archive,
):
    nasm_version = DOWNLOADS["nasm-windows-bin"]["version"]

    log("extracting %s to %s" % (openssl_archive, build_root))
    extract_tar_to_directory(openssl_archive, build_root)
    log("extracting %s to %s" % (nasm_archive, build_root))
    extract_tar_to_directory(nasm_archive, build_root)
    log("extracting %s to %s" % (jom_archive, build_root))
    extract_zip_to_directory(jom_archive, build_root / "jom")

    nasm_path = build_root / ("cpython-bin-deps-nasm-%s" % nasm_version)
    jom_path = build_root / "jom"

    env = dict(os.environ)
    # Add Perl and nasm paths to front of PATH.
    env["PATH"] = "%s;%s;%s;%s" % (perl_path.parent, nasm_path, jom_path, env["PATH"])

    source_root = build_root / ("openssl-%s" % openssl_version)

    # uplink.c tries to find the OPENSSL_Applink function exported from the current
    # executable. However, it is exported from _ssl[_d].pyd in shared builds. So
    # update its sounce to look for it from there.
    static_replace_in_file(
        source_root / "ms" / "uplink.c",
        b"((h = GetModuleHandle(NULL)) == NULL)",
        b'((h = GetModuleHandleA("_ssl.pyd")) == NULL) if ((h = GetModuleHandleA("_ssl_d.pyd")) == NULL) if ((h = GetModuleHandle(NULL)) == NULL)',
    )

    if arch == "x86":
        configure = "VC-WIN32"
        prefix = "32"
    elif arch == "amd64":
        configure = "VC-WIN64A"
        prefix = "64"
    else:
        print("invalid architecture: %s" % arch)
        sys.exit(1)

    # The official CPython OpenSSL builds hack ms/uplink.c to change the
    # ``GetModuleHandle(NULL)`` invocation to load things from _ssl.pyd
    # instead. But since we statically link the _ssl extension, this hackery
    # is not required.

    # Set DESTDIR to affect install location.
    dest_dir = build_root / "install"
    env["DESTDIR"] = str(dest_dir)
    install_root = dest_dir / prefix

    exec_and_log(
        [
            str(perl_path),
            "Configure",
            configure,
            "no-idea",
            "no-mdc2",
            "no-tests",
            "--prefix=/%s" % prefix,
        ],
        source_root,
        {
            **env,
            "CFLAGS": env.get("CFLAGS", "") + " /FS",
        },
    )

    # exec_and_log(["nmake"], source_root, env)
    exec_and_log(
        [str(jom_path / "jom"), "/J", str(multiprocessing.cpu_count())],
        source_root,
        env,
    )

    # We don't care about accessory files, docs, etc. So just run `install_sw`
    # target to get the main files.
    exec_and_log(["nmake", "install_sw"], source_root, env)

    # Copy the _static libraries as well.
    for l in ("crypto", "ssl"):
        basename = "lib%s_static.lib" % l
        source = source_root / basename
        dest = install_root / "lib" / basename
        log("copying %s to %s" % (source, dest))
        shutil.copyfile(source, dest)


def build_openssl(
    entry: str,
    perl_path: pathlib.Path,
    arch: str,
    profile: str,
    dest_archive: pathlib.Path,
):
    """Build OpenSSL from sources using the Perl executable specified."""

    openssl_version = DOWNLOADS[entry]["version"]

    # First ensure the dependencies are in place.
    openssl_archive = download_entry(entry, BUILD)
    nasm_archive = download_entry("nasm-windows-bin", BUILD)
    jom_archive = download_entry("jom-windows-bin", BUILD)

    with tempfile.TemporaryDirectory(prefix="openssl-build-") as td:
        td = pathlib.Path(td)

        root_32 = td / "x86"
        root_64 = td / "x64"

        if arch == "x86":
            root_32.mkdir()
            build_openssl_for_arch(
                perl_path,
                "x86",
                openssl_archive,
                openssl_version,
                nasm_archive,
                root_32,
                profile,
                jom_archive=jom_archive,
            )
        elif arch == "amd64":
            root_64.mkdir()
            build_openssl_for_arch(
                perl_path,
                "amd64",
                openssl_archive,
                openssl_version,
                nasm_archive,
                root_64,
                profile,
                jom_archive=jom_archive,
            )
        else:
            raise ValueError("unhandled arch: %s" % arch)

        install = td / "out"

        if arch == "x86":
            shutil.copytree(root_32 / "install" / "32", install / "openssl" / "win32")
        else:
            shutil.copytree(root_64 / "install" / "64", install / "openssl" / "amd64")

        with dest_archive.open("wb") as fh:
            create_tar_from_directory(fh, install)


def build_libffi(
    python: str,
    arch: str,
    sh_exe: pathlib.Path,
    msvc_version: str,
    dest_archive: pathlib.Path,
):
    with tempfile.TemporaryDirectory(prefix="libffi-build-") as td:
        td = pathlib.Path(td)

        ffi_source_path = td / "libffi"

        # As of April 15, 2020, the libffi source release on GitHub doesn't
        # have patches that we need to build. https://bugs.python.org/issue40293
        # tracks getting a proper release. Until then, git clone the repo.
        subprocess.run(
            [
                "git.exe",
                "-c",
                "core.autocrlf=input",
                "clone",
                "--single-branch",
                "--branch",
                "libffi",
                "https://github.com/python/cpython-source-deps.git",
                str(ffi_source_path),
            ],
            check=True,
        )

        subprocess.run(
            [
                "git.exe",
                "-c",
                "core.autocrlf=input",
                "checkout",
                "16fad4855b3d8c03b5910e405ff3a04395b39a98",
            ],
            cwd=ffi_source_path,
            check=True,
        )

        # We build libffi by running the build script that CPython ships.
        python_archive = download_entry(python, BUILD)
        extract_tar_to_directory(python_archive, td)

        python_entry = DOWNLOADS[python]
        prepare_libffi = (
            td
            / ("Python-%s" % python_entry["version"])
            / "PCbuild"
            / "prepare_libffi.bat"
        )

        env = dict(os.environ)
        env["LIBFFI_SOURCE"] = str(ffi_source_path)
        env["VCVARSALL"] = str(find_vcvarsall_path(msvc_version))
        env["SH"] = str(sh_exe)

        args = [str(prepare_libffi), "-pdb"]
        if arch == "x86":
            args.append("-x86")
            artifacts_path = ffi_source_path / "i686-pc-cygwin"
        else:
            args.append("-x64")
            artifacts_path = ffi_source_path / "x86_64-w64-cygwin"

        subprocess.run(args, env=env, check=True)

        out_dir = td / "out" / "libffi"
        out_dir.mkdir(parents=True)

        for f in os.listdir(artifacts_path / ".libs"):
            if f.endswith((".lib", ".exp", ".dll", ".pdb")):
                shutil.copyfile(artifacts_path / ".libs" / f, out_dir / f)

        shutil.copytree(artifacts_path / "include", out_dir / "include")
        shutil.copyfile(
            artifacts_path / "fficonfig.h", out_dir / "include" / "fficonfig.h"
        )

        with dest_archive.open("wb") as fh:
            create_tar_from_directory(fh, td / "out")


RE_ADDITIONAL_DEPENDENCIES = re.compile(
    "<AdditionalDependencies>([^<]+)</AdditionalDependencies>"
)


def collect_python_build_artifacts(
    pcbuild_path: pathlib.Path,
    out_dir: pathlib.Path,
    python_majmin: str,
    arch: str,
    config: str,
    openssl_entry: str,
):
    """Collect build artifacts from Python.

    Copies them into an output directory and returns a data structure describing
    the files.
    """
    outputs_path = pcbuild_path / arch
    intermediates_path = (
        pcbuild_path / "obj" / ("%s%s_%s" % (python_majmin, arch, config))
    )

    if not outputs_path.exists():
        log("%s does not exist" % outputs_path)
        sys.exit(1)

    if not intermediates_path.exists():
        log("%s does not exist" % intermediates_path)
        sys.exit(1)

    # Things we want to collect:
    # 1. object files that contribute to libpython
    # 2. libraries for dependencies

    # The build throws everything in the same directory hierarchy, so we can't
    # easily filter by path to identify e.g. core versus extensions. We rely on
    # tagging projects instead. We validate that all directories are known to
    # us.

    # Projects that aren't relevant to us.
    ignore_projects = {
        # We don't care about build artifacts for the python executable.
        "python",
        "pythonw",
        # Used to bootstrap interpreter.
        "_freeze_module",
        # Don't care about venvlauncher executable.
        "venvlauncher",
        "venvwlauncher",
        # Test extensions.
        "_ctypes_test",
        "_testbuffer",
        "_testcapi",
        "_testclinic",
        "_testconsole",
        "_testembed",
        "_testimportmultiple",
        "_testinternalcapi",
        "_testsinglephase",
        "_testmultiphase",
        "xxlimited",
        "xxlimited_35",
    }

    other_projects = {"pythoncore"}
    other_projects.add("python3dll")

    # Projects providing dependencies.
    depends_projects = set()

    # Projects that provide extensions.
    extension_projects = set()

    dirs = {p for p in os.listdir(intermediates_path)}

    for extension, entry in CONVERT_TO_BUILTIN_EXTENSIONS.items():
        if extension not in dirs:
            if entry.get("ignore_missing"):
                continue
            else:
                log("extension not present: %s" % extension)
                sys.exit(1)

        extension_projects.add(extension)

    depends_projects |= {
        "liblzma",
        "sqlite3",
    }

    known_projects = (
        ignore_projects | other_projects | depends_projects | extension_projects
    )

    unknown = dirs - known_projects

    if unknown:
        log(
            "encountered build directory for unknown projects: %s"
            % ", ".join(sorted(unknown))
        )
        sys.exit(1)

    res = {"core": {"objs": []}, "extensions": {}}

    res["object_file_format"] = "coff"

    def process_project(project: pathlib.Path, dest_dir: pathlib.Path):
        for f in sorted(os.listdir(intermediates_path / project)):
            p = intermediates_path / project / f
            dest = dest_dir / p.name

            if p.suffix == ".obj":
                log("copying object file %s to %s" % (p, dest_dir))
                shutil.copyfile(p, dest)
                yield f

    def find_additional_dependencies(project: pathlib.Path):
        vcproj = pcbuild_path / ("%s.vcxproj" % project)

        with vcproj.open("r", encoding="utf8") as fh:
            for line in fh:
                m = RE_ADDITIONAL_DEPENDENCIES.search(line)

                if not m:
                    continue

                depends = set(m.group(1).split(";"))
                depends.discard("%(AdditionalDependencies)")

                return depends

        return set()

    # Copy object files for core sources into their own directory.
    core_dir = out_dir / "build" / "core"
    core_dir.mkdir(parents=True)

    for obj in process_project("pythoncore", core_dir):
        res["core"]["objs"].append("build/core/%s" % obj)

    # Copy config.c into output directory, next to its object file.
    shutil.copyfile(
        pcbuild_path / ".." / "PC" / "config.c", out_dir / "build" / "core" / "config.c"
    )

    assert "build/core/config.obj" in res["core"]["objs"]
    res["inittab_object"] = "build/core/config.obj"
    res["inittab_source"] = "build/core/config.c"
    res["inittab_cflags"] = ["-DNDEBUG", "-DPy_BUILD_CORE"]

    exts = ("lib", "exp")

    for ext in exts:
        source = outputs_path / ("python%s.%s" % (python_majmin, ext))
        dest = core_dir / ("python%s.%s" % (python_majmin, ext))
        log("copying %s" % source)
        shutil.copyfile(source, dest)

    res["core"]["shared_lib"] = "install/python%s.dll" % python_majmin

    # We hack up pythoncore.vcxproj and the list in it when this function
    # runs isn't totally accurate. We hardcode the list from the CPython
    # distribution.
    # TODO pull from unaltered file
    res["core"]["links"] = [
        {"name": "version", "system": True},
        {"name": "ws2_32", "system": True},
        # In addition to the ones explicitly in the project, there are some
        # implicit link libraries not present. We list those as well.
        {"name": "Ole32", "system": True},
        {"name": "OleAut32", "system": True},
        {"name": "User32", "system": True},
    ]

    # pathcch is required on 3.9+ and its presence drops support for Windows 7.
    if python_majmin != "38":
        res["core"]["links"].append({"name": "pathcch", "system": True})

    # shlwapi was dropped from 3.9.9+.
    if python_majmin == "38":
        res["core"]["links"].append({"name": "shlwapi", "system": True})

    # Copy files for extensions into their own directories.
    for ext in sorted(extension_projects):
        dest_dir = out_dir / "build" / "extensions" / ext
        dest_dir.mkdir(parents=True)

        additional_depends = find_additional_dependencies(ext)
        additional_depends -= CONVERT_TO_BUILTIN_EXTENSIONS.get(ext, {}).get(
            "ignore_additional_depends", set()
        )

        entry = {
            "in_core": False,
            "objs": [],
            "init_fn": "PyInit_%s" % ext,
            "shared_lib": None,
            "static_lib": None,
            "links": [
                {"name": n[:-4], "system": True} for n in sorted(additional_depends)
            ],
            "variant": "default",
        }

        for obj in process_project(ext, dest_dir):
            entry["objs"].append("build/extensions/%s/%s" % (ext, obj))

        for lib in CONVERT_TO_BUILTIN_EXTENSIONS.get(ext, {}).get("shared_depends", []):
            entry["links"].append(
                {"name": lib, "path_dynamic": "install/DLLs/%s.dll" % lib}
            )

        for lib in CONVERT_TO_BUILTIN_EXTENSIONS.get(ext, {}).get(
            "shared_depends_%s" % arch, []
        ):
            entry["links"].append(
                {"name": lib, "path_dynamic": "install/DLLs/%s.dll" % lib}
            )

        if ext in EXTENSION_TO_LIBRARY_DOWNLOADS_ENTRY:
            licenses = set()
            license_paths = set()
            license_public_domain = False

            for name in EXTENSION_TO_LIBRARY_DOWNLOADS_ENTRY[ext]:
                if name == "openssl":
                    name = openssl_entry

                download_entry = DOWNLOADS[name]

                # This will raise if no license metadata defined. This is
                # intentional because EXTENSION_TO_LIBRARY_DOWNLOADS_ENTRY is
                # manually curated and we want to fail fast.
                licenses |= set(download_entry["licenses"])
                license_paths.add("licenses/%s" % download_entry["license_file"])
                license_public_domain = download_entry.get("license_public_domain")

            entry["licenses"] = list(sorted(licenses))
            entry["license_paths"] = list(sorted(license_paths))
            entry["license_public_domain"] = license_public_domain

        res["extensions"][ext] = [entry]

        # Copy the extension static library.
        ext_static = outputs_path / ("%s.lib" % ext)
        dest = dest_dir / ("%s.lib" % ext)
        log("copying static extension %s" % ext_static)
        shutil.copyfile(ext_static, dest)

        res["extensions"][ext][0]["shared_lib"] = "install/DLLs/%s.pyd" % ext

    lib_dir = out_dir / "build" / "lib"
    lib_dir.mkdir()

    # Copy libraries for dependencies into the lib directory.
    for depend in sorted(depends_projects):
        static_source = outputs_path / ("%s.lib" % depend)
        static_dest = lib_dir / ("%s.lib" % depend)

        log("copying link library %s" % static_source)
        shutil.copyfile(static_source, static_dest)

        shared_source = outputs_path / ("%s.dll" % depend)
        if shared_source.exists():
            shared_dest = lib_dir / ("%s.dll" % depend)
            log("copying shared library %s" % shared_source)
            shutil.copyfile(shared_source, shared_dest)

    return res


def build_cpython(
    python_entry_name: str,
    target_triple: str,
    arch: str,
    profile,
    msvc_version: str,
    windows_sdk_version: str,
    openssl_archive,
    libffi_archive,
    openssl_entry: str,
) -> pathlib.Path:
    pgo = profile == "pgo"

    msbuild = find_msbuild(msvc_version)
    log("found MSBuild at %s" % msbuild)

    # The python.props file keys off MSBUILD, so it needs to be set.
    os.environ["MSBUILD"] = str(msbuild)

    bzip2_archive = download_entry("bzip2", BUILD)
    sqlite_archive = download_entry("sqlite", BUILD)
    tk_bin_archive = download_entry(
        "tk-windows-bin", BUILD, local_name="tk-windows-bin.tar.gz"
    )
    xz_archive = download_entry("xz", BUILD)
    zlib_archive = download_entry("zlib", BUILD)

    python_archive = download_entry(python_entry_name, BUILD)
    entry = DOWNLOADS[python_entry_name]

    python_version = entry["version"]

    setuptools_wheel = download_entry("setuptools", BUILD)
    pip_wheel = download_entry("pip", BUILD)

    if arch == "amd64":
        build_platform = "x64"
        build_directory = "amd64"
    elif arch == "x86":
        build_platform = "win32"
        build_directory = "win32"
    else:
        raise ValueError("unhandled arch: %s" % arch)

    with tempfile.TemporaryDirectory(prefix="python-build-") as td:
        td = pathlib.Path(td)

        with concurrent.futures.ThreadPoolExecutor(10) as e:
            fs = []
            for a in (
                python_archive,
                bzip2_archive,
                openssl_archive,
                sqlite_archive,
                tk_bin_archive,
                xz_archive,
                zlib_archive,
            ):
                log("extracting %s to %s" % (a, td))
                fs.append(e.submit(extract_tar_to_directory, a, td))

            for f in fs:
                f.result()

        extract_tar_to_directory(libffi_archive, td)

        # We need all the OpenSSL library files in the same directory to appease
        # install rules.
        openssl_arch = {"amd64": "amd64", "x86": "win32"}[arch]
        openssl_root = td / "openssl" / openssl_arch
        openssl_bin_path = openssl_root / "bin"
        openssl_lib_path = openssl_root / "lib"

        for f in sorted(os.listdir(openssl_bin_path)):
            if not f.startswith("lib"):
                continue

            source = openssl_bin_path / f
            dest = openssl_lib_path / f
            log("copying %s to %s" % (source, dest))
            shutil.copyfile(source, dest)

        cpython_source_path = td / ("Python-%s" % python_version)
        pcbuild_path = cpython_source_path / "PCbuild"

        out_dir = td / "out"

        build_dir = out_dir / "python" / "build"
        build_dir.mkdir(parents=True)

        # Parse config.c before we hack it up: we want a pristine copy.
        config_c_path = cpython_source_path / "PC" / "config.c"

        with config_c_path.open("r", encoding="utf8") as fh:
            config_c = fh.read()

        builtin_extensions = parse_config_c(config_c)

        hack_project_files(
            td,
            cpython_source_path,
            build_directory,
            python_version=python_version,
        )

        if pgo:
            run_msbuild(
                msbuild,
                pcbuild_path,
                configuration="PGInstrument",
                platform=build_platform,
                python_version=python_version,
                windows_sdk_version=windows_sdk_version,
            )

            # build-windows.py sets some environment variables which cause the
            # test harness to pick up the wrong `test` module. We unset these
            # so things work as expected.
            env = dict(os.environ)
            paths = [
                p for p in env["PATH"].split(";") if p != str(BUILD / "venv" / "bin")
            ]
            env["PATH"] = ";".join(paths)
            del env["PYTHONPATH"]

            env["PYTHONHOME"] = str(cpython_source_path)

            # For some reason, .pgc files aren't being created if we invoke the
            # test harness normally (all tests) or with -j to perform parallel
            # test execution. We work around this by invoking the test harness
            # separately for each test.
            instrumented_python = (
                pcbuild_path / build_directory / "instrumented" / "python.exe"
            )

            tests = subprocess.run(
                [str(instrumented_python), "-m", "test", "--list-tests"],
                cwd=cpython_source_path,
                env=env,
                check=False,
                stdout=subprocess.PIPE,
            ).stdout

            tests = [l.strip() for l in tests.decode("utf-8").splitlines() if l.strip()]

            for test in sorted(tests):
                # Only look at specific tests, to keep runtime down.
                if test not in PGO_TESTS:
                    continue

                # test_regrtest hangs for some reason. It is the test for the
                # test harness itself and isn't exercising useful code. Skip it.
                if test == "test_regrtest":
                    continue

                exec_and_log(
                    [
                        str(instrumented_python),
                        "-m",
                        "test",
                        # --pgo simply disables some tests, quiets output, and ignores the
                        # exit code. We could disable it if we wanted more verbose test
                        # output...
                        "--pgo",
                        test,
                    ],
                    str(pcbuild_path),
                    env,
                    exit_on_error=False,
                )

            run_msbuild(
                msbuild,
                pcbuild_path,
                configuration="PGUpdate",
                platform=build_platform,
                python_version=python_version,
                windows_sdk_version=windows_sdk_version,
            )
            artifact_config = "PGUpdate"

        else:
            run_msbuild(
                msbuild,
                pcbuild_path,
                configuration="Release",
                platform=build_platform,
                python_version=python_version,
                windows_sdk_version=windows_sdk_version,
            )
            artifact_config = "Release"

        install_dir = out_dir / "python" / "install"

        # The PC/layout directory contains a script for copying files into
        # a release-like directory. Use that for assembling the standalone
        # build.

        # It doesn't clean up the temp directory it creates. So pass one to it
        # under our tempdir.
        layout_tmp = td / "layouttmp"
        layout_tmp.mkdir()

        args = [
            str(cpython_source_path / "python.bat"),
            str(cpython_source_path / "PC" / "layout"),
            "-vv",
            "--source",
            str(cpython_source_path),
            "--build",
            str(pcbuild_path / build_directory),
            "--copy",
            str(install_dir),
            "--temp",
            str(layout_tmp),
            "--include-dev",
            "--include-symbols",
            "--include-tests",
            "--include-venv",
        ]

        # CPython 3.12 removed distutils.
        if not meets_python_minimum_version(python_version, "3.12"):
            args.append("--include-distutils")

        args.extend(["--include-idle", "--include-stable", "--include-tcltk"])

        exec_and_log(
            args,
            pcbuild_path,
            os.environ,
        )

        # We install pip by using pip to install itself. This leverages a feature
        # where Python can automatically recognize wheel/zip files on sys.path and
        # import their contents. According to
        # https://github.com/pypa/pip/issues/11146 running pip from a wheel is not
        # supported. But it has historically worked and is simple. So do this until
        # it stops working and we need to switch to running pip from the filesytem.
        pip_env = dict(os.environ)
        pip_env["PYTHONPATH"] = str(pip_wheel)

        # Install pip and setuptools.
        exec_and_log(
            [
                str(install_dir / "python.exe"),
                "-m",
                "pip",
                "install",
                "--no-cache-dir",
                "--no-index",
                str(pip_wheel),
            ],
            td,
            pip_env,
        )

        exec_and_log(
            [
                str(install_dir / "python.exe"),
                "-m",
                "pip",
                "install",
                "--no-cache-dir",
                "--no-index",
                str(setuptools_wheel),
            ],
            td,
            pip_env,
        )

        # The executables in the Scripts/ directory don't work because they reference
        # python.dll in the wrong path. You can run these via e.g. `python.exe -m pip`.
        # So just delete them for now.
        for filename in sorted(os.listdir(install_dir / "Scripts")):
            assert filename.startswith("pip") and filename.endswith(".exe")
            p = install_dir / "Scripts" / filename
            log("removing non-functional executable: %s" % p)
            os.unlink(p)

        # But this leaves the Scripts directory empty, which we don't want. So
        # create a placeholder file to ensure the directory is created on archive
        # extract.
        with (install_dir / "Scripts" / ".empty").open("ab"):
            pass

        # Now copy the build artifacts into the output directory.
        build_info = collect_python_build_artifacts(
            pcbuild_path,
            out_dir / "python",
            "".join(entry["version"].split(".")[0:2]),
            build_directory,
            artifact_config,
            openssl_entry=openssl_entry,
        )

        for ext, init_fn in sorted(builtin_extensions.items()):
            if ext in build_info["extensions"]:
                log("built-in extension should not have a build entry: %s" % ext)
                sys.exit(1)

            build_info["extensions"][ext] = [
                {
                    "in_core": True,
                    "objs": [],
                    "init_fn": init_fn,
                    "links": [],
                    "shared_lib": None,
                    "static_lib": None,
                    "variant": "default",
                }
            ]

        for extension, entries in build_info["extensions"].items():
            for record in entries:
                record["required"] = extension in REQUIRED_EXTENSIONS

        # Copy OpenSSL libraries as a one-off.
        for lib in ("crypto", "ssl"):
            name = "lib%s.lib" % lib

            source = td / "openssl" / build_directory / "lib" / name
            dest = out_dir / "python" / "build" / "lib" / name
            log("copying %s to %s" % (source, dest))
            shutil.copyfile(source, dest)

        shutil.copyfile(
            cpython_source_path / "Tools" / "scripts" / "run_tests.py",
            out_dir / "python" / "build" / "run_tests.py",
        )

        licenses_dir = out_dir / "python" / "licenses"
        licenses_dir.mkdir()
        for f in sorted(os.listdir(ROOT)):
            if f.startswith("LICENSE.") and f.endswith(".txt"):
                shutil.copyfile(ROOT / f, licenses_dir / f)

        extension_module_loading = ["builtin", "shared-library"]

        # Patches to CPython above (search for __declspec) always force
        # __declspec(dllexport), even for static distributions.
        python_symbol_visibility = "dllexport"

        crt_features = ["vcruntime:140"]

        if profile == "pgo":
            optimizations = "pgo"
        else:
            optimizations = "noopt"

        # Create PYTHON.json file describing this distribution.
        python_info = {
            "version": "7",
            "target_triple": target_triple,
            "optimizations": optimizations,
            "python_tag": entry["python_tag"],
            "python_version": python_version,
            "python_symbol_visibility": python_symbol_visibility,
            "python_stdlib_test_packages": sorted(STDLIB_TEST_PACKAGES),
            "python_extension_module_loading": extension_module_loading,
            "libpython_link_mode": "shared",
            "crt_features": crt_features,
            "build_info": build_info,
            "licenses": entry["licenses"],
            "license_path": "licenses/LICENSE.cpython.txt",
            "run_tests": "build/run_tests.py",
        }

        # Collect information from running Python script.
        python_exe = out_dir / "python" / "install" / "python.exe"
        metadata_path = td / "metadata.json"
        env = dict(os.environ)
        env["ROOT"] = str(out_dir / "python")
        subprocess.run(
            [
                str(python_exe),
                str(SUPPORT / "generate_metadata.py"),
                str(metadata_path),
            ],
            env=env,
            check=True,
        )

        with metadata_path.open("rb") as fh:
            metadata = json.load(fh)

        python_info.update(metadata)

        python_info["tcl_library_path"] = "install/tcl"
        python_info["tcl_library_paths"] = [
            "dde1.4",
            "reg1.3",
            "tcl8.6",
            "tk8.6",
            "tcl8",
            "tix8.4.3",
        ]

        validate_python_json(python_info, extension_modules=None)

        with (out_dir / "python" / "PYTHON.json").open("w", encoding="utf8") as fh:
            json.dump(python_info, fh, sort_keys=True, indent=4)

        dest_path = BUILD / (
            "cpython-%s-%s-%s.tar"
            % (
                entry["version"],
                target_triple,
                profile,
            )
        )

        data = io.BytesIO()
        create_tar_from_directory(data, td / "out")
        data.seek(0)

        data = normalize_tar_archive(data)

        with dest_path.open("wb") as fh:
            while True:
                chunk = data.read(32768)
                if not chunk:
                    break

                fh.write(chunk)

        return dest_path


def fetch_strawberry_perl() -> pathlib.Path:
    strawberryperl_zip = download_entry("strawberryperl", BUILD)
    strawberryperl = BUILD / "strawberry-perl"
    strawberryperl.mkdir(exist_ok=True)
    with zipfile.ZipFile(strawberryperl_zip) as zf:
        zf.extractall(strawberryperl)
    return strawberryperl


def main() -> None:
    BUILD.mkdir(exist_ok=True)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--vs",
        choices={"2019", "2022"},
        default="2019",
        help="Visual Studio version to use",
    )
    parser.add_argument(
        "--python",
        choices={
            "cpython-3.8",
            "cpython-3.9",
            "cpython-3.10",
            "cpython-3.11",
            "cpython-3.12",
            "cpython-3.13",
        },
        default="cpython-3.11",
        help="Python distribution to build",
    )
    parser.add_argument(
        "--profile",
        choices={"noopt", "pgo"},
        default="noopt",
        help="How to compile Python",
    )
    parser.add_argument(
        "--sh", required=True, help="Path to sh.exe in a cygwin or mingw installation"
    )
    parser.add_argument(
        "--windows-sdk-version",
        default="10.0.20348.0",
        help="Windows SDK version to build with",
    )

    args = parser.parse_args()

    log_path = BUILD / "build.log"

    with log_path.open("wb") as log_fh:
        LOG_FH[0] = log_fh

        if os.environ.get("Platform") == "x86":
            target_triple = "i686-pc-windows-msvc"
            arch = "x86"
        else:
            target_triple = "x86_64-pc-windows-msvc"
            arch = "amd64"

        # TODO need better dependency checking.

        # CPython 3.11+ have native support for OpenSSL 3.x. We anticipate this
        # will change in a future minor release once OpenSSL 1.1 goes out of support.
        # But who knows.
        if args.python in ("cpython-3.8", "cpython-3.9", "cpython-3.10"):
            openssl_entry = "openssl-1.1"
        else:
            openssl_entry = "openssl-3.0"

        openssl_archive = BUILD / (
            "%s-%s-%s.tar" % (openssl_entry, target_triple, args.profile)
        )
        if not openssl_archive.exists():
            perl_path = fetch_strawberry_perl() / "perl" / "bin" / "perl.exe"
            LOG_PREFIX[0] = "openssl"
            build_openssl(
                openssl_entry,
                perl_path,
                arch,
                profile=args.profile,
                dest_archive=openssl_archive,
            )

        libffi_archive = BUILD / ("libffi-%s-%s.tar" % (target_triple, args.profile))
        if not libffi_archive.exists():
            build_libffi(
                args.python,
                arch,
                pathlib.Path(args.sh),
                args.vs,
                libffi_archive,
            )

        LOG_PREFIX[0] = "cpython"
        tar_path = build_cpython(
            args.python,
            target_triple,
            arch,
            profile=args.profile,
            msvc_version=args.vs,
            windows_sdk_version=args.windows_sdk_version,
            openssl_archive=openssl_archive,
            libffi_archive=libffi_archive,
            openssl_entry=openssl_entry,
        )

        if "PYBUILD_RELEASE_TAG" in os.environ:
            release_tag = os.environ["PYBUILD_RELEASE_TAG"]
        else:
            release_tag = release_tag_from_git()

        # Create, e.g., `cpython-3.10.13+20240224-x86_64-pc-windows-msvc-pgo.tar.zst`.
        dest_path = compress_python_archive(
            tar_path,
            DIST,
            "%s-%s" % (tar_path.stem, release_tag),
        )

        # Copy to, e.g., `cpython-3.10.13+20240224-x86_64-pc-windows-msvc-shared-pgo.tar.zst`.
        # The 'shared-' prefix is no longer needed, but we're double-publishing under
        # both names during the transition period.
        filename: str = dest_path.name
        if not filename.endswith("-%s-%s.tar.zst" % (args.profile, release_tag)):
            raise ValueError("expected filename to end with profile: %s" % filename)
        filename = filename.removesuffix("-%s-%s.tar.zst" % (args.profile, release_tag))
        filename = filename + "-shared-%s-%s.tar.zst" % (args.profile, release_tag)
        shutil.copy2(dest_path, dest_path.with_name(filename))


if __name__ == "__main__":
    sys.exit(main())
