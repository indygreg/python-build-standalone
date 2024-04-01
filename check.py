#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

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

    # Lints:
    #   Sort imports
    #   Unused import
    #   Unused variable
    check_args = ["--select", "I,F401,F841"]
    format_args = []

    if args.fix:
        check_args.append("--fix")
    else:
        format_args.append("--check")

    check_result = subprocess.run(["ruff", "check"] + check_args, stdout=sys.stdout, stderr=sys.stderr)
    format_result = subprocess.run(["ruff", "format"] + format_args, stdout=sys.stdout, stderr=sys.stderr)

    sys.exit(check_result.returncode + format_result.returncode)


if __name__ == "__main__":
    try:
        if "PYBUILD_BOOTSTRAPPED" not in os.environ:
            bootstrap()
        else:
            run()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
