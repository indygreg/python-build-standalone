#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf ncurses-${NCURSES_VERSION}.tar.gz

pushd ncurses-${NCURSES_VERSION}

patch -p1 << 'EOF'
diff --git a/configure b/configure
--- a/configure
+++ b/configure
@@ -15350,7 +15350,7 @@ echo "${ECHO_T}$with_stripping" >&6
 
 if test "$with_stripping" = yes
 then
-	INSTALL_OPT_S="-s"
+	INSTALL_OPT_S="-s --strip-program=${STRIP}"
 else
 	INSTALL_OPT_S=
 fi
EOF

CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC" ./configure \
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE} \
    --prefix=/tools/deps \
    --without-cxx \
    --enable-widec \
    --disable-db-install
make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
