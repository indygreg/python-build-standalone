#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf libffi-${LIBFFI_VERSION}.tar.gz

pushd libffi-${LIBFFI_VERSION}

# Upstream commit ce077e5565366171aa1b4438749b0922fce887a4 to resolve a missing declaration.
patch -p1 << 'EOF'
diff --git a/include/ffi_common.h b/include/ffi_common.h
index 2bd31b0..c53a794 100644
--- a/include/ffi_common.h
+++ b/include/ffi_common.h
@@ -128,6 +128,10 @@ void *ffi_data_to_code_pointer (void *data) FFI_HIDDEN;
    static trampoline. */
 int ffi_tramp_is_present (void *closure) FFI_HIDDEN;

+/* Return a file descriptor of a temporary zero-sized file in a
+   writable and executable filesystem. */
+int open_temp_exec_file(void) FFI_HIDDEN;
+
 /* Extended cif, used in callback from assembly routine */
 typedef struct
 {
diff --git a/src/tramp.c b/src/tramp.c
index 7e005b0..5f19b55 100644
--- a/src/tramp.c
+++ b/src/tramp.c
@@ -39,6 +39,10 @@
 #ifdef __linux__
 #define _GNU_SOURCE 1
 #endif
+
+#include <ffi.h>
+#include <ffi_common.h>
+
 #include <stdio.h>
 #include <unistd.h>
 #include <stdlib.h>
EOF

EXTRA_CONFIGURE=

# mkostemp() was introduced in macOS 10.10 and libffi doesn't have
# runtime guards for it. So ban the symbol when targeting old macOS.
if [ "${APPLE_MIN_DEPLOYMENT_TARGET}" = "10.9" ]; then
    EXTRA_CONFIGURE="${EXTRA_CONFIGURE} ac_cv_func_mkostemp=no"
fi

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" LDFLAGS="${EXTRA_TARGET_LDFLAGS}" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --disable-shared \
    ${EXTRA_CONFIGURE}

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
