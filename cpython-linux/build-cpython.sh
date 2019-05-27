#!/usr/bin/env bash
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

set -ex

cd /build

export PATH=/tools/clang-linux64/bin:/tools/host/bin:/tools/deps/bin:$PATH

# configure somehow has problems locating llvm-profdata even though it is in
# PATH. The macro it is using allows us to specify its path via an
# environment variable.
export LLVM_PROFDATA=/tools/clang-linux64/bin/llvm-profdata

# We force linking of external static libraries by removing the shared
# libraries. This is hacky. But we're building in a temporary container
# and it gets the job done.
find /tools/deps -name '*.so*' -exec rm {} \;

tar -xf Python-${PYTHON_VERSION}.tar.xz

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

cp Modules/readline.c Modules/readline-libedit.c

# Python supports using libedit instead of readline. But Modules/readline.c
# has all of this behind ``#ifdef __APPLE__`` instead of a more specific
# feature flag. All occurrences of __APPLE__ in that file are related to
# libedit. So we just replace the content. USE_LIBEDIT comes from our
# static-modules file.
# TODO make changes upstream to allow libedit to more easily be used
sed -i s/__APPLE__/USE_LIBEDIT/g Modules/readline-libedit.c

# Most bits look at CFLAGS. But setup.py only looks at CPPFLAGS.
# So we need to set both.
CFLAGS="-fPIC -I/tools/deps/include -I/tools/deps/include/ncurses"
CPPFLAGS=$CFLAGS
LDFLAGS="-L/tools/deps/lib"

if [ "${CC}" = "musl-clang" ]; then
    CFLAGS="${CFLAGS} -static"
    CPPFLAGS="${CPPFLAGS} -static"
    LDFLAGS="${LDFLAGS} -static"
fi

CONFIGURE_FLAGS="--prefix=/install --with-openssl=/tools/deps --without-ensurepip"

# TODO support --with-lto
# --with-lto will produce .o files that are LLVM bitcode and aren't compatible
# with downstream consumers that can't handle them.
if [ -n "${CPYTHON_OPTIMIZED}" ]; then
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --enable-optimizations"
fi

CFLAGS=$CFLAGS CPPFLAGS=$CFLAGS LDFLAGS=$LDFLAGS \
    ./configure ${CONFIGURE_FLAGS}

# Supplement produced Makefile with our modifications.
cat ../Makefile.extra >> Makefile

make -j `nproc`
make -j `nproc` install DESTDIR=/build/out/python

# Downstream consumers don't require bytecode files. So remove them.
# Ideally we'd adjust the build system. But meh.
find /build/out/python/install -type d -name __pycache__ -print0 | xargs -0 rm -rf

# Also copy object files so they can be linked in a custom manner by
# downstream consumers.
for d in Modules Objects Parser Programs Python; do
    mkdir -p /build/out/python/build/$d
    cp -av $d/*.o /build/out/python/build/$d/
done

# Also copy extension variant metadata files.
cp -av Modules/VARIANT-*.data /build/out/python/build/Modules/

# The object files need to be linked against library dependencies. So copy
# library files as well.
mkdir /build/out/python/build/lib
cp -av /tools/deps/lib/*.a /build/out/python/build/lib/
cp -av /tools/deps/libedit/lib/*.a /build/out/python/build/lib/

# config.c defines _PyImport_Inittab and extern references to modules, which
# downstream consumers may want to strip. We bundle config.c and config.c.in so
# a custom one can be produced downstream.
# frozen.c is something similar for frozen modules.
# Setup.dist/Setup.local are useful to parse for active modules and library
# dependencies.
cp -av Modules/config.c /build/out/python/build/Modules/
cp -av Modules/config.c.in /build/out/python/build/Modules/
cp -av Python/frozen.c /build/out/python/build/Python/
cp -av Modules/Setup.dist /build/out/python/build/Modules/
cp -av Modules/Setup.local /build/out/python/build/Modules/
cp /build/python-licenses.rst /build/out/python/LICENSE.rst
