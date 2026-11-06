#!/usr/bin/env python3
"""Manage only HomeDNS, preserving other Termux services."""
import argparse
import datetime
import json
import os
import subprocess
import tarfile

from common import APP, CONFIG, STATE, LOGS, api


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "start", "stop", "restart", "refresh", "backup", "logs"))
    args = parser.parse_args()
    service = os.environ["PREFIX"] + "/var/service/homedns"
    if args.action in ("start", "stop", "restart"):
        if args.action == "stop":
            # sv down alone is lost at reboot; down persists operator intent.
            from pathlib import Path
            (Path(service) / "down").touch(mode=0o600)
        elif args.action == "start":
            from pathlib import Path
            (Path(service) / "down").unlink(missing_ok=True)
        subprocess.run(["sv", "-w", "20", {"start": "up", "stop": "down", "restart": "restart"}[args.action], service], check=True)
    elif args.action == "status":
        subprocess.run(["sv", "status", service], check=True)
        status = api("/status")
        filters = api("/filtering/status")
        print(json.dumps({"version": status["version"], "dns_port": status["dns_port"],
                          "protection_enabled": status["protection_enabled"],
                          "filters": [{k: f.get(k) for k in ("name", "enabled", "rules_count")} for f in filters["filters"]]}, indent=2))
    elif args.action == "refresh":
        print(api("/filtering/refresh", {"whitelist": False}))
    elif args.action == "logs":
        subprocess.run(["tail", "-n", "60", str(LOGS / "service/current")], check=True)
    elif args.action == "backup":
        # Stop briefly so mutable data and YAML are consistent. Preserve stopped state.
        result = subprocess.check_output(["sv", "status", service], text=True)
        running = result.startswith("run:")
        if running:
            subprocess.run(["sv", "-w", "20", "down", service], check=True)
        try:
            directory = STATE.parent / "homedns-backups"
            directory.mkdir(mode=0o700, exist_ok=True)
            filename = directory / ("homedns-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".tar.gz")
            with tarfile.open(filename, "w:gz") as tar:
                tar.add(CONFIG, arcname="config")
                tar.add(STATE, arcname="data")
                if (APP / "provenance.json").exists():
                    tar.add(APP / "provenance.json", arcname="provenance.json")
            filename.chmod(0o600)
            print("Private backup:", filename)
        finally:
            if running:
                subprocess.run(["sv", "-w", "20", "up", service], check=True)


if __name__ == "__main__":
    os.umask(0o077)
    main()
