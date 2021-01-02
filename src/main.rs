// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

mod macho;

use {
    crate::macho::*,
    anyhow::{anyhow, Context, Result},
    clap::{App, AppSettings, Arg, ArgMatches, SubCommand},
    goblin::mach::load_command::CommandVariant,
    lazy_static::lazy_static,
    scroll::Pread,
    std::{
        convert::TryInto,
        io::Read,
        path::{Path, PathBuf},
    },
};

lazy_static! {
    static ref MACHO_ALLOWED_DYLIBS: Vec<MachOAllowedDylib> = {
        [
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.8.dylib".to_string(),
                max_compatibility_version: "3.8.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.8d.dylib".to_string(),
                max_compatibility_version: "3.8.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.9.dylib".to_string(),
                max_compatibility_version: "3.9.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "@executable_path/../lib/libpython3.9d.dylib".to_string(),
                max_compatibility_version: "3.9.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/AppKit.framework/Versions/C/AppKit".to_string(),
                max_compatibility_version: "45.0.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/ApplicationServices.framework/Versions/A/ApplicationServices".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/Carbon.framework/Versions/A/Carbon".to_string(),
                max_compatibility_version: "2.0.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name:
                    "/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation"
                        .to_string(),
                max_compatibility_version: "150.0.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/CoreGraphics.framework/Versions/A/CoreGraphics".to_string(),
                max_compatibility_version: "64.0.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/CoreServices.framework/Versions/A/CoreServices".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/CoreText.framework/Versions/A/CoreText".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/Foundation.framework/Versions/C/Foundation".to_string(),
                max_compatibility_version: "300.0.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "/System/Library/Frameworks/SystemConfiguration.framework/Versions/A/SystemConfiguration".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "/usr/lib/libedit.3.dylib".to_string(),
                max_compatibility_version: "2.0.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "/usr/lib/libncurses.5.4.dylib".to_string(),
                max_compatibility_version: "5.4.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "/usr/lib/libobjc.A.dylib".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "/usr/lib/libpanel.5.4.dylib".to_string(),
                max_compatibility_version: "5.4.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "/usr/lib/libSystem.B.dylib".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
            },
            MachOAllowedDylib {
                name: "/usr/lib/libz.1.dylib".to_string(),
                max_compatibility_version: "1.0.0".try_into().unwrap(),
            },
        ]
        .to_vec()
    };
}

fn validate_macho(path: &Path, macho: &goblin::mach::MachO, bytes: &[u8]) -> Result<Vec<String>> {
    let mut errors = vec![];

    for load_command in &macho.load_commands {
        match load_command.command {
            CommandVariant::LoadDylib(command)
            | CommandVariant::LoadUpwardDylib(command)
            | CommandVariant::ReexportDylib(command)
            | CommandVariant::LoadWeakDylib(command)
            | CommandVariant::LazyLoadDylib(command) => {
                let lib = bytes.pread::<&str>(load_command.offset + command.dylib.name as usize)?;

                if let Some(entry) = MACHO_ALLOWED_DYLIBS.iter().find(|l| l.name == lib) {
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
                } else {
                    errors.push(format!("{} loads illegal library {}", path.display(), lib));
                }
            }
            _ => {}
        }
    }

    Ok(errors)
}

fn validate_distribution(path: &Path) -> Result<Vec<String>> {
    let mut errors = vec![];

    let fh =
        std::fs::File::open(&path).with_context(|| format!("unable to open {}", path.display()))?;

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
                goblin::Object::Mach(mach) => match mach {
                    goblin::mach::Mach::Binary(macho) => {
                        errors.extend(validate_macho(path.as_ref(), &macho, &data)?);
                    }
                    goblin::mach::Mach::Fat(_) => {
                        errors.push(format!("unexpected fat mach-o binary: {}", path.display()));
                    }
                },
                _ => {}
            }
        }
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
