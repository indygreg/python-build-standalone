#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

tar -xf bzip2-${BZIP2_VERSION}.tar.gz

pushd bzip2-${BZIP2_VERSION}

make -j ${NUM_CPUS} install \
    CC=clang \
    CFLAGS="-fPIC" \
    PREFIX=${ROOT}/out
