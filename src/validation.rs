// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

use {
    crate::{json::*, macho::*},
    anyhow::{anyhow, Context, Result},
    clap::ArgMatches,
    goblin::mach::load_command::CommandVariant,
    once_cell::sync::Lazy,
    scroll::Pread,
    std::{
        collections::{BTreeSet, HashMap},
        convert::TryInto,
        io::Read,
        iter::FromIterator,
        path::{Path, PathBuf},
    },
};

const RECOGNIZED_TRIPLES: &[&str] = &[
    "aarch64-apple-darwin",
    "aarch64-apple-ios",
    "aarch64-unknown-linux-gnu",
    "armv7-unknown-linux-gnueabi",
    "armv7-unknown-linux-gnueabihf",
    "arm64-apple-tvos",
    "i686-pc-windows-msvc",
    "i686-unknown-linux-gnu",
    "mips-unknown-linux-gnu",
    "mipsel-unknown-linux-gnu",
    "mips64el-unknown-linux-gnuabi64",
    "s390x-unknown-linux-gnu",
    "thumbv7k-apple-watchos",
    "x86_64-apple-darwin",
    "x86_64-apple-ios",
    "x86_64-apple-tvos",
    "x86_64-apple-watchos",
    "x86_64-pc-windows-msvc",
    "x86_64-unknown-linux-gnu",
    "x86_64_v2-unknown-linux-gnu",
    "x86_64_v3-unknown-linux-gnu",
    "x86_64_v4-unknown-linux-gnu",
    "x86_64-unknown-linux-musl",
    "x86_64_v2-unknown-linux-musl",
    "x86_64_v3-unknown-linux-musl",
    "x86_64_v4-unknown-linux-musl",
];

const ELF_ALLOWED_LIBRARIES: &[&str] = &[
    // LSB set.
    "libc.so.6",
    "libcrypt.so.1",
    "libdl.so.2",
    "libm.so.6",
    "libpthread.so.0",
    "librt.so.1",
    "libutil.so.1",
];

const PE_ALLOWED_LIBRARIES: &[&str] = &[
    "ADVAPI32.dll",
    "api-ms-win-core-path-l1-1-0.dll",
    "api-ms-win-crt-conio-l1-1-0.dll",
    "api-ms-win-crt-convert-l1-1-0.dll",
    "api-ms-win-crt-heap-l1-1-0.dll",
    "api-ms-win-crt-environment-l1-1-0.dll",
    "api-ms-win-crt-filesystem-l1-1-0.dll",
    "api-ms-win-crt-locale-l1-1-0.dll",
    "api-ms-win-crt-math-l1-1-0.dll",
    "api-ms-win-crt-process-l1-1-0.dll",
    "api-ms-win-crt-runtime-l1-1-0.dll",
    "api-ms-win-crt-stdio-l1-1-0.dll",
    "api-ms-win-crt-string-l1-1-0.dll",
    "api-ms-win-crt-time-l1-1-0.dll",
    "api-ms-win-crt-utility-l1-1-0.dll",
    "bcrypt.dll",
    "Cabinet.dll",
    "COMCTL32.dll",
    "COMDLG32.dll",
    "CRYPT32.dll",
    "GDI32.dll",
    "IMM32.dll",
    "IPHLPAPI.DLL",
    "KERNEL32.dll",
    "msi.dll",
    "NETAPI32.dll",
    "ole32.dll",
    "OLEAUT32.dll",
    "RPCRT4.dll",
    "SHELL32.dll",
    "SHLWAPI.dll",
    "USER32.dll",
    "USERENV.dll",
    "VERSION.dll",
    "VCRUNTIME140.dll",
    "WINMM.dll",
    "WS2_32.dll",
    // Our libraries.
    "libcrypto-1_1.dll",
    "libcrypto-1_1-x64.dll",
    "libffi-8.dll",
    "libssl-1_1.dll",
    "libssl-1_1-x64.dll",
    "python3.dll",
    "python38.dll",
    "python39.dll",
    "python310.dll",
    "sqlite3.dll",
    "tcl86t.dll",
    "tk86t.dll",
];

static GLIBC_MAX_VERSION_BY_TRIPLE: Lazy<HashMap<&'static str, version_compare::Version<'static>>> =
    Lazy::new(|| {
        let mut versions = HashMap::new();

        versions.insert(
            "aarch64-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "armv7-unknown-linux-gnueabi",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "armv7-unknown-linux-gnueabihf",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "i686-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "mips-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "mipsel-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "mips64el-unknown-linux-gnuabi64",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "s390x-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "x86_64-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "x86_64_v2-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "x86_64_v3-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );
        versions.insert(
            "x86_64_v4-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );

        // musl shouldn't link against glibc.
        versions.insert(
            "x86_64-unknown-linux-musl",
            version_compare::Version::from("1").unwrap(),
        );
        versions.insert(
            "x86_64_v2-unknown-linux-musl",
            version_compare::Version::from("1").unwrap(),
        );
        versions.insert(
            "x86_64_v3-unknown-linux-musl",
            version_compare::Version::from("1").unwrap(),
        );
        versions.insert(
            "x86_64_v4-unknown-linux-musl",
            version_compare::Version::from("1").unwrap(),
        );

        versions
    });

static ELF_ALLOWED_LIBRARIES_BY_TRIPLE: Lazy<HashMap<&'static str, Vec<&'static str>>> =
    Lazy::new(|| {
        [
            (
                "armv7-unknown-linux-gnueabi",
                vec!["ld-linux.so.3", "libgcc_s.so.1"],
            ),
            (
                "armv7-unknown-linux-gnueabihf",
                vec!["ld-linux-armhf.so.3", "libgcc_s.so.1"],
            ),
            ("i686-unknown-linux-gnu", vec!["ld-linux-x86-64.so.2"]),
            ("mips-unknown-linux-gnu", vec!["ld.so.1"]),
            ("mipsel-unknown-linux-gnu", vec!["ld.so.1"]),
            ("mips64el-unknown-linux-gnuabi64", vec![]),
            ("s390x-unknown-linux-gnu", vec!["ld64.so.1"]),
            ("x86_64-unknown-linux-gnu", vec!["ld-linux-x86-64.so.2"]),
            ("x86_64_v2-unknown-linux-gnu", vec!["ld-linux-x86-64.so.2"]),
            ("x86_64_v3-unknown-linux-gnu", vec!["ld-linux-x86-64.so.2"]),
            ("x86_64_v4-unknown-linux-gnu", vec!["ld-linux-x86-64.so.2"]),
        ]
        .iter()
        .cloned()
        .collect()
    });

static DARWIN_ALLOWED_DYLIBS: Lazy<Vec<MachOAllowedDylib>> = Lazy::new(|| {
    [
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.8.dylib".to_string(),
                max_compatibility_version: "3.8.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.8d.dylib".to_string(),
                max_compatibility_version: "3.8.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.9.dylib".to_string(),
                max_compatibility_version: "3.9.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.9d.dylib".to_string(),
                max_compatibility_version: "3.9.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.10.dylib".to_string(),
                max_compatibility_version: "3.10.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.10d.dylib".to_string(),
                max_compatibility_version: "3.10.0".try_into().unwrap(),
                required: false,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/AppKit.framework/Versions/C/AppKit".to_string(),
                max_compatibility_version: "45.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/ApplicationServices.framework/Versions/A/ApplicationServices".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/Carbon.framework/Versions/A/Carbon".to_string(),
                max_compatibility_version: "2.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name:
                    "/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation"
                        .to_string(),
                max_compatibility_version: "150.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/CoreGraphics.framework/Versions/A/CoreGraphics".to_string(),
                max_compatibility_version: "64.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/CoreServices.framework/Versions/A/CoreServices".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/CoreText.framework/Versions/A/CoreText".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/Foundation.framework/Versions/C/Foundation".to_string(),
                max_compatibility_version: "300.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/SystemConfiguration.framework/Versions/A/SystemConfiguration".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/usr/lib/libedit.3.dylib".to_string(),
                max_compatibility_version: "2.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/usr/lib/libncurses.5.4.dylib".to_string(),
                max_compatibility_version: "5.4.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/usr/lib/libobjc.A.dylib".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/usr/lib/libpanel.5.4.dylib".to_string(),
                max_compatibility_version: "5.4.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/usr/lib/libSystem.B.dylib".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
            MachOAllowedDylib {
                name: "/usr/lib/libz.1.dylib".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
                required: true,
            },
        ]
        .to_vec()
});

static IOS_ALLOWED_DYLIBS: Lazy<Vec<MachOAllowedDylib>> = Lazy::new(|| {
    [
        MachOAllowedDylib {
            name: "@executable_path/../lib/libpython3.9.dylib".to_string(),
            max_compatibility_version: "3.9.0".try_into().unwrap(),
            required: false,
        },
        MachOAllowedDylib {
            name: "@executable_path/../lib/libpython3.9d.dylib".to_string(),
            max_compatibility_version: "3.9.0".try_into().unwrap(),
            required: false,
        },
        MachOAllowedDylib {
            name: "@executable_path/../lib/libpython3.10.dylib".to_string(),
            max_compatibility_version: "3.10.0".try_into().unwrap(),
            required: false,
        },
        MachOAllowedDylib {
            name: "@executable_path/../lib/libpython3.10d.dylib".to_string(),
            max_compatibility_version: "3.10.0".try_into().unwrap(),
            required: false,
        },
        // For some reason, CoreFoundation is present in debug/noopt builds but not
        // LTO builds.
        MachOAllowedDylib {
            name: "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation".to_string(),
            max_compatibility_version: "150.0.0".try_into().unwrap(),
            required: false,
        },
        MachOAllowedDylib {
            name: "/usr/lib/libSystem.B.dylib".to_string(),
            max_compatibility_version: "1.0.0".try_into().unwrap(),
            required: true,
        },
        MachOAllowedDylib {
            name: "/usr/lib/libz.1.dylib".to_string(),
            max_compatibility_version: "1.0.0".try_into().unwrap(),
            required: true,
        },
    ]
    .to_vec()
});

static PLATFORM_TAG_BY_TRIPLE: Lazy<HashMap<&'static str, &'static str>> = Lazy::new(|| {
    [
        ("aarch64-apple-darwin", "macosx-11.0-arm64"),
        ("aarch64-apple-ios", "iOS-aarch64"),
        ("aarch64-unknown-linux-gnu", "linux-aarch64"),
        ("armv7-unknown-linux-gnueabi", "linux-arm"),
        ("armv7-unknown-linux-gnueabihf", "linux-arm"),
        ("i686-pc-windows-msvc", "win32"),
        ("i686-unknown-linux-gnu", "linux-i686"),
        ("mips-unknown-linux-gnu", "linux-mips"),
        ("mipsel-unknown-linux-gnu", "linux-mipsel"),
        ("mips64el-unknown-linux-gnuabi64", "todo"),
        ("s390x-unknown-linux-gnu", "linux-s390x"),
        ("x86_64-apple-darwin", "macosx-10.9-x86_64"),
        ("x86_64-apple-ios", "iOS-x86_64"),
        ("x86_64-pc-windows-msvc", "win-amd64"),
        ("x86_64-unknown-linux-gnu", "linux-x86_64"),
        ("x86_64_v2-unknown-linux-gnu", "linux-x86_64"),
        ("x86_64_v3-unknown-linux-gnu", "linux-x86_64"),
        ("x86_64_v4-unknown-linux-gnu", "linux-x86_64"),
        ("x86_64-unknown-linux-musl", "linux-x86_64"),
        ("x86_64_v2-unknown-linux-musl", "linux-x86_64"),
        ("x86_64_v3-unknown-linux-musl", "linux-x86_64"),
        ("x86_64_v4-unknown-linux-musl", "linux-x86_64"),
    ]
    .iter()
    .cloned()
    .collect()
});

const ELF_BANNED_SYMBOLS: &[&str] = &[
    // Deprecated as of glibc 2.34 in favor of sched_yield.
    "pthread_yield",
];

/// Symbols that we don't want to appear in mach-o binaries.
const MACHO_BANNED_SYMBOLS_NON_AARCH64: &[&str] = &[
    // _readv and _pwritev are introduced when building with the macOS 11 SDK.
    // If present, they can cause errors re-linking object files. So we ban their
    // existence.
    "_preadv", "_pwritev",
];

static WANTED_WINDOWS_STATIC_PATHS: Lazy<BTreeSet<PathBuf>> = Lazy::new(|| {
    [
        PathBuf::from("python/build/lib/libffi.lib"),
        PathBuf::from("python/build/lib/libcrypto_static.lib"),
        PathBuf::from("python/build/lib/liblzma.lib"),
        PathBuf::from("python/build/lib/libssl_static.lib"),
        PathBuf::from("python/build/lib/sqlite3.lib"),
    ]
    .iter()
    .cloned()
    .collect()
});

const GLOBALLY_BANNED_EXTENSIONS: &[&str] = &[
    // Due to linking issues. See comment in cpython.py.
    "nis",
];

const PYTHON_VERIFICATIONS: &str = include_str!("verify_distribution.py");

fn allowed_dylibs_for_triple(triple: &str) -> Vec<MachOAllowedDylib> {
    match triple {
        "aarch64-apple-darwin" => DARWIN_ALLOWED_DYLIBS.clone(),
        "x86_64-apple-darwin" => DARWIN_ALLOWED_DYLIBS.clone(),
        "aarch64-apple-ios" => IOS_ALLOWED_DYLIBS.clone(),
        "x86_64-apple-ios" => IOS_ALLOWED_DYLIBS.clone(),
        _ => vec![],
    }
}

fn validate_elf(
    json: &PythonJsonMain,
    target_triple: &str,
    python_major_minor: &str,
    path: &Path,
    elf: &goblin::elf::Elf,
    bytes: &[u8],
) -> Result<Vec<String>> {
    let mut system_links = BTreeSet::new();
    for link in &json.build_info.core.links {
        if link.system.unwrap_or_default() {
            system_links.insert(link.name.as_str());
        }
    }
    for extension in json.build_info.extensions.values() {
        for variant in extension {
            for link in &variant.links {
                if link.system.unwrap_or_default() {
                    system_links.insert(link.name.as_str());
                }
            }
        }
    }

    let mut errors = vec![];

    let wanted_cpu_type = match target_triple {
        "aarch64-unknown-linux-gnu" => goblin::elf::header::EM_AARCH64,
        "armv7-unknown-linux-gnueabi" => goblin::elf::header::EM_ARM,
        "armv7-unknown-linux-gnueabihf" => goblin::elf::header::EM_ARM,
        "i686-unknown-linux-gnu" => goblin::elf::header::EM_386,
        "mips-unknown-linux-gnu" => goblin::elf::header::EM_MIPS,
        "mipsel-unknown-linux-gnu" => goblin::elf::header::EM_MIPS,
        "mips64el-unknown-linux-gnuabi64" => 0,
        "s390x-unknown-linux-gnu" => goblin::elf::header::EM_S390,
        "x86_64-unknown-linux-gnu" => goblin::elf::header::EM_X86_64,
        "x86_64_v2-unknown-linux-gnu" => goblin::elf::header::EM_X86_64,
        "x86_64_v3-unknown-linux-gnu" => goblin::elf::header::EM_X86_64,
        "x86_64_v4-unknown-linux-gnu" => goblin::elf::header::EM_X86_64,
        "x86_64-unknown-linux-musl" => goblin::elf::header::EM_X86_64,
        "x86_64_v2-unknown-linux-musl" => goblin::elf::header::EM_X86_64,
        "x86_64_v3-unknown-linux-musl" => goblin::elf::header::EM_X86_64,
        "x86_64_v4-unknown-linux-musl" => goblin::elf::header::EM_X86_64,
        _ => panic!("unhandled target triple: {}", target_triple),
    };

    if elf.header.e_machine != wanted_cpu_type {
        errors.push(format!(
            "invalid ELF machine type in {}; wanted {}, got {}",
            path.display(),
            wanted_cpu_type,
            elf.header.e_machine
        ));
    }

    let mut allowed_libraries = ELF_ALLOWED_LIBRARIES
        .iter()
        .map(|x| x.to_string())
        .collect::<Vec<_>>();
    if let Some(extra) = ELF_ALLOWED_LIBRARIES_BY_TRIPLE.get(target_triple) {
        allowed_libraries.extend(extra.iter().map(|x| x.to_string()));
    }

    allowed_libraries.push(format!(
        "$ORIGIN/../lib/libpython{}.so.1.0",
        python_major_minor
    ));
    allowed_libraries.push(format!(
        "$ORIGIN/../lib/libpython{}d.so.1.0",
        python_major_minor
    ));

    for lib in &elf.libraries {
        if !allowed_libraries.contains(&lib.to_string()) {
            errors.push(format!("{} loads illegal library {}", path.display(), lib));
        }

        // Most linked libraries should have an annotation in the JSON metadata.
        let requires_annotation = !lib.contains("libpython")
            && !lib.starts_with("ld-linux")
            && !lib.starts_with("ld64.so")
            && !lib.starts_with("ld.so")
            && !lib.starts_with("libc.so")
            && !lib.starts_with("libgcc_s.so");

        if requires_annotation {
            if lib.starts_with("lib") {
                if let Some(index) = lib.rfind(".so") {
                    let lib_name = &lib[3..index];

                    // There should be a system links entry for this library in the JSON
                    // metadata.
                    //
                    // Nominally we would look at where this ELF came from and make sure
                    // the annotation is present in its section (e.g. core or extension).
                    // But this is more work.
                    if !system_links.contains(lib_name) {
                        errors.push(format!(
                            "{} library load of {} does not have system link build annotation",
                            path.display(),
                            lib
                        ));
                    }
                } else {
                    errors.push(format!(
                        "{} library load of {} does not have .so extension",
                        path.display(),
                        lib
                    ));
                }
            } else {
                errors.push(format!(
                    "{} library load of {} does not begin with lib",
                    path.display(),
                    lib
                ));
            }
        }
    }

    let wanted_glibc_max_version = GLIBC_MAX_VERSION_BY_TRIPLE
        .get(target_triple)
        .expect("max glibc version not defined for target triple");

    // functionality doesn't yet support mips.
    if !target_triple.starts_with("mips") && !target_triple.starts_with("s390x-") {
        let mut undefined_symbols = tugger_binary_analysis::find_undefined_elf_symbols(&bytes, elf);
        undefined_symbols.sort();

        for symbol in undefined_symbols {
            if ELF_BANNED_SYMBOLS.contains(&symbol.symbol.as_str()) {
                errors.push(format!(
                    "{} defines banned ELF symbol {}",
                    path.display(),
                    symbol.symbol,
                ));
            }

            if let Some(version) = &symbol.version {
                let parts: Vec<&str> = version.splitn(2, '_').collect();

                if parts.len() == 2 {
                    if parts[0] == "GLIBC" {
                        let v = version_compare::Version::from(parts[1])
                            .expect("unable to parse version");

                        if &v > wanted_glibc_max_version {
                            errors.push(format!(
                                "{} references too new glibc symbol {:?}",
                                path.display(),
                                symbol
                            ))
                        }
                    }
                }
            }
        }
    }

    Ok(errors)
}

fn validate_macho(
    target_triple: &str,
    path: &Path,
    macho: &goblin::mach::MachO,
    bytes: &[u8],
) -> Result<(Vec<String>, Vec<String>)> {
    let mut errors = vec![];
    let mut seen_dylibs = vec![];

    let wanted_cpu_type = match target_triple {
        "aarch64-apple-darwin" => goblin::mach::cputype::CPU_TYPE_ARM64,
        "aarch64-apple-ios" => goblin::mach::cputype::CPU_TYPE_ARM64,
        "x86_64-apple-darwin" => goblin::mach::cputype::CPU_TYPE_X86_64,
        "x86_64-apple-ios" => goblin::mach::cputype::CPU_TYPE_X86_64,
        _ => return Err(anyhow!("unhandled target triple: {}", target_triple)),
    };

    if macho.header.cputype() != wanted_cpu_type {
        errors.push(format!(
            "{} has incorrect CPU type; got {}, wanted {}",
            path.display(),
            macho.header.cputype(),
            wanted_cpu_type
        ));
    }

    for load_command in &macho.load_commands {
        match load_command.command {
            CommandVariant::LoadDylib(command)
            | CommandVariant::LoadUpwardDylib(command)
            | CommandVariant::ReexportDylib(command)
            | CommandVariant::LoadWeakDylib(command)
            | CommandVariant::LazyLoadDylib(command) => {
                let lib = bytes.pread::<&str>(load_command.offset + command.dylib.name as usize)?;

                let allowed = allowed_dylibs_for_triple(target_triple);

                if let Some(entry) = allowed.iter().find(|l| l.name == lib) {
                    let load_version =
                        MachOPackedVersion::from(command.dylib.compatibility_version);
                    if load_version > entry.max_compatibility_version {
                        errors.push(format!(
                            "{} loads too new version of {}; got {}, max allowed {}",
                            path.display(),
                            lib,
                            load_version,
                            entry.max_compatibility_version
                        ));
                    }

                    seen_dylibs.push(lib.to_string());
                } else {
                    errors.push(format!("{} loads illegal library {}", path.display(), lib));
                }
            }
            _ => {}
        }
    }

    if let Some(symbols) = &macho.symbols {
        for symbol in symbols {
            let (name, _) = symbol?;

            if target_triple != "aarch64-apple-darwin"
                && (MACHO_BANNED_SYMBOLS_NON_AARCH64.contains(&name))
            {
                errors.push(format!(
                    "{} references unallowed symbol {}",
                    path.display(),
                    name
                ));
            }
        }
    }

    Ok((errors, seen_dylibs))
}

fn validate_pe(path: &Path, pe: &goblin::pe::PE) -> Result<Vec<String>> {
    let mut errors = vec![];

    for lib in &pe.libraries {
        if !PE_ALLOWED_LIBRARIES.contains(lib) {
            errors.push(format!("{} loads illegal library {}", path.display(), lib));
        }
    }

    Ok(errors)
}

/// Attempt to parse data as an object file and validate it.
fn validate_possible_object_file(
    json: &PythonJsonMain,
    python_major_minor: &str,
    triple: &str,
    path: &Path,
    data: &[u8],
) -> Result<(Vec<String>, BTreeSet<String>)> {
    let mut errors = vec![];
    let mut seen_dylibs = BTreeSet::new();

    if let Ok(object) = goblin::Object::parse(&data) {
        match object {
            goblin::Object::Elf(elf) => {
                errors.extend(validate_elf(
                    json,
                    triple,
                    python_major_minor,
                    path.as_ref(),
                    &elf,
                    &data,
                )?);
            }
            goblin::Object::Mach(mach) => match mach {
                goblin::mach::Mach::Binary(macho) => {
                    let (local_errors, local_seen_dylibs) =
                        validate_macho(triple, path.as_ref(), &macho, &data)?;

                    errors.extend(local_errors);
                    seen_dylibs.extend(local_seen_dylibs);
                }
                goblin::mach::Mach::Fat(_) => {
                    if path.to_string_lossy() != "python/build/lib/libclang_rt.osx.a" {
                        errors.push(format!("unexpected fat mach-o binary: {}", path.display()));
                    }
                }
            },
            goblin::Object::PE(pe) => {
                // We don't care about the wininst-*.exe distutils executables.
                if !path.to_string_lossy().contains("wininst-") {
                    errors.extend(validate_pe(path.as_ref(), &pe)?);
                }
            }
            _ => {}
        }
    }

    Ok((errors, seen_dylibs))
}

fn validate_json(json: &PythonJsonMain, triple: &str, is_debug: bool) -> Result<Vec<String>> {
    let mut errors = vec![];

    if json.version != "7" {
        errors.push(format!(
            "expected version 7 in PYTHON.json; got {}",
            json.version
        ));
    }

    // Distributions built with Apple SDKs should have SDK metadata.
    if triple.contains("-apple-") {
        if json.apple_sdk_canonical_name.is_none() {
            errors.push("JSON missing apple_sdk_canonical_name on Apple triple".to_string());
        }
        if json.apple_sdk_deployment_target.is_none() {
            errors.push("JSON missing apple_sdk_deployment_target on Apple triple".to_string());
        }
        if json.apple_sdk_platform.is_none() {
            errors.push("JSON missing apple_sdk_platform on Apple triple".to_string());
        }
        if json.apple_sdk_version.is_none() {
            errors.push("JSON missing apple_sdk_version on Apple triple".to_string());
        }
    }

    let wanted_platform_tag = PLATFORM_TAG_BY_TRIPLE
        .get(triple)
        .ok_or_else(|| anyhow!("platform tag not defined for triple {}", triple))?
        .clone();

    if json.python_platform_tag != wanted_platform_tag {
        errors.push(format!(
            "wanted platform tag {}; got {}",
            wanted_platform_tag, json.python_platform_tag
        ));
    }

    if is_debug
        && !json
            .python_config_vars
            .get("abiflags")
            .unwrap()
            .contains('d')
    {
        errors.push("abiflags does not contain 'd'".to_string());
    }

    for extension in json.build_info.extensions.keys() {
        if GLOBALLY_BANNED_EXTENSIONS.contains(&extension.as_str()) {
            errors.push(format!("banned extension detected: {}", extension));
        }
    }

    Ok(errors)
}

fn validate_distribution(dist_path: &Path) -> Result<Vec<String>> {
    let mut errors = vec![];
    let mut seen_dylibs = BTreeSet::new();
    let mut seen_paths = BTreeSet::new();
    let mut seen_symlink_targets = BTreeSet::new();

    let dist_filename = dist_path
        .file_name()
        .expect("unable to obtain filename")
        .to_string_lossy();

    let triple = RECOGNIZED_TRIPLES
        .iter()
        .find(|triple| {
            dist_path
                .to_string_lossy()
                .contains(&format!("-{}-", triple))
        })
        .ok_or_else(|| {
            anyhow!(
                "could not identify triple from distribution filename: {}",
                dist_path.display()
            )
        })?;

    let python_major_minor = if dist_filename.starts_with("cpython-3.8.") {
        "3.8"
    } else if dist_filename.starts_with("cpython-3.9.") {
        "3.9"
    } else if dist_filename.starts_with("cpython-3.10.") {
        "3.10"
    } else {
        return Err(anyhow!("could not parse Python version from filename"));
    };

    let is_debug = dist_filename.contains("-debug-");

    let mut tf = crate::open_distribution_archive(&dist_path)?;

    // First entry in archive should be python/PYTHON.json.
    let mut entries = tf.entries()?;

    let mut wanted_python_paths = BTreeSet::new();
    let mut json = None;

    let mut entry = entries.next().unwrap()?;
    if entry.path()?.display().to_string() == "python/PYTHON.json" {
        seen_paths.insert(entry.path()?.to_path_buf());

        let mut data = Vec::new();
        entry.read_to_end(&mut data)?;
        json = Some(parse_python_json(&data).context("parsing PYTHON.json")?);
        errors.extend(validate_json(json.as_ref().unwrap(), triple, is_debug)?);

        wanted_python_paths.extend(
            json.as_ref()
                .unwrap()
                .python_paths
                .values()
                .map(|x| format!("python/{}", x)),
        );
    } else {
        errors.push(format!(
            "1st archive entry should be for python/PYTHON.json; got {}",
            entry.path()?.display()
        ));
    }

    for entry in entries {
        let mut entry = entry.map_err(|e| anyhow!("failed to iterate over archive: {}", e))?;
        let path = entry.path()?.to_path_buf();

        seen_paths.insert(path.clone());

        if let Some(link_name) = entry.link_name()? {
            seen_symlink_targets.insert(path.parent().unwrap().join(link_name));
        }

        // If this path starts with a path referenced in wanted_python_paths,
        // remove the prefix from wanted_python_paths so we don't error on it
        // later.
        let removals = wanted_python_paths
            .iter()
            .filter(|prefix| path.starts_with(prefix))
            .map(|x| x.to_string())
            .collect::<Vec<_>>();
        for p in removals {
            wanted_python_paths.remove(&p);
        }

        let mut data = Vec::new();
        entry.read_to_end(&mut data)?;

        let (local_errors, local_seen_dylibs) = validate_possible_object_file(
            json.as_ref().unwrap(),
            python_major_minor,
            &triple,
            &path,
            &data,
        )?;
        errors.extend(local_errors);
        seen_dylibs.extend(local_seen_dylibs);

        // Descend into archive files (static libraries are archive files and members
        // are usually object files).
        if let Ok(archive) = goblin::archive::Archive::parse(&data) {
            for member in archive.members() {
                let member_data = archive
                    .extract(member, &data)
                    .with_context(|| format!("extracting {} from {}", member, path.display()))?;

                let member_path = path.with_file_name(format!(
                    "{}:{}",
                    path.file_name().unwrap().to_string_lossy(),
                    member
                ));

                let (local_errors, local_seen_dylibs) = validate_possible_object_file(
                    json.as_ref().unwrap(),
                    python_major_minor,
                    &triple,
                    &member_path,
                    &member_data,
                )?;
                errors.extend(local_errors);
                seen_dylibs.extend(local_seen_dylibs);
            }
        }

        if path == PathBuf::from("python/PYTHON.json") {
            errors.push("python/PYTHON.json seen twice".to_string());
        }
    }

    for path in seen_symlink_targets {
        if !seen_paths.contains(&path) {
            errors.push(format!(
                "symlink target {} referenced in archive but not found",
                path.display()
            ));
        }
    }

    for path in wanted_python_paths {
        errors.push(format!(
            "path prefix {} seen in python_paths does not appear in archive",
            path
        ));
    }

    let wanted_dylibs = BTreeSet::from_iter(
        allowed_dylibs_for_triple(triple)
            .iter()
            .filter(|d| d.required)
            .map(|d| d.name.clone()),
    );

    for lib in wanted_dylibs.difference(&seen_dylibs) {
        errors.push(format!("required library dependency {} not seen", lib));
    }

    if triple.contains("-windows-") && dist_path.to_string_lossy().contains("-static-") {
        for path in WANTED_WINDOWS_STATIC_PATHS.difference(&seen_paths) {
            errors.push(format!("required path {} not seen", path.display()));
        }
    }

    Ok(errors)
}

fn verify_distribution_behavior(dist_path: &Path) -> Result<Vec<String>> {
    let mut errors = vec![];

    let temp_dir = tempfile::TempDir::new()?;

    let mut tf = crate::open_distribution_archive(dist_path)?;

    tf.unpack(temp_dir.path())?;

    let python_json_path = temp_dir.path().join("python").join("PYTHON.json");
    let python_json_data = std::fs::read(&python_json_path)?;
    let python_json = parse_python_json(&python_json_data)?;

    let python_exe = temp_dir.path().join("python").join(python_json.python_exe);

    let test_file = temp_dir.path().join("verify.py");
    std::fs::write(&test_file, PYTHON_VERIFICATIONS.as_bytes())?;

    eprintln!("  running interpreter tests (output should follow)");
    let output = duct::cmd(&python_exe, &[test_file.display().to_string()])
        .stdout_to_stderr()
        .unchecked()
        .run()?;

    if !output.status.success() {
        errors.push("errors running interpreter tests".to_string());
    }

    Ok(errors)
}

pub fn command_validate_distribution(args: &ArgMatches) -> Result<()> {
    let run = args.is_present("run");

    let mut success = true;

    for path in args.values_of("path").unwrap() {
        let path = PathBuf::from(path);
        println!("validating {}", path.display());
        let mut errors = validate_distribution(&path)?;

        if run {
            errors.extend(verify_distribution_behavior(&path)?.into_iter());
        }

        if errors.is_empty() {
            println!("  {} OK", path.display());
        } else {
            for error in errors {
                println!("  error: {}", error);
            }

            success = false;
        }
    }

    if success {
        Ok(())
    } else {
        Err(anyhow!("errors found"))
    }
}
