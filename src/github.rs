// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

use {
    anyhow::{anyhow, Result},
    clap::ArgMatches,
    octocrab::OctocrabBuilder,
    once_cell::sync::Lazy,
    serde::Deserialize,
    std::{collections::HashMap, io::Read, path::PathBuf},
    zip::ZipArchive,
};

static SUFFIXES_BY_TRIPLE: Lazy<HashMap<&'static str, Vec<&'static str>>> = Lazy::new(|| {
    let mut h = HashMap::new();

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
    h.insert("x86_64-unknown-linux-musl", linux_suffixes_nopgo.clone());

    h
});

#[derive(Clone, Debug, Deserialize)]
struct Artifact {
    archive_download_url: String,
    created_at: String,
    expired: bool,
    expires_at: String,
    id: u64,
    name: String,
    node_id: String,
    size_in_bytes: u64,
    updated_at: String,
    url: String,
}

#[derive(Clone, Debug, Deserialize)]
struct Artifacts {
    artifacts: Vec<Artifact>,
    total_count: u64,
}

pub async fn command_fetch_release_distributions(args: &ArgMatches<'_>) -> Result<()> {
    let dest_dir = PathBuf::from(args.value_of("dest").expect("dest directory should be set"));
    let org = args
        .value_of("organization")
        .expect("organization should be set");
    let repo = args.value_of("repo").expect("repo should be set");

    let client = OctocrabBuilder::new()
        .personal_token(
            args.value_of("token")
                .expect("token should be required argument")
                .to_string(),
        )
        .build()?;

    let workflows = client.workflows(org, repo);

    let workflow_ids = workflows
        .list()
        .send()
        .await?
        .into_iter()
        .map(|wf| wf.id)
        .collect::<Vec<_>>();

    let mut runs: Vec<octocrab::models::workflows::Run> = vec![];

    for workflow_id in workflow_ids {
        runs.push(
            workflows
                .list_runs(format!("{}", workflow_id))
                .event("push")
                .status("success")
                .send()
                .await?
                .into_iter()
                .find(|run| {
                    run.head_sha == args.value_of("commit").expect("commit should be defined")
                })
                .ok_or_else(|| anyhow!("could not find workflow run for commit"))?,
        );
    }

    let mut fs = vec![];

    for run in runs {
        let res = client
            .execute(client.request_builder(run.artifacts_url, reqwest::Method::GET))
            .await?;

        if !res.status().is_success() {
            return Err(anyhow!("non-HTTP 200 fetching artifacts"));
        }

        let artifacts: Artifacts = res.json().await?;

        for artifact in artifacts.artifacts {
            if matches!(
                artifact.name.as_str(),
                "pythonbuild" | "sccache" | "toolchain"
            ) {
                continue;
            }

            println!("downloading {}", artifact.name);
            let res = client
                .execute(
                    client.request_builder(artifact.archive_download_url, reqwest::Method::GET),
                )
                .await?;

            fs.push(res.bytes());
        }
    }

    for res in futures::future::join_all(fs).await {
        let data = res?;

        let mut za = ZipArchive::new(std::io::Cursor::new(data))?;
        for i in 0..za.len() {
            let mut zf = za.by_index(i)?;

            let name = zf.name().to_string();

            if let Some(suffixes) = SUFFIXES_BY_TRIPLE.iter().find_map(|(triple, suffixes)| {
                if name.contains(triple) {
                    Some(suffixes)
                } else {
                    None
                }
            }) {
                if suffixes.iter().any(|suffix| name.contains(suffix)) {
                    let dest_path = dest_dir.join(&name);
                    let mut buf = vec![];
                    zf.read_to_end(&mut buf)?;
                    std::fs::write(&dest_path, &buf)?;

                    println!("releasing {}", name);
                } else {
                    println!("{} not a release artifact for triple", name);
                }
            } else {
                println!("{} does not match any registered release triples", name);
            }
        }
    }

    Ok(())
}
