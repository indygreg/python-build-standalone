#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

cd /build

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH
export PKG_CONFIG_PATH=/tools/deps/share/pkgconfig:/tools/deps/lib/pkgconfig

tar -xf libXau-${LIBXAU_VERSION}.tar.gz
pushd libXau-${LIBXAU_VERSION}

if [ "${CC}" = "musl-clang" ]; then
    EXTRA_FLAGS="--disable-shared"
fi

CFLAGS="-fPIC" ./configure \
    --prefix=/tools/deps \
    ${EXTRA_FLAGS}

make -j `nproc`
make -j `nproc` install DESTDIR=/build/out
