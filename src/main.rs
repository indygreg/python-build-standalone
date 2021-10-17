// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

mod github;
mod json;
mod macho;
mod validation;

use {
    anyhow::{anyhow, Context, Result},
    clap::{App, AppSettings, Arg, SubCommand},
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
    let app = App::new("Python Build")
        .setting(AppSettings::ArgRequiredElseHelp)
        .version("0.1")
        .author("Gregory Szorc <gregory.szorc@gmail.com>")
        .about("Perform tasks related to building Python distributions");
    let app = app.subcommand(
        SubCommand::with_name("fetch-release-distributions")
            .about("Fetch builds from GitHub Actions that are release artifacts")
            .arg(
                Arg::with_name("token")
                    .long("--token")
                    .required(true)
                    .takes_value(true)
                    .help("GitHub API token"),
            )
            .arg(
                Arg::with_name("commit")
                    .long("--commit")
                    .takes_value(true)
                    .help("Git commit whose artifacts to fetch"),
            )
            .arg(
                Arg::with_name("dest")
                    .long("dest")
                    .required(true)
                    .takes_value(true)
                    .help("Destination directory"),
            )
            .arg(
                Arg::with_name("organization")
                    .long("--org")
                    .takes_value(true)
                    .default_value("indygreg")
                    .help("GitHub organization"),
            )
            .arg(
                Arg::with_name("repo")
                    .long("--repo")
                    .takes_value(true)
                    .default_value("python-build-standalone")
                    .help("GitHub repository name"),
            ),
    );

    let app = app.subcommand(
        SubCommand::with_name("upload-release-distributions")
            .about("Upload release distributions to a GitHub release")
            .arg(
                Arg::with_name("token")
                    .long("--token")
                    .required(true)
                    .takes_value(true)
                    .help("GitHub API token"),
            )
            .arg(
                Arg::with_name("dist")
                    .long("--dist")
                    .required(true)
                    .takes_value(true)
                    .help("Directory with release artifacts"),
            )
            .arg(
                Arg::with_name("datetime")
                    .long("--datetime")
                    .required(true)
                    .takes_value(true)
                    .help("Date/time tag associated with builds"),
            )
            .arg(
                Arg::with_name("tag")
                    .long("--tag")
                    .required(true)
                    .takes_value(true)
                    .help("Release tag"),
            )
            .arg(
                Arg::with_name("ignore_missing")
                    .long("--ignore-missing")
                    .help("Continue even if there are missing artifacts"),
            )
            .arg(
                Arg::with_name("organization")
                    .long("--org")
                    .takes_value(true)
                    .default_value("indygreg")
                    .help("GitHub organization"),
            )
            .arg(
                Arg::with_name("repo")
                    .long("--repo")
                    .takes_value(true)
                    .default_value("python-build-standalone")
                    .help("GitHub repository name"),
            ),
    );

    let app = app.subcommand(
        SubCommand::with_name("validate-distribution")
            .about("Ensure a distribution archive conforms to standards")
            .arg(
                Arg::with_name("run")
                    .long("--run")
                    .help("Run the interpreter to verify behavior"),
            )
            .arg(
                Arg::with_name("path")
                    .help("Path to tar.zst file to validate")
                    .multiple(true)
                    .required(true),
            ),
    );

    let matches = app.get_matches();

    match matches.subcommand() {
        ("fetch-release-distributions", Some(args)) => {
            tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .unwrap()
                .block_on(crate::github::command_fetch_release_distributions(args))
        }
        ("upload-release-distributions", Some(args)) => {
            tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .unwrap()
                .block_on(crate::github::command_upload_release_distributions(args))
        }
        ("validate-distribution", Some(args)) => {
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
