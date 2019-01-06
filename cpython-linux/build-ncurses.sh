#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

cd /build

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH
export CC=clang
export CXX=clang++

tar -xf ncurses-${NCURSES_VERSION}.tar.gz

pushd ncurses-${NCURSES_VERSION}

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" ./configure \
    --build=x86_64-unknown-linux-gnu \
    --host=${TARGET} \
    --prefix=/tools/deps
make -j `nproc`
make -j `nproc` install DESTDIR=/build/out
