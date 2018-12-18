This project builds CPython for Linux in a mostly deterministic and
reproducible manner. The resulting Python build is mostly self-contained
and the binaries are capable of running on many Linux distributions.

The produced binaries perform minimal loading of shared libraries.
The required shared libraries are:

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

These shared libraries should be present on most modern Linux distros.
