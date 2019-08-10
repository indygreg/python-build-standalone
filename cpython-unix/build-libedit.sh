#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf libedit-${LIBEDIT_VERSION}.tar.gz

pushd libedit-${LIBEDIT_VERSION}

cflags="${EXTRA_TARGET_CFLAGS} -fPIC -I${TOOLS_PATH}/deps/include -I${TOOLS_PATH}/deps/include/ncurses"

# musl doesn't define __STDC_ISO_10646__, so work around that.
if [ "${CC}" = "musl-clang" ]; then
    cflags="${cflags} -D__STDC_ISO_10646__=201103L"
fi

# Install to /tools/deps/libedit so it doesn't conflict with readline's files.
CLFAGS="${cflags}" CPPFLAGS="${cflags}" LDFLAGS="-L${TOOLS_PATH}/deps/lib" \
    ./configure \
        --build=${BUILD_TRIPLE} \
        --host=${TARGET_TRIPLE} \
        --prefix=/tools/deps/libedit \
        --disable-shared

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out

# Alias readline/{history.h, readline.h} for readline compatibility.
if [ -e ${ROOT}/out/tools/deps/libedit/include ]; then
    mkdir ${ROOT}/out/tools/deps/libedit/include/readline
    ln -s ../editline/readline.h ${ROOT}/out/tools/deps/libedit/include/readline/readline.h
    ln -s ../editline/readline.h ${ROOT}/out/tools/deps/libedit/include/readline/history.h
fi
