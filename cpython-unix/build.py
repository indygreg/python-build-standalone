#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import docker

from pythonbuild.buildenv import build_environment
from pythonbuild.cpython import (
    derive_setup_local,
    parse_config_c,
    parse_setup_line,
    STDLIB_TEST_PACKAGES,
)
from pythonbuild.docker import build_docker_image, get_image
from pythonbuild.downloads import DOWNLOADS
from pythonbuild.logging import log, set_logger
from pythonbuild.utils import (
    add_env_common,
    add_licenses_to_extension_entry,
    download_entry,
    validate_python_json,
    write_package_versions,
)

ROOT = pathlib.Path(os.path.abspath(__file__)).parent.parent
BUILD = ROOT / "build"
DOWNLOADS_PATH = BUILD / "downloads"
SUPPORT = ROOT / "cpython-unix"

# Target older macOS on x86 for maximum run-time compatibility.
MACOSX_DEPLOYMENT_TARGET_X86 = "10.9"

# ARM macOS only supports 11.0+, so we can use a newer target.
MACOSX_DEPLOYMENT_TARGET_ARM = "11.0"


def install_sccache(build_env):
    """Attempt to install sccache into the build environment.

    This will attempt to locate a sccache executable and copy it
    into the root directory of the build environment.
    """
    candidates = [
        # Prefer a binary in the project itself.
        ROOT
        / "sccache",
    ]

    # Look for sccache in $PATH, but only if the build environment
    # isn't isolated, as copying binaries into an isolated environment
    # may not run. And running sccache in an isolated environment won't
    # do anything meaningful unless an external cache is being used.
    if not build_env.is_isolated:
        for path in os.environ.get("PATH", "").split(":"):
            if not path:
                continue

            candidates.append(pathlib.Path(path) / "sccache")

    for candidate in candidates:
        if candidate.exists():
            build_env.copy_file(candidate)
            return


def add_target_env(env, platform, target_triple, build_env):
    add_env_common(env)

    env["PYBUILD_PLATFORM"] = platform
    env["TOOLS_PATH"] = build_env.tools_path

    if platform == "linux64":
        env["BUILD_TRIPLE"] = "x86_64-unknown-linux-gnu"
        env["TARGET_TRIPLE"] = "x86_64-unknown-linux-gnu"

    if platform == "macos":
        env["BUILD_TRIPLE"] = "x86_64-apple-darwin18.7.0"

        if target_triple == "x86_64-apple-darwin":
            env["MACOSX_DEPLOYMENT_TARGET"] = MACOSX_DEPLOYMENT_TARGET_X86
            env["TARGET_TRIPLE"] = "x86_64-apple-darwin18.7.0"
            arches = ["x86_64"]
            sdk_platform = "macosx"
        elif target_triple == "aarch64-apple-darwin":
            env["MACOSX_DEPLOYMENT_TARGET"] = MACOSX_DEPLOYMENT_TARGET_ARM
            env["TARGET_TRIPLE"] = "aarch64-apple-darwin"
            arches = ["arm64"]
            sdk_platform = "macosx"
        elif target_triple == "aarch64-apple-ios":
            env["TARGET_TRIPLE"] = "aarch64-apple-ios"
            # TODO arm64e not supported by open source Clang.
            arches = ["arm64"]
            sdk_platform = "iphoneos"
        else:
            raise ValueError("unhandled target triple: %s" % target_triple)

        env["PATH"] = "/usr/bin:/bin"

        extra_target_cflags = [
            # Suppress extremely verbose warnings we see with LLVM 10.
            "-Wno-nullability-completeness",
            "-Wno-expansion-to-defined",
            # LLVM 11 contains commit https://reviews.llvm.org/D83250,
            # which enables -Werror for undef-prefix=TARGET_OS_.
            # However, the macOS SDK has headers that reference deprecated
            # TARGET_OS defines, like TARGET_OS_EMBEDDED. So LLVM 11 refuses
            # to work with the macOS SDKs out of the box. We work around
            # this by undoing the -Werror=undef-prefix in that commit.
            "-Wno-undef-prefix",
        ]

        extra_target_ldflags = []

        for arch in arches:
            extra_target_cflags.extend(["-arch", arch])
            extra_target_ldflags.extend(["-arch", arch])

        if "APPLE_SDK_PATH" in os.environ:
            sdk_path = os.environ["APPLE_SDK_PATH"]
        else:
            # macOS SDK has historically been in /usr courtesy of an
            # installer provided by Xcode. But with Catalina, the files
            # are now typically in
            # /Applications/Xcode.app/Contents/Developer/Platforms/.
            # The proper way to resolve this path is with xcrun, which
            # will give us the headers that Xcode is configured to use.
            res = subprocess.run(
                ["xcrun", "--sdk", sdk_platform, "--show-sdk-path"],
                check=True,
                capture_output=True,
                encoding="utf-8",
            )

            sdk_path = res.stdout.strip()

        if not os.path.exists(sdk_path):
            raise Exception("macOS SDK path %s does not exist" % sdk_path)

        extra_target_cflags.extend(
            [
                "-isysroot",
                sdk_path,
                "-F%s" % os.path.join(sdk_path, "System", "Library", "Frameworks"),
                "-I%s" % os.path.join(sdk_path, "System", "Library", "Frameworks"),
            ]
        )

        extra_target_ldflags.extend(["-isysroot", sdk_path])

        env["EXTRA_TARGET_CFLAGS"] = " ".join(extra_target_cflags)
        env["EXTRA_TARGET_LDFLAGS"] = " ".join(extra_target_ldflags)


def toolchain_archive_path(package_name, host_platform):
    entry = DOWNLOADS[package_name]

    basename = "%s-%s-%s.tar" % (package_name, entry["version"], host_platform)

    return BUILD / basename


def install_binutils(platform):
    return platform != "macos"


def simple_build(
    client,
    image,
    entry,
    host_platform,
    target_triple,
    optimizations,
    dest_archive,
    extra_archives=None,
):
    archive = download_entry(entry, DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        build_env.install_toolchain(
            BUILD,
            host_platform,
            binutils=install_binutils(host_platform),
            clang=True,
            musl="musl" in target_triple,
        )

        for a in extra_archives or []:
            build_env.install_artifact_archive(BUILD, a, target_triple, optimizations)

        build_env.copy_file(archive)
        build_env.copy_file(SUPPORT / ("build-%s.sh" % entry))

        env = {
            "CC": "clang",
            "TOOLCHAIN": "clang-%s" % host_platform,
            "%s_VERSION" % entry.upper().replace("-", "_"): DOWNLOADS[entry]["version"],
        }
        if "musl" in target_triple:
            env["CC"] = "musl-clang"

        add_target_env(env, host_platform, target_triple, build_env)

        build_env.run("build-%s.sh" % entry, environment=env)

        build_env.get_tools_archive(dest_archive, "deps")


def build_binutils(client, image, host_platform):
    """Build binutils in the Docker image."""
    archive = download_entry("binutils", DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        install_sccache(build_env)

        build_env.copy_file(archive)
        build_env.copy_file(SUPPORT / "build-binutils.sh")

        env = {"BINUTILS_VERSION": DOWNLOADS["binutils"]["version"]}

        add_env_common(env)

        build_env.run(
            "build-binutils.sh", environment=env,
        )

        build_env.get_tools_archive(
            toolchain_archive_path("binutils", host_platform), "host"
        )


def build_gcc(client, image, host_platform):
    """Build GCC in the Docker image."""
    gcc_archive = download_entry("gcc", DOWNLOADS_PATH)
    gmp_archive = download_entry("gmp", DOWNLOADS_PATH)
    isl_archive = download_entry("isl", DOWNLOADS_PATH)
    mpc_archive = download_entry("mpc", DOWNLOADS_PATH)
    mpfr_archive = download_entry("mpfr", DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        install_sccache(build_env)

        log("copying archives to container...")
        for a in (gcc_archive, gmp_archive, isl_archive, mpc_archive, mpfr_archive):
            build_env.copy_file(a)

        build_env.copy_file(toolchain_archive_path("binutils", host_platform))
        build_env.copy_file(SUPPORT / "build-gcc.sh")

        env = {
            "BINUTILS_VERSION": DOWNLOADS["binutils"]["version"],
            "GCC_VERSION": DOWNLOADS["gcc"]["version"],
            "GMP_VERSION": DOWNLOADS["gmp"]["version"],
            "ISL_VERSION": DOWNLOADS["isl"]["version"],
            "MPC_VERSION": DOWNLOADS["mpc"]["version"],
            "MPFR_VERSION": DOWNLOADS["mpfr"]["version"],
        }

        add_env_common(env)

        build_env.run("build-gcc.sh", environment=env)

        build_env.get_tools_archive(
            toolchain_archive_path("gcc", host_platform), "host"
        )


def build_clang(client, image, host_platform):
    if "linux" in host_platform:
        cmake_archive = download_entry("cmake-linux-bin", DOWNLOADS_PATH)
        ninja_archive = download_entry("ninja-linux-bin", DOWNLOADS_PATH)
    elif "macos" in host_platform:
        cmake_archive = download_entry("cmake-macos-bin", DOWNLOADS_PATH)
        ninja_archive = download_entry("ninja-macos-bin", DOWNLOADS_PATH)

    clang_archive = download_entry("clang", DOWNLOADS_PATH)
    clang_rt_archive = download_entry("clang-compiler-rt", DOWNLOADS_PATH)
    lld_archive = download_entry("lld", DOWNLOADS_PATH)
    llvm_archive = download_entry("llvm", DOWNLOADS_PATH)
    libcxx_archive = download_entry("libc++", DOWNLOADS_PATH)
    libcxxabi_archive = download_entry("libc++abi", DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        install_sccache(build_env)

        log("copying archives to container...")
        for a in (
            cmake_archive,
            ninja_archive,
            clang_archive,
            clang_rt_archive,
            lld_archive,
            llvm_archive,
            libcxx_archive,
            libcxxabi_archive,
        ):
            build_env.copy_file(a)

        tools_path = "clang-%s" % host_platform
        build_sh = "build-clang-%s.sh" % host_platform
        binutils = install_binutils(host_platform)
        gcc = binutils

        env = {
            "CLANG_COMPILER_RT_VERSION": DOWNLOADS["clang-compiler-rt"]["version"],
            "CLANG_VERSION": DOWNLOADS["clang"]["version"],
            "CMAKE_VERSION": DOWNLOADS["cmake-linux-bin"]["version"],
            "COMPILER_RT_VERSION": DOWNLOADS["clang-compiler-rt"]["version"],
            "GCC_VERSION": DOWNLOADS["gcc"]["version"],
            "LIBCXX_VERSION": DOWNLOADS["libc++"]["version"],
            "LIBCXXABI_VERSION": DOWNLOADS["libc++abi"]["version"],
            "LLD_VERSION": DOWNLOADS["lld"]["version"],
            "LLVM_VERSION": DOWNLOADS["llvm"]["version"],
        }

        add_env_common(env)

        build_env.install_toolchain(BUILD, host_platform, binutils=binutils, gcc=gcc)

        build_env.copy_file(SUPPORT / build_sh)
        build_env.run(build_sh, environment=env)

        build_env.get_tools_archive(
            toolchain_archive_path("clang", host_platform), tools_path
        )


def build_musl(client, image, host_platform):
    musl_archive = download_entry("musl", DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        build_env.install_toolchain(BUILD, host_platform, binutils=True, clang=True)
        build_env.copy_file(musl_archive)
        build_env.copy_file(SUPPORT / "build-musl.sh")

        env = {
            "MUSL_VERSION": DOWNLOADS["musl"]["version"],
            "TOOLCHAIN": "clang-%s" % host_platform,
        }

        build_env.run("build-musl.sh", environment=env)

        build_env.get_tools_archive(
            toolchain_archive_path("musl", host_platform), "host"
        )


def build_libedit(
    client, image, host_platform, target_triple, optimizations, dest_archive
):
    libedit_archive = download_entry("libedit", DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        build_env.install_toolchain(
            BUILD,
            host_platform,
            binutils=install_binutils(host_platform),
            clang=True,
            musl="musl" in target_triple,
        )

        build_env.install_artifact_archive(
            BUILD, "ncurses", target_triple, optimizations
        )
        build_env.copy_file(libedit_archive)
        build_env.copy_file(SUPPORT / "build-libedit.sh")

        env = {
            "CC": "clang",
            "TOOLCHAIN": "clang-%s" % host_platform,
            "LIBEDIT_VERSION": DOWNLOADS["libedit"]["version"],
        }

        if "musl" in target_triple:
            env["CC"] = "musl-clang"

        add_target_env(env, host_platform, target_triple, build_env)

        build_env.run("build-libedit.sh", environment=env)
        build_env.get_tools_archive(dest_archive, "deps")


def build_readline(
    client, image, host_platform, target_triple, optimizations, dest_archive
):
    readline_archive = download_entry("readline", DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        build_env.install_toolchain(
            BUILD,
            host_platform,
            binutils=True,
            clang=True,
            musl="musl" in target_triple,
        )

        build_env.install_artifact_archive(
            BUILD, "ncurses", target_triple, optimizations
        )
        build_env.copy_file(readline_archive)
        build_env.copy_file(SUPPORT / "build-readline.sh")

        env = {
            "CC": "clang",
            "TOOLCHAIN": "clang-%s" % host_platform,
            "READLINE_VERSION": DOWNLOADS["readline"]["version"],
        }

        if "musl" in target_triple:
            env["CC"] = "musl-clang"

        add_target_env(env, host_platform, target_triple, build_env)

        build_env.run("build-readline.sh", environment=env)
        build_env.get_tools_archive(dest_archive, "deps")


def build_tix(client, image, host_platform, target_triple, optimizations, dest_archive):
    tcl_archive = download_entry("tcl", DOWNLOADS_PATH)
    tk_archive = download_entry("tk", DOWNLOADS_PATH)
    tix_archive = download_entry("tix", DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        build_env.install_toolchain(
            BUILD,
            host_platform,
            binutils=install_binutils(host_platform),
            clang=True,
            musl="musl" in target_triple,
        )

        depends = {"tcl", "tk"}
        if host_platform != "macos":
            depends |= {"libX11", "xorgproto"}

        for p in sorted(depends):
            build_env.install_artifact_archive(BUILD, p, target_triple, optimizations)

        for p in (tcl_archive, tk_archive, tix_archive, SUPPORT / "build-tix.sh"):
            build_env.copy_file(p)

        env = {
            "CC": "clang",
            "TOOLCHAIN": "clang-%s" % host_platform,
            "TCL_VERSION": DOWNLOADS["tcl"]["version"],
            "TIX_VERSION": DOWNLOADS["tix"]["version"],
            "TK_VERSION": DOWNLOADS["tk"]["version"],
        }

        if "musl" in target_triple:
            env["CC"] = "musl-clang"

        add_target_env(env, host_platform, target_triple, build_env)

        build_env.run("build-tix.sh", environment=env)
        build_env.get_tools_archive(dest_archive, "deps")


def python_build_info(
    build_env,
    version,
    platform,
    target_triple,
    musl,
    optimizations,
    config_c_in,
    setup_dist,
    setup_local,
    libressl=False,
):
    """Obtain build metadata for the Python distribution."""

    log("resolving Python distribution build info")

    bi = {"core": {"objs": [], "links": []}, "extensions": {}}

    binary_suffix = ""

    if platform == "linux64":
        bi["core"][
            "static_lib"
        ] = "install/lib/python{version}/config-{version}{binary_suffix}-x86_64-linux-gnu/libpython{version}{binary_suffix}.a".format(
            version=version, binary_suffix=binary_suffix
        )

        if not musl:
            bi["core"]["shared_lib"] = "install/lib/libpython%s%s.so.1.0" % (
                version,
                binary_suffix,
            )

        if optimizations in ("lto", "pgo+lto"):
            object_file_format = "llvm-bitcode:%s" % DOWNLOADS["llvm"]["version"]
        else:
            object_file_format = "elf"
    elif platform == "macos":
        bi["core"][
            "static_lib"
        ] = "install/lib/python{version}/config-{version}{binary_suffix}-darwin/libpython{version}{binary_suffix}.a".format(
            version=version, binary_suffix=binary_suffix
        )
        bi["core"]["shared_lib"] = "install/lib/libpython%s%s.dylib" % (
            version,
            binary_suffix,
        )

        if optimizations in ("lto", "pgo+lto"):
            object_file_format = "llvm-bitcode:%s" % DOWNLOADS["llvm"]["version"]
        else:
            object_file_format = "mach-o"
    else:
        raise Exception("unsupported platform: %s" % platform)

    bi["object_file_format"] = object_file_format

    # Object files for the core distribution are found by walking the
    # build artifacts.
    core_objs = set()
    modules_objs = set()

    for f in build_env.find_output_files("python/build", "*.o"):
        rel_path = pathlib.Path("build") / f

        if rel_path.parts[1] in ("Objects", "Parser", "Python"):
            core_objs.add(rel_path)

        if rel_path.parts[1] == "Modules":
            modules_objs.add(rel_path)

    for p in sorted(core_objs):
        log("adding core object file: %s" % p)
        bi["core"]["objs"].append(str(p))

    assert pathlib.Path("build/Modules/config.o") in modules_objs
    bi["inittab_object"] = "build/Modules/config.o"
    bi["inittab_source"] = "build/Modules/config.c"
    # TODO ideally we'd get these from the build environment
    bi["inittab_cflags"] = ["-std=c99", "-DNDEBUG", "-DPy_BUILD_CORE"]

    libraries = set()

    for f in build_env.find_output_files("python/build/lib", "*.a"):
        # Strip "lib" prefix and ".a" suffix.
        libname = f[3:-2]

        libraries.add(libname)

    # Extension data is derived by "parsing" the Setup.dist and Setup.local files.

    def process_setup_line(line, variant=None):
        d = parse_setup_line(line, variant)

        if not d:
            return

        extension = d["extension"]
        log("processing extension %s (variant %s)" % (extension, d["variant"]))

        objs = []

        for obj in sorted(d["posix_obj_paths"]):
            obj = pathlib.Path("build") / obj
            log("adding object file %s for extension %s" % (obj, extension))
            objs.append(str(obj))

            # Mark object file as used so we don't include it in the core
            # object files below. .remove() would be nicer, as we would catch
            # missing object files. But some sources (like math.c) are used by
            # multiple modules!
            modules_objs.discard(obj)

        links = []

        for framework in sorted(d["frameworks"]):
            log("adding framework %s for extension %s" % (framework, extension))
            links.append({"name": framework, "framework": True})

        for libname in sorted(d["links"]):
            log("adding library %s for extension %s" % (libname, extension))

            if libname in libraries:
                entry = {"name": libname, "path_static": "build/lib/lib%s.a" % libname}

                links.append(entry)
            else:
                links.append({"name": libname, "system": True})

        entry = {
            "in_core": False,
            "init_fn": "PyInit_%s" % extension,
            "links": links,
            "objs": objs,
            "variant": d["variant"],
        }

        if libressl:
            ignore_keys = {"openssl"}
        else:
            ignore_keys = {"libressl"}

        add_licenses_to_extension_entry(entry, ignore_keys=ignore_keys)

        bi["extensions"].setdefault(extension, []).append(entry)

    found_start = False

    for line in setup_dist.splitlines():
        if not found_start:
            if line.startswith(b"PYTHONPATH="):
                found_start = True
                continue

            continue

        process_setup_line(line)

    for line in setup_local.splitlines():
        if line.startswith(b"*static*"):
            continue

        if line.startswith(b"*disabled*"):
            break

        process_setup_line(line)

    # Extension variants are denoted by the presence of
    # Modules/VARIANT-<extension>-<variant>.data files that describe the
    # extension. Find those files and process them.
    tf = build_env.get_output_archive("python/build/Modules", as_tar=True)

    for ti in tf:
        basename = os.path.basename(ti.name)

        if not basename.startswith("VARIANT-") or not basename.endswith(".data"):
            continue

        variant = basename[:-5].split("-")[2]
        line = tf.extractfile(ti).read().strip()
        process_setup_line(line, variant=variant)

    # There are also a setup of built-in extensions defined in config.c.in which
    # aren't built using the Setup.* files and are part of the core libpython
    # distribution. Define extensions entries for these so downstream consumers
    # can register their PyInit_ functions.
    for name, init_fn in sorted(config_c_in.items()):
        log("adding in-core extension %s" % name)
        bi["extensions"].setdefault(name, []).append(
            {
                "in_core": True,
                "init_fn": init_fn,
                "links": [],
                "objs": [],
                "variant": "default",
            }
        )

    with get_target_support_file(
        "required-extensions", version, platform, target_triple
    ).open("r") as fh:
        required_extensions = {l.strip() for l in fh if l.strip()}

    for extension, entries in bi["extensions"].items():
        for entry in entries:
            entry["required"] = extension in required_extensions

    # Any paths left in modules_objs are not part of any extension and are
    # instead part of the core distribution.
    for p in sorted(modules_objs):
        log("adding core object file %s" % p)
        bi["core"]["objs"].append(str(p))

    return bi


def get_target_support_file(prefix, python_version, host_platform, target_triple):
    candidates = [
        SUPPORT / ("%s.%s.%s" % (prefix, python_version, target_triple)),
        SUPPORT / ("%s.%s.%s" % (prefix, python_version, host_platform)),
    ]

    for path in candidates:
        if path.exists():
            return path

    raise Exception(
        "Could not find support file %s for (%s, %s, %s)",
        prefix,
        python_version,
        host_platform,
        target_triple,
    )


def build_cpython(
    client,
    image,
    host_platform,
    target_triple,
    optimizations,
    dest_archive,
    libressl=False,
    version=None,
):
    """Build CPython in a Docker image'"""
    entry_name = "cpython-%s" % version
    entry = DOWNLOADS[entry_name]

    python_archive = download_entry(entry_name, DOWNLOADS_PATH)
    setuptools_archive = download_entry("setuptools", DOWNLOADS_PATH)
    pip_archive = download_entry("pip", DOWNLOADS_PATH)

    with get_target_support_file(
        "static-modules", version, host_platform, target_triple
    ).open("rb") as fh:
        static_modules_lines = [l.rstrip() for l in fh if not l.startswith(b"#")]

    with get_target_support_file(
        "disabled-static-modules", version, host_platform, target_triple
    ).open("rb") as fh:
        disabled_static_modules = {
            l.strip() for l in fh if l.strip() and not l.strip().startswith(b"#")
        }

    setup = derive_setup_local(
        static_modules_lines,
        python_archive,
        python_version=entry["version"],
        musl="musl" in target_triple,
        debug=optimizations == "debug",
        disabled=disabled_static_modules,
    )

    config_c_in = parse_config_c(setup["config_c_in"].decode("utf-8"))
    setup_dist_content = setup["setup_dist"]
    setup_local_content = setup["setup_local"]
    extra_make_content = setup["make_data"]

    with build_environment(client, image) as build_env:
        build_env.install_toolchain(
            BUILD,
            host_platform,
            binutils=install_binutils(host_platform),
            clang=True,
            musl="musl" in target_triple,
        )

        # TODO support bdb/gdbm toggle
        packages = {
            "bzip2",
            "libffi",
            "xz",
            "zlib",
        }

        bdb = host_platform != "macos"
        if bdb:
            packages.add("bdb")

        libedit = target_triple != "aarch64-apple-ios"
        if libedit:
            packages.add("libedit")

        if libressl:
            packages.add("libressl")
        else:
            packages.add("openssl")

        # We use the system ncurses on macOS for now.
        ncurses = host_platform != "macos"
        if ncurses:
            packages.add("ncurses")

        readline = host_platform != "macos"
        if readline:
            packages.add("readline")

        sqlite = target_triple != "aarch64-apple-ios"
        if sqlite:
            packages.add("sqlite")

        tk = target_triple != "aarch64-apple-ios"
        if tk:
            packages |= {"tcl", "tix", "tk"}

        uuid = target_triple != "aarch64-apple-ios"
        if uuid:
            packages.add("uuid")

        if host_platform == "linux64":
            packages |= {"libX11", "libXau", "libxcb", "xorgproto"}

        for p in sorted(packages):
            build_env.install_artifact_archive(BUILD, p, target_triple, optimizations)

        for p in (
            python_archive,
            setuptools_archive,
            pip_archive,
            SUPPORT / "build-cpython.sh",
        ):
            build_env.copy_file(p)

        for f in sorted(os.listdir(ROOT)):
            if f.startswith("LICENSE.") and f.endswith(".txt"):
                build_env.copy_file(ROOT / f)

        with tempfile.NamedTemporaryFile("wb") as fh:
            # In case default file masks cause wonkiness.
            os.chmod(fh.name, 0o644)

            fh.write(setup_local_content)
            fh.flush()

            build_env.copy_file(fh.name, dest_name="Setup.local")

        with tempfile.NamedTemporaryFile("wb") as fh:
            os.chmod(fh.name, 0o644)
            fh.write(extra_make_content)
            fh.flush()

            build_env.copy_file(fh.name, dest_name="Makefile.extra")

        env = {
            "CC": "clang",
            "PIP_VERSION": DOWNLOADS["pip"]["version"],
            "PYTHON_VERSION": entry["version"],
            "PYTHON_MAJMIN_VERSION": entry["version"][:3],
            "SETUPTOOLS_VERSION": DOWNLOADS["setuptools"]["version"],
            "TOOLCHAIN": "clang-%s" % host_platform,
        }

        if "musl" in target_triple:
            env["CC"] = "musl-clang"

        if optimizations == "debug":
            env["CPYTHON_DEBUG"] = "1"
        if optimizations in ("pgo", "pgo+lto"):
            env["CPYTHON_OPTIMIZED"] = "1"
        if optimizations in ("lto", "pgo+lto"):
            env["CPYTHON_LTO"] = "1"

        add_target_env(env, host_platform, target_triple, build_env)

        build_env.run("build-cpython.sh", environment=env)

        extension_module_loading = ["builtin"]
        crt_features = []

        if host_platform == "linux64":
            if "musl" in target_triple:
                crt_features.append("static")
            else:
                extension_module_loading.append("shared-library")
                crt_features.append("glibc-dynamic")

                glibc_max_version = build_env.get_file("glibc_version.txt").strip()
                if not glibc_max_version:
                    raise Exception("failed to retrieve glibc max symbol version")

                crt_features.append(
                    "glibc-max-symbol-version:%s" % glibc_max_version.decode("ascii")
                )

            python_symbol_visibility = "global-default"

        elif host_platform == "macos":
            python_symbol_visibility = "global-default"
            extension_module_loading.append("shared-library")
            crt_features.append("libSystem")
        else:
            raise ValueError("unhandled platform: %s" % host_platform)

        # Create PYTHON.json file describing this distribution.
        python_info = {
            "version": "6",
            "target_triple": target_triple,
            "optimizations": optimizations,
            "python_tag": entry["python_tag"],
            "python_version": entry["version"],
            "python_stdlib_test_packages": sorted(STDLIB_TEST_PACKAGES),
            "python_symbol_visibility": python_symbol_visibility,
            "python_extension_module_loading": extension_module_loading,
            "libpython_link_mode": "static" if "musl" in target_triple else "shared",
            "crt_features": crt_features,
            "run_tests": "build/run_tests.py",
            "build_info": python_build_info(
                build_env,
                version,
                host_platform,
                target_triple,
                "musl" in target_triple,
                optimizations,
                config_c_in,
                setup_dist_content,
                setup_local_content,
                libressl=libressl,
            ),
            "licenses": entry["licenses"],
            "license_path": "licenses/LICENSE.cpython.txt",
        }

        python_info["tcl_library_path"] = "install/lib"
        python_info["tcl_library_paths"] = [
            "tcl8",
            "tcl8.6",
            "thread2.8.5",
            "Tix8.4.3",
            "tk8.6",
        ]

        # Add metadata derived from built distribution.
        extra_metadata = build_env.get_file("metadata.json")
        python_info.update(json.loads(extra_metadata))

        validate_python_json(python_info)

        with tempfile.NamedTemporaryFile("w") as fh:
            json.dump(python_info, fh, sort_keys=True, indent=4)
            fh.flush()

            if image:
                dest_path = "/build/out/python"
            else:
                dest_path = "out/python"

            build_env.copy_file(fh.name, dest_path, dest_name="PYTHON.json")

        with open(dest_archive, "wb") as fh:
            fh.write(build_env.get_output_archive("python"))


def main():
    BUILD.mkdir(exist_ok=True)
    DOWNLOADS_PATH.mkdir(exist_ok=True)
    (BUILD / "logs").mkdir(exist_ok=True)

    if os.environ.get("PYBUILD_NO_DOCKER"):
        client = None
    else:
        try:
            client = docker.from_env()
            client.ping()
        except Exception as e:
            print("unable to connect to Docker: %s" % e)
            return 1

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--host-platform", required=True, help="Platform we are building from"
    )
    parser.add_argument(
        "--target-triple",
        required=True,
        help="Host triple that we are building Python for",
    )
    parser.add_argument(
        "--optimizations",
        choices={"debug", "noopt", "pgo", "lto", "pgo+lto"},
        required=True,
        help="Optimization profile to use",
    )
    parser.add_argument(
        "--toolchain",
        action="store_true",
        help="Indicates we are building a toolchain artifact",
    )
    parser.add_argument(
        "--dest-archive", required=True, help="Path to archive that we are producing"
    )
    parser.add_argument("action")

    args = parser.parse_args()

    action = args.action

    target_triple = args.target_triple
    host_platform = args.host_platform
    optimizations = args.optimizations
    dest_archive = pathlib.Path(args.dest_archive)

    if args.action == "versions":
        log_name = "versions"
    elif args.action.startswith("image-"):
        log_name = "image-%s" % action
    elif args.toolchain:
        log_name = "%s-%s" % (action, host_platform)
    else:
        entry = DOWNLOADS[action]
        log_name = "%s-%s-%s-%s" % (
            action,
            entry["version"],
            target_triple,
            optimizations,
        )

    log_path = BUILD / "logs" / ("build.%s.log" % log_name)

    with log_path.open("wb") as log_fh:
        set_logger(action, log_fh)
        if action == "versions":
            write_package_versions(BUILD / "versions")

        elif action.startswith("image-"):
            build_docker_image(client, ROOT, BUILD, action[6:])

        elif action == "binutils":
            build_binutils(client, get_image(client, ROOT, BUILD, "gcc"), host_platform)

        elif action == "clang":
            build_clang(
                client,
                get_image(client, ROOT, BUILD, "clang"),
                host_platform=host_platform,
            )

        elif action == "gcc":
            build_gcc(client, get_image(client, ROOT, BUILD, "gcc"), host_platform)

        elif action == "musl":
            build_musl(client, get_image(client, ROOT, BUILD, "gcc"), host_platform)

        elif action == "libedit":
            build_libedit(
                client,
                get_image(client, ROOT, BUILD, "build"),
                host_platform=host_platform,
                target_triple=target_triple,
                optimizations=optimizations,
                dest_archive=dest_archive,
            )

        elif action == "readline":
            build_readline(
                client,
                get_image(client, ROOT, BUILD, "build"),
                host_platform=host_platform,
                target_triple=target_triple,
                optimizations=optimizations,
                dest_archive=dest_archive,
            )

        elif action in (
            "bdb",
            "bzip2",
            "gdbm",
            "gettext",
            "inputproto",
            "kbproto",
            "libffi",
            "libpthread-stubs",
            "libressl",
            "ncurses",
            "openssl",
            "sqlite",
            "tcl",
            "uuid",
            "x11-util-macros",
            "xextproto",
            "xorgproto",
            "xproto",
            "xtrans",
            "xz",
            "zlib",
        ):
            simple_build(
                client,
                get_image(client, ROOT, BUILD, "build"),
                action,
                host_platform=host_platform,
                target_triple=target_triple,
                optimizations=optimizations,
                dest_archive=dest_archive,
            )

        elif action == "libX11":
            simple_build(
                client,
                get_image(client, ROOT, BUILD, "build"),
                action,
                host_platform=host_platform,
                target_triple=target_triple,
                optimizations=optimizations,
                dest_archive=dest_archive,
                extra_archives={
                    "inputproto",
                    "kbproto",
                    "libpthread-stubs",
                    "libXau",
                    "libxcb",
                    "x11-util-macros",
                    "xextproto",
                    "xorgproto",
                    "xproto",
                    "xtrans",
                },
            )

        elif action == "libXau":
            simple_build(
                client,
                get_image(client, ROOT, BUILD, "build"),
                action,
                host_platform=host_platform,
                target_triple=target_triple,
                optimizations=optimizations,
                dest_archive=dest_archive,
                extra_archives={"x11-util-macros", "xproto"},
            )

        elif action == "xcb-proto":
            simple_build(
                client,
                get_image(client, ROOT, BUILD, "xcb"),
                action,
                host_platform=host_platform,
                target_triple=target_triple,
                optimizations=optimizations,
                dest_archive=dest_archive,
            )

        elif action == "libxcb":
            simple_build(
                client,
                get_image(client, ROOT, BUILD, "xcb"),
                action,
                host_platform=host_platform,
                target_triple=target_triple,
                optimizations=optimizations,
                dest_archive=dest_archive,
                extra_archives={"libpthread-stubs", "libXau", "xcb-proto", "xproto"},
            )

        elif action == "tix":
            build_tix(
                client,
                get_image(client, ROOT, BUILD, "build"),
                host_platform=host_platform,
                target_triple=target_triple,
                optimizations=optimizations,
                dest_archive=dest_archive,
            )

        elif action == "tk":
            extra_archives = {"tcl"}
            if host_platform != "macos":
                extra_archives |= {
                    "libX11",
                    "libXau",
                    "libxcb",
                    "xcb-proto",
                    "xorgproto",
                }

            simple_build(
                client,
                get_image(client, ROOT, BUILD, "xcb"),
                action,
                host_platform=host_platform,
                target_triple=target_triple,
                optimizations=optimizations,
                dest_archive=dest_archive,
                extra_archives=extra_archives,
            )

        elif action in ("cpython-3.8", "cpython-3.9"):
            build_cpython(
                client,
                get_image(client, ROOT, BUILD, "build"),
                host_platform=host_platform,
                target_triple=target_triple,
                optimizations=optimizations,
                dest_archive=dest_archive,
                libressl="PYBUILD_LIBRESSL" in os.environ,
                version=action.split("-")[1],
            )

        else:
            print("unknown build action: %s" % action)
            return 1


if __name__ == "__main__":
    sys.exit(main())
