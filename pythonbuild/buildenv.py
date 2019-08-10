# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import contextlib
import io
import pathlib
import shutil
import tarfile
import tempfile

from .docker import container_exec, container_get_archive, copy_file_to_container
from .downloads import DOWNLOADS
from .logging import log
from .utils import create_tar_from_directory, exec_and_log


class ContainerContext(object):
    def __init__(self, container):
        self.container = container

    def copy_file(self, source: pathlib.Path, dest_path, dest_name=None):
        dest_name = dest_name or source.name
        copy_file_to_container(source, self.container, dest_path, dest_name)

    def install_artifact_archive(self, build_dir, package_name, platform, musl=False):
        entry = DOWNLOADS[package_name]
        basename = "%s-%s-%s%s.tar" % (
            package_name,
            entry["version"],
            platform,
            "-musl" if musl else "",
        )

        p = build_dir / basename

        self.copy_file(p, "/build")
        self.run(["/bin/tar", "-C", "/tools", "-xf", "/build/%s" % p.name], user="root")

    def install_toolchain(
        self, build_dir, platform, binutils=False, gcc=False, musl=False, clang=False
    ):
        if binutils:
           self.install_artifact_archive(build_dir, "binutils", platform)

        if gcc:
            self.install_artifact_archive(build_dir, "gcc", platform)

        if clang:
            self.install_artifact_archive(build_dir, "clang", platform)

        if musl:
            self.install_artifact_archive(build_dir, "musl", platform)

    def run(self, program, user="build", environment=None):
        container_exec(self.container, program, user=user, environment=environment)

    def run_capture(self, command, user=None):
        return self.container.exec_run(command, user=user)

    def get_tools_archive(self, dest, name):
        log("copying container files to %s" % dest)
        data = container_get_archive(self.container, "/build/out/tools/%s" % name)

        with open(dest, "wb") as fh:
            fh.write(data)

    def get_archive(self, path, as_tar=False):
        data = container_get_archive(self.container, path)
        data = io.BytesIO(data)

        if as_tar:
            return tarfile.open(fileobj=data)
        else:
            return data.getvalue()


class TempdirContext(object):
    def __init__(self, td):
        self.td = pathlib.Path(td)

    def copy_file(self, source: pathlib.Path, dest_path, dest_name=None):
        dest_path = dest_path.lstrip("/")
        dest_dir = self.td / dest_path
        dest_dir.mkdir(exist_ok=True)

        dest_name = dest_name or source.name
        log("copying %s to %s/%s" % (source, dest_dir, dest_name))
        shutil.copy(source, dest_dir / dest_name)

    def install_toolchain(
        self, build_dir, platform, binutils=False, gcc=False, musl=False, clang=False
    ):
        if binutils:
            self.install_artifact_archive(build_dir, "binutils", platform)

        if gcc:
            self.install_artifact_archive(build_dir, "gcc", platform)

        if clang:
            self.install_artifact_archive(build_dir, "clang", platform)

        if musl:
            self.install_artifact_archive(build_dir, "musl", platform)

    def run(self, program, user="build", environment=None):
        if user != "build":
            raise Exception('cannot change user in temp directory builds')

        if isinstance(program, str) and program.startswith("/"):
            program = str(self.td / program[1:])

        exec_and_log(program, cwd=self.td, env=environment)

    def get_tools_archive(self, dest, name):
        log("copying built files to %s" % dest)

        with dest.open('wb') as fh:
            create_tar_from_directory(fh, self.td / 'out')


@contextlib.contextmanager
def build_environment(client, image):
    if client is not None:
        container = client.containers.run(
            image, command=["/bin/sleep", "86400"], detach=True
        )
        td = None
        context = ContainerContext(container)
    else:
        container = None
        td = tempfile.TemporaryDirectory()
        context = TempdirContext(td.name)

    try:
        yield context
    finally:
        if container:
            container.stop(timeout=0)
            container.remove()
        else:
            td.cleanup()
