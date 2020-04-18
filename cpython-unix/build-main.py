#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import argparse
import datetime
import os
import pathlib
import subprocess
import sys

from pythonbuild.downloads import DOWNLOADS
from pythonbuild.utils import compress_python_archive

ROOT = pathlib.Path(os.path.abspath(__file__)).parent.parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Produce a debug build")
    parser.add_argument(
        "--libressl", action="store_true", help="Build LibreSSL instead of OpenSSL"
    )
    parser.add_argument(
        "--musl", action="store_true", help="Build against musl libc (Linux only)"
    )
    parser.add_argument(
        "--optimized", action="store_true", help="Build an optimized build"
    )
    parser.add_argument(
        "--python",
        choices={"cpython-3.7", "cpython-3.8"},
        default="cpython-3.7",
        help="Python distribution to build",
    )
    parser.add_argument(
        "--no-docker",
        action="store_true",
        default=True if sys.platform == "darwin" else False,
        help="Disable building in Docker",
    )

    args = parser.parse_args()

    env = dict(os.environ)

    if args.debug:
        env["PYBUILD_DEBUG"] = "1"
    if args.libressl:
        env["PYBUILD_LIBRESSL"] = "1"
    if args.musl:
        env["PYBUILD_MUSL"] = "1"
    if args.optimized:
        env["PYBUILD_OPTIMIZED"] = "1"
    if args.no_docker:
        env["PYBUILD_NO_DOCKER"] = "1"

    if sys.platform == "linux":
        platform = "linux64"
    elif sys.platform == "darwin":
        platform = "macos"
    else:
        raise Exception("unhandled platform")

    env["PYBUILD_UNIX_PLATFORM"] = platform

    entry = DOWNLOADS[args.python]
    env["PYBUILD_PYTHON_VERSION"] = entry["version"]
    env["PYBUILD_PYTHON_MAJOR_VERSION"] = ".".join(entry["version"].split(".")[0:2])

    now = datetime.datetime.utcnow()

    subprocess.run(["make"], env=env, check=True)

    basename = "cpython-%s-%s" % (entry["version"], platform)
    extra = ""

    if args.musl:
        basename += "-musl"
        extra = "-musl"
    if args.debug:
        basename += "-debug"
        extra += "-debug"
    if args.optimized:
        basename += "-pgo"
        extra += "-pgo"

    basename += ".tar"

    DIST.mkdir(exist_ok=True)

    compress_python_archive(
        BUILD / basename,
        DIST,
        "cpython-%s-%s%s-%s"
        % (entry["version"], platform, extra, now.strftime("%Y%m%dT%H:%M")),
    )


if __name__ == "__main__":
    sys.exit(main())
