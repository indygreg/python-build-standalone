#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:$PATH

tar -xf libedit-${LIBEDIT_VERSION}.tar.gz

pushd libedit-${LIBEDIT_VERSION}

# libedit's configure isn't smart enough to look for ncursesw. So we teach it
# to. Ideally we would edit configure.ac and run autoconf. But Jessie's autoconf
# is older than what generated libedit's and the tools complain about this at
# run-time. So we hack up the configure script instead.
patch -p1 << "EOF"
diff --git a/configure b/configure
index 26dd8d0..4b6d47c 100755
--- a/configure
+++ b/configure
@@ -12921,14 +12921,14 @@ test -n "$NROFF" || NROFF="/bin/false"
 
 
 
-{ printf "%s\n" "$as_me:${as_lineno-$LINENO}: checking for tgetent in -lncurses" >&5
-printf %s "checking for tgetent in -lncurses... " >&6; }
-if test ${ac_cv_lib_ncurses_tgetent+y}
+{ printf "%s\n" "$as_me:${as_lineno-$LINENO}: checking for tgetent in -lncursesw" >&5
+printf %s "checking for tgetent in -lncursesw... " >&6; }
+if test ${ac_cv_lib_ncursesw_tgetent+y}
 then :
   printf %s "(cached) " >&6
 else $as_nop
   ac_check_lib_save_LIBS=$LIBS
-LIBS="-lncurses  $LIBS"
+LIBS="-lncursesw  $LIBS"
 cat confdefs.h - <<_ACEOF >conftest.$ac_ext
 /* end confdefs.h.  */
 
@@ -12946,21 +12946,21 @@ return tgetent ();
 _ACEOF
 if ac_fn_c_try_link "$LINENO"
 then :
-  ac_cv_lib_ncurses_tgetent=yes
+  ac_cv_lib_ncursesw_tgetent=yes
 else $as_nop
-  ac_cv_lib_ncurses_tgetent=no
+  ac_cv_lib_ncursesw_tgetent=no
 fi
 rm -f core conftest.err conftest.$ac_objext conftest.beam \
     conftest$ac_exeext conftest.$ac_ext
 LIBS=$ac_check_lib_save_LIBS
 fi
-{ printf "%s\n" "$as_me:${as_lineno-$LINENO}: result: $ac_cv_lib_ncurses_tgetent" >&5
-printf "%s\n" "$ac_cv_lib_ncurses_tgetent" >&6; }
-if test "x$ac_cv_lib_ncurses_tgetent" = xyes
+{ printf "%s\n" "$as_me:${as_lineno-$LINENO}: result: $ac_cv_lib_ncursesw_tgetent" >&5
+printf "%s\n" "$ac_cv_lib_ncursesw_tgetent" >&6; }
+if test "x$ac_cv_lib_ncursesw_tgetent" = xyes
 then :
   printf "%s\n" "#define HAVE_LIBNCURSES 1" >>confdefs.h
 
-  LIBS="-lncurses $LIBS"
+  LIBS="-lncursesw $LIBS"
 
 else $as_nop
   { printf "%s\n" "$as_me:${as_lineno-$LINENO}: checking for tgetent in -lcurses" >&5
@@ -13089,7 +13089,7 @@ then :
   LIBS="-ltinfo $LIBS"
 
 else $as_nop
-  as_fn_error $? "libncurses, libcurses, libtermcap or libtinfo is required!" "$LINENO" 5
+  as_fn_error $? "libncursesw, libcurses, libtermcap or libtinfo is required!" "$LINENO" 5
 
 fi
 
EOF

cflags="${EXTRA_TARGET_CFLAGS} -fPIC -I${TOOLS_PATH}/deps/include -I${TOOLS_PATH}/deps/include/ncursesw"
ldflags="${EXTRA_TARGET_LDFLAGS} -L${TOOLS_PATH}/deps/lib"

# musl doesn't define __STDC_ISO_10646__, so work around that.
if [ "${CC}" = "musl-clang" ]; then
    cflags="${cflags} -D__STDC_ISO_10646__=201103L"
fi

# Install to /tools/deps/libedit so it doesn't conflict with readline's files.
CFLAGS="${cflags}" CPPFLAGS="${cflags}" LDFLAGS="${ldflags}" \
    ./configure \
        --build=${BUILD_TRIPLE} \
        --host=${TARGET_TRIPLE} \
        --prefix=/tools/deps/libedit \
        --disable-shared

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out

# Alias readline/{history.h, readline.h} for readline compatibility.
if [ -e ${ROOT}/out/tools/deps/libedit/include ]; then
    mkdir ${ROOT}/out/tools/deps/libedit/include/readline
    ln -s ../editline/readline.h ${ROOT}/out/tools/deps/libedit/include/readline/readline.h
    ln -s ../editline/readline.h ${ROOT}/out/tools/deps/libedit/include/readline/history.h
fi
