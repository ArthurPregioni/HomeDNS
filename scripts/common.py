"""Private runtime paths and loopback-only AdGuard Home API access."""
import base64
import json
import os
from pathlib import Path
import tempfile
import socket
import time
import urllib.request

CONFIG = Path.home() / ".config/homedns"
STATE = Path.home() / ".local/share/homedns"
LOGS = Path.home() / ".local/state/homedns"
APP = Path.home() / "apps/homedns"
API = "http://127.0.0.1:13000/control"


def private_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api(path, data=None, method=None, authenticated=True, timeout=90):
    headers = {"Content-Type": "application/json"}
    if authenticated:
        credentials = json.loads((CONFIG / "login.json").read_text())
        raw = (credentials["username"] + ":" + credentials["password"]).encode()
        headers["Authorization"] = "Basic " + base64.b64encode(raw).decode()
    request = urllib.request.Request(
        API + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers=headers, method=method,
    )
    # Never proxy or redirect local administrator credentials.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        content = response.read()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return content.decode()


def wait_ready():
    port = json.loads((CONFIG / "runtime.json").read_text())["dns_port"]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            api("/status", timeout=2)
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("HomeDNS API and DNS listener did not become ready")
