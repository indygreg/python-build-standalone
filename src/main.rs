// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

mod json;
mod macho;

use {
    crate::{json::*, macho::*},
    anyhow::{anyhow, Context, Result},
    clap::{App, AppSettings, Arg, ArgMatches, SubCommand},
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
    "thumbv7k-apple-watchos",
    "x86_64-apple-darwin",
    "x86_64-apple-ios",
    "x86_64-apple-tvos",
    "x86_64-apple-watchos",
    "x86_64-pc-windows-msvc",
    "x86_64-unknown-linux-gnu",
    "x86_64-unknown-linux-musl",
];

const ELF_ALLOWED_LIBRARIES: &[&str] = &[
    // LSB set.
    "libc.so.6",
    "libcrypt.so.1",
    "libdl.so.2",
    "libm.so.6",
    "libnsl.so.1",
    "libpthread.so.0",
    "librt.so.1",
    "libutil.so.1",
    // Our set.
    "libpython3.8.so.1.0",
    "libpython3.8d.so.1.0",
    "libpython3.9.so.1.0",
    "libpython3.9d.so.1.0",
    "libpython3.10.so.1.0",
    "libpython3.10d.so.1.0",
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
    "libffi-7.dll",
    "libssl-1_1.dll",
    "libssl-1_1-x64.dll",
    "python38.dll",
    "python39.dll",
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
            "x86_64-unknown-linux-gnu",
            version_compare::Version::from("2.17").unwrap(),
        );
        // musl shouldn't link against glibc.
        versions.insert(
            "x86_64-unknown-linux-musl",
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
            ("x86_64-unknown-linux-gnu", vec!["ld-linux-x86-64.so.2"]),
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
        ("x86_64-apple-darwin", "macosx-10.9-x86_64"),
        ("x86_64-apple-ios", "iOS-x86_64"),
        ("x86_64-pc-windows-msvc", "win-amd64"),
        ("x86_64-unknown-linux-gnu", "linux-x86_64"),
        ("x86_64-unknown-linux-musl", "linux-x86_64"),
    ]
    .iter()
    .cloned()
    .collect()
});

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
    target_triple: &str,
    path: &Path,
    elf: &goblin::elf::Elf,
    bytes: &[u8],
) -> Result<Vec<String>> {
    let mut errors = vec![];

    let wanted_cpu_type = match target_triple {
        "aarch64-unknown-linux-gnu" => goblin::elf::header::EM_AARCH64,
        "armv7-unknown-linux-gnueabi" => goblin::elf::header::EM_ARM,
        "armv7-unknown-linux-gnueabihf" => goblin::elf::header::EM_ARM,
        "i686-unknown-linux-gnu" => goblin::elf::header::EM_386,
        "mips-unknown-linux-gnu" => goblin::elf::header::EM_MIPS,
        "mipsel-unknown-linux-gnu" => goblin::elf::header::EM_MIPS,
        "mips64el-unknown-linux-gnuabi64" => 0,
        "x86_64-unknown-linux-gnu" => goblin::elf::header::EM_X86_64,
        "x86_64-unknown-linux-musl" => goblin::elf::header::EM_X86_64,
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

    let mut allowed_libraries = ELF_ALLOWED_LIBRARIES.to_vec();
    if let Some(extra) = ELF_ALLOWED_LIBRARIES_BY_TRIPLE.get(target_triple) {
        allowed_libraries.extend(extra.iter());
    }

    for lib in &elf.libraries {
        if !allowed_libraries.contains(lib) {
            errors.push(format!("{} loads illegal library {}", path.display(), lib));
        }
    }

    let wanted_glibc_max_version = GLIBC_MAX_VERSION_BY_TRIPLE
        .get(target_triple)
        .expect("max glibc version not defined for target triple");

    // functionality doesn't yet support mips.
    if !target_triple.starts_with("mips") {
        let mut undefined_symbols = tugger_binary_analysis::find_undefined_elf_symbols(&bytes, elf);
        undefined_symbols.sort();

        for symbol in undefined_symbols {
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

fn validate_json(json: &PythonJsonMain, triple: &str) -> Result<Vec<String>> {
    let mut errors = vec![];

    if json.version != "6" {
        errors.push(format!(
            "expected version 6 in PYTHON.json; got {}",
            json.version
        ));
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

    Ok(errors)
}

fn validate_distribution(dist_path: &Path) -> Result<Vec<String>> {
    let mut errors = vec![];
    let mut seen_dylibs = BTreeSet::new();

    let fh = std::fs::File::open(&dist_path)
        .with_context(|| format!("unable to open {}", dist_path.display()))?;

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

    let reader = std::io::BufReader::new(fh);
    let dctx = zstd::stream::Decoder::new(reader)?;
    let mut tf = tar::Archive::new(dctx);

    for entry in tf.entries()? {
        let mut entry = entry.map_err(|e| anyhow!("failed to iterate over archive: {}", e))?;
        let path = entry.path()?.to_path_buf();

        let mut data = Vec::new();
        entry.read_to_end(&mut data)?;

        if let Ok(object) = goblin::Object::parse(&data) {
            match object {
                goblin::Object::Elf(elf) => {
                    errors.extend(validate_elf(triple, path.as_ref(), &elf, &data)?);
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
                            errors
                                .push(format!("unexpected fat mach-o binary: {}", path.display()));
                        }
                    }
                },
                goblin::Object::PE(pe) => {
                    // We don't care about the wininst-*.exe distutils executables.
                    if path.to_string_lossy().contains("wininst-") {
                        continue;
                    }

                    errors.extend(validate_pe(path.as_ref(), &pe)?);
                }
                _ => {}
            }
        }

        if path == PathBuf::from("python/PYTHON.json") {
            let json = parse_python_json(&data).context("parsing PYTHON.json")?;

            errors.extend(validate_json(&json, triple)?);
        }
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

    Ok(errors)
}

fn command_validate_distribution(args: &ArgMatches) -> Result<()> {
    let mut success = true;

    for path in args.values_of("path").unwrap() {
        let path = PathBuf::from(path);
        println!("validating {}", path.display());
        let errors = validate_distribution(&path)?;

        if errors.is_empty() {
            println!("{} OK", path.display());
        } else {
            for error in errors {
                println!("error: {}", error);
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

fn main_impl() -> Result<()> {
    let matches = App::new("Python Build")
        .setting(AppSettings::ArgRequiredElseHelp)
        .version("0.1")
        .author("Gregory Szorc <gregory.szorc@gmail.com>")
        .about("Perform tasks related to building Python distributions")
        .subcommand(
            SubCommand::with_name("validate-distribution")
                .about("Ensure a distribution archive conforms to standards")
                .arg(
                    Arg::with_name("path")
                        .help("Path to tar.zst file to validate")
                        .multiple(true)
                        .required(true),
                ),
        )
        .get_matches();

    match matches.subcommand() {
        ("validate-distribution", Some(args)) => command_validate_distribution(args),
        _ => Err(anyhow!("invalid sub-command")),
    }
}

fn main() {
    let exit_code = match main_impl() {
        Ok(()) => 0,
        Err(err) => {
            eprintln!("Error: {:?}", err);
            1
        }
    };

    std::process::exit(exit_code);
}
