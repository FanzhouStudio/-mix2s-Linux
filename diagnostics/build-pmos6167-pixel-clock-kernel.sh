#!/usr/bin/env bash
# Build the SDM845 pixel-clock candidate on the host. No phone writes.
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src_dir="$repo_dir/../linux-sdm845-6.16.7-r0"
out_dir="$repo_dir/../out-pmos6167-panel"
patch_file="$repo_dir/diagnostics/patches/0002-sdm845-pixel-clock-parent-enable.patch"
source_file="$src_dir/drivers/clk/qcom/dispcc-sdm845.c"

printf '%s  %s\n' \
  '803d2cf85b248c3da41a9c9178d69d211eccf5d1adb72acd5343e09cbb65782f727e579939287c91712c69a862bed7344a0e2bc893c2791a971b6fed95ec6f1a' \
  "$repo_dir/downloads/linux-sdm845-6.16.7-r0.tar.gz" | sha512sum -c -
printf '%s  %s\n' \
  'cca4392d651fbc95ebee97f4d890e72c982a27241c254cba88b8ea159427239f' \
  "$repo_dir/artifacts/pmos6167/kernel.config" | sha256sum -c -

if [[ $(grep -Fxc $'\tpinfo->base.prepare_prev_first = true;' \
  "$src_dir/drivers/gpu/drm/panel/panel-novatek-nt35596s.c") != 1 ]]; then
  echo 'Verified Polaris panel fix missing or duplicated' >&2
  exit 1
fi

if [[ $(grep -Fc 'CLK_SET_RATE_PARENT | CLK_OPS_PARENT_ENABLE' "$source_file") == 0 ]]; then
  patch -d "$src_dir" -p1 -i "$patch_file"
fi
if [[ $(grep -Fc 'CLK_SET_RATE_PARENT | CLK_OPS_PARENT_ENABLE' "$source_file") != 2 ]]; then
  echo 'Pixel-clock fix missing or duplicated' >&2
  exit 1
fi

printf '%s  %s\n' \
  '88d10d5a5b987ea0533771aab84b7b385b0d4cedbcc4b444a3ae69a92d7a6b21' \
  "$out_dir/.config" | sha256sum -c -
printf '%s  %s\n' \
  'd0e49e79bd438b68f6a6797b9b08f22151138d2e4c0cc09cffacd55db62d95df' \
  "$repo_dir/artifacts/pmos6167-panel-baseline-Image.gz" | sha256sum -c -
make -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 \
  KBUILD_BUILD_VERSION=4-postmarketos-qcom-sdm845 -j2 Image.gz

release=$(make -s -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 kernelrelease)
[[ "$release" == '6.16.7-sdm845' ]] || { echo "Kernel release mismatch: $release" >&2; exit 1; }
sha256sum "$out_dir/arch/arm64/boot/Image.gz"
