# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import gzip
import hashlib
import os
import pathlib
import tarfile
import urllib.request

import zstandard

from .downloads import (
    DOWNLOADS,
)


def hash_path(p: pathlib.Path):
    h = hashlib.sha256()

    with p.open('rb') as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


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
        if not url.endswith('.gz') and fh.info().get('Content-Encoding') == 'gzip':
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
        raise IntegrityError('size mismatch on %s: wanted %d; got %d' % (
            url, size, length))

    if digest != sha256:
        raise IntegrityError('sha256 mismatch on %s: wanted %s; got %s' % (
            url, sha256, digest))


def download_to_path(url: str, path: pathlib.Path, size: int, sha256: str):
    """Download a URL to a filesystem path, possibly with verification."""

    # We download to a temporary file and rename at the end so there's
    # no chance of the final file being partially written or containing
    # bad data.
    print('downloading %s to %s' % (url, path))

    if path.exists():
        good = True

        if path.stat().st_size != size:
            print('existing file size is wrong; removing')
            good = False

        if good:
            if hash_path(path) != sha256:
                print('existing file hash is wrong; removing')
                good = False

        if good:
            print('%s exists and passes integrity checks' % path)
            return

        path.unlink()

    tmp = path.with_name('%s.tmp' % path.name)

    try:
        with tmp.open('wb') as fh:
            for chunk in secure_download_stream(url, size, sha256):
                fh.write(chunk)
    except IntegrityError:
        tmp.unlink()
        raise

    tmp.rename(path)
    print('successfully downloaded %s' % url)


def download_entry(key: str, dest_path: pathlib.Path, local_name=None) -> pathlib.Path:
    entry = DOWNLOADS[key]
    url = entry['url']

    local_name = local_name or url[url.rindex('/') + 1:]

    local_path = dest_path / local_name
    download_to_path(url, local_path, entry['size'], entry['sha256'])

    return local_path


def create_tar_from_directory(fh, base_path: pathlib.Path):
    with tarfile.open(name='', mode='w', fileobj=fh, dereference=True) as tf:
        for root, dirs, files in os.walk(base_path):
            dirs.sort()

            for f in sorted(files):
                full = base_path / root / f
                rel = full.relative_to(base_path)
                tf.add(full, rel)


def extract_tar_to_directory(source: pathlib.Path, dest: pathlib.Path):
    with tarfile.open(source, 'r') as tf:
        tf.extractall(dest)


def compress_python_archive(source_path: pathlib.Path,
                            dist_path: pathlib.Path,
                            basename: str):
    dest_path = dist_path / ('%s.tar.zst' % basename)
    temp_path = dist_path / ('%s.tar.zst.tmp' % basename)

    print('compressing Python archive to %s' % dest_path)

    try:
        with source_path.open('rb') as ifh, temp_path.open('wb') as ofh:
            cctx = zstandard.ZstdCompressor(level=15)
            cctx.copy_stream(ifh, ofh, source_path.stat().st_size)

        temp_path.rename(dest_path)
    except Exception:
        temp_path.unlink()
        raise

    print('%s has SHA256 %s' % (dest_path, hash_path(dest_path)))

    return dest_path


def add_license_to_link_entry(entry):
    """Add licenses keys to a ``link`` entry for JSON distribution info."""
    name = entry['name']

    for value in DOWNLOADS.values():
        if name not in value.get('library_names', []):
            continue

        # Don't add licenses annotations if they aren't defined. This leaves
        # things as "unknown" to consumers.
        if 'licenses' not in value:
            continue

        entry['licenses'] = value['licenses']
        entry['license_path'] = 'licenses/%s' % value['license_file']
        entry['license_public_domain'] = value.get('license_public_domain', False)

        return
