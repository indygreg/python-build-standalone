.. _quirks:

===============
Behavior Quirks
===============

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
point to a path that doesn't exist. The *terminfo database*
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

   $ TERMINFO_DIRS=/etc/terminfo:/lib/terminfo:/usr/share/terminfo install/bin/python3.7

``_tkinter.TclError: Can't find a usable init.tcl``
===================================================

You may see the aforementioned error when running Python
code like ``import tkinter; tkinter.Tk()``.

What's happening here is that tk code can't locate a tcl file
needed to initialize it.

Python's ``tkinter`` module is a bit funky in that it doesn't
try very hard to find this support code on all platform. It
has code for locating the files from a relative directory
on Windows. But nothing on other platforms. Instead, Python assumes
that the defaults paths compiled into tcl/tk are proper.

Since python-build-standalone builds its own tcl/tk packages
and the build configuration is likely different from your
machine, the search paths for tcl resources compiled into
the python-build-standalone binaries likely point to nowhere
on your machine.

You can work around this problem by setting the ``TCL_LIBRARY``
environment variable to the location of the missing tcl resources.
e.g.::

   $ TCL_LIBRARY=`pwd`/install/lib/tcl8.6 install/bin/python3
