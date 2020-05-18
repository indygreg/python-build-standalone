#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -eo pipefail

export PYBUILD_RELEASE_TAG=$(date -u '+%Y%m%dT%H%M')

./build-macos.py --python cpython-3.7 --optimizations debug
./build-macos.py --python cpython-3.7 --optimizations pgo
./build-macos.py --python cpython-3.8 --optimizations debug
./build-macos.py --python cpython-3.8 --optimizations pgo
