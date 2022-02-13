#!/usr/bin/env bash
# This script is needed to handle a race in GCC's build system and a bug in
# sccache.
#
# GCC's build system could materialize `xgcc` and invoke commands like
# `xgcc -dumpspecs` before make materializes `cc1`. This is relevant because
# sccache invokes `<compiler> -E` on the first invocation of a compiler to
# determine which flavor of compiler to treat it as. And `gcc -E` requires
# support binaries like `cc1` in order to work. Our wrapper script sniffs
# for existence of `cc1` to mitigate this race condiion.
#
# Furthermore, sccache doesn't honor `-B` arguments when running
# `<compiler> -E`. So even if a support binary like `cc1` may exist, GCC may
# not know where to find it. Our wrapper script works around this by ensuring
# the compiler's directory is always on PATH.
#
# This script/approach is arguably not sound for use outside of the value of
# STAGE_CC_WRAPPER in GCC's build system. You have been warned.

set -o errexit
set -o pipefail

dir=$(dirname $1)
cc1=${dir}/cc1

if [ -e "${cc1}"  ]; then
  export PATH=${dir}:${PATH}
  exec sccache "$@"
else
  exec "$@"
fi
