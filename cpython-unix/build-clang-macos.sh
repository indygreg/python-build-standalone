#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

tar --strip-components=1 -xf ${ROOT}/cmake-${CMAKE_VERSION}-Darwin-x86_64.tar.gz

mkdir ninja
pushd ninja
unzip ${ROOT}/ninja-mac.zip
popd

export PATH=${ROOT}/CMake.app/Contents/bin:${ROOT}/ninja/:${PATH}

mkdir llvm
pushd llvm
tar --strip-components=1 -xf ${ROOT}/llvm-${LLVM_VERSION}.src.tar.xz
popd

mkdir llvm/tools/clang
pushd llvm/tools/clang
tar --strip-components=1 -xf ${ROOT}/cfe-${CLANG_VERSION}.src.tar.xz
popd

mkdir llvm/tools/lld
pushd llvm/tools/lld
tar --strip-components=1 -xf ${ROOT}/lld-${LLD_VERSION}.src.tar.xz
popd

mkdir llvm/projects/compiler-rt
pushd llvm/projects/compiler-rt
tar --strip-components=1 -xf ${ROOT}/compiler-rt-${CLANG_COMPILER_RT_VERSION}.src.tar.xz
popd

mkdir llvm/projects/libcxx
pushd llvm/projects/libcxx
tar --strip-components=1 -xf ${ROOT}/libcxx-${LIBCXX_VERSION}.src.tar.xz
popd

mkdir llvm/projects/libcxxabi
pushd llvm/projects/libcxxabi
tar --strip-components=1 -xf ${ROOT}/libcxxabi-${LIBCXXABI_VERSION}.src.tar.xz
popd

mkdir llvm-objdir
pushd llvm-objdir

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
    -DLLVM_ENABLE_LIBCXX=ON \
    -DLLVM_OPTIMIZED_TABLEGEN=ON \
    -DLLVM_TARGETS_TO_BUILD=X86 \
    -DLLVM_LINK_LLVM_DYLIB=ON \
    ../../llvm

DESTDIR=${ROOT}/out ninja install

# We should arguably do a 2nd build using Clang to build Clang.

# Move out of objdir
popd
