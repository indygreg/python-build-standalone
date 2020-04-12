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
unzip setuptools-${SETUPTOOLS_VERSION}.zip
tar -xf pip-${PIP_VERSION}.tar.gz

cat Setup.local
mv Setup.local Python-${PYTHON_VERSION}/Modules/Setup.local

cat Makefile.extra

pushd Python-${PYTHON_VERSION}

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

# Most bits look at CFLAGS. But setup.py only looks at CPPFLAGS.
# So we need to set both.
CFLAGS="-fPIC -I${TOOLS_PATH}/deps/include -I${TOOLS_PATH}/deps/include/ncurses"

if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
    CFLAGS="${CFLAGS} -I${TOOLS_PATH}/deps/lib/libffi-3.2.1/include -I${TOOLS_PATH}/deps/include/uuid"

    CFLAGS="${CFLAGS} -I${MACOS_SDK_PATH}/System/Library/Frameworks/Tk.framework/Versions/8.5/Headers"
    CFLAGS="${CFLAGS} -F${MACOS_SDK_PATH}/System/Library/Frameworks"

    # Prevent using symbols not supported by current macOS SDK target.
    CFLAGS="${CFLAGS} -Werror=unguarded-availability-new"
fi

CPPFLAGS=$CFLAGS
LDFLAGS="-L${TOOLS_PATH}/deps/lib"

if [ "${CC}" = "musl-clang" ]; then
    CFLAGS="${CFLAGS} -static"
    CPPFLAGS="${CPPFLAGS} -static"
    LDFLAGS="${LDFLAGS} -static"
fi

CONFIGURE_FLAGS="--prefix=/install --with-openssl=${TOOLS_PATH}/deps --without-ensurepip"

if [ -n "${CPYTHON_DEBUG}" ]; then
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --with-pydebug"
fi

# TODO support --with-lto
# --with-lto will produce .o files that are LLVM bitcode and aren't compatible
# with downstream consumers that can't handle them.
if [ -n "${CPYTHON_OPTIMIZED}" ]; then
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --enable-optimizations"
fi

CFLAGS=$CFLAGS CPPFLAGS=$CFLAGS LDFLAGS=$LDFLAGS \
    ./configure ${CONFIGURE_FLAGS}

# configure checks for the presence of functions and blindly uses them,
# even if they aren't available in the target macOS SDK. Work around that.
if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
    sed -i "" "s/#define HAVE_UTIMENSAT 1//g" pyconfig.h
    sed -i "" "s/#define HAVE_FUTIMENS 1//g" pyconfig.h
fi

# Supplement produced Makefile with our modifications.
cat ../Makefile.extra >> Makefile

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} install DESTDIR=${ROOT}/out/python

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

${ROOT}/out/python/install/bin/python3 setup.py install
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

diff --git a/src/pip/_vendor/packaging/tags.py b/src/pip/_vendor/packaging/tags.py
index 60a69d8..08c0597 100644
--- a/src/pip/_vendor/packaging/tags.py
+++ b/src/pip/_vendor/packaging/tags.py
@@ -466,7 +466,10 @@ def _glibc_version_string_ctypes():
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

${ROOT}/out/python/install/bin/python3 setup.py install
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
    "bytecode_magic_number": codecs.encode(importlib.util.MAGIC_NUMBER, "hex").decode("ascii"),
    "python_paths": {},
    "python_exe": "install/bin/python%s%s" % (sysconfig.get_python_version(), sys.abiflags),
    "python_major_minor_version": sysconfig.get_python_version(),
}

root = os.environ["ROOT"]
for name, path in sysconfig.get_paths().items():
    rel = os.path.relpath(path, os.path.join(root, "out", "python"))
    metadata["python_paths"][name] = rel

with open(sys.argv[1], "w") as fh:
    json.dump(metadata, fh, sort_keys=True, indent=4)
EOF

PYTHON_EXE=${ROOT}/out/python/install/bin/$(readlink ${ROOT}/out/python/install/bin/python3)

${ROOT}/out/python/install/bin/python3 ${ROOT}/generate_metadata.py ${ROOT}/metadata.json
cat ${ROOT}/metadata.json

if [ "${CC}" != "musl-clang" ]; then
    objdump -T ${PYTHON_EXE} | grep GLIBC_ | awk '{print $5}' | awk -F_ '{print $2}' | sort -V | tail -n 1 > ${ROOT}/glibc_version.txt
    cat ${ROOT}/glibc_version.txt
fi

# Downstream consumers don't require bytecode files. So remove them.
# Ideally we'd adjust the build system. But meh.
find ${ROOT}/out/python/install -type d -name __pycache__ -print0 | xargs -0 rm -rf

# Ensure lib-dynload exists, or Python complains on startup.
mkdir -p ${ROOT}/out/python/install/lib/python${PYTHON_MAJMIN_VERISON}/lib-dynload

# Symlink libpython so we don't have 2 copies. We only need to do
# this on Python 3.7, as 3.8 dropped the m ABI suffix from binary names.

if [ "${PYTHON_MAJMIN_VERSION}" = "3.7" ]; then
    if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
        PYTHON_ARCH="darwin"
    else
        PYTHON_ARCH="x86_64-linux-gnu"
    fi

    LIBPYTHON=libpython${PYTHON_MAJMIN_VERSION}m.a
    ln -sf \
        python${PYTHON_MAJMIN_VERSION}/config-${PYTHON_MAJMIN_VERSION}m-${PYTHON_ARCH}/${LIBPYTHON} \
        ${ROOT}/out/python/install/lib/${LIBPYTHON}

    # Ditto for Python executable.
    ln -sf \
        python${PYTHON_MAJMIN_VERSION}m \
        ${ROOT}/out/python/install/bin/python${PYTHON_MAJMIN_VERSION}
fi

# Also copy object files so they can be linked in a custom manner by
# downstream consumers.
for d in Modules Objects Parser Programs Python; do
    mkdir -p ${ROOT}/out/python/build/$d
    cp -av $d/*.o ${ROOT}/out/python/build/$d/
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

# And prune libraries we never reference.
rm -f ${ROOT}/out/python/build/lib/{libdb-6.0,libxcb-*,libX11-xcb}.a

# Copy tcl/tk/tix resources needed by tkinter.
if [ "${PYBUILD_PLATFORM}" != "macos" ]; then
  mkdir ${ROOT}/out/python/install/lib/tcl
  for source in ${TOOLS_PATH}/deps/lib/{tcl8,tcl8.6,thread2.8.5,Tix8.4.3,tk8.6}; do
    cp -av $source ${ROOT}/out/python/install/lib/
  done
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
