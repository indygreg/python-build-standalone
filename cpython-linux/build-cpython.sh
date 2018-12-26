#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

set -ex

cd /build

export PATH=/tools/clang-linux64/bin:/tools/host/bin:/tools/deps/bin:$PATH
export CC=clang
export CXX=clang++

# We force linking of external static libraries by removing the shared
# libraries. This is hacky. But we're building in a temporary container
# and it gets the job done.
find /tools/deps -name '*.so*' -exec rm {} \;

tar -xf Python-${PYTHON_VERSION}.tar.xz

cat Setup.local
mv Setup.local Python-${PYTHON_VERSION}/Modules/Setup.local

pushd Python-${PYTHON_VERSION}

# Most bits look at CFLAGS. But setup.py only looks at CPPFLAGS.
# So we need to set both.
CFLAGS="-I/tools/deps/include -I/tools/deps/include/ncurses"
CPPFLAGS=$CFLAGS
LDFLAGS="-L/tools/deps/lib"

CONFIGURE_FLAGS="--prefix=/install --with-openssl=/tools/deps --without-ensurepip"

if [ -n "${CPYTHON_OPTIMIZED}" ]; then
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --enable-optimizations --with-lto"
fi

CFLAGS=$CFLAGS CPPFLAGS=$CFLAGS LDFLAGS=$LDFLAGS \
    ./configure ${CONFIGURE_FLAGS}

# Supplement produced Makefile with our modifications.
cat ../Makefile.extra >> Makefile

make -j `nproc`
make -j `nproc` install DESTDIR=/build/out/python

# Also copy object files so they can be linked in a custom manner by
# downstream consumers.
for d in Modules Objects Parser Programs Python; do
    mkdir -p /build/out/python/build/$d
    cp -av $d/*.o /build/out/python/build/$d/
done

# The object files need to be linked against library dependencies. So copy
# library files as well.
mkdir /build/out/python/lib
cp -av /tools/deps/lib/*.a /build/out/python/lib/

# config.c defines _PyImport_Inittab and extern references to modules, which
# downstream consumers may want to strip. We bundle config.c and config.c.in so
# a custom one can be produced downstream.
# frozen.c is something similar for frozen modules.
# Setup.dist/Setup.local are useful to parse for active modules and library
# dependencies.
cp -av Modules/config.c /build/out/python/build/Modules/
cp -av Modules/config.c.in /build/out/python/build/Modules/
cp -av Python/frozen.c /build/out/python/build/Python/
cp -av Modules/Setup.dist /build/out/python/build/Modules/
cp -av Modules/Setup.local /build/out/python/build/Modules/
cp /build/python-licenses.rst /build/out/python/LICENSE.rst
