#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -e

cd /build

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH
export CC=clang

tar -xf musl-${MUSL_VERSION}.tar.gz

pushd musl-${MUSL_VERSION}

./configure \
    --prefix=/tools/host \
    --disable-shared

make -j `nproc`
make -j `nproc` install DESTDIR=/build/out

popd
