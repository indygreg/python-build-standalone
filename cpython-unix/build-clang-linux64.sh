#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# We build the host/main Clang initially using GCC. Then we rebuild
# Clang using Clang.
#
# The behavior of library search paths is a bit wonky.
#
# The binutils/gcc/libstdc++ that we use to build are in a non-standard
# location: /tools/gcc. Furthermore, we want the produced Clang
# distribution to be self-contained and not have dependencies on
# a GCC install.
#
# To solve the latter requirement, we copy various GCC libraries
# and includes into the Clang install directory. When done the way
# we have, Clang automagically finds the header files. And since
# binaries have an rpath of $ORIGIN/../lib, libstdc++ and libgcc_s
# can be found at load time.
#
# However, as part of building itself, Clang executes binaries that
# it itself just built. These binaries need to load a modern libstdc++.
# (The system's libstdc++ is too old.)  Since these just-built binaries
# aren't in an install location, the $ORIGIN/../lib rpath won't work.
# So, we set LD_LIBRARY_PATH when building so the modern libstdc++
# can be located.
#
# Furthermore, Clang itself needs to link against a modern libstdc++.
# But the system library search paths take precedence when invoking
# the linker via clang. We force linking against a modern libstdc++
# by passing -L to the linker when building Clang.
#
# All of these tricks combine to produce a Clang distribution with
# GNU libstdc++ and that uses GNU binutils.

set -ex

ROOT=$(pwd)
SCCACHE="${ROOT}/sccache"

mkdir /tools/extra
tar -C /tools/extra --strip-components=1 -xf ${ROOT}/cmake-${CMAKE_VERSION}-Linux-x86_64.tar.gz

unzip ninja-linux.zip
mv ninja /tools/extra/bin/

export PATH=/tools/extra/bin:/tools/host/bin:$PATH

EXTRA_FLAGS=

if [ -x "${SCCACHE}" ]; then
  "${SCCACHE}" --start-server
  EXTRA_FLAGS="${EXTRA_FLAGS} -DCMAKE_C_COMPILER_LAUNCHER=${SCCACHE} -DCMAKE_CXX_COMPILER_LAUNCHER=${SCCACHE}"
fi

if [ -n "${CI}" ]; then
  NUM_JOBS=${NUM_JOBS_AGGRESSIVE}
else
  NUM_JOBS=${NUM_CPUS}
fi

# clang requires a modern Python to build.
tar -xf Python-${PYTHON_VERSION}.tar.xz
pushd "Python-${PYTHON_VERSION}"
CC="${HOST_CC}" CFLAGS="${EXTRA_HOST_CFLAGS}" CPPFLAGS="${EXTRA_HOST_CFLAGS}" LDFLAGS="${EXTRA_HOST_LDFLAGS}" ./configure \
  --prefix /tools/host \
  --without-ensurepip
make -j "${NUM_CPUS}" install
popd

mkdir llvm
pushd llvm
tar --strip-components=1 -xf ${ROOT}/llvm-project-${CLANG_VERSION}.src.tar.xz
popd

mkdir llvm-objdir
pushd llvm-objdir

# Stage 1: Build with GCC.
mkdir stage1
pushd stage1
cmake \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/tools/clang-stage1 \
    -DCMAKE_C_COMPILER=/tools/host/bin/gcc \
    -DCMAKE_CXX_COMPILER=/tools/host/bin/g++ \
    -DCMAKE_ASM_COMPILER=/tools/host/bin/gcc \
    -DCMAKE_CXX_FLAGS="-Wno-cast-function-type" \
    -DCMAKE_EXE_LINKER_FLAGS="-Wl,-Bsymbolic-functions" \
    -DCMAKE_SHARED_LINKER_FLAGS="-Wl,-Bsymbolic-functions" \
    -DLLVM_ENABLE_PROJECTS="clang" \
    -DLLVM_TARGETS_TO_BUILD=X86 \
    -DLLVM_BINUTILS_INCDIR=/tools/host/include \
    -DLLVM_LINK_LLVM_DYLIB=ON \
    -DLLVM_INSTALL_UTILS=ON \
    ${EXTRA_FLAGS} \
    ../../llvm/llvm

LD_LIBRARY_PATH=/tools/host/lib64 ninja -j ${NUM_JOBS} install

mkdir -p /tools/clang-stage1/lib/gcc/x86_64-unknown-linux-gnu/${GCC_VERSION}
cp -av /tools/host/lib/gcc/x86_64-unknown-linux-gnu/${GCC_VERSION}/* /tools/clang-stage1/lib/gcc/x86_64-unknown-linux-gnu/${GCC_VERSION}/
cp -av /tools/host/lib64/* /tools/clang-stage1/lib/
mkdir -p /tools/clang-stage1/lib32
cp -av /tools/host/lib32/* /tools/clang-stage1/lib32/
cp -av /tools/host/include/* /tools/clang-stage1/include/

popd

find /tools/clang-stage1 | sort

# Stage 2: Build with GCC built Clang.
mkdir stage2
pushd stage2
cmake \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/tools/clang-stage2 \
    -DCMAKE_C_COMPILER=/tools/clang-stage1/bin/clang \
    -DCMAKE_CXX_COMPILER=/tools/clang-stage1/bin/clang++ \
    -DCMAKE_ASM_COMPILER=/tools/clang-stage1/bin/clang \
    -DCMAKE_C_FLAGS="-fPIC" \
    -DCMAKE_CXX_FLAGS="-fPIC -Qunused-arguments -L/tools/clang-stage1/lib" \
    -DCMAKE_EXE_LINKER_FLAGS="-Wl,-Bsymbolic-functions -L/tools/clang-stage1/lib" \
    -DCMAKE_SHARED_LINKER_FLAGS="-Wl,-Bsymbolic-functions -L/tools/clang-stage1/lib" \
    -DLLVM_ENABLE_PROJECTS="clang" \
    -DLLVM_TARGETS_TO_BUILD=X86 \
    -DLLVM_BINUTILS_INCDIR=/tools/host/include \
    -DLLVM_LINK_LLVM_DYLIB=ON \
    -DLLVM_INSTALL_UTILS=ON \
    ${EXTRA_FLAGS} \
    ../../llvm/llvm

LD_LIBRARY_PATH=/tools/clang-stage1/lib ninja -j ${NUM_JOBS} install

mkdir -p /tools/clang-stage2/lib/gcc/x86_64-unknown-linux-gnu/${GCC_VERSION}
cp -av /tools/host/lib/gcc/x86_64-unknown-linux-gnu/${GCC_VERSION}/* /tools/clang-stage2/lib/gcc/x86_64-unknown-linux-gnu/${GCC_VERSION}/
cp -av /tools/host/lib64/* /tools/clang-stage2/lib/
mkdir -p /tools/clang-stage2/lib32
cp -av /tools/host/lib32/* /tools/clang-stage2/lib32/
cp -av /tools/host/include/* /tools/clang-stage2/include/

popd

find /tools/clang-stage2 | sort

# Stage 3: Build with Clang built Clang.
#
# We remove LLVM_TARGETS_TO_BUILD from this configuration, enabling
# support for all targets. The stage 1 and 2 builds don't benefit from
# non-native target support, which is why we exclude host target support
# above.
mkdir stage3
pushd stage3
cmake \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/tools/clang-linux64 \
    -DCMAKE_C_COMPILER=/tools/clang-stage2/bin/clang \
    -DCMAKE_CXX_COMPILER=/tools/clang-stage2/bin/clang++ \
    -DCMAKE_ASM_COMPILER=/tools/clang-stage2/bin/clang \
    -DCMAKE_C_FLAGS="-fPIC" \
    -DCMAKE_CXX_FLAGS="-fPIC -Qunused-arguments -L/tools/clang-stage2/lib" \
    -DCMAKE_EXE_LINKER_FLAGS="-Wl,-Bsymbolic-functions -L/tools/clang-stage2/lib" \
    -DCMAKE_SHARED_LINKER_FLAGS="-Wl,-Bsymbolic-functions -L/tools/clang-stage2/lib" \
    -DLLVM_ENABLE_PROJECTS="clang;compiler-rt;lld" \
    -DLLVM_BINUTILS_INCDIR=/tools/host/include \
    -DLLVM_LINK_LLVM_DYLIB=ON \
    -DLLVM_INSTALL_UTILS=ON \
    -DCOMPILER_RT_BUILD_SANITIZERS=OFF \
    -DCOMPILER_RT_BUILD_LIBFUZZER=OFF \
    -DCOMPILER_RT_BUILD_MEMPROF=OFF \
    -DCOMPILER_RT_BUILD_ORC=OFF \
    -DCOMPILER_RT_BUILD_XRAY=OFF \
    ${EXTRA_FLAGS} \
    ../../llvm/llvm

LD_LIBRARY_PATH=/tools/clang-stage2/lib DESTDIR=${ROOT}/out ninja -j ${NUM_JOBS} install

mkdir -p ${ROOT}/out/tools/clang-linux64/lib/gcc/x86_64-unknown-linux-gnu/${GCC_VERSION}
cp -av /tools/host/lib/gcc/x86_64-unknown-linux-gnu/${GCC_VERSION}/* ${ROOT}/out/tools/clang-linux64/lib/gcc/x86_64-unknown-linux-gnu/${GCC_VERSION}/
cp -av /tools/host/lib64/* ${ROOT}/out/tools/clang-linux64/lib/
mkdir -p ${ROOT}/out/tools/clang-linux64/lib32/
cp -av /tools/host/lib32/* ${ROOT}/out/tools/clang-linux64/lib32/
cp -av /tools/host/include/* ${ROOT}/out/tools/clang-linux64/include/

popd

# Move out of objdir
popd
