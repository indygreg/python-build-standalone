#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH

tar -xf libressl-${LIBRESSL_VERSION}.tar.gz

pushd libressl-${LIBRESSL_VERSION}

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --with-openssldir=/etc/ssl \
    --disable-shared

make -j `nproc`
make -j `nproc` install DESTDIR=${ROOT}/out
