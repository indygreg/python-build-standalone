#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

cd /build

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH
export CC=clang
export CXX=clang++

tar -xf libedit-${LIBEDIT_VERSION}.tar.gz

pushd libedit-${LIBEDIT_VERSION}

cflags="${EXTRA_TARGET_CFLAGS} -fPIC -I/tools/deps/include -I/tools/deps/include/ncurses"

# Install to /tools/deps/libedit so it doesn't conflict with readline's files.
CLFAGS="${cflags}" CPPFLAGS="${cflags}" LDFLAGS="-L/tools/deps/lib" \
    ./configure \
        --build=x86_64-unknown-linux-gnu \
        --host=${TARGET} \
        --prefix=/tools/deps/libedit \

make -j `nproc`
make -j `nproc` install DESTDIR=/build/out

# Alias readline/{history.h, readline.h} for readline compatibility.
mkdir /build/out/tools/deps/libedit/include/readline
ln -s ../editline/readline.h /build/out/tools/deps/libedit/include/readline/readline.h
ln -s ../editline/readline.h /build/out/tools/deps/libedit/include/readline/history.h
