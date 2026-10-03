#!/usr/bin/env python3
"""Create/update a GitHub prerelease, then publish after all assets upload.

The token is obtained through the host's existing Git credential helper and
is never printed or placed on a command line.  A failed upload leaves a draft
that can be resumed with the same arguments.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

import requests


REPO = "FanzhouStudio/-mix2s-Linux"
API = f"https://api.github.com/repos/{REPO}"


def credential() -> str:
    result = subprocess.run(
        ["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
        text=True, capture_output=True, check=True,
    )
    fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    return fields["password"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_request(session: requests.Session, method: str, url: str, **kwargs):
    response = session.request(method, url, timeout=(20, 120), **kwargs)
    if response.status_code >= 400:
        raise RuntimeError(f"GitHub {method} failed ({response.status_code}): {response.text[:600]}")
    return response.json() if response.content else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", type=Path, required=True)
    parser.add_argument("--asset", type=Path, action="append", required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    assets = args.asset
    for asset in assets:
        if not asset.is_file():
            parser.error(f"asset missing: {asset}")
        if asset.stat().st_size >= 2 * 1024**3:
            parser.error(f"GitHub asset must be below 2 GiB: {asset}")

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {credential()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "polaris-ubuntu-release",
    })
    lookup = session.get(f"{API}/releases/tags/{args.tag}", timeout=(20, 120))
    if lookup.status_code == 404:
        release = json_request(session, "POST", f"{API}/releases", json={
            "tag_name": args.tag, "name": args.title,
            "body": args.body.read_text(), "draft": True, "prerelease": True,
        })
        print(f"Created draft release {args.tag}", flush=True)
    elif lookup.ok:
        release = lookup.json()
        if not release["draft"]:
            raise RuntimeError("release already published; refusing to replace assets")
        release = json_request(session, "PATCH", release["url"], json={
            "name": args.title, "body": args.body.read_text(), "prerelease": True,
        })
        print(f"Resuming draft release {args.tag}", flush=True)
    else:
        raise RuntimeError(f"GitHub release lookup failed ({lookup.status_code}): {lookup.text[:600]}")

    for path in assets:
        name = path.name
        size = path.stat().st_size
        digest = sha256(path)
        old = next((item for item in release["assets"] if item["name"] == name), None)
        if old is not None:
            if old["size"] == size and old.get("digest") == f"sha256:{digest}" and old["state"] == "uploaded":
                print(f"Already uploaded: {name}", flush=True)
                continue
            json_request(session, "DELETE", old["url"])
        upload_url = release["upload_url"].split("{", 1)[0]
        print(f"Uploading {name} ({size} bytes)", flush=True)
        with path.open("rb") as stream:
            response = session.post(
                upload_url, params={"name": name},
                headers={"Content-Type": "application/octet-stream"},
                data=stream, timeout=(30, 3600),
            )
        if response.status_code != 201:
            raise RuntimeError(f"GitHub asset upload failed ({response.status_code}): {response.text[:600]}")
        item = response.json()
        if item["size"] != size or item["state"] != "uploaded":
            raise RuntimeError(f"GitHub did not confirm complete upload: {name}")
        if item.get("digest") and item["digest"] != f"sha256:{digest}":
            raise RuntimeError(f"GitHub digest mismatch: {name}")
        print(f"Uploaded {name}", flush=True)
        release = json_request(session, "GET", release["url"])

    expected = {path.name for path in assets}
    actual = {item["name"] for item in release["assets"] if item["state"] == "uploaded"}
    if not expected <= actual:
        raise RuntimeError(f"missing release assets: {sorted(expected - actual)}")
    if args.publish:
        release = json_request(session, "PATCH", release["url"], json={"draft": False, "prerelease": True})
        print(f"Published {release['html_url']}", flush=True)
    else:
        print(f"Draft ready: {release['html_url']}", flush=True)


if __name__ == "__main__":
    main()
