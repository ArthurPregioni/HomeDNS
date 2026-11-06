#!/usr/bin/env python3
"""Compile pinned upstream source with a small Termux argv compatibility shim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go", default="go")
    args = parser.parse_args()
    release = json.loads((ROOT / "config/release.json").read_text())
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    source = cache / "AdGuardHome-source"
    artifact = cache / "android-arm64"
    artifact.mkdir(exist_ok=True)
    if not source.exists():
        subprocess.run(["git", "clone", "--depth", "1", "--branch", release["version"],
                        "https://github.com/AdguardTeam/AdGuardHome.git", str(source)], check=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if commit != release["source_commit"]:
        raise RuntimeError("Unexpected upstream commit")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=source):
        raise RuntimeError("Upstream source modified; refusing to build")
    import shutil
    shim = ROOT / "config/android-argv.go"
    shutil.copyfile(shim, source / "homedns_android_argv.go")
    go_version = subprocess.check_output([args.go, "version"], text=True).strip()
    if ("go" + release["go_version"] + " ") not in go_version:
        raise RuntimeError("Use Go " + release["go_version"])
    subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=source / "client_v2", check=True)
    subprocess.run(["npm", "run", "build-prod"], cwd=source / "client_v2", check=True)
    package = "github.com/AdguardTeam/AdGuardHome/internal/version"
    flags = f"-s -w -X {package}.version={release['version']} -X {package}.channel=development"
    env = dict(os.environ, CGO_ENABLED="0", GOOS="android", GOARCH="arm64", GOTELEMETRY="off", GOTOOLCHAIN="local")
    output = artifact / "AdGuardHome"
    subprocess.run([args.go, "build", "-trimpath", "-buildmode=pie", "-ldflags", flags,
                    "-o", str(output), "."], cwd=source, env=env, check=True)
    helper = artifact / "hash-password"
    subprocess.run([args.go, "build", "-trimpath", "-buildmode=pie", "-ldflags", "-s -w",
                    "-o", str(helper), str(ROOT / "config/hash-password.go")],
                   cwd=source, env=env, check=True)
    (artifact / "provenance.json").write_text(json.dumps({
        "version": release["version"], "source_commit": commit,
        "go_version": go_version, "target": "android/arm64", "buildmode": "pie",
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "argv_shim_sha256": hashlib.sha256(shim.read_bytes()).hexdigest(),
        "hash_helper_sha256": hashlib.sha256(helper.read_bytes()).hexdigest(),
        "hash_source_sha256": hashlib.sha256((ROOT / "config/hash-password.go").read_bytes()).hexdigest(),
    }, indent=2) + "\n")
    shutil.copyfile(source / "LICENSE.txt", artifact / "ADGUARD-LICENSE.txt")
    print("Android build:", output)


if __name__ == "__main__":
    main()
