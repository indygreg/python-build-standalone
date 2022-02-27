.. _running:

=====================
Running Distributions
=====================

Obtaining Distributions
=======================

Pre-built distributions are published as releases on GitHub at
https://github.com/indygreg/python-build-standalone/releases.
Simply go to that page and find the latest release along with
its release notes.

Published distributions vary by their:

* Python version
* Target machine architecture
* Build configuration
* Archive flavor

The Python version is hopefully pretty obvious.

The target machine architecture defines the CPU type and operating
system the distribution runs on. We use LLVM target triples.

The build configuration denotes how Python and its dependencies were built.
Common configurations include:

``pgo+lto``
   Profile guided optimization and link-time optimization. These should be
   the fastest distributions since they have the most build-time
   optimizations.

``pgo``
   Profile guided optimization.

``lto``
   Link-time optimization.

``noopt``
   A regular optimized build without PGO or LTO.

``debug``
   A debug build. No optimizations.

The archive flavor denotes the content in the archive. See
:ref:`distributions` for more. Casual users will likely want to use the
``install_only`` archive, as most users do not need the build artifacts
present in the ``full`` archive.

Extracting Distributions
========================

Distributions are defined as zstandard or gzip compressed tarballs.

Modern versions of ``tar`` support zstandard and you can extract
like any normal archive::

   $ tar -axvf path/to/distribution.tar.zstd

(The ``-a`` argument tells tar to guess the compression format by
the file extension.)

If you do not have ``tar``, you can install and use the ``zstd``
tool (typically available via a ``zstd`` or ``zstandard`` system
package)::

   $ zstd -d path/to/distribution.tar.zstd
   $ tar -xvf path/to/distribution.tar

If you want to extract the distribution with Python, use the
``zstandard`` Python package:

.. code-block:: python

   import tarfile
   import zstandard

   with open("path/to/distribution.tar.zstd", "rb") as ifh:
       dctx = zstandard.ZstdDecompressor()
       with dctx.stream_reader(ifh) as reader:
           with tarfile.open(mode="r|", fileobj=reader) as tf:
               tf.extractall("path/to/output/directory")

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
* libcrypt.so.1 (required by crypt extension)
* libm.so.6
* libc.so.6
* ld-linux-x86-64.so.2

The minimum glibc version required is 2.17. This should make binaries
compatible with the following Linux distributions:

* Fedora 21+
* RHEL/CentOS 7+
* openSUSE 13.2+
* Debian 8+ (Jessie)
* Ubuntu 14.04+

If built with MUSL, no shared library dependencies nor glibc version
requirements exist and the binaries should *just work* on practically any
Linux system.

Windows
-------

Windows distributions model the requirements of the official Python
distributions:

* Windows 7 or Windows Server 2012 or newer on Python 3.8.
* Windows 8 or Windows Server 2012 or newer on Python 3.9+.

Windows binaries have a dependency on the Microsoft Visual C++ Redistributable,
likely from MSVC 2015 (``vcruntime140.dll``). This dependency is not
provided in the distribution and will need to be provided by downstream
distributors.

Licensing
=========

Python and its various dependencies are governed by varied software use
licenses. This impacts the rights and requirements of downstream consumers.

Most licenses are fairly permissive. Notable exceptions to this are GDBM and
readline, which are both licensed under GPL Version 3. Python 3.10 and
newer distributions do not link against GDBM and readline and are not
GPL encumbered. Older Python distributions may link against these libraries
and may be subject to the GPL.

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
