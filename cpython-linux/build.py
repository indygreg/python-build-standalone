#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import argparse
import contextlib
import io
import json
import operator
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
    add_licenses_to_extension_entry,
    download_entry,
    write_package_versions,
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
                data = fh.read()
            client.images.load(data)

            return image_id

        else:
            return build_docker_image(client, name)


def copy_file_to_container(path, container, container_path, archive_path=None):
    """Copy a path on the local filesystem to a running container."""
    buf = io.BytesIO()
    tf = tarfile.open('irrelevant', 'w', buf)

    dest_path = archive_path or path.name
    tf.add(str(path), dest_path)
    tf.close()

    log('copying %s to container:%s/%s' % (path, container_path, dest_path))
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


# 2019-01-01T00:00:00
DEFAULT_MTIME = 1546329600


def container_get_archive(container, path):
    """Get a deterministic tar archive from a container."""
    data, stat = container.get_archive(path)
    old_data = io.BytesIO()
    for chunk in data:
        old_data.write(chunk)

    old_data.seek(0)

    new_data = io.BytesIO()

    with tarfile.open(fileobj=old_data) as itf, tarfile.open(fileobj=new_data, mode='w') as otf:
        for member in sorted(itf.getmembers(), key=operator.attrgetter('name')):
            file_data = itf.extractfile(member) if not member.linkname else None
            member.mtime = DEFAULT_MTIME
            otf.addfile(member, file_data)

    return new_data.getvalue()


def install_tools_archive(container, source: pathlib.Path):
    copy_file_to_container(source, container, '/build')
    container_exec(
        container, ['/bin/tar', '-C', '/tools', '-xf', '/build/%s' % source.name],
        user='root')


def copy_toolchain(container, gcc=False, musl=False):
    install_tools_archive(container, archive_path('binutils', 'linux64'))

    if gcc:
        install_tools_archive(container, archive_path('gcc', 'linux64'))

    clang_linux64 = archive_path('clang', 'linux64')
    musl_linux64 = archive_path('musl', 'linux64')

    if clang_linux64.exists():
        install_tools_archive(container, clang_linux64)

    if musl:
        install_tools_archive(container, musl_linux64)


def copy_rust(container):
    rust = download_entry('rust', BUILD)

    copy_file_to_container(rust, container, '/build')
    container.exec_run(['/bin/mkdir', 'p', '/tools/rust'])
    container.exec_run(
        ['/bin/tar', '-C', '/tools/rust', '--strip-components', '1',
         '-xf', '/build/%s' % rust.name])


def download_tools_archive(container, dest, name):
    log('copying container files to %s' % dest)
    data = container_get_archive(container, '/build/out/tools/%s' % name)

    with open(dest, 'wb') as fh:
        fh.write(data)


def add_target_env(env, platform):
    env['TARGET'] = 'x86_64-unknown-linux-gnu'


def archive_path(package_name: str, platform: str, musl=False):
    entry = DOWNLOADS[package_name]
    basename = '%s-%s-%s%s.tar' % (
        package_name,
        entry['version'],
        platform,
        '-musl' if musl else '')

    return BUILD / basename


def simple_build(client, image, entry, platform, musl=False, extra_archives=None):
    archive = download_entry(entry, BUILD)

    with run_container(client, image) as container:
        copy_toolchain(container, musl=musl)

        for a in extra_archives or []:
            install_tools_archive(container, archive_path(a, platform, musl=musl))

        copy_file_to_container(archive, container, '/build')
        copy_file_to_container(SUPPORT / ('build-%s.sh' % entry),
                               container, '/build')

        env = {
            'CC': 'clang',
            'TOOLCHAIN': 'clang-linux64',
            '%s_VERSION' % entry.upper().replace('-', '_'): DOWNLOADS[entry]['version'],
        }
        if musl:
            env['CC'] = 'musl-clang'

        add_target_env(env, platform)

        container_exec(container, '/build/build-%s.sh' % entry,
                       environment=env)

        download_tools_archive(container,
                               archive_path(entry, platform, musl=musl),
                               'deps')


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

        download_tools_archive(container, archive_path('binutils', 'linux64'),
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

        copy_file_to_container(archive_path('binutils', 'linux64'),
                               container,
                               '/build')
        copy_file_to_container(SUPPORT / 'build-gcc.sh', container,
                               '/build')

        container_exec(
            container, '/build/build-gcc.sh',
            environment={
                'BINUTILS_VERSION': DOWNLOADS['binutils']['version'],
                'GCC_VERSION': DOWNLOADS['gcc']['version'],
                'GMP_VERSION': DOWNLOADS['gmp']['version'],
                'ISL_VERSION': DOWNLOADS['isl']['version'],
                'MPC_VERSION': DOWNLOADS['mpc']['version'],
                'MPFR_VERSION': DOWNLOADS['mpfr']['version'],
            })

        download_tools_archive(container,
                               archive_path('gcc', 'linux64'),
                               'host')


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

        download_tools_archive(container,
                               archive_path('clang', suffix),
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

        download_tools_archive(container,
                               archive_path('musl', 'linux64'),
                               'host')


def build_libedit(client, image, platform, musl=False):
    libedit_archive = download_entry('libedit', BUILD)

    with run_container(client, image) as container:
        copy_toolchain(container, musl=musl)

        dep_platform = platform
        if musl:
            dep_platform += '-musl'

        install_tools_archive(container, archive_path('ncurses', platform, musl=musl))
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
        download_tools_archive(container,
                               archive_path('libedit', platform, musl=musl),
                               'deps')


def build_readline(client, image, platform, musl=False):
    readline_archive = download_entry('readline', BUILD)

    with run_container(client, image) as container:
        copy_toolchain(container, musl=musl)

        dep_platform = platform
        if musl:
            dep_platform += '-musl'

        install_tools_archive(container, archive_path('ncurses', platform, musl=musl))
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

        download_tools_archive(container,
                               archive_path('readline', platform, musl=musl),
                               'deps')


def python_build_info(container, config_c_in, setup_dist, setup_local, libressl=False):
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
            'variant': d['variant'],
        }

        if libressl:
            ignore_keys = {'openssl'}
        else:
            ignore_keys = {'libressl'}

        add_licenses_to_extension_entry(entry, ignore_keys=ignore_keys)

        bi['extensions'].setdefault(extension, []).append(entry)

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


def build_cpython(client, image, platform, debug=False, optimized=False, musl=False,
                  libressl=False, version=None):
    """Build CPython in a Docker image'"""
    entry_name = 'cpython-%s' % version
    entry = DOWNLOADS[entry_name]

    python_archive = download_entry(entry_name, BUILD)
    setuptools_archive = download_entry('setuptools', BUILD)
    pip_archive = download_entry('pip', BUILD)

    with (SUPPORT / 'static-modules').open('rb') as fh:
        static_modules_lines = [l.rstrip() for l in fh if not l.startswith(b'#')]

    setup = derive_setup_local(static_modules_lines, python_archive,
                               python_version=entry['version'],
                               musl=musl, debug=debug)

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
        install_tools_archive(container, archive_path('bdb', platform, musl=musl))
        install_tools_archive(container, archive_path('bzip2', platform, musl=musl))
        install_tools_archive(container, archive_path('libedit', platform, musl=musl))
        install_tools_archive(container, archive_path('libffi', platform, musl=musl))
        install_tools_archive(container, archive_path('libX11', platform, musl=musl))
        install_tools_archive(container, archive_path('libXau', platform, musl=musl))
        install_tools_archive(container, archive_path('libxcb', platform, musl=musl))
        install_tools_archive(container, archive_path('ncurses', platform, musl=musl))

        if libressl:
            install_tools_archive(container, archive_path('libressl', platform, musl=musl))
        else:
            install_tools_archive(container, archive_path('openssl', platform, musl=musl))

        install_tools_archive(container, archive_path('readline', platform, musl=musl))
        install_tools_archive(container, archive_path('sqlite', platform, musl=musl))
        install_tools_archive(container, archive_path('tcl', platform, musl=musl))
        install_tools_archive(container, archive_path('tk', platform, musl=musl))
        install_tools_archive(container, archive_path('uuid', platform, musl=musl))
        install_tools_archive(container, archive_path('xorgproto', platform, musl=musl))
        install_tools_archive(container, archive_path('xz', platform, musl=musl))
        install_tools_archive(container, archive_path('zlib', platform, musl=musl))
        #copy_rust(container)
        copy_file_to_container(python_archive, container, '/build')
        copy_file_to_container(setuptools_archive, container, '/build')
        copy_file_to_container(pip_archive, container, '/build')
        copy_file_to_container(SUPPORT / 'build-cpython.sh', container,
                               '/build')

        for f in sorted(os.listdir(ROOT)):
            if f.startswith('LICENSE.') and f.endswith('.txt'):
                copy_file_to_container(ROOT / f, container, '/build')

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
            'PYTHON_VERSION': entry['version'],
            'SETUPTOOLS_VERSION': DOWNLOADS['setuptools']['version'],
        }

        if musl:
            env['CC'] = 'musl-clang'

        if debug:
            env['CPYTHON_DEBUG'] = '1'
        if optimized:
            env['CPYTHON_OPTIMIZED'] = '1'

        container_exec(container, '/build/build-cpython.sh',
                       environment=env)

        fully_qualified_name = 'python%s%sm' % (
            entry['version'][0:3], 'd' if debug else ''
        )

        # Create PYTHON.json file describing this distribution.
        python_info = {
            'version': '2',
            'os': 'linux',
            'arch': 'x86_64',
            'python_flavor': 'cpython',
            'python_version': entry['version'],
            'python_exe': 'install/bin/%s' % fully_qualified_name,
            'python_include': 'install/include/%s' % fully_qualified_name,
            'python_stdlib': 'install/lib/python%s' % entry['version'][0:3],
            'build_info': python_build_info(container, config_c_in,
                                            setup_dist_content, setup_local_content,
                                            libressl=libressl),
            'licenses': entry['licenses'],
            'license_path': 'licenses/LICENSE.cpython.txt',
        }

        with tempfile.NamedTemporaryFile('w') as fh:
            json.dump(python_info, fh, sort_keys=True, indent=4)
            fh.flush()

            copy_file_to_container(fh.name, container,
                                   '/build/out/python',
                                   archive_path='PYTHON.json')

        basename = 'cpython-%s-%s' % (entry['version'], platform)

        if musl:
            basename += '-musl'
        if debug:
            basename += '-debug'
        if optimized:
            basename += '-pgo'

        basename += '.tar'

        dest_path = BUILD / basename
        data = container_get_archive(container, '/build/out/python')

        with dest_path.open('wb') as fh:
            fh.write(data)


def main():
    BUILD.mkdir(exist_ok=True)

    try:
        client = docker.from_env()
        client.ping()
    except Exception as e:
        print('unable to connect to Docker: %s' % e)
        return 1

    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--platform')
    parser.add_argument('--optimized', action='store_true')
    parser.add_argument('action')

    args = parser.parse_args()

    action = args.action

    name = action
    if args.platform:
        name += '-%s' % args.platform
    if args.debug:
        name += '-debug'
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
        if action == 'versions':
            write_package_versions(BUILD / 'versions')

        elif action.startswith('image-'):
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

        elif action in ('bdb', 'bzip2', 'gdbm', 'inputproto', 'kbproto', 'libffi',
                        'libpthread-stubs', 'libressl',
                        'ncurses', 'openssl', 'sqlite', 'tcl', 'uuid', 'x11-util-macros',
                        'xextproto', 'xorgproto', 'xproto', 'xtrans', 'xz', 'zlib'):
            simple_build(client, get_image(client, 'build'), action, platform=platform,
                         musl=musl)

        elif action == 'libX11':
            simple_build(client, get_image(client, 'build'), action,
                         platform=platform,
                         musl=musl,
                         extra_archives={
                             'inputproto',
                             'kbproto',
                             'libpthread-stubs',
                             'libXau',
                             'libxcb',
                             'x11-util-macros',
                             'xextproto',
                             'xorgproto',
                             'xproto',
                             'xtrans',
                         })

        elif action == 'libXau':
            simple_build(client, get_image(client, 'build'), action, platform=platform,
                         musl=musl, extra_archives={'x11-util-macros', 'xproto'})

        elif action == 'xcb-proto':
            simple_build(client, get_image(client, 'xcb'), action, platform=platform,
                         musl=musl)

        elif action == 'libxcb':
            simple_build(client, get_image(client, 'xcb'), action, platform=platform,
                         musl=musl,
                         extra_archives={
                             'libpthread-stubs',
                             'libXau',
                             'xcb-proto',
                             'xproto',
                         })

        elif action == 'tk':
            simple_build(client, get_image(client, 'xcb'), action,
                         platform=platform,
                         musl=musl,
                         extra_archives={
                             'tcl',
                             'libX11',
                             'libXau',
                             'libxcb',
                             'xcb-proto',
                             'xorgproto',
                         })

        elif action == 'cpython':
            build_cpython(client, get_image(client, 'build'), platform=platform,
                          musl=musl, debug=args.debug, optimized=args.optimized,
                          libressl='PYBUILD_LIBRESSL' in os.environ,
                          version=os.environ['PYBUILD_PYTHON_VERSION'][0:3])

        else:
            print('unknown build action: %s' % action)
            return 1


if __name__ == '__main__':
    sys.exit(main())
