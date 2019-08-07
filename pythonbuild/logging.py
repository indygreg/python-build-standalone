# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

LOG_PREFIX = [None]
LOG_FH = [None]


def set_logger(prefix, fh):
    LOG_PREFIX[0] = prefix
    LOG_FH[0] = fh


def log(msg):
    if isinstance(msg, bytes):
        msg_str = msg.decode("utf-8", "replace")
        msg_bytes = msg
    else:
        msg_str = msg
        msg_bytes = msg.encode("utf-8", "replace")

    print("%s> %s" % (LOG_PREFIX[0], msg_str))

    if LOG_FH[0]:
        LOG_FH[0].write(msg_bytes + b"\n")


def log_raw(data):
    if LOG_FH[0]:
        LOG_FH[0].write(data)
