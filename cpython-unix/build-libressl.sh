#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

cd /build

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH

tar -xf libressl-${LIBRESSL_VERSION}.tar.gz

pushd libressl-${LIBRESSL_VERSION}

# Backport of https://github.com/libressl-portable/portable/pull/529 for MUSL support.
patch -p1 << EOF
diff --git a/crypto/compat/getprogname_linux.c b/crypto/compat/getprogname_linux.c
index 2c89743..4e7e31f 100644
--- a/crypto/compat/getprogname_linux.c
+++ b/crypto/compat/getprogname_linux.c
@@ -26,9 +26,7 @@ getprogname(void)
 #if defined(__ANDROID_API__) && __ANDROID_API__ < 21
 	extern const char *__progname;
 	return __progname;
-#elif defined(__GLIBC__)
-	return program_invocation_short_name;
 #else
-#error "Cannot emulate getprogname"
+	return program_invocation_short_name;
 #endif
 }
EOF

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" CPPFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --with-openssldir=/etc/ssl \
    --disable-shared

make -j `nproc`
make -j `nproc` install DESTDIR=/build/out
