ROOT := $(abspath $(CURDIR)/..)
HERE := $(ROOT)/cpython-macos
OUTDIR := $(ROOT)/build

BUILD := $(HERE)/build.py
NULL :=

PLATFORM := macos

TOOLCHAIN_DEPENDENCIES := $(OUTDIR)/clang-macos.tar

default: $(OUTDIR)/cpython-macos.tar

$(OUTDIR)/clang-macos.tar: $(HERE)/build-clang.sh
	$(BUILD) clang

$(OUTDIR)/bdb-macos.tar: $(HERE)/build-bdb.sh $(TOOLCHAIN_DEPENDENCIES)
	$(BUILD) bdb

$(OUTDIR)/bzip2-macos.tar: $(HERE)/build-bzip2.sh $(TOOLCHAIN_DEPENDENCIES)
	$(BUILD) bzip2

$(OUTDIR)/libedit-macos.tar: $(HERE)/build-libedit.sh $(TOOLCHAIN_DEPENDENCIES)
	$(BUILD) libedit

$(OUTDIR)/libffi-macos.tar: $(HERE)/build-libffi.sh $(TOOLCHAIN_DEPENDENCIES)
	$(BUILD) libffi

$(OUTDIR)/openssl-macos.tar: $(HERE)/build-openssl.sh $(TOOLCHAIN_DEPENDENCIES)
	$(BUILD) openssl

$(OUTDIR)/ncurses-macos.tar: $(HERE)/build-ncurses.sh $(TOOLCHAIN_DEPENDENCIES)
	$(BUILD) ncurses

$(OUTDIR)/sqlite-macos.tar: $(HERE)/build-sqlite.sh $(TOOLCHAIN_DEPENDENCIES)
	$(BUILD) sqlite

$(OUTDIR)/uuid-macos.tar: $(HERE)/build-uuid.sh $(TOOLCHAIN_DEPENDENCIES)
	$(BUILD) uuid

$(OUTDIR)/xz-macos.tar: $(HERE)/build-xz.sh $(TOOLCHAIN_DEPENDENCIES)
	$(BUILD) xz

$(OUTDIR)/zlib-macos.tar: $(HERE)/build-zlib.sh $(TOOLCHAIN_DEPENDENCIES)
	$(BUILD) zlib

PYTHON_DEPENDS := \
    $(TOOLCHAIN_DEPENDENCIES) \
	$(HERE)/static-modules \
	$(HERE)/build-cpython.sh \
	$(OUTDIR)/clang-macos.tar \
	$(OUTDIR)/bdb-macos.tar \
    $(OUTDIR)/bzip2-macos.tar \
    $(OUTDIR)/libedit-macos.tar \
    $(OUTDIR)/libffi-macos.tar \
    $(OUTDIR)/ncurses-macos.tar \
    $(OUTDIR)/openssl-macos.tar \
    $(OUTDIR)/sqlite-macos.tar \
    $(OUTDIR)/uuid-macos.tar \
    $(OUTDIR)/xz-macos.tar \
    $(OUTDIR)/zlib-macos.tar \
    $(NULL)

$(OUTDIR)/cpython-macos.tar: $(PYTHON_DEPENDS)
	$(BUILD) cpython
