#!/bin/sh
# Reproduce the RAM-only arm64 Xvfb runtime for the integrated diagnostic boot.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
bundle="$root/artifacts/linux728-polaris-candidate/xvfb-offscreen"
mkdir -p "$bundle/root"

if [ ! -f "$bundle/xvfb_21.1.22-1ubuntu1.2_arm64.deb" ]; then
    curl -fL --retry 3 -o "$bundle/xvfb_21.1.22-1ubuntu1.2_arm64.deb" \
        https://ports.ubuntu.com/ubuntu-ports/pool/universe/x/xorg-server/xvfb_21.1.22-1ubuntu1.2_arm64.deb
fi
if [ ! -f "$bundle/libunwind8_1.8.3-0ubuntu1_arm64.deb" ]; then
    curl -fL --retry 3 -o "$bundle/libunwind8_1.8.3-0ubuntu1_arm64.deb" \
        https://ports.ubuntu.com/ubuntu-ports/pool/main/libu/libunwind/libunwind8_1.8.3-0ubuntu1_arm64.deb
fi

(
    cd "$bundle"
    printf '%s  %s\n' \
        804bf4c17ed6c96fe27c2c08a2351f3a91642357f8f556f43a451d81a1d15a6e xvfb_21.1.22-1ubuntu1.2_arm64.deb \
        a20a6c94339bc429223bc7d4205b756f223fd4418cf10e9a52761babe9252168 libunwind8_1.8.3-0ubuntu1_arm64.deb |
        sha256sum -c -
)
dpkg-deb -x "$bundle/xvfb_21.1.22-1ubuntu1.2_arm64.deb" "$bundle/root"
dpkg-deb -x "$bundle/libunwind8_1.8.3-0ubuntu1_arm64.deb" "$bundle/root"
tar --sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner \
    -C "$bundle/root" -czf "$bundle/xvfb-runtime-arm64.tgz" \
    usr/bin/Xvfb usr/lib/aarch64-linux-gnu
sha256sum "$bundle/xvfb-runtime-arm64.tgz"
