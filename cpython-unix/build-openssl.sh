#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf openssl-${OPENSSL_VERSION}.tar.gz

pushd openssl-${OPENSSL_VERSION}

# Otherwise it gets set to /tools/deps/ssl by default.
EXTRA_FLAGS="--openssldir=/etc/ssl"

# musl is missing support for various primitives.
# TODO disable secure memory is a bit scary. We should look into a proper
# workaround.
if [ "${CC}" = "musl-clang" ]; then
    EXTRA_FLAGS="${EXTRA_FLAGS} no-async -DOPENSSL_NO_ASYNC -D__STDC_NO_ATOMICS__=1 no-engine -DOPENSSL_NO_SECURE_MEMORY"
fi

if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
  OPENSSL_TARGET=darwin64-x86_64-cc
elif [ "${TARGET_TRIPLE}" = "x86_64-unknown-linux-gnu" ]; then
  OPENSSL_TARGET=linux-x86_64
elif [ "${TARGET_TRIPLE}" = "aarch64-unknown-linux-gnu" ]; then
  OPENSSL_TARGET=linux-aarch64
elif [ "${TARGET_TRIPLE}" = "arm-unknown-linux-gnueabihf" ]; then
  OPENSSL_TARGET=linux-armv4
else
  echo "Error: unsupported target"
  exit 1
fi

CFLAGS="${EXTRA_TARGET_CFLAGS}" /usr/bin/perl ./Configure \
    --prefix=/tools/deps \
    ${OPENSSL_TARGET} \
    no-shared \
    ${EXTRA_FLAGS}

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
