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
tar -xf setuptools-${SETUPTOOLS_VERSION}.tar.gz
tar -xf pip-${PIP_VERSION}.tar.gz

# If we are cross-compiling, we need to build a host Python to use during
# the build.
if [ "${BUILD_TRIPLE}" != "${TARGET_TRIPLE}" ]; then
  pushd "Python-${PYTHON_VERSION}"

  ./configure --prefix "${TOOLS_PATH}/pyhost"
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

# configure doesn't support cross-compiling on Apple. Teach it.
patch -p1 << "EOF"
diff --git a/configure b/configure
index 1d81c00c63..8a7370c291 100755
--- a/configure
+++ b/configure
@@ -3358,6 +3358,9 @@ if test "$cross_compiling" = yes; then
 	*-*-cygwin*)
 		_host_cpu=
 		;;
+	*-*-darwin*)
+		_host_cpu=
+		;;
 	*-*-vxworks*)
 		_host_cpu=$host_cpu
 		;;
@@ -6199,13 +6202,6 @@ esac
   fi
 fi
 
-if test "$cross_compiling" = yes; then
-    case "$READELF" in
-	readelf|:)
-	as_fn_error $? "readelf for the host is required for cross builds" "$LINENO" 5
-	;;
-    esac
-fi
 
 
 
EOF

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
    else
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
    fi
fi

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

# libedit on non-macOS requires various hacks because readline.c assumes
# libedit is only used on macOS and its readline/libedit detection code
# makes various assumptions about the macOS environment.
#
# USE_LIBEDIT comes from our static-modules file.
#
# TODO make upstream patches to readline.c to properly support libedit
# on other platforms.
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
index 57335fe911..f3e83ff932 100644
--- a/Modules/readline-libedit.c
+++ b/Modules/readline-libedit.c
@@ -486,7 +486,7 @@ set the word delimiters for completion");

 /* _py_free_history_entry: Utility function to free a history entry. */

-#if defined(RL_READLINE_VERSION) && RL_READLINE_VERSION >= 0x0500
+#ifndef USE_LIBEDIT

 /* Readline version >= 5.0 introduced a timestamp field into the history entry
    structure; this needs to be freed to avoid a memory leak.  This version of
@@ -1032,7 +1032,7 @@ flex_complete(const char *text, int start, int end)
 #ifdef HAVE_RL_COMPLETION_APPEND_CHARACTER
     rl_completion_append_character ='\0';
 #endif
-#ifdef HAVE_RL_COMPLETION_SUPPRESS_APPEND
+#ifndef USE_LIBEDIT
     rl_completion_suppress_append = 0;
 #endif


EOF

# Modules/readline.c has various libedit conditions behind an
# ``#ifdef __APPLE__`` instead of a more specific feature flag. All
# occurrences of __APPLE__ in that file are related to libedit. So we
# just replace the content.
sed s/__APPLE__/USE_LIBEDIT/g Modules/readline-libedit.c > tmp
mv tmp Modules/readline-libedit.c

# Modules/_hashopenssl.c redefines some libcrypto symbols on Python 3.9 and
# this makes the linker unhappy. So rename the symbols to work around.
# https://bugs.python.org/issue41949.
if [ "${PYTHON_MAJMIN_VERSION}" = "3.9" ]; then
    patch -p1 <<EOF
diff --git a/Modules/_hashopenssl.c b/Modules/_hashopenssl.c
index adc8653773..fc9070fc21 100644
--- a/Modules/_hashopenssl.c
+++ b/Modules/_hashopenssl.c
@@ -32,7 +32,7 @@
 #  error "OPENSSL_THREADS is not defined, Python requires thread-safe OpenSSL"
 #endif

-#if (OPENSSL_VERSION_NUMBER < 0x10100000L) || defined(LIBRESSL_VERSION_NUMBER)
+#if (OPENSSL_VERSION_NUMBER < 0x10100000L)
 /* OpenSSL < 1.1.0 */
 #define EVP_MD_CTX_new EVP_MD_CTX_create
 #define EVP_MD_CTX_free EVP_MD_CTX_destroy
EOF
fi

# Most bits look at CFLAGS. But setup.py only looks at CPPFLAGS.
# So we need to set both.
CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC -I${TOOLS_PATH}/deps/include -I${TOOLS_PATH}/deps/include/ncursesw"
LDFLAGS="${EXTRA_TARGET_LDFLAGS} -L${TOOLS_PATH}/deps/lib"

if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
    # Ensure we use the configured SDK. This also enables cross-compilation.
    CFLAGS="${CFLAGS} -isysroot ${MACOS_SDK_PATH}"
    LDFLAGS="${LDFLAGS} -isysroot ${MACOS_SDK_PATH}"

    CFLAGS="${CFLAGS} -I${TOOLS_PATH}/deps/lib/libffi-3.2.1/include -I${TOOLS_PATH}/deps/include/uuid"
    CFLAGS="${CFLAGS} -F${MACOS_SDK_PATH}/System/Library/Frameworks"

    # Prevent using symbols not supported by current macOS SDK target.
    CFLAGS="${CFLAGS} -Werror=unguarded-availability-new"
fi

CPPFLAGS=$CFLAGS

CONFIGURE_FLAGS="
    --build=${BUILD_TRIPLE} \
    --host=${TARGET_TRIPLE}
    --prefix=/install
    --with-openssl=${TOOLS_PATH}/deps
    --without-ensurepip"

if [ "${CC}" = "musl-clang" ]; then
    CFLAGS="${CFLAGS} -static"
    CPPFLAGS="${CPPFLAGS} -static"
    LDFLAGS="${LDFLAGS} -static"
    PYBUILD_SHARED=0
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

    if [ "${BUILD_TRIPLE}" != "${TARGET_TRIPLE}" ]; then
      # Python's configure doesn't support cross-compiling on macOS. So we need
      # to explicitly set MACHDEP to avoid busted checks. The code for setting
      # MACHDEP also sets ac_sys_system/ac_sys_release, so we have to set
      # those as well.
      CONFIGURE_FLAGS="${CONFIGURE_FLAGS} MACHDEP=darwin"
      CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_sys_system=Darwin"
      CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_sys_release=$(uname -r)"

      # getaddrinfo buggy test fails for some reason.
      CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_buggy_getaddrinfo=no"

      # We also need to nerf the /dev/* check
      CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_file__dev_ptc=no"
      CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_file__dev_ptmx=no"
    fi
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
if [ "${BUILD_TRIPLE}" != "${TARGET_TRIPLE}" ]; then
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
        LIBPYTHON_SHARED_LIBRARY=${ROOT}/out/python/install/lib/libpython${PYTHON_MAJMIN_VERSION}${PYTHON_BINARY_SUFFIX}.so.1.0

        patchelf --set-rpath '$ORIGIN/../lib' ${ROOT}/out/python/install/bin/python${PYTHON_MAJMIN_VERSION}

        # libpython3.so isn't present in debug builds.
        if [ -z "${CPYTHON_DEBUG}" ]; then
            patchelf --set-rpath '$ORIGIN/../lib' ${ROOT}/out/python/install/lib/libpython3.so
        fi

        if [ -n "${PYTHON_BINARY_SUFFIX}" ]; then
            patchelf --set-rpath '$ORIGIN/../lib' ${ROOT}/out/python/install/bin/python${PYTHON_MAJMIN_VERSION}${PYTHON_BINARY_SUFFIX}
        fi
    fi
fi

# Install pip so we can patch it to work with non-dynamic executables
# and work around https://github.com/pypa/pip/issues/6543. But pip's bundled
# setuptools has the same bug! So we need to install a patched version.
pushd ${ROOT}/setuptools-${SETUPTOOLS_VERSION}
patch -p1 <<EOF
diff --git a/setuptools/_vendor/packaging/tags.py b/setuptools/_vendor/packaging/tags.py
index ec9942f0..1b306ca7 100644
--- a/setuptools/_vendor/packaging/tags.py
+++ b/setuptools/_vendor/packaging/tags.py
@@ -283,7 +283,10 @@ def _glibc_version_string():
     # which libc our process is actually using.
     #
     # Note: typeshed is wrong here so we are ignoring this line.
-    process_namespace = ctypes.CDLL(None)  # type: ignore
+    try:
+        process_namespace = ctypes.CDLL(None)  # type: ignore
+    except OSError:
+        return None
     try:
         gnu_get_libc_version = process_namespace.gnu_get_libc_version
     except AttributeError:
EOF

${BUILD_PYTHON} setup.py install
popd

pushd ${ROOT}/pip-${PIP_VERSION}
patch -p1 <<EOF
diff --git a/src/pip/_internal/utils/glibc.py b/src/pip/_internal/utils/glibc.py
--- a/src/pip/_internal/utils/glibc.py
+++ b/src/pip/_internal/utils/glibc.py
@@ -18,7 +18,10 @@ def glibc_version_string():
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

${BUILD_PYTHON} setup.py install
popd

# Emit metadata to be used in PYTHON.json.
cat > ${ROOT}/generate_metadata.py << EOF
import codecs
import importlib.machinery
import importlib.util
import json
import os
import sys
import sysconfig

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
        "extension": importlib.machinery.EXTENSION_SUFFIXES,
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

root = os.environ["ROOT"]
for name, path in sysconfig.get_paths().items():
    rel = os.path.relpath(path, os.path.join(root, "out", "python"))
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
if [ ! -d ${LIB_DYNLOAD} ]; then
  mkdir -p ${LIB_DYNLOAD}
  touch ${LIB_DYNLOAD}/.empty
fi

# Symlink libpython so we don't have 2 copies.
if [ -n "${PYTHON_BINARY_SUFFIX}" ]; then
    if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
        PYTHON_ARCH="darwin"
    else
        PYTHON_ARCH="x86_64-linux-gnu"
    fi

    LIBPYTHON=libpython${PYTHON_MAJMIN_VERSION}${PYTHON_BINARY_SUFFIX}.a
    ln -sf \
        python${PYTHON_MAJMIN_VERSION}/config-${PYTHON_MAJMIN_VERSION}${PYTHON_BINARY_SUFFIX}-${PYTHON_ARCH}/${LIBPYTHON} \
        ${ROOT}/out/python/install/lib/${LIBPYTHON}

    # Ditto for Python executable.
    ln -sf \
        python${PYTHON_MAJMIN_VERSION}${PYTHON_BINARY_SUFFIX} \
        ${ROOT}/out/python/install/bin/python${PYTHON_MAJMIN_VERSION}
fi

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
if [ "${PYBUILD_PLATFORM}" != "macos" ]; then
    cp -av Modules/VARIANT-*.data ${ROOT}/out/python/build/Modules/
fi

# The object files need to be linked against library dependencies. So copy
# library files as well.
mkdir ${ROOT}/out/python/build/lib
cp -av ${TOOLS_PATH}/deps/lib/*.a ${ROOT}/out/python/build/lib/
cp -av ${TOOLS_PATH}/deps/libedit/lib/*.a ${ROOT}/out/python/build/lib/

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

# Copy tcl/tk/tix resources needed by tkinter.
mkdir ${ROOT}/out/python/install/lib/tcl
# Keep this list in sync with tcl_library_paths.
for source in ${TOOLS_PATH}/deps/lib/{tcl8,tcl8.6,thread2.8.5,Tix8.4.3,tk8.6}; do
    cp -av $source ${ROOT}/out/python/install/lib/
done

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
