#!/usr/bin/env bash

set -euo pipefail

# ========== CONFIGURATION ==========
YEAR="2026"
MONTH="07"
START_DAY="01"
END_DAY="24"

HOST="10.10.4.57"
USER="nusapala"
PASSWORD="nusapala01"
WORKERS="4"
SCAN_WORKERS="4"
PREFETCH_REQUESTS="16"
REQUEST_SIZE="32768"
RETRIES="3"
OUTPUT_BASE_DIR="./cv_screening_data"

# ========== SETUP ==========
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
venv_python="/mnt/secondary/remote_downloader/.venv/bin/python"

if [[ ! -x "$venv_python" ]]; then
  echo "Virtual-environment Python not found or not executable: $venv_python" >&2
  exit 1
fi

echo "=========================================="
echo "Starting bulk download"
echo "Period: $YEAR-$MONTH-$START_DAY to $YEAR-$MONTH-$END_DAY"
echo "Host: $HOST"
echo "Workers: $WORKERS"
echo "Scan workers: $SCAN_WORKERS"
echo "Prefetch requests per worker: $PREFETCH_REQUESTS"
echo "SFTP request size: $REQUEST_SIZE bytes"
echo "Retries per file: $RETRIES"
echo "=========================================="
echo ""

# ========== DOWNLOAD LOOP ==========
failed_days=0

for day in $(seq -f "%02g" "$START_DAY" "$END_DAY"); do
  date_folder="${YEAR}-${MONTH}-${day}"
  output_dir="${OUTPUT_BASE_DIR}/${date_folder}"
  remote_path="/home/${USER}/program/cv/cv-screening/data/${date_folder}"
  
  echo "=========================================="
  echo "[$day/24] Downloading: $date_folder"
  echo "=========================================="
  
  if "$venv_python" "$script_dir/ssh_download.py" \
      --host "$HOST" \
      --user "$USER" \
      --path "$remote_path" \
      --output "$output_dir" \
      --password "$PASSWORD" \
      --workers "$WORKERS" \
      --scan-workers "$SCAN_WORKERS" \
      --prefetch-requests "$PREFETCH_REQUESTS" \
      --request-size "$REQUEST_SIZE" \
      --retries "$RETRIES"; then
    echo "✅ Completed: $date_folder"
  else
    echo "⚠️ Completed with unresolved failures: $date_folder" >&2
    failed_days=$((failed_days + 1))
  fi
  echo ""
done

echo "=========================================="
echo "✅ All downloads complete!"
echo "Files saved to: $OUTPUT_BASE_DIR"
echo "Dates with unresolved failures: $failed_days"
echo "=========================================="

if ((failed_days > 0)); then
  exit 1
fi
