#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

cd /build

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH

tar -xf libuuid-${UUID_VERSION}.tar.gz
pushd libuuid-${UUID_VERSION}

CFLAGS="-fPIC" CPPFLAGS="-fPIC" ./configure \
    --prefix=/tools/deps \
    --disable-shared

make -j `nproc`
make -j `nproc` install DESTDIR=/build/out
