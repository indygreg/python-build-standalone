ROOT := $(abspath $(CURDIR)/..)
HERE := $(ROOT)/cpython-unix
OUTDIR := $(ROOT)/build

BUILD := $(HERE)/build.py
NULL :=

COMMON_DEPENDS := \
#    $(BUILD) \
    $(NULL)

ifndef PYBUILD_UNIX_PLATFORM
    $(error PYBUILD_UNIX_PLATFORM not defined)
endif

PLATFORM := $(PYBUILD_UNIX_PLATFORM)
BASE_PLATFORM := $(PLATFORM)

ifeq ($(PLATFORM),linux64)
    NEED_BINUTILS := 1
    NEED_GCC := 1
    NEED_MUSL :=
    NEED_GDBM := 1
endif

ifeq ($(PLATFORM),macos)
    NEED_BINUTILS :=
    NEED_GCC :=
    NEED_MUSL :=
    NEED_GDBM :=
endif

BASE_PLATFORM := $(PLATFORM)

ifdef PYBUILD_MUSL
    PLATFORM := $(PLATFORM)-musl
    NEED_MUSL := 1
endif

ifdef PYBUILD_DEBUG
	DEFAULT_EXTRA := -debug
else
ifdef PYBUILD_OPTIMIZED
	DEFAULT_EXTRA := -pgo
else
	DEFAULT_EXTRA :=
endif
endif

# Always write out package version files.
$(shell $(BUILD) versions)
include $(OUTDIR)/versions/VERSION.*

BASE_TOOLCHAIN_DEPENDS := \
    $(if $(NEED_BINUTILS),$(OUTDIR)/binutils-$(BINUTILS_VERSION)-$(BASE_PLATFORM).tar) \
    $(if $(NEED_GCC),$(OUTDIR)/gcc-$(GCC_VERSION)-$(BASE_PLATFORM).tar) \
    $(OUTDIR)/clang-$(CLANG_VERSION)-$(BASE_PLATFORM).tar \
    $(NULL)

TOOLCHAIN_DEPENDS := \
    $(BASE_TOOLCHAIN_DEPENDS) \
    $(if $(NEED_MUSL),$(OUTDIR)/musl-$(MUSL_VERSION)-$(BASE_PLATFORM).tar) \
    $(NULL)

PYTHON_DEP_DEPENDS := \
    $(if $(PYBUILD_NO_DOCKER),,$(OUTDIR)/image-build.tar) \
    $(TOOLCHAIN_DEPENDS) \
    $(NULL)

default: $(OUTDIR)/cpython-$(PYBUILD_PYTHON_VERSION)-$(PLATFORM)$(DEFAULT_EXTRA).tar

ifndef PYBUILD_NO_DOCKER
$(OUTDIR)/image-%.tar: $(HERE)/%.Dockerfile $(COMMON_DEPENDS)
	$(BUILD) image-$*
endif

$(OUTDIR)/binutils-$(BINUTILS_VERSION)-$(BASE_PLATFORM).tar: $(OUTDIR)/image-gcc.tar $(HERE)/build-binutils.sh
	$(BUILD) binutils

$(OUTDIR)/gcc-$(GCC_VERSION)-$(BASE_PLATFORM).tar: $(OUTDIR)/binutils-$(BINUTILS_VERSION)-$(BASE_PLATFORM).tar $(HERE)/build-gcc.sh
	$(BUILD) gcc

CLANG_DEPENDS := \
    $(if $(NEED_BINUTILS),$(OUTDIR)/binutils-$(BINUTILS_VERSION)-$(BASE_PLATFORM).tar) \
    $(if $(NEED_GCC),$(OUTDIR)/gcc-$(GCC_VERSION)-$(BASE_PLATFORM).tar) \
    $(if $(PYBUILD_NO_DOCKER),,$(OUTDIR)/image-clang.tar) \
    $(HERE)/build-clang-$(BASE_PLATFORM).sh \
    $(NULL)

$(OUTDIR)/clang-$(CLANG_VERSION)-$(BASE_PLATFORM).tar: $(CLANG_DEPENDS)
	$(BUILD) clang --platform $(BASE_PLATFORM)

$(OUTDIR)/musl-$(MUSL_VERSION)-linux64.tar: $(BASE_TOOLCHAIN_DEPENDS) $(HERE)/build-musl.sh
	$(BUILD) musl

$(OUTDIR)/bdb-$(BDB_VERSION)-%.tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-bdb.sh
	$(BUILD) --platform $* bdb

$(OUTDIR)/bzip2-$(BZIP2_VERSION)-%.tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-bzip2.sh
	$(BUILD) --platform $* bzip2

$(OUTDIR)/gdbm-$(GDBM_VERSION)-%.tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-gdbm.sh
	$(BUILD) --platform $* gdbm

$(OUTDIR)/inputproto-$(INPUTPROTO_VERSION)-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-inputproto.sh
	$(BUILD) --platform $(PLATFORM) inputproto

$(OUTDIR)/kbproto-$(KBPROTO_VERSION)-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-kbproto.sh
	$(BUILD) --platform $(PLATFORM) kbproto

$(OUTDIR)/libffi-$(LIBFFI_VERSION)-%.tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-libffi.sh
	$(BUILD) --platform $* libffi

$(OUTDIR)/libpthread-stubs-$(LIBPTHREAD_STUBS_VERSION)-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-libpthread-stubs.sh $(OUTDIR)/image-build.tar
	$(BUILD) --platform $(PLATFORM) libpthread-stubs

LIBX11_DEPENDS = \
    $(PYTHON_DEP_DEPENDS) \
    $(HERE)/build-libX11.sh \
    $(OUTDIR)/xproto-$(XPROTO_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/xextproto-$(XEXTPROTO_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/kbproto-$(KBPROTO_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/inputproto-$(INPUTPROTO_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/libxcb-$(LIBXCB_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/xtrans-$(XTRANS_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/xorgproto-$(XORGPROTO_VERSION)-$(PLATFORM).tar \
    $(NULL)

$(OUTDIR)/libX11-$(LIBX11_VERSION)-$(PLATFORM).tar: $(LIBX11_DEPENDS)
	$(BUILD) --platform $(PLATFORM) libX11

$(OUTDIR)/libXau-$(LIBXAU_VERSION)-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-libXau.sh $(OUTDIR)/x11-util-macros-$(X11_UTIL_MACROS_VERSION)-$(PLATFORM).tar $(OUTDIR)/xproto-$(XPROTO_VERSION)-$(PLATFORM).tar
	$(BUILD) --platform $(PLATFORM) libXau

LIBXCB_DEPENDS = \
    $(PYTHON_DEP_DEPENDS) \
    $(HERE)/build-libxcb.sh \
    $(OUTDIR)/image-xcb.tar \
    $(OUTDIR)/xcb-proto-$(XCB_PROTO_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/libXau-$(LIBXAU_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/xproto-$(XPROTO_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/libpthread-stubs-$(LIBPTHREAD_STUBS_VERSION)-$(PLATFORM).tar
    $(NULL)

$(OUTDIR)/libxcb-$(LIBXCB_VERSION)-$(PLATFORM).tar: $(LIBXCB_DEPENDS)
	$(BUILD) --platform $(PLATFORM) libxcb

$(OUTDIR)/ncurses-$(NCURSES_VERSION)-%.tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-ncurses.sh
	$(BUILD) --platform $* ncurses

$(OUTDIR)/openssl-$(OPENSSL_VERSION)-%.tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-openssl.sh
	$(BUILD) --platform $* openssl

$(OUTDIR)/libedit-$(LIBEDIT_VERSION)-%.tar: $(PYTHON_DEP_DEPENDS) $(OUTDIR)/ncurses-$(NCURSES_VERSION)-%.tar $(HERE)/build-libedit.sh
	$(BUILD) --platform $* libedit

$(OUTDIR)/libressl-$(LIBRESSL_VERSION)-%.tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-libressl.sh
	$(BUILD) --platform $* libressl

$(OUTDIR)/readline-$(READLINE_VERSION)-%.tar: $(PYTHON_DEP_DEPENDS) $(OUTDIR)/ncurses-$(NCURSES_VERSION)-$(PLATFORM).tar $(HERE)/build-readline.sh
	$(BUILD) --platform $* readline

$(OUTDIR)/sqlite-$(SQLITE_VERSION)-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-sqlite.sh
	$(BUILD) --platform $(PLATFORM) sqlite

$(OUTDIR)/tcl-$(TCL_VERSION)-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-tcl.sh
	$(BUILD) --platform $(PLATFORM) tcl

TIX_DEPENDS = \
    $(HERE)/build-tix.sh \
    $(OUTDIR)/tcl-$(TCL_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/tcl-$(TCL_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/tk-$(TK_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/libX11-$(LIBX11_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/xorgproto-$(XORGPROTO_VERSION)-$(PLATFORM).tar \
    $(NULL)

$(OUTDIR)/tix-$(TIX_VERSION)-$(PLATFORM).tar: $(TIX_DEPENDS)
	$(BUILD) --platform $(PLATFORM) tix

$(OUTDIR)/tk-$(TK_VERSION)-$(PLATFORM).tar: $(HERE)/build-tk.sh $(OUTDIR)/tcl-$(TCL_VERSION)-$(PLATFORM).tar $(OUTDIR)/libX11-$(LIBX11_VERSION)-$(PLATFORM).tar
	$(BUILD) --platform $(PLATFORM) tk

$(OUTDIR)/uuid-$(UUID_VERSION)-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-uuid.sh
	$(BUILD) --platform $(PLATFORM) uuid

$(OUTDIR)/x11-util-macros-$(X11_UTIL_MACROS_VERSION)-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-x11-util-macros.sh
	$(BUILD) --platform $(PLATFORM) x11-util-macros

$(OUTDIR)/xcb-proto-$(XCB_PROTO_VERSION)-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-xcb-proto.sh
	$(BUILD) --platform $(PLATFORM) xcb-proto

$(OUTDIR)/xextproto-$(XEXTPROTO_VERSION)-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-xextproto.sh
	$(BUILD) --platform $(PLATFORM) xextproto

$(OUTDIR)/xorgproto-$(XORGPROTO_VERSION)-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-xorgproto.sh
	$(BUILD) --platform $(PLATFORM) xorgproto

$(OUTDIR)/xproto-$(XPROTO_VERSION)-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-xproto.sh
	$(BUILD) --platform $(PLATFORM) xproto

$(OUTDIR)/xtrans-$(XTRANS_VERSION)-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-xtrans.sh
	$(BUILD) --platform $(PLATFORM) xtrans

$(OUTDIR)/xz-$(XZ_VERSION)-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-xz.sh
	$(BUILD) --platform $(PLATFORM) xz

$(OUTDIR)/zlib-$(ZLIB_VERSION)-$(PLATFORM).tar: $(TOOLCHAIN_DEPENDS) $(HERE)/build-zlib.sh
	$(BUILD) --platform $(PLATFORM) zlib

PYTHON_DEPENDS := \
    $(OUTDIR)/bdb-$(BDB_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/bzip2-$(BZIP2_VERSION)-$(PLATFORM).tar \
    $(if $(NEED_GDBM),$(OUTDIR)/gdbm-$(GDBM_VERSION)-$(PLATFORM).tar) \
    $(OUTDIR)/libedit-$(LIBEDIT_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/libffi-$(LIBFFI_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/libX11-$(LIBX11_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/libXau-$(LIBXAU_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/libxcb-$(LIBXCB_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/ncurses-$(NCURSES_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/readline-$(READLINE_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/sqlite-$(SQLITE_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/tcl-$(TCL_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/tix-$(TIX_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/tk-$(TK_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/uuid-$(UUID_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/xorgproto-$(XORGPROTO_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/xz-$(XZ_VERSION)-$(PLATFORM).tar \
    $(OUTDIR)/zlib-$(ZLIB_VERSION)-$(PLATFORM).tar \
    $(HERE)/static-modules \
    $(NULL)

ifdef PYBUILD_LIBRESSL
PYTHON_DEPENDS += $(OUTDIR)/libressl-$(LIBRESSL_VERSION)-$(PLATFORM).tar
else
PYTHON_DEPENDS += $(OUTDIR)/openssl-$(OPENSSL_VERSION)-$(PLATFORM).tar
endif

$(OUTDIR)/cpython-$(PYBUILD_PYTHON_VERSION)-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-cpython.sh $(PYTHON_DEPENDS)
	$(BUILD) --platform $(PLATFORM) cpython

$(OUTDIR)/cpython-$(PYBUILD_PYTHON_VERSION)-$(PLATFORM)-debug.tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-cpython.sh $(PYTHON_DEPENDS)
	$(BUILD) --platform $(PLATFORM) --debug cpython

$(OUTDIR)/cpython-$(PYBUILD_PYTHON_VERSION)-$(PLATFORM)-pgo.tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-cpython.sh $(PYTHON_DEPENDS)
	$(BUILD) --platform $(PLATFORM) --optimized cpython
