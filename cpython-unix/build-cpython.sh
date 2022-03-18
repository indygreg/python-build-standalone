#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

export ROOT=`pwd`

export PATH=${TOOLS_PATH}/${TOOLCHAIN}/bin:${TOOLS_PATH}/host/bin:${TOOLS_PATH}/deps/bin:$PATH

# configure somehow has problems locating llvm-profdata even though it is in
# PATH. The macro it is using allows us to specify its path via an
# environment variable.
export LLVM_PROFDATA=${TOOLS_PATH}/${TOOLCHAIN}/bin/llvm-profdata

# We force linking of external static libraries by removing the shared
# libraries. This is hacky. But we're building in a temporary container
# and it gets the job done.
find ${TOOLS_PATH}/deps -name '*.so*' -exec rm {} \;

tar -xf Python-${PYTHON_VERSION}.tar.xz

PIP_WHEEL="${ROOT}/pip-${PIP_VERSION}-py3-none-any.whl"
SETUPTOOLS_WHEEL="${ROOT}/setuptools-${SETUPTOOLS_VERSION}-py3-none-any.whl"

# pip and setuptools don't properly handle the case where the current executable
# isn't dynamic. This is tracked by https://github.com/pypa/pip/issues/6543.
# We need to patch both.
#
# Ideally we'd do this later in the build. However, since we use the pip
# wheel to bootstrap itself, we need to patch the wheel before it is used.
#
# Wheels are zip files. So we simply unzip, patch, and rezip.
mkdir pip-tmp
pushd pip-tmp
unzip "${PIP_WHEEL}"
rm -f "${PIP_WHEEL}"

patch -p1 <<EOF
diff --git a/pip/_internal/utils/glibc.py b/pip/_internal/utils/glibc.py
index 819979d80..4ae91e364 100644
--- a/pip/_internal/utils/glibc.py
+++ b/pip/_internal/utils/glibc.py
@@ -47,7 +47,10 @@ def glibc_version_string_ctypes():
     # manpage says, "If filename is NULL, then the returned handle is for the
     # main program". This way we can let the linker do the work to figure out
     # which libc our process is actually using.
-    process_namespace = ctypes.CDLL(None)
+    try:
+        process_namespace = ctypes.CDLL(None)
+    except OSError:
+        return None
     try:
         gnu_get_libc_version = process_namespace.gnu_get_libc_version
     except AttributeError:
EOF

zip -r "${PIP_WHEEL}" *
popd
rm -rf pip-tmp

# If we are cross-compiling, we need to build a host Python to use during
# the build.
if [ -n "${CROSS_COMPILING}" ]; then
  pushd "Python-${PYTHON_VERSION}"

  # Same patch as below. See comment there.
  if [ "${CC}" = "clang" ]; then
    if [ "${PYTHON_MAJMIN_VERSION}" != "3.8" ]; then
      patch -p1 <<"EOF"
diff --git a/configure b/configure
index d078887b2f..78654eed29 100755
--- a/configure
+++ b/configure
@@ -5366,20 +5366,7 @@ $as_echo "none" >&6; }
 fi
 rm -f conftest.c conftest.out

-{ $as_echo "$as_me:${as_lineno-$LINENO}: checking for multiarch" >&5
-$as_echo_n "checking for multiarch... " >&6; }
-case $ac_sys_system in #(
-  Darwin*) :
-    MULTIARCH="" ;; #(
-  FreeBSD*) :
-    MULTIARCH="" ;; #(
-  *) :
-    MULTIARCH=$($CC --print-multiarch 2>/dev/null)
- ;;
-esac
-
-{ $as_echo "$as_me:${as_lineno-$LINENO}: result: $MULTIARCH" >&5
-$as_echo "$MULTIARCH" >&6; }
+MULTIARCH=

 if test x$PLATFORM_TRIPLET != x && test x$MULTIARCH != x; then
   if test x$PLATFORM_TRIPLET != x$MULTIARCH; then

EOF
    else
      patch -p1 <<"EOF"
diff --git a/configure b/configure
index c091865aff..0aeea8cedb 100755
--- a/configure
+++ b/configure
@@ -5318,10 +5318,7 @@ $as_echo "none" >&6; }
 fi
 rm -f conftest.c conftest.out

-if test x$PLATFORM_TRIPLET != xdarwin; then
-  MULTIARCH=$($CC --print-multiarch 2>/dev/null)
-fi
-
+MULTIARCH=

 if test x$PLATFORM_TRIPLET != x && test x$MULTIARCH != x; then
   if test x$PLATFORM_TRIPLET != x$MULTIARCH; then
EOF
    fi
  fi

  # When cross-compiling, we need to build a host Python that has working zlib
  # and ctypes extensions, otherwise various things fail. (`make install` fails
  # without zlib and setuptools / pip used by target install fail due to missing
  # ctypes.)
  #
  # On Apple, the dependencies are present in the Apple SDK and missing extensions
  # are built properly by setup.py. However, on other platforms, we need to teach
  # the host build system where to find things.
  #
  # Adding /usr paths on Linux is a bit funky. This is a side-effect or our
  # custom Clang purposefully omitting default system search paths to help
  # prevent unwanted dependencies from sneaking in.
  case "${BUILD_TRIPLE}" in
    x86_64-unknown-linux-gnu)
      EXTRA_HOST_CFLAGS="${EXTRA_HOST_CFLAGS} -I/usr/include/x86_64-linux-gnu"
      EXTRA_HOST_CPPFLAGS="${EXTRA_HOST_CPPFLAGS} -I/usr/include/x86_64-linux-gnu"
      EXTRA_HOST_LDFLAGS="${EXTRA_HOST_LDFLAGS} -L/usr/lib/x86_64-linux-gnu"
      ;;
    *)
      ;;
  esac

  CC="${HOST_CC}" CXX="${HOST_CXX}" CFLAGS="${EXTRA_HOST_CFLAGS}" CPPFLAGS="${EXTRA_HOST_CFLAGS}" LDFLAGS="${EXTRA_HOST_LDFLAGS}" ./configure \
    --prefix "${TOOLS_PATH}/pyhost" \
    --without-ensurepip

  make -j "${NUM_CPUS}" install

  # configure will look for a pythonX.Y executable. Install our host Python
  # at the front of PATH.
  export PATH="${TOOLS_PATH}/pyhost/bin:${PATH}"

  popd
  # Nuke and re-pave the source directory out of paranoia.
  rm -rf "Python-${PYTHON_VERSION}"
  tar -xf "Python-${PYTHON_VERSION}.tar.xz"
fi

cat Setup.local
mv Setup.local Python-${PYTHON_VERSION}/Modules/Setup.local

cat Makefile.extra

pushd Python-${PYTHON_VERSION}

# configure assumes cross compiling when host != target and doesn't provide a way to
# override. Our target triple normalization may lead configure into thinking we
# aren't cross-compiling when we are. So force a static "yes" value when our
# build system says we are cross-compiling.
if [ -n "${CROSS_COMPILING}" ]; then
  patch -p1 <<"EOF"
diff --git a/configure b/configure
index d078887b2f..8f1ea07cd8 100755
--- a/configure
+++ b/configure
@@ -1329,14 +1329,7 @@ build=$build_alias
 host=$host_alias
 target=$target_alias

-# FIXME: To remove some day.
-if test "x$host_alias" != x; then
-  if test "x$build_alias" = x; then
-    cross_compiling=maybe
-  elif test "x$build_alias" != "x$host_alias"; then
-    cross_compiling=yes
-  fi
-fi
+cross_compiling=yes

 ac_tool_prefix=
 test -n "$host_alias" && ac_tool_prefix=$host_alias-
EOF
fi

# configure doesn't support cross-compiling on Apple. Teach it.
patch -p1 << "EOF"
diff --git a/configure b/configure
index 1252335472..6665645839 100755
--- a/configure
+++ b/configure
@@ -3301,6 +3301,15 @@ then
 	*-*-cygwin*)
 		ac_sys_system=Cygwin
 		;;
+	*-apple-ios*)
+		ac_sys_system=iOS
+		;;
+	*-apple-tvos*)
+		ac_sys_system=tvOS
+		;;
+	*-apple-watchos*)
+		ac_sys_system=watchOS
+		;;
 	*-*-vxworks*)
 	    ac_sys_system=VxWorks
 	    ;;
@@ -3351,6 +3360,19 @@ if test "$cross_compiling" = yes; then
 	*-*-cygwin*)
 		_host_cpu=
 		;;
+	*-*-darwin*)
+		_host_cpu=
+		;;
+	*-apple-*)
+	  case "$host_cpu" in
+	  arm*)
+	    _host_cpu=arm
+	    ;;
+	  *)
+	    _host_cpu=$host_cpu
+	    ;;
+	  esac
+	  ;;
 	*-*-vxworks*)
 		_host_cpu=$host_cpu
 		;;
@@ -3359,7 +3381,22 @@ if test "$cross_compiling" = yes; then
 		MACHDEP="unknown"
 		as_fn_error $? "cross build not supported for $host" "$LINENO" 5
 	esac
-	_PYTHON_HOST_PLATFORM="$MACHDEP${_host_cpu:+-$_host_cpu}"
+
+	case "$host" in
+	  # The _PYTHON_HOST_PLATFORM environment variable is used to
+	  # override the platform name in distutils and sysconfig when
+	  # cross-compiling. On Apple, the platform name expansion logic
+	  # is non-trivial, including renaming MACHDEP=darwin to macosx
+	  # and including the deployment target (or current OS version if
+	  # not set). Our hack here is not generic, but gets the job done
+	  # for python-build-standalone's cross-compile use cases.
+	  aarch64-apple-darwin*)
+	    _PYTHON_HOST_PLATFORM="macosx-${MACOSX_DEPLOYMENT_TARGET}-arm64"
+	    ;;
+	  *)
+	    _PYTHON_HOST_PLATFORM="$MACHDEP${_host_cpu:+-$_host_cpu}"
+	esac
+
 fi
 
 # Some systems cannot stand _XOPEN_SOURCE being defined at all; they
@@ -5968,7 +6005,7 @@ $as_echo "#define Py_ENABLE_SHARED 1" >>confdefs.h
 	  BLDLIBRARY='-Wl,+b,$(LIBDIR) -L. -lpython$(LDVERSION)'
 	  RUNSHARED=SHLIB_PATH=`pwd`${SHLIB_PATH:+:${SHLIB_PATH}}
 	  ;;
-    Darwin*)
+    Darwin*|iOS*|tvOS*|watchOS*)
     	LDLIBRARY='libpython$(LDVERSION).dylib'
 	BLDLIBRARY='-L. -lpython$(LDVERSION)'
 	RUNSHARED=DYLD_LIBRARY_PATH=`pwd`${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}
@@ -6205,16 +6242,6 @@ esac
   fi
 fi
 
-if test "$cross_compiling" = yes; then
-    case "$READELF" in
-	readelf|:)
-	as_fn_error $? "readelf for the host is required for cross builds" "$LINENO" 5
-	;;
-    esac
-fi
-
-
-
 case $MACHDEP in
 hp*|HP*)
 	# install -d does not work on HP-UX
@@ -9541,6 +9568,11 @@ then
 			BLDSHARED="$LDSHARED"
 		fi
 		;;
+  iOS*|tvOS*|watchOS*)
+    LDSHARED='$(CC) -bundle -undefined dynamic_lookup'
+    LDCXXSHARED='$(CXX) -bundle -undefined dynamic_lookup'
+    BLDSHARED="$LDSHARED"
+    ;;
 	Linux*|GNU*|QNX*|VxWorks*)
 		LDSHARED='$(CC) -shared'
 		LDCXXSHARED='$(CXX) -shared';;
EOF

# This patch is slightly different on Python 3.10+.
if [ "${PYTHON_MAJMIN_VERSION}" = "3.10" ]; then
    patch -p1 << "EOF"
diff --git a/configure b/configure
index 2d379feb4b..3eb8dbe9ea 100755
--- a/configure
+++ b/configure
@@ -3426,6 +3448,12 @@ $as_echo "#define _BSD_SOURCE 1" >>confdefs.h
     define_xopen_source=no;;
   Darwin/[12][0-9].*)
     define_xopen_source=no;;
+  iOS/*)
+    define_xopen_source=no;;
+  tvOS/*)
+    define_xopen_source=no;;
+  watchOS/*)
+    define_xopen_source=no;;
   # On QNX 6.3.2, defining _XOPEN_SOURCE prevents netdb.h from
   # defining NI_NUMERICHOST.
   QNX/6.3.2)
EOF
else
    patch -p1 << "EOF"
diff --git a/configure b/configure
index 2d379feb4b..3eb8dbe9ea 100755
--- a/configure
+++ b/configure
@@ -3426,6 +3448,12 @@ $as_echo "#define _BSD_SOURCE 1" >>confdefs.h
     define_xopen_source=no;;
   Darwin/[12][0-9].*)
     define_xopen_source=no;;
+  iOS/*)
+    define_xopen_source=no;;
+  tvOS/*)
+    define_xopen_source=no;;
+  watchOS/*)
+    define_xopen_source=no;;
   # On AIX 4 and 5.1, mbstate_t is defined only when _XOPEN_SOURCE == 500 but
   # used in wcsnrtombs() and mbsnrtowcs() even if _XOPEN_SOURCE is not defined
   # or has another value. By not (re)defining it, the defaults come in place.
EOF
fi

# Configure nerfs RUNSHARED when cross-compiling, which prevents PGO from running when
# we can in fact run the target binaries (e.g. x86_64 host and i686 target). Undo that.
if [ -n "${CROSS_COMPILING}" ]; then
    patch -p1 << "EOF"
diff --git a/configure b/configure
index 1252335472..33c11fbade 100755
--- a/configure
+++ b/configure
@@ -5989,10 +5989,6 @@ else # shared is disabled
   esac
 fi
 
-if test "$cross_compiling" = yes; then
-	RUNSHARED=
-fi
-
 { $as_echo "$as_me:${as_lineno-$LINENO}: result: $LDLIBRARY" >&5
 $as_echo "$LDLIBRARY" >&6; }
 
EOF
fi

# Clang 13 actually prints something with --print-multiarch, confusing CPython's
# configure. This is reported as https://bugs.python.org/issue45405. We nerf the
# check since we know what we're doing.
if [ "${CC}" = "clang" ]; then
    if [ "${PYTHON_MAJMIN_VERSION}" != "3.8" ]; then
        patch -p1 <<"EOF"
diff --git a/configure b/configure
index d078887b2f..78654eed29 100755
--- a/configure
+++ b/configure
@@ -5366,20 +5366,7 @@ $as_echo "none" >&6; }
 fi
 rm -f conftest.c conftest.out

-{ $as_echo "$as_me:${as_lineno-$LINENO}: checking for multiarch" >&5
-$as_echo_n "checking for multiarch... " >&6; }
-case $ac_sys_system in #(
-  Darwin*) :
-    MULTIARCH="" ;; #(
-  FreeBSD*) :
-    MULTIARCH="" ;; #(
-  *) :
-    MULTIARCH=$($CC --print-multiarch 2>/dev/null)
- ;;
-esac
-
-{ $as_echo "$as_me:${as_lineno-$LINENO}: result: $MULTIARCH" >&5
-$as_echo "$MULTIARCH" >&6; }
+MULTIARCH=

 if test x$PLATFORM_TRIPLET != x && test x$MULTIARCH != x; then
   if test x$PLATFORM_TRIPLET != x$MULTIARCH; then

EOF
    else
        patch -p1 <<"EOF"
diff --git a/configure b/configure
index c091865aff..0aeea8cedb 100755
--- a/configure
+++ b/configure
@@ -5318,10 +5318,7 @@ $as_echo "none" >&6; }
 fi
 rm -f conftest.c conftest.out

-if test x$PLATFORM_TRIPLET != xdarwin; then
-  MULTIARCH=$($CC --print-multiarch 2>/dev/null)
-fi
-
+MULTIARCH=

 if test x$PLATFORM_TRIPLET != x && test x$MULTIARCH != x; then
   if test x$PLATFORM_TRIPLET != x$MULTIARCH; then
EOF
    fi
fi

# Add a make target to write the PYTHON_FOR_BUILD variable so we can
# invoke the host Python on our own.
patch -p1 << "EOF"
diff --git a/Makefile.pre.in b/Makefile.pre.in
index f128444b98..d2013a2987 100644
--- a/Makefile.pre.in
+++ b/Makefile.pre.in
@@ -1930,6 +1930,12 @@ patchcheck: @DEF_MAKE_RULE@
 
 Python/thread.o: @THREADHEADERS@ $(srcdir)/Python/condvar.h
 
+write-python-for-build:
+	echo "#!/bin/sh" > python-for-build
+	echo "set -e" >> python-for-build
+	echo "exec env $(PYTHON_FOR_BUILD) \$$@" >> python-for-build
+	chmod +x python-for-build
+
 # Declare targets that aren't real files
 .PHONY: all build_all sharedmods check-clean-src oldsharedmods test quicktest
 .PHONY: install altinstall oldsharedinstall bininstall altbininstall
EOF

# We build all extensions statically. So remove the auto-generated make
# rules that produce shared libraries for them.
patch -p1 << "EOF"
diff --git a/Modules/makesetup b/Modules/makesetup
--- a/Modules/makesetup
+++ b/Modules/makesetup
@@ -241,18 +241,11 @@ sed -e 's/[ 	]*#.*//' -e '/^[ 	]*$/d' |
 		case $doconfig in
 		yes)	OBJS="$OBJS $objs";;
 		esac
-		for mod in $mods
-		do
-			file="$srcdir/$mod\$(EXT_SUFFIX)"
-			case $doconfig in
-			no)	SHAREDMODS="$SHAREDMODS $file";;
-			esac
-			rule="$file: $objs"
-			rule="$rule; \$(BLDSHARED) $objs $libs $ExtraLibs -o $file"
-			echo "$rule" >>$rulesf
-		done
 	done
 
+	# Deduplicate OBJS.
+	OBJS=$(echo $OBJS | tr ' ' '\n' | sort -u | xargs)
+
 	case $SHAREDMODS in
 	'')	;;
 	*)	DEFS="SHAREDMODS=$SHAREDMODS$NL$DEFS";;
EOF

# The default build rule for the macOS dylib doesn't pick up libraries
# from modules / makesetup. So patch it accordingly.
patch -p1 << "EOF"
diff --git a/Makefile.pre.in b/Makefile.pre.in
--- a/Makefile.pre.in
+++ b/Makefile.pre.in
@@ -628,7 +628,7 @@ libpython3.so:	libpython$(LDVERSION).so
 	$(BLDSHARED) $(NO_AS_NEEDED) -o $@ -Wl,-h$@ $^
 
 libpython$(LDVERSION).dylib: $(LIBRARY_OBJS)
-	 $(CC) -dynamiclib -Wl,-single_module $(PY_CORE_LDFLAGS) -undefined dynamic_lookup -Wl,-install_name,$(prefix)/lib/libpython$(LDVERSION).dylib -Wl,-compatibility_version,$(VERSION) -Wl,-current_version,$(VERSION) -o $@ $(LIBRARY_OBJS) $(DTRACE_OBJS) $(SHLIBS) $(LIBC) $(LIBM); \
+	 $(CC) -dynamiclib -Wl,-single_module $(PY_CORE_LDFLAGS) -undefined dynamic_lookup -Wl,-install_name,$(prefix)/lib/libpython$(LDVERSION).dylib -Wl,-compatibility_version,$(VERSION) -Wl,-current_version,$(VERSION) -o $@ $(LIBRARY_OBJS) $(DTRACE_OBJS) $(MODLIBS) $(SHLIBS) $(LIBC) $(LIBM); \
 
 
 libpython$(VERSION).sl: $(LIBRARY_OBJS)
EOF

# Also on macOS, the `python` executable is linked against libraries defined by statically
# linked modules. But those libraries should only get linked into libpython, not the
# executable. This behavior is kinda suspect on all platforms, as it could be adding
# library dependencies that shouldn't need to be there.
if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
    if [ "${PYTHON_MAJMIN_VERSION}" = "3.8" ]; then
        patch -p1 <<"EOF"
diff --git a/Makefile.pre.in b/Makefile.pre.in
--- a/Makefile.pre.in
+++ b/Makefile.pre.in
@@ -563,7 +563,7 @@ clinic: check-clean-src $(srcdir)/Modules/_blake2/blake2s_impl.c
 
 # Build the interpreter
 $(BUILDPYTHON):	Programs/python.o $(LIBRARY) $(LDLIBRARY) $(PY3LIBRARY)
-	$(LINKCC) $(PY_CORE_LDFLAGS) $(LINKFORSHARED) -o $@ Programs/python.o $(BLDLIBRARY) $(LIBS) $(MODLIBS) $(SYSLIBS)
+	$(LINKCC) $(PY_CORE_LDFLAGS) $(LINKFORSHARED) -o $@ Programs/python.o $(BLDLIBRARY) $(LIBS) $(SYSLIBS)
 
 platform: $(BUILDPYTHON) pybuilddir.txt
 	$(RUNSHARED) $(PYTHON_FOR_BUILD) -c 'import sys ; from sysconfig import get_platform ; print("%s-%d.%d" % (get_platform(), *sys.version_info[:2]))' >platform
EOF
    elif [ "${PYTHON_MAJMIN_VERSION}" = "3.9" ]; then
        patch -p1 <<"EOF"
diff --git a/Makefile.pre.in b/Makefile.pre.in
--- a/Makefile.pre.in
+++ b/Makefile.pre.in
@@ -563,7 +563,7 @@ clinic: check-clean-src $(srcdir)/Modules/_blake2/blake2s_impl.c

 # Build the interpreter
 $(BUILDPYTHON):	Programs/python.o $(LIBRARY) $(LDLIBRARY) $(PY3LIBRARY) $(EXPORTSYMS)
-	$(LINKCC) $(PY_CORE_LDFLAGS) $(LINKFORSHARED) -o $@ Programs/python.o $(BLDLIBRARY) $(LIBS) $(MODLIBS) $(SYSLIBS)
+	$(LINKCC) $(PY_CORE_LDFLAGS) $(LINKFORSHARED) -o $@ Programs/python.o $(BLDLIBRARY) $(LIBS) $(SYSLIBS)

 platform: $(BUILDPYTHON) pybuilddir.txt
 	$(RUNSHARED) $(PYTHON_FOR_BUILD) -c 'import sys ; from sysconfig import get_platform ; print("%s-%d.%d" % (get_platform(), *sys.version_info[:2]))' >platform
EOF
    else
        patch -p1 <<"EOF"
diff --git a/Makefile.pre.in b/Makefile.pre.in
--- a/Makefile.pre.in
+++ b/Makefile.pre.in
@@ -563,7 +563,7 @@ clinic: check-clean-src $(srcdir)/Modules/_blake2/blake2s_impl.c

 # Build the interpreter
 $(BUILDPYTHON):	Programs/python.o $(LIBRARY_DEPS)
-	$(LINKCC) $(PY_CORE_LDFLAGS) $(LINKFORSHARED) -o $@ Programs/python.o $(BLDLIBRARY) $(LIBS) $(MODLIBS) $(SYSLIBS)
+	$(LINKCC) $(PY_CORE_LDFLAGS) $(LINKFORSHARED) -o $@ Programs/python.o $(BLDLIBRARY) $(LIBS) $(SYSLIBS)

 platform: $(BUILDPYTHON) pybuilddir.txt
 	$(RUNSHARED) $(PYTHON_FOR_BUILD) -c 'import sys ; from sysconfig import get_platform ; print("%s-%d.%d" % (get_platform(), *sys.version_info[:2]))' >platform
EOF
    fi
fi

# The macOS code for sniffing for _dyld_shared_cache_contains_path is a bit buggy
# and doesn't support all our building scenarios. We replace it with something
# more reasonable. This patch likely isn't generally appropriate. But since we
# guarantee we're building with a 11.0+ SDK, it should be safe.
patch -p1 << "EOF"
diff --git a/Modules/_ctypes/callproc.c b/Modules/_ctypes/callproc.c
index b0f1e0bd04..80e81fe65c 100644
--- a/Modules/_ctypes/callproc.c
+++ b/Modules/_ctypes/callproc.c
@@ -1450,29 +1450,8 @@ copy_com_pointer(PyObject *self, PyObject *args)
 }
 #else
 #ifdef __APPLE__
-#ifdef HAVE_DYLD_SHARED_CACHE_CONTAINS_PATH
 #define HAVE_DYLD_SHARED_CACHE_CONTAINS_PATH_RUNTIME \
     __builtin_available(macOS 11.0, iOS 14.0, tvOS 14.0, watchOS 7.0, *)
-#else
-// Support the deprecated case of compiling on an older macOS version
-static void *libsystem_b_handle;
-static bool (*_dyld_shared_cache_contains_path)(const char *path);
-
-__attribute__((constructor)) void load_dyld_shared_cache_contains_path(void) {
-    libsystem_b_handle = dlopen("/usr/lib/libSystem.B.dylib", RTLD_LAZY);
-    if (libsystem_b_handle != NULL) {
-        _dyld_shared_cache_contains_path = dlsym(libsystem_b_handle, "_dyld_shared_cache_contains_path");
-    }
-}
-
-__attribute__((destructor)) void unload_dyld_shared_cache_contains_path(void) {
-    if (libsystem_b_handle != NULL) {
-        dlclose(libsystem_b_handle);
-    }
-}
-#define HAVE_DYLD_SHARED_CACHE_CONTAINS_PATH_RUNTIME \
-    _dyld_shared_cache_contains_path != NULL
-#endif

 static PyObject *py_dyld_shared_cache_contains_path(PyObject *self, PyObject *args)
 {
EOF

# Code that runs at ctypes module import time does not work with
# non-dynamic binaries. Patch Python to work around this.
# See https://bugs.python.org/issue37060.
patch -p1 << EOF
diff --git a/Lib/ctypes/__init__.py b/Lib/ctypes/__init__.py
--- a/Lib/ctypes/__init__.py
+++ b/Lib/ctypes/__init__.py
@@ -441,7 +441,10 @@ if _os.name == "nt":
 elif _sys.platform == "cygwin":
     pythonapi = PyDLL("libpython%d.%d.dll" % _sys.version_info[:2])
 else:
-    pythonapi = PyDLL(None)
+    try:
+        pythonapi = PyDLL(None)
+    except OSError:
+        pythonapi = None


 if _os.name == "nt":
EOF

# CPython 3.10 added proper support for building against libedit outside of
# macOS. On older versions, we need to patch readline.c and distribute
# multiple extension module variants.
#
# USE_LIBEDIT comes from our static-modules file.
if [[ "${PYTHON_MAJMIN_VERSION}" = "3.8" || "${PYTHON_MAJMIN_VERSION}" = "3.9" ]]; then
    cp Modules/readline.c Modules/readline-libedit.c

    # readline.c assumes that a modern readline API version has a free_history_entry().
    # but libedit does not. Change the #ifdef accordingly.
    #
    # Similarly, we invoke configure using readline, which sets
    # HAVE_RL_COMPLETION_SUPPRESS_APPEND improperly. So hack that. This is a bug
    # in our build system, as we should probably be invoking configure again when
    # using libedit.
    patch -p1 << EOF
diff --git a/Modules/readline-libedit.c b/Modules/readline-libedit.c
index 1e74f997b0..56a36e26e6 100644
--- a/Modules/readline-libedit.c
+++ b/Modules/readline-libedit.c
@@ -511,7 +511,7 @@ set the word delimiters for completion");
 
 /* _py_free_history_entry: Utility function to free a history entry. */
 
-#if defined(RL_READLINE_VERSION) && RL_READLINE_VERSION >= 0x0500
+#ifndef USE_LIBEDIT
 
 /* Readline version >= 5.0 introduced a timestamp field into the history entry
    structure; this needs to be freed to avoid a memory leak.  This version of
@@ -1055,7 +1055,7 @@ flex_complete(const char *text, int start, int end)
 #ifdef HAVE_RL_COMPLETION_APPEND_CHARACTER
     rl_completion_append_character ='\0';
 #endif
-#ifdef HAVE_RL_COMPLETION_SUPPRESS_APPEND
+#ifndef USE_LIBEDIT
     rl_completion_suppress_append = 0;
 #endif
 
@@ -1241,7 +1241,7 @@ readline_until_enter_or_signal(const char *prompt, int *signal)
             PyEval_SaveThread();
             if (s < 0) {
                 rl_free_line_state();
-#if defined(RL_READLINE_VERSION) && RL_READLINE_VERSION >= 0x0700
+#ifndef USE_LIBEDIT
                 rl_callback_sigcleanup();
 #endif
                 rl_cleanup_after_signal();
EOF
fi

# iOS doesn't have system(). Teach posixmodule.c about that.
if [ "${PYTHON_MAJMIN_VERSION}" != "3.8" ]; then
    patch -p1 <<EOF
diff --git a/Modules/posixmodule.c b/Modules/posixmodule.c
index 12f72f525f..4503c5fc60 100644
--- a/Modules/posixmodule.c
+++ b/Modules/posixmodule.c
@@ -326,6 +326,13 @@ corresponding Unix manual entries for more information on calls.");
 #  endif  /* _MSC_VER */
 #endif  /* ! __WATCOMC__ || __QNX__ */

+#if __APPLE__
+#include <TargetConditionals.h>
+#if TARGET_OS_IPHONE
+#    undef HAVE_SYSTEM
+#endif
+#endif
+
 _Py_IDENTIFIER(__fspath__);

 /*[clinic input]
EOF
fi

# Most bits look at CFLAGS. But setup.py only looks at CPPFLAGS.
# So we need to set both.
CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC -I${TOOLS_PATH}/deps/include -I${TOOLS_PATH}/deps/include/ncursesw"
LDFLAGS="${EXTRA_TARGET_LDFLAGS} -L${TOOLS_PATH}/deps/lib"
EXTRA_CONFIGURE_FLAGS=

if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
    CFLAGS="${CFLAGS} -I${TOOLS_PATH}/deps/include/uuid"

    # Prevent using symbols not supported by current macOS SDK target.
    CFLAGS="${CFLAGS} -Werror=unguarded-availability-new"
fi

# CPython 3.10 introduced proper support for libedit on all platforms. Link against
# libedit by default because it isn't GPL.
#
# Ideally we wouldn't need to adjust global compiler and linker flags. But configure
# performs detection of readline features and sets some preprocessor defines accordingly.
# So we define these accordingly.
if [[ "${PYBUILD_PLATFORM}" != "macos" && "${PYTHON_MAJMIN_VERSION}" != "3.8" && "${PYTHON_MAJMIN_VERSION}" != "3.9" ]]; then
    CFLAGS="${CFLAGS} -I${TOOLS_PATH}/deps/libedit/include"
    LDFLAGS="${LDFLAGS} -L${TOOLS_PATH}/deps/libedit/lib"
    EXTRA_CONFIGURE_FLAGS="${EXTRA_CONFIGURE_FLAGS} --with-readline=editline"
fi

CPPFLAGS=$CFLAGS

CONFIGURE_FLAGS="
    --build=${BUILD_TRIPLE}
    --host=${TARGET_TRIPLE}
    --prefix=/install
    --with-openssl=${TOOLS_PATH}/deps
    --without-ensurepip
    ${EXTRA_CONFIGURE_FLAGS}"

if [ "${CC}" = "musl-clang" ]; then
    CFLAGS="${CFLAGS} -static"
    CPPFLAGS="${CPPFLAGS} -static"
    LDFLAGS="${LDFLAGS} -static"
    PYBUILD_SHARED=0

    # In order to build the _blake2 extension module with SSE3+ instructions, we need
    # musl-clang to find headers that provide access to the intrinsics, as they are not
    # provided by musl. These are part of the include files that are part of clang.
    # But musl-clang eliminates them from the default include path. So copy them into
    # place.
    for h in /tools/clang-linux64/lib/clang/*/include/*intrin.h /tools/clang-linux64/lib/clang/*/include/{__wmmintrin_aes.h,__wmmintrin_pclmul.h,mm_malloc.h}; do
        filename=$(basename "$h")
        if [ -e "/tools/host/include/${filename}" ]; then
            echo "${filename} already exists; don't need to copy!"
            exit 1
        fi
        cp "$h" /tools/host/include/
    done
else
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --enable-shared"
    PYBUILD_SHARED=1
fi

if [ -n "${CPYTHON_DEBUG}" ]; then
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --with-pydebug"
fi

if [ -n "${CPYTHON_OPTIMIZED}" ]; then
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --enable-optimizations"
fi

if [ -n "${CPYTHON_LTO}" ]; then
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --with-lto"
fi

if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
    # Configure may detect libintl from non-system sources, such
    # as Homebrew or MacPorts. So nerf the check to prevent this.
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_lib_intl_textdomain=no"

    # When building against an 11.0+ SDK, preadv() and pwritev() are
    # detected and used, despite only being available in the 11.0+ SDK. This
    # prevents object files from re-linking when built with older SDKs.
    # So we disable them. But not in aarch64-apple-darwin, as that target
    # requires the 11.0 SDK.
    #
    # This solution is less than ideal. Modern versions of Python support
    # weak linking and it should be possible to coerce these functions into
    # being weakly linked.
    if [ "${TARGET_TRIPLE}" != "aarch64-apple-darwin" ]; then
        CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_func_preadv=no"
        CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_func_pwritev=no"
    fi

    if [ -n "${CROSS_COMPILING}" ]; then
        # Python's configure doesn't support cross-compiling on macOS. So we need
        # to explicitly set MACHDEP to avoid busted checks. The code for setting
        # MACHDEP also sets ac_sys_system/ac_sys_release, so we have to set
        # those as well.
        if [ "${TARGET_TRIPLE}" = "aarch64-apple-darwin" ]; then
            CONFIGURE_FLAGS="${CONFIGURE_FLAGS} MACHDEP=darwin"
            CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_sys_system=Darwin"
            CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_sys_release=$(uname -r)"
        elif [ "${TARGET_TRIPLE}" = "aarch64-apple-ios" ]; then
            CONFIGURE_FLAGS="${CONFIGURE_FLAGS} MACHDEP=iOS"
            CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_sys_system=iOS"
            CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_sys_release="
            # clock_settime() not available on iOS.
            CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_func_clock_settime=no"
            # getentropy() not available on iOS.
            CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_func_getentropy=no"
        elif [ "${TARGET_TRIPLE}" = "x86_64-apple-darwin" ]; then
            CONFIGURE_FLAGS="${CONFIGURE_FLAGS} MACHDEP=darwin"
            CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_sys_system=Darwin"
            CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_sys_release=$(uname -r)"
        elif [ "${TARGET_TRIPLE}" = "x86_64-apple-ios" ]; then
            CONFIGURE_FLAGS="${CONFIGURE_FLAGS} MACHDEP=iOS"
            CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_sys_system=iOS"
            CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_sys_release="
            # clock_settime() not available on iOS.
            CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_func_clock_settime=no"
            # getentropy() not available on iOS.
            CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_func_getentropy=no"
        else
            echo "unsupported target triple: ${TARGET_TRIPLE}"
            exit 1
        fi
    fi

    # Python's configure looks exclusively at MACOSX_DEPLOYMENT_TARGET for
    # determining the platform tag. We specify the minimum target via cflags
    # like -mmacosx-version-min but configure doesn't pick up on those. In
    # addition, configure isn't smart enough to look at environment variables
    # for other SDK targets to determine the OS version. So our hack here is
    # to expose MACOSX_DEPLOYMENT_TARGET everywhere so the value percolates
    # into platform tag.
    export MACOSX_DEPLOYMENT_TARGET="${APPLE_MIN_DEPLOYMENT_TARGET}"
fi

if [ -n "${CROSS_COMPILING}" ]; then
    # configure doesn't like a handful of scenarios when cross-compiling.
    #
    # getaddrinfo buggy test fails for some reason. So we short-circuit it.
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_buggy_getaddrinfo=no"
    # The /dev/* check also fails for some reason.
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_file__dev_ptc=no"
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_file__dev_ptmx=no"
fi

CFLAGS=$CFLAGS CPPFLAGS=$CFLAGS LDFLAGS=$LDFLAGS \
    ./configure ${CONFIGURE_FLAGS}

# configure checks for the presence of functions and blindly uses them,
# even if they aren't available in the target macOS SDK. Work around that.
# But only on Python 3.8, as Python 3.9.1 improved this functionality.
if [[ "${PYBUILD_PLATFORM}" = "macos" && "${PYTHON_MAJMIN_VERSION}" = "3.8" ]]; then
    sed -i "" "s/#define HAVE_UTIMENSAT 1//g" pyconfig.h
    sed -i "" "s/#define HAVE_FUTIMENS 1//g" pyconfig.h
fi

# Supplement produced Makefile with our modifications.
cat ../Makefile.extra >> Makefile

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out/python

if [ -n "${CPYTHON_DEBUG}" ]; then
    PYTHON_BINARY_SUFFIX=d
else
    PYTHON_BINARY_SUFFIX=
fi

# Python interpreter to use during the build. When cross-compiling,
# we have the Makefile emit a script which sets some environment
# variables that force the invoked Python to pick up the configuration
# of the target Python but invoke the host binary.
if [ -n "${CROSS_COMPILING}" ]; then
    make write-python-for-build
    BUILD_PYTHON=$(pwd)/python-for-build
else
    BUILD_PYTHON=${ROOT}/out/python/install/bin/python3
fi

# If we're building a shared library hack some binaries so rpath is set.
# This ensures we can run the binary in any location without
# LD_LIBRARY_PATH pointing to the directory containing libpython.
if [ "${PYBUILD_SHARED}" = "1" ]; then
    if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
        LIBPYTHON_SHARED_LIBRARY_BASENAME=libpython${PYTHON_MAJMIN_VERSION}${PYTHON_BINARY_SUFFIX}.dylib
        LIBPYTHON_SHARED_LIBRARY=${ROOT}/out/python/install/lib/${LIBPYTHON_SHARED_LIBRARY_BASENAME}

        # There's only 1 dylib produced on macOS and it has the binary suffix.
        install_name_tool \
            -change /install/lib/${LIBPYTHON_SHARED_LIBRARY_BASENAME} @executable_path/../lib/${LIBPYTHON_SHARED_LIBRARY_BASENAME} \
            ${ROOT}/out/python/install/bin/python${PYTHON_MAJMIN_VERSION}

        # Python's build system doesn't make this file writable.
        chmod 755 ${ROOT}/out/python/install/lib/${LIBPYTHON_SHARED_LIBRARY_BASENAME}
        install_name_tool \
            -change /install/lib/${LIBPYTHON_SHARED_LIBRARY_BASENAME} @executable_path/${LIBPYTHON_SHARED_LIBRARY_BASENAME} \
            ${ROOT}/out/python/install/lib/${LIBPYTHON_SHARED_LIBRARY_BASENAME}

        # We also normalize /tools/deps/lib/libz.1.dylib to the system location.
        install_name_tool \
            -change /tools/deps/lib/libz.1.dylib /usr/lib/libz.1.dylib \
            ${ROOT}/out/python/install/bin/python${PYTHON_MAJMIN_VERSION}
        install_name_tool \
            -change /tools/deps/lib/libz.1.dylib /usr/lib/libz.1.dylib \
            ${ROOT}/out/python/install/lib/${LIBPYTHON_SHARED_LIBRARY_BASENAME}

        if [ -n "${PYTHON_BINARY_SUFFIX}" ]; then
            install_name_tool \
                -change /install/lib/${LIBPYTHON_SHARED_LIBRARY_BASENAME} @executable_path/../lib/${LIBPYTHON_SHARED_LIBRARY_BASENAME} \
                ${ROOT}/out/python/install/bin/python${PYTHON_MAJMIN_VERSION}${PYTHON_BINARY_SUFFIX}
        fi
    else
        LIBPYTHON_SHARED_LIBRARY_BASENAME=libpython${PYTHON_MAJMIN_VERSION}${PYTHON_BINARY_SUFFIX}.so.1.0
        LIBPYTHON_SHARED_LIBRARY=${ROOT}/out/python/install/lib/${LIBPYTHON_SHARED_LIBRARY_BASENAME}

        # If we simply set DT_RUNPATH via --set-rpath, LD_LIBRARY_PATH would be used before
        # DT_RUNPATH, which could result in confusion at run-time. But if DT_NEEDED
        # contains a slash, the explicit path is used.
        patchelf --replace-needed ${LIBPYTHON_SHARED_LIBRARY_BASENAME} "\$ORIGIN/../lib/${LIBPYTHON_SHARED_LIBRARY_BASENAME}" \
            ${ROOT}/out/python/install/bin/python${PYTHON_MAJMIN_VERSION}

        # libpython3.so isn't present in debug builds.
        if [ -z "${CPYTHON_DEBUG}" ]; then
            patchelf --replace-needed ${LIBPYTHON_SHARED_LIBRARY_BASENAME} "\$ORIGIN/../lib/${LIBPYTHON_SHARED_LIBRARY_BASENAME}" \
                ${ROOT}/out/python/install/lib/libpython3.so
        fi

        if [ -n "${PYTHON_BINARY_SUFFIX}" ]; then
            patchelf --replace-needed ${LIBPYTHON_SHARED_LIBRARY_BASENAME} "\$ORIGIN/../lib/${LIBPYTHON_SHARED_LIBRARY_BASENAME}" \
                ${ROOT}/out/python/install/bin/python${PYTHON_MAJMIN_VERSION}${PYTHON_BINARY_SUFFIX}
        fi
    fi
fi

# Install setuptools and pip as they are common tools that should be in any
# Python distribution.
#
# We disabled ensurepip because we insist on providing our own pip and don't
# want the final product to possibly be contaminated by another version.
#
# It is possible for the Python interpreter to run wheels directly. So we
# simply use our pip to install self. Kinda crazy, but it works!

${BUILD_PYTHON} "${PIP_WHEEL}/pip" install --prefix="${ROOT}/out/python/install" --no-cache-dir --no-index "${PIP_WHEEL}"
${BUILD_PYTHON} "${PIP_WHEEL}/pip" install --prefix="${ROOT}/out/python/install" --no-cache-dir --no-index "${SETUPTOOLS_WHEEL}"

# Emit metadata to be used in PYTHON.json.
cat > ${ROOT}/generate_metadata.py << EOF
import codecs
import importlib.machinery
import importlib.util
import json
import os
import sys
import sysconfig

# When doing cross builds, sysconfig still picks up abiflags from the
# host Python, which is never built in debug mode. Patch abiflags accordingly.
if os.environ.get("CPYTHON_DEBUG") and "d" not in sysconfig.get_config_var("abiflags"):
    sys.abiflags += "d"
    sysconfig._CONFIG_VARS["abiflags"] += "d"

# importlib.machinery.EXTENSION_SUFFIXES picks up its value from #define in C
# code. When we're doing a cross-build, the C code is the build machine, not
# the host/target and is wrong. The logic here essentially reimplements the
# logic for _PyImport_DynLoadFiletab in dynload_shlib.c, which is what
# importlib.machinery.EXTENSION_SUFFIXES ultimately calls into.
extension_suffixes = [".%s.so" % sysconfig.get_config_var("SOABI")]

alt_soabi = sysconfig.get_config_var("ALT_SOABI")
if alt_soabi:
    # The value can be double quoted for some reason.
    extension_suffixes.append(".%s.so" % alt_soabi.strip('"'))

# Always version 3 in Python 3.
extension_suffixes.append(".abi3.so")

extension_suffixes.append(".so")

metadata = {
    "python_abi_tag": sys.abiflags,
    "python_implementation_cache_tag": sys.implementation.cache_tag,
    "python_implementation_hex_version": sys.implementation.hexversion,
    "python_implementation_name": sys.implementation.name,
    "python_implementation_version": [str(x) for x in sys.implementation.version],
    "python_platform_tag": sysconfig.get_platform(),
    "python_suffixes": {
        "bytecode": importlib.machinery.BYTECODE_SUFFIXES,
        "debug_bytecode": importlib.machinery.DEBUG_BYTECODE_SUFFIXES,
        "extension": extension_suffixes,
        "optimized_bytecode": importlib.machinery.OPTIMIZED_BYTECODE_SUFFIXES,
        "source": importlib.machinery.SOURCE_SUFFIXES,
    },
    "python_bytecode_magic_number": codecs.encode(importlib.util.MAGIC_NUMBER, "hex").decode("ascii"),
    "python_paths": {},
    "python_paths_abstract": sysconfig.get_paths(expand=False),
    "python_exe": "install/bin/python%s%s" % (sysconfig.get_python_version(), sys.abiflags),
    "python_major_minor_version": sysconfig.get_python_version(),
    "python_stdlib_platform_config": sysconfig.get_config_var("LIBPL").lstrip("/"),
    "python_config_vars": {k: str(v) for k, v in sysconfig.get_config_vars().items()},
}

# When cross-compiling, we use a host Python to run this script. There are
# some hacks to get sysconfig to pick up the correct data file. However,
# these hacks don't work for sysconfig.get_paths() and we get paths to the host
# Python paths. We work around this by overwriting some variables used for
# expansion. The Rust validator ensures any paths referenced by python_paths
# exist, so we don't need to validate here.
root = os.environ["ROOT"]
prefix = os.path.join(root, "out", "python")

# These are modified in _PYTHON_BUILD mode. Restore to normal.
sysconfig._INSTALL_SCHEMES["posix_prefix"]["include"] = "{installed_base}/include/python{py_version_short}{abiflags}"
sysconfig._INSTALL_SCHEMES["posix_prefix"]["platinclude"] = "{installed_platbase}/include/python{py_version_short}{abiflags}"

sysconfig_vars = dict(sysconfig.get_config_vars())
sysconfig_vars["base"] = os.path.join(prefix, "install")
sysconfig_vars["installed_base"] = os.path.join(prefix, "install")
sysconfig_vars["installed_platbase"] = os.path.join(prefix, "install")
sysconfig_vars["platbase"] = os.path.join(prefix, "install")

for name, path in sysconfig.get_paths(vars=sysconfig_vars).items():
    rel = os.path.relpath(path, prefix)
    metadata["python_paths"][name] = rel

with open(sys.argv[1], "w") as fh:
    json.dump(metadata, fh, sort_keys=True, indent=4)
EOF

${BUILD_PYTHON} ${ROOT}/generate_metadata.py ${ROOT}/metadata.json
cat ${ROOT}/metadata.json

if [ "${CC}" != "musl-clang" ]; then
    objdump -T ${LIBPYTHON_SHARED_LIBRARY} | grep GLIBC_ | awk '{print $5}' | awk -F_ '{print $2}' | sort -V | tail -n 1 > ${ROOT}/glibc_version.txt
    cat ${ROOT}/glibc_version.txt
fi

# Downstream consumers don't require bytecode files. So remove them.
# Ideally we'd adjust the build system. But meh.
find ${ROOT}/out/python/install -type d -name __pycache__ -print0 | xargs -0 rm -rf

# Ensure lib-dynload exists, or Python complains on startup.
LIB_DYNLOAD=${ROOT}/out/python/install/lib/python${PYTHON_MAJMIN_VERSION}/lib-dynload
mkdir -p "${LIB_DYNLOAD}"
touch "${LIB_DYNLOAD}/.empty"

# Symlink libpython so we don't have 2 copies.
case "${TARGET_TRIPLE}" in
aarch64-unknown-linux-gnu)
    PYTHON_ARCH="aarch64-linux-gnu"
    ;;
# This is too aggressive. But we don't have patches in place for
# setting the platform name properly on non-Darwin.
*-apple-*)
    PYTHON_ARCH="darwin"
    ;;
armv7-unknown-linux-gnueabi)
    PYTHON_ARCH="arm-linux-gnueabi"
    ;;
armv7-unknown-linux-gnueabihf)
    PYTHON_ARCH="arm-linux-gnueabihf"
    ;;
i686-unknown-linux-gnu)
    PYTHON_ARCH="i386-linux-gnu"
    ;;
mips-unknown-linux-gnu)
    PYTHON_ARCH="mips-linux-gnu"
    ;;
mipsel-unknown-linux-gnu)
    PYTHON_ARCH="mipsel-linux-gnu"
    ;;
mips64el-unknown-linux-gnuabi64)
    PYTHON_ARCH="mips64el-linux-gnuabi64"
    ;;
s390x-unknown-linux-gnu)
    PYTHON_ARCH="s390x-linux-gnu"
    ;;
x86_64-unknown-linux-*)
    PYTHON_ARCH="x86_64-linux-gnu"
    ;;
*)
    echo "unhandled target triple: ${TARGET_TRIPLE}"
    exit 1
esac

LIBPYTHON=libpython${PYTHON_MAJMIN_VERSION}${PYTHON_BINARY_SUFFIX}.a
ln -sf \
    python${PYTHON_MAJMIN_VERSION}/config-${PYTHON_MAJMIN_VERSION}${PYTHON_BINARY_SUFFIX}-${PYTHON_ARCH}/${LIBPYTHON} \
    ${ROOT}/out/python/install/lib/${LIBPYTHON}

if [ -n "${PYTHON_BINARY_SUFFIX}" ]; then
    # Ditto for Python executable.
    ln -sf \
        python${PYTHON_MAJMIN_VERSION}${PYTHON_BINARY_SUFFIX} \
        ${ROOT}/out/python/install/bin/python${PYTHON_MAJMIN_VERSION}
fi

if [ ! -f ${ROOT}/out/python/install/bin/python3 ]; then
    echo "python3 executable does not exist"
    exit 1
fi

# Fixup shebangs in Python scripts to reference the local python interpreter.
cat > ${ROOT}/fix_shebangs.py << EOF
import os
import sys

ROOT = sys.argv[1]

for f in sorted(os.listdir(ROOT)):
    full = os.path.join(ROOT, f)

    if os.path.islink(full) or not os.path.isfile(full):
        continue

    with open(full, "rb") as fh:
        initial = fh.read(64)

    if not initial.startswith(b"#!"):
        continue

    print("rewriting shebang in %s" % full)

    lines = []

    with open(full, "rb") as fh:
        next(fh)

        lines.extend([
            b"#!/bin/sh\n",
            b'"exec" "\$(dirname \$0)/python${PYTHON_MAJMIN_VERSION}${PYTHON_BINARY_SUFFIX}" "\$0" "\$@"\n',
        ])

        lines.extend(fh)

    with open(full, "wb") as fh:
        fh.write(b"".join(lines))
EOF

${BUILD_PYTHON} ${ROOT}/fix_shebangs.py ${ROOT}/out/python/install/bin

# Also copy object files so they can be linked in a custom manner by
# downstream consumers.
for d in Modules Objects Parser Parser/pegen Programs Python; do
    # Parser/pegen only exists in 3.9+
    if [ -d $d ]; then
        mkdir -p ${ROOT}/out/python/build/$d
        cp -av $d/*.o ${ROOT}/out/python/build/$d/
    fi
done

# Also copy extension variant metadata files.
if compgen -G "Modules/VARIANT-*.data" > /dev/null; then
    cp -av Modules/VARIANT-*.data ${ROOT}/out/python/build/Modules/
fi

# The object files need to be linked against library dependencies. So copy
# library files as well.
mkdir ${ROOT}/out/python/build/lib
cp -av ${TOOLS_PATH}/deps/lib/*.a ${ROOT}/out/python/build/lib/

if [ -d "${TOOLS_PATH}/deps/libedit" ]; then
    cp -av ${TOOLS_PATH}/deps/libedit/lib/*.a ${ROOT}/out/python/build/lib/
fi

# On Apple, Python 3.9+ uses __builtin_available() to sniff for feature
# availability. This symbol is defined by clang_rt, which isn't linked
# by default. When building a static library, one must explicitly link
# against clang_rt or you will get an undefined symbol error for
# ___isOSVersionAtLeast.
#
# We copy the libclang_rt.<platform>.a library from our clang into the
# distribution so it is available. See documentation in quirks.rst for more.
if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
  cp -av $(dirname $(which clang))/../lib/clang/*/lib/darwin/libclang_rt.osx.a ${ROOT}/out/python/build/lib/
fi

# And prune libraries we never reference.
rm -f ${ROOT}/out/python/build/lib/{libdb-6.0,libxcb-*,libX11-xcb}.a

if [ -d "${TOOLS_PATH}/deps/lib/tcl8" ]; then
    # Copy tcl/tk/tix resources needed by tkinter.
    mkdir ${ROOT}/out/python/install/lib/tcl
    # Keep this list in sync with tcl_library_paths.
    for source in ${TOOLS_PATH}/deps/lib/{itcl4.2.2,tcl8,tcl8.6,thread2.8.7,tk8.6}; do
        cp -av $source ${ROOT}/out/python/install/lib/
    done

    if [ "${PYBUILD_PLATFORM}" != "macos" ]; then
        cp -av ${TOOLS_PATH}/deps/lib/Tix8.4.3 ${ROOT}/out/python/install/lib/
    fi
fi

# config.c defines _PyImport_Inittab and extern references to modules, which
# downstream consumers may want to strip. We bundle config.c and config.c.in so
# a custom one can be produced downstream.
# frozen.c is something similar for frozen modules.
# Setup.dist/Setup.local are useful to parse for active modules and library
# dependencies.
cp -av Modules/config.c ${ROOT}/out/python/build/Modules/
cp -av Modules/config.c.in ${ROOT}/out/python/build/Modules/
cp -av Python/frozen.c ${ROOT}/out/python/build/Python/
cp -av Modules/Setup* ${ROOT}/out/python/build/Modules/

# Copy the test hardness runner for convenience.
cp -av Tools/scripts/run_tests.py ${ROOT}/out/python/build/

mkdir ${ROOT}/out/python/licenses
cp ${ROOT}/LICENSE.*.txt ${ROOT}/out/python/licenses/
