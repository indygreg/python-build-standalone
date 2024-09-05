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

# autoconf has some paths hardcoded into scripts. These paths just work in
# the containerized build environment. But from macOS the paths are wrong.
# Explicitly point to the proper path via environment variable overrides.
export AUTOCONF=${TOOLS_PATH}/host/bin/autoconf
export AUTOHEADER=${TOOLS_PATH}/host/bin/autoheader
export AUTOM4TE=${TOOLS_PATH}/host/bin/autom4te
export autom4te_perllibdir=${TOOLS_PATH}/host/share/autoconf
export AC_MACRODIR=${TOOLS_PATH}/host/share/autoconf
export M4=${TOOLS_PATH}/host/bin/m4
export trailer_m4=${TOOLS_PATH}/host/share/autoconf/autoconf/trailer.m4

# The share/autoconf/autom4te.cfg file also hard-codes some paths. Rewrite
# those to the real tools path.
if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
  sed_args="-i '' -e"
else
  sed_args="-i"
fi

sed ${sed_args} "s|/tools/host|${TOOLS_PATH}/host|g" ${TOOLS_PATH}/host/share/autoconf/autom4te.cfg

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

patch -p1 -i ${ROOT}/patch-pip-static-binary.patch

zip -r "${PIP_WHEEL}" *
popd
rm -rf pip-tmp

cat Setup.local
mv Setup.local Python-${PYTHON_VERSION}/Modules/Setup.local

cat Makefile.extra

pushd Python-${PYTHON_VERSION}

# configure doesn't support cross-compiling on Apple. Teach it.
if [ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_12}" ]; then
    patch -p1 -i ${ROOT}/patch-apple-cross-3.12.patch
else
    patch -p1 -i ${ROOT}/patch-apple-cross.patch
fi

# This patch is slightly different on Python 3.10+.
if [ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_10}" ]; then
    patch -p1 -i ${ROOT}/patch-xopen-source-ios.patch
else
    patch -p1 -i ${ROOT}/patch-xopen-source-ios-legacy.patch
fi

# LIBTOOL_CRUFT is unused and breaks cross-compiling on macOS. Nuke it.
# Submitted upstream at https://github.com/python/cpython/pull/101048.
if [ -n "${PYTHON_MEETS_MAXIMUM_VERSION_3_11}" ]; then
    patch -p1 -i ${ROOT}/patch-configure-remove-libtool-cruft.patch
fi

# Configure nerfs RUNSHARED when cross-compiling, which prevents PGO from running when
# we can in fact run the target binaries (e.g. x86_64 host and i686 target). Undo that.
if [ -n "${CROSS_COMPILING}" ]; then
    if [ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_11}" ]; then
        patch -p1 -i ${ROOT}/patch-dont-clear-runshared.patch
    else
        patch -p1 -i ${ROOT}/patch-dont-clear-runshared-legacy.patch
    fi
fi

# Clang 13 actually prints something with --print-multiarch, confusing CPython's
# configure. This is reported as https://bugs.python.org/issue45405. We nerf the
# check since we know what we're doing.
if [ "${CC}" = "clang" ]; then
    if [ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_9}" ]; then
        patch -p1 -i ${ROOT}/patch-disable-multiarch.patch
    else
        patch -p1 -i ${ROOT}/patch-disable-multiarch-legacy.patch
    fi
fi

# Python 3.11 supports using a provided Python to use during bootstrapping
# (e.g. freezing). Normally it only uses this Python during cross-compiling.
# This patch forces always using it. See comment related to
# `--with-build-python` for more.
if [ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_11}" ]; then
    patch -p1 -i ${ROOT}/patch-always-build-python-for-freeze.patch
fi

# Add a make target to write the PYTHON_FOR_BUILD variable so we can
# invoke the host Python on our own.
if [ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_12}" ]; then
    patch -p1 -i ${ROOT}/patch-write-python-for-build-3.12.patch
else
    patch -p1 -i ${ROOT}/patch-write-python-for-build.patch
fi

# Object files can get listed multiple times leading to duplicate symbols
# when linking. Prevent this.
if [ -n "${PYTHON_MEETS_MAXIMUM_VERSION_3_10}" ]; then
  patch -p1 -i ${ROOT}/patch-makesetup-deduplicate-objs.patch
fi

# The default build rule for the macOS dylib doesn't pick up libraries
# from modules / makesetup. So patch it accordingly.
patch -p1 -i ${ROOT}/patch-macos-link-extension-modules.patch

# Also on macOS, the `python` executable is linked against libraries defined by statically
# linked modules. But those libraries should only get linked into libpython, not the
# executable. This behavior is kinda suspect on all platforms, as it could be adding
# library dependencies that shouldn't need to be there.
if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
    if [ "${PYTHON_MAJMIN_VERSION}" = "3.8" ]; then
        patch -p1 -i ${ROOT}/patch-python-link-modules-3.8.patch
    elif [ "${PYTHON_MAJMIN_VERSION}" = "3.9" ]; then
        patch -p1 -i ${ROOT}/patch-python-link-modules-3.9.patch
    elif [ "${PYTHON_MAJMIN_VERSION}" = "3.10" ]; then
        patch -p1 -i ${ROOT}/patch-python-link-modules-3.10.patch
    else
        patch -p1 -i ${ROOT}/patch-python-link-modules-3.11.patch
    fi
fi

# The macOS code for sniffing for _dyld_shared_cache_contains_path falls back on a
# possibly inappropriate code path if a configure time check fails. This is not
# appropriate for certain cross-compiling scenarios. See discussion at
# https://bugs.python.org/issue44689.
if [ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_11}" ]; then
    patch -p1 -i ${ROOT}/patch-ctypes-callproc.patch
else
    patch -p1 -i ${ROOT}/patch-ctypes-callproc-legacy.patch
fi

# Code that runs at ctypes module import time does not work with
# non-dynamic binaries. Patch Python to work around this.
# See https://bugs.python.org/issue37060.
patch -p1 -i ${ROOT}/patch-ctypes-static-binary.patch

# Older versions of Python need patching to work with modern mpdecimal.
if [ -n "${PYTHON_MEETS_MAXIMUM_VERSION_3_9}" ]; then
    patch -p1 -i ${ROOT}/patch-decimal-modern-mpdecimal.patch
fi

# CPython 3.10 added proper support for building against libedit outside of
# macOS. On older versions, we need to patch readline.c.
if [ -n "${PYTHON_MEETS_MAXIMUM_VERSION_3_9}" ]; then
    # readline.c assumes that a modern readline API version has a free_history_entry().
    # but libedit does not. Change the #ifdef accordingly.
    #
    # Similarly, we invoke configure using readline, which sets
    # HAVE_RL_COMPLETION_SUPPRESS_APPEND improperly. So hack that. This is a bug
    # in our build system, as we should probably be invoking configure again when
    # using libedit.
    patch -p1 -i ${ROOT}/patch-readline-libedit.patch
fi

# iOS doesn't have system(). Teach posixmodule.c about that.
# Python 3.11 makes this a configure time check, so we don't need the patch there.
if [[ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_9}" && -n "${PYTHON_MEETS_MAXIMUM_VERSION_3_10}" ]]; then
    patch -p1 -i ${ROOT}/patch-posixmodule-remove-system.patch
fi

# Python 3.11 has configure support for configuring extension modules. We really,
# really, really want to use this feature because it looks promising. But at the
# time we added this code the functionality didn't support all extension modules
# nor did it easily support static linking, including static linking of extra
# libraries (which appears to be a limitation of `makesetup`). So for now we
# disable the functionality and require our auto-generated Setup.local to provide
# everything.
if [ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_11}" ]; then
    if [ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_12}" ]; then
        patch -p1 -i ${ROOT}/patch-configure-disable-stdlib-mod-3.12.patch
    else
        patch -p1 -i ${ROOT}/patch-configure-disable-stdlib-mod.patch
    fi

    # This hack also prevents the conditional definition of the pwd module in
    # Setup.bootstrap.in from working. So we remove that conditional.
    patch -p1 -i ${ROOT}/patch-pwd-remove-conditional.patch
fi

# The optimization make targets are both phony and non-phony. This leads
# to PGO targets getting reevaluated after a build when you use multiple
# make invocations. e.g. `make install` like we do below. Fix that.
if [ -n "${PYTHON_MEETS_MAXIMUM_VERSION_3_11}" ]; then
    patch -p1 -i ${ROOT}/patch-pgo-make-targets.patch
fi

# There's a post-build Python script that verifies modules were
# built correctly. Ideally we'd invoke this. But our nerfing of
# the configure-based module building and replacing it with our
# own Setup-derived version completely breaks assumptions in this
# script. So leave it off for now... at our own peril.
if [ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_12}" ]; then
    patch -p1 -i ${ROOT}/patch-checksharedmods-disable.patch
fi

# CPython < 3.11 always linked against libcrypt. We backport part of
# upstream commit be21706f3760bec8bd11f85ce02ed6792b07f51f to avoid this
# behavior.
if [ -n "${PYTHON_MEETS_MAXIMUM_VERSION_3_10}" ]; then
    patch -p1 -i ${ROOT}/patch-configure-crypt-no-modify-libs.patch
fi

# We patched configure.ac above. Reflect those changes.
autoconf

# configure assumes cross compiling when host != target and doesn't provide a way to
# override. Our target triple normalization may lead configure into thinking we
# aren't cross-compiling when we are. So force a static "yes" value when our
# build system says we are cross-compiling.
if [ -n "${CROSS_COMPILING}" ]; then
  patch -p1 -i ${ROOT}/patch-force-cross-compile.patch
fi

# Most bits look at CFLAGS. But setup.py only looks at CPPFLAGS.
# So we need to set both.
CFLAGS="${EXTRA_TARGET_CFLAGS} -fPIC -I${TOOLS_PATH}/deps/include -I${TOOLS_PATH}/deps/include/ncursesw"
LDFLAGS="${EXTRA_TARGET_LDFLAGS} -L${TOOLS_PATH}/deps/lib"

# Some target configurations use `-fvisibility=hidden`. Python's configure handles
# symbol visibility properly itself. So let it do its thing.
CFLAGS=${CFLAGS//-fvisibility=hidden/}

# But some symbols from some dependency libraries are still non-hidden for some
# reason. We force the linker to do our bidding.
if [ "${PYBUILD_PLATFORM}" != "macos" ]; then
    LDFLAGS="${LDFLAGS} -Wl,--exclude-libs,ALL"
fi

EXTRA_CONFIGURE_FLAGS=

if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
    CFLAGS="${CFLAGS} -I${TOOLS_PATH}/deps/include/uuid"

    # Prevent using symbols not supported by current macOS SDK target.
    CFLAGS="${CFLAGS} -Werror=unguarded-availability-new"
fi

# Always build against libedit instead of the default of readline.
# macOS always uses the system libedit, so no tweaks are needed.
if [ "${PYBUILD_PLATFORM}" != "macos" ]; then
    # CPython 3.10 introduced proper configure support for libedit, so add configure
    # flag there.
    if [ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_10}" ]; then
        EXTRA_CONFIGURE_FLAGS="${EXTRA_CONFIGURE_FLAGS} --with-readline=editline"
    fi
fi

# On Python 3.12 we need to link the special hacl library provided some SHA-256
# implementations. Since we hack up the regular extension building mechanism, we
# need to reinvent this wheel.
if [ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_12}" ]; then
    LDFLAGS="${LDFLAGS} -LModules/_hacl"
fi

# On PPC we need to prevent the glibc 2.22 __tls_get_addr_opt symbol
# from being introduced to preserve runtime compatibility with older
# glibc.
if [[ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_12}" && "${TARGET_TRIPLE}" = "ppc64le-unknown-linux-gnu" ]]; then
    LDFLAGS="${LDFLAGS} -Wl,--no-tls-get-addr-optimize"
fi

CPPFLAGS=$CFLAGS

CONFIGURE_FLAGS="
    --build=${BUILD_TRIPLE}
    --host=${TARGET_TRIPLE}
    --prefix=/install
    --with-openssl=${TOOLS_PATH}/deps
    --with-system-expat
    --with-system-libmpdec
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
    for h in /tools/${TOOLCHAIN}/lib/clang/*/include/*intrin.h /tools/${TOOLCHAIN}/lib/clang/*/include/{__wmmintrin_aes.h,__wmmintrin_pclmul.h,mm_malloc.h}; do
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
    if [[ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_12}" && -n "${BOLT_CAPABLE}" ]]; then
        CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --enable-bolt"
    fi
fi

if [ -n "${CPYTHON_LTO}" ]; then
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --with-lto"
fi

# Python 3.11 introduces a --with-build-python to denote the host Python.
# It is required when cross-compiling. But we always build a host Python
# to avoid complexity with the bootstrap Python binary.
if [ -n "${PYTHON_MEETS_MINIMUM_VERSION_3_11}" ]; then
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --with-build-python=${TOOLS_PATH}/host/bin/python${PYTHON_MAJMIN_VERSION}"
fi

if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
    # Configure may detect libintl from non-system sources, such
    # as Homebrew or MacPorts. So nerf the check to prevent this.
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_lib_intl_textdomain=no"

    # CPython 3.9+ have proper support for weakly referenced symbols and
    # runtime availability guards. CPython 3.8 will emit weak symbol references
    # (this happens automatically when linking due to SDK version targeting).
    # However CPython lacks the runtime availability guards for most symbols.
    # This results in runtime failures when attempting to resolve/call the
    # symbol.
    #
    # Unfortunately, this means we need to ban weak symbols on CPython 3.8, to
    # the detriment of performance. However, we can actually use most symbols
    # on aarch64 because it targets macOS SDK 11.0, not 10.9. But more modern
    # symbols do need to be banned.
    if [ -n "${PYTHON_MEETS_MAXIMUM_VERSION_3_9}" ]; then
        if [ "${TARGET_TRIPLE}" != "aarch64-apple-darwin" ]; then
            for symbol in clock_getres clock_gettime clock_settime faccessat fchmodat fchownat fdopendir fstatat futimens getentropy linkat mkdirat openat preadv pwritev readlinkat renameat symlinkat unlinkat utimensat; do
                CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_func_${symbol}=no"
            done
        fi

        # mkfifoat, mknodat introduced in SDK 13.0.
        for symbol in mkfifoat mknodat; do
            CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_func_${symbol}=no"
        done
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

# We use ndbm on macOS and BerkeleyDB elsewhere.
if [ "${PYBUILD_PLATFORM}" = "macos" ]; then
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --with-dbmliborder=ndbm"
else
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} --with-dbmliborder=bdb"
fi

if [ -n "${CROSS_COMPILING}" ]; then
    # configure doesn't like a handful of scenarios when cross-compiling.
    #
    # getaddrinfo buggy test fails for some reason. So we short-circuit it.
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_buggy_getaddrinfo=no"
    # The /dev/* check also fails for some reason.
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_file__dev_ptc=no"
    CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_file__dev_ptmx=no"

    # When cross-compiling, configure cannot detect if the target system has a
    # working tzset function in C. This influences whether or not the compiled
    # python will end up with the time.tzset function or not. All linux targets,
    # however, should have a working tzset function via libc. So we manually
    # indicate this to the configure script.
    if [ "${PYBUILD_PLATFORM}" != "macos" ]; then
        CONFIGURE_FLAGS="${CONFIGURE_FLAGS} ac_cv_working_tzset=yes"
    fi
fi

CFLAGS=$CFLAGS CPPFLAGS=$CFLAGS LDFLAGS=$LDFLAGS \
    ./configure ${CONFIGURE_FLAGS}

# Supplement produced Makefile with our modifications.
cat ../Makefile.extra >> Makefile

make -j ${NUM_CPUS}
make -j ${NUM_CPUS} sharedinstall DESTDIR=${ROOT}/out/python
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

# Hack up the system configuration settings to aid portability.
#
# The goal here is to make the system configuration as generic as possible so
# that a) it works on as many machines as possible b) doesn't leak details
# about the build environment, which is non-portable.
cat > ${ROOT}/hack_sysconfig.py << EOF
import os
import sys
import sysconfig

ROOT = sys.argv[1]

MAJMIN = ".".join([str(sys.version_info[0]), str(sys.version_info[1])])
PYTHON_CONFIG = os.path.join(ROOT, "install", "bin", "python%s-config" % MAJMIN)
PLATFORM_CONFIG = os.path.join(ROOT, sysconfig.get_config_var("LIBPL").lstrip("/"))
MAKEFILE = os.path.join(PLATFORM_CONFIG, "Makefile")
SYSCONFIGDATA = os.path.join(
    ROOT,
    "install",
    "lib",
    "python%s" % MAJMIN,
    "%s.py" % sysconfig._get_sysconfigdata_name(),
)

def replace_in_file(path, search, replace):
    with open(path, "rb") as fh:
        data = fh.read()

    if search.encode("utf-8") in data:
        print("replacing '%s' in %s with '%s'" % (search, path, replace))
    else:
        print("warning: '%s' not in %s" % (search, path))

    data = data.replace(search.encode("utf-8"), replace.encode("utf-8"))

    with open(path, "wb") as fh:
        fh.write(data)


def replace_in_all(search, replace):
    replace_in_file(PYTHON_CONFIG, search, replace)
    replace_in_file(MAKEFILE, search, replace)
    replace_in_file(SYSCONFIGDATA, search, replace)


# -fdebug-default-version is Clang only. Strip so compiling works on GCC.
replace_in_all("-fdebug-default-version=4", "")

# Remove some build environment paths.
# This is /tools on Linux but can be a dynamic path / temp directory on macOS
# and when not using container builds.
tools_path = os.environ["TOOLS_PATH"]
replace_in_all("-I%s/deps/include/ncursesw" % tools_path, "")
replace_in_all("-I%s/deps/include/uuid" % tools_path, "")
replace_in_all("-I%s/deps/include" % tools_path, "")
replace_in_all("-L%s/deps/lib" % tools_path, "")

EOF

${BUILD_PYTHON} ${ROOT}/hack_sysconfig.py ${ROOT}/out/python

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
ppc64le-unknown-linux-gnu)
    PYTHON_ARCH="powerpc64le-linux-gnu"
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

ln -sf \
    "$(readlink ${ROOT}/out/python/install/bin/python3)" \
    ${ROOT}/out/python/install/bin/python

# Fixup shebangs in Python scripts to reference the local python interpreter.
cat > ${ROOT}/fix_shebangs.py << EOF
import os
import sys

ROOT = sys.argv[1]

def fix_shebang(full):
    if os.path.islink(full) or not os.path.isfile(full):
        return

    with open(full, "rb") as fh:
        initial = fh.read(256)

    if not initial.startswith(b"#!"):
        return

    if b"\n" not in initial:
        raise Exception("could not find end of shebang line; consider increasing read count")

    initial = initial.splitlines()[0].decode("utf-8", "replace")

    # Some shebangs are allowed.
    if "bin/env" in initial or "bin/sh" in initial or "bin/bash" in initial:
        print("ignoring %s due to non-python shebang (%s)" % (full, initial))
        return

    # Make sure it is a Python script and not something else.
    if "/python" not in initial:
       raise Exception("unexpected shebang (%s) in %s" % (initial, full))

    print("rewriting Python shebang (%s) in %s" % (initial, full))

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


for root, dirs, files in os.walk(ROOT):
    dirs[:] = sorted(dirs)

    for f in sorted(files):
        fix_shebang(os.path.join(root, f))
EOF

${BUILD_PYTHON} ${ROOT}/fix_shebangs.py ${ROOT}/out/python/install

# Also copy object files so they can be linked in a custom manner by
# downstream consumers.
OBJECT_DIRS="Objects Parser Parser/pegen Programs Python"
OBJECT_DIRS="${OBJECT_DIRS} Modules"
for ext in _blake2 cjkcodecs _ctypes _ctypes/darwin _decimal _expat _hacl _io _multiprocessing _sha3 _sqlite _sre _xxtestfuzz ; do
    OBJECT_DIRS="${OBJECT_DIRS} Modules/${ext}"
done

for d in ${OBJECT_DIRS}; do
    # Not all directories are in all Python versions. And some directories may
    # exist but not have object files.
    if compgen -G "${d}/*.o" > /dev/null; then
        mkdir -p ${ROOT}/out/python/build/$d
        cp -av $d/*.o ${ROOT}/out/python/build/$d/
    fi
done

# The object files need to be linked against library dependencies. So copy
# library files as well.
mkdir ${ROOT}/out/python/build/lib
cp -av ${TOOLS_PATH}/deps/lib/*.a ${ROOT}/out/python/build/lib/

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
    for source in ${TOOLS_PATH}/deps/lib/{itcl4.2.4,tcl8,tcl8.6,thread2.8.9,tk8.6}; do
        cp -av $source ${ROOT}/out/python/install/lib/
    done

    if [ "${PYBUILD_PLATFORM}" != "macos" ]; then
        cp -av ${TOOLS_PATH}/deps/lib/Tix8.4.3 ${ROOT}/out/python/install/lib/
    fi
fi

# Copy the terminfo database if present.
if [ -d "${TOOLS_PATH}/deps/usr/share/terminfo" ]; then
  cp -av ${TOOLS_PATH}/deps/usr/share/terminfo ${ROOT}/out/python/install/share/
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
