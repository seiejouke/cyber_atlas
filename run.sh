#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/python ]; then
    printf '%s\n' 'Create .venv and install requirements first. See README.md.' >&2
    exit 1
fi
exec .venv/bin/python main.py "$@"
