ROOT := $(abspath $(CURDIR)/..)
HERE := $(ROOT)/cpython-macos
OUTDIR := $(ROOT)/build

BUILD := $(HERE)/build.py
NULL :=

PLATFORM := macos

default: $(OUTDIR)/cpython-macos.tar

$(OUTDIR)/clang-macos.tar: $(HERE)/build-clang.sh
	$(BUILD) clang

$(OUTDIR)/bdb-macos.tar: $(HERE)/build-bdb.sh
	$(BUILD) bdb

$(OUTDIR)/bzip2-macos.tar: $(HERE)/build-bzip2.sh
	$(BUILD) bzip2

$(OUTDIR)/libedit-macos.tar: $(HERE)/build-libedit.sh
	$(BUILD) libedit

$(OUTDIR)/libffi-macos.tar: $(HERE)/build-libffi.sh
	$(BUILD) libffi

$(OUTDIR)/openssl-macos.tar: $(HERE)/build-openssl.sh
	$(BUILD) openssl

$(OUTDIR)/ncurses-macos.tar: $(HERE)/build-ncurses.sh
	$(BUILD) ncurses

$(OUTDIR)/sqlite-macos.tar: $(HERE)/build-sqlite.sh
	$(BUILD) sqlite

$(OUTDIR)/uuid-macos.tar: $(HERE)/build-uuid.sh
	$(BUILD) uuid

$(OUTDIR)/xz-macos.tar: $(HERE)/build-xz.sh
	$(BUILD) xz

$(OUTDIR)/zlib-macos.tar: $(HERE)/build-zlib.sh
	$(BUILD) zlib

PYTHON_DEPENDS := \
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
