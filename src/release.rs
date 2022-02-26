// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

use {once_cell::sync::Lazy, std::collections::BTreeMap};

pub static SUFFIXES_BY_TRIPLE: Lazy<BTreeMap<&'static str, Vec<&'static str>>> = Lazy::new(|| {
    let mut h = BTreeMap::new();

    // macOS.
    let macos_suffixes = vec!["debug", "lto", "pgo", "pgo+lto", "install_only"];
    h.insert("aarch64-apple-darwin", macos_suffixes.clone());
    h.insert("x86_64-apple-darwin", macos_suffixes);

    // Windows.
    let windows_suffixes = vec!["shared-pgo", "static-noopt", "shared-install_only"];
    h.insert("i686-pc-windows-msvc", windows_suffixes.clone());
    h.insert("x86_64-pc-windows-msvc", windows_suffixes);

    // Linux.
    let linux_suffixes_pgo = vec!["debug", "lto", "pgo", "pgo+lto", "install_only"];
    let linux_suffixes_nopgo = vec!["debug", "lto", "noopt", "install_only"];

    h.insert("aarch64-unknown-linux-gnu", linux_suffixes_nopgo.clone());

    h.insert("i686-unknown-linux-gnu", linux_suffixes_pgo.clone());

    h.insert("x86_64-unknown-linux-gnu", linux_suffixes_pgo.clone());
    h.insert("x86_64_v2-unknown-linux-gnu", linux_suffixes_pgo.clone());
    h.insert("x86_64_v3-unknown-linux-gnu", linux_suffixes_pgo.clone());
    h.insert("x86_64_v4-unknown-linux-gnu", linux_suffixes_nopgo.clone());
    h.insert("x86_64-unknown-linux-musl", linux_suffixes_nopgo.clone());
    h.insert("x86_64_v2-unknown-linux-musl", linux_suffixes_nopgo.clone());
    h.insert("x86_64_v3-unknown-linux-musl", linux_suffixes_nopgo.clone());
    h.insert("x86_64_v4-unknown-linux-musl", linux_suffixes_nopgo.clone());

    h
});
