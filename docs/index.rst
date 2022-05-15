Python Standalone Builds
========================

This project produces self-contained, highly-portable Python
distributions. These Python distributions contain a fully-usable,
full-featured Python installation: most extension modules from
the Python standard library are present and their library
dependencies are either distributed with the distribution or
are statically linked.

The Python distributions are built in a manner to minimize
run-time dependencies. This includes limiting the CPU instructions
that can be used and limiting the set of shared libraries required
at run-time. The goal is for the produced distribution to work on
any system for the targeted architecture.

Some distributions ship with their build artifacts (object files,
libraries, etc) along with rich metadata describing the distribution
and how it was assembled. The build artifacts can be recombined by
downstream repackagers to derive a custom Python distribution, possibly
without certain features like SQLite and OpenSSL. This is useful for
embedding Python in a larger binary. See the
`PyOxidizer <https://github.com/indygreg/PyOxidizer>`_ sister project
for such a downstream repackager.

Many users of these distributions might be better served by the
`PyOxy <https://pyoxidizer.readthedocs.io/en/latest/pyoxy.html>`_
sister project. PyOxy takes these Python distributions and adds some
Rust code for enhancing the functionality of the Python interpreter.
The official PyOxy release binaries are single file executables providing
a full-featured Python interpreter.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   running
   building
   quirks
   technotes
   distributions
   status

Indices and tables
==================

* :ref:`genindex`
* :ref:`search`
