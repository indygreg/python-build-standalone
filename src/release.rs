// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

use {once_cell::sync::Lazy, std::collections::BTreeMap};

/// Describes a release for a given target triple.
pub struct TripleRelease {
    /// Build suffixes to release.
    pub suffixes: Vec<&'static str>,
    /// Build suffix to use for the `install_only` artifact.
    pub install_only_suffix: &'static str,
}

pub static RELEASE_TRIPLES: Lazy<BTreeMap<&'static str, TripleRelease>> = Lazy::new(|| {
    let mut h = BTreeMap::new();

    // macOS.
    let macos_suffixes = vec!["debug", "lto", "pgo", "pgo+lto", "install_only"];
    h.insert(
        "aarch64-apple-darwin",
        TripleRelease {
            suffixes: macos_suffixes.clone(),
            install_only_suffix: "pgo+lto",
        },
    );
    h.insert(
        "x86_64-apple-darwin",
        TripleRelease {
            suffixes: macos_suffixes,
            install_only_suffix: "pgo+lto",
        },
    );

    // Windows.
    let windows_suffixes = vec!["shared-pgo", "static-noopt", "shared-install_only"];
    h.insert(
        "i686-pc-windows-msvc",
        TripleRelease {
            suffixes: windows_suffixes.clone(),
            install_only_suffix: "shared-pgo",
        },
    );
    h.insert(
        "x86_64-pc-windows-msvc",
        TripleRelease {
            suffixes: windows_suffixes,
            install_only_suffix: "shared-pgo",
        },
    );

    // Linux.
    let linux_suffixes_pgo = vec!["debug", "lto", "pgo", "pgo+lto", "install_only"];
    let linux_suffixes_nopgo = vec!["debug", "lto", "noopt", "install_only"];

    h.insert(
        "aarch64-unknown-linux-gnu",
        TripleRelease {
            suffixes: linux_suffixes_nopgo.clone(),
            install_only_suffix: "lto",
        },
    );

    h.insert(
        "i686-unknown-linux-gnu",
        TripleRelease {
            suffixes: linux_suffixes_pgo.clone(),
            install_only_suffix: "pgo+lto",
        },
    );

    h.insert(
        "x86_64-unknown-linux-gnu",
        TripleRelease {
            suffixes: linux_suffixes_pgo.clone(),
            install_only_suffix: "pgo+lto",
        },
    );
    h.insert(
        "x86_64_v2-unknown-linux-gnu",
        TripleRelease {
            suffixes: linux_suffixes_pgo.clone(),
            install_only_suffix: "pgo+lto",
        },
    );
    h.insert(
        "x86_64_v3-unknown-linux-gnu",
        TripleRelease {
            suffixes: linux_suffixes_pgo.clone(),
            install_only_suffix: "pgo+lto",
        },
    );
    h.insert(
        "x86_64_v4-unknown-linux-gnu",
        TripleRelease {
            suffixes: linux_suffixes_nopgo.clone(),
            install_only_suffix: "lto",
        },
    );
    h.insert(
        "x86_64-unknown-linux-musl",
        TripleRelease {
            suffixes: linux_suffixes_nopgo.clone(),
            install_only_suffix: "lto",
        },
    );
    h.insert(
        "x86_64_v2-unknown-linux-musl",
        TripleRelease {
            suffixes: linux_suffixes_nopgo.clone(),
            install_only_suffix: "lto",
        },
    );
    h.insert(
        "x86_64_v3-unknown-linux-musl",
        TripleRelease {
            suffixes: linux_suffixes_nopgo.clone(),
            install_only_suffix: "lto",
        },
    );
    h.insert(
        "x86_64_v4-unknown-linux-musl",
        TripleRelease {
            suffixes: linux_suffixes_nopgo.clone(),
            install_only_suffix: "lto",
        },
    );

    h
});
