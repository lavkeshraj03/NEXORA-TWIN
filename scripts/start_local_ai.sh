#!/bin/sh
# Keep inference on this Mac and bound model/context memory. No model is downloaded here.
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$project_dir/.local"
if curl --silent --fail --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Ollama is already running on 127.0.0.1:11434."
  echo "Use ollama list to confirm the selected models are installed."
  exit 0
fi
command -v ollama >/dev/null 2>&1 || { echo "Install Ollama before starting local AI." >&2; exit 1; }
python3 - "$project_dir" <<'PY'
import os, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
environment = os.environ.copy()
environment.update(OLLAMA_HOST="127.0.0.1:11434", OLLAMA_NO_CLOUD="1", OLLAMA_MAX_LOADED_MODELS="1", OLLAMA_NUM_PARALLEL="1", OLLAMA_CONTEXT_LENGTH="4096", OLLAMA_KEEP_ALIVE="0")
with (root/".local/ollama.log").open("ab") as log:
    process = subprocess.Popen(["ollama", "serve"], env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
(root/".local/ollama.pid").write_text(str(process.pid))
PY
attempt=0
while [ "$attempt" -lt 20 ]; do
  if curl --silent --fail --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "Local Ollama is ready. Logs: .local/ollama.log"
    exit 0
  fi
  attempt=$((attempt+1))
  sleep 1
done
echo "Ollama did not become ready. Inspect .local/ollama.log." >&2
exit 1
