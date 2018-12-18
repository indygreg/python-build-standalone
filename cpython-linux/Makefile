ROOT := $(abspath $(CURDIR)/..)
HERE := $(ROOT)/cpython-linux
OUTDIR := $(ROOT)/build

BUILD := $(HERE)/build.py
NULL :=

COMMON_DEPENDS := \
#    $(BUILD) \
    $(NULL)

PLATFORM := linux64

TOOLCHAIN_DEPENDS := \
    $(OUTDIR)/binutils-linux64.tar \
    $(OUTDIR)/gcc-linux64.tar \
    $(OUTDIR)/clang-linux64.tar \
    $(NULL)

default: $(OUTDIR)/cpython-linux64.tar

$(OUTDIR)/image-%.tar: $(HERE)/%.Dockerfile $(COMMON_DEPENDS)
	$(BUILD) image-$*

$(OUTDIR)/binutils-linux64.tar: $(OUTDIR)/image-gcc.tar $(HERE)/build-binutils.sh
	$(BUILD) binutils

$(OUTDIR)/gcc-linux64.tar: $(OUTDIR)/binutils-linux64.tar $(HERE)/build-gcc.sh
	$(BUILD) gcc

$(OUTDIR)/clang-linux64.tar: $(OUTDIR)/binutils-linux64.tar $(OUTDIR)/gcc-linux64.tar $(OUTDIR)/image-clang.tar $(HERE)/build-clang.sh
	$(BUILD) clang

$(OUTDIR)/bzip2-%.tar: $(OUTDIR)/image-build.tar $(TOOLCHAIN_DEPENDS) $(HERE)/build-bzip2.sh
	$(BUILD) --platform $* bzip2

$(OUTDIR)/gdbm-%.tar: $(TOOLCHAIN_DEPENDS) $(HERE)/build-gdbm.sh
	$(BUILD) --platform $* gdbm

$(OUTDIR)/libffi-%.tar: $(TOOLCHAIN_DEPENDS) $(HERE)/build-libffi.sh
	$(BUILD) --platform $* libffi

$(OUTDIR)/ncurses-%.tar: $(TOOLCHAIN_DEPENDS) $(HERE)/build-ncurses.sh
	$(BUILD) --platform $* ncurses

$(OUTDIR)/openssl-%.tar: $(TOOLCHAIN_DEPENDS) $(HERE)/build-openssl.sh
	$(BUILD) --platform $* openssl

$(OUTDIR)/readline-%.tar: $(TOOLCHAIN_DEPENDS) $(OUTDIR)/ncurses-$(PLATFORM).tar $(HERE)/build-readline.sh
	$(BUILD) --platform $* readline

$(OUTDIR)/sqlite-$(PLATFORM).tar: $(TOOLCHAIN_DEPENDS) $(HERE)/build-sqlite.sh
	$(BUILD) --platform $(PLATFORM) sqlite

$(OUTDIR)/tcltk-$(PLATFORM).tar: $(TOOLCHAIN_DEPENDS) $(HERE)/build-tcltk.sh
	$(BUILD) --platform $(PLATFORM) tcltk

$(OUTDIR)/uuid-$(PLATFORM).tar: $(TOOLCHAIN_DEPENDS) $(HERE)/build-uuid.sh
	$(BUILD) --platform $(PLATFORM) uuid

$(OUTDIR)/xz-$(PLATFORM).tar: $(TOOLCHAIN_DEPENDS) $(HERE)/build-xz.sh
	$(BUILD) --platform $(PLATFORM) xz

$(OUTDIR)/zlib-$(PLATFORM).tar: $(TOOLCHAIN_DEPENDS) $(HERE)/build-zlib.sh
	$(BUILD) --platform $(PLATFORM) zlib

PYTHON_DEPENDS := \
    $(OUTDIR)/bzip2-$(PLATFORM).tar \
    $(OUTDIR)/gdbm-$(PLATFORM).tar \
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

$(OUTDIR)/cpython-$(PLATFORM).tar: $(TOOLCHAIN_DEPENDS) $(HERE)/build-cpython.sh $(PYTHON_DEPENDS)
	$(BUILD) --platform $(PLATFORM) cpython
