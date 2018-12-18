#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -ex

cd /build

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH
export CC=clang
export CXX=clang++

tar -xf gdbm-${GDBM_VERSION}.tar.gz

pushd gdbm-${GDBM_VERSION}

# CPython setup.py looks for libgdbm_compat and gdbm-ndbm.h,
# which require --enable-libgdbm-compat.
CLFAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" ./configure \
    --build=x86_64-unknown-linux-gnu \
    --target=${TARGET} \
    --prefix=/tools/deps \
    --enable-libgdbm-compat

make -j `nproc`
make -j `nproc` install DESTDIR=/build/out
