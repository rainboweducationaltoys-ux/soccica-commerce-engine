#!/bin/bash

set -e

cd "$(dirname "$0")"

export PYTHONPATH="$PWD/src"

mkdir -p logs

MAIN_LOG="logs/continuous_run.log"
MAX_ITERATIONS=1000

iteration=0

echo "=== Sürekli döngü başladı: $(date) ===" >> "$MAIN_LOG"

while [ $iteration -lt $MAX_ITERATIONS ]; do
    iteration=$((iteration + 1))

    spotlight_priced=$(sqlite3 data/soccica.db "SELECT COUNT(*) FROM products WHERE status='spotlight_priced';")
    ready=$(sqlite3 data/soccica.db "SELECT COUNT(*) FROM products WHERE status='ready_for_shopify';")

    echo "--- İterasyon $iteration — $(date) — spotlight_priced=$spotlight_priced ready_for_shopify=$ready ---" >> "$MAIN_LOG"

    if [ "$spotlight_priced" -eq 0 ] && [ "$ready" -eq 0 ]; then
        echo "Kuyruklar boş, döngü sonlandırılıyor: $(date)" >> "$MAIN_LOG"
        break
    fi

    if ! .venv/bin/python src/run_spotlight_all.py >> "$MAIN_LOG" 2>&1; then
        echo "İterasyon $iteration hata ile bitti, 30sn sonra devam edilecek." >> "$MAIN_LOG"
        sleep 30
    fi

    sleep 5
done

echo "=== Sürekli döngü tamamlandı: $(date) — toplam iterasyon: $iteration ===" >> "$MAIN_LOG"
