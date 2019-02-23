#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import datetime
import os
import pathlib
import subprocess
import sys
import venv


ROOT = pathlib.Path(os.path.abspath(__file__)).parent
BUILD = ROOT / 'build'
DIST = ROOT / 'dist'
VENV = BUILD / 'venv'
PIP = VENV / 'bin' / 'pip'
PYTHON = VENV / 'bin' / 'python'
REQUIREMENTS = ROOT / 'requirements.txt'
MAKE_DIR = ROOT / 'cpython-macos'


def bootstrap():
    BUILD.mkdir(exist_ok=True)
    DIST.mkdir(exist_ok=True)

    venv.create(VENV, with_pip=True)

    subprocess.run([str(PIP), 'install', '-r', str(REQUIREMENTS)],
                   check=True)

    os.environ['PYBUILD_BOOTSTRAPPED'] = '1'
    os.environ['PATH'] = '%s:%s' % (str(VENV / 'bin'), os.environ['PATH'])
    os.environ['PYTHONPATH'] = str(ROOT)
    subprocess.run([str(PYTHON), __file__], check=True)


def run():
    from pythonbuild.downloads import DOWNLOADS
    from pythonbuild.utils import compress_python_archive

    now = datetime.datetime.utcnow()

    subprocess.run(['make'],
                   cwd=str(MAKE_DIR), check=True)

    source_path = BUILD / 'cpython-macos.tar'

    compress_python_archive(source_path, DIST, 'cpython-%s-macos-%s' % (
        DOWNLOADS['cpython-3.7']['version'], now.strftime('%Y%m%dT%H%M')))


if __name__ == '__main__':
    try:
        if 'PYBUILD_BOOTSTRAPPED' not in os.environ:
            bootstrap()
        else:
            run()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
