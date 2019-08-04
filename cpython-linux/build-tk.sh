#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

cd /build

export PATH=/tools/deps/bin:/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH
export PKG_CONFIG_PATH=/tools/deps/share/pkgconfig:/tools/deps/lib/pkgconfig

tar -xf tk${TK_VERSION}-src.tar.gz
pushd tk8.6.9/unix

CFLAGS="-fPIC" ./configure \
    --prefix=/tools/deps \
    --x-includes=/tools/deps/include \
    --x-libraries=/tools/deps/lib \
    --with-tcl=/tools/deps/lib \
    --enable-shared=no
make -j `nproc`
make -j `nproc` install DESTDIR=/build/out
