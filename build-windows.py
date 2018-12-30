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
PIP = VENV / 'Scripts' / 'pip.exe'
PYTHON = VENV / 'Scripts' / 'python.exe'
REQUIREMENTS = ROOT / 'requirements.win.txt'
WINDOWS_DIR = ROOT / 'cpython-windows'


def bootstrap():
    BUILD.mkdir(exist_ok=True)
    DIST.mkdir(exist_ok=True)

    venv.create(VENV, with_pip=True)

    subprocess.run([str(PIP), 'install', '-r', str(REQUIREMENTS)],
                   check=True)

    os.environ['PYBUILD_BOOTSTRAPPED'] = '1'
    os.environ['PATH'] = '%s;%s' % (str(VENV / 'bin'), os.environ['PATH'])
    os.environ['PYTHONPATH'] = str(ROOT)
    subprocess.run([str(PYTHON), __file__], check=True)


def run():
    import zstandard
    from pythonbuild.downloads import DOWNLOADS
    from pythonbuild.utils import hash_path

    now = datetime.datetime.utcnow()

    env = dict(os.environ)
    env['PYTHONUNBUFFERED'] = '1'

    subprocess.run([str(PYTHON), 'build.py'],
                   cwd=str(WINDOWS_DIR), env=env, check=True,
                   bufsize=0)

    source_path = BUILD / 'cpython-windows.tar'
    dest_path = DIST / ('cpython-%s-windows-amd64-%s.tar.zst' % (
        DOWNLOADS['cpython-3.7']['version'], now.strftime('%Y%m%dT%H%M')))

    print('compressing Python archive to %s' % dest_path)
    with source_path.open('rb') as ifh, dest_path.open('wb') as ofh:
        cctx = zstandard.ZstdCompressor(level=15)
        cctx.copy_stream(ifh, ofh, source_path.stat().st_size)

    sha256 = hash_path(dest_path)
    print('%s has SHA256 %s' % (dest_path, sha256))


if __name__ == '__main__':
    if 'PERL' not in os.environ:
        print('PERL must point to a perl executable')
        sys.exit(1)

    try:
        if 'PYBUILD_BOOTSTRAPPED' not in os.environ:
            bootstrap()
        else:
            run()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
