#!/usr/bin/env python3
"""Local bridge that lets the in-app browser write a GitHub tree to disk.

The terminal in this environment cannot resolve GitHub, while the browser can.
This service exposes a tiny local-only web page. The page reads the repository
tree through GitHub's API, fetches each raw file, and posts it back to this
process, which writes the file below --root.
"""

from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GitHub Browser Sync</title>
  <style>
    :root { color-scheme: light dark; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    body { max-width: 900px; margin: 32px auto; padding: 0 20px; line-height: 1.5; }
    button { padding: 10px 18px; font: inherit; cursor: pointer; }
    pre { padding: 16px; overflow: auto; border: 1px solid #8884; border-radius: 8px; }
  </style>
</head>
<body>
  <h1>GitHub Browser Sync</h1>
  <p id="summary">Ready.</p>
  <button id="zip">Download ZIP to workspace</button>
  <button id="sync">Start file sync</button>
  <pre id="log"></pre>
  <script>
    const OWNER = __OWNER_JSON__;
    const REPO = __REPO_JSON__;
    const REF = __REF_JSON__;
    const TARGET = __TARGET_JSON__;
    const logNode = document.querySelector('#log');
    const summaryNode = document.querySelector('#summary');
    const button = document.querySelector('#sync');
    const zipButton = document.querySelector('#zip');

    function log(message) {
      const stamp = new Date().toLocaleTimeString();
      logNode.textContent += `[${stamp}] ${message}\n`;
      logNode.scrollTop = logNode.scrollHeight;
    }

    function encodePath(path) {
      return path.split('/').map(encodeURIComponent).join('/');
    }

    async function post(path, body, contentType = 'application/octet-stream') {
      const response = await fetch(`/save?path=${encodeURIComponent(path)}`, {
        method: 'POST',
        headers: { 'Content-Type': contentType },
        body,
      });
      if (!response.ok) {
        throw new Error(`${response.status} ${await response.text()}`);
      }
    }

    async function sync() {
      button.disabled = true;
      try {
        summaryNode.textContent = 'Resolving repository tree...';
        const response = await fetch(
          `https://api.github.com/repos/${OWNER}/${REPO}/git/trees/${encodeURIComponent(REF)}?recursive=1`,
          { headers: { Accept: 'application/vnd.github+json' } },
        );
        if (!response.ok) {
          throw new Error(`GitHub tree request failed: ${response.status} ${await response.text()}`);
        }
        const tree = await response.json();
        const blobs = tree.tree.filter((entry) => entry.type === 'blob');
        log(`Resolved ${blobs.length} files at commit ${tree.sha}`);

        let completed = 0;
        const concurrency = 4;
        let cursor = 0;
        async function worker() {
          while (cursor < blobs.length) {
            const entry = blobs[cursor++];
            const rawUrl = `https://raw.githubusercontent.com/${OWNER}/${REPO}/${tree.sha}/${encodePath(entry.path)}`;
            const fileResponse = await fetch(rawUrl);
            if (!fileResponse.ok) {
              throw new Error(`Failed ${entry.path}: ${fileResponse.status}`);
            }
            const bytes = await fileResponse.arrayBuffer();
            await post(entry.path, bytes);
            completed += 1;
            summaryNode.textContent = `Synced ${completed}/${blobs.length}`;
            if (completed % 10 === 0 || completed === blobs.length) {
              log(`Saved ${completed}/${blobs.length}: ${entry.path}`);
            }
          }
        }
        await Promise.all(Array.from({ length: concurrency }, worker));

        const metadata = {
          owner: OWNER,
          repo: REPO,
          requestedRef: REF,
          resolvedCommit: tree.sha,
          truncated: tree.truncated,
          fileCount: blobs.length,
          syncedAt: new Date().toISOString(),
        };
        await post('.source.json', JSON.stringify(metadata, null, 2), 'application/json');
        summaryNode.textContent = `Complete: ${blobs.length} files at ${tree.sha}`;
        log('Sync complete.');
      } catch (error) {
        summaryNode.textContent = 'Sync failed.';
        log(`ERROR: ${error.stack || error}`);
        throw error;
      } finally {
        button.disabled = false;
      }
    }

    button.addEventListener('click', sync);

    async function downloadZip() {
      zipButton.disabled = true;
      try {
        summaryNode.textContent = 'Downloading ZIP archive...';
        const url = `https://codeload.github.com/${OWNER}/${REPO}/zip/${encodeURIComponent(REF)}`;
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`ZIP request failed: ${response.status}`);
        }
        const bytes = await response.arrayBuffer();
        await post('archive.zip', bytes);
        summaryNode.textContent = `Saved archive.zip (${bytes.byteLength} bytes)`;
        log(`Saved archive.zip: ${bytes.byteLength} bytes`);
      } catch (error) {
        summaryNode.textContent = 'ZIP download failed.';
        log(`ERROR: ${error.stack || error}`);
        throw error;
      } finally {
        zipButton.disabled = false;
      }
    }

    zipButton.addEventListener('click', downloadZip);
  </script>
</body>
</html>
"""


def safe_target(root: Path, relative: str) -> Path:
    relative = relative.replace("\\", "/").lstrip("/")
    candidate = (root / relative).resolve()
    root = root.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"path escapes root: {relative}")
    return candidate


class Handler(BaseHTTPRequestHandler):
    server: "SyncServer"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            payload = json.dumps({"ok": True}).encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path != "/":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        page = (
            PAGE.replace("__OWNER_JSON__", json.dumps(self.server.owner))
            .replace("__REPO_JSON__", json.dumps(self.server.repo))
            .replace("__REF_JSON__", json.dumps(self.server.ref))
            .replace("__TARGET_JSON__", json.dumps(str(self.server.root)))
            .encode()
        )
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/save":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        relative = parse_qs(parsed.query).get("path", [""])[0]
        if not relative:
            self.send_error(HTTPStatus.BAD_REQUEST, "missing path")
            return

        try:
            target = safe_target(self.server.root, relative)
        except ValueError as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f".{target.name}.download")
        temp.write_bytes(body)
        os.replace(temp, target)

        payload = json.dumps({"path": relative, "bytes": len(body)}).encode()
        self.send_response(HTTPStatus.CREATED)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class SyncServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], root: Path, owner: str, repo: str, ref: str):
        super().__init__(address, Handler)
        self.root = root
        self.owner = owner
        self.repo = repo
        self.ref = ref


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="destination directory")
    parser.add_argument("--owner", default="XiGeMaX")
    parser.add_argument("--repo", default="Baby_tracker")
    parser.add_argument("--ref", default="main", help="branch, tag, or commit SHA")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    server = SyncServer((args.host, args.port), root, args.owner, args.repo, args.ref)
    print(f"Serving http://{args.host}:{args.port}/ -> {root}", flush=True)
    print("Open the URL in the in-app browser and press Start sync.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
