#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

cd /build

export PATH=/tools/${TOOLCHAIN}/bin:/tools/host/bin:$PATH
export PKG_CONFIG_PATH=/tools/deps/share/pkgconfig:/tools/deps/lib/pkgconfig

tar -xf libX11-${LIBX11_VERSION}.tar.gz
pushd libX11-${LIBX11_VERSION}

patch -p1 << 'EOF'
diff --git a/configure b/configure
--- a/configure
+++ b/configure
@@ -19557,8 +19557,6 @@ else
 		RAWCPPFLAGS="-undef -ansi"
 		{ $as_echo "$as_me:${as_lineno-$LINENO}: result: yes, with -ansi" >&5
 $as_echo "yes, with -ansi" >&6; }
-	else
-		as_fn_error $? "${RAWCPP} defines unix with or without -undef.  I don't know what to do." "$LINENO" 5
 	fi
 fi
 rm -f conftest.$ac_ext
@@ -19578,8 +19576,6 @@ else
 		RAWCPPFLAGS="${RAWCPPFLAGS} -traditional"
 		{ $as_echo "$as_me:${as_lineno-$LINENO}: result: yes" >&5
 $as_echo "yes" >&6; }
-	else
-		as_fn_error $? "${RAWCPP} does not preserve whitespace with or without -traditional.  I don't know what to do." "$LINENO" 5
 	fi
 fi
 rm -f conftest.$ac_ext
EOF

CFLAGS="-fPIC -I/tools/deps/include" ./configure \
    --prefix=/tools/deps

make -j `nproc`
make -j `nproc` install DESTDIR=/build/out
