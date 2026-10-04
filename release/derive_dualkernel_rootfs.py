#!/usr/bin/env python3
"""Add the verified 7.2.8 zram files to the audited public Ubuntu rootfs.

This works entirely on the host. It avoids another large read of the phone's
userdata after live exports stalled under both the 7.2.8 and 6.1 kernels.
"""

from __future__ import annotations

import argparse
import subprocess
import tarfile
from pathlib import Path


def add_file(archive: tarfile.TarFile, name: str, source: Path, mode: int) -> None:
    item = tarfile.TarInfo(name)
    item.mode = mode
    item.uid = 0
    item.gid = 0
    item.mtime = 0
    item.size = source.stat().st_size
    with source.open("rb") as stream:
        archive.addfile(item, stream)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    root = Path(__file__).resolve().parent
    additions = (
        ("etc/systemd/system/polaris-zram.service", root / "../diagnostics/polaris-zram.service", 0o644),
        ("usr/local/sbin/polaris-zram-setup", root / "../diagnostics/polaris-zram-setup", 0o755),
        ("usr/local/lib/polaris-zram/7.2.8-polaris/zsmalloc.ko", root / "../diagnostics/modules/7.2.8-polaris/zsmalloc.ko", 0o644),
        ("usr/local/lib/polaris-zram/7.2.8-polaris/zram.ko", root / "../diagnostics/modules/7.2.8-polaris/zram.ko", 0o644),
    )
    decoder = subprocess.Popen(("zstd", "-dc", str(args.base)), stdout=subprocess.PIPE)
    encoder = subprocess.Popen(("zstd", "-T2", "-3", "-q", "-o", str(args.output)), stdin=subprocess.PIPE)
    assert decoder.stdout is not None and encoder.stdin is not None
    count = 0
    try:
        with tarfile.open(fileobj=decoder.stdout, mode="r|") as source, \
                tarfile.open(fileobj=encoder.stdin, mode="w|", format=tarfile.PAX_FORMAT) as target:
            for item in source:
                if item.name.startswith("/") or ".." in item.name.split("/"):
                    raise ValueError(f"unsafe base path: {item.name}")
                if item.isreg():
                    content = source.extractfile(item)
                    assert content is not None
                    target.addfile(item, content)
                else:
                    target.addfile(item)
                count += 1

            for name in (
                "usr/local/lib/polaris-zram",
                "usr/local/lib/polaris-zram/7.2.8-polaris",
            ):
                item = tarfile.TarInfo(name)
                item.type = tarfile.DIRTYPE
                item.mode = 0o755
                item.uid = item.gid = item.mtime = 0
                target.addfile(item)
            for name, path, mode in additions:
                add_file(target, name, path, mode)
            item = tarfile.TarInfo("etc/systemd/system/multi-user.target.wants/polaris-zram.service")
            item.type = tarfile.SYMTYPE
            item.linkname = "../polaris-zram.service"
            item.mode = 0o777
            item.uid = item.gid = item.mtime = 0
            target.addfile(item)
    finally:
        encoder.stdin.close()
        decoder.stdout.close()
    if decoder.wait() or encoder.wait():
        raise RuntimeError("rootfs derivation failed; do not publish the output")
    print(f"wrote {args.output}; copied {count} base entries and added 7.2.8 zram files")


if __name__ == "__main__":
    main()
