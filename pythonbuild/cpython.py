# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import re
import tarfile

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


def derive_setup_local(static_modules_lines, cpython_source_archive, disabled=None):
    """Derive the content of the Modules/Setup.local file."""
    # makesetup parses lines with = as extra config options. There appears
    # to be no easy way to define e.g. -Dfoo=bar in Setup.local. We hack
    # around this by producing a Makefile supplement that overrides the build
    # rules for certain targets to include these missing values.
    extra_cflags = {}

    disabled = disabled or set()
    disabled |= UNSUPPORTED_MODULES

    with tarfile.open(str(cpython_source_archive)) as tf:
        ifh = tf.extractfile('Python-3.7.1/Modules/Setup.dist')
        source_lines = ifh.readlines()

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

    return b'\n'.join(dest_lines), b'\n'.join(make_lines)
