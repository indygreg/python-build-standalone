# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import pathlib
import re
import tarfile

from .downloads import (
    DOWNLOADS,
)

# Module entries from Setup.dist that we can copy verbatim without
# issue.
STATIC_MODULES = {
    b'_asyncio',
    b'_bisect',
    b'_blake2',
    b'_codecs_cn',
    b'_codecs_hk',
    b'_codecs_iso2022',
    b'_codecs_jp',
    b'_codecs_kr',
    b'_codecs_tw',
    b'_contextvars',
    b'_csv',
    b'_datetime',
    b'_heapq',
    b'_md5',
    b'_multibytecodec',
    b'_pickle',
    b'_posixsubprocess',
    b'_random',
    b'_sha1',
    b'_sha256',
    b'_sha512',
    b'_sha3',
    b'_socket',
    b'_struct',
    b'_testcapi',
    b'_weakref',
    b'_xxtestfuzz',
    b'array',
    b'audioop',
    b'binascii',
    b'cmath',
    b'fcntl',
    b'grp',
    b'math',
    b'mmap',
    b'nis',
    b'parser',
    b'resource',
    b'select',
    b'spwd',
    b'syslog',
    b'termios',
    b'unicodedata',
    b'xxlimited',
    b'zlib',
}

# Modules we don't (yet) support building.
UNSUPPORTED_MODULES = {
    b'_tkinter',
}


def parse_setup_line(line: bytes):
    """Parse a line in a ``Setup.*`` file."""
    if b'#' in line:
        line = line[:line.index(b'#')].rstrip()

    if not line:
        return

    words = line.split()

    extension = words[0].decode('ascii')

    objs = set()
    links = set()

    for word in words:
        # Arguments looking like C source files are converted to object files.
        if word.endswith(b'.c'):
            # Object files are named according to the basename: parent
            # directories they may happen to reside in are stripped out.
            source_path = pathlib.Path(word.decode('ascii'))
            obj_path = pathlib.Path('Modules/%s' % source_path.with_suffix('.o').name)
            objs.add(obj_path)

        # Arguments looking like link libraries are converted to library
        # dependencies.
        elif word.startswith(b'-l'):
            links.add(word[2:].decode('ascii'))

    return {
        'extension': extension,
        'posix_obj_paths': objs,
        'links': links,
    }


def derive_setup_local(static_modules_lines, cpython_source_archive, disabled=None):
    """Derive the content of the Modules/Setup.local file."""
    python_version = DOWNLOADS['cpython-3.7']['version']

    # makesetup parses lines with = as extra config options. There appears
    # to be no easy way to define e.g. -Dfoo=bar in Setup.local. We hack
    # around this by producing a Makefile supplement that overrides the build
    # rules for certain targets to include these missing values.
    extra_cflags = {}

    disabled = disabled or set()
    disabled |= UNSUPPORTED_MODULES

    with tarfile.open(str(cpython_source_archive)) as tf:
        ifh = tf.extractfile('Python-%s/Modules/Setup.dist' % python_version)
        source_lines = ifh.readlines()

        ifh = tf.extractfile('Python-%s/Modules/config.c.in' % python_version)
        config_c_in = ifh.read()

    found_shared = False

    dest_lines = []
    make_lines = []

    for line in source_lines:
        line = line.rstrip()

        if line == b'#*shared*':
            found_shared = True
            dest_lines.append(b'*static*')

        if not found_shared:
            continue

        # Stop processing at the #*disabled* line.
        if line == b'#*disabled*':
            break

        if line.startswith(tuple(b'#%s' % k for k in STATIC_MODULES)):
            line = line[1:]

            if b'#' in line:
                line = line[:line.index(b'#')]

            module = line.split()[0]
            if module in disabled:
                continue

            dest_lines.append(line)

    RE_DEFINE = re.compile(b'-D[^=]+=[^\s]+')

    for line in static_modules_lines:
        # makesetup parses lines with = as extra config options. There appears
        # to be no easy way to define e.g. -Dfoo=bar in Setup.local. We hack
        # around this by detecting the syntax we'd like to support and move the
        # variable defines to a Makefile supplement that overrides variables for
        # specific targets.
        for m in RE_DEFINE.finditer(line):
            sources = [w for w in line.split() if w.endswith(b'.c')]
            for source in sources:
                obj = b'Modules/%s.o' % os.path.basename(source)[:-2]

                extra_cflags.setdefault(obj, []).append(m.group(0))

        line = RE_DEFINE.sub(b'', line)

        if b'=' in line:
            raise Exception('= appears in EXTRA_MODULES line; will confuse '
                            'makesetup: %s' % line.decode('utf-8'))
        dest_lines.append(line)

    dest_lines.append(b'\n*disabled*\n')
    dest_lines.extend(sorted(disabled))

    dest_lines.append(b'')

    for target in sorted(extra_cflags):
        make_lines.append(
            b'%s: PY_STDMODULE_CFLAGS += %s' %
            (target, b' '.join(extra_cflags[target])))

    return {
        'config_c_in': config_c_in,
        'setup_dist': b'\n'.join(source_lines),
        'setup_local': b'\n'.join(dest_lines),
        'make_data': b'\n'.join(make_lines),
    }


RE_INITTAB_ENTRY = re.compile('\{"([^"]+)", ([^\}]+)\},')


def parse_config_c(s: str):
    """Parse the contents of a config.c file.

    The file defines external symbols for module init functions and the
    mapping of module name to module initializer function.
    """

    # Some config.c files have #ifdef. We don't care about those because
    # in all cases the condition is true.

    extensions = {}

    seen_inittab = False

    for line in s.splitlines():
        if line.startswith('struct _inittab'):
            seen_inittab = True

        if not seen_inittab:
            continue

        if '/* Sentinel */' in line:
            break

        m = RE_INITTAB_ENTRY.search(line)

        if m:
            extensions[m.group(1)] = m.group(2)

    return extensions
