# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

DOWNLOADS = {
    # 6.0.19 is the last version licensed under the Sleepycat license.
    'bdb': {
        'url': 'https://ftp.tw.freebsd.org/distfiles/bdb/db-6.0.19.tar.gz',
        'size': 36541923,
        'sha256': '2917c28f60903908c2ca4587ded1363b812c4e830a5326aaa77c9879d13ae18e',
        'version': '6.0.19',
    },
    'binutils': {
        'url': 'ftp://ftp.gnu.org/gnu/binutils/binutils-2.31.tar.xz',
        'size': 20445772,
        'sha256': '231036df7ef02049cdbff0681f4575e571f26ea8086cf70c2dcd3b6c0f4216bf',
        'version': '2.31',
    },
    'bzip2': {
        'url': 'https://ftp.sunet.se/mirror/archive/ftp.sunet.se/pub/Linux/distributions/bifrost/download/src/bzip2-1.0.6.tar.gz',
        'size': 782025,
        'sha256': 'a2848f34fcd5d6cf47def00461fcb528a0484d8edef8208d6d2e2909dc61d9cd',
        'version': '1.0.6',
    },
    'clang': {
        'url': 'http://releases.llvm.org/7.0.0/cfe-7.0.0.src.tar.xz',
        'size': 12541904,
        'sha256': '550212711c752697d2f82c648714a7221b1207fd9441543ff4aa9e3be45bba55',
        'version': '7.0.0',
    },
    'clang-compiler-rt': {
        'url': 'http://releases.llvm.org/7.0.0/compiler-rt-7.0.0.src.tar.xz',
        'size': 1815168,
        'sha256': 'bdec7fe3cf2c85f55656c07dfb0bd93ae46f2b3dd8f33ff3ad6e7586f4c670d6',
        'version': '7.0.0',
    },
    'cmake-linux-bin': {
        'url': 'https://github.com/Kitware/CMake/releases/download/v3.13.0/cmake-3.13.0-Linux-x86_64.tar.gz',
        'size': 38391207,
        'sha256': '1c6612f3c6dd62959ceaa96c4b64ba7785132de0b9cbc719eea6fe1365cc8d94',
        'version': '3.13.0',
    },
    'cpython-3.7': {
        'url': 'https://www.python.org/ftp/python/3.7.2/Python-3.7.2.tar.xz',
        'size': 17042320,
        'sha256': 'd83fe8ce51b1bb48bbcf0550fd265b9a75cdfdfa93f916f9e700aef8444bf1bb',
        'version': '3.7.2',
    },
    'gcc': {
        'url': 'https://ftp.gnu.org/gnu/gcc/gcc-8.2.0/gcc-8.2.0.tar.xz',
        'size': 63460876,
        'sha256': '196c3c04ba2613f893283977e6011b2345d1cd1af9abeac58e916b1aab3e0080',
        'version': '8.2.0',
    },
    'gdbm': {
        'url': 'ftp://ftp.gnu.org/gnu/gdbm/gdbm-1.18.1.tar.gz',
        'size': 941863,
        'sha256': '86e613527e5dba544e73208f42b78b7c022d4fa5a6d5498bf18c8d6f745b91dc',
        'version': '1.18.1',
    },
    'gmp': {
        'url': 'https://ftp.gnu.org/gnu/gmp/gmp-6.1.2.tar.xz',
        'size': 1946336,
        'sha256': '87b565e89a9a684fe4ebeeddb8399dce2599f9c9049854ca8c0dfbdea0e21912',
        'version': '6.1.2',
    },
    'isl': {
        'url': 'ftp://gcc.gnu.org/pub/gcc/infrastructure/isl-0.18.tar.bz2',
        'size': 1658291,
        'sha256': '6b8b0fd7f81d0a957beb3679c81bbb34ccc7568d5682844d8924424a0dadcb1b',
        'version': '0.18',
    },
    'libc++': {
        'url': 'http://releases.llvm.org/7.0.0/libcxx-7.0.0.src.tar.xz',
        'size': 1652496,
        'sha256': '9b342625ba2f4e65b52764ab2061e116c0337db2179c6bce7f9a0d70c52134f0',
        'version': '7.0.0',
    },
    'libc++abi': {
        'url': 'http://releases.llvm.org/7.0.0/libcxxabi-7.0.0.src.tar.xz',
        'size': 535792,
        'sha256': '9b45c759ff397512eae4d938ff82827b1bd7ccba49920777e5b5e460baeb245f',
        'version': '7.0.0',
    },
    'libedit': {
        'url': 'https://www.thrysoee.dk/editline/libedit-20181209-3.1.tar.gz',
        'size': 521931,
        'sha256': '2811d70c0b000f2ca91b7cb1a37203134441743c4fcc9c37b0b687f328611064',
        'version': '20181209-3.1',
    },
    'libffi': {
        'url': 'ftp://sourceware.org/pub/libffi/libffi-3.2.1.tar.gz',
        'size': 940837,
        'sha256': 'd06ebb8e1d9a22d19e38d63fdb83954253f39bedc5d46232a05645685722ca37',
        'version': '3.2.1',
    },
    'libx11': {
        'url': 'https://www.x.org/releases/X11R7.7/src/lib/libX11-1.5.0.tar.gz',
        'size': 3073820,
        'sha256': '2ddc05170baf70dd650ee6108c5882eb657cafaf61a5b5261badb26703122518',
    },
    'lld': {
        'url': 'http://releases.llvm.org/7.0.0/lld-7.0.0.src.tar.xz',
        'size': 915692,
        'sha256': 'fbcf47c5e543f4cdac6bb9bbbc6327ff24217cd7eafc5571549ad6d237287f9c',
        'version': '7.0.0',
    },
    'llvm': {
        'url': 'http://releases.llvm.org/7.0.0/llvm-7.0.0.src.tar.xz',
        'size': 28324368,
        'sha256': '8bc1f844e6cbde1b652c19c1edebc1864456fd9c78b8c1bea038e51b363fe222',
        'version': '7.0.0',
    },
    'mpc': {
        'url': 'http://www.multiprecision.org/downloads/mpc-1.0.3.tar.gz',
        'size': 669925,
        'sha256': '617decc6ea09889fb08ede330917a00b16809b8db88c29c31bfbb49cbf88ecc3',
        'version': '1.0.3',
    },
    'mpfr': {
        'url': 'https://ftp.gnu.org/gnu/mpfr/mpfr-3.1.6.tar.xz',
        'size': 1133672,
        'sha256': '7a62ac1a04408614fccdc506e4844b10cf0ad2c2b1677097f8f35d3a1344a950',
        'version': '3.1.6',
    },
    'ncurses': {
        'url': 'https://ftp.gnu.org/pub/gnu/ncurses/ncurses-6.1.tar.gz',
        'size': 3365395,
        'sha256': 'aa057eeeb4a14d470101eff4597d5833dcef5965331be3528c08d99cebaa0d17',
        'version': '6.1',
    },
    'ninja-linux-bin': {
        'url': 'https://github.com/ninja-build/ninja/releases/download/v1.8.2/ninja-linux.zip',
        'size': 77854,
        'sha256': 'd2fea9ff33b3ef353161ed906f260d565ca55b8ca0568fa07b1d2cab90a84a07',
    },
    'openssl': {
        'url': 'https://www.openssl.org/source/openssl-1.1.1a.tar.gz',
        'size': 8350547,
        'sha256': 'fc20130f8b7cbd2fb918b2f14e2f429e109c31ddd0fb38fc5d71d9ffed3f9f41',
        'version': '1.1.1a',
    },
    'readline': {
        'url': 'ftp://ftp.gnu.org/gnu/readline/readline-6.3.tar.gz',
        'size': 2468560,
        'sha256': '56ba6071b9462f980c5a72ab0023893b65ba6debb4eeb475d7a563dc65cafd43',
        'version': '6.3',
    },
    'rust': {
        'url': 'https://static.rust-lang.org/dist/rust-1.30.1-x86_64-unknown-linux-gnu.tar.gz',
        'size': 236997689,
        'sha256': 'a01a493ed8946fc1c15f63e74fc53299b26ebf705938b4d04a388a746dfdbf9e',
    },
    'sqlite': {
        'url': 'https://www.sqlite.org/2018/sqlite-autoconf-3260000.tar.gz',
        'size': 2779667,
        'sha256': '5daa6a3fb7d1e8c767cd59c4ded8da6e4b00c61d3b466d0685e35c4dd6d7bf5d',
        'version': '3260000',
    },
    'tcl': {
        'url': 'https://prdownloads.sourceforge.net/tcl/tcl8.6.9-src.tar.gz',
        'size': 10000896,
        'sha256': 'ad0cd2de2c87b9ba8086b43957a0de3eb2eb565c7159d5f53ccbba3feb915f4e',
    },
    'tk': {
        'url': 'https://prdownloads.sourceforge.net/tcl/tk8.6.9.1-src.tar.gz',
        'size': 4364603,
        'sha256': '8fcbcd958a8fd727e279f4cac00971eee2ce271dc741650b1fc33375fb74ebb4',
    },
    'uuid': {
        'url': 'https://sourceforge.net/projects/libuuid/files/libuuid-1.0.3.tar.gz',
        'size': 318256,
        'sha256': '46af3275291091009ad7f1b899de3d0cea0252737550e7919d17237997db5644',
        'version': '1.0.3',
    },
    'xz': {
        'url': 'https://tukaani.org/xz/xz-5.2.4.tar.gz',
        'size': 1572354,
        'sha256': 'b512f3b726d3b37b6dc4c8570e137b9311e7552e8ccbab4d39d47ce5f4177145',
        'version': '5.2.4',
    },
    'zlib': {
        'url': 'https://zlib.net/zlib-1.2.11.tar.gz',
        'size': 607698,
        'sha256': 'c3e5e9fdd5004dcb542feda5ee4f0ff0744628baf8ed2dd5d66f8ca1197cb1a1',
        'version': '1.2.11',
    },
}
