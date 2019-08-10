#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import argparse
import json
import multiprocessing
import os
import pathlib
import sys
import tempfile

import docker

from pythonbuild.buildenv import build_environment
from pythonbuild.cpython import derive_setup_local, parse_config_c, parse_setup_line
from pythonbuild.docker import build_docker_image, get_image
from pythonbuild.downloads import DOWNLOADS
from pythonbuild.logging import log, set_logger
from pythonbuild.utils import (
    add_licenses_to_extension_entry,
    download_entry,
    write_package_versions,
)

ROOT = pathlib.Path(os.path.abspath(__file__)).parent.parent
BUILD = ROOT / "build"
DOWNLOADS_PATH = BUILD / "downloads"
SUPPORT = ROOT / "cpython-unix"

MACOSX_DEPLOYMENT_TARGET = "10.9"


REQUIRED_EXTENSIONS = {
    "_codecs",
    "_io",
    "_signal",
    "_thread",
    "_tracemalloc",
    "_weakref",
    "faulthandler",
    "posix",
}


def add_target_env(env, platform, build_env):
    env["NUM_CPUS"] = "%d" % multiprocessing.cpu_count()
    env["TOOLS_PATH"] = build_env.tools_path

    if platform == "linux64":
        env["BUILD_TRIPLE"] = "x86_64-unknown-linux-gnu"
        env["TARGET_TRIPLE"] = "x86_64-unknown-linux-gnu"

    if platform == "macos":
        env["MACOSX_DEPLOYMENT_TARGET"] = MACOSX_DEPLOYMENT_TARGET
        env["BUILD_TRIPLE"] = "x86_64-apple-darwin18.7.0"
        env["TARGET_TRIPLE"] = "x86_64-apple-darwin18.7.0"
        env["PATH"] = "/usr/bin:/bin"


def archive_path(package_name: str, platform: str, musl=False):
    entry = DOWNLOADS[package_name]
    basename = "%s-%s-%s%s.tar" % (
        package_name,
        entry["version"],
        platform,
        "-musl" if musl else "",
    )

    return BUILD / basename


def install_binutils(platform):
    return platform != "macos"


def simple_build(client, image, entry, platform, musl=False, extra_archives=None):
    archive = download_entry(entry, DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        build_env.install_toolchain(
            BUILD, platform, binutils=install_binutils(platform), clang=True, musl=musl
        )

        for a in extra_archives or []:
            build_env.install_artifact_archive(BUILD, a, platform, musl=musl)

        build_env.copy_file(archive)
        build_env.copy_file(SUPPORT / ("build-%s.sh" % entry))

        env = {
            "CC": "clang",
            "TOOLCHAIN": "clang-%s" % platform,
            "%s_VERSION" % entry.upper().replace("-", "_"): DOWNLOADS[entry]["version"],
        }
        if musl:
            env["CC"] = "musl-clang"

        add_target_env(env, platform, build_env)

        build_env.run("build-%s.sh" % entry, environment=env)

        build_env.get_tools_archive(archive_path(entry, platform, musl=musl), "deps")


def build_binutils(client, image):
    """Build binutils in the Docker image."""
    archive = download_entry("binutils", DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        build_env.copy_file(archive)
        build_env.copy_file(SUPPORT / "build-binutils.sh")

        build_env.exec(
            "/build/build-binutils.sh",
            environment={"BINUTILS_VERSION": DOWNLOADS["binutils"]["version"]},
        )

        build_env.get_tools_archive(archive_path("binutils", "linux64"), "host")


def build_gcc(client, image):
    """Build GCC in the Docker image."""
    gcc_archive = download_entry("gcc", DOWNLOADS_PATH)
    gmp_archive = download_entry("gmp", DOWNLOADS_PATH)
    isl_archive = download_entry("isl", DOWNLOADS_PATH)
    mpc_archive = download_entry("mpc", DOWNLOADS_PATH)
    mpfr_archive = download_entry("mpfr", DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        log("copying archives to container...")
        for a in (gcc_archive, gmp_archive, isl_archive, mpc_archive, mpfr_archive):
            build_env.copy_file(a)

        build_env.copy_file(archive_path("binutils", "linux64"))
        build_env.copy_file(SUPPORT / "build-gcc.sh")

        build_env.exec(
            "/build/build-gcc.sh",
            environment={
                "BINUTILS_VERSION": DOWNLOADS["binutils"]["version"],
                "GCC_VERSION": DOWNLOADS["gcc"]["version"],
                "GMP_VERSION": DOWNLOADS["gmp"]["version"],
                "ISL_VERSION": DOWNLOADS["isl"]["version"],
                "MPC_VERSION": DOWNLOADS["mpc"]["version"],
                "MPFR_VERSION": DOWNLOADS["mpfr"]["version"],
            },
        )

        build_env.get_tools_archive(archive_path("gcc", "linux64"), "host")


def build_clang(client, image, platform):
    if "linux" in platform:
        cmake_archive = download_entry("cmake-linux-bin", DOWNLOADS_PATH)
        ninja_archive = download_entry("ninja-linux-bin", DOWNLOADS_PATH)
    elif "macos" in platform:
        cmake_archive = download_entry("cmake-macos-bin", DOWNLOADS_PATH)
        ninja_archive = download_entry("ninja-macos-bin", DOWNLOADS_PATH)

    clang_archive = download_entry("clang", DOWNLOADS_PATH)
    clang_rt_archive = download_entry("clang-compiler-rt", DOWNLOADS_PATH)
    lld_archive = download_entry("lld", DOWNLOADS_PATH)
    llvm_archive = download_entry("llvm", DOWNLOADS_PATH)
    libcxx_archive = download_entry("libc++", DOWNLOADS_PATH)
    libcxxabi_archive = download_entry("libc++abi", DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
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

        tools_path = "clang-%s" % platform
        build_sh = "build-clang-%s.sh" % platform
        binutils = install_binutils(platform)
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

        build_env.install_toolchain(BUILD, platform, binutils=binutils, gcc=gcc)

        build_env.copy_file(SUPPORT / build_sh)
        build_env.run(build_sh, environment=env)

        build_env.get_tools_archive(archive_path("clang", platform), tools_path)


def build_musl(client, image):
    musl_archive = download_entry("musl", DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        build_env.install_toolchain(BUILD, "linux64", binutils=True, clang=True)
        build_env.copy_file(musl_archive)
        build_env.copy_file(SUPPORT / "build-musl.sh")

        env = {
            "MUSL_VERSION": DOWNLOADS["musl"]["version"],
            "TOOLCHAIN": "clang-linux64",
        }

        build_env.run("build-musl.sh", environment=env)

        build_env.get_tools_archive(archive_path("musl", "linux64"), "host")


def build_libedit(client, image, platform, musl=False):
    libedit_archive = download_entry("libedit", DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        build_env.install_toolchain(
            BUILD, platform, binutils=install_binutils(platform), clang=True, musl=musl
        )

        dep_platform = platform
        if musl:
            dep_platform += "-musl"

        build_env.install_artifact_archive(BUILD, "ncurses", platform, musl=musl)
        build_env.copy_file(libedit_archive)
        build_env.copy_file(SUPPORT / "build-libedit.sh")

        env = {
            "CC": "clang",
            "TOOLCHAIN": "clang-linux64",
            "LIBEDIT_VERSION": DOWNLOADS["libedit"]["version"],
        }

        if musl:
            env["CC"] = "musl-clang"

        add_target_env(env, platform, build_env)

        build_env.run("build-libedit.sh", environment=env)
        build_env.get_tools_archive(
            archive_path("libedit", platform, musl=musl), "deps"
        )


def build_readline(client, image, platform, musl=False):
    readline_archive = download_entry("readline", DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        build_env.install_toolchain(
            BUILD, platform, binutils=True, clang=True, musl=musl
        )

        dep_platform = platform
        if musl:
            dep_platform += "-musl"

        build_env.install_artifact_archive(BUILD, "ncurses", platform, musl=musl)
        build_env.copy_file(readline_archive)
        build_env.copy_file(SUPPORT / "build-readline.sh")

        env = {
            "CC": "clang",
            "TOOLCHAIN": "clang-linux64",
            "READLINE_VERSION": DOWNLOADS["readline"]["version"],
        }

        if musl:
            env["CC"] = "musl-clang"

        add_target_env(env, platform, build_env)

        build_env.run("build-readline.sh", environment=env)
        build_env.get_tools_archive(
            archive_path("readline", platform, musl=musl), "deps"
        )


def build_tix(client, image, platform, musl=False):
    tcl_archive = download_entry("tcl", DOWNLOADS_PATH)
    tk_archive = download_entry("tk", DOWNLOADS_PATH)
    tix_archive = download_entry("tix", DOWNLOADS_PATH)

    with build_environment(client, image) as build_env:
        build_env.install_toolchain(
            BUILD, platform, binutils=True, clang=True, musl=musl
        )

        for p in ("tcl", "tk", "libX11", "xorgproto"):
            build_env.install_artifact_archive(BUILD, p, platform, musl=musl)

        for p in (tcl_archive, tk_archive, tix_archive, SUPPORT / "build-tix.sh"):
            build_env.copy_file(p)

        env = {
            "CC": "clang",
            "TOOLCHAIN": "clang-linux64",
            "TCL_VERSION": DOWNLOADS["tcl"]["version"],
            "TIX_VERSION": DOWNLOADS["tix"]["version"],
            "TK_VERSION": DOWNLOADS["tk"]["version"],
        }

        if musl:
            env["CC"] = "musl-clang"

        add_target_env(env, platform, build_env)

        build_env.run("build-tix.sh", environment=env)
        build_env.get_tools_archive(archive_path("tix", platform, musl=musl), "deps")


def python_build_info(build_env, config_c_in, setup_dist, setup_local, libressl=False):
    """Obtain build metadata for the Python distribution."""

    bi = {"core": {"objs": [], "links": []}, "extensions": {}}

    # Object files for the core distribution are found by walking the
    # build artifacts.
    core_objs = set()
    modules_objs = set()

    res = build_env.run_capture(
        ["/usr/bin/find", "/build/out/python/build", "-name", "*.o"], user="build"
    )

    for line in res[1].splitlines():
        if not line.strip():
            continue

        p = pathlib.Path(os.fsdecode(line))
        rel_path = p.relative_to("/build/out/python")

        if rel_path.parts[1] in ("Objects", "Parser", "Python"):
            core_objs.add(rel_path)

        if rel_path.parts[1] == "Modules":
            modules_objs.add(rel_path)

    for p in sorted(core_objs):
        log("adding core object file: %s" % p)
        bi["core"]["objs"].append(str(p))

    libraries = set()

    for line in build_env.run_capture(
        ["/usr/bin/find", "/build/out/python/build/lib", "-name", "*.a"], user="build"
    )[1].splitlines():

        if not line.strip():
            continue

        f = line[len("/build/out/python/build/lib/") :].decode("ascii")

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
    tf = build_env.get_archive("/build/out/python/build/Modules", as_tar=True)

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

    for extension, entries in bi["extensions"].items():
        for entry in entries:
            entry["required"] = extension in REQUIRED_EXTENSIONS

    # Any paths left in modules_objs are not part of any extension and are
    # instead part of the core distribution.
    for p in sorted(modules_objs):
        log("adding core object file %s" % p)
        bi["core"]["objs"].append(str(p))

    return bi


def build_cpython(
    client,
    image,
    platform,
    debug=False,
    optimized=False,
    musl=False,
    libressl=False,
    version=None,
):
    """Build CPython in a Docker image'"""
    entry_name = "cpython-%s" % version
    entry = DOWNLOADS[entry_name]

    python_archive = download_entry(entry_name, DOWNLOADS_PATH)
    setuptools_archive = download_entry("setuptools", DOWNLOADS_PATH)
    pip_archive = download_entry("pip", DOWNLOADS_PATH)

    with (SUPPORT / "static-modules").open("rb") as fh:
        static_modules_lines = [l.rstrip() for l in fh if not l.startswith(b"#")]

    setup = derive_setup_local(
        static_modules_lines,
        python_archive,
        python_version=entry["version"],
        musl=musl,
        debug=debug,
    )

    config_c_in = parse_config_c(setup["config_c_in"].decode("utf-8"))
    setup_dist_content = setup["setup_dist"]
    setup_local_content = setup["setup_local"]
    extra_make_content = setup["make_data"]

    with build_environment(client, image) as build_env:
        build_env.install_toolchain(
            BUILD, platform, binutils=install_binutils(platform), clang=True, musl=musl
        )

        dep_platform = platform
        if musl:
            dep_platform += "-musl"

        # TODO support bdb/gdbm toggle
        packages = {
            "bdb",
            "bzip2",
            "libedit",
            "libffi",
            "libX11",
            "libXau",
            "libxcb",
            "ncurses",
            "readline",
            "sqlite",
            "tcl",
            "tix",
            "tk",
            "uuid",
            "xorgproto",
            "xz",
            "zlib",
        }

        if libressl:
            packages.add("libressl")
        else:
            packages.add("openssl")

        for p in sorted(packages):
            build_env.install_artifact_archive(BUILD, p, platform, musl=musl)

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

        # TODO copy latest pip/setuptools.

        with tempfile.NamedTemporaryFile("wb") as fh:
            fh.write(setup_local_content)
            fh.flush()

            build_env.copy_file(fh.name, dest_name="Setup.local")

        with tempfile.NamedTemporaryFile("wb") as fh:
            fh.write(extra_make_content)
            fh.flush()

            build_env.copy_file(fh.name, dest_name="Makefile.extra")

        env = {
            "CC": "clang",
            "PIP_VERSION": DOWNLOADS["pip"]["version"],
            "PYTHON_VERSION": entry["version"],
            "PYTHON_MAJMIN_VERSION": entry["version"][:3],
            "SETUPTOOLS_VERSION": DOWNLOADS["setuptools"]["version"],
        }

        if musl:
            env["CC"] = "musl-clang"

        if debug:
            env["CPYTHON_DEBUG"] = "1"
        if optimized:
            env["CPYTHON_OPTIMIZED"] = "1"

        build_env.run("build-cpython.sh", environment=env)

        fully_qualified_name = "python%s%sm" % (
            entry["version"][0:3],
            "d" if debug else "",
        )

        # Create PYTHON.json file describing this distribution.
        python_info = {
            "version": "3",
            "os": "linux",
            "arch": "x86_64",
            "python_flavor": "cpython",
            "python_version": entry["version"],
            "python_exe": "install/bin/%s" % fully_qualified_name,
            "python_include": "install/include/%s" % fully_qualified_name,
            "python_stdlib": "install/lib/python%s" % entry["version"][0:3],
            "build_info": python_build_info(
                build_env,
                config_c_in,
                setup_dist_content,
                setup_local_content,
                libressl=libressl,
            ),
            "licenses": entry["licenses"],
            "license_path": "licenses/LICENSE.cpython.txt",
            "tcl_library_path": "install/lib/tcl",
        }

        with tempfile.NamedTemporaryFile("w") as fh:
            json.dump(python_info, fh, sort_keys=True, indent=4)
            fh.flush()

            build_env.copy_file(fh.name, "/build/out/python", dest_name="PYTHON.json")

        basename = "cpython-%s-%s" % (entry["version"], platform)

        if musl:
            basename += "-musl"
        if debug:
            basename += "-debug"
        if optimized:
            basename += "-pgo"

        basename += ".tar"

        dest_path = BUILD / basename

        with dest_path.open("wb") as fh:
            fh.write(build_env.get_archive("/build/out/python"))


def main():
    BUILD.mkdir(exist_ok=True)
    DOWNLOADS_PATH.mkdir(exist_ok=True)
    (BUILD / "logs").mkdir(exist_ok=True)

    try:
        client = docker.from_env()
        client.ping()
    except Exception as e:
        if os.environ.get("PYBUILD_NO_DOCKER"):
            client = None
        else:
            print("unable to connect to Docker: %s" % e)
            return 1

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--platform")
    parser.add_argument("--optimized", action="store_true")
    parser.add_argument("action")

    args = parser.parse_args()

    action = args.action

    name = action
    if args.platform:
        name += "-%s" % args.platform
    if args.debug:
        name += "-debug"
    if args.optimized:
        name += "-pgo"

    platform = args.platform
    musl = False

    if platform and platform.endswith("-musl"):
        musl = True
        platform = platform[:-5]

    log_path = BUILD / "logs" / ("build.%s.log" % name)

    with log_path.open("wb") as log_fh:
        set_logger(name, log_fh)
        if action == "versions":
            write_package_versions(BUILD / "versions")

        elif action.startswith("image-"):
            build_docker_image(client, ROOT, BUILD, action[6:])

        elif action == "binutils":
            build_binutils(client, get_image(client, ROOT, BUILD, "gcc"))

        elif action == "clang":
            build_clang(
                client, get_image(client, ROOT, BUILD, "clang"), platform=platform
            )

        elif action == "gcc":
            build_gcc(client, get_image(client, ROOT, BUILD, "gcc"))

        elif action == "musl":
            build_musl(client, get_image(client, ROOT, BUILD, "gcc"))

        elif action == "libedit":
            build_libedit(
                client,
                get_image(client, ROOT, BUILD, "build"),
                platform=platform,
                musl=musl,
            )

        elif action == "readline":
            build_readline(
                client,
                get_image(client, ROOT, BUILD, "build"),
                platform=platform,
                musl=musl,
            )

        elif action in (
            "bdb",
            "bzip2",
            "gdbm",
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
                platform=platform,
                musl=musl,
            )

        elif action == "libX11":
            simple_build(
                client,
                get_image(client, ROOT, BUILD, "build"),
                action,
                platform=platform,
                musl=musl,
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
                platform=platform,
                musl=musl,
                extra_archives={"x11-util-macros", "xproto"},
            )

        elif action == "xcb-proto":
            simple_build(
                client,
                get_image(client, ROOT, BUILD, "xcb"),
                action,
                platform=platform,
                musl=musl,
            )

        elif action == "libxcb":
            simple_build(
                client,
                get_image(client, ROOT, BUILD, "xcb"),
                action,
                platform=platform,
                musl=musl,
                extra_archives={"libpthread-stubs", "libXau", "xcb-proto", "xproto"},
            )

        elif action == "tix":
            build_tix(
                client,
                get_image(client, ROOT, BUILD, "build"),
                platform=platform,
                musl=musl,
            )

        elif action == "tk":
            simple_build(
                client,
                get_image(client, ROOT, BUILD, "xcb"),
                action,
                platform=platform,
                musl=musl,
                extra_archives={
                    "tcl",
                    "libX11",
                    "libXau",
                    "libxcb",
                    "xcb-proto",
                    "xorgproto",
                },
            )

        elif action == "cpython":
            build_cpython(
                client,
                get_image(client, ROOT, BUILD, "build"),
                platform=platform,
                musl=musl,
                debug=args.debug,
                optimized=args.optimized,
                libressl="PYBUILD_LIBRESSL" in os.environ,
                version=os.environ["PYBUILD_PYTHON_VERSION"][0:3],
            )

        else:
            print("unknown build action: %s" % action)
            return 1


if __name__ == "__main__":
    sys.exit(main())
