#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import argparse
import multiprocessing
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from pythonbuild.cpython import (
    derive_setup_local
)
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
SUPPORT = ROOT / 'cpython-macos'

MACOSX_DEPLOYMENT_TARGET = '10.14'

DISABLED_STATIC_MODULES = {
    # We don't support GDBM because it is GPL v3.
    b'_gdbm',
    # Not available on macOS.
    b'nis',
    # Not available on macOS.
    b'ossaudiodev',
    # Not available on macOS.
    b'spwd',
}

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


def exec_and_log(args, cwd, env):
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

    if p.returncode:
        print('process exited %d' % p.returncode)
        sys.exit(p.returncode)


def simple_build(entry):
    archive = download_entry(entry, BUILD)

    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)

        shutil.copyfile(archive, td / archive.name)

        extract_tar_to_directory(BUILD / 'clang-macos.tar', td)
        toolchain_path = td / 'clang-macos' / 'bin'

        env = dict(os.environ)
        env['%s_VERSION' % entry.upper()] = DOWNLOADS[entry]['version']

        # We force a PATH only containing system files: we don't want
        # pollution from homebrew, macports, etc.
        env['PATH'] = '%s:/usr/bin:/bin' % toolchain_path

        env['MACOSX_DEPLOYMENT_TARGET'] = MACOSX_DEPLOYMENT_TARGET
        env['NUM_CPUS'] = '%s' % multiprocessing.cpu_count()

        exec_and_log([SUPPORT / ('build-%s.sh' % entry)], td, env)

        dest_path = BUILD / ('%s-macos.tar' % entry)

        with dest_path.open('wb') as fh:
            create_tar_from_directory(fh, td / 'out')


def build_clang():
    cmake_archive = download_entry('cmake-macos-bin', BUILD)
    ninja_archive = download_entry('ninja-macos-bin', BUILD)
    clang_archive = download_entry('clang', BUILD)
    clang_rt_archive = download_entry('clang-compiler-rt', BUILD)
    lld_archive = download_entry('lld', BUILD)
    llvm_archive = download_entry('llvm', BUILD)
    libcxx_archive = download_entry('libc++', BUILD)
    libcxxabi_archive = download_entry('libc++abi', BUILD)

    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)

        for a in (cmake_archive, ninja_archive, clang_archive, clang_rt_archive,
                  lld_archive, llvm_archive, libcxx_archive, libcxxabi_archive):
            shutil.copyfile(a, td / a.name)

        env = {
            'CMAKE_VERSION': DOWNLOADS['cmake-macos-bin']['version'],
            'NINJA_VERSION': DOWNLOADS['ninja-macos-bin']['version'],
            'CLANG_COMPILER_RT_VERSION': DOWNLOADS['clang-compiler-rt']['version'],
            'CLANG_VERSION': DOWNLOADS['clang']['version'],
            'COMPILER_RT_VERSION': DOWNLOADS['clang-compiler-rt']['version'],
            'LIBCXX_VERSION': DOWNLOADS['libc++']['version'],
            'LIBCXXABI_VERSION': DOWNLOADS['libc++abi']['version'],
            'LLD_VERSION': DOWNLOADS['lld']['version'],
            'LLVM_VERSION': DOWNLOADS['llvm']['version'],

            'PATH': '/usr/bin:/bin',
        }

        exec_and_log([SUPPORT / 'build-clang.sh'], td, env)

        dest_path = BUILD / 'clang-macos.tar'

        with dest_path.open('wb') as fh:
            create_tar_from_directory(fh, td / 'out')


def build_cpython():
    python_archive = download_entry('cpython-3.7', BUILD)
    python_version = DOWNLOADS['cpython-3.7']['version']

    with (SUPPORT / 'static-modules').open('rb') as fh:
        static_modules_lines = [l.rstrip() for l in fh if not l.startswith(b'#')]

    setup_local_content, extra_make_content = derive_setup_local(
        static_modules_lines, python_archive, disabled=DISABLED_STATIC_MODULES)

    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)

        extract_tar_to_directory(BUILD / 'clang-macos.tar', td)
        toolchain_path = td / 'clang-macos' / 'bin'

        deps_dir = td / 'deps'
        deps_dir.mkdir()

        extract_tar_to_directory(BUILD / 'bdb-macos.tar', deps_dir)
        extract_tar_to_directory(BUILD / 'bzip2-macos.tar', deps_dir)
        extract_tar_to_directory(BUILD / 'libedit-macos.tar', deps_dir)
        extract_tar_to_directory(BUILD / 'libffi-macos.tar', deps_dir)
        # We use the system ncurses and statically link (for now).
        #extract_tar_to_directory(BUILD / 'ncurses-macos.tar', deps_dir)
        extract_tar_to_directory(BUILD / 'openssl-macos.tar', deps_dir)
        extract_tar_to_directory(BUILD / 'sqlite-macos.tar', deps_dir)
        extract_tar_to_directory(BUILD / 'uuid-macos.tar', deps_dir)
        extract_tar_to_directory(BUILD / 'xz-macos.tar', deps_dir)
        extract_tar_to_directory(BUILD / 'zlib-macos.tar', deps_dir)

        extract_tar_to_directory(python_archive, td)

        setup_local_path = td / ('Python-%s' % python_version) / 'Modules' / 'Setup.local'
        with setup_local_path.open('wb') as fh:
            fh.write(setup_local_content)

        makefile_extra_path = td / 'Makefile.extra'
        with makefile_extra_path.open('wb') as fh:
            fh.write(extra_make_content)

        shutil.copyfile(ROOT / 'python-licenses.rst', td / 'python-licenses.rst')

        env = dict(os.environ)
        env['PYTHON_VERSION'] = python_version

        # We force a PATH only containing system files: we don't want
        # pollution from homebrew, macports, etc.
        env['PATH'] = '%s:/usr/bin:/bin' % toolchain_path

        env['MACOSX_DEPLOYMENT_TARGET'] = MACOSX_DEPLOYMENT_TARGET
        env['NUM_CPUS'] = '%s' % multiprocessing.cpu_count()

        env['CPYTHON_OPTIMIZED'] = '1'

        exec_and_log([SUPPORT / 'build-cpython.sh'], td, env)

        dest_path = BUILD / 'cpython-macos.tar'

        with dest_path.open('wb') as fh:
            create_tar_from_directory(fh, td / 'out')


def main():
    BUILD.mkdir(exist_ok=True)

    parser = argparse.ArgumentParser()
    parser.add_argument('action')

    args = parser.parse_args()

    action = args.action

    log_path = BUILD / ('build.%s-macos.log' % action)
    LOG_PREFIX[0] = '%s-macos' % action

    with log_path.open('wb') as log_fh:
        LOG_FH[0] = log_fh

        if action in ('bdb', 'bzip2', 'libedit', 'libffi', 'openssl', 'ncurses', 'sqlite', 'uuid', 'xz', 'zlib'):
            simple_build(action)

        elif action == 'clang':
            build_clang()

        elif action == 'cpython':
            build_cpython()

        else:
            print('unknown build action: %s' % action)
            return 1


if __name__ == '__main__':
    sys.exit(main())
