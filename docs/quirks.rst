.. _quirks:

===============
Behavior Quirks
===============

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
