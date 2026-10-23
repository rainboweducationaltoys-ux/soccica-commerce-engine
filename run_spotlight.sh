#!/bin/bash

set -e

cd "$(dirname "$0")"

export PYTHONPATH="$PWD/src"

EXPORT_DIR="input/spotlight_exports"

newest_file=$(ls -t "$EXPORT_DIR"/*.xlsx 2>/dev/null | head -n 1)

if [ -z "$newest_file" ]; then
    echo "Hata: $EXPORT_DIR içinde .xlsx dosyası bulunamadı."
    exit 1
fi

echo "En yeni Spotlight export dosyası: $newest_file"

./.venv/bin/python src/run_spotlight_all.py
