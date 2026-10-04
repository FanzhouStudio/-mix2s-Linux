#!/usr/bin/env bash
# Host-only 7.2.8 display handoff diagnostic; no phone partition writes.
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src_dir="$repo_dir/src"
out_dir="$repo_dir/../out-linux728-polaris-candidate"
patch_map="$repo_dir/diagnostics/patches/0009-linux728-polaris-xbl-iommu-after-attach.patch"
patch_delay="$repo_dir/diagnostics/patches/0008-linux728-polaris-defer-msm-drm.patch"
patch_short="$repo_dir/diagnostics/patches/0010-linux728-polaris-drm-delay-5s.patch"
variant_image="$repo_dir/artifacts/linux728-polaris-candidate/Image-xbl-iommu-after-attach.gz"

[[ -f "$src_dir/Makefile" && -f "$out_dir/.config" ]]
patch --dry-run -p1 -d "$src_dir" -i "$patch_map"
patch --dry-run -p1 -d "$src_dir" -i "$patch_delay"
applied_map=0
applied_delay=0
applied_short=0
restore_sources() {
  if (( applied_short )); then
    patch -R -p1 -d "$src_dir" -i "$patch_short"
  fi
  if (( applied_delay )); then
    patch -R -p1 -d "$src_dir" -i "$patch_delay"
  fi
  if (( applied_map )); then
    patch -R -p1 -d "$src_dir" -i "$patch_map"
  fi
  patch --dry-run -p1 -d "$src_dir" -i "$patch_delay" >/dev/null
  patch --dry-run -p1 -d "$src_dir" -i "$patch_map" >/dev/null
  if (( applied_map || applied_delay || applied_short )); then
    make -s -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 -j4 Image.gz
  fi
}
trap restore_sources EXIT

patch -p1 -d "$src_dir" -i "$patch_map"
applied_map=1
patch -p1 -d "$src_dir" -i "$patch_delay"
applied_delay=1
patch --dry-run -p1 -d "$src_dir" -i "$patch_short"
patch -p1 -d "$src_dir" -i "$patch_short"
applied_short=1
make -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 -j4 Image.gz
install -m 0644 "$out_dir/arch/arm64/boot/Image.gz" "$variant_image"
sha256sum "$variant_image"
printf 'Phone partition writes: none\n'
