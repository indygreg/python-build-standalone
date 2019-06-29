ROOT := $(abspath $(CURDIR)/..)
HERE := $(ROOT)/cpython-linux
OUTDIR := $(ROOT)/build

BUILD := $(HERE)/build.py
NULL :=

COMMON_DEPENDS := \
#    $(BUILD) \
    $(NULL)

PLATFORM := linux64

ifdef PYBUILD_MUSL
    PLATFORM := $(PLATFORM)-musl
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

BASE_TOOLCHAIN_DEPENDS := \
    $(OUTDIR)/binutils-linux64.tar \
    $(OUTDIR)/gcc-linux64.tar \
    $(OUTDIR)/clang-linux64.tar \
    $(NULL)

TOOLCHAIN_DEPENDS := \
    $(BASE_TOOLCHAIN_DEPENDS) \
    $(OUTDIR)/musl-linux64.tar \
    $(NULL)

PYTHON_DEP_DEPENDS := \
    $(OUTDIR)/image-build.tar \
    $(TOOLCHAIN_DEPENDS) \
    $(NULL)

default: $(OUTDIR)/cpython-$(PLATFORM)$(DEFAULT_EXTRA).tar

$(OUTDIR)/image-%.tar: $(HERE)/%.Dockerfile $(COMMON_DEPENDS)
	$(BUILD) image-$*

$(OUTDIR)/binutils-linux64.tar: $(OUTDIR)/image-gcc.tar $(HERE)/build-binutils.sh
	$(BUILD) binutils

$(OUTDIR)/gcc-linux64.tar: $(OUTDIR)/binutils-linux64.tar $(HERE)/build-gcc.sh
	$(BUILD) gcc

$(OUTDIR)/clang-linux64.tar: $(OUTDIR)/binutils-linux64.tar $(OUTDIR)/gcc-linux64.tar $(OUTDIR)/image-clang.tar $(HERE)/build-clang.sh
	$(BUILD) clang

$(OUTDIR)/musl-linux64.tar: $(BASE_TOOLCHAIN_DEPENDS) $(HERE)/build-musl.sh
	$(BUILD) musl

$(OUTDIR)/bdb-%.tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-bdb.sh
	$(BUILD) --platform $* bdb

$(OUTDIR)/bzip2-%.tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-bzip2.sh
	$(BUILD) --platform $* bzip2

$(OUTDIR)/gdbm-%.tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-gdbm.sh
	$(BUILD) --platform $* gdbm

$(OUTDIR)/libffi-%.tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-libffi.sh
	$(BUILD) --platform $* libffi

$(OUTDIR)/ncurses-%.tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-ncurses.sh
	$(BUILD) --platform $* ncurses

$(OUTDIR)/openssl-%.tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-openssl.sh
	$(BUILD) --platform $* openssl

$(OUTDIR)/libedit-%.tar: $(PYTHON_DEP_DEPENDS) $(OUTDIR)/ncurses-%.tar $(HERE)/build-libedit.sh
	$(BUILD) --platform $* libedit

$(OUTDIR)/readline-%.tar: $(PYTHON_DEP_DEPENDS) $(OUTDIR)/ncurses-$(PLATFORM).tar $(HERE)/build-readline.sh
	$(BUILD) --platform $* readline

$(OUTDIR)/sqlite-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-sqlite.sh
	$(BUILD) --platform $(PLATFORM) sqlite

$(OUTDIR)/tcltk-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-tcltk.sh
	$(BUILD) --platform $(PLATFORM) tcltk

$(OUTDIR)/uuid-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-uuid.sh
	$(BUILD) --platform $(PLATFORM) uuid

$(OUTDIR)/xz-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-xz.sh
	$(BUILD) --platform $(PLATFORM) xz

$(OUTDIR)/zlib-$(PLATFORM).tar: $(TOOLCHAIN_DEPENDS) $(HERE)/build-zlib.sh
	$(BUILD) --platform $(PLATFORM) zlib

PYTHON_DEPENDS := \
    $(OUTDIR)/bdb-$(PLATFORM).tar \
    $(OUTDIR)/bzip2-$(PLATFORM).tar \
    $(OUTDIR)/gdbm-$(PLATFORM).tar \
    $(OUTDIR)/libedit-$(PLATFORM).tar \
    $(OUTDIR)/libffi-$(PLATFORM).tar \
    $(OUTDIR)/ncurses-$(PLATFORM).tar \
    $(OUTDIR)/openssl-$(PLATFORM).tar \
    $(OUTDIR)/readline-$(PLATFORM).tar \
    $(OUTDIR)/sqlite-$(PLATFORM).tar \
    $(OUTDIR)/uuid-$(PLATFORM).tar \
    $(OUTDIR)/xz-$(PLATFORM).tar \
    $(OUTDIR)/zlib-$(PLATFORM).tar \
    $(HERE)/static-modules \
    $(NULL)

$(OUTDIR)/cpython-$(PLATFORM).tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-cpython.sh $(PYTHON_DEPENDS)
	$(BUILD) --platform $(PLATFORM) cpython

$(OUTDIR)/cpython-$(PLATFORM)-debug.tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-cpython.sh $(PYTHON_DEPENDS)
	$(BUILD) --platform $(PLATFORM) --debug cpython

$(OUTDIR)/cpython-$(PLATFORM)-pgo.tar: $(PYTHON_DEP_DEPENDS) $(HERE)/build-cpython.sh $(PYTHON_DEPENDS)
	$(BUILD) --platform $(PLATFORM) --optimized cpython
