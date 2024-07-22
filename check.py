#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import venv

ROOT = pathlib.Path(os.path.abspath(__file__)).parent
VENV = ROOT / "venv.dev"
PIP = VENV / "bin" / "pip"
PYTHON = VENV / "bin" / "python"
REQUIREMENTS = ROOT / "requirements.dev.txt"


def bootstrap():
    venv.create(VENV, with_pip=True)

    subprocess.run([str(PIP), "install", "-r", str(REQUIREMENTS)], check=True)

    os.environ["PYBUILD_BOOTSTRAPPED"] = "1"
    os.environ["PATH"] = "%s:%s" % (str(VENV / "bin"), os.environ["PATH"])
    os.environ["PYTHONPATH"] = str(ROOT)

    args = [str(PYTHON), __file__, *sys.argv[1:]]

    os.execv(str(PYTHON), args)


def run_command(command: list[str]) -> int:
    print("$ " + " ".join(command))
    returncode = subprocess.run(
        command, stdout=sys.stdout, stderr=sys.stderr
    ).returncode
    print()
    return returncode


def run():
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    parser = argparse.ArgumentParser(description="Check code.")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Fix problems",
    )
    args = parser.parse_args()

    check_args = []
    format_args = []
    mypy_args = []

    if args.fix:
        check_args.append("--fix")
    else:
        format_args.append("--check")

    check_result = run_command(["ruff", "check"] + check_args)
    format_result = run_command(["ruff", "format"] + format_args)
    mypy_result = run_command(["mypy"] + mypy_args)

    if check_result + format_result + mypy_result:
        print("Checks failed!")
        sys.exit(1)
    else:
        print("Checks passed!")


if __name__ == "__main__":
    try:
        if "PYBUILD_BOOTSTRAPPED" not in os.environ:
            bootstrap()
        else:
            run()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
