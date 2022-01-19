#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf ncurses-${NCURSES_VERSION}.tar.gz

# When cross-compiling, ncurses uses the host `tic` to build the terminfo
# database. But our build environment's `tic` is too old to process this
# ncurses version. Our workaround is to build ncurses for the host when
# cross-compiling then make its `tic` available to the target ncurses
# build.
if [[ -n "${CROSS_COMPILING}" && "${PYBUILD_PLATFORM}" != "macos" ]]; then
  echo "building host ncurses to provide modern tic for cross-compile"

  pushd ncurses-${NCURSES_VERSION}
  CC="${HOST_CC}" ./configure --prefix=${TOOLS_PATH}/host --without-cxx --without-tests --without-manpages --enable-widec
  make -j ${NUM_CPUS}
  make -j ${NUM_CPUS} install

  popd

  # Nuke and re-pave the source directory.
  rm -rf ncurses-${NCURSES_VERSION}
  tar -xf ncurses-${NCURSES_VERSION}.tar.gz
fi

pushd ncurses-${NCURSES_VERSION}

# `make install` will strip installed programs (like tic) by default. This is
# fine. However, cross-compiles can run into issues where `strip` doesn't
# recognize the target architecture. We could fix this by overriding strip.
# But we don't care about the installed binaries, so we simply disable
# stripping of the binaries.
CONFIGURE_FLAGS="
    --build=${BUILD_TRIPLE}
    --host=${TARGET_TRIPLE}
    --prefix=/tools/deps
    --without-cxx
    --without-tests
    --without-manpages
    --disable-stripping
    --enable-widec"

# ncurses wants --with-build-cc when cross-compiling. But it insists on CC
# and this value not being equal, even though using the same binary with
# different compiler flags is doable!
if [[ -n "${CROSS_COMPILING}" && "${PYBUILD_PLATFORM}" != "macos" ]]; then
  CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --with-build-cc=$(which "${HOST_CC}")"
fi

if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
  CONFIGURE_FLAGS="${CONFIGURE_FLAGS}
    --datadir=/usr/share
    --sysconfdir=/etc
    --sharedstatedir=/usr/com
    --with-terminfo-dirs=/usr/share/terminfo
    --with-default-terminfo-dir=/usr/share/terminfo
    --disable-db-install
  "
fi

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" ./configure ${CONFIGURE_FLAGS}
make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
