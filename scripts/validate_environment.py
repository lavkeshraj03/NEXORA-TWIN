"""Read-only readiness smoke test. Run while the backend is serving."""
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

url = "http://127.0.0.1:8000/api/v1/health/ready"
try:
    with urlopen(url, timeout=15) as response:
        result = json.load(response)
except HTTPError as exc:
    result = json.load(exc)
except (URLError, TimeoutError):
    print("Backend is unreachable. Start the services first.")
    sys.exit(1)

for name, check in result["checks"].items():
    print(f"{name}: {check['status']} — {check['detail']}")
sys.exit(0 if result["status"] == "ready" else 1)
