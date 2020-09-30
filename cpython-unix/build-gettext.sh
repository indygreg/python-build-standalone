#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf gettext-${GETTEXT_VERSION}.tar.gz

pushd gettext-${GETTEXT_VERSION}

# If libunistring exists on the system, it can get picked up and introduce
# an added dependency. So we force use of the bundled version.
CLFAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --disable-shared \
    --disable-java \
    --disable-dependency-tracking \
    --with-included-libcroco \
    --with-included-gettext \
    --with-included-glib \
    --with-included-libunistring \
    --with-included-libxml \
    --without-libiconv-prefix \
    --without-libintl-prefix \
    --without-libncurses-prefix \
    --without-libtermcap-prefix \
    --without-libxcurses-prefix \
    --without-libcurses-prefix \
    --without-libtextstyle-prefix \
    --without-libunistring-prefix \
    --without-libxml2-prefix \
    --without-git

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
