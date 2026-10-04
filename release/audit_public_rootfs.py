#!/usr/bin/env python3
"""Inspect the public archive for required boot files and private-data paths."""

from __future__ import annotations

import argparse
import subprocess
import tarfile


REQUIRED = {
    "etc/polaris-ubuntu-rootfs",
    "etc/shadow",
    "etc/sudoers.d/90-polaris",
    "etc/netplan/01-polaris.yaml",
    "usr/lib/systemd/systemd",
    "etc/systemd/system/polaris-zram.service",
    "etc/systemd/system/multi-user.target.wants/polaris-zram.service",
    "usr/local/sbin/polaris-zram-setup",
    "usr/local/lib/polaris-zram/7.2.8-polaris/zram.ko",
    "usr/local/lib/polaris-zram/7.2.8-polaris/zsmalloc.ko",
    "home/polaris/.config/monitors.xml",
}
ALLOWED_HOME = {
    "home", "home/polaris", "home/polaris/.config",
    "home/polaris/.config/environment.d",
    "home/polaris/.config/monitors.xml",
    "home/polaris/.config/environment.d/60-polaris-gtk-renderer.conf",
}
BAD_PATH_MARKERS = (
    "1panel", "chatgpt", "clash-verge", "linuxqq", "qq.png",
    "ssh_host_", "etc/wpa_supplicant/", "system-connections/",
    "auth.conf", "polaris-stage-nm", "private/",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive")
    args = parser.parse_args()
    dec = subprocess.Popen(("zstd", "-dc", args.archive), stdout=subprocess.PIPE)
    assert dec.stdout is not None
    names = set()
    problems = []
    count = 0
    with tarfile.open(fileobj=dec.stdout, mode="r|") as archive:
        for item in archive:
            name = item.name.rstrip("/")
            names.add(name)
            count += 1
            if name.startswith("/") or ".." in name.split("/"):
                problems.append(f"unsafe path: {name}")
            if name.startswith("home/") and name not in ALLOWED_HOME:
                problems.append(f"unexpected home path: {name}")
            if any(marker in name.lower() for marker in BAD_PATH_MARKERS):
                problems.append(f"private/optional path: {name}")
            if name.startswith("var/") and not (
                name in {"var", "var/lib", "var/cache", "var/log", "var/tmp", "var/spool", "var/lib/apt", "var/lib/apt/lists"}
                or name.startswith("var/lib/dpkg/")
                or name == "var/lib/dpkg"
                or name == "var/lib/apt/extended_states"
            ):
                problems.append(f"unexpected var path: {name}")
            if item.isreg() and name in {"etc/shadow", "etc/gshadow", "etc/sudoers.d/90-polaris", "etc/gdm3/custom.conf", "var/lib/dpkg/status"}:
                f = archive.extractfile(item)
                assert f is not None
                data = f.read().decode("utf-8", "replace")
                if name in {"etc/shadow", "etc/gshadow"}:
                    for row in data.splitlines():
                        fields = row.split(":")
                        if len(fields) > 1 and fields[1] != "!":
                            problems.append(f"unlocked credential in {name}")
                elif name == "etc/sudoers.d/90-polaris" and "NOPASSWD" in data:
                    problems.append("passwordless sudo remains")
                elif name == "etc/gdm3/custom.conf" and "AutomaticLoginEnable=true" in data:
                    problems.append("automatic login remains")
                elif name == "var/lib/dpkg/status":
                    for package in ("clash-verge", "chatgpt", "linuxqq", "qq"):
                        if f"Package: {package}\n" in data:
                            problems.append(f"removed {package} package still in dpkg status")
    code = dec.wait()
    if code:
        problems.append(f"zstd decompression exited {code}")
    problems.extend(f"missing {name}" for name in sorted(REQUIRED - names))
    print(f"archive entries: {count}; required entries: {len(REQUIRED & names)}/{len(REQUIRED)}; issues: {len(problems)}")
    for problem in problems[:50]:
        print(problem)
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
