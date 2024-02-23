# Diff 2 releases using diffocope.
diff a b:
  diffoscope \
    --html build/diff.html \
    --exclude 'python/build/**' \
    --exclude-command '^readelf.*' \
    --exclude-command '^xxd.*' \
    --exclude-command '^objdump.*' \
    --exclude-command '^strings.*' \
    --max-report-size 9999999999 \
    --max-page-size 999999999 \
    --max-diff-block-lines 100000 \
    --max-page-diff-block-lines 100000 \
    {{ a }} {{ b }}

diff-python-json a b:
  diffoscope \
    --html build/diff.html \
    --exclude 'python/build/**' \
    --exclude 'python/install/**' \
    --max-diff-block-lines 100000 \
    --max-page-diff-block-lines 100000 \
    {{ a }} {{ b }}

cat-python-json archive:
  tar -x --to-stdout -f {{ archive }} python/PYTHON.json

# Download release artifacts from GitHub Actions
release-download-distributions token commit:
  mkdir -p dist
  cargo run --release -- fetch-release-distributions --token {{token}} --commit {{commit}} --dest dist

# Upload release artifacts to a GitHub release.
release-upload-distributions token datetime tag:
  cargo run --release -- upload-release-distributions --token {{token}} --datetime {{datetime}} --tag {{tag}} --dist dist

release-set-latest-release tag:
  #!/usr/bin/env bash
  set -euxo pipefail

  git switch latest-release
  cat << EOF > latest-release.json
  {
    "version": 1,
    "tag": "{{tag}}",
    "release_url": "https://github.com/indygreg/python-build-standalone/releases/tag/{{tag}}",
    "asset_url_prefix": "https://github.com/indygreg/python-build-standalone/releases/download/{{tag}}"
  }
  EOF

  git commit -a -m 'set latest release to {{tag}}'
  git switch main

  git push origin latest-release

# Perform a release.
release token commit tag:
  #!/bin/bash
  set -eo pipefail

  rm -rf dist
  just release-download-distributions {{token}} {{commit}}
  datetime=$(ls dist/cpython-3.10.*-x86_64-unknown-linux-gnu-install_only-*.tar.gz  | awk -F- '{print $8}' | awk -F. '{print $1}')
  just release-upload-distributions {{token}} ${datetime} {{tag}}
  just release-set-latest-release {{tag}}

download-stats:
    build/venv.*/bin/python3 -c 'import pythonbuild.utils as u; u.release_download_statistics()'
