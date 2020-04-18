.. _technotes:

===============
Technical Notes
===============

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
===================

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

Upgrading CPython
=================

This section documents some of the work that needs to be performed
when upgrading CPython major versions.

Review Release Notes
--------------------

CPython's release notes often have a section on build system changes.
e.g. https://docs.python.org/3/whatsnew/3.8.html#build-and-c-api-changes.
These are a must review.

``Modules/Setup``
-----------------

The ``Modules/Setup`` file defines the default extension build settings
for *boring* extensions which are always compiled the same way.

We need to audit it for differences such as added/removed extensions,
changes to compile settings, etc just in case we have special code
handling an extension defined in this file.

See code in ``cpython.py`` dealing with this file.

``setup.py`` / ``static-modules``
---------------------------------

The ``setup.py`` script in the Python source distribution defines
logic for dynamically building C extensions depending on environment
settings.

Because we don't like what this file does by default in many cases,
we have instead defined static compilation invocations for various
extensions in ``static-modules.*`` files. Presence of an extension
in this file overrides CPython's ``setup.py`` logic. Essentially what
we've done is encoded what ``setup.py`` would have done into our
``static-modules.*`` files, bypassing ``setup.py``.

This means that we need to audit ``setup.py`` every time we perform
an upgrade to see if we need to adjust the content of our
``static-modules.*`` files.

A telltale way to find added extension is to look for ``.so`` files
in ``python/install/lib/pythonX.Y/lib-dynload``. If an extension
exists in a static build, it is being built by ``setup.py`` and
we may be missing an entry in our ``static-modules.*`` files.

The most robust method to audit changes is to run a build of CPython
out of a source checkout and then manually compare the compiler
invocations for each extension against what exists in our
``static-modules.*`` files. Differences like missing source files
should be obvious, as they usually result in a compilation failure.
But differences in preprocessor defines are more subtle and can
sneak in if we aren't careful.
