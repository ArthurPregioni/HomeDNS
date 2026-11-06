#!/usr/bin/env python3
"""Install an Android build of pinned AdGuard Home source in Termux."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request

from common import APP, CONFIG, STATE, LOGS, api, private_write

ROOT = Path(__file__).resolve().parents[1]


def expose_dns(config, address):
    """Set explicit IPv4 bindings; Android restricts interface enumeration."""
    address = str(ipaddress.IPv4Address(address))
    pattern = r"(?m)^  bind_hosts:\n    - (?:127\.0\.0\.1|0\.0\.0\.0)\n(?:    - [0-9.]+\n)?(?=  [a-z_]+:|\Z)"
    text, count = re.subn(pattern, f"  bind_hosts:\n    - 127.0.0.1\n    - {address}\n", config)
    if count != 1:
        raise ValueError("Unexpected DNS bindings; refusing to edit configuration")
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lan", required=True, help="Allowed Wi-Fi IPv4 CIDR")
    parser.add_argument("--dns-port", type=int, default=1053)
    parser.add_argument("--bind-address", required=True, help="Phone Wi-Fi IPv4 address (reserve it in DHCP)")
    parser.add_argument("--binary", type=Path, required=True, help="Locally compiled Android PIE binary (with provenance.json)")
    args = parser.parse_args()
    lan = ipaddress.ip_network(args.lan, strict=True)
    if lan.version != 4 or not lan.is_private or lan.is_loopback:
        parser.error("--lan must be a private Wi-Fi IPv4 subnet")
    address = ipaddress.IPv4Address(args.bind_address)
    if address not in lan or address in (lan.network_address, lan.broadcast_address):
        parser.error("--bind-address must be a host inside --lan")
    if not 1024 <= args.dns_port <= 65535 or args.dns_port == 13000:
        parser.error("Use an unprivileged DNS port, different from web port 13000")
    prefix = Path(os.environ.get("PREFIX", ""))
    if not str(prefix).startswith("/data/data/com.termux/"):
        parser.error("Run this installer inside Termux on the phone")
    if platform.machine() != "aarch64":
        parser.error("This pinned binary is for ARM64 only")
    for directory in (APP, CONFIG, STATE, LOGS):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for port, kind in ((args.dns_port, socket.SOCK_DGRAM),
                       (args.dns_port, socket.SOCK_STREAM),
                       (13000, socket.SOCK_STREAM)):
        with socket.socket(socket.AF_INET, kind) as sock:
            if kind == socket.SOCK_STREAM:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", port))

    release = json.loads((ROOT / "config/release.json").read_text())
    binary = APP / "bin/AdGuardHome"
    if args.binary:
        metadata = json.loads(args.binary.with_name("provenance.json").read_text())
        digest = hashlib.sha256(args.binary.read_bytes()).hexdigest()
        shim_digest = hashlib.sha256((ROOT / "config/android-argv.go").read_bytes()).hexdigest()
        if (metadata["source_commit"] != release["source_commit"] or metadata["sha256"] != digest
                or metadata.get("argv_shim_sha256") != shim_digest):
            raise RuntimeError("Android build provenance or checksum mismatch")
        helper_source = args.binary.with_name("hash-password")
        if (hashlib.sha256(helper_source.read_bytes()).hexdigest() != metadata["hash_helper_sha256"]
                or hashlib.sha256((ROOT / "config/hash-password.go").read_bytes()).hexdigest() != metadata["hash_source_sha256"]):
            raise RuntimeError("Password utility checksum mismatch")
        binary.parent.mkdir(mode=0o700, exist_ok=True)
        shutil.copyfile(args.binary, binary)
        license_file = args.binary.with_name("ADGUARD-LICENSE.txt")
        if not license_file.is_file():
            raise RuntimeError("Android build must include ADGUARD-LICENSE.txt")
        shutil.copyfile(license_file, APP / "ADGUARD-LICENSE.txt")
        shutil.copyfile(helper_source, APP / "bin/hash-password")
        (APP / "bin/hash-password").chmod(0o700)
        binary.chmod(0o700)
        private_write(APP / "provenance.json", json.dumps(metadata, indent=2) + "\n")
    try:
        version = subprocess.check_output([str(binary), "--version"], text=True).strip()
    except subprocess.CalledProcessError as error:
        raise RuntimeError("This Termux cannot run the Linux release. Use build-android.py and --binary; see README.") from error
    if release["version"] not in version:
        raise RuntimeError("Installed binary differs from pinned version")
    config = CONFIG / "AdGuardHome.yaml"
    login = CONFIG / "login.json"
    if not login.exists():
        if config.exists():
            raise RuntimeError("Existing config without credentials; refusing to overwrite")
        private_write(login, json.dumps({"username": "admin", "password": secrets.token_urlsafe(27)}) + "\n")
    credentials = json.loads(login.read_text())
    if not config.exists():
        # The first-run wizard requires privileged ports even if another port
        # is intended. Seed the documented config instead; root is unnecessary.
        hashed = subprocess.check_output([str(APP / "bin/hash-password")],
                                         input=credentials["password"].encode()).decode().strip()
        private_write(config, json.dumps({
            "schema_version": 34,
            "http": {"address": "127.0.0.1:13000"},
            "users": [{"name": credentials["username"], "password": hashed}],
            "language": "pt-br",
            "dns": {"bind_hosts": ["127.0.0.1", str(address)], "port": args.dns_port,
                    "allowed_clients": ["127.0.0.0/8", str(lan)],
                    "upstream_dns": ["https://dns.quad9.net/dns-query", "https://cloudflare-dns.com/dns-query"],
                    "bootstrap_dns": ["9.9.9.9", "1.1.1.1"],
                    "use_private_ptr_resolvers": False, "resolve_clients": False},
            "querylog": {"enabled": False},
        }, indent=2) + "\n")
    elif config.read_text().lstrip().startswith("{"):
        seed = json.loads(config.read_text())
        seed["dns"]["bind_hosts"] = ["127.0.0.1", str(address)]
        private_write(config, json.dumps(seed, indent=2) + "\n")
    else:
        private_write(config, expose_dns(config.read_text(), str(address)))
    command = [str(binary), "--config", str(config), "--work-dir", str(STATE),
               "--web-addr", "127.0.0.1:13000", "--no-check-update"]
    with (LOGS / "install.log").open("ab") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(60):
                if process.poll() is not None:
                    raise RuntimeError("AdGuard Home exited; inspect private install.log")
                try:
                    api("/filtering/status")
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.5)
            else:
                raise RuntimeError("Initial API did not become ready")
            api("/access/set", {"allowed_clients": ["127.0.0.0/8", str(lan)],
                                "disallowed_clients": [], "blocked_hosts": []})
            api("/dns_config", {
                "upstream_dns": ["https://dns.quad9.net/dns-query", "https://cloudflare-dns.com/dns-query"],
                "bootstrap_dns": ["9.9.9.9", "1.1.1.1"], "fallback_dns": [],
                "ratelimit": 100, "blocking_mode": "default",
                "use_private_ptr_resolvers": False, "resolve_clients": False,
            })
            querylog = api("/querylog/config")
            querylog.update(enabled=False, anonymize_client_ip=True)
            api("/querylog/config/update", querylog, method="PUT")
            api("/filtering/config", {"enabled": True, "interval": 24})
            api("/protection", {"enabled": True})
            api("/filtering/refresh", {"whitelist": False})
            filters = api("/filtering/status")
            enabled = [f for f in filters["filters"] if f["enabled"] and f.get("rules_count", 0) > 0]
            if not enabled:
                raise RuntimeError("No blocklist loaded; inspect network before activation")
            print("Blocklists loaded:", sum(f["rules_count"] for f in enabled), "rules", flush=True)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    # ACL is already saved before exposing DNS to the LAN. Web stays on loopback.
    previous = config.read_text()
    private_write(config, expose_dns(previous, str(address)))
    try:
        subprocess.run(command + ["--check-config"], check=True, stdout=subprocess.DEVNULL)
    except Exception:
        private_write(config, previous)
        raise
    private_write(CONFIG / "runtime.json", json.dumps({"lan": str(lan), "bind_address": str(address), "dns_port": args.dns_port}) + "\n")
    service = prefix / "var/service/homedns"
    if service.exists() and not (service / ".homedns-managed").exists():
        raise RuntimeError("Unmanaged homedns service exists; refusing to replace")
    (service / "log").mkdir(parents=True, exist_ok=True)
    (service / ".homedns-managed").touch(mode=0o600)
    import shlex
    private_write(service / "run", f"#!{prefix}/bin/sh\nexec 2>&1\numask 077\nexec " + shlex.join(command) + "\n")
    private_write(service / "log/run", f"#!{prefix}/bin/sh\nexec svlogd -tt {shlex.quote(str(LOGS / 'service'))}\n")
    (LOGS / "service").mkdir(mode=0o700, exist_ok=True)
    private_write(LOGS / "service/config", "s1000000\nn4\n")
    (service / "run").chmod(0o700)
    (service / "log/run").chmod(0o700)
    boot = Path.home() / ".termux/boot/60-homedns"
    private_write(boot, f"#!{prefix}/bin/sh\nexport PREFIX={prefix}\nexport PATH={prefix}/bin:$PATH\nexport SVDIR={prefix}/var/service\numask 077\n[ -f {service}/down ] && exit 0\ntermux-wake-lock\nservice-daemon start\nsv -w 20 up {service}\n")
    boot.chmod(0o700)
    subprocess.run(["termux-wake-lock"], check=True)
    # Google Play Termux returns 1 if the shared supervisor is already up.
    # The subsequent sv command is the actual readiness check.
    subprocess.run(["service-daemon", "start"], check=False)
    subprocess.run(["sv", "-w", "20", "up", str(service)], check=True)
    print("AdGuard Home installed. DNS:", args.dns_port, "Admin: loopback:13000")
    print("Wi-Fi cutover still requires router support for the nonstandard DNS port.")


if __name__ == "__main__":
    os.umask(0o077)
    main()
