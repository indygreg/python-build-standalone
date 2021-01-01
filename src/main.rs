// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

use {
    anyhow::{anyhow, Context, Result},
    clap::{App, AppSettings, Arg, ArgMatches, SubCommand},
    std::{
        io::Read,
        path::{Path, PathBuf},
    },
};

/// dylib paths that we are allowed to load.
const MACHO_ALLOW_LIBRARIES: &[&str] = &[
    "self",
    "@executable_path/../lib/libpython3.8.dylib",
    "@executable_path/../lib/libpython3.9.dylib",
    // TODO fix these references?
    "/install/lib/libpython3.8.dylib",
    "/install/lib/libpython3.8d.dylib",
    "/install/lib/libpython3.9.dylib",
    "/install/lib/libpython3.9d.dylib",
    "/System/Library/Frameworks/AppKit.framework/Versions/C/AppKit",
    "/System/Library/Frameworks/ApplicationServices.framework/Versions/A/ApplicationServices",
    "/System/Library/Frameworks/Carbon.framework/Versions/A/Carbon",
    "/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation",
    "/System/Library/Frameworks/CoreGraphics.framework/Versions/A/CoreGraphics",
    "/System/Library/Frameworks/CoreServices.framework/Versions/A/CoreServices",
    "/System/Library/Frameworks/CoreText.framework/Versions/A/CoreText",
    "/System/Library/Frameworks/Foundation.framework/Versions/C/Foundation",
    "/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit",
    "/System/Library/Frameworks/SystemConfiguration.framework/Versions/A/SystemConfiguration",
    "/usr/lib/libSystem.B.dylib",
    "/usr/lib/libedit.3.dylib",
    "/usr/lib/libncurses.5.4.dylib",
    "/usr/lib/libobjc.A.dylib",
    "/usr/lib/libpanel.5.4.dylib",
    "/usr/lib/libz.1.dylib",
];

fn validate_macho(path: &Path, macho: &goblin::mach::MachO) -> Result<()> {
    for lib in &macho.libs {
        if !MACHO_ALLOW_LIBRARIES.contains(lib) {
            return Err(anyhow!("{} loads illegal library: {}", path.display(), lib));
        }
    }

    Ok(())
}

fn command_validate_distribution(args: &ArgMatches) -> Result<()> {
    let mut success = true;

    let path = PathBuf::from(args.value_of("path").unwrap());

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
                        validate_macho(path.as_ref(), &macho)?;
                    }
                    goblin::mach::Mach::Fat(_) => {
                        println!("unexpected fat mach-o binary: {}", path.display());
                        success = false;
                    }
                },
                _ => {}
            }
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
