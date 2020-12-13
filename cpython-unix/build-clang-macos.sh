#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=$(pwd)
SCCACHE="${ROOT}/sccache"

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
tar --strip-components=1 -xf ${ROOT}/clang-${CLANG_VERSION}.src.tar.xz
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

# This is used in CI to use the 10.15 SDK.
MACOSX_SDK_PATH_10_15=/Applications/Xcode_12.1.1.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk

# This seems to be required on macOS 11 for clang to find system libraries.
MACOSX_SDK_PATH=/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk

if [ -d ${MACOSX_SDK_PATH_10_15} ]; then
  EXTRA_FLAGS=-DDEFAULT_SYSROOT=${MACOSX_SDK_PATH_10_15}
elif [ -d ${MACOSX_SDK_PATH} ]; then
  EXTRA_FLAGS=-DDEFAULT_SYSROOT=${MACOSX_SDK_PATH}
fi

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
    -DLLVM_ENABLE_LIBCXX=ON \
    -DLLVM_OPTIMIZED_TABLEGEN=ON \
    -DLLVM_TARGETS_TO_BUILD=X86 \
    -DLLVM_LINK_LLVM_DYLIB=ON \
    ${EXTRA_FLAGS} \
    ../../llvm

if [ -n "${CI}" ]; then
  NUM_JOBS=${NUM_JOBS_AGGRESSIVE}
else
  NUM_JOBS=0
fi

DESTDIR=${ROOT}/out ninja -j ${NUM_JOBS} install

# We should arguably do a 2nd build using Clang to build Clang.

# Move out of objdir
popd
