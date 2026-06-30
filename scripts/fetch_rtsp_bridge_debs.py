#!/usr/bin/env python3
from __future__ import annotations

import argparse
import lzma
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT_PACKAGES = (
    "python3-gi",
    "python3-gst-1.0",
    "gir1.2-gst-rtsp-server-1.0",
    "gstreamer1.0-plugins-base",
    "gstreamer1.0-plugins-good",
    "gstreamer1.0-plugins-ugly",
)

BASE_URL = "http://ports.ubuntu.com/ubuntu-ports"
SUITES = ("jammy", "jammy-updates", "jammy-security")
COMPONENTS = ("main", "universe", "multiverse")
DEP_FIELDS = ("Pre-Depends", "Depends")
USER_AGENT = "dog-remote-tool-deb-fetch/1.0"


def open_url(url: str, timeout: int):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=timeout)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch arm64 RTSP bridge debs for offline robots.")
    root = Path(__file__).resolve().parents[1]
    default_out = root / "resources" / "rtsp_bridge" / "ubuntu22.04-arm64" / "debs"
    parser.add_argument("output", nargs="?", default=str(default_out))
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--arch", default="arm64")
    parser.add_argument("--suite", action="append", dest="suites")
    return parser.parse_args()


def parse_packages(text: str) -> list[dict[str, str]]:
    packages: list[dict[str, str]] = []
    current: dict[str, str] = {}
    last_key = ""
    for line in text.splitlines():
        if not line:
            if current:
                packages.append(current)
            current = {}
            last_key = ""
            continue
        if line.startswith(" ") and last_key:
            current[last_key] += "\n" + line[1:]
            continue
        key, _, value = line.partition(":")
        if not value:
            continue
        last_key = key
        current[key] = value.strip()
    if current:
        packages.append(current)
    return packages


def version_newer(new: str, old: str) -> bool:
    if not old:
        return True
    try:
        return subprocess.run(
            ["dpkg", "--compare-versions", new, "gt", old],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0
    except OSError:
        return new > old


def load_index(base_url: str, suites: tuple[str, ...], arch: str) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for suite in suites:
        for component in COMPONENTS:
            url = f"{base_url}/dists/{suite}/{component}/binary-{arch}/Packages.xz"
            print(f"[rtsp-debs] index {url}", flush=True)
            try:
                with open_url(url, timeout=30) as response:
                    data = lzma.decompress(response.read()).decode("utf-8", errors="replace")
            except Exception as exc:
                print(f"[rtsp-debs] WARN: cannot read {url}: {exc}", file=sys.stderr, flush=True)
                continue
            for package in parse_packages(data):
                name = package.get("Package", "")
                if not name:
                    continue
                old = index.get(name, {})
                if version_newer(package.get("Version", ""), old.get("Version", "")):
                    index[name] = package
    return index


def split_dep_groups(value: str) -> list[str]:
    groups: list[str] = []
    start = 0
    depth = 0
    for pos, char in enumerate(value):
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char == "," and depth == 0:
            groups.append(value[start:pos].strip())
            start = pos + 1
    tail = value[start:].strip()
    if tail:
        groups.append(tail)
    return groups


def dep_name(text: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9+.-]*)(?::[A-Za-z0-9-]+|:any)?", text)
    return match.group(1) if match else ""


def dependencies(package: dict[str, str], index: dict[str, dict[str, str]]) -> list[str]:
    result: list[str] = []
    for field in DEP_FIELDS:
        for group in split_dep_groups(package.get(field, "")):
            for alternative in group.split("|"):
                name = dep_name(alternative)
                if name in index:
                    result.append(name)
                    break
    return result


def resolve(root_packages: tuple[str, ...], index: dict[str, dict[str, str]]) -> list[str]:
    missing = [name for name in root_packages if name not in index]
    if missing:
        raise SystemExit(f"[rtsp-debs] ERROR: packages missing from index: {', '.join(missing)}")
    seen: set[str] = set()
    ordered: list[str] = []
    queue = list(root_packages)
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        ordered.append(name)
        queue.extend(dep for dep in dependencies(index[name], index) if dep not in seen)
    return ordered


def download(base_url: str, package: dict[str, str], output: Path) -> None:
    filename = package["Filename"]
    url = f"{base_url}/{filename}"
    target = output / Path(filename).name
    if target.exists() and target.stat().st_size > 0:
        print(f"[rtsp-debs] keep {target.name}", flush=True)
        return
    print(f"[rtsp-debs] get {target.name}", flush=True)
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with open_url(url, timeout=60) as response:
                target.write_bytes(response.read())
            return
        except Exception as exc:
            last_error = exc
            print(f"[rtsp-debs] WARN: retry {attempt}/3 failed for {target.name}: {exc}", file=sys.stderr, flush=True)
            time.sleep(attempt)
    raise RuntimeError(f"failed to download {url}") from last_error


def main() -> int:
    args = parse_args()
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    suites = tuple(args.suites) if args.suites else SUITES
    index = load_index(args.base_url, suites, args.arch)
    packages = resolve(ROOT_PACKAGES, index)
    print(f"[rtsp-debs] resolved {len(packages)} packages", flush=True)
    for name in packages:
        download(args.base_url, index[name], output)
    manifest = output.parent / "manifest.txt"
    manifest.write_text(
        "\n".join(f"{name} {index[name].get('Version', '')}" for name in packages) + "\n",
        encoding="utf-8",
    )
    print(f"[rtsp-debs] wrote {manifest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
