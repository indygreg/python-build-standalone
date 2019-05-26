#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

cd /build

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH

tar -xf bzip2-${BZIP2_VERSION}.tar.gz

pushd bzip2-${BZIP2_VERSION}

make -j `nproc` install \
    AR=/tools/host/bin/${TOOLCHAIN_PREFIX}ar \
    CC="${CC}" \
    CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" \
    LDFLAGS="${EXTRA_TARGET_LDFLAGS}" \
    PREFIX=/build/out/tools/deps
