"""Local deterministic web pages for browser agent benchmarking.

Run standalone:
    python -m src.benchmarks.browser_fixture_server

Use in tests:
    server = BrowserFixtureServer(port=0)
    server.start()
    url = server.url_for("/login")
    ...
    server.stop()
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn


class BrowserFixtureServer:
    """A tiny FastAPI server serving deterministic web tasks."""

    DEFAULT_PAGES: Dict[str, str] = {
        "/login": """
<!doctype html>
<html>
<head><title>Login</title></head>
<body>
  <h1>Login</h1>
  <form id="login-form">
    <input id="username" type="text" placeholder="Username" />
    <input id="password" type="password" placeholder="Password" />
    <button id="submit" type="button">Login</button>
  </form>
  <p id="result"></p>
  <script>
    document.getElementById('submit').addEventListener('click', () => {
      const u = document.getElementById('username').value;
      const p = document.getElementById('password').value;
      const result = (u === 'admin' && p === 'houdini123') ? 'Welcome, admin!' : 'Invalid credentials';
      document.getElementById('result').textContent = result;
    });
  </script>
</body>
</html>
""",
        "/todo": """
<!doctype html>
<html>
<head><title>Todo List</title></head>
<body>
  <h1>Todo List</h1>
  <input id="new-todo" type="text" placeholder="New task" />
  <button id="add">Add</button>
  <ul id="list"></ul>
  <script>
    document.getElementById('add').addEventListener('click', () => {
      const input = document.getElementById('new-todo');
      if (!input.value) return;
      const li = document.createElement('li');
      li.textContent = input.value;
      document.getElementById('list').appendChild(li);
      input.value = '';
    });
  </script>
</body>
</html>
""",
        "/search": """
<!doctype html>
<html>
<head><title>Search</title></head>
<body>
  <h1>Search</h1>
  <input id="query" type="text" placeholder="Search..." />
  <button id="go">Search</button>
  <div id="results"></div>
  <script>
    document.getElementById('go').addEventListener('click', () => {
      const q = document.getElementById('query').value.toLowerCase();
      const results = document.getElementById('results');
      if (q.includes('houdini')) {
        results.innerHTML = '<p>Result 1: Houdini Agent</p><p>Result 2: Houdini VFX</p>';
      } else {
        results.innerHTML = '<p>No results found</p>';
      }
    });
  </script>
</body>
</html>
""",
    }

    def __init__(self, port: int = 8123):
        self.port = port
        self._app = FastAPI()
        self._server: Optional[uvicorn.Server] = None
        self._thread: Optional[threading.Thread] = None
        self._setup_routes()

    def _setup_routes(self):
        for path, html in self.DEFAULT_PAGES.items():
            self._app.add_api_route(path, lambda html=html: HTMLResponse(content=html), methods=["GET"])

        @self._app.get("/tasks.json")
        def tasks():
            return JSONResponse(content=self._load_tasks())

    def _load_tasks(self) -> List[Dict[str, Any]]:
        path = Path(__file__).with_name("web_benchmark_tasks.json")
        if path.exists():
            return json.loads(path.read_text())
        return []

    def start(self):
        config = uvicorn.Config(self._app, host="127.0.0.1", port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()

        deadline = time.time() + 5
        while time.time() < deadline:
            if self._server.started:
                break
            if not self._thread.is_alive():
                raise RuntimeError("Fixture server thread died during startup")
            time.sleep(0.05)
        else:
            raise RuntimeError("Fixture server failed to start within 5s")

        sock = self._server.servers[0].sockets[0]
        self._actual_port = sock.getsockname()[1]

    def stop(self):
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)
            if self._thread.is_alive() and self._server:
                self._server.force_exit = True
                self._thread.join(timeout=2)
        self._server = None
        self._thread = None

    def url_for(self, path: str) -> str:
        if not getattr(self, "_actual_port", None):
            raise RuntimeError("Server not started or port not assigned")
        return f"http://127.0.0.1:{self._actual_port}{path}"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8123)
    args = parser.parse_args()
    server = BrowserFixtureServer(port=args.port)
    server.start()
    print(f"Fixture server running at {server.url_for('/')}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
