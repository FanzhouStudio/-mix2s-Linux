#!/usr/bin/env bash
# Host-only display IOMMU handoff diagnostic. Never writes to the phone.
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src_dir="$repo_dir/src"
out_dir="$repo_dir/../out-linux728-polaris-candidate"
patch_file="$repo_dir/diagnostics/patches/0007-linux728-polaris-xbl-display-iommu-map.patch"
base_image="$repo_dir/artifacts/linux728-polaris-candidate/Image.gz"
variant_image="$repo_dir/artifacts/linux728-polaris-candidate/Image-xbl-iommu.gz"

[[ -f "$src_dir/Makefile" && -f "$out_dir/.config" && -f "$base_image" ]]
base_digest=$(sha256sum "$base_image" | cut -d ' ' -f 1)
[[ "$base_digest" == '1be5e1f71353485e8df8a574f6c26a3bd541df33231a98e02c973dc6837a9b48' ]]
patch --dry-run -p1 -d "$src_dir" -i "$patch_file"
patch -p1 -d "$src_dir" -i "$patch_file"
restore_base_kernel() {
  patch -R -p1 -d "$src_dir" -i "$patch_file"
  make -s -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 -j4 Image.gz
  # The rebuilt Image embeds a fresh build timestamp, so compare the
  # restored source to the upstream tarball instead of comparing Image hashes.
  tar -xOf "$repo_dir/downloads/linux-7.2.8.tar.xz" \
    linux-7.2.8/drivers/gpu/drm/msm/msm_iommu.c | \
    cmp - "$src_dir/drivers/gpu/drm/msm/msm_iommu.c"
}
trap restore_base_kernel EXIT

make -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 -j4 Image.gz
install -m 0644 "$out_dir/arch/arm64/boot/Image.gz" "$variant_image"
sha256sum "$variant_image"
printf 'Phone partition writes: none\n'
