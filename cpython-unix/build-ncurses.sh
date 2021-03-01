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
if [[ "${BUILD_TRIPLE}" != "${TARGET_TRIPLE}" && "${PYBUILD_PLATFORM}" != "macos" ]]; then
  echo "building host ncurses to provide modern tic for cross-compile"

  OLD_CC=${CC}
  unset CC

  if [ -e "${TOOLS_PATH}/${TOOLCHAIN}/bin/clang" ]; then
    export CC="${TOOLS_PATH}/${TOOLCHAIN}/bin/clang"
  fi

  pushd ncurses-${NCURSES_VERSION}
  ./configure --prefix=${TOOLS_PATH}/host --without-cxx --without-tests --without-manpages --enable-widec
  make -j ${NUM_CPUS}
  make -j ${NUM_CPUS} install

  export CC=${OLD_CC}

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
if [[ "${BUILD_TRIPLE}" != "${TARGET_TRIPLE}" && "${PYBUILD_PLATFORM}" != "macos" ]]; then
  # Look for and use our Clang toolchain by default. If not present, fall
  # back to likely path to system GCC.
  if [ -e "${TOOLS_PATH}/${TOOLCHAIN}/bin/clang" ]; then
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --with-build-cc=${TOOLS_PATH}/${TOOLCHAIN}/bin/clang"
  else
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --with-build-cc=/usr/bin/x86_64-linux-gnu-gcc"
  fi
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
