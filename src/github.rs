// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

use {
    crate::release::RELEASE_TRIPLES,
    anyhow::{anyhow, Result},
    clap::ArgMatches,
    futures::StreamExt,
    octocrab::{models::workflows::WorkflowListArtifact, Octocrab, OctocrabBuilder},
    std::{collections::BTreeSet, io::Read, path::PathBuf},
    zip::ZipArchive,
};

async fn fetch_artifact(client: &Octocrab, artifact: WorkflowListArtifact) -> Result<bytes::Bytes> {
    println!("downloading {}", artifact.name);
    let res = client
        .execute(client.request_builder(artifact.archive_download_url, reqwest::Method::GET))
        .await?;

    Ok(res.bytes().await?)
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
        let page = client
            .actions()
            .list_workflow_run_artifacts(org, repo, run.id)
            .send()
            .await?;

        let artifacts = client
            .all_pages::<octocrab::models::workflows::WorkflowListArtifact>(
                page.value.expect("untagged request should have page"),
            )
            .await?;

        for artifact in artifacts {
            if matches!(
                artifact.name.as_str(),
                "pythonbuild" | "sccache" | "toolchain"
            ) {
                continue;
            }

            fs.push(fetch_artifact(&client, artifact));
        }
    }

    let mut buffered = futures::stream::iter(fs).buffer_unordered(4);

    while let Some(res) = buffered.next().await {
        let data = res?;

        let mut za = ZipArchive::new(std::io::Cursor::new(data))?;
        for i in 0..za.len() {
            let mut zf = za.by_index(i)?;

            let name = zf.name().to_string();

            if let Some(release) = RELEASE_TRIPLES.iter().find_map(|(triple, release)| {
                if name.contains(triple) {
                    Some(release)
                } else {
                    None
                }
            }) {
                if release.suffixes.iter().any(|suffix| name.contains(suffix)) {
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

pub async fn command_upload_release_distributions(args: &ArgMatches<'_>) -> Result<()> {
    let dist_dir = PathBuf::from(args.value_of("dist").expect("dist should be specified"));
    let datetime = args
        .value_of("datetime")
        .expect("datetime should be specified");
    let tag = args.value_of("tag").expect("tag should be specified");
    let ignore_missing = args.is_present("ignore_missing");
    let token = args
        .value_of("token")
        .expect("token should be specified")
        .to_string();
    let organization = args
        .value_of("organization")
        .expect("organization should be specified");
    let repo = args.value_of("repo").expect("repo should be specified");

    let mut filenames = std::fs::read_dir(&dist_dir)?
        .into_iter()
        .map(|x| {
            let path = x?.path();
            let filename = path
                .file_name()
                .ok_or_else(|| anyhow!("unable to resolve file name"))?;

            Ok(filename.to_string_lossy().to_string())
        })
        .collect::<Result<Vec<_>>>()?;
    filenames.sort();

    let filenames = filenames
        .into_iter()
        .filter(|x| x.contains(datetime) && x.starts_with("cpython-"))
        .collect::<BTreeSet<_>>();

    let mut python_versions = BTreeSet::new();
    for filename in &filenames {
        let parts = filename.split('-').collect::<Vec<_>>();
        python_versions.insert(parts[1]);
    }

    let mut wanted_filenames = BTreeSet::new();
    for version in python_versions {
        for (triple, release) in RELEASE_TRIPLES.iter() {
            for suffix in &release.suffixes {
                let extension = if suffix.contains("install_only") {
                    "tar.gz"
                } else {
                    "tar.zst"
                };

                wanted_filenames.insert(format!(
                    "cpython-{}-{}-{}-{}.{}",
                    version, triple, suffix, datetime, extension
                ));
            }
        }
    }

    let missing = wanted_filenames.difference(&filenames).collect::<Vec<_>>();
    for f in &missing {
        println!("missing release artifact: {}", f);
    }
    if !missing.is_empty() && !ignore_missing {
        return Err(anyhow!("missing release artifacts"));
    }

    let client = OctocrabBuilder::new().personal_token(token).build()?;
    let repo = client.repos(organization, repo);
    let releases = repo.releases();

    let release = if let Ok(release) = releases.get_by_tag(tag).await {
        release
    } else {
        return Err(anyhow!(
            "release {} does not exist; create it via GitHub web UI",
            tag
        ));
    };

    for filename in wanted_filenames.intersection(&filenames) {
        if release.assets.iter().any(|asset| &asset.name == filename) {
            println!("release asset {} already present; skipping", filename);
            continue;
        }

        let path = dist_dir.join(filename);
        let file_data = std::fs::read(&path)?;

        let mut url = release.upload_url.clone();
        let path = url.path().to_string();

        if let Some(path) = path.strip_suffix("%7B") {
            url.set_path(path);
        }

        url.query_pairs_mut()
            .clear()
            .append_pair("name", filename.as_str());

        println!("uploading {} to {}", filename, url);

        let request = client
            .request_builder(url, reqwest::Method::POST)
            .header("Content-Length", file_data.len())
            .header("Content-Type", "application/x-tar")
            .body(file_data);

        let response = client.execute(request).await?;

        if !response.status().is_success() {
            return Err(anyhow!("HTTP {}", response.status()));
        }
    }

    Ok(())
}
