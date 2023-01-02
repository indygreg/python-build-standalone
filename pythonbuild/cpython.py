# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import pathlib
import re
import tarfile

import jsonschema
import yaml

from pythonbuild.logging import log

EXTENSION_MODULE_SCHEMA = {
    "type": "object",
    "properties": {
        "defines": {"type": "array", "items": {"type": "string"}},
        "defines-conditional": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "define": {"type": "string"},
                    "targets": {"type": "array", "items": {"type": "string"}},
                    "minimum-python-version": {"type": "string"},
                },
                "required": ["define"],
            },
        },
        "disabled-targets": {"type": "array", "items": {"type": "string"}},
        "frameworks": {"type": "array", "items": {"type": "string"}},
        "includes": {"type": "array", "items": {"type": "string"}},
        "includes-conditional": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "targets": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "includes-deps": {"type": "array", "items": {"type": "string"}},
        "links": {"type": "array", "items": {"type": "string"}},
        "links-conditional": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "targets": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "linker-args": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "args": {"type": "array", "items": {"type": "string"}},
                    "targets": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": False,
            },
        },
        "minimum-python-version": {"type": "string"},
        "maximum-python-version": {"type": "string"},
        "required-targets": {"type": "array", "items": {"type": "string"}},
        "sources": {"type": "array", "items": {"type": "string"}},
        "sources-conditional": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "targets": {"type": "array", "items": {"type": "string"}},
                    "minimum-python-version": {"type": "string"},
                    "maximum-python-version": {"type": "string"},
                },
                "additionalProperties": False,
                "required": ["source"],
            },
        },
    },
    "additionalProperties": False,
}

EXTENSION_MODULES_SCHEMA = {
    "type": "object",
    "patternProperties": {
        "^[a-z_]+$": EXTENSION_MODULE_SCHEMA,
    },
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

        elif word.startswith(b"-hidden-l"):
            links.add(word[len("-hidden-l") :].decode("ascii"))

        elif word == b"-framework":
            frameworks.add(words[i + 1].decode("ascii"))

    return {
        "extension": extension,
        "posix_obj_paths": objs,
        "links": links,
        "frameworks": frameworks,
        "variant": variant or "default",
    }


def link_for_target(lib: str, target_triple: str) -> str:
    # TODO use -Wl,-hidden-lbz2?
    # TODO use -Wl,--exclude-libs,libfoo.a?
    if "-apple-" in target_triple:
        return f"-Xlinker -hidden-l{lib}"
    else:
        return f"-l{lib}"


def meets_python_minimum_version(got: str, wanted: str) -> bool:
    parts = got.split(".")
    got_major, got_minor = int(parts[0]), int(parts[1])

    parts = wanted.split(".")
    wanted_major, wanted_minor = int(parts[0]), int(parts[1])

    return (got_major, got_minor) >= (wanted_major, wanted_minor)


def meets_python_maximum_version(got: str, wanted: str) -> bool:
    parts = got.split(".")
    got_major, got_minor = int(parts[0]), int(parts[1])

    parts = wanted.split(".")
    wanted_major, wanted_minor = int(parts[0]), int(parts[1])

    return (got_major, got_minor) <= (wanted_major, wanted_minor)


def derive_setup_local(
    static_modules_lines,
    cpython_source_archive,
    python_version,
    target_triple,
    extension_modules,
    musl=False,
    debug=False,
):
    """Derive the content of the Modules/Setup.local file."""

    disabled = set()

    for name, info in sorted(extension_modules.items()):
        python_min_match = meets_python_minimum_version(
            python_version, info.get("minimum-python-version", "1.0")
        )
        python_max_match = meets_python_maximum_version(
            python_version, info.get("maximum-python-version", "100.0")
        )

        if not (python_min_match and python_max_match):
            log(
                f"disabling extension module {name} because Python version incompatible"
            )
            disabled.add(name.encode("ascii"))

        if targets := info.get("disabled-targets"):
            if any(re.match(p, target_triple) for p in targets):
                log(
                    "disabling extension module %s because disabled for this target triple"
                    % name
                )
                disabled.add(name.encode("ascii"))

    # makesetup parses lines with = as extra config options. There appears
    # to be no easy way to define e.g. -Dfoo=bar in Setup.local. We hack
    # around this by producing a Makefile supplement that overrides the build
    # rules for certain targets to include these missing values.
    extra_cflags = {}

    disabled = disabled or set()

    if debug:
        # Doesn't work in debug builds.
        disabled.add(b"xxlimited")
        disabled.add(b"xxlimited_35")

    with tarfile.open(str(cpython_source_archive)) as tf:
        ifh = tf.extractfile("Python-%s/Modules/Setup" % python_version)

        source_lines = ifh.readlines()

        ifh = tf.extractfile("Python-%s/Modules/config.c.in" % python_version)
        config_c_in = ifh.read()

    dest_lines = []
    make_lines = []
    dist_modules = set()

    RE_VARIABLE = re.compile(rb"^[a-zA-Z_]+\s*=")
    RE_EXTENSION_MODULE = re.compile(rb"^([a-z_]+)\s+[a-zA-Z/_-]+\.c\s")

    for line in source_lines:
        line = line.rstrip()

        if not line:
            continue

        # Looks like a variable assignment.
        if RE_VARIABLE.match(line):
            continue

        if line == b"#*shared*":
            # Convert all shared extension modules to static.
            dest_lines.append(b"*static*")

        # Look for all extension modules.
        if b"#" in line:
            # Look for extension syntax before and after comment.
            for part in line.split(b"#"):
                if m := RE_EXTENSION_MODULE.match(part):
                    dist_modules.add(m.group(1).decode("ascii"))
                    break

    missing = dist_modules - set(extension_modules.keys())

    if missing:
        raise Exception(
            "missing extension modules from YAML: %s" % ", ".join(sorted(missing))
        )

    RE_DEFINE = re.compile(rb"-D[^=]+=[^\s]+")
    RE_VARIANT = re.compile(rb"VARIANT=([^\s]+)\s")

    seen_variants = set()
    seen_extensions = set()

    # Collect all extension modules seen in the static-modules file.
    for line in static_modules_lines:
        entry = parse_setup_line(line, "")
        if entry:
            seen_extensions.add(entry["extension"])

    static_modules_lines = list(static_modules_lines)

    # Derive lines from YAML metadata.

    # Ensure pure YAML extensions are emitted.
    for name in sorted(set(extension_modules.keys()) - seen_extensions):
        info = extension_modules[name]

        if "sources" not in info:
            continue

        log(f"deriving Setup line for {name}")

        line = name

        for source in info.get("sources", []):
            line += " %s" % source

        for entry in info.get("sources-conditional", []):
            if targets := entry.get("targets", []):
                target_match = any(re.match(p, target_triple) for p in targets)
            else:
                target_match = True

            python_min_match = meets_python_minimum_version(
                python_version, entry.get("minimum-python-version", "1.0")
            )
            python_max_match = meets_python_maximum_version(
                python_version, entry.get("maximum-python-version", "100.0")
            )

            if target_match and (python_min_match and python_max_match):
                line += f" {entry['source']}"

        for define in info.get("defines", []):
            line += f" -D{define}"

        for entry in info.get("defines-conditional", []):
            if targets := entry.get("targets", []):
                target_match = any(re.match(p, target_triple) for p in targets)
            else:
                target_match = True

            python_min_match = meets_python_minimum_version(
                python_version, entry.get("minimum-python-version", "1.0")
            )

            if target_match and python_min_match:
                line += f" -D{entry['define']}"

        for path in info.get("includes", []):
            line += f" -I{path}"

        for entry in info.get("includes-conditional", []):
            if any(re.match(p, target_triple) for p in entry["targets"]):
                line += f" -I{entry['path']}"

        for path in info.get("includes-deps", []):
            # Includes are added to global search path.
            if "-apple-" in target_triple:
                continue

            line += f" -I/tools/deps/{path}"

        for lib in info.get("links", []):
            line += " %s" % link_for_target(lib, target_triple)

        for entry in info.get("links-conditional", []):
            if any(re.match(p, target_triple) for p in entry["targets"]):
                line += " %s" % link_for_target(entry["name"], target_triple)

        if "-apple-" in target_triple:
            for framework in info.get("frameworks", []):
                line += f" -framework {framework}"

        for entry in info.get("linker-args", []):
            if any(re.match(p, target_triple) for p in entry["targets"]):
                for arg in entry["args"]:
                    line += f" -Xlinker {arg}"

        static_modules_lines.append(line.encode("ascii"))

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


def extension_modules_config(yaml_path: pathlib.Path):
    """Loads the extension-modules.yml file."""
    with yaml_path.open("r", encoding="utf-8") as fh:
        data = yaml.load(fh, Loader=yaml.SafeLoader)

    jsonschema.validate(data, EXTENSION_MODULES_SCHEMA)

    return data
