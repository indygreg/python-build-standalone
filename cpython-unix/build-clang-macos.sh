#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=$(pwd)
SCCACHE="${ROOT}/sccache"

tar --strip-components=1 -xf ${ROOT}/cmake-${CMAKE_VERSION}-macos-universal.tar.gz

mkdir ninja
pushd ninja
unzip ${ROOT}/ninja-mac.zip
popd

export PATH=${ROOT}/CMake.app/Contents/bin:${ROOT}/ninja/:${PATH}

mkdir llvm
pushd llvm
tar --strip-components=1 -xf ${ROOT}/llvm-project-${CLANG_VERSION}.src.tar.xz
popd

mkdir llvm-objdir
pushd llvm-objdir

# Configure a compiler wrapper if one is defined.
if [ -x "${SCCACHE}" ]; then
    EXTRA_FLAGS="${EXTRA_FLAGS} -DCMAKE_C_COMPILER_LAUNCHER=${SCCACHE} -DCMAKE_CXX_COMPILER_LAUNCHER=${SCCACHE}"
fi

# Stage 1: Build with system Clang
mkdir stage1
pushd stage1
cmake \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/tools/clang-macos \
    -DCMAKE_C_COMPILER=/usr/bin/clang \
    -DCMAKE_CXX_COMPILER=/usr/bin/clang++ \
    -DCMAKE_ASM_COMPILER=/usr/bin/clang \
    -DLLVM_ENABLE_PROJECTS="clang;compiler-rt;libcxx;libcxxabi;lld" \
    -DLLVM_ENABLE_LIBCXX=ON \
    -DLLVM_OPTIMIZED_TABLEGEN=ON \
    -DLLVM_LINK_LLVM_DYLIB=ON \
    -DLLVM_TARGETS_TO_BUILD="AArch64;X86" \
    -DCOMPILER_RT_BUILD_SANITIZERS=OFF \
    -DCOMPILER_RT_BUILD_LIBFUZZER=OFF \
    -DCOMPILER_RT_BUILD_MEMPROF=OFF \
    -DCOMPILER_RT_BUILD_ORC=OFF \
    -DCOMPILER_RT_BUILD_XRAY=OFF \
    ${EXTRA_FLAGS} \
    ../../llvm/llvm

if [ -n "${CI}" ]; then
    NUM_JOBS=${NUM_JOBS_AGGRESSIVE}
else
    NUM_JOBS=${NUM_CPUS}
fi

DESTDIR=${ROOT}/out ninja -j ${NUM_JOBS} install

# We should arguably do a 2nd build using Clang to build Clang.

# Move out of objdir
popd
