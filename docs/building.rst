.. _building:

========
Building
========

Linux
=====

The host system must be 64-bit. A Python 3.5+ interpreter must be
available. The execution environment must have access to a Docker
daemon (all build operations are performed in Docker containers for
isolation from the host system).

To build a Python distribution for Linux x64::

    $ ./build-linux.py
    # With profile-guided optimizations (generated code should be faster):
    $ ./build-linux.py --optimizations pgo
    # Produce a debug build.
    $ ./build-linux.py --optimizations debug

You can also build another version of Python. e.g.::

    $ ./build-linux.py --python cpython-3.8

To build a Python distribution for Linux x64 using musl libc::

    $ ./build-linux.py --target x86_64-unknown-linux-musl

macOS
=====

The XCode command line tools must be installed. A Python 3 interpreter
is required to execute the build. ``/usr/bin/clang`` must exist.

macOS SDK headers must be installed. Try running ``xcode-select --install``
to install them if you see errors about e.g. ``stdio.h`` not being found.
Verify they are installed by running ``xcrun --show-sdk-path``. It
should print something like
``/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk``
on modern versions of macOS.

To build a Python distribution for macOS::

    $ ./build-macos.py

macOS uses the same build code as Linux, just without Docker.
So similar build configuration options are available.

Windows
=======

Visual Studio 2017 (or later) is required. A compatible Windows SDK is required
(10.0.17763.0 as per CPython 3.7.2).

If building CPython 3.8+, there are the following additional requirements:

* A ``git.exe`` on ``PATH`` (to clone ``libffi`` from source).
* An installation of Cywgin with the ``autoconf``, ``automake``, ``libtool``,
  and ``make`` packages installed. (``libffi`` build dependency.)

To build a Python distribution for Windows x64::

   # From a Visual Studio 2017/2019 x64 native tools command prompt:
   $ py.exe build-windows.py --profile static

It is also possible to build a more traditional dynamically linked
distribution, optionally with PGO optimizations::

   $ py.exe build-windows.py --profile shared
   $ py.exe build-windows.py --profile shared-pgo

If building CPython 3.8+, you will need to specify the path to a
``sh.exe`` installed from cygwin. e.g.

   $ py.exe build-windows.py --python cpython-3.8 --sh c:\cygwin\bin\sh.exe --profile shared

To build a 32-bit x86 binary, simply use an ``x86 Native Tools
Command Prompt`` instead of ``x64``.
