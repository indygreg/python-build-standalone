#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf ncurses-${NCURSES_VERSION}.tar.gz

pushd ncurses-${NCURSES_VERSION}

CONFIGURE_FLAGS="
    --build=${BUILD_TRIPLE}
    --host=${TARGET_TRIPLE}
    --prefix=/tools/deps
    --without-cxx
    --enable-widec"

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

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" ./configure ${CONFIGURE_FLAGS}
make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
