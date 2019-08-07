# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import contextlib
import pathlib
import shutil
import tempfile

from .docker import container_exec, container_get_archive, copy_file_to_container
from .logging import log


class ContainerContext(object):
    def __init__(self, container):
        self.container = container

    def copy_file(self, source: pathlib.Path, dest_path, dest_name=None):
        dest_name = dest_name or source.name
        copy_file_to_container(source, self.container, dest_path, dest_name)

    def exec(self, program, environment=None):
        container_exec(self.container, program, environment=environment)

    def get_tools_archive(self, dest, name):
        log("copying container files to %s" % dest)
        data = container_get_archive(self.container, "/build/out/tools/%s" % name)

        with open(dest, "wb") as fh:
            fh.write(data)


class TempdirContext(object):
    def __init__(self, td):
        self.td = pathlib.Path(td)

    def copy_file(self, source: pathlib.Path, dest_path, dest_name=None):
        dest_path = dest_path.lstrip("/")
        dest_dir = self.td / dest_path
        dest_dir.mkdir(exist_ok=True)

        dest_name = dest_name or source.name
        log("copying %s to %s/%s" % (source, dest_dir, dest_name))
        shutil.copyfile(source, dest_dir / dest_name)


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
