#!/bin/bash

set -e

cd "$(dirname "$0")"

export PYTHONPATH="$PWD/src"

./.venv/bin/python src/run_all.py