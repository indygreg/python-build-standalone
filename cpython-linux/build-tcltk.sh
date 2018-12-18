#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -ex

cd /build

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH
export CC=clang
export CXX=clang++

tar -xf tcl8.6.9-src.tar.gz

pushd tcl8.6.9/unix
./configure --prefix=/tools/deps
make -j `nproc`
make -j `nproc` install DESTDIR=/build/out
make -j `nproc` install
popd

tar -xf libX11-1.5.0.tar.gz
pushd libX11-1.5.0
./configure --prefix=/tools/deps
make -j `nproc`
make -j `nproc` install DEST=/build/out
make -j `nproc` install
popd

tar -xf tk8.6.9.1-src.tar.gz
pushd tk8.6.9/unix

./configure --prefix=/tools/deps --with-tcl=/tools/deps/lib

make -j `nproc`
make -j `nproc` install DESTDIR=/build/out
