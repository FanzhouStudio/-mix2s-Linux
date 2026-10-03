#!/usr/bin/env python3
"""Stream a sanitized Polaris system snapshot into a public tar.zst archive.

Run on the host over SSH or from a read-only mounted partition in ADB recovery.
The phone only reads its root filesystem.  No home directory, private service
state, Android partitions, or personal network configuration is transferred.
This archive is a system base, not a backup of user data.
"""

from __future__ import annotations

import argparse
import io
import os
import shlex
import subprocess
import sys
import tarfile
import time
from pathlib import Path


READ_PATHS = (
    "etc", "usr", "bin", "sbin", "lib", "boot",
    "var/lib/dpkg", "var/lib/apt/extended_states",
)

MONITORS_XML = '''<monitors version="2">
  <configuration>
    <layoutmode>logical</layoutmode>
    <logicalmonitor>
      <x>0</x><y>0</y><scale>1.6666666269302368</scale><primary>yes</primary>
      <monitor>
        <monitorspec><connector>DSI-1</connector><vendor>unknown</vendor><product>unknown</product><serial>unknown</serial></monitorspec>
        <mode><width>1080</width><height>2160</height><rate>60.000</rate></mode>
      </monitor>
    </logicalmonitor>
  </configuration>
</monitors>
'''

# Filter both names and subtrees.  Package-owned optional applications are
# omitted because their archives, account state, or licenses are not part of
# the public Ubuntu base.
SKIP_PREFIXES = (
    "etc/1panel", "etc/NetworkManager", "etc/netplan",
    "etc/apt/auth.conf.d", "etc/ssl/private", "etc/wpa_supplicant",
    "etc/wireguard", "etc/openvpn", "etc/ppp", "etc/ModemManager",
    "etc/systemd/system/1panel", "etc/systemd/system/opt-QQ.mount",
    "etc/systemd/system/polaris-chatgpt-mount.service",
    "etc/default/chatgpt", "etc/apparmor.d/chatgpt.dpkg-new",
    "usr/lib/Clash Verge", "usr/lib/chatgpt",
    "usr/lib/chatgpt-incomplete-", "usr/share/doc/clash-verge",
    "usr/share/applications/Clash Verge.desktop",
    "usr/share/applications/qq.desktop",
    "usr/share/applications/qq.desktop.dpkg-new",
    "usr/local/bin/1panel", "usr/local/bin/1pctl",
    "usr/local/bin/chatgpt", "usr/local/bin/polaris-open-1panel",
    "usr/local/bin/polaris-qq-", "usr/local/etc",
    "usr/local/sbin/polaris-1panel", "usr/local/sbin/polaris-stage-nm",
    "usr/local/sbin/polaris-backup-stable",
    "usr/bin/clash-verge", "usr/bin/verge-mihomo",
    "usr/bin/qq", "var/lib/dpkg/info/clash-verge.",
    "var/lib/dpkg/info/chatgpt.", "var/lib/dpkg/info/linuxqq.",
    "var/lib/dpkg/info/qq.",
)
SKIP_EXACT = {
    "etc/crypttab", "etc/ssh/ssh_host_keys", "etc/shadow-",
    "etc/gshadow-", "etc/passwd-", "etc/group-",
    "etc/apt/auth.conf", "usr/share/applications/chatgpt.desktop",
}
SKIP_NAME_PARTS = (
    "clash-verge", "1panel", "chatgpt", "opt-qq.mount", "qq.png", "linuxqq",
)


def excluded(name: str) -> bool:
    if name in SKIP_EXACT:
        return True
    if (name.startswith("etc/shadow") and name != "etc/shadow") or \
            (name.startswith("etc/gshadow") and name != "etc/gshadow"):
        return True
    if name.startswith("etc/ssh/ssh_host_"):
        return True
    if any(name == p or name.startswith(p + "/") for p in SKIP_PREFIXES):
        return True
    if any(name.startswith(p) for p in (
        "usr/lib/chatgpt-incomplete-", "usr/local/bin/polaris-qq-",
        "var/lib/dpkg/info/clash-verge.", "var/lib/dpkg/info/chatgpt.",
        "var/lib/dpkg/info/linuxqq.", "var/lib/dpkg/info/qq.",
        "usr/local/bin/1panel",
        "usr/local/sbin/polaris-1panel", "usr/bin/clash-verge",
        "usr/bin/verge-mihomo", "etc/systemd/system/polaris-1panel",
    )):
        return True
    parts = name.split("/")
    return any(part.lower().startswith(SKIP_NAME_PARTS) for part in parts)


def sanitize_shadow(data: bytes) -> bytes:
    lines = []
    for line in data.decode("utf-8").splitlines():
        fields = line.split(":")
        if len(fields) >= 2:
            fields[1] = "!"
        lines.append(":".join(fields))
    return ("\n".join(lines) + "\n").encode()


def sanitize_status(data: bytes) -> bytes:
    stanzas = data.decode("utf-8").strip().split("\n\n")
    excluded_packages = {"clash-verge", "chatgpt", "linuxqq", "qq"}
    kept = []
    for stanza in stanzas:
        package_line = next((line for line in stanza.splitlines() if line.startswith("Package: ")), "")
        package = package_line.removeprefix("Package: ").lower()
        if package not in excluded_packages:
            kept.append(stanza)
    return ("\n\n".join(kept) + "\n").encode()


def replacement(name: str, content: bytes) -> bytes | None:
    if name in ("etc/shadow", "etc/gshadow"):
        return sanitize_shadow(content)
    if name == "etc/sudoers.d/90-polaris":
        return b"polaris ALL=(ALL:ALL) ALL\n"
    if name == "etc/machine-id":
        return b""
    if name == "etc/hostname":
        return b"polaris-ubuntu\n"
    if name == "etc/hosts":
        return b"127.0.0.1 localhost\n127.0.1.1 polaris-ubuntu\n::1 localhost ip6-localhost ip6-loopback\n"
    if name == "etc/gdm3/custom.conf":
        text = content.decode("utf-8")
        text = text.replace("AutomaticLoginEnable=true", "AutomaticLoginEnable=false")
        text = text.replace("AutomaticLogin=polaris", "# AutomaticLogin=polaris")
        return text.encode()
    if name == "var/lib/dpkg/status":
        return sanitize_status(content)
    return None


class RateLimitedReader:
    def __init__(self, stream, rate: int):
        self.stream = stream
        self.rate = rate
        self.started = time.monotonic()
        self.total = 0

    def read(self, size: int = -1) -> bytes:
        data = self.stream.read(size)
        self.total += len(data)
        delay = self.total / self.rate - (time.monotonic() - self.started)
        if delay > 0:
            time.sleep(delay)
        return data


def add_dir(archive: tarfile.TarFile, name: str, mode: int, uid=0, gid=0) -> None:
    item = tarfile.TarInfo(name)
    item.type = tarfile.DIRTYPE
    item.mode = mode
    item.uid = uid
    item.gid = gid
    item.mtime = 0
    archive.addfile(item)


def add_text(archive: tarfile.TarFile, name: str, content: str, mode=0o644) -> None:
    data = content.encode()
    item = tarfile.TarInfo(name)
    item.mode = mode
    item.uid = 0
    item.gid = 0
    item.mtime = 0
    item.size = len(data)
    archive.addfile(item, io.BytesIO(data))


def add_home_text(archive: tarfile.TarFile, name: str, content: str) -> None:
    data = content.encode()
    item = tarfile.TarInfo(name)
    item.mode = 0o644
    item.uid = 1000
    item.gid = 1104
    item.mtime = 0
    item.size = len(data)
    archive.addfile(item, io.BytesIO(data))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("ssh", "adb"), default="ssh")
    parser.add_argument("--host")
    parser.add_argument("--identity", type=Path)
    parser.add_argument("--known-hosts", type=Path)
    parser.add_argument("--adb-bin", type=Path)
    parser.add_argument("--root-dir", default="/mnt/ubuntu")
    parser.add_argument("--adb-excludes", default="/tmp/polaris-public-excludes")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rate-mib", type=float, default=3.0)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    if args.rate_mib <= 0:
        parser.error("rate must be positive")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.transport == "ssh":
        if not all((args.host, args.identity, args.known_hosts)):
            parser.error("SSH requires --host, --identity and --known-hosts")
        remote = shlex.join((
            "sudo", "-n", "ionice", "-c3", "nice", "-n", "15", "tar",
            "--one-file-system", "--numeric-owner", "--acls", "--xattrs",
            "-C", "/", "-cf", "-", *READ_PATHS,
        ))
        command = (
            "ssh", "-i", str(args.identity), "-o", "BatchMode=yes",
            "-o", "Compression=no", "-o", "StrictHostKeyChecking=yes",
            "-o", f"UserKnownHostsFile={args.known_hosts}",
            f"polaris@{args.host}", remote,
        )
    else:
        if not args.adb_bin:
            parser.error("ADB requires --adb-bin")
        remote = shlex.join((
            "tar", "-C", args.root_dir, "-X", args.adb_excludes,
            "-cf", "-", *READ_PATHS,
        ))
        command = (str(args.adb_bin), "exec-out", "sh", "-c", remote)
    source_proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    zstd = subprocess.Popen((
        "zstd", "-T2", "-3", "-q", "-o", str(args.output),
    ), stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    count = 0
    omitted = 0
    try:
        assert source_proc.stdout is not None and zstd.stdin is not None
        reader = RateLimitedReader(source_proc.stdout, int(args.rate_mib * 1024 * 1024))
        with tarfile.open(fileobj=reader, mode="r|") as source, \
                tarfile.open(fileobj=zstd.stdin, mode="w|", format=tarfile.PAX_FORMAT) as target:
            for item in source:
                name = item.name.lstrip("./")
                if not name or name.startswith("/") or ".." in name.split("/"):
                    continue
                if excluded(name):
                    omitted += 1
                    continue
                item.name = name
                item.pax_headers.pop("path", None)
                item.uname = ""
                item.gname = ""
                if item.isreg():
                    content = source.extractfile(item)
                    assert content is not None
                    if name in (
                        "etc/shadow", "etc/gshadow", "etc/sudoers.d/90-polaris",
                        "etc/machine-id", "etc/hostname", "etc/hosts",
                        "etc/gdm3/custom.conf", "var/lib/dpkg/status",
                    ):
                        data = replacement(name, content.read())
                        assert data is not None
                        item.size = len(data)
                        target.addfile(item, io.BytesIO(data))
                    else:
                        target.addfile(item, content)
                else:
                    target.addfile(item)
                count += 1
                if count % 10000 == 0:
                    print(f"archived {count} entries; read {reader.total // 1048576} MiB", file=sys.stderr, flush=True)

            for name, mode, uid, gid in (
                ("dev", 0o755, 0, 0), ("proc", 0o555, 0, 0),
                ("sys", 0o555, 0, 0), ("run", 0o755, 0, 0),
                ("tmp", 0o1777, 0, 0), ("root", 0o700, 0, 0),
                ("home", 0o755, 0, 0), ("home/polaris", 0o700, 1000, 1104),
                ("opt", 0o755, 0, 0), ("mnt", 0o755, 0, 0),
                ("media", 0o755, 0, 0), ("srv", 0o755, 0, 0),
                ("var", 0o755, 0, 0), ("var/lib", 0o755, 0, 0),
                ("var/cache", 0o755, 0, 0), ("var/log", 0o755, 0, 0),
                ("var/tmp", 0o1777, 0, 0), ("var/spool", 0o755, 0, 0),
                ("var/lib/apt", 0o755, 0, 0), ("var/lib/apt/lists", 0o755, 0, 0),
                ("etc/NetworkManager", 0o755, 0, 0),
                ("etc/NetworkManager/system-connections", 0o700, 0, 0),
                ("etc/netplan", 0o755, 0, 0),
                ("home/polaris/.config", 0o700, 1000, 1104),
                ("home/polaris/.config/environment.d", 0o700, 1000, 1104),
            ):
                add_dir(target, name, mode, uid, gid)
            add_text(target, "etc/netplan/01-polaris.yaml", "network:\n  version: 2\n  renderer: NetworkManager\n")
            add_home_text(target, "home/polaris/.config/monitors.xml", MONITORS_XML)
            add_home_text(target, "home/polaris/.config/environment.d/60-polaris-gtk-renderer.conf", "GSK_RENDERER=gl\n")
    finally:
        if zstd.stdin is not None:
            zstd.stdin.close()

    source_error = source_proc.stderr.read().decode("utf-8", "replace") if source_proc.stderr else ""
    zstd_error = zstd.stderr.read().decode("utf-8", "replace") if zstd.stderr else ""
    source_code = source_proc.wait()
    zstd_code = zstd.wait()
    if source_code or zstd_code:
        raise RuntimeError(f"export failed: source={source_code}, zstd={zstd_code}; {source_error}; {zstd_error}")
    print(f"archive complete: {args.output}; entries={count}, omitted={omitted}")


if __name__ == "__main__":
    main()
