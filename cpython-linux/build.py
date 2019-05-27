#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import argparse
import contextlib
import io
import json
import os
import pathlib
import sys
import tarfile
import tempfile

import docker
import jinja2

from pythonbuild.cpython import (
    derive_setup_local,
    parse_config_c,
    parse_setup_line,
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


def copy_toolchain(container, gcc=False, musl=False):
    install_tools_archive(container, BUILD / 'binutils-linux64.tar')

    if gcc:
        install_tools_archive(container, BUILD / 'gcc-linux64.tar')

    clang_linux64 = BUILD / 'clang-linux64.tar'

    if clang_linux64.exists():
        install_tools_archive(container, clang_linux64)

    if musl:
        install_tools_archive(container, BUILD / 'musl-linux64.tar')


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


def simple_build(client, image, entry, platform, musl=False):
    archive = download_entry(entry, BUILD)

    with run_container(client, image) as container:
        copy_toolchain(container, musl=musl)
        copy_file_to_container(archive, container, '/build')
        copy_file_to_container(SUPPORT / ('build-%s.sh' % entry),
                               container, '/build')

        env = {
            'CC': 'clang',
            'TOOLCHAIN': 'clang-linux64',
            '%s_VERSION' % entry.upper(): DOWNLOADS[entry]['version'],
        }
        if musl:
            env['CC'] = 'musl-clang'

        add_target_env(env, platform)

        container_exec(container, '/build/build-%s.sh' % entry,
                       environment=env)

        basename = '%s-%s' % (entry, platform)
        if musl:
            basename += '-musl'
        dest_path = '%s.tar' % basename
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

        copy_toolchain(container, gcc=gcc)

        copy_file_to_container(SUPPORT / build_sh, container,
                               '/build')

        container_exec(container, '/build/%s' % build_sh,
                       environment=env)

        download_tools_archive(container, BUILD / ('clang-%s.tar' % suffix),
                               tools_path)


def build_musl(client, image):
    musl_archive = download_entry('musl', BUILD)

    with run_container(client, image) as container:
        copy_toolchain(container)
        copy_file_to_container(musl_archive, container, '/build')
        copy_file_to_container(SUPPORT / 'build-musl.sh', container, '/build')

        env = {
            'MUSL_VERSION': DOWNLOADS['musl']['version'],
            'TOOLCHAIN': 'clang-linux64',
        }

        container_exec(container, '/build/build-musl.sh',
                       environment=env)

        download_tools_archive(container, BUILD / 'musl-linux64.tar',
                               'host')


def build_libedit(client, image, platform, musl=False):
    libedit_archive = download_entry('libedit', BUILD)

    with run_container(client, image) as container:
        copy_toolchain(container, musl=musl)

        dep_platform = platform
        if musl:
            dep_platform += '-musl'

        install_tools_archive(container, BUILD / ('ncurses-%s.tar' % dep_platform))
        copy_file_to_container(libedit_archive, container, '/build')
        copy_file_to_container(SUPPORT / 'build-libedit.sh', container,
                               '/build')

        env = {
            'CC': 'clang',
            'TOOLCHAIN': 'clang-linux64',
            'LIBEDIT_VERSION': DOWNLOADS['libedit']['version'],
        }

        if musl:
            env['CC'] = 'musl-clang'

        add_target_env(env, platform)

        container_exec(container, '/build/build-libedit.sh', environment=env)
        basename = 'libedit-%s' % platform
        if musl:
            basename += '-musl'
        dest_path = '%s.tar' % basename
        download_tools_archive(container, BUILD / dest_path, 'deps')


def build_readline(client, image, platform, musl=False):
    readline_archive = download_entry('readline', BUILD)

    with run_container(client, image) as container:
        copy_toolchain(container, musl=musl)

        dep_platform = platform
        if musl:
            dep_platform += '-musl'

        install_tools_archive(container, BUILD / ('ncurses-%s.tar' % dep_platform))
        copy_file_to_container(readline_archive, container, '/build')
        copy_file_to_container(SUPPORT / 'build-readline.sh', container,
                               '/build')

        env = {
            'CC': 'clang',
            'TOOLCHAIN': 'clang-linux64',
            'READLINE_VERSION': DOWNLOADS['readline']['version'],
        }

        if musl:
            env['CC'] = 'musl-clang'

        add_target_env(env, platform)

        container_exec(container, '/build/build-readline.sh',
                       environment=env)
        basename = 'readline-%s' % platform
        if musl:
            basename += '-musl'
        dest_path = '%s.tar' % basename
        download_tools_archive(container, BUILD / dest_path, 'deps')


def build_tcltk(client, image, platform, musl=False):
    tcl_archive = download_entry('tcl', BUILD)
    tk_archive = download_entry('tk', BUILD)
    x11_archive = download_entry('libx11', BUILD)

    with run_container(client, image) as container:
        copy_toolchain(container, musl=musl)

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

        basename = 'tcltk-%s' % platform
        if musl:
            basename += '-musl'
        dest_path = '%s.tar' % basename
        download_tools_archive(container, BUILD / dest_path)


def python_build_info(container, config_c_in, setup_dist, setup_local):
    """Obtain build metadata for the Python distribution."""

    bi = {
        'core': {
            'objs': [],
            'links': [],
        },
        'extensions': {}
    }

    # Object files for the core distribution are found by walking the
    # build artifacts.
    core_objs = set()
    modules_objs = set()

    res = container.exec_run(
        ['/usr/bin/find', '/build/out/python/build', '-name', '*.o'],
        user='build')

    for line in res[1].splitlines():
        if not line.strip():
            continue

        p = pathlib.Path(os.fsdecode(line))
        rel_path = p.relative_to('/build/out/python')

        if rel_path.parts[1] in ('Objects', 'Parser', 'Python'):
            core_objs.add(rel_path)

        if rel_path.parts[1] == 'Modules':
            modules_objs.add(rel_path)

    for p in sorted(core_objs):
        log('adding core object file: %s' % p)
        bi['core']['objs'].append(str(p))

    libraries = set()

    for line in container.exec_run(
        ['/usr/bin/find', '/build/out/python/build/lib', '-name', '*.a'],
        user='build')[1].splitlines():

        if not line.strip():
            continue

        f = line[len('/build/out/python/build/lib/'):].decode('ascii')

        # Strip "lib" prefix and ".a" suffix.
        libname = f[3:-2]

        libraries.add(libname)

    # Extension data is derived by "parsing" the Setup.dist and Setup.local files.

    def process_setup_line(line, variant=None):
        d = parse_setup_line(line, variant)

        if not d:
            return

        extension = d['extension']
        log('processing extension %s (variant %s)' % (extension, d['variant']))

        objs = []

        for obj in sorted(d['posix_obj_paths']):
            obj = pathlib.Path('build') / obj
            log('adding object file %s for extension %s' % (obj, extension))
            objs.append(str(obj))

            # Mark object file as used so we don't include it in the core
            # object files below. .remove() would be nicer, as we would catch
            # missing object files. But some sources (like math.c) are used by
            # multiple modules!
            modules_objs.discard(obj)

        links = []

        for libname in sorted(d['links']):
            log('adding library %s for extension %s' % (libname, extension))

            if libname in libraries:
                links.append({
                    'name': libname,
                    'path_static': 'build/lib/lib%s.a' % libname,
                })
            else:
                links.append({
                    'name': libname,
                    'system': True,
                })

        bi['extensions'].setdefault(extension, []).append({
            'in_core': False,
            'init_fn': 'PyInit_%s' % extension,
            'links': links,
            'objs': objs,
            'variant': d['variant'],
        })


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

    # Extension variants are denoted by the presence of
    # Modules/VARIANT-<extension>-<variant>.data files that describe the
    # extension. Find those files and process them.
    data, stat = container.get_archive('/build/out/python/build/Modules')
    data = io.BytesIO(b''.join(data))

    tf = tarfile.open(fileobj=data)

    for ti in tf:
        basename = os.path.basename(ti.name)

        if not basename.startswith('VARIANT-') or not basename.endswith('.data'):
            continue

        variant = basename[:-5].split('-')[2]
        line = tf.extractfile(ti).read().strip()
        process_setup_line(line, variant=variant)

    # There are also a setup of built-in extensions defined in config.c.in which
    # aren't built using the Setup.* files and are part of the core libpython
    # distribution. Define extensions entries for these so downstream consumers
    # can register their PyInit_ functions.
    for name, init_fn in sorted(config_c_in.items()):
        log('adding in-core extension %s' % name)
        bi['extensions'].setdefault(name, []).append({
            'in_core': True,
            'init_fn': init_fn,
            'links': [],
            'objs': [],
            'variant': 'default',
        })

    for extension, entries in bi['extensions'].items():
        for entry in entries:
            entry['required'] = extension in REQUIRED_EXTENSIONS

    # Any paths left in modules_objs are not part of any extension and are
    # instead part of the core distribution.
    for p in sorted(modules_objs):
        log('adding core object file %s' % p)
        bi['core']['objs'].append(str(p))

    return bi


def build_cpython(client, image, platform, optimized=False, musl=False):
    """Build CPythin in a Docker image'"""
    python_archive = download_entry('cpython-3.7', BUILD)
    setuptools_archive = download_entry('setuptools', BUILD)
    pip_archive = download_entry('pip', BUILD)

    with (SUPPORT / 'static-modules').open('rb') as fh:
        static_modules_lines = [l.rstrip() for l in fh if not l.startswith(b'#')]

    setup = derive_setup_local(static_modules_lines, python_archive,
                               musl=musl)

    config_c_in = parse_config_c(setup['config_c_in'].decode('utf-8'))
    setup_dist_content = setup['setup_dist']
    setup_local_content = setup['setup_local']
    extra_make_content = setup['make_data']

    with run_container(client, image) as container:
        copy_toolchain(container, musl=musl)

        dep_platform = platform
        if musl:
            dep_platform += '-musl'

        # TODO support bdb/gdbm toggle
        install_tools_archive(container, BUILD / ('bdb-%s.tar' % dep_platform))
        install_tools_archive(container, BUILD / ('bzip2-%s.tar' % dep_platform))
        install_tools_archive(container, BUILD / ('libedit-%s.tar' % dep_platform))
        install_tools_archive(container, BUILD / ('libffi-%s.tar' % dep_platform))
        install_tools_archive(container, BUILD / ('ncurses-%s.tar' % dep_platform))
        install_tools_archive(container, BUILD / ('openssl-%s.tar' % dep_platform))
        install_tools_archive(container, BUILD / ('readline-%s.tar' % dep_platform))
        install_tools_archive(container, BUILD / ('sqlite-%s.tar' % dep_platform))
        # tk requires a bunch of X11 stuff.
        #install_tools_archive(container, BUILD / ('tcltk-%s.tar' % dep_platform))
        install_tools_archive(container, BUILD / ('uuid-%s.tar' % dep_platform))
        install_tools_archive(container, BUILD / ('xz-%s.tar' % dep_platform))
        install_tools_archive(container, BUILD / ('zlib-%s.tar' % dep_platform))
        #copy_rust(container)
        copy_file_to_container(python_archive, container, '/build')
        copy_file_to_container(setuptools_archive, container, '/build')
        copy_file_to_container(pip_archive, container, '/build')
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
            'CC': 'clang',
            'PIP_VERSION': DOWNLOADS['pip']['version'],
            'PYTHON_VERSION': DOWNLOADS['cpython-3.7']['version'],
            'SETUPTOOLS_VERSION': DOWNLOADS['setuptools']['version'],
        }

        if musl:
            env['CC'] = 'musl-clang'

        if optimized:
            env['CPYTHON_OPTIMIZED'] = '1'

        container_exec(container, '/build/build-cpython.sh',
                       environment=env)

        # Create PYTHON.json file describing this distribution.
        python_info = {
            'version': '1',
            'os': 'linux',
            'arch': 'x86_64',
            'python_flavor': 'cpython',
            'python_version': DOWNLOADS['cpython-3.7']['version'],
            'python_exe': 'install/bin/python3.7',
            'python_include': 'install/include/python3.7m',
            'python_stdlib': 'install/lib/python3.7',
            'build_info': python_build_info(container, config_c_in,
                                            setup_dist_content, setup_local_content),
        }

        with tempfile.NamedTemporaryFile('w') as fh:
            json.dump(python_info, fh, sort_keys=True, indent=4)
            fh.flush()

            copy_file_to_container(fh.name, container,
                                   '/build/out/python',
                                   archive_path='PYTHON.json')

        basename = 'cpython-%s' % platform

        if musl:
            basename += '-musl'
        if optimized:
            basename += '-pgo'

        basename += '.tar'

        dest_path = BUILD / basename
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
    parser.add_argument('--optimized', action='store_true')
    parser.add_argument('action')

    args = parser.parse_args()

    action = args.action

    name = action
    if args.platform:
        name += '-%s' % args.platform
    if args.optimized:
        name += '-pgo'

    platform = args.platform
    musl = False

    if platform and platform.endswith('-musl'):
        musl = True
        platform = platform[:-5]

    log_path = BUILD / ('build.%s.log' % name)
    LOG_PREFIX[0] = name

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

        elif action == 'musl':
            build_musl(client, get_image(client, 'gcc'))

        elif action == 'libedit':
            build_libedit(client, get_image(client, 'build'), platform=platform,
                          musl=musl)

        elif action == 'readline':
            build_readline(client, get_image(client, 'build'), platform=platform,
                           musl=musl)

        elif action in ('bdb', 'bzip2', 'gdbm', 'libffi', 'ncurses', 'openssl', 'sqlite', 'uuid', 'xz', 'zlib'):
            simple_build(client, get_image(client, 'build'), action, platform=platform,
                         musl=musl)

        elif action == 'tcltk':
            build_tcltk(client, get_image(client, 'build'), platform=platform,
                        musl=musl)

        elif action == 'cpython':
            build_cpython(client, get_image(client, 'build'), platform=platform,
                          musl=musl, optimized=args.optimized)

        else:
            print('unknown build action: %s' % action)
            return 1


if __name__ == '__main__':
    sys.exit(main())
