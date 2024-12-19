# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

DOWNLOADS = {
    "autoconf": {
        "url": "https://ftp.gnu.org/gnu/autoconf/autoconf-2.71.tar.gz",
        "size": 2003781,
        "sha256": "431075ad0bf529ef13cb41e9042c542381103e80015686222b8a9d4abef42a1c",
        "version": "2.71",
    },
    # 6.0.19 is the last version licensed under the Sleepycat license.
    "bdb": {
        "url": "https://ftp.osuosl.org/pub/blfs/conglomeration/db/db-6.0.19.tar.gz",
        "size": 36541923,
        "sha256": "2917c28f60903908c2ca4587ded1363b812c4e830a5326aaa77c9879d13ae18e",
        "version": "6.0.19",
        "library_names": ["db"],
        "licenses": ["Sleepycat"],
        "license_file": "LICENSE.bdb.txt",
    },
    "binutils": {
        "url": "https://ftp.gnu.org/gnu/binutils/binutils-2.43.tar.xz",
        "size": 28175768,
        "sha256": "b53606f443ac8f01d1d5fc9c39497f2af322d99e14cea5c0b4b124d630379365",
        "version": "2.43",
    },
    "bzip2": {
        "url": "https://sourceware.org/pub/bzip2/bzip2-1.0.8.tar.gz",
        "size": 810029,
        "sha256": "ab5a03176ee106d3f0fa90e381da478ddae405918153cca248e682cd0c4a2269",
        "version": "1.0.8",
        "library_names": ["bz2"],
        "licenses": ["bzip2-1.0.6"],
        "license_file": "LICENSE.bzip2.txt",
    },
    "cpython-3.9": {
        "url": "https://www.python.org/ftp/python/3.9.21/Python-3.9.21.tar.xz",
        "size": 19647056,
        "sha256": "3126f59592c9b0d798584755f2bf7b081fa1ca35ce7a6fea980108d752a05bb1",
        "version": "3.9.21",
        "licenses": ["Python-2.0", "CNRI-Python"],
        "license_file": "LICENSE.cpython.txt",
        "python_tag": "cp39",
    },
    "cpython-3.10": {
        "url": "https://www.python.org/ftp/python/3.10.16/Python-3.10.16.tar.xz",
        "size": 19610392,
        "sha256": "bfb249609990220491a1b92850a07135ed0831e41738cf681d63cf01b2a8fbd1",
        "version": "3.10.16",
        "licenses": ["Python-2.0", "CNRI-Python"],
        "license_file": "LICENSE.cpython.txt",
        "python_tag": "cp310",
    },
    "cpython-3.11": {
        "url": "https://www.python.org/ftp/python/3.11.11/Python-3.11.11.tar.xz",
        "size": 20085792,
        "sha256": "2a9920c7a0cd236de33644ed980a13cbbc21058bfdc528febb6081575ed73be3",
        "version": "3.11.11",
        "licenses": ["Python-2.0", "CNRI-Python"],
        "license_file": "LICENSE.cpython.txt",
        "python_tag": "cp311",
    },
    "cpython-3.12": {
        "url": "https://www.python.org/ftp/python/3.12.8/Python-3.12.8.tar.xz",
        "size": 20489808,
        "sha256": "c909157bb25ec114e5869124cc2a9c4a4d4c1e957ca4ff553f1edc692101154e",
        "version": "3.12.8",
        "licenses": ["Python-2.0", "CNRI-Python"],
        "license_file": "LICENSE.cpython.txt",
        "python_tag": "cp312",
    },
    "cpython-3.13": {
        "url": "https://www.python.org/ftp/python/3.13.1/Python-3.13.1.tar.xz",
        "size": 22589692,
        "sha256": "9cf9427bee9e2242e3877dd0f6b641c1853ca461f39d6503ce260a59c80bf0d9",
        "version": "3.13.1",
        "licenses": ["Python-2.0", "CNRI-Python"],
        "license_file": "LICENSE.cpython.txt",
        "python_tag": "cp313",
    },
    "expat": {
        "url": "https://github.com/libexpat/libexpat/releases/download/R_2_6_3/expat-2.6.3.tar.xz",
        "size": 485600,
        "sha256": "274db254a6979bde5aad404763a704956940e465843f2a9bd9ed7af22e2c0efc",
        "version": "2.6.3",
        "library_names": ["expat"],
        "licenses": ["MIT"],
        "license_file": "LICENSE.expat.txt",
    },
    "inputproto": {
        "url": "https://www.x.org/archive/individual/proto/inputproto-2.3.2.tar.gz",
        "size": 244334,
        "sha256": "10eaadd531f38f7c92ab59ef0708ca195caf3164a75c4ed99f0c04f2913f6ef3",
        "version": "2.3.2",
    },
    "jom-windows-bin": {
        "url": "http://download.qt.io/official_releases/jom/jom_1_1_4.zip",
        "size": 1696930,
        "sha256": "d533c1ef49214229681e90196ed2094691e8c4a0a0bef0b2c901debcb562682b",
        "version": "1.1.4",
    },
    "kbproto": {
        "url": "https://www.x.org/archive/individual/proto/kbproto-1.0.7.tar.gz",
        "size": 325858,
        "sha256": "828cb275b91268b1a3ea950d5c0c5eb076c678fdf005d517411f89cc8c3bb416",
        "version": "1.0.7",
    },
    # 20221009-3.1 fails to build on musl due to an includes issue.
    "libedit": {
        "url": "https://thrysoee.dk/editline/libedit-20210910-3.1.tar.gz",
        "size": 524722,
        "sha256": "6792a6a992050762edcca28ff3318cdb7de37dccf7bc30db59fcd7017eed13c5",
        "version": "20210910-3.1",
        "library_names": ["edit"],
        "licenses": ["BSD-3-Clause"],
        "license_file": "LICENSE.libedit.txt",
    },
    "libffi-3.3": {
        "url": "https://github.com/libffi/libffi/releases/download/v3.3/libffi-3.3.tar.gz",
        "size": 1305466,
        "sha256": "72fba7922703ddfa7a028d513ac15a85c8d54c8d67f55fa5a4802885dc652056",
        "version": "3.3",
        "library_names": ["ffi"],
        "licenses": ["MIT"],
        "license_file": "LICENSE.libffi.txt",
    },
    "libffi": {
        "url": "https://github.com/libffi/libffi/releases/download/v3.4.6/libffi-3.4.6.tar.gz",
        "size": 1391684,
        "sha256": "b0dea9df23c863a7a50e825440f3ebffabd65df1497108e5d437747843895a4e",
        "version": "3.4.6",
        "library_names": ["ffi"],
        "licenses": ["MIT"],
        "license_file": "LICENSE.libffi.txt",
    },
    "libpthread-stubs": {
        "url": "https://www.x.org/archive/individual/lib/libpthread-stubs-0.5.tar.gz",
        "size": 74938,
        "sha256": "593196cc746173d1e25cb54a93a87fd749952df68699aab7e02c085530e87747",
        "version": "0.5",
    },
    "libX11": {
        "url": "https://www.x.org/archive/individual/lib/libX11-1.6.12.tar.gz",
        "size": 3168158,
        "sha256": "0fce5fc0a24a3dc728174eccd0cb8d6a1b37a2ec1654bd5628c84e5bc200d594",
        "version": "1.6.12",
        "library_names": ["X11", "X11-xcb"],
        "licenses": ["MIT", "X11"],
        "license_file": "LICENSE.libX11.txt",
    },
    "libXau": {
        "url": "https://www.x.org/releases/individual/lib/libXau-1.0.11.tar.gz",
        "size": 404973,
        "sha256": "3a321aaceb803577a4776a5efe78836eb095a9e44bbc7a465d29463e1a14f189",
        "version": "1.0.11",
        "library_names": ["Xau"],
        "licenses": ["MIT"],
        "license_file": "LICENSE.libXau.txt",
    },
    # Newer versions of libxcb require a modern Python to build. We can take this
    # dependency once we feel like doing the work.
    "libxcb": {
        "url": "https://xcb.freedesktop.org/dist/libxcb-1.14.tar.gz",
        "size": 640322,
        "sha256": "2c7fcddd1da34d9b238c9caeda20d3bd7486456fc50b3cc6567185dbd5b0ad02",
        "version": "1.14",
        "library_names": ["xcb"],
        "licenses": ["MIT"],
        "license_file": "LICENSE.libxcb.txt",
    },
    "llvm-14-x86_64-linux": {
        "url": "https://github.com/indygreg/toolchain-tools/releases/download/toolchain-bootstrap%2F20220508/llvm-14.0.3+20220508-gnu_only-x86_64-unknown-linux-gnu.tar.zst",
        "size": 158614671,
        "sha256": "04cb77c660f09df017a57738ae9635ef23a506024789f2f18da1304b45af2023",
        "version": "14.0.3+20220508",
    },
    # Remember to update LLVM_URL in src/release.rs whenever upgrading.
    "llvm-18-x86_64-linux": {
        "url": "https://github.com/indygreg/toolchain-tools/releases/download/toolchain-bootstrap%2F20240713/llvm-18.0.8+20240713-gnu_only-x86_64-unknown-linux-gnu.tar.zst",
        "size": 242840506,
        "sha256": "080c233fc7d75031b187bbfef62a4f9abc01188effb0c68fbc7dc4bc7370ee5b",
        "version": "18.0.8+20240713",
    },
    # Remember to update LLVM_URL in src/release.rs whenever upgrading.
    "llvm-aarch64-macos": {
        "url": "https://github.com/indygreg/toolchain-tools/releases/download/toolchain-bootstrap%2F20240713/llvm-18.0.8+20240713-aarch64-apple-darwin.tar.zst",
        "size": 136598617,
        "sha256": "320da8d639186e020e7d54cdc35b7a5473b36cef08fdf7b22c03b59a273ba593",
        "version": "18.0.8+20240713",
    },
    # Remember to update LLVM_URL in src/release.rs whenever upgrading.
    "llvm-x86_64-macos": {
        "url": "https://github.com/indygreg/toolchain-tools/releases/download/toolchain-bootstrap%2F20240713/llvm-18.0.8+20240713-x86_64-apple-darwin.tar.zst",
        "size": 136599290,
        "sha256": "3032161d1cadb8996b07fe5762444c956842b5a7d798b2fcfe5a04574fdf7549",
        "version": "18.0.8+20240713",
    },
    "m4": {
        "url": "https://ftp.gnu.org/gnu/m4/m4-1.4.19.tar.xz",
        "size": 1654908,
        "sha256": "63aede5c6d33b6d9b13511cd0be2cac046f2e70fd0a07aa9573a04a82783af96",
        "version": "1.4.19",
    },
    "mpdecimal": {
        "url": "https://www.bytereef.org/software/mpdecimal/releases/mpdecimal-4.0.0.tar.gz",
        "size": 315325,
        "sha256": "942445c3245b22730fd41a67a7c5c231d11cb1b9936b9c0f76334fb7d0b4468c",
        "version": "4.0.0",
        "library_names": ["mpdec"],
        "licenses": ["BSD-2-Clause"],
        "license_file": "LICENSE.mpdecimal.txt",
    },
    "musl": {
        "url": "https://musl.libc.org/releases/musl-1.2.5.tar.gz",
        "size": 1080786,
        "sha256": "a9a118bbe84d8764da0ea0d28b3ab3fae8477fc7e4085d90102b8596fc7c75e4",
        "version": "1.2.5",
    },
    "ncurses": {
        "url": "https://ftp.gnu.org/pub/gnu/ncurses/ncurses-6.5.tar.gz",
        "size": 3688489,
        "sha256": "136d91bc269a9a5785e5f9e980bc76ab57428f604ce3e5a5a90cebc767971cc6",
        "version": "6.5",
        "library_names": ["ncurses", "ncursesw", "panel", "panelw"],
        "licenses": ["X11"],
        "license_file": "LICENSE.ncurses.txt",
    },
    # Remember to update OPENSSL_VERSION_INFO in verify_distribution.py whenever upgrading.
    "openssl-1.1": {
        "url": "https://www.openssl.org/source/openssl-1.1.1w.tar.gz",
        "size": 9893384,
        "sha256": "cf3098950cb4d853ad95c0841f1f9c6d3dc102dccfcacd521d93925208b76ac8",
        "version": "1.1.1w",
        "library_names": ["crypto", "ssl"],
        "licenses": ["OpenSSL"],
        "license_file": "LICENSE.openssl-1.1.txt",
    },
    # We use OpenSSL 3.0 because it is an LTS release and has a longer support
    # window. If CPython ends up gaining support for 3.1+ releases, we can consider
    # using the latest available.
    # Remember to update OPENSSL_VERSION_INFO in verify_distribution.py whenever upgrading.
    "openssl-3.0": {
        "url": "https://www.openssl.org/source/openssl-3.0.15.tar.gz",
        "size": 15318633,
        "sha256": "23c666d0edf20f14249b3d8f0368acaee9ab585b09e1de82107c66e1f3ec9533",
        "version": "3.0.15",
        "library_names": ["crypto", "ssl"],
        "licenses": ["Apache-2.0"],
        "license_file": "LICENSE.openssl-3.txt",
    },
    "nasm-windows-bin": {
        "url": "https://github.com/python/cpython-bin-deps/archive/nasm-2.11.06.tar.gz",
        "size": 384826,
        "sha256": "8af0ae5ceed63fa8a2ded611d44cc341027a91df22aaaa071efedc81437412a5",
        "version": "2.11.06",
    },
    "patchelf": {
        "url": "https://github.com/NixOS/patchelf/releases/download/0.13.1/patchelf-0.13.1.tar.bz2",
        "size": 173598,
        "sha256": "39e8aeccd7495d54df094d2b4a7c08010ff7777036faaf24f28e07777d1598e2",
        "version": "0.13.1",
    },
    "pip": {
        "url": "https://files.pythonhosted.org/packages/ef/7d/500c9ad20238fcfcb4cb9243eede163594d7020ce87bd9610c9e02771876/pip-24.3.1-py3-none-any.whl",
        "size": 1822182,
        "sha256": "3790624780082365f47549d032f3770eeb2b1e8bd1f7b2e02dace1afa361b4ed",
        "version": "24.3.1",
    },
    "readline": {
        "url": "https://ftp.gnu.org/gnu/readline/readline-8.2.tar.gz",
        "size": 3043952,
        "sha256": "3feb7171f16a84ee82ca18a36d7b9be109a52c04f492a053331d7d1095007c35",
        "version": "8.2",
        "library_names": ["readline"],
        "licenses": ["GPL-3.0-only"],
        "license_file": "LICENSE.readline.txt",
    },
    "setuptools": {
        "url": "https://files.pythonhosted.org/packages/55/21/47d163f615df1d30c094f6c8bbb353619274edccf0327b185cc2493c2c33/setuptools-75.6.0-py3-none-any.whl",
        "size": 1224032,
        "sha256": "ce74b49e8f7110f9bf04883b730f4765b774ef3ef28f722cce7c273d253aaf7d",
        "version": "75.6.0",
    },
    # Remember to update verify_distribution.py when version changed.
    "sqlite": {
        "url": "https://www.sqlite.org/2024/sqlite-autoconf-3470100.tar.gz",
        "size": 3328564,
        "sha256": "416a6f45bf2cacd494b208fdee1beda509abda951d5f47bc4f2792126f01b452",
        "version": "3470100",
        "actual_version": "3.47.1.0",
        "library_names": ["sqlite3"],
        "licenses": [],
        "license_file": "LICENSE.sqlite.txt",
        "license_public_domain": True,
    },
    "strawberryperl": {
        "url": "https://github.com/StrawberryPerl/Perl-Dist-Strawberry/releases/download/SP_53822_64bit/strawberry-perl-5.38.2.2-64bit-portable.zip",
        "size": 264199638,
        "sha256": "ea451686065d6338d7e4d4a04c9af49f17951d15aa4c2e19ab8cb56fa2373440",
        "version": "5.38.2.2",
    },
    "tcl": {
        "url": "https://prdownloads.sourceforge.net/tcl/tcl8.6.14-src.tar.gz",
        "size": 11627322,
        "sha256": "5880225babf7954c58d4fb0f5cf6279104ce1cd6aa9b71e9a6322540e1c4de66",
        "version": "8.6.14",
        "library_names": ["tcl8.6"],
        "licenses": ["TCL"],
        "license_file": "LICENSE.tcl.txt",
    },
    "tix": {
        "url": "https://github.com/python/cpython-source-deps/archive/tix-8.4.3.6.tar.gz",
        "size": 1836451,
        "sha256": "f7b21d115867a41ae5fd7c635a4c234d3ca25126c3661eb36028c6e25601f85e",
        "version": "8.4.3.6",
        "licenses": ["TCL"],
        "license_file": "LICENSE.tix.txt",
    },
    "tk": {
        "url": "https://prdownloads.sourceforge.net/tcl/tk8.6.14-src.tar.gz",
        "size": 4510695,
        "sha256": "8ffdb720f47a6ca6107eac2dd877e30b0ef7fac14f3a84ebbd0b3612cee41a94",
        "version": "8.6.14",
        "library_names": ["tk8.6"],
        "licenses": ["TCL"],
        "license_file": "LICENSE.tcl.txt",
    },
    "tk-windows-bin": {
        "url": "https://github.com/python/cpython-bin-deps/archive/c624cc881bd0e5071dec9de4b120cbe9985d8c14.tar.gz",
        "size": 9497943,
        "sha256": "9b8e77d55f40ceaedd140ccca0daa804f0d43346d5abfcead9b547b5590f82f8",
        "version": "8.6.14",
        "git_commit": "c624cc881bd0e5071dec9de4b120cbe9985d8c14",
    },
    "uuid": {
        "url": "https://sourceforge.net/projects/libuuid/files/libuuid-1.0.3.tar.gz",
        "size": 318256,
        "sha256": "46af3275291091009ad7f1b899de3d0cea0252737550e7919d17237997db5644",
        "version": "1.0.3",
        "library_names": ["uuid"],
        "licenses": ["BSD-3-Clause"],
        "license_file": "LICENSE.libuuid.txt",
    },
    "x11-util-macros": {
        "url": "https://www.x.org/archive/individual/util/util-macros-1.20.1.tar.gz",
        "size": 105481,
        "sha256": "b373f72887b1394ce2193180a60cb0d1fb8b17bc96ddd770cfd7a808cb489a15",
        "version": "1.20.1",
    },
    "xcb-proto": {
        "url": "https://www.x.org/archive/individual/proto/xcb-proto-1.14.1.tar.gz",
        "size": 194674,
        "sha256": "85cd21e9d9fbc341d0dbf11eace98d55d7db89fda724b0e598855fcddf0944fd",
        "version": "1.14.1",
    },
    "xextproto": {
        "url": "https://www.x.org/archive/individual/proto/xextproto-7.3.0.tar.gz",
        "size": 290814,
        "sha256": "1b1bcdf91221e78c6c33738667a57bd9aaa63d5953174ad8ed9929296741c9f5",
        "version": "7.3.0",
    },
    # Newer versions from at least 2023 have build failures for reasons we haven't
    # fully investigated.
    "xorgproto": {
        "url": "https://www.x.org/archive/individual/proto/xorgproto-2019.1.tar.gz",
        "size": 1119813,
        "sha256": "38ad1d8316515785d53c5162b4b7022918e03c11d72a5bd9df0a176607f42bca",
        "version": "2019.1",
    },
    "xproto": {
        "url": "https://www.x.org/archive/individual/proto/xproto-7.0.31.tar.gz",
        "size": 367979,
        "sha256": "6d755eaae27b45c5cc75529a12855fed5de5969b367ed05003944cf901ed43c7",
        "version": "7.0.31",
    },
    "xtrans": {
        "url": "https://www.x.org/archive/individual/lib/xtrans-1.5.0.tar.gz",
        "size": 230197,
        "sha256": "a806f8a92f879dcd0146f3f1153fdffe845f2fc0df9b1a26c19312b7b0a29c86",
        "version": "1.5.0",
    },
    # IMPORTANT: xz 5.6 has a backdoor. Be extremely cautious before taking any xz
    # upgrade since it isn't clear which versions are safe.
    "xz": {
        "url": "https://github.com/indygreg/python-build-standalone/releases/download/20240224/xz-5.2.12.tar.gz",
        "size": 2190541,
        "sha256": "61bda930767dcb170a5328a895ec74cab0f5aac4558cdda561c83559db582a13",
        "version": "5.2.12",
        "library_names": ["lzma"],
        # liblzma is in the public domain. Other parts of code have licenses. But
        # we only use liblzma.
        "licenses": [],
        "license_file": "LICENSE.liblzma.txt",
        "license_public_domain": True,
    },
    "zlib": {
        "url": "https://github.com/madler/zlib/releases/download/v1.2.13/zlib-1.2.13.tar.gz",
        "size": 1497445,
        "sha256": "b3a24de97a8fdbc835b9833169501030b8977031bcb54b3b3ac13740f846ab30",
        "version": "1.2.13",
        "library_names": ["z"],
        "licenses": ["Zlib"],
        "license_file": "LICENSE.zlib.txt",
    },
}
