#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH
export PKG_CONFIG_PATH=${TOOLS_PATH}/deps/share/pkgconfig:${TOOLS_PATH}/deps/lib/pkgconfig

tar -xf tcl${TCL_VERSION}-src.tar.gz
pushd tcl${TCL_VERSION}

patch -p1 << 'EOF'
diff --git a/unix/Makefile.in b/unix/Makefile.in
--- a/unix/Makefile.in
+++ b/unix/Makefile.in
@@ -1724,7 +1724,7 @@ configure-packages:
 		  $$i/configure --with-tcl=../.. \
 		      --with-tclinclude=$(GENERIC_DIR) \
 		      $(PKG_CFG_ARGS) --libdir=$(PACKAGE_DIR) \
-		      --enable-shared --enable-threads; ) || exit $$?; \
+		      --enable-shared=no --enable-threads; ) || exit $$?; \
 	      fi; \
 	    fi; \
 	  fi; \
EOF

# Remove packages we don't care about and can pull in unwanted symbols.
rm -rf pkgs/sqlite* pkgs/tdbc*

pushd unix

CFLAGS="-fPIC -I${TOOLS_PATH}/deps/include"

if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
  CFLAGS="${CFLAGS} -Wno-nullability-completeness -Wno-expansion-to-defined"
  CFLAGS="${CFLAGS} -I${MACOS_SDK_PATH}/System/Library/Frameworks -F${MACOS_SDK_PATH}/System/Library/Frameworks"
fi

CFLAGS="${CFLAGS}" CPPFLAGS="${CFLAGS}" ./configure \
    --prefix=/tools/deps \
    --enable-shared=no \
    --enable-threads

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out
make -j ${NUM_CPUS} install-private-headers DESTDIR=${ROOT}/out

# For some reason libtcl*.a have weird permissions. Fix that.
chmod 644 ${ROOT}/out/tools/deps/lib/libtcl*.a