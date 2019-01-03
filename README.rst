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
* Static/dynamic linking toggles for dependencies
* Support for configuring which toolchain/version to use

Instructions
============

To build a Python distribution for Linux x64::

    $ ./build-linux.py

To build a Python distribution for macOS::

    $ ./build-macos.py

To build a Python distribution for Windows x64::

   # Install ActivePerl
   # From a Visual Studio 2017 x64 native tools command prompt:
   $ set PERL=c:\path\to\activeperl\bin\perl.exe
   $ py.exe build-windows.py

Requirements
============

Linux
-----

The host system must be 64-bit. A Python 3.5+ interpreter must be
available. The execution environment must have access to a Docker
daemon (all build operations are performed in Docker containers for
isolation from the host system).

macOS
-----

The XCode command line tools must be installed. A Python 3 interpreter
is required to execute the build. ``/usr/bin/clang`` must exist.

macOS SDK headers must be installed in ``/usr/include`` in order to work
with the Clang toolchain that is built. If ``/usr/include`` does not
exist, try running the installer. e.g.::

    open /Library/Developer/CommandLineTools/Packages/macOS_SDK_headers_for_macOS_10.14.pkg

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

Reconsuming Build Artifacts
===========================

Produced Python distributions contain object files and libraries for the
built Python and its dependencies. It is possible for downstream consumers
to take these build artifacts and link them into a new binary.

Reconsuming the build artifacts this way can be a bit fragile due to
incompatibilities between the host that generated them and the target that
is consuming them.

To ensure optimal compatibility, it is highly recommended to use the same
toolchain for all operations.

This is often harder than it sounds. For example, if these build artifacts
were to be combined into a Rust binary, the version of LLVM that the Rust
compiler itself was built against can matter. As a concrete example, the
Rust 1.31 compiler will produce LLVM intrinsics that vary from intrinsics
that would be produced with LLVM/Clang 7. At linking time, you would get
errors like the following::

    Intrinsic has incorrect argument type!
    void (i8*, i8, i64, i1)* @llvm.memset.p0i8.i64

In the future, we will allow configuring the toolchain used so it can match
requirements of downstream consumers. For the moment, we hard-code the toolchain
version.

Dependency Notes
================

DBM
---

Python has the option of building its ``_dbm`` extension against
NDBM, GDBM, and Berkeley DB. Both NDBM and GDBM are GNU GPL Version 3.
Modern versions of Berkeley DB are GNU AGPL v3. Versions 6.0.19 and
older are licensed under the Sleepycat License. The Sleepycat License
is more permissive. So we build the ``_dbm`` extension against BDB
6.0.19.

readline / libedit / ncurses
----------------------------

Python has the option of building its ``readline`` extension against
either ``libreadline`` or ``libedit``. ``libreadline`` is licensed GNU
GPL Version 3 and ``libedit`` has a more permissive license. We choose
to link against ``libedit`` because of the more permissive license.

``libedit``/``libreadline`` link against a curses library, most likely
``ncurses``. And ``ncurses`` has tie-ins with a terminal database. This
is a thorny situation, as terminal databases can be difficult to
distribute because end-users often want software to respect their
terminal databases. But for that to work, ``ncurses`` needs to be compiled
in a way that respects the user's environment.

On macOS, we statically link a ``libedit`` we compile ourselves. We
dynamically link against ``libncurses``, which is provided by the
system, typically in ``/usr/lib``.

Distribution Format
===================

The output of a build is referred to as a Python *distribution*.

A distribution is a zstandard-compressed tar file. All paths inside the
tar archive are prefixed with ``python/``. Within the ``python/`` directory
are the following well-known paths:

PYTHON.json
   Machine readable file describing this Python distribution.

   See the ``PYTHON.json File`` section for the format of this file.

LICENSE.rst
   Contains license information of software contained in the distribution.

By convention, the ``build/`` directory contains artifacts from building
this distribution (object files, libraries, etc) and the ``install/`` directory
contains a working, self-contained Python installation of this distribution.
The ``PYTHON.json`` file should be read to determine where specific entities
are located within the archive.

PYTHON.json File
----------------

The ``PYTHON.json`` file describes the Python distribution in a machine
readable manner. This file is meant to be opened by downstream consumers
of this distribution so that they may learn things about the distribution
without have to resort to heuristics.

The file contains a JSON map. This map has the following keys:

version
   Version number of the file format. Currently ``0`` until semantics are
   stabilized.

os
   Target operating system for the distribution. e.g. ``linux``, ``macos``,
   or ``windows``.

arch
   Target architecture for the distribution. e.g. ``x86`` (32-bit) or
   ``x86_64`` (64-bit).

python_favor
   Type of Python distribution. e.g. ``cpython``.

python_version
   Version of Python being distribution. e.g. ``3.7.2``.

python_exe
   Relative path to main Python interpreter executable.

python_include
   Relative path to include path for Python headers. If this path is on
   the compiler's include path, ``#include <Python.h>`` should work.

python_stdlib
   Relative path to Python's standard library (where ``.py`` and resource
   files are located).

build_info
   A map describing build configuration and artifacts for this distribution.

   See the ``build_info Data`` section below.

build_info Data
---------------

The ``build_info`` key in the ``PYTHON.json`` file describes build artifacts
in the Python distribution. The primary goal of the data is to give downstream
distribution consumers enough details to integrate build artifacts into their
own build systems. This includes the ability to produce a Python binary with a
custom set of built-in extension modules.

This map has the following keys:

core
   A map describing the core Python distribution (essentially libpython).

   objs
      An array of paths to object files constituting the Python core distribution.

      Core object files are typically object files that are linked together to
      create libpython.

   system_lib_depends
      An array of extra system libraries this library depends on.

extensions
   A map of extension names to a map describing the extension.

   Extensions are non-core/non-essential parts of the Python distribution that
   are frequently built as standalone entities.

   Names in this map denote the name of the extension module.

   Values are maps with the following keys:

   builtin
      Boolean indicating if this extension is built-in to libpython. If true,
      the extension is baked into the core distribution / object files. If
      false, the extension is distributed as a standalone, loadable library.

   init_fn
      The name of the extension module initialization function for this
      extension.

      The string value may be ``NULL``, which may need special handling by
      consumers.

   objs
      An array of paths to object files constituting this extension module.

   static_lib
      The path to a static library defining this extension module.

   system_lib_depends
      An array of extra system libraries this extension depends on.

links
   A map describing additional linking information needed for this distribution.

   Some core distributions and extensions may require linking against additional
   libraries. This map describes those requirements.

   This map has the following keys:

   core
      An array of link requirement maps.

   extensions
      A map of extension name to an array of link requirement maps.

   Each entry in the link array is a map with the following keys:

   name
      Name of the library being linked against.

   path_static
      Path to the static version of this library, if available in the
      distribution.

   path_dynamic
      Path to the dynamic version of this library, if available in the
      distribution.
