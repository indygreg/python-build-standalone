# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import pathlib
import re
import tarfile

from .downloads import DOWNLOADS

# Module entries from Setup.dist that we can copy verbatim without
# issue.
STATIC_MODULES = {
    b"_asyncio",
    b"_bisect",
    b"_blake2",
    b"_codecs_cn",
    b"_codecs_hk",
    b"_codecs_iso2022",
    b"_codecs_jp",
    b"_codecs_kr",
    b"_codecs_tw",
    b"_contextvars",
    b"_csv",
    b"_datetime",
    b"_heapq",
    b"_md5",
    b"_multibytecodec",
    b"_pickle",
    b"_posixsubprocess",
    b"_random",
    b"_sha1",
    b"_sha256",
    b"_sha512",
    b"_sha3",
    b"_socket",
    b"_statistics",
    b"_struct",
    # Despite being a test module, this needs to be built as a
    # built-in in order to facilitate testing.
    b"_testinternalcapi",
    b"_weakref",
    b"_zoneinfo",
    b"array",
    b"audioop",
    b"binascii",
    b"cmath",
    b"fcntl",
    b"grp",
    b"math",
    b"mmap",
    b"nis",
    b"parser",
    b"resource",
    b"select",
    b"spwd",
    b"syslog",
    b"termios",
    b"unicodedata",
    b"zlib",
}

# Modules we don't (yet) support building.
UNSUPPORTED_MODULES = {
    # nis (only installable on UNIX platforms) is globally disabled because
    # it has a dependency on libnsl, which isn't part of the Linux Standard
    # Base specification. This library has a wonky history where it was once
    # part of glibc and core system installs but is slowly being phased away
    # from base installations. There are potential workarounds to adding nis
    # support. See discussion in
    # https://github.com/indygreg/python-build-standalone/issues/51.
    b"nis",
}

# Packages that define tests.
STDLIB_TEST_PACKAGES = {
    "bsddb.test",
    "ctypes.test",
    "distutils.tests",
    "email.test",
    "idlelib.idle_test",
    "json.tests",
    "lib-tk.test",
    "lib2to3.tests",
    "sqlite3.test",
    "test",
    "tkinter.test",
    "unittest.test",
}


def parse_setup_line(line: bytes, variant: str):
    """Parse a line in a ``Setup.*`` file."""
    if b"#" in line:
        line = line[: line.index(b"#")].rstrip()

    if not line:
        return

    words = line.split()

    extension = words[0].decode("ascii")

    objs = set()
    links = set()
    frameworks = set()

    for i, word in enumerate(words):
        # Arguments looking like C source files are converted to object files.
        if word.endswith(b".c"):
            # Object files are named according to the basename: parent
            # directories they may happen to reside in are stripped out.
            source_path = pathlib.Path(word.decode("ascii"))

            if variant:
                obj_path = pathlib.Path(
                    "Modules/VARIANT-%s-%s-%s"
                    % (extension, variant, source_path.with_suffix(".o").name)
                )
            else:
                obj_path = pathlib.Path(
                    "Modules/%s" % source_path.with_suffix(".o").name
                )

            objs.add(obj_path)

        # Arguments looking like link libraries are converted to library
        # dependencies.
        elif word.startswith(b"-l"):
            links.add(word[2:].decode("ascii"))

        elif word == b"-framework":
            frameworks.add(words[i + 1].decode("ascii"))

    return {
        "extension": extension,
        "posix_obj_paths": objs,
        "links": links,
        "frameworks": frameworks,
        "variant": variant or "default",
    }


def derive_setup_local(
    static_modules_lines,
    cpython_source_archive,
    python_version,
    disabled=None,
    musl=False,
    debug=False,
):
    """Derive the content of the Modules/Setup.local file."""
    # makesetup parses lines with = as extra config options. There appears
    # to be no easy way to define e.g. -Dfoo=bar in Setup.local. We hack
    # around this by producing a Makefile supplement that overrides the build
    # rules for certain targets to include these missing values.
    extra_cflags = {}

    disabled = disabled or set()
    disabled |= UNSUPPORTED_MODULES

    if musl:
        # Missing header dependencies.
        disabled.add(b"nis")
        disabled.add(b"ossaudiodev")

    if debug:
        # Doesn't work in debug builds.
        disabled.add(b"xxlimited")
        disabled.add(b"xxlimited_35")

    with tarfile.open(str(cpython_source_archive)) as tf:
        # Setup.dist removed in Python 3.8.
        try:
            ifh = tf.extractfile("Python-%s/Modules/Setup.dist" % python_version)
        except KeyError:
            ifh = tf.extractfile("Python-%s/Modules/Setup" % python_version)

        source_lines = ifh.readlines()

        ifh = tf.extractfile("Python-%s/Modules/config.c.in" % python_version)
        config_c_in = ifh.read()

    found_shared = False

    dest_lines = []
    make_lines = []

    for line in source_lines:
        line = line.rstrip()

        if line == b"#*shared*":
            found_shared = True
            dest_lines.append(b"*static*")

        if not found_shared:
            continue

        # Stop processing at the #*disabled* line.
        if line == b"#*disabled*":
            break

        if line.startswith(tuple(b"#%s" % k for k in STATIC_MODULES)):
            line = line[1:]

            if b"#" in line:
                line = line[: line.index(b"#")]

            module = line.split()[0]
            if module in disabled:
                continue

            dest_lines.append(line)

    RE_DEFINE = re.compile(rb"-D[^=]+=[^\s]+")
    RE_VARIANT = re.compile(rb"VARIANT=([^\s]+)\s")

    seen_variants = set()

    for line in static_modules_lines:
        if not line.strip():
            continue

        # This was added to support musl, since not all extensions build in the
        # musl environment.
        if line.split()[0] in disabled:
            continue

        # We supplement the format to support declaring extension variants.
        # A variant results in multiple compiles of a given extension.
        # However, the CPython build system doesn't take kindly to this because
        # a) we can only have a single extension with a given name
        # b) it assumes the init function matches the extension name
        # c) attempting to link multiple variants into the same binary can often
        #    result in duplicate symbols when variants use different libraries
        #    implementing the same API.
        #
        # When we encounter a variant, we only pass the 1st variant through to
        # Setup.local. We then supplement the Makefile with rules to build
        # remaining variants.
        m = RE_VARIANT.search(line)
        if m:
            line = RE_VARIANT.sub(b"", line)
            variant = m.group(1)
            extension = line.split()[0]

            cflags = []
            ldflags = []

            for w in line.split()[1:]:
                if w.startswith((b"-I", b"-D")):
                    cflags.append(w)
                elif w.startswith((b"-L", b"-l")):
                    ldflags.append(w)
                elif w.endswith(b".c"):
                    pass
                else:
                    raise ValueError("unexpected content in Setup variant line: %s" % w)

            if extension in seen_variants:
                sources = [w for w in line.split() if w.endswith(b".c")]
                object_files = []
                for source in sources:
                    basename = os.path.basename(source)[:-2]

                    # Use a unique name to ensure there aren't collisions
                    # across extension variants.
                    object_file = b"Modules/VARIANT-%s-%s-%s.o" % (
                        extension,
                        variant,
                        basename,
                    )
                    object_files.append(object_file)
                    make_lines.append(
                        b"%s: $(srcdir)/Modules/%s; "
                        b"$(CC) $(PY_BUILTIN_MODULE_CFLAGS) "
                        b"%s -c $(srcdir)/Modules/%s -o %s"
                        % (object_file, source, b" ".join(cflags), source, object_file)
                    )

                # This is kind of a lie in the case of musl. That's fine.
                extension_target = b"Modules/%s-VARIANT-%s$(EXT_SUFFIX)" % (
                    extension,
                    variant,
                )

                make_lines.append(
                    b"%s: %s" % (extension_target, b" ".join(object_files))
                )

                # We can't link a shared library in MUSL since everything is static.
                if not musl:
                    make_lines.append(
                        b"\t$(BLDSHARED) %s %s -o Modules/%s-VARIANT-%s$(EXT_SUFFIX)"
                        % (
                            b" ".join(object_files),
                            b" ".join(ldflags),
                            extension,
                            variant,
                        )
                    )

                make_lines.append(
                    b'\techo "%s" > Modules/VARIANT-%s-%s.data'
                    % (line, extension, variant)
                )

                # Add dependencies to $(LIBRARY) target to force compilation of
                # extension variant.
                make_lines.append(b"$(LIBRARY): %s" % extension_target)

                continue

            else:
                seen_variants.add(extension)

        # makesetup parses lines with = as extra config options. There appears
        # to be no easy way to define e.g. -Dfoo=bar in Setup.local. We hack
        # around this by detecting the syntax we'd like to support and move the
        # variable defines to a Makefile supplement that overrides variables for
        # specific targets.
        for m in RE_DEFINE.finditer(line):
            sources = [w for w in line.split() if w.endswith(b".c")]
            for source in sources:
                obj = b"Modules/%s.o" % os.path.basename(source)[:-2]

                extra_cflags.setdefault(obj, []).append(m.group(0))

        line = RE_DEFINE.sub(b"", line)

        if b"=" in line:
            raise Exception(
                "= appears in EXTRA_MODULES line; will confuse "
                "makesetup: %s" % line.decode("utf-8")
            )
        dest_lines.append(line)

    dest_lines.append(b"\n*disabled*\n")
    dest_lines.extend(sorted(disabled))

    dest_lines.append(b"")

    for target in sorted(extra_cflags):
        make_lines.append(
            b"%s: PY_STDMODULE_CFLAGS += %s" % (target, b" ".join(extra_cflags[target]))
        )

    return {
        "config_c_in": config_c_in,
        "setup_dist": b"\n".join(source_lines),
        "setup_local": b"\n".join(dest_lines),
        "make_data": b"\n".join(make_lines),
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
        if line.startswith("struct _inittab"):
            seen_inittab = True

        if not seen_inittab:
            continue

        if "/* Sentinel */" in line:
            break

        m = RE_INITTAB_ENTRY.search(line)

        if m:
            extensions[m.group(1)] = m.group(2)

    return extensions
