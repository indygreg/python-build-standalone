#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import argparse
import json
import multiprocessing
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import zipfile

from pythonbuild.cpython import (
    derive_setup_local,
    parse_config_c,
    parse_setup_line,
)
from pythonbuild.downloads import (
    DOWNLOADS,
)
from pythonbuild.utils import (
    add_licenses_to_extension_entry,
    create_tar_from_directory,
    download_entry,
    extract_tar_to_directory,
)

ROOT = pathlib.Path(os.path.abspath(__file__)).parent.parent
BUILD = ROOT / 'build'
SUPPORT = ROOT / 'cpython-macos'

MACOSX_DEPLOYMENT_TARGET = '10.9'

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

REQUIRED_EXTENSIONS = {
    '_codecs',
    '_io',
    '_signal',
    '_thread',
    '_tracemalloc',
    '_weakref',
    'faulthandler',
    'posix',
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
    clang_archive = download_entry('clang-6', BUILD)
    clang_rt_archive = download_entry('clang-compiler-rt-6', BUILD)
    lld_archive = download_entry('lld-6', BUILD)
    llvm_archive = download_entry('llvm-6', BUILD)
    libcxx_archive = download_entry('libc++-6', BUILD)
    libcxxabi_archive = download_entry('libc++abi-6', BUILD)

    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)

        for a in (cmake_archive, ninja_archive, clang_archive, clang_rt_archive,
                  lld_archive, llvm_archive, libcxx_archive, libcxxabi_archive):
            shutil.copyfile(a, td / a.name)

        env = {
            'CMAKE_VERSION': DOWNLOADS['cmake-macos-bin']['version'],
            'NINJA_VERSION': DOWNLOADS['ninja-macos-bin']['version'],
            'CLANG_COMPILER_RT_VERSION': DOWNLOADS['clang-compiler-rt-6']['version'],
            'CLANG_VERSION': DOWNLOADS['clang-6']['version'],
            'COMPILER_RT_VERSION': DOWNLOADS['clang-compiler-rt-6']['version'],
            'LIBCXX_VERSION': DOWNLOADS['libc++-6']['version'],
            'LIBCXXABI_VERSION': DOWNLOADS['libc++abi-6']['version'],
            'LLD_VERSION': DOWNLOADS['lld-6']['version'],
            'LLVM_VERSION': DOWNLOADS['llvm-6']['version'],

            'PATH': '/usr/bin:/bin',
        }

        exec_and_log([SUPPORT / 'build-clang.sh'], td, env)

        dest_path = BUILD / 'clang-macos.tar'

        with dest_path.open('wb') as fh:
            create_tar_from_directory(fh, td / 'out')


def python_build_info(python_path: pathlib.Path, config_c_in,
                      setup_dist, setup_local):
    bi = {
        'core': {
            'objs': [],
            'links': [],
        },
        'extensions': {},
    }

    # This is very similar to the Linux code and could probably be
    # consolidated...
    core_objs = set()
    modules_objs = set()

    for root, dirs, files in os.walk(python_path / 'build'):
        for f in files:
            p = pathlib.Path(root) / f
            rel_path = p.relative_to(python_path)

            if p.suffix != '.o':
                continue

            if rel_path.parts[1] in ('Objects', 'Parser', 'Python'):
                core_objs.add(rel_path)

            elif rel_path.parts[1] == 'Modules':
                modules_objs.add(rel_path)

    for p in sorted(core_objs):
        log('adding core object file %s' % p)
        bi['core']['objs'].append(str(p))

    libraries = set()

    for f in os.listdir(python_path / 'build' / 'lib'):
        if not f.endswith('.a'):
            continue

        # Strip "lib" prefix and ".a" suffix.
        libname = f[3:-2]
        libraries.add(libname)

    # Extensions are derived by parsing the Setup.dist and Setup.local
    # files.

    def process_setup_line(line):
        d = parse_setup_line(line, variant=None)

        if not d:
            return

        extension = d['extension']
        log('processing extension %s' % extension)

        objs = []

        for obj in sorted(d['posix_obj_paths']):
            obj = pathlib.Path('build') / obj
            log('adding object file %s for extension %s' % (obj, extension))
            objs.append(str(obj))

            modules_objs.discard(obj)

        links = []

        for framework in sorted(d['frameworks']):
            log('adding framework %s for extension %s' % (framework, extension))

            links.append({
                'name': framework,
                'framework': True,
            })

        for libname in sorted(d['links']):
            log('adding library %s for extension %s' % (libname, extension))

            if libname in libraries:
                entry = {
                    'name': libname,
                    'path_static': 'build/lib/lib%s.a' % libname,
                }

                links.append(entry)
            else:
                links.append({
                    'name': libname,
                    'system': True,
                })

        entry = {
            'in_core': False,
            'init_fn': 'PyInit_%s' % extension,
            'links': links,
            'objs': objs,
            'variant': 'default',
        }

        add_licenses_to_extension_entry(entry)

        bi['extensions'][extension] = [entry]

    found_start = False

    for line in setup_dist.splitlines():
        if not found_start:
            if line.startswith(b'PYTHONPATH='):
                found_start = True
                continue

            continue

        process_setup_line(line)

    for line in setup_local.splitlines():
        if line.startswith(b'*static*'):
            continue

        if line.startswith(b'*disabled*'):
            break

        process_setup_line(line)

    for name, init_fn in sorted(config_c_in.items()):
        log('adding in-core extension %s' % name)
        bi['extensions'][name] = [{
            'in_core': True,
            'init_fn': init_fn,
            'links': [],
            'objs': [],
            'variant': 'default',
        }]

    for extension, entries in bi['extensions'].items():
        for entry in entries:
            entry['required'] = extension in REQUIRED_EXTENSIONS

    # Any paths left in modules_objs are not part of any extensions and
    # are instead part of the core distribution.
    for p in sorted(modules_objs):
        log('adding core object file %s' % p)
        bi['core']['objs'].append(str(p))

    return bi


def build_cpython(optimized=False):
    python_archive = download_entry('cpython-3.7', BUILD)
    python_version = DOWNLOADS['cpython-3.7']['version']
    setuptools_archive = download_entry('setuptools', BUILD)
    pip_archive = download_entry('pip', BUILD)

    with (SUPPORT / 'static-modules').open('rb') as fh:
        static_modules_lines = [l.rstrip() for l in fh if not l.startswith(b'#')]

    setup = derive_setup_local(
        static_modules_lines, python_archive,
        DOWNLOADS['cpython-3.7']['version'],
        disabled=DISABLED_STATIC_MODULES)

    config_c_in = parse_config_c(setup['config_c_in'].decode('utf-8'))
    setup_dist_content = setup['setup_dist']
    setup_local_content = setup['setup_local']
    extra_make_content = setup['make_data']

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
        extract_tar_to_directory(pip_archive, td)

        with zipfile.ZipFile(setuptools_archive) as zf:
            zf.extractall(td)

        setup_local_path = td / ('Python-%s' % python_version) / 'Modules' / 'Setup.local'
        with setup_local_path.open('wb') as fh:
            fh.write(setup_local_content)

        makefile_extra_path = td / 'Makefile.extra'
        with makefile_extra_path.open('wb') as fh:
            fh.write(extra_make_content)

        for f in sorted(os.listdir(ROOT)):
            if f.startswith('LICENSE.') and f.endswith('.txt'):
                shutil.copyfile(ROOT / f, td / f)

        env = dict(os.environ)
        env['PYTHON_VERSION'] = python_version
        env['SETUPTOOLS_VERSION'] = DOWNLOADS['setuptools']['version']
        env['PIP_VERSION'] = DOWNLOADS['pip']['version']

        # We force a PATH only containing system files: we don't want
        # pollution from homebrew, macports, etc.
        env['PATH'] = '%s:/usr/bin:/bin' % toolchain_path

        env['MACOSX_DEPLOYMENT_TARGET'] = MACOSX_DEPLOYMENT_TARGET
        env['NUM_CPUS'] = '%s' % multiprocessing.cpu_count()

        if optimized:
            env['CPYTHON_OPTIMIZED'] = '1'

        exec_and_log([SUPPORT / 'build-cpython.sh'], td, env)

        # Create PYTHON.json file describing this distribution.
        python_info = {
            'version': '2',
            'os': 'macos',
            'arch': 'x86_64',
            'python_flavor': 'cpython',
            'python_version': python_version,
            'python_exe': 'install/bin/python3',
            'python_include': 'install/include/python3.7m',
            'python_stdlib': 'install/lib/python3.7',
            'build_info': python_build_info(td / 'out' / 'python',
                                            config_c_in,
                                            setup_dist_content,
                                            setup_local_content),
            'licenses': DOWNLOADS['cpython-3.7']['licenses'],
            'license_path': 'licenses/LICENSE.cpython.txt',
        }

        with (td / 'out' / 'python' / 'PYTHON.json').open('w') as fh:
            json.dump(python_info, fh, sort_keys=True, indent=4)

        basename = 'cpython-macos'

        if optimized:
            basename += '-pgo'

        basename += '.tar'

        dest_path = BUILD / basename

        with dest_path.open('wb') as fh:
            create_tar_from_directory(fh, td / 'out')


def main():
    BUILD.mkdir(exist_ok=True)

    parser = argparse.ArgumentParser()
    parser.add_argument('--optimized', action='store_true')
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
            build_cpython(optimized=args.optimized)

        else:
            print('unknown build action: %s' % action)
            return 1


if __name__ == '__main__':
    sys.exit(main())
