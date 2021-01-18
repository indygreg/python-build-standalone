#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import argparse
import os
import pathlib
import subprocess
import sys

from pythonbuild.downloads import DOWNLOADS
from pythonbuild.utils import (
    compress_python_archive,
    release_tag_from_git,
)

ROOT = pathlib.Path(os.path.abspath(__file__)).parent.parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"


def main():
    if sys.platform == "linux":
        host_platform = "linux64"
        default_target_triple = "x86_64-unknown-linux-gnu"
        targets = {
            default_target_triple,
            "x86_64-unknown-linux-musl",
        }
    elif sys.platform == "darwin":
        host_platform = "macos"
        default_target_triple = "x86_64-apple-darwin"
        targets = {default_target_triple, "aarch64-apple-darwin"}
    else:
        print("unsupport build platform: %s" % sys.platform)
        return 1

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--target-triple",
        default=default_target_triple,
        choices=targets,
        help="Target host triple to build for",
    )

    parser.add_argument(
        "--optimizations",
        choices={"debug", "noopt", "pgo", "lto", "pgo+lto"},
        default="noopt",
        help="Optimizations to apply when compiling Python",
    )

    parser.add_argument(
        "--libressl", action="store_true", help="Build LibreSSL instead of OpenSSL"
    )
    parser.add_argument(
        "--python",
        choices={"cpython-3.8", "cpython-3.9"},
        default="cpython-3.8",
        help="Python distribution to build",
    )
    parser.add_argument(
        "--no-docker",
        action="store_true",
        default=True if sys.platform == "darwin" else False,
        help="Disable building in Docker",
    )

    args = parser.parse_args()

    target_triple = args.target_triple

    musl = "musl" in target_triple

    env = dict(os.environ)

    env["PYBUILD_HOST_PLATFORM"] = host_platform
    env["PYBUILD_TARGET_TRIPLE"] = target_triple
    env["PYBUILD_OPTIMIZATIONS"] = args.optimizations
    if args.libressl or musl:
        env["PYBUILD_LIBRESSL"] = "1"
    if musl:
        env["PYBUILD_MUSL"] = "1"
    if args.no_docker:
        env["PYBUILD_NO_DOCKER"] = "1"

    entry = DOWNLOADS[args.python]
    env["PYBUILD_PYTHON_VERSION"] = entry["version"]
    env["PYBUILD_PYTHON_MAJOR_VERSION"] = ".".join(entry["version"].split(".")[0:2])

    if "PYBUILD_RELEASE_TAG" in os.environ:
        release_tag = os.environ["PYBUILD_RELEASE_TAG"]
    else:
        release_tag = release_tag_from_git()

    archive_components = [
        "cpython-%s" % entry["version"],
        target_triple,
        args.optimizations,
    ]

    build_basename = "-".join(archive_components) + ".tar"
    dist_basename = "-".join(archive_components + [release_tag])

    subprocess.run(["make"], env=env, check=True)

    DIST.mkdir(exist_ok=True)

    compress_python_archive(BUILD / build_basename, DIST, dist_basename)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
