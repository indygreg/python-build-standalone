#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`
DEPS_DIR="${ROOT}/deps"

export CC=clang
export CXX=clang++

# We force linking of external static libraries by removing the shared
# libraries. This is hacky. But we're building in a temporary directory
# and it gets the job done.
find ${DEPS_DIR} -name '*.so*' -exec rm {} \;
find ${DEPS_DIR} -name '*.dylib' -exec rm {} \;

cat Python-${PYTHON_VERSION}/Modules/Setup.local

pushd Python-${PYTHON_VERSION}

# Most bits look at CFLAGS. But setup.py only looks at CPPFLAGS.
# So we need to set both.
CFLAGS="-I${DEPS_DIR}/include -I${DEPS_DIR}/lib/libffi-3.2.1/include -I/${DEPS_DIR}/include/ncurses -I${DEPS_DIR}/include/uuid"
CPPFLAGS=$CFLAGS
LDFLAGS="-L${DEPS_DIR}/lib"

CONFIGURE_FLAGS="--prefix=/install --with-openssl=${DEPS_DIR} --without-ensurepip"

if [ -n "${CPYTHON_OPTIMIZED}" ]; then
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --enable-optimizations --with-lto"
fi

CFLAGS=$CFLAGS CPPFLAGS=$CFLAGS LDFLAGS=$LDFLAGS \
    ./configure ${CONFIGURE_FLAGS}

# Supplement produced Makefile with our modifications.
cat ../Makefile.extra >> Makefile

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out/python

# Also copy object files so they can be linked in a custom manner by
# downstream consumers.
for d in Modules Objects Parser Programs Python; do
    mkdir -p ${ROOT}/out/python/build/$d
    cp -av $d/*.o ${ROOT}/out/python/build/$d/
done

# The object files need to be linked against library dependencies. So copy
# library files as well.
mkdir ${ROOT}/out/python/build/lib
cp -av ${DEPS_DIR}/lib/*.a ${ROOT}/out/python/build/lib/

# config.c defines _PyImport_Inittab and extern references to modules, which
# downstream consumers may want to strip. We bundle config.c and config.c.in so
# a custom one can be produced downstream.
# frozen.c is something similar for frozen modules.
# Setup.dist/Setup.local are useful to parse for active modules and library
# dependencies.
cp -av Modules/config.c ${ROOT}/out/python/build/Modules/
cp -av Modules/config.c.in ${ROOT}/out/python/build/Modules/
cp -av Python/frozen.c ${ROOT}/out/python/build/Python/
cp -av Modules/Setup.dist ${ROOT}/out/python/build/Modules/
cp -av Modules/Setup.local ${ROOT}/out/python/build/Modules/

cp ${ROOT}/python-licenses.rst ${ROOT}/out/python/LICENSE.rst
