#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export CC=clang
export CXX=clang++

tar -xf xz-${XZ_VERSION}.tar.gz

pushd xz-${XZ_VERSION}

CFLAGS="-fPIC" CPPFLAGS="-fPIC" CCASFLAGS="-fPIC" ./configure \
    --prefix=/ \
    --disable-xz \
    --disable-xzdec \
    --disable-lzmadec \
    --disable-lzmainfo \
    --disable-lzma-links \
    --disable-scripts

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
