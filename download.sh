#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
venv_python="/opt/personal/.personal-venv/bin/python"

if [[ ! -x "$venv_python" ]]; then
  echo "Virtual-environment Python not found or not executable: $venv_python" >&2
  exit 1
fi

exec "$venv_python" "$script_dir/ssh_download.py" \
  --host 10.10.4.57 \
  --user nusapala \
  --path /home/nusapala/program/cv/cv-screening/data/2026-07-24 \
  --output ~/cv_screening_test_date \
  --password nusapala01 \
  --workers 8
