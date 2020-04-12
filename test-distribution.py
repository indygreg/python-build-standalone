#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Script to run Python tests from a distribution archive."""

import json
import pathlib
import subprocess
import sys
import tarfile
import tempfile

import zstandard


def main(args):
    if not args:
        print("Usage: test-distribution.py path/to/distribution.tar.zst")
        return 1

    distribution_path = args[0]

    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)

        with open(distribution_path, "rb") as fh:
            dctx = zstandard.ZstdDecompressor()
            with dctx.stream_reader(fh) as reader:
                with tarfile.open(mode="r|", fileobj=reader) as tf:
                    tf.extractall(td)

        root = td / "python"

        python_json = root / "PYTHON.json"

        with python_json.open("rb") as fh:
            info = json.load(fh)

        test_args = [
            str(root / info["python_exe"]),
            str(root / info["run_tests"]),
        ]

        test_args.extend(args[1:])

        return subprocess.run(test_args).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
