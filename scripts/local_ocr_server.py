"""Loopback-only macOS Vision bridge implementing the application's optional OCR contract."""
import json
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, payload):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.respond(200 if self.path == "/health" else 404, {"service": "macOS Vision OCR", "languages": ["en-US"], "ready": ROOT.joinpath(".local/nexora-ocr").is_file()})

    def do_POST(self):
        if self.path != "/ocr":
            return self.respond(404, {"error": "Route not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.respond(400, {"error": "Invalid content length"})
        if not 1 <= length <= 2*1024*1024 or self.headers.get("Content-Type") != "application/pdf":
            return self.respond(413, {"error": "Expected an application/pdf body up to 2 MiB"})
        self.connection.settimeout(10)
        raw = self.rfile.read(length)
        if len(raw) != length or not raw.startswith(b"%PDF-"):
            return self.respond(422, {"error": "Invalid PDF"})
        try:
            with tempfile.TemporaryDirectory(prefix="nexora-ocr-") as folder:
                source = Path(folder)/"source.pdf"
                source.write_bytes(raw)
                completed = subprocess.run([str(ROOT/".local/nexora-ocr"), str(source)], capture_output=True, timeout=40, check=True)
            if len(completed.stdout) > 1024*1024:
                raise ValueError("OCR output exceeded the limit")
            self.respond(200, json.loads(completed.stdout))
        except Exception:
            self.respond(502, {"error": "Local OCR could not process this document within its limits"})

    def log_message(self, *_):
        pass  # Never log document text, request bodies or original filenames.


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 11435), Handler).serve_forever()
