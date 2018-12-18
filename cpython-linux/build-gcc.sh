#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -e

cd /build

tar -C /tools -xf /build/binutils-linux64.tar
export PATH=/tools/host/bin:$PATH

tar -xf gcc-${GCC_VERSION}.tar.xz
tar -xf gmp-${GMP_VERSION}.tar.xz
tar -xf isl-${ISL_VERSION}.tar.bz2
tar -xf mpc-${MPC_VERSION}.tar.gz
tar -xf mpfr-${MPFR_VERSION}.tar.xz

pushd gcc-${GCC_VERSION}
ln -sf ../gmp-${GMP_VERSION} gmp
ln -sf ../isl-${ISL_VERSION} isl
ln -sf ../mpc-${MPC_VERSION} mpc
ln -sf ../mpfr-${MPFR_VERSION} mpfr
popd

mkdir gcc-objdir

pushd gcc-objdir
../gcc-${GCC_VERSION}/configure \
    --build=x86_64-unknown-linux-gnu \
    --prefix=/tools/host \
    --enable-languages=c,c++ \
    --disable-nls \
    --disable-gnu-unique-object \
    --enable-__cxa_atexit \
    --with-sysroot=/

make -j `nproc`
make -j `nproc` install DESTDIR=/build/out
popd
