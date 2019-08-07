#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

cd /build

export PATH=/tools/deps/bin:/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH
export PKG_CONFIG_PATH=/tools/deps/share/pkgconfig:/tools/deps/lib/pkgconfig

tar -xf tk${TK_VERSION}-src.tar.gz
pushd tk8.6.9/unix

CFLAGS="-fPIC" ./configure \
    --prefix=/tools/deps \
    --x-includes=/tools/deps/include \
    --x-libraries=/tools/deps/lib \
    --with-tcl=/tools/deps/lib \
    --enable-shared=no

# For some reason musl isn't link libXau and libxcb. So we hack the Makefile
# to do what we want.
#
# In addition, the wish binary is also failing to link. So we remove it
# from the build and the installation (it shouldn't be needed anyway).
if [ "${CC}" = "musl-clang" ]; then
    sed -i 's/-ldl  -lpthread /-ldl  -lpthread -lXau -lxcb/' tkConfig.sh
    sed -i 's/-lpthread $(X11_LIB_SWITCHES) -ldl  -lpthread/-lpthread $(X11_LIB_SWITCHES) -ldl  -lpthread -lXau -lxcb/' Makefile
    sed -i 's/all: binaries libraries doc/all: libraries/' Makefile
    sed -i 's/install-binaries: $(TK_STUB_LIB_FILE) $(TK_LIB_FILE) ${WISH_EXE}/install-binaries: $(TK_STUB_LIB_FILE) $(TK_LIB_FILE)/' Makefile
fi

make -j `nproc`
touch wish
make -j `nproc` install DESTDIR=/build/out
rm /build/out/tools/deps/bin/wish*
