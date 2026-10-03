#!/usr/bin/env bash
# Host-only kernel build: defer MSM DRM so USB ACM can log display probe.
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src_dir="$repo_dir/src"
out_dir="$repo_dir/../out-linux728-polaris-candidate"
patch_map="$repo_dir/diagnostics/patches/0007-linux728-polaris-xbl-display-iommu-map.patch"
patch_delay="$repo_dir/diagnostics/patches/0008-linux728-polaris-defer-msm-drm.patch"
variant_image="$repo_dir/artifacts/linux728-polaris-candidate/Image-xbl-iommu-serial-first.gz"

[[ -f "$src_dir/Makefile" && -f "$out_dir/.config" ]]
patch --dry-run -p1 -d "$src_dir" -i "$patch_map"
patch --dry-run -p1 -d "$src_dir" -i "$patch_delay"
applied_map=0
applied_delay=0
restore_sources() {
  if (( applied_delay )); then
    patch -R -p1 -d "$src_dir" -i "$patch_delay"
  fi
  if (( applied_map )); then
    patch -R -p1 -d "$src_dir" -i "$patch_map"
  fi
  patch --dry-run -p1 -d "$src_dir" -i "$patch_delay" >/dev/null
  patch --dry-run -p1 -d "$src_dir" -i "$patch_map" >/dev/null
  tar -xOf "$repo_dir/downloads/linux-7.2.8.tar.xz" \
    linux-7.2.8/drivers/gpu/drm/msm/msm_iommu.c | \
    cmp - "$src_dir/drivers/gpu/drm/msm/msm_iommu.c"
  tar -xOf "$repo_dir/downloads/linux-7.2.8.tar.xz" \
    linux-7.2.8/drivers/gpu/drm/msm/msm_drv.c | \
    cmp - "$src_dir/drivers/gpu/drm/msm/msm_drv.c"
  if (( applied_map || applied_delay )); then
    make -s -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 -j4 Image.gz
  fi
}
trap restore_sources EXIT

patch -p1 -d "$src_dir" -i "$patch_map"
applied_map=1
patch -p1 -d "$src_dir" -i "$patch_delay"
applied_delay=1
make -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 -j4 Image.gz
install -m 0644 "$out_dir/arch/arm64/boot/Image.gz" "$variant_image"
sha256sum "$variant_image"
printf 'Phone partition writes: none\n'
