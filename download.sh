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
WORKERS="8"
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
echo "=========================================="
echo ""

# ========== DOWNLOAD LOOP ==========
for day in $(seq -f "%02g" "$START_DAY" "$END_DAY"); do
  date_folder="${YEAR}-${MONTH}-${day}"
  output_dir="${OUTPUT_BASE_DIR}/${date_folder}"
  remote_path="/home/${USER}/program/cv/cv-screening/data/${date_folder}"
  
  echo "=========================================="
  echo "[$day/24] Downloading: $date_folder"
  echo "=========================================="
  
  "$venv_python" "$script_dir/ssh_download.py" \
    --host "$HOST" \
    --user "$USER" \
    --path "$remote_path" \
    --output "$output_dir" \
    --password "$PASSWORD" \
    --workers "$WORKERS"
  
  echo "✅ Completed: $date_folder"
  echo ""
done

echo "=========================================="
echo "✅ All downloads complete!"
echo "Files saved to: $OUTPUT_BASE_DIR"
echo "=========================================="