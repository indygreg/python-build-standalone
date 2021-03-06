ROOT := $(abspath $(CURDIR)/..)
HERE := $(ROOT)/cpython-unix
OUTDIR := $(ROOT)/build

BUILD := $(HERE)/build.py
NULL :=

COMMON_DEPENDS := \
#    $(BUILD) \
    $(NULL)

ifndef PYBUILD_TARGET_TRIPLE
    $(error PYBUILD_TARGET_TRIPLE not defined)
endif

ifndef PYBUILD_OPTIMIZATIONS
    $(error PYBUILD_OPTIMIZATIONS not defined)
endif

ifndef PYBUILD_HOST_PLATFORM
    $(error PYBUILD_HOST_PLATFORM not defined)
endif

ifndef PYBUILD_PYTHON_VERSION
    $(error PYBUILD_PYTHON_VERSION not defined)
endif

ifndef PYBUILD_PYTHON_MAJOR_VERSION
    $(error PYBUILD_PYTHON_MAJOR_VERSION not defined)
endif

TARGET_TRIPLE := $(PYBUILD_TARGET_TRIPLE)
HOST_PLATFORM := $(PYBUILD_HOST_PLATFORM)
PACKAGE_SUFFIX := $(TARGET_TRIPLE)-$(PYBUILD_OPTIMIZATIONS)

RUN_BUILD = $(BUILD) \
    --host-platform $(HOST_PLATFORM) \
    --target-triple $(TARGET_TRIPLE) \
    --optimizations $(PYBUILD_OPTIMIZATIONS) \
    --dest-archive $@ \
    $(NULL)

ifeq ($(HOST_PLATFORM),linux64)
    NEED_BDB := 1
    NEED_BINUTILS := 1
    NEED_GCC := 1
    NEED_MUSL :=
    NEED_GDBM := 1
    NEED_GETTEXT :=
    NEED_LIBEDIT := 1
    NEED_NCURSES := 1
    NEED_X11 := 1
    NEED_READLINE := 1
    NEED_SQLITE := 1
    NEED_TIX := 1
    NEED_UUID := 1
endif

ifeq ($(HOST_PLATFORM),macos)
ifeq ($(TARGET_TRIPLE),aarch64-apple-ios)
    NEED_BDB :=
    NEED_BINUTILS :=
    NEED_GCC :=
    NEED_MUSL :=
    NEED_GDBM :=
    NEED_GETTEXT :=
    NEED_LIBEDIT :=
    NEED_NCURSES :=
    NEED_SQLITE :=
    NEED_X11 :=
    NEED_READLINE :=
    NEED_TIX :=
    NEED_UUID :=
else
    NEED_BDB :=
    NEED_BINUTILS :=
    NEED_GCC :=
    NEED_MUSL :=
    NEED_GDBM :=
    NEED_GETTEXT :=
    NEED_LIBEDIT := 1
    NEED_NCURSES := 1
    NEED_X11 :=
    NEED_READLINE :=
    NEED_SQLITE := 1
    NEED_TIX := 1
    NEED_UUID := 1
endif
endif

ifdef PYBUILD_MUSL
    PLATFORM := $(PLATFORM)-musl
    NEED_MUSL := 1
endif

ifdef PYBUILD_LIBRESSL
    NEED_LIBRESSL := 1
    NEED_OPENSSL :=
else
    NEED_OPENSSL := 1
    NEED_LIBRESSL :=
endif

# Always write out package version files.
$(shell $(RUN_BUILD) dummy_archive versions)
include $(OUTDIR)/versions/VERSION.*

BASE_TOOLCHAIN_DEPENDS := \
    $(if $(NEED_BINUTILS),$(OUTDIR)/binutils-$(BINUTILS_VERSION)-$(HOST_PLATFORM).tar) \
    $(if $(NEED_GCC),$(OUTDIR)/gcc-$(GCC_VERSION)-$(HOST_PLATFORM).tar) \
    $(OUTDIR)/clang-$(CLANG_VERSION)-$(HOST_PLATFORM).tar \
    $(NULL)

TOOLCHAIN_DEPENDS := \
    $(BASE_TOOLCHAIN_DEPENDS) \
    $(if $(NEED_MUSL),$(OUTDIR)/musl-$(MUSL_VERSION)-$(HOST_PLATFORM).tar) \
    $(NULL)

PYTHON_DEP_DEPENDS := \
    $(if $(PYBUILD_NO_DOCKER),,$(OUTDIR)/image-build.tar) \
    $(if $(PYBUILD_SKIP_TOOLCHAIN),,$(TOOLCHAIN_DEPENDS)) \
    $(NULL)

default: $(OUTDIR)/cpython-$(PYBUILD_PYTHON_VERSION)-$(PACKAGE_SUFFIX).tar

ifndef PYBUILD_NO_DOCKER
$(OUTDIR)/image-%.tar: $(HERE)/%.Dockerfile $(COMMON_DEPENDS)
	$(RUN_BUILD) --toolchain image-$*
endif

$(OUTDIR)/binutils-$(BINUTILS_VERSION)-$(HOST_PLATFORM).tar: $(OUTDIR)/image-gcc.tar $(HERE)/build-binutils.sh
	$(RUN_BUILD) --toolchain binutils

GCC_DEPENDS := \
    $(OUTDIR)/binutils-$(BINUTILS_VERSION)-$(HOST_PLATFORM).tar \
    $(OUTDIR)/versions/VERSION.gmp \
    $(OUTDIR)/versions/VERSION.isl \
    $(OUTDIR)/versions/VERSION.mpc \
    $(OUTDIR)/versions/VERSION.mpfr \
    $(HERE)/build-gcc.sh \
    $(NULL)

$(OUTDIR)/gcc-$(GCC_VERSION)-$(HOST_PLATFORM).tar: $(GCC_DEPENDS)
	$(RUN_BUILD) --toolchain gcc

CLANG_DEPENDS := \
    $(if $(NEED_BINUTILS),$(OUTDIR)/binutils-$(BINUTILS_VERSION)-$(HOST_PLATFORM).tar) \
    $(if $(NEED_GCC),$(OUTDIR)/gcc-$(GCC_VERSION)-$(HOST_PLATFORM).tar) \
    $(if $(PYBUILD_NO_DOCKER),,$(OUTDIR)/image-clang.tar) \
    $(HERE)/build-clang-$(HOST_PLATFORM).sh \
    $(NULL)

$(OUTDIR)/clang-$(CLANG_VERSION)-$(HOST_PLATFORM).tar: $(CLANG_DEPENDS)
	$(RUN_BUILD) --toolchain clang

$(OUTDIR)/musl-$(MUSL_VERSION)-$(HOST_PLATFORM).tar: $(BASE_TOOLCHAIN_DEPENDS) $(HERE)/build-musl.sh
	$(RUN_BUILD) --toolchain musl

ifeq ($(HOST_PLATFORM),linux64)
    TOOLCHAIN_TARGET := $(OUTDIR)/musl-$(MUSL_VERSION)-$(HOST_PLATFORM).tar
else
    TOOLCHAIN_TARGET := $(OUTDIR)/clang-$(CLANG_VERSION)-$(HOST_PLATFORM).tar
endif

toolchain: $(TOOLCHAIN_TARGET)

$(OUTDIR)/bdb-$(BDB_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-bdb.sh
	$(RUN_BUILD) bdb

$(OUTDIR)/bzip2-$(BZIP2_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-bzip2.sh
	$(RUN_BUILD) bzip2

$(OUTDIR)/gdbm-$(GDBM_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-gdbm.sh
	$(RUN_BUILD) gdbm

$(OUTDIR)/gettext-$(GETTEXT_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-gettext.sh
	$(RUN_BUILD) gettext

$(OUTDIR)/inputproto-$(INPUTPROTO_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-inputproto.sh
	$(RUN_BUILD) inputproto

$(OUTDIR)/kbproto-$(KBPROTO_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-kbproto.sh
	$(RUN_BUILD) kbproto

$(OUTDIR)/libffi-$(LIBFFI_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-libffi.sh
	$(RUN_BUILD) libffi

$(OUTDIR)/libpthread-stubs-$(LIBPTHREAD_STUBS_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-libpthread-stubs.sh $(OUTDIR)/image-build.tar
	$(RUN_BUILD) libpthread-stubs

LIBX11_DEPENDS = \
    $(PYTHON_DEP_DEPENDS) \
    $(HERE)/build-libX11.sh \
    $(OUTDIR)/xproto-$(XPROTO_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/xextproto-$(XEXTPROTO_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/kbproto-$(KBPROTO_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/inputproto-$(INPUTPROTO_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/libxcb-$(LIBXCB_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/xtrans-$(XTRANS_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/xorgproto-$(XORGPROTO_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(NULL)

$(OUTDIR)/libX11-$(LIBX11_VERSION)-$(PACKAGE_SUFFIX).tar: $(LIBX11_DEPENDS)
	$(RUN_BUILD) libX11

LIBXAU_DEPENDS = \
    $(PYTHON_DEP_DEPENDS) \
    $(HERE)/build-libXau.sh \
    $(OUTDIR)/x11-util-macros-$(X11_UTIL_MACROS_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/xproto-$(XPROTO_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(NULL)

$(OUTDIR)/libXau-$(LIBXAU_VERSION)-$(PACKAGE_SUFFIX).tar: $(LIBXAU_DEPENDS)
	$(RUN_BUILD) libXau

LIBXCB_DEPENDS = \
    $(PYTHON_DEP_DEPENDS) \
    $(HERE)/build-libxcb.sh \
    $(OUTDIR)/image-xcb.tar \
    $(OUTDIR)/xcb-proto-$(XCB_PROTO_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/libXau-$(LIBXAU_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/xproto-$(XPROTO_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/libpthread-stubs-$(LIBPTHREAD_STUBS_VERSION)-$(PACKAGE_SUFFIX).tar
    $(NULL)

$(OUTDIR)/libxcb-$(LIBXCB_VERSION)-$(PACKAGE_SUFFIX).tar: $(LIBXCB_DEPENDS)
	$(RUN_BUILD) libxcb

$(OUTDIR)/ncurses-$(NCURSES_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-ncurses.sh
	$(RUN_BUILD) ncurses

$(OUTDIR)/openssl-$(OPENSSL_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-openssl.sh
	$(RUN_BUILD) openssl

LIBEDIT_DEPENDS = \
    $(PYTHON_DEP_DEPENDS) \
    $(OUTDIR)/ncurses-$(NCURSES_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(HERE)/build-libedit.sh \
    $(NULL)

$(OUTDIR)/libedit-$(LIBEDIT_VERSION)-$(PACKAGE_SUFFIX).tar: $(LIBEDIT_DEPENDS)
	$(RUN_BUILD) libedit

$(OUTDIR)/libressl-$(LIBRESSL_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-libressl.sh
	$(RUN_BUILD) libressl

READLINE_DEPENDS = \
    $(PYTHON_DEP_DEPENDS) \
    $(OUTDIR)/ncurses-$(NCURSES_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(HERE)/build-readline.sh

$(OUTDIR)/readline-$(READLINE_VERSION)-$(PACKAGE_SUFFIX).tar: $(READLINE_DEPENDS)
	$(RUN_BUILD) readline

$(OUTDIR)/sqlite-$(SQLITE_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-sqlite.sh
	$(RUN_BUILD) sqlite

$(OUTDIR)/tcl-$(TCL_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-tcl.sh
	$(RUN_BUILD) tcl

TIX_DEPENDS = \
    $(HERE)/build-tix.sh \
    $(OUTDIR)/tcl-$(TCL_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/tk-$(TK_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(if $(NEED_X11),$(OUTDIR)/libX11-$(LIBX11_VERSION)-$(PACKAGE_SUFFIX).tar) \
    $(NULL)

$(OUTDIR)/tix-$(TIX_VERSION)-$(PACKAGE_SUFFIX).tar: $(TIX_DEPENDS)
	$(RUN_BUILD) tix

TK_DEPENDS = \
    $(HERE)/build-tk.sh \
    $(OUTDIR)/tcl-$(TCL_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(if $(NEED_X11),$(OUTDIR)/libX11-$(LIBX11_VERSION)-$(PACKAGE_SUFFIX).tar) \
    $(NULL)

$(OUTDIR)/tk-$(TK_VERSION)-$(PACKAGE_SUFFIX).tar: $(TK_DEPENDS)
	$(RUN_BUILD) tk

$(OUTDIR)/uuid-$(UUID_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-uuid.sh
	$(RUN_BUILD) uuid

$(OUTDIR)/x11-util-macros-$(X11_UTIL_MACROS_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-x11-util-macros.sh
	$(RUN_BUILD) x11-util-macros

$(OUTDIR)/xcb-proto-$(XCB_PROTO_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-xcb-proto.sh
	$(RUN_BUILD) xcb-proto

$(OUTDIR)/xextproto-$(XEXTPROTO_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-xextproto.sh
	$(RUN_BUILD) xextproto

$(OUTDIR)/xorgproto-$(XORGPROTO_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-xorgproto.sh
	$(RUN_BUILD) xorgproto

$(OUTDIR)/xproto-$(XPROTO_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-xproto.sh
	$(RUN_BUILD) xproto

$(OUTDIR)/xtrans-$(XTRANS_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-xtrans.sh
	$(RUN_BUILD) xtrans

$(OUTDIR)/xz-$(XZ_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-xz.sh
	$(RUN_BUILD) xz

$(OUTDIR)/zlib-$(ZLIB_VERSION)-$(PACKAGE_SUFFIX).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-zlib.sh
	$(RUN_BUILD) zlib

PYTHON_DEPENDS := \
    $(if $(NEED_BDB),$(OUTDIR)/bdb-$(BDB_VERSION)-$(PACKAGE_SUFFIX).tar) \
    $(OUTDIR)/bzip2-$(BZIP2_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(if $(NEED_GDBM),$(OUTDIR)/gdbm-$(GDBM_VERSION)-$(PACKAGE_SUFFIX).tar) \
    $(if $(NEED_GETTEXT),$(OUTDIR)/gettext-$(GETTEXT_VERSION)-$(PACKAGE_SUFFIX).tar) \
    $(if $(NEED_LIBEDIT),$(OUTDIR)/libedit-$(LIBEDIT_VERSION)-$(PACKAGE_SUFFIX).tar) \
    $(OUTDIR)/libffi-$(LIBFFI_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(if $(NEED_LIBRESSL),$(OUTDIR)/libressl-$(LIBRESSL_VERSION)-$(PACKAGE_SUFFIX).tar) \
    $(if $(NEED_NCURSES),$(OUTDIR)/ncurses-$(NCURSES_VERSION)-$(PACKAGE_SUFFIX).tar) \
    $(if $(NEED_OPENSSL),$(OUTDIR)/openssl-$(OPENSSL_VERSION)-$(PACKAGE_SUFFIX).tar) \
    $(if $(NEED_READLINE),$(OUTDIR)/readline-$(READLINE_VERSION)-$(PACKAGE_SUFFIX).tar) \
    $(if $(NEED_SQLITE),$(OUTDIR)/sqlite-$(SQLITE_VERSION)-$(PACKAGE_SUFFIX).tar) \
    $(if $(NEED_TIX),$(OUTDIR)/tix-$(TIX_VERSION)-$(PACKAGE_SUFFIX).tar) \
    $(if $(NEED_UUID),$(OUTDIR)/uuid-$(UUID_VERSION)-$(PACKAGE_SUFFIX).tar) \
    $(OUTDIR)/xz-$(XZ_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(OUTDIR)/zlib-$(ZLIB_VERSION)-$(PACKAGE_SUFFIX).tar \
    $(HERE)/disabled-static-modules.$(PYBUILD_PYTHON_MAJOR_VERSION).$(HOST_PLATFORM) \
    $(HERE)/required-extensions.$(PYBUILD_PYTHON_MAJOR_VERSION).$(HOST_PLATFORM) \
    $(HERE)/static-modules.$(PYBUILD_PYTHON_MAJOR_VERSION).$(HOST_PLATFORM) \
    $(NULL)

ALL_PYTHON_DEPENDS = \
    $(PYTHON_DEP_DEPENDS) \
    $(HERE)/build-cpython.sh \
    $(PYTHON_DEPENDS) \
    $(NULL)

$(OUTDIR)/cpython-$(CPYTHON_3.8_VERSION)-$(PACKAGE_SUFFIX).tar: $(ALL_PYTHON_DEPENDS)
	$(RUN_BUILD) cpython-3.8

$(OUTDIR)/cpython-$(CPYTHON_3.9_VERSION)-$(PACKAGE_SUFFIX).tar: $(ALL_PYTHON_DEPENDS)
	$(RUN_BUILD) cpython-3.9
