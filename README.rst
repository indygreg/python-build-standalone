========================
Python Standalone Builds
========================

This project produces self-contained, highly-portable Python
distributions. These Python distributions contain a fully-usable,
full-featured Python installation as well as their build artifacts
(object files, libraries, etc).

The included build artifacts can be recombined by downstream
repackagers to derive a custom Python distribution, possibly without
certain features like SQLite and OpenSSL. This is useful for
embedding Python in a larger binary, where a full Python is
often not needed and where interfacing with the Python C API
is desirable. (See the
`PyOxidizer <https://github.com/indygreg/PyOxidizer>`_ sister project
for such a downstream repackager.)

The Python distributions are built in a manner to minimize
run-time dependencies. This includes limiting the CPU instructions
that can be used and limiting the set of shared libraries required
at run-time. The goal is for the produced distribution to work on
any system for the targeted architecture.

Project Status
==============

The project can be considered beta quality. It is still under active
development.

There is support for producing 64-bit CPython distributions for Windows,
macOS, and Linux. All distributions are highly self-contained and have
limited shared library dependencies. Static linking is used aggressively.

Planned and features include:

* Static/dynamic linking toggles for dependencies
* Support for configuring which toolchain/version to use
* Support for BSDs
* Support for iOS and/or Android
* Support for Windows 32-bit
* Support for Python distributions that aren't CPython

Instructions
============

To build a Python distribution for Linux x64::

    $ ./build-linux.py
    # With profile-guided optimizations (generated code should be faster):
    $ ./build-linux.py --optimized

You can also build another version of Python. e.g.::

    $ ./build-linux.py --python cpython-3.8

To build a Python distribution for Linux x64 using musl libc::

    $ ./build-linux.py --musl --libressl

To build a Python distribution for macOS::

    $ ./build-macos.py

To build a Python distribution for Windows x64::

   # From a Visual Studio 2017 x64 native tools command prompt:
   $ py.exe build-windows.py

It is also possible to build a more traditional dynamically linked
distribution, optionally with PGO optimizations::

   $ py.exe build-windows.py --profile shared
   $ py.exe build-windows.py --profile shared-pgo

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

macOS SDK headers must be installed. Try running ``xcode-select --install``
to install them if you see errors about e.g. ``stdio.h`` not being found.
Verify they are installed by running ``xcrun --show-sdk-path``. It
should print something like
``/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk``
on modern versions of macOS.

Windows
-------

Visual Studio 2017 (or later) is required. A compatible Windows SDK is required
(10.0.17763.0 as per CPython 3.7.2).

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

Runtime Requirements
====================

Linux
-----

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

If built with MUSL, no shared library dependencies exist and the binaries
should *just work* on practically any Linux system.

Windows
-------

Windows binaries have a dependency on the Microsoft Visual C++ Redistributable,
likely from MSVC 2015 (``vcruntime140.dll``). This dependency is not
provided in the distribution and will need to be provided by downstream
distributors.

Licensing
=========

Python and its various dependencies are governed by varied software use
licenses. This impacts the rights and requirements of downstream consumers.

Most licenses are fairly permissive. Notable exceptions to this are GDBM and
readline, which are both licensed under GPL Version 3.

**It is important to understand the licensing requirements when integrating
the output of this project into derived works.** To help with this, the
JSON document describing the Python distribution contains licensing metadata
and the archive contains copies of license texts.

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

On Linux, we statically link a ``libedit`` we compile ourselves, which
is compiled against a ``libncurses`` we build ourselves.

OpenSSL / LibreSSL
------------------

By default we compile with OpenSSL. We have some support for compiling
against LibreSSL.

LibreSSL is currently required for musl libc builds because
https://github.com/openssl/openssl/commit/38023b87f037f4b832c236dfce2a76272be08763
broke OpenSSL in our build environment. Projects like Alpine Linux appear
to still be able to build OpenSSL 1.1.1c. It requires certain headers
to be in place though. When we tried to work around this, it turned out to
be easier to compile with LibreSSL than with OpenSSL.

Distribution Format
===================

The output of a build is referred to as a Python *distribution*.

A distribution is a zstandard-compressed tar file. All paths inside the
tar archive are prefixed with ``python/``. Within the ``python/`` directory
are the following well-known paths:

PYTHON.json
   Machine readable file describing this Python distribution.

   See the ``PYTHON.json File`` section for the format of this file.

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
without having to resort to heuristics.

The file contains a JSON map. This map has the following keys:

version
   Version number of the file format. Currently ``5``.

os
   Target operating system for the distribution. e.g. ``linux``, ``macos``,
   or ``windows``.

arch
   Target architecture for the distribution. e.g. ``x86`` (32-bit) or
   ``x86_64`` (64-bit).

python_tag
   The PEP 425 *Python Tag* value. e.g. ``cp38``.

   (Version 5 or above only.)

python_abi_tag
   The PEP 425 *ABI Tag* value. e.g. ``cp37m``.

   (Version 5 or above only.)

python_platform_tag
   The PEP 425 *Platform Tag* value. e.g. ``linux_x86_64``.

   (Version 5 or above only.)

python_flavor
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

python_stdlib_test_packages
   Array of strings of Python packages that define tests. (Version 4 or above
   only.)

link_mode
   How `libpython` is linked. Values can be one of the following:

   `static`
      Statically linked.

   `shared`
      Dynamically linked. (A `libpythonXY` shared library will be part
      of the distribution.)

   (Version 4 or above only.)

build_info
   A map describing build configuration and artifacts for this distribution.

   See the ``build_info Data`` section below.

licenses
   Array of strings containing the license shortname identifiers from the
   SPDX license list (https://spdx.org/licenses/) for the Python distribution.

  (Version 2 or above only.)

license_path
   Path to a text file containing the license for this Python distribution.

   (Version 2 or above only.)

tcl_library_path
   Relative path to location of tcl library files. The path should be a
   directory tree containing tcl files to support the tkinter extension.
   This will include a subset of the library files provided by the tcl, tk,
   and tix packages.

   (Version 3 or above only.)

build_info Data
---------------

The ``build_info`` key in the ``PYTHON.json`` file describes build artifacts
in the Python distribution. The primary goal of the data is to give downstream
distribution consumers enough details to integrate build artifacts into their
own build systems. This includes the ability to produce a Python binary with a
custom set of built-in extension modules.

This map has the following keys:

core
   A map describing the core Python distribution (essentially `libpython`).

   objs
      An array of paths to object files constituting the Python core distribution.

      Core object files are typically object files that are linked together to
      create libpython.

   links
      An array of linking requirement maps. (See below for data format.)

   shared_lib
      Path to a shared library representing `libpython`. May not be defined.
      (Version 4 or above only.)

   static_lib
      Path to a static library representing `libpython`. May not be defined.
      (Version 4 or above only.)

extensions
   A map of extension names to an array of maps describing candidate extensions.

   Extensions are non-core/non-essential parts of the Python distribution that
   are frequently built as standalone entities.

   Names in this map denote the name of the extension module.

   Values are arrays of maps. Each map represents a potential candidate
   providing the extension. There is frequently only a single extension
   candidate. Multiple candidates can occur if there are e.g. varying
   libraries an extension can be linked against to supply underlying
   functionality.

   Each map has the following keys:

   in_core
      Boolean indicating if this extension is defined by the core distribution.

      If true, object files should be in the ``['core']['objs']`` array, not the
      ``objs`` array in this map.

      Downstream consumers should key off this value to determine how to
      assemble this extension's code into a new distribution.

      This field was introduced to support Windows, where CPython's Visual
      Studio project files define various extensions as part of the project
      providing libpython. This is in contrast to make-based builds, where
      the ``Modules/Setup.*`` files treat each extension as separate entities.

   init_fn
      The name of the extension module initialization function for this
      extension.

      The string value may be ``NULL``, which may need special handling by
      consumers.

   licenses
      Array of strings containing the license shortname identifiers from the
      SPDX license list (https://spdx.org/licenses/).

      If this field is missing, licenses are unknown. Empty array denotes no known
      licenses.

      The license applies to additional libraries needed by this extension, not
      the extension itself, as extensions should be licensed the same as the
      Python distribution.

      (Version 2 or above only.)

   license_path
      Paths to text files containing the licenses for this extension.

      (Version 2 or above only.)

   license_public_domain
      Bool indicating that the license for the extension is in the public
      domain.

      There is no SPDX identifier for public domain. And we want to be explicit
      about something being in the public domain because of the legal implications.

      (Version 2 or above only.)

   links
      An array of linking requirement maps. (See below for data format.)

   objs
      An array of paths to object files constituting this extension module.

   required
      Boolean indicating if this extension is required to initialize the Python
      interpreter.

   shared_lib
      The path to a shared library defining this extension module. May not
      be defined. (Version 4 or above only.)

   static_lib
      The path to a static library defining this extension module. May not
      be defined.

   variant
      String describing this extension variant. Downstream consumers can key off
      this value to choose an appropriate extension variant when there are
      multiple options.

Each entry in a ``links`` array is a map with the following keys:

name
   Name of the library being linked against.

path_static
   Path to the static version of this library, if available in the
   distribution.

path_dynamic
   Path to the dynamic version of this library, if available in the
   distribution.

framework
   Denotes that the link target is a macOS framework.

system
   Denotes that the link target is a system library.

   System libraries are typically passed into the linker by name only and
   found using default library search paths.
