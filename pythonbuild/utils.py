# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import gzip
import hashlib
import multiprocessing
import os
import pathlib
import subprocess
import sys
import tarfile
import zipfile
import urllib.request

import yaml
import zstandard

from .downloads import DOWNLOADS
from .logging import log


def get_targets(yaml_path: pathlib.Path):
    """Obtain the parsed targets YAML file."""
    with yaml_path.open("rb") as fh:
        return yaml.load(fh, Loader=yaml.SafeLoader)


def get_target_settings(yaml_path: pathlib.Path, target: str):
    """Obtain the settings for a named target."""
    return get_targets(yaml_path)[target]


def supported_targets(yaml_path: pathlib.Path):
    """Obtain a set of named targets that we can build."""
    targets = set()

    for target, settings in get_targets(yaml_path).items():
        for platform in settings["host_platforms"]:
            if sys.platform == platform:
                targets.add(target)

    return targets


def target_needs(yaml_path: pathlib.Path, target: str):
    """Obtain the dependencies needed to build the specified target."""
    settings = get_targets(yaml_path)[target]

    needs = set(settings["needs"])

    if "PYBUILD_LIBRESSL" in os.environ:
        needs.add("libressl")
    else:
        needs.add("openssl")

    return needs


def release_tag_from_git():
    return (
        subprocess.check_output(
            [
                "git",
                "log",
                "-n",
                "1",
                "--date=format:%Y%m%dT%H%M",
                "--pretty=format:%ad",
            ]
        )
        .strip()
        .decode("ascii")
    )


def hash_path(p: pathlib.Path):
    h = hashlib.sha256()

    with p.open("rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


def write_if_different(p: pathlib.Path, data: bytes):
    """Write a file if it is missing or its content is different."""
    if p.exists():
        with p.open("rb") as fh:
            existing = fh.read()
        write = existing != data
    else:
        write = True

    if write:
        with p.open("wb") as fh:
            fh.write(data)


def write_triples_makefiles(targets, dest_dir: pathlib.Path):
    """Write out makefiles containing make variable settings derived from config."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    for triple, settings in targets.items():
        makefile_path = dest_dir / ("Makefile.%s" % triple)

        lines = []
        for need in settings.get("needs", []):
            lines.append("NEED_%s := 1\n" % need.upper())

        if "PYBUILD_LIBRESSL" in os.environ:
            lines.append("NEED_LIBRESSL := 1\n")
        else:
            lines.append("NEED_OPENSSL := 1\n")

        image_suffix = settings.get("docker_image_suffix", "")

        lines.append("DOCKER_IMAGE_BUILD := build%s\n" % image_suffix)
        lines.append("DOCKER_IMAGE_XCB := xcb%s\n" % image_suffix)

        write_if_different(makefile_path, "".join(lines).encode("ascii"))


def write_package_versions(dest_path: pathlib.Path):
    """Write out versions of packages to files in a directory."""
    dest_path.mkdir(parents=True, exist_ok=True)

    for k, v in DOWNLOADS.items():
        p = dest_path / ("VERSION.%s" % k)
        content = "%s_VERSION := %s\n" % (k.upper().replace("-", "_"), v["version"])
        write_if_different(p, content.encode("ascii"))


class IntegrityError(Exception):
    """Represents an integrity error when downloading a URL."""


def secure_download_stream(url, size, sha256):
    """Securely download a URL to a stream of chunks.

    If the integrity of the download fails, an IntegrityError is
    raised.
    """
    h = hashlib.sha256()
    length = 0

    with urllib.request.urlopen(url) as fh:
        if not url.endswith(".gz") and fh.info().get("Content-Encoding") == "gzip":
            fh = gzip.GzipFile(fileobj=fh)

        while True:
            chunk = fh.read(65536)
            if not chunk:
                break

            h.update(chunk)
            length += len(chunk)

            yield chunk

    digest = h.hexdigest()

    if length != size or digest != sha256:
        raise IntegrityError(
            "integrity mismatch on %s: wanted size=%d, sha256=%s; got size=%d, sha256=%s"
            % (url, size, sha256, length, digest)
        )


def download_to_path(url: str, path: pathlib.Path, size: int, sha256: str):
    """Download a URL to a filesystem path, possibly with verification."""

    # We download to a temporary file and rename at the end so there's
    # no chance of the final file being partially written or containing
    # bad data.
    print("downloading %s to %s" % (url, path))

    if path.exists():
        good = True

        if path.stat().st_size != size:
            print("existing file size is wrong; removing")
            good = False

        if good:
            if hash_path(path) != sha256:
                print("existing file hash is wrong; removing")
                good = False

        if good:
            print("%s exists and passes integrity checks" % path)
            return

        path.unlink()

    tmp = path.with_name("%s.tmp" % path.name)

    try:
        with tmp.open("wb") as fh:
            for chunk in secure_download_stream(url, size, sha256):
                fh.write(chunk)
    except IntegrityError:
        tmp.unlink()
        raise

    tmp.rename(path)
    print("successfully downloaded %s" % url)


def download_entry(key: str, dest_path: pathlib.Path, local_name=None) -> pathlib.Path:
    entry = DOWNLOADS[key]
    url = entry["url"]

    local_name = local_name or url[url.rindex("/") + 1 :]

    local_path = dest_path / local_name
    download_to_path(url, local_path, entry["size"], entry["sha256"])

    return local_path


def create_tar_from_directory(fh, base_path: pathlib.Path, path_prefix=None):
    with tarfile.open(name="", mode="w", fileobj=fh) as tf:
        for root, dirs, files in os.walk(base_path):
            dirs.sort()

            for f in sorted(files):
                full = base_path / root / f
                rel = full.relative_to(base_path)
                if path_prefix:
                    rel = pathlib.Path(path_prefix) / rel
                tf.add(full, rel)


def extract_tar_to_directory(source: pathlib.Path, dest: pathlib.Path):
    with tarfile.open(source, "r") as tf:
        tf.extractall(dest)


def extract_zip_to_directory(source: pathlib.Path, dest: pathlib.Path):
    with zipfile.ZipFile(source, "r") as zf:
        zf.extractall(dest)


def compress_python_archive(
    source_path: pathlib.Path, dist_path: pathlib.Path, basename: str
):
    dest_path = dist_path / ("%s.tar.zst" % basename)
    temp_path = dist_path / ("%s.tar.zst.tmp" % basename)

    print("compressing Python archive to %s" % dest_path)

    try:
        with source_path.open("rb") as ifh, temp_path.open("wb") as ofh:
            params = zstandard.ZstdCompressionParameters.from_level(
                22, strategy=zstandard.STRATEGY_BTULTRA2
            )
            cctx = zstandard.ZstdCompressor(compression_params=params)
            cctx.copy_stream(ifh, ofh, source_path.stat().st_size)

        temp_path.rename(dest_path)
    except Exception:
        temp_path.unlink()
        raise

    print("%s has SHA256 %s" % (dest_path, hash_path(dest_path)))

    return dest_path


def add_licenses_to_extension_entry(entry, ignore_keys=None):
    """Add licenses keys to a ``extensions`` entry for JSON distribution info."""

    have_licenses = False
    licenses = set()
    license_paths = set()
    license_public_domain = None

    have_local_link = False

    for link in entry["links"]:
        name = link["name"]
        if "path_static" in link or "path_dynamic" in link:
            have_local_link = True

        for key, value in DOWNLOADS.items():
            if ignore_keys and key in ignore_keys:
                continue

            if name not in value.get("library_names", []):
                continue

            # Don't add licenses annotations if they aren't defined. This leaves
            # things as "unknown" to consumers.
            if "licenses" not in value:
                continue

            have_licenses = True
            licenses |= set(value["licenses"])
            license_paths.add("licenses/%s" % value["license_file"])
            license_public_domain = value.get("license_public_domain", False)

    if have_local_link and not have_licenses:
        raise Exception(
            "missing license for local library for extension entry: %s" % entry
        )

    if not have_licenses:
        return

    entry["licenses"] = sorted(licenses)
    entry["license_paths"] = sorted(license_paths)
    entry["license_public_domain"] = license_public_domain


def add_env_common(env):
    """Adds extra keys to environment variables."""

    cpu_count = multiprocessing.cpu_count()
    env["NUM_CPUS"] = "%d" % cpu_count
    env["NUM_JOBS_AGGRESSIVE"] = "%d" % max(cpu_count + 2, cpu_count * 2)

    if "CI" in os.environ:
        env["CI"] = "1"

    for k in (
        # Proxy variables used for sccache remote cache.
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "SCCACHE_BUCKET",
        "SCCACHE_S3_USE_SSL",
    ):
        if k in os.environ:
            env[k] = os.environ[k]


def exec_and_log(args, cwd, env):
    p = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        bufsize=1,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    for line in iter(p.stdout.readline, b""):
        log(line.rstrip())

    p.wait()

    if p.returncode:
        if "PYBUILD_BREAK_ON_FAILURE" in os.environ:
            import pdb

            pdb.set_trace()

        print("process exited %d" % p.returncode)
        sys.exit(p.returncode)


def validate_python_json(info):
    """Validate a PYTHON.json file for problems.

    Raises an exception if an issue is detected.
    """

    for name, variants in info["build_info"]["extensions"].items():
        for ext in variants:
            variant = ext["variant"]

            local_links = set()

            for link in ext["links"]:
                if "path_static" in link:
                    local_links.add(link["path_static"])
                if "path_dynamic" in link:
                    local_links.add(link["path_dynamic"])

                if not local_links and "framework" not in link and "system" not in link:
                    raise Exception(
                        "Invalid link entry for extension %s[%s]: link type not defined"
                        % (name, variant)
                    )

            if (
                local_links
                and not ext.get("licenses")
                and not ext.get("license_public_domain")
            ):
                raise Exception(
                    "Missing license annotations for extension %s[%s] for library files %s"
                    % (name, variant, ", ".join(sorted(local_links)))
                )
