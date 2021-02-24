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
if [ "${BUILD_TRIPLE}" != "${TARGET_TRIPLE}" ]; then
  echo "building host ncurses to provide modern tic for cross-compile"

  pushd ncurses-${NCURSES_VERSION}
  ./configure --prefix=${TOOLS_PATH}/host --without-cxx --without-tests --without-manpages --enable-widec
  make -j ${NUM_CPUS}
  make -j ${NUM_CPUS} install

  popd

  # Nuke and re-pave the source directory.
  rm -rf ncurses-${NCURSES_VERSION}
  tar -xf ncurses-${NCURSES_VERSION}.tar.gz
fi

pushd ncurses-${NCURSES_VERSION}

CONFIGURE_FLAGS="
    --build=${BUILD_TRIPLE}
    --host=${TARGET_TRIPLE}
    --prefix=/tools/deps
    --without-cxx
    --without-tests
    --without-manpages
    --enable-widec"

# ncurses wants --with-build-cc when cross-compiling.
if [ "${BUILD_TRIPLE}" != "${TARGET_TRIPLE}" ]; then
  CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --with-build-cc=${TOOLS_PATH}/${TOOLCHAIN}/bin/clang"
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
