#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$project_dir/.local"
if curl --silent --fail --max-time 2 http://127.0.0.1:11435/health >/dev/null 2>&1; then
  echo "Local OCR service is already running."
  exit 0
fi
if [ ! -x "$project_dir/.local/nexora-ocr" ] || [ "$project_dir/scripts/local_ocr.swift" -nt "$project_dir/.local/nexora-ocr" ]; then
  swiftc -O -module-cache-path /private/tmp/nexora-swift-module-cache "$project_dir/scripts/local_ocr.swift" -o "$project_dir/.local/nexora-ocr"
fi
python3 - "$project_dir" <<'PY'
import json, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
binary = str(root/".local/nexora-ocr")
fixture = str(root/".local/ocr-warmup.pdf")
subprocess.run([binary, "--fixture", fixture], check=True, timeout=30)
result = subprocess.run([binary, fixture], check=True, capture_output=True, timeout=90)
if not any(page.get("text", "").strip() for page in json.loads(result.stdout)["pages"]):
    raise SystemExit("Local OCR warm-up failed; service was not started")
PY
python3 - "$project_dir" <<'PY'
import subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
with (root/".local/ocr.log").open("ab") as log:
    process = subprocess.Popen([sys.executable, str(root/"scripts/local_ocr_server.py")], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
(root/".local/ocr.pid").write_text(str(process.pid))
PY
attempt=0
while [ "$attempt" -lt 20 ]; do
  if curl --silent --fail --max-time 2 http://127.0.0.1:11435/health >/dev/null 2>&1; then
    echo "Local OCR is ready on port 11435. Logs: .local/ocr.log"
    exit 0
  fi
  attempt=$((attempt+1))
  sleep 1
done
echo "Local OCR did not become ready. Inspect .local/ocr.log." >&2
exit 1
