#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -eo pipefail

export PYBUILD_RELEASE_TAG=$(date --utc '+%Y%m%dT%H%M')

./build-linux.py --target-triple x86_64-unknown-linux-gnu --python cpython-3.8 --optimizations debug
./build-linux.py --target-triple x86_64-unknown-linux-gnu --python cpython-3.8 --optimizations pgo
./build-linux.py --target-triple x86_64-unknown-linux-gnu --python cpython-3.9 --optimizations debug
./build-linux.py --target-triple x86_64-unknown-linux-gnu --python cpython-3.9 --optimizations pgo

./build-linux.py --target-triple x86_64-unknown-linux-musl --python cpython-3.8 --optimizations debug --libressl
./build-linux.py --target-triple x86_64-unknown-linux-musl --python cpython-3.8 --optimizations noopt --libressl
./build-linux.py --target-triple x86_64-unknown-linux-musl --python cpython-3.9 --optimizations debug --libressl
./build-linux.py --target-triple x86_64-unknown-linux-musl --python cpython-3.9 --optimizations noopt --libressl
