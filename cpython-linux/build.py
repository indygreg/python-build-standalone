#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import contextlib
import io
import os
import pathlib
import sys
import tarfile
import tempfile

import docker
import jinja2

from pythonbuild.cpython import (
    derive_setup_local
)
from pythonbuild.downloads import (
    DOWNLOADS,
)
from pythonbuild.utils import (
    download_entry,
)

ROOT = pathlib.Path(os.path.abspath(__file__)).parent.parent
BUILD = ROOT / 'build'
SUPPORT = ROOT / 'cpython-linux'

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


def ensure_docker_image(client, fh, image_path=None):
    res = client.api.build(fileobj=fh, decode=True)

    image = None

    for s in res:
        if 'stream' in s:
            for l in s['stream'].strip().splitlines():
                log(l)

        if 'aux' in s and 'ID' in s['aux']:
            image = s['aux']['ID']

    if not image:
        raise Exception('unable to determine built Docker image')

    if image_path:
        tar_path = image_path.with_suffix('.tar')
        with tar_path.open('wb') as fh:
            for chunk in client.images.get(image).save():
                fh.write(chunk)

        with image_path.open('w') as fh:
            fh.write(image + '\n')

    return image


def build_docker_image(client, name):
    image_path = BUILD / ('image-%s' % name)

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / 'cpython-linux')))

    tmpl = env.get_template('%s.Dockerfile' % name)
    data = tmpl.render()

    return ensure_docker_image(client, io.BytesIO(data.encode('utf')),
                               image_path=image_path)


def get_image(client, name):
    image_path = BUILD / ('image-%s' % name)
    tar_path = image_path.with_suffix('.tar')

    with image_path.open('r') as fh:
        image_id = fh.read().strip()

    try:
        client.images.get(image_id)
        return image_id
    except docker.errors.ImageNotFound:
        if tar_path.exists():
            with tar_path.open('rb') as fh:
                client.api.import_image_from_stream(fh)

            return image_id

        else:
            return build_docker_image(client, name)


def copy_file_to_container(path, container, container_path, archive_path=None):
    """Copy a path on the local filesystem to a running container."""
    buf = io.BytesIO()
    tf = tarfile.open('irrelevant', 'w', buf)

    tf.add(str(path), archive_path or path.name)
    tf.close()

    log('copying %s to container' % path)
    container.put_archive(container_path, buf.getvalue())


@contextlib.contextmanager
def run_container(client, image):
    container = client.containers.run(
        image, command=['/bin/sleep', '86400'], detach=True)
    try:
        yield container
    finally:
        container.stop(timeout=0)
        container.remove()


def container_exec(container, command, user='build',
                   environment=None):
    # docker-py's exec_run() won't return the exit code. So we reinvent the
    # wheel.
    create_res = container.client.api.exec_create(
        container.id, command, user=user, environment=environment)

    exec_output = container.client.api.exec_start(create_res['Id'], stream=True)

    for chunk in exec_output:
        for l in chunk.strip().splitlines():
            log(l)

        if LOG_FH[0]:
            LOG_FH[0].write(chunk)

    inspect_res = container.client.api.exec_inspect(create_res['Id'])

    if inspect_res['ExitCode'] != 0:
        raise Exception('exit code %d from %s' % (inspect_res['ExitCode'],
                                                  command))


def install_tools_archive(container, source: pathlib.Path):
    copy_file_to_container(source, container, '/build')
    container_exec(
        container, ['/bin/tar', '-C', '/tools', '-xf', '/build/%s' % source.name],
        user='root')


def copy_toolchain(container, platform=None, gcc=False):
    install_tools_archive(container, BUILD / 'binutils-linux64.tar')

    if gcc:
        install_tools_archive(container, BUILD / 'gcc-linux64.tar')

    clang_linux64 = BUILD / 'clang-linux64.tar'

    if clang_linux64.exists():
        install_tools_archive(container, clang_linux64)


def copy_rust(container):
    rust = download_entry('rust', BUILD)

    copy_file_to_container(rust, container, '/build')
    container.exec_run(['/bin/mkdir', 'p', '/tools/rust'])
    container.exec_run(
        ['/bin/tar', '-C', '/tools/rust', '--strip-components', '1',
         '-xf', '/build/%s' % rust.name])


def download_tools_archive(container, dest, name):
    data, stat = container.get_archive('/build/out/tools/%s' % name)

    with open(dest, 'wb') as fh:
        for chunk in data:
            fh.write(chunk)


def add_target_env(env, platform):
    env['TARGET'] = 'x86_64-unknown-linux-gnu'


def simple_build(client, image, entry, platform):
    archive = download_entry(entry, BUILD)

    with run_container(client, image) as container:
        copy_toolchain(container, platform=platform)
        copy_file_to_container(archive, container, '/build')
        copy_file_to_container(SUPPORT / ('build-%s.sh' % entry),
                               container, '/build')

        env = {
            'TOOLCHAIN': 'clang-linux64',
            '%s_VERSION' % entry.upper(): DOWNLOADS[entry]['version'],
        }

        add_target_env(env, platform)

        container_exec(container, '/build/build-%s.sh' % entry,
                       environment=env)
        dest_path = '%s-%s.tar' % (entry, platform)
        download_tools_archive(container, BUILD / dest_path, 'deps')


def build_binutils(client, image):
    """Build binutils in the Docker image."""
    archive = download_entry('binutils', BUILD)

    with run_container(client, image) as container:
        copy_file_to_container(archive, container, '/build')
        copy_file_to_container(SUPPORT / 'build-binutils.sh', container,
                               '/build')

        container_exec(
            container, '/build/build-binutils.sh',
            environment={
                'BINUTILS_VERSION': DOWNLOADS['binutils']['version'],
            })

        download_tools_archive(container, BUILD / 'binutils-linux64.tar',
                               'host')


def build_gcc(client, image):
    """Build GCC in the Docker image."""
    gcc_archive = download_entry('gcc', BUILD)
    gmp_archive = download_entry('gmp', BUILD)
    isl_archive = download_entry('isl', BUILD)
    mpc_archive = download_entry('mpc', BUILD)
    mpfr_archive = download_entry('mpfr', BUILD)

    with run_container(client, image) as container:
        log('copying archives to container...')
        for a in (gcc_archive, gmp_archive, isl_archive, mpc_archive,
                  mpfr_archive):
            copy_file_to_container(a, container, '/build')

        copy_file_to_container(BUILD / 'binutils-linux64.tar', container,
                               '/build')
        copy_file_to_container(SUPPORT / 'build-gcc.sh', container,
                               '/build')

        container_exec(
            container, '/build/build-gcc.sh',
            environment={
                'GCC_VERSION': DOWNLOADS['gcc']['version'],
                'GMP_VERSION': DOWNLOADS['gmp']['version'],
                'ISL_VERSION': DOWNLOADS['isl']['version'],
                'MPC_VERSION': DOWNLOADS['mpc']['version'],
                'MPFR_VERSION': DOWNLOADS['mpfr']['version'],
            })

        download_tools_archive(container, BUILD / 'gcc-linux64.tar', 'host')


def build_clang(client, image):
    cmake_archive = download_entry('cmake-linux-bin', BUILD)
    ninja_archive = download_entry('ninja-linux-bin', BUILD)
    clang_archive = download_entry('clang', BUILD)
    clang_rt_archive = download_entry('clang-compiler-rt', BUILD)
    lld_archive = download_entry('lld', BUILD)
    llvm_archive = download_entry('llvm', BUILD)
    libcxx_archive = download_entry('libc++', BUILD)
    libcxxabi_archive = download_entry('libc++abi', BUILD)

    with run_container(client, image) as container:
        log('copying archives to container...')
        for a in (cmake_archive, ninja_archive, clang_archive, clang_rt_archive,
                  lld_archive, llvm_archive, libcxx_archive, libcxxabi_archive):
            copy_file_to_container(a, container, '/build')

        toolchain_platform = None
        tools_path = 'clang-linux64'
        suffix = 'linux64'
        build_sh = 'build-clang.sh'
        gcc = True

        env = {
            'CLANG_COMPILER_RT_VERSION': DOWNLOADS['clang-compiler-rt']['version'],
            'CLANG_VERSION': DOWNLOADS['clang']['version'],
            'CMAKE_VERSION': DOWNLOADS['cmake-linux-bin']['version'],
            'COMPILER_RT_VERSION': DOWNLOADS['clang-compiler-rt']['version'],
            'GCC_VERSION': DOWNLOADS['gcc']['version'],
            'LIBCXX_VERSION': DOWNLOADS['libc++']['version'],
            'LIBCXXABI_VERSION': DOWNLOADS['libc++abi']['version'],
            'LLD_VERSION': DOWNLOADS['lld']['version'],
            'LLVM_VERSION': DOWNLOADS['llvm']['version'],
        }

        copy_toolchain(container, toolchain_platform, gcc=gcc)

        copy_file_to_container(SUPPORT / build_sh, container,
                               '/build')

        container_exec(container, '/build/%s' % build_sh,
                       environment=env)

        download_tools_archive(container, BUILD / ('clang-%s.tar' % suffix),
                               tools_path)


def build_readline(client, image, platform):
    readline_archive = download_entry('readline', BUILD)

    with run_container(client, image) as container:
        copy_toolchain(container, platform=platform)
        install_tools_archive(container, BUILD / ('ncurses-%s.tar'% platform))
        copy_file_to_container(readline_archive, container, '/build')
        copy_file_to_container(SUPPORT / 'build-readline.sh', container,
                               '/build')

        env = {
            'TOOLCHAIN': 'clang-linux64',
            'READLINE_VERSION': DOWNLOADS['readline']['version'],
        }

        add_target_env(env, platform)

        container_exec(container, '/build/build-readline.sh',
                       environment=env)
        dest_path = 'readline-%s.tar' % platform
        download_tools_archive(container, BUILD / dest_path, 'deps')


def build_tcltk(client, image, platform):
    tcl_archive = download_entry('tcl', BUILD)
    tk_archive = download_entry('tk', BUILD)
    x11_archive = download_entry('libx11', BUILD)

    with run_container(client, image) as container:
        copy_toolchain(container, platform=platform)

        copy_file_to_container(tcl_archive, container, '/build')
        copy_file_to_container(tk_archive, container, '/build')
        copy_file_to_container(x11_archive, container, '/build')
        copy_file_to_container(SUPPORT / 'build-tcltk.sh', container,
                               '/build')

        env = {
            'TOOLCHAIN': 'clang-%s' % platform,
        }

        container_exec(container, '/build/build-tcltk.sh',
                       environment=env)

        dest_path = 'tcltk-%s.tar' % platform
        download_tools_archive(container, BUILD / dest_path)


def build_cpython(client, image, platform):
    """Build CPythin in a Docker image'"""
    python_archive = download_entry('cpython-3.7', BUILD)

    with (SUPPORT / 'static-modules').open('rb') as fh:
        static_modules_lines = [l.rstrip() for l in fh if not l.startswith(b'#')]

    setup_local_content, extra_make_content = derive_setup_local(
        static_modules_lines, python_archive)

    with run_container(client, image) as container:
        copy_toolchain(container, platform=platform)
        install_tools_archive(container, BUILD / ('bzip2-%s.tar' % platform))
        # TODO build against Berkeley DB to avoid GPLv3.
        install_tools_archive(container, BUILD / ('gdbm-%s.tar' % platform))
        install_tools_archive(container, BUILD / ('libffi-%s.tar' % platform))
        install_tools_archive(container, BUILD / ('ncurses-%s.tar' % platform))
        install_tools_archive(container, BUILD / ('openssl-%s.tar' % platform))
        install_tools_archive(container, BUILD / ('readline-%s.tar' % platform))
        install_tools_archive(container, BUILD / ('sqlite-%s.tar' % platform))
        # tk requires a bunch of X11 stuff.
        #install_tools_archive(container, BUILD / ('tcltk-%s.tar' % platform))
        install_tools_archive(container, BUILD / ('uuid-%s.tar' % platform))
        install_tools_archive(container, BUILD / ('xz-%s.tar' % platform))
        install_tools_archive(container, BUILD / ('zlib-%s.tar' % platform))
        #copy_rust(container)
        copy_file_to_container(python_archive, container, '/build')
        copy_file_to_container(SUPPORT / 'build-cpython.sh', container,
                               '/build')
        copy_file_to_container(ROOT / 'python-licenses.rst', container, '/build')

        # TODO copy latest pip/setuptools.

        with tempfile.NamedTemporaryFile('wb') as fh:
            fh.write(setup_local_content)
            fh.flush()

            copy_file_to_container(fh.name, container,
                                   '/build',
                                   archive_path='Setup.local')

        with tempfile.NamedTemporaryFile('wb') as fh:
            fh.write(extra_make_content)
            fh.flush()

            copy_file_to_container(fh.name, container,
                                   '/build',
                                   archive_path='Makefile.extra')

        env = {
            'CPYTHON_OPTIMIZED': '1',
            'PYTHON_VERSION': DOWNLOADS['cpython-3.7']['version'],
        }

        container_exec(container, '/build/build-cpython.sh',
                       environment=env)
        dest_path = BUILD / ('cpython-%s.tar' % platform)

        data, stat = container.get_archive('/build/out/python')

        with dest_path.open('wb') as fh:
            for chunk in data:
                fh.write(chunk)


def main():
    BUILD.mkdir(exist_ok=True)

    try:
        client = docker.from_env()
        client.ping()
    except Exception as e:
        print('unable to connect to Docker: %s' % e)
        return 1

    parser = argparse.ArgumentParser()
    parser.add_argument('--platform')
    parser.add_argument('action')

    args = parser.parse_args()

    action = args.action

    log_path = BUILD / ('build.%s.log' % action)
    LOG_PREFIX[0] = action
    if args.platform:
        log_path = BUILD / ('build.%s-%s.log' % (action, args.platform))
        LOG_PREFIX[0] = '%s-%s' % (action, args.platform)

    with log_path.open('wb') as log_fh:
        LOG_FH[0] = log_fh
        if action.startswith('image-'):
            build_docker_image(client, action[6:])

        elif action == 'binutils':
            build_binutils(client, get_image(client, 'gcc'))

        elif action == 'clang':
            build_clang(client, get_image(client, 'clang'))

        elif action == 'gcc':
            build_gcc(client, get_image(client, 'gcc'))

        elif action == 'readline':
            build_readline(client, get_image(client, 'build'), platform=args.platform)

        elif action in ('bzip2', 'gdbm', 'libffi', 'ncurses', 'openssl', 'sqlite', 'uuid', 'xz', 'zlib'):
            simple_build(client, get_image(client, 'build'), action, platform=args.platform)

        elif action == 'tcltk':
            build_tcltk(client, get_image(client, 'build'), platform=args.platform)

        elif action == 'cpython':
            build_cpython(client, get_image(client, 'build'), platform=args.platform)

        else:
            print('unknown build action: %s' % action)
            return 1


if __name__ == '__main__':
    sys.exit(main())
