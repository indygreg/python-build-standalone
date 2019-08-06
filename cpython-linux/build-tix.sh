#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

cd /build

export PATH=/tools/deps/bin:/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH
export PKG_CONFIG_PATH=/tools/deps/share/pkgconfig:/tools/deps/lib/pkgconfig

# We need the tcl/tk source extracted because tix looks for private symbols.
tar -xf tcl${TCL_VERSION}-src.tar.gz
tar -xf tk${TK_VERSION}-src.tar.gz

tar -xf tix-${TIX_VERSION}.tar.gz

cd cpython-source-deps-tix-${TIX_VERSION}

# Yes, really.
chmod +x configure

# -DUSE_INTERP_RESULT is to allow tix to use deprecated fields or something
# like that.
CFLAGS="-fPIC -DUSE_INTERP_RESULT" ./configure \
    --prefix=/tools/deps \
    --x-includes=/tools/deps/include \
    --x-libraries=/tools/deps/lib \
    --with-tcl=/tools/deps/lib \
    --with-tk=/tools/deps/lib \
    --enable-shared=no

make -j `nproc`
make -j `nproc` install DESTDIR=/build/out
