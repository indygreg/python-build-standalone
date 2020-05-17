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
index 5f20ebe..eecc67a 100755
--- a/configure
+++ b/configure
@@ -12448,13 +12448,13 @@ test -n "$NROFF" || NROFF="/bin/false"



-{ $as_echo "$as_me:${as_lineno-$LINENO}: checking for tgetent in -lncurses" >&5
-$as_echo_n "checking for tgetent in -lncurses... " >&6; }
-if ${ac_cv_lib_ncurses_tgetent+:} false; then :
+{ $as_echo "$as_me:${as_lineno-$LINENO}: checking for tgetent in -lncursesw" >&5
+$as_echo_n "checking for tgetent in -lncursesw... " >&6; }
+if ${ac_cv_lib_ncursesw_tgetent+:} false; then :
   $as_echo_n "(cached) " >&6
 else
   ac_check_lib_save_LIBS=$LIBS
-LIBS="-lncurses  $LIBS"
+LIBS="-lncursesw  $LIBS"
 cat confdefs.h - <<_ACEOF >conftest.$ac_ext
 /* end confdefs.h.  */

@@ -12474,22 +12474,22 @@ return tgetent ();
 }
 _ACEOF
 if ac_fn_c_try_link "$LINENO"; then :
-  ac_cv_lib_ncurses_tgetent=yes
+  ac_cv_lib_ncursesw_tgetent=yes
 else
-  ac_cv_lib_ncurses_tgetent=no
+  ac_cv_lib_ncursesw_tgetent=no
 fi
 rm -f core conftest.err conftest.$ac_objext \
     conftest$ac_exeext conftest.$ac_ext
 LIBS=$ac_check_lib_save_LIBS
 fi
-{ $as_echo "$as_me:${as_lineno-$LINENO}: result: $ac_cv_lib_ncurses_tgetent" >&5
-$as_echo "$ac_cv_lib_ncurses_tgetent" >&6; }
-if test "x$ac_cv_lib_ncurses_tgetent" = xyes; then :
+{ $as_echo "$as_me:${as_lineno-$LINENO}: result: $ac_cv_lib_ncursesw_tgetent" >&5
+$as_echo "$ac_cv_lib_ncursesw_tgetent" >&6; }
+if test "x$ac_cv_lib_ncursesw_tgetent" = xyes; then :
   cat >>confdefs.h <<_ACEOF
 #define HAVE_LIBNCURSES 1
 _ACEOF

-  LIBS="-lncurses $LIBS"
+  LIBS="-lncursesw $LIBS"

 else
   { $as_echo "$as_me:${as_lineno-$LINENO}: checking for tgetent in -lcurses" >&5
@@ -12624,7 +12624,7 @@ _ACEOF
   LIBS="-ltinfo $LIBS"

 else
-  as_fn_error $? "libncurses, libcurses, libtermcap or libtinfo is required!" "$LINENO" 5
+  as_fn_error $? "libncursesw, libcurses, libtermcap or libtinfo is required!" "$LINENO" 5

 fi

EOF

cflags="${EXTRA_TARGET_CFLAGS} -fPIC -I${TOOLS_PATH}/deps/include -I${TOOLS_PATH}/deps/include/ncursesw"

# musl doesn't define __STDC_ISO_10646__, so work around that.
if [ "${CC}" = "musl-clang" ]; then
    cflags="${cflags} -D__STDC_ISO_10646__=201103L"
fi

# Install to /tools/deps/libedit so it doesn't conflict with readline's files.
CLFAGS="${cflags}" CPPFLAGS="${cflags}" LDFLAGS="-L${TOOLS_PATH}/deps/lib" \
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
