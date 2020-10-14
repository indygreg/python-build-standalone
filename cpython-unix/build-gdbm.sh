#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf gdbm-${GDBM_VERSION}.tar.gz

pushd gdbm-${GDBM_VERSION}

# Patch to work with -fno-common, which LLVM 11 enabled.
patch -p1 <<EOF
diff --git a/src/parseopt.c b/src/parseopt.c
index a7b504f..1f6b561 100644
--- a/src/parseopt.c
+++ b/src/parseopt.c
@@ -255,8 +255,6 @@ print_option_descr (const char *descr, size_t lmargin, size_t rmargin)
 }
 
 char *parseopt_program_name;
-char *parseopt_program_doc;
-char *parseopt_program_args;
 const char *program_bug_address = "<" PACKAGE_BUGREPORT ">";
 void (*parseopt_help_hook) (FILE *stream);
 
EOF


# CPython setup.py looks for libgdbm_compat and gdbm-ndbm.h,
# which require --enable-libgdbm-compat.
CLFAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --disable-shared \
    --enable-libgdbm-compat

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
