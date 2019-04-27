#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

cd /build

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH
export CC=clang
export CXX=clang++

tar -xf sqlite-autoconf-3280000.tar.gz
pushd sqlite-autoconf-3280000

CFLAGS="-fPIC" CPPFLAGS="-fPIC" ./configure --prefix /tools/deps

make -j `nproc`
make -j `nproc` install DESTDIR=/build/out
