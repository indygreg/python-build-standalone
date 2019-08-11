#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf sqlite-autoconf-${SQLITE_VERSION}.tar.gz
pushd sqlite-autoconf-${SQLITE_VERSION}

CFLAGS="-fPIC" CPPFLAGS="-fPIC" ./configure \
    --prefix /tools/deps \
    --disable-shared

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
