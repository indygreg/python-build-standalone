# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import gzip
import hashlib
import os
import pathlib
import subprocess
import sys
import tarfile
import zipfile
import urllib.request

import zstandard

from .downloads import DOWNLOADS
from .logging import log


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

    if length != size:
        raise IntegrityError(
            "size mismatch on %s: wanted %d; got %d" % (url, size, length)
        )

    if digest != sha256:
        raise IntegrityError(
            "sha256 mismatch on %s: wanted %s; got %s" % (url, sha256, digest)
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
                22, compression_strategy=zstandard.STRATEGY_BTULTRA2
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

    for link in entry["links"]:
        name = link["name"]

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

    if not have_licenses:
        return

    entry["licenses"] = sorted(licenses)
    entry["license_paths"] = sorted(license_paths)
    entry["license_public_domain"] = license_public_domain


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
        print("process exited %d" % p.returncode)
        sys.exit(p.returncode)
