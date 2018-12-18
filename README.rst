========================
Python Standalone Builds
========================

This project contains code for building Python distributions that are
self-contained and highly portable (the binaries can be executed
on most target machines).

The intended audience of this project are people wanting to produce
applications that embed Python in a larger executable. The artifacts
that this project produces make it easier to build highly-portable
applications containing Python.

Most consumers of this project can bypass the building of artifacts
and consume the pre-built binaries produced from it.

Project Status
==============

The project can be considered alpha quality. It is still in a heavy state
of flux.

Currently, it produces a nearly full-featured CPython distribution for
Linux that is fully statically linked with the exception of some very
common system libraries.

Planned features include:

* Support for Windows
* Support for macOS
* Static/dynamic linking toggles for dependencies

Instructions
============

To build a Python distribution for Linux x64::

    $ ./build-linux.py

Requirements
============

Linux
-----

The host system must be 64-bit. A Python 3.5+ interpreter must be
available. The execution environment must have access to a Docker
daemon (all build operations are performed in Docker containers for
isolation from the host system).

How It Works
============

The first thing the ``build-*`` scripts do is bootstrap an environment
for building Python. On Linux, a base Docker image based on a deterministic
snapshot of Debian Wheezy is created. A modern binutils and GCC are built
in this environment. That modern GCC is then used to build a modern Clang.
Clang is then used to build all of Python's dependencies (openssl, ncurses,
readline, sqlite, etc). Finally, Python itself is built.

Python is built in such a way that extensions are statically linked
against their dependencies. e.g. instead of the ``sqlite3`` Python
extension having a run-time dependency against ``libsqlite3.so``, the
SQLite symbols are statically inlined into the Python extension object
file.

From the built Python, we produce an archive containing the raw Python
distribution (as if you had run ``make install``) as well as other files
useful for downstream consumers.

Setup.local Hackery
-------------------

Python's build system reads the ``Modules/Setup`` and ``Modules/Setup.local``
files to influence how C extensions are built. By default, many extensions
have no entry in these files and the ``setup.py`` script performs work
to compile these extensions. (``setup.py`` looks for headers, libraries,
etc, and sets up the proper compiler flags.)

``setup.py`` doesn't provide a lot of flexibility and relies on a lot
of default behavior in ``distutils`` as well as other inline code in
``setup.py``. This default behavior is often undesirable for our
desired outcome of producing a standalone Python distribution.

Since the build environment is mostly deterministic and since we have
special requirements, we generate a custom ``Setup.local`` file that
builds C extensions in a specific manner. The undesirable behavior of
``setup.py`` is bypassed and the Python C extensions are compiled just
the way we want.

Linux Runtime Requirements
==========================

The produced Linux binaries have minimal references to shared
libraries and thus can be executed on most Linux systems.

The following shared libraries are referenced:

* linux-vdso.so.1
* libpthread.so.0
* libdl.so.2 (required by ctypes extension)
* libutil.so.1
* librt.so.1
* libnsl.so.1 (required by nis extension)
* libcrypt.so.1 (required by crypt extension)
* libm.so.6
* libc.so.6
* ld-linux-x86-64.so.2

Licensing
=========

Python and its various dependencies are governed by varied software use
licenses. This impacts the rights and requirements of downstream consumers.

The ``python-licenses.rst`` file contained in this repository and produced
artifacts summarizes the licenses of various components.

Most licenses are fairly permissive. Notable exceptions to this are GDBM and
readline, which are both licensed under GPL Version 3.

**It is important to understand the licensing requirements when integrating
the output of this project into derived works.**
