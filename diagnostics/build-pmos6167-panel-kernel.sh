#!/usr/bin/env bash
# Build the official SDM845 6.16.7 source with the historical Polaris panel fix.
# This script only writes host files. Use the separate RAM diagnostic packager
# and `fastboot boot` before considering any partition update.
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src_dir="$repo_dir/../linux-sdm845-6.16.7-r0"
out_dir="$repo_dir/../out-pmos6167-panel"
source_tar="$repo_dir/downloads/linux-sdm845-6.16.7-r0.tar.gz"
panel_source="$src_dir/drivers/gpu/drm/panel/panel-novatek-nt35596s.c"

printf '%s  %s\n' \
  '803d2cf85b248c3da41a9c9178d69d211eccf5d1adb72acd5343e09cbb65782f727e579939287c91712c69a862bed7344a0e2bc893c2791a971b6fed95ec6f1a' \
  "$source_tar" | sha512sum -c -
printf '%s  %s\n' \
  'd7c857500348a1420ccd1a255c667704e54ee88f5c563bcb92885aaa5a9b5dc5a87d12ab782822de523d01c63b277ff60b57cc5307a0663bf42ad7b69da3d1c5' \
  "$repo_dir/diagnostics/patches/0001-polaris-panel-prepare-prev-first.patch" | sha512sum -c -
printf '%s  %s\n' \
  'cca4392d651fbc95ebee97f4d890e72c982a27241c254cba88b8ea159427239f' \
  "$repo_dir/artifacts/pmos6167/kernel.config" | sha256sum -c -

if [[ $(grep -Fxc $'\tpinfo->base.prepare_prev_first = true;' "$panel_source") != 1 ]]; then
  echo 'Expected historical NT35596S panel fix is absent or duplicated' >&2
  exit 1
fi

mkdir -p "$out_dir"
cp "$repo_dir/artifacts/pmos6167/kernel.config" "$out_dir/.config"
make -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 \
  KBUILD_BUILD_VERSION=4-postmarketos-qcom-sdm845 olddefconfig
make -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 \
  KBUILD_BUILD_VERSION=4-postmarketos-qcom-sdm845 -j2 Image.gz

release=$(make -s -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 kernelrelease)
if [[ "$release" != '6.16.7-sdm845' ]]; then
  echo "Kernel release mismatch: $release" >&2
  exit 1
fi
printf 'Built %s, release %s, SHA256 ' "$out_dir/arch/arm64/boot/Image.gz" "$release"
sha256sum "$out_dir/arch/arm64/boot/Image.gz"
