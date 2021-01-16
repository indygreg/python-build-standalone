.. _quirks:

===============
Behavior Quirks
===============

.. _quirk_shebangs:

Bad Shebangs in Python Scripts
==============================

Various Python scripts under ``install/bin/`` (e.g. ``pip``) have
shebangs looking like ``#!/build/out/python/install/bin/python3``.
This ``/build/out/`` directory is where the distribution is built
from. Python is writing out shebangs for Python scripts with
that absolute path.

To work around this issue, you can mass rewrite the shebangs to
point the directory where the distribution is extracted/installed
to. Here is a sample shell one-liner to get you started::

   $ find install/bin/ -type f -exec sed -i '1 s/^#!.*python.*/#!.\/python3/' {} \;

Alternatively, you can sometimes execute ``python3 -m <module>``
to get equivalent functionality to what the installed script would
do. e.g. to run pip, ``python3 -m pip ...``.

.. _quirk_backspace_key:

Backscape Key Doesn't work in Python REPL
=========================================

If you attempt to run ``python`` and the backspace key doesn't
erase characters or the arrow keys don't work as expected, this
is because the executable can't find the *terminfo database*.

When you type a special key like the backspace key, this is
registered as a key press. There is special software (typically
``readline`` or ``libedit``) that most interactive programs use
that intercepts these special key presses and converts them into
special behavior, such as moving the cursor back instead of
forward. But because computer environments are different,
there needs to be some definition of how these special
behaviors are performed. This is the *terminfo database*.

When ``readline`` and ``libedit`` are compiled, there is
typically a hard-coded set of search locations for the
*terminfo database* baked into the built library. And when
you build a program (like Python) locally, you link against
``readline`` or ``libedit`` and get these default locations
*for free*.

Because python-build-standalone Python distributions compile
and use their own version of ``readline``/``libedit`` and
because the build environment is different from your
machine, the default search locations for the *terminfo
database* built into binaries distributed with this project
may point to a path that doesn't exist. The *terminfo database*
cannot be located and ``readline``/``libedit`` do not know
how to convert special key presses to special behavior.

The solution to this is to set an environment variable
with the location of the *terminfo database*.

If running a Debian based Linux distribution (including Ubuntu)::

   $ TERMINFO_DIRS=/etc/terminfo:/lib/terminfo:/usr/share/terminfo

If running a RedHat based Linux distribution::

   $ TERMINFO_DIRS=/etc/terminfo:/usr/share/terminfo

If running macOS::

   $ TERMINFO_DIRS=/usr/share/terminfo

e.g.::

   $ TERMINFO_DIRS=/etc/terminfo:/lib/terminfo:/usr/share/terminfo install/bin/python3.9

The macOS distributions built with this project should automatically
use the terminfo database in ``/usr/share/terminfo``. Please file
a bug report if the macOS distributions do not behave as expected.

.. _quirk_tcl:

Tcl/tk Support Files
====================

Python functionality using tcl/tk (such as the ``tkinter`` or ``turtle``
modules) requires loading ``.tcl`` support files from the filesystem.
If these support files cannot be found, you'll get an error like
``_tkinter.TclError: Can't find a usable init.tcl in the following
directories:``.

Distributions produced from this project contain tcl/tk support files.
The paths to these files in the extracted distribution are advertised
in the ``PYTHON.json`` file.

When tcl is initialized by Python, Python and tcl attempt to locate the
``.tcl`` support files. If the ``tcl<X.Y>/init.tcl`` file cannot be found,
an error occurs.

But the mechanism for finding the ``.tcl`` files varies by platform.

On all platforms, if the ``TCL_LIBRARY`` environment variable is set,
it will be used to locate the ``.tcl`` support files. This environment
variable is processed by tcl itself and is documented at
https://wiki.tcl-lang.org/page/TCL_LIBRARY.

On Windows, CPython will attempt to locate the ``.tcl`` support files in
well-defined directories. The C code performs the equivalent of the
following:

.. code-block:: python

   import os
   import sys

   def get_tcl_path():
       # e.g. sys.prefix/tcl/tcl8.6
       p = os.path.join(sys.prefix, "tcl", "tcl<X.Y>")
       if os.path.exists(p):
           return p

       return None

If Python's code can find the support files in the well-defined location,
it calls into the tcl C API and defines the ``tcl_library`` variable to the
found path.

The most robust way to ensure Python/tcl can find the ``.tcl`` support files
is to define ``TCL_LIBRARY`` to the path to the ``.tcl`` files present in
the extracted Python distribution. It is possible to define this environment
variable from within Python. But it must be done before running any Python
code in the ``tkinter`` module. The following example should work on Linux
and macOS distributions:

.. code-block:: python

   import os
   import sys

   os.environ["TCL_LIBRARY"] = os.path.join(os.path.dirname(sys.executable), "..", "lib", "tcl8.6")

   import turtle

If you don't set ``TCL_LIBRARY`` on Linux and macOS, the default search
mechanics implemented by Tcl are used. These may pick up ``.tcl`` files from
a location outside the Python distribution. This may *just work*. This may
fail fast. Or it could result in undefined behavior. For best results,
forcefully point Tcl at the ``.tcl`` files from the Python distribution
produced by this project.

On Windows, explicitly setting ``TCL_LIBRARY`` is not required as the
default install layout of this project's Python distributions allows CPython's
filesystem probing code to find the ``.tcl`` files. As long as the
files from ``python/install/tcl`` are present (in a ``tcl`` directory
under the directory where the ``python.exe`` is), things should *just work*.

For reference, PyOxidizer's approach to this problem is to copy all the
``.tcl`` files from the Python distribution into an install location. At
run time, the ``TCL_LIBRARY`` environment variable is set from within
the process before the Python interpreter is initialized. This ensures the
``.tcl`` files from the Python distribution are used.

.. _quirk_macos_linking:

Linking Static Library on macOS
===============================

Python 3.9+ makes use of the ``__builtin_available()`` compiler feature.
This functionality requires a symbol from ``libclang_rt``, which may not
be linked by default. Failure to link against ``libclang_rt`` could result
in a linker error due to an undefined symbol ``___isOSVersionAtLeast``.

To work around this linker failure, link against the static library
``libclang_rt.<platform>.a`` present in the Clang installation. e.g.
``libclang_rt.osx.a``. You can find this library by invoking
``clang --print-search-dirs`` and looking in the ``lib/darwin`` directory
under the printed ``libraries`` directory. An example path is
``/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/clang/12.0.0/lib/darwin/libclang_rt.osx.a``.

A copy of the ``libclang_rt.<platform>.a`` from the Clang used to build
the distribution is included in the archive. However, it isn't annotated
in ``PYTHON.json`` because we're unsure if using the file with another
build/version of Clang is supported. Use at your own risk.

See https://jonnyzzz.com/blog/2018/06/05/link-error-2/ and
https://jonnyzzz.com/blog/2018/06/13/link-error-3/ for more on this topic.
