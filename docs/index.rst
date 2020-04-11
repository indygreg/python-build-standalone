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

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   building.rst
   running.rst
   technotes.rst
   distributions.rst
   status.rst

Indices and tables
==================

* :ref:`genindex`
* :ref:`search`
