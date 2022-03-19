// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

use {
    crate::release::{produce_install_only, RELEASE_TRIPLES},
    anyhow::{anyhow, Result},
    clap::ArgMatches,
    futures::StreamExt,
    octocrab::{
        models::{repos::Release, workflows::WorkflowListArtifact},
        Octocrab, OctocrabBuilder,
    },
    rayon::prelude::*,
    sha2::{Digest, Sha256},
    std::{
        collections::{BTreeMap, BTreeSet, HashMap},
        io::Read,
        path::PathBuf,
    },
    zip::ZipArchive,
};

async fn fetch_artifact(client: &Octocrab, artifact: WorkflowListArtifact) -> Result<bytes::Bytes> {
    println!("downloading {}", artifact.name);
    let res = client
        .execute(client.request_builder(artifact.archive_download_url, reqwest::Method::GET))
        .await?;

    Ok(res.bytes().await?)
}

async fn upload_release_artifact(
    client: &Octocrab,
    release: &Release,
    filename: &str,
    data: Vec<u8>,
    dry_run: bool,
) -> Result<()> {
    if release.assets.iter().any(|asset| asset.name == filename) {
        println!("release asset {} already present; skipping", filename);
        return Ok(());
    }

    let mut url = release.upload_url.clone();
    let path = url.path().to_string();

    if let Some(path) = path.strip_suffix("%7B") {
        url.set_path(path);
    }

    url.query_pairs_mut().clear().append_pair("name", filename);

    println!("uploading to {}", url);

    let request = client
        .request_builder(url, reqwest::Method::POST)
        .header("Content-Length", data.len())
        .header("Content-Type", "application/x-tar")
        .body(data);

    if dry_run {
        return Ok(());
    }

    let response = client.execute(request).await?;

    if !response.status().is_success() {
        return Err(anyhow!("HTTP {}", response.status()));
    }

    Ok(())
}

pub async fn command_fetch_release_distributions(args: &ArgMatches) -> Result<()> {
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

    let mut workflow_names = HashMap::new();

    let workflow_ids = workflows
        .list()
        .send()
        .await?
        .into_iter()
        .map(|wf| {
            workflow_names.insert(wf.id.clone(), wf.name);

            wf.id
        })
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
                .ok_or_else(|| {
                    anyhow!(
                        "could not find workflow run for commit for workflow {}",
                        workflow_names
                            .get(&workflow_id)
                            .expect("should have workflow name")
                    )
                })?,
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
            ) || artifact.name.contains("install-only")
            {
                continue;
            }

            fs.push(fetch_artifact(&client, artifact));
        }
    }

    let mut buffered = futures::stream::iter(fs).buffer_unordered(4);

    let mut install_paths = vec![];

    while let Some(res) = buffered.next().await {
        let data = res?;

        let mut za = ZipArchive::new(std::io::Cursor::new(data))?;
        for i in 0..za.len() {
            let mut zf = za.by_index(i)?;

            let name = zf.name().to_string();

            if let Some((triple, release)) = RELEASE_TRIPLES.iter().find_map(|(triple, release)| {
                if name.contains(triple) {
                    Some((triple, release))
                } else {
                    None
                }
            }) {
                let stripped_name = if let Some(s) = name.strip_suffix(".tar.zst") {
                    s
                } else {
                    println!("{} not a .tar.zst artifact", name);
                    continue;
                };

                let stripped_name = &stripped_name[0..stripped_name.len() - "-YYYYMMDDTHHMM".len()];

                let triple_start = stripped_name
                    .find(triple)
                    .expect("validated triple presence above");

                let build_suffix = &stripped_name[triple_start + triple.len() + 1..];

                if !release
                    .suffixes
                    .iter()
                    .any(|suffix| build_suffix == *suffix)
                {
                    println!("{} not a release artifact for triple", name);
                    continue;
                }

                let dest_path = dest_dir.join(&name);
                let mut buf = vec![];
                zf.read_to_end(&mut buf)?;
                std::fs::write(&dest_path, &buf)?;

                println!("releasing {}", name);

                if build_suffix == release.install_only_suffix {
                    install_paths.push(dest_path);
                }
            } else {
                println!("{} does not match any registered release triples", name);
            }
        }
    }

    install_paths
        .par_iter()
        .try_for_each(|path| -> Result<()> {
            println!(
                "producing install_only archive from {}",
                path.file_name()
                    .expect("should have file name")
                    .to_string_lossy()
            );

            let dest_path = produce_install_only(&path)?;

            println!(
                "releasing {}",
                dest_path
                    .file_name()
                    .expect("should have file name")
                    .to_string_lossy()
            );

            Ok(())
        })?;

    Ok(())
}

pub async fn command_upload_release_distributions(args: &ArgMatches) -> Result<()> {
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
    let dry_run = args.is_present("dry_run");

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

    let mut wanted_filenames = BTreeMap::new();
    for version in python_versions {
        for (triple, release) in RELEASE_TRIPLES.iter() {
            if let Some(req) = &release.python_version_requirement {
                let python_version = semver::Version::parse(version)?;
                if !req.matches(&python_version) {
                    continue;
                }
            }

            for suffix in &release.suffixes {
                wanted_filenames.insert(
                    format!(
                        "cpython-{}-{}-{}-{}.tar.zst",
                        version, triple, suffix, datetime
                    ),
                    format!(
                        "cpython-{}+{}-{}-{}-full.tar.zst",
                        version, tag, triple, suffix
                    ),
                );
            }

            wanted_filenames.insert(
                format!(
                    "cpython-{}-{}-install_only-{}.tar.gz",
                    version, triple, datetime
                ),
                format!("cpython-{}+{}-{}-install_only.tar.gz", version, tag, triple),
            );
        }
    }

    let missing = wanted_filenames
        .keys()
        .filter(|x| !filenames.contains(*x))
        .collect::<Vec<_>>();

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

    let mut digests = BTreeMap::new();

    for (source, dest) in wanted_filenames {
        if !filenames.contains(&source) {
            continue;
        }

        let file_data = std::fs::read(dist_dir.join(&source))?;

        let mut digest = Sha256::new();
        digest.update(&file_data);

        let digest = hex::encode(digest.finalize());

        digests.insert(dest.clone(), digest.clone());

        upload_release_artifact(&client, &release, &dest, file_data, dry_run).await?;
        upload_release_artifact(
            &client,
            &release,
            &format!("{}.sha256", dest),
            format!("{}\n", digest).into_bytes(),
            dry_run,
        )
        .await?;
    }

    let shasums = digests
        .iter()
        .map(|(filename, digest)| format!("{}  {}\n", digest, filename))
        .collect::<Vec<_>>()
        .join("");

    std::fs::write(dist_dir.join("SHA256SUMS"), shasums.as_bytes())?;

    upload_release_artifact(
        &client,
        &release,
        "SHA256SUMS",
        shasums.into_bytes(),
        dry_run,
    )
    .await?;

    Ok(())
}
