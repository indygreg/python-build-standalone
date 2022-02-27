// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

mod github;
mod json;
mod macho;
mod release;
mod validation;

use {
    anyhow::{anyhow, Context, Result},
    clap::{Arg, Command},
    std::{io::Read, path::Path},
};

pub fn open_distribution_archive(path: &Path) -> Result<tar::Archive<impl Read>> {
    let fh =
        std::fs::File::open(path).with_context(|| format!("unable to open {}", path.display()))?;

    let reader = std::io::BufReader::new(fh);
    let dctx = zstd::stream::Decoder::new(reader)?;

    Ok(tar::Archive::new(dctx))
}

fn main_impl() -> Result<()> {
    let app = Command::new("Python Build")
        .arg_required_else_help(true)
        .version("0.1")
        .author("Gregory Szorc <gregory.szorc@gmail.com>")
        .about("Perform tasks related to building Python distributions");
    let app = app.subcommand(
        Command::new("fetch-release-distributions")
            .about("Fetch builds from GitHub Actions that are release artifacts")
            .arg(
                Arg::new("token")
                    .long("--token")
                    .required(true)
                    .takes_value(true)
                    .help("GitHub API token"),
            )
            .arg(
                Arg::new("commit")
                    .long("--commit")
                    .takes_value(true)
                    .help("Git commit whose artifacts to fetch"),
            )
            .arg(
                Arg::new("dest")
                    .long("dest")
                    .required(true)
                    .takes_value(true)
                    .help("Destination directory"),
            )
            .arg(
                Arg::new("organization")
                    .long("--org")
                    .takes_value(true)
                    .default_value("indygreg")
                    .help("GitHub organization"),
            )
            .arg(
                Arg::new("repo")
                    .long("--repo")
                    .takes_value(true)
                    .default_value("python-build-standalone")
                    .help("GitHub repository name"),
            ),
    );

    let app = app.subcommand(
        Command::new("convert-install-only")
            .about("Convert a .tar.zst archive to an install_only tar.gz archive")
            .arg(
                Arg::new("path")
                    .required(true)
                    .takes_value(true)
                    .help("Path of archive to convert"),
            ),
    );

    let app = app.subcommand(
        Command::new("upload-release-distributions")
            .about("Upload release distributions to a GitHub release")
            .arg(
                Arg::new("token")
                    .long("--token")
                    .required(true)
                    .takes_value(true)
                    .help("GitHub API token"),
            )
            .arg(
                Arg::new("dist")
                    .long("--dist")
                    .required(true)
                    .takes_value(true)
                    .help("Directory with release artifacts"),
            )
            .arg(
                Arg::new("datetime")
                    .long("--datetime")
                    .required(true)
                    .takes_value(true)
                    .help("Date/time tag associated with builds"),
            )
            .arg(
                Arg::new("dry_run")
                    .short('n')
                    .help("Dry run mode; do not actually upload"),
            )
            .arg(
                Arg::new("tag")
                    .long("--tag")
                    .required(true)
                    .takes_value(true)
                    .help("Release tag"),
            )
            .arg(
                Arg::new("ignore_missing")
                    .long("--ignore-missing")
                    .help("Continue even if there are missing artifacts"),
            )
            .arg(
                Arg::new("organization")
                    .long("--org")
                    .takes_value(true)
                    .default_value("indygreg")
                    .help("GitHub organization"),
            )
            .arg(
                Arg::new("repo")
                    .long("--repo")
                    .takes_value(true)
                    .default_value("python-build-standalone")
                    .help("GitHub repository name"),
            ),
    );

    let app = app.subcommand(
        Command::new("validate-distribution")
            .about("Ensure a distribution archive conforms to standards")
            .arg(
                Arg::new("run")
                    .long("--run")
                    .help("Run the interpreter to verify behavior"),
            )
            .arg(
                Arg::new("path")
                    .help("Path to tar.zst file to validate")
                    .multiple_occurrences(true)
                    .multiple_values(true)
                    .required(true),
            ),
    );

    let matches = app.get_matches();

    match matches.subcommand() {
        Some(("convert-install-only", args)) => {
            let path = args.value_of("path").expect("path argument is required");

            let dest_path =
                crate::release::produce_install_only(std::path::PathBuf::from(path).as_path())?;
            println!("wrote {}", dest_path.display());

            Ok(())
        }
        Some(("fetch-release-distributions", args)) => {
            tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .unwrap()
                .block_on(crate::github::command_fetch_release_distributions(args))
        }
        Some(("upload-release-distributions", args)) => {
            tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .unwrap()
                .block_on(crate::github::command_upload_release_distributions(args))
        }
        Some(("validate-distribution", args)) => {
            crate::validation::command_validate_distribution(args)
        }
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
