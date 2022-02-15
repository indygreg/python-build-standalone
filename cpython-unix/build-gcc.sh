#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

cd /build

tar -C /tools -xf /build/binutils-${BINUTILS_VERSION}-linux64.tar
export PATH=/tools/host/bin:$PATH

HAVE_SCCACHE=

if [ -x sccache ]; then
  HAVE_SCCACHE=1
  mv sccache /tools/host/bin/
  cp sccache-wrapper.sh /tools/host/bin/
fi

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

if [ -n "${HAVE_SCCACHE}" ]; then
  sccache --start-server
  export CC="sccache /usr/bin/gcc"
  export CXX="sccache /usr/bin/g++"
  export STAGE_CC_WRAPPER=sccache-wrapper.sh
fi

mkdir gcc-objdir

pushd gcc-objdir

# We don't use GCC for anything other than building llvm/clang. So
# we can skip the 3 stage bootstrap to save time.
../gcc-${GCC_VERSION}/configure \
    --build=x86_64-unknown-linux-gnu \
    --prefix=/tools/host \
    --disable-bootstrap \
    --enable-languages=c,c++ \
    --disable-nls \
    --disable-gnu-unique-object \
    --enable-__cxa_atexit \
    --with-sysroot=/

make -j `nproc`
make -j `nproc` install DESTDIR=/build/out
popd

if [ -n "${HAVE_SCCACHE}" ]; then
  sccache -s
fi

