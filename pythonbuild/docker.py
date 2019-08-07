# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from .logging import (
    log,
)


def ensure_docker_image(client, fh, image_path=None):
    res = client.api.build(fileobj=fh, decode=True)

    image = None

    for s in res:
        if 'stream' in s:
            for l in s['stream'].strip().splitlines():
                log(l)

        if 'aux' in s and 'ID' in s['aux']:
            image = s['aux']['ID']

    if not image:
        raise Exception('unable to determine built Docker image')

    if image_path:
        tar_path = image_path.with_suffix('.tar')
        with tar_path.open('wb') as fh:
            for chunk in client.images.get(image).save():
                fh.write(chunk)

        with image_path.open('w') as fh:
            fh.write(image + '\n')

    return image
