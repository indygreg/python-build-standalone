#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

cd /build

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH

tar -xf libedit-${LIBEDIT_VERSION}.tar.gz

pushd libedit-${LIBEDIT_VERSION}

cflags="${EXTRA_TARGET_CFLAGS} -fPIC -I/tools/deps/include -I/tools/deps/include/ncurses"

# musl doesn't define __STDC_ISO_10646__, so work around that.
if [ "${CC}" = "musl-clang" ]; then
    cflags="${cflags} -D__STDC_ISO_10646__=201103L"
fi

# Install to /tools/deps/libedit so it doesn't conflict with readline's files.
CLFAGS="${cflags}" CPPFLAGS="${cflags}" LDFLAGS="-L/tools/deps/lib" \
    ./configure \
        --build=${BUILD_TRIPLE} \
        --host=${TARGET_TRIPLE} \
        --prefix=/tools/deps/libedit \
        --disable-shared

make -j `nproc`
make -j `nproc` install DESTDIR=/build/out

# Alias readline/{history.h, readline.h} for readline compatibility.
mkdir /build/out/tools/deps/libedit/include/readline
ln -s ../editline/readline.h /build/out/tools/deps/libedit/include/readline/readline.h
ln -s ../editline/readline.h /build/out/tools/deps/libedit/include/readline/history.h
