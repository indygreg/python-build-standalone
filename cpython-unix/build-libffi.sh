#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

cd /build

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH

tar -xf libffi-${LIBFFI_VERSION}.tar.gz

pushd libffi-${LIBFFI_VERSION}

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --disable-shared

make -j `nproc`
make -j `nproc` install DESTDIR=/build/out
