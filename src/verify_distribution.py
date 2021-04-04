# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

TERMINFO_DIRS = [
    "/etc/terminfo",
    "/lib/terminfo",
    "/usr/share/terminfo",
]


def verify():
    """Verifies that a built Python distribution behaves as expected."""
    import sys

    sys.dont_write_bytecode = True

    import os

    here = os.path.dirname(sys.executable)
    install_root = os.path.dirname(here)

    # Need to set TCL_LIBRARY so local tcl/tk files get picked up.
    os.environ["TCL_LIBRARY"] = os.path.join(install_root, "lib", "tcl", "tcl")

    # Need to set TERMINFO_DIRS so terminfo database can be located.
    if "TERMINFO_DIRS" not in os.environ:
        terminfo_dirs = [p for p in TERMINFO_DIRS if os.path.exists(p)]
        if terminfo_dirs:
            os.environ["TERMINFO_DIRS"] = ":".join(terminfo_dirs)

    verify_compression()
    verify_ctypes()
    verify_curses()
    verify_hashlib()
    verify_sqlite()
    verify_ssl()
    verify_tkinter()


def verify_compression():
    import bz2, lzma, zlib

    assert lzma.is_check_supported(lzma.CHECK_CRC64)
    assert lzma.is_check_supported(lzma.CHECK_SHA256)


def verify_ctypes():
    import ctypes

    assert ctypes.pythonapi is not None

    # https://bugs.python.org/issue42688
    @ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p)
    def error_handler(fif, message):
        pass


def verify_curses():
    import curses

    curses.initscr()
    curses.endwin()


def verify_hashlib():
    import hashlib

    wanted_hashes = {
        "blake2b",
        "blake2s",
        "md4",
        "md5",
        "md5-sha1",
        "mdc2",
        "ripemd160",
        "sha1",
        "sha224",
        "sha256",
        "sha3_224",
        "sha3_256",
        "sha3_384",
        "sha3_512",
        "sha384",
        "sha3_224",
        "sha3_256",
        "sha3_384",
        "sha3_512",
        "sha512",
        "sha512_224",
        "sha512_256",
        "shake_128",
        "shake_256",
        "shake_128",
        "shake_256",
        "sm3",
        "whirlpool",
    }

    missing_hashes = wanted_hashes - hashlib.algorithms_available

    assert not missing_hashes, "missing hashes: %s" % missing_hashes


def verify_sqlite():
    import sqlite3

    assert sqlite3.sqlite_version_info == (3, 35, 4), "got %r" % (
        sqlite3.sqlite_version_info,
    )


def verify_ssl():
    import ssl

    assert ssl.HAS_TLSv1
    assert ssl.HAS_TLSv1_1
    assert ssl.HAS_TLSv1_2
    assert ssl.HAS_TLSv1_3

    assert ssl.OPENSSL_VERSION_INFO == (1, 1, 1, 11, 15), "got %r" % (
        ssl.OPENSSL_VERSION_INFO,
    )

    context = ssl.create_default_context()


def verify_tkinter():
    import tkinter as tk

    class Application(tk.Frame):
        def __init__(self, master=None):
            super().__init__(master)
            self.master = master
            self.pack()

            self.hi_there = tk.Button(self)
            self.hi_there["text"] = "Hello World\n(click me)"
            self.hi_there["command"] = self.say_hi
            self.hi_there.pack(side="top")

            self.quit = tk.Button(
                self, text="QUIT", fg="red", command=self.master.destroy
            )
            self.quit.pack(side="bottom")

        def say_hi(self):
            print("hi there, everyone!")

    root = tk.Tk()
    Application(master=root)


if __name__ == "__main__":
    verify()
