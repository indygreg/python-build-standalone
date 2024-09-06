"""
Run Python's test suite.

As of Python 3.13, this script is no longer included in Python itself.
Instead, use:

    $ python -m test --slow-ci

"""

import os
import sys


def main(regrtest_args):
    args = [
        sys.executable,
        "-m",
        "test",
        "--slow-ci",
    ]

    args.extend(regrtest_args)
    print(" ".join(args))

    os.execv(sys.executable, args)


if __name__ == "__main__":
    main(sys.argv[1:])
