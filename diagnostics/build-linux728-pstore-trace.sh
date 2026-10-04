#!/usr/bin/env bash
# Host-only build of the proven display kernel with persistent RAM diagnostics.
# Reuses the existing object tree to avoid another multi-gigabyte build cache.
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src_dir="$repo_dir/src"
out_dir="$repo_dir/../out-linux728-polaris-candidate"
artifact_dir="$repo_dir/artifacts/linux728-polaris-candidate"
patch_map="$repo_dir/diagnostics/patches/0009-linux728-polaris-xbl-iommu-after-attach.patch"
patch_delay="$repo_dir/diagnostics/patches/0008-linux728-polaris-defer-msm-drm.patch"
patch_short="$repo_dir/diagnostics/patches/0010-linux728-polaris-drm-delay-5s.patch"
patch_xbl="$repo_dir/diagnostics/patches/0006-linux728-polaris-xbl-framebuffer-reserve.patch"
patch_pstore="$repo_dir/diagnostics/patches/0011-linux728-polaris-ramoops.patch"
variant_image="$artifact_dir/Image-xbl-iommu-pstore-trace.gz"
variant_dtb="$artifact_dir/sdm845-xiaomi-polaris-xbl-pstore.dtb"

[[ -f "$src_dir/Makefile" && -f "$out_dir/.config" ]]
available_blocks=$(stat -f -c %a "$out_dir")
block_size=$(stat -f -c %S "$out_dir")
(( available_blocks * block_size > 1610612736 )) || {
  echo 'Less than 1.5 GiB free; refusing to rebuild the kernel' >&2
  exit 1
}
patch --dry-run -p1 -d "$src_dir" -i "$patch_map"
patch --dry-run -p1 -d "$src_dir" -i "$patch_delay"

applied_map=0
applied_delay=0
applied_short=0
applied_xbl=0
applied_pstore=0
restore_sources() {
  if (( applied_pstore )); then patch -R -p1 -d "$src_dir" -i "$patch_pstore"; fi
  if (( applied_xbl )); then patch -R -p1 -d "$src_dir" -i "$patch_xbl"; fi
  if (( applied_short )); then patch -R -p1 -d "$src_dir" -i "$patch_short"; fi
  if (( applied_delay )); then patch -R -p1 -d "$src_dir" -i "$patch_delay"; fi
  if (( applied_map )); then patch -R -p1 -d "$src_dir" -i "$patch_map"; fi
  patch --dry-run -p1 -d "$src_dir" -i "$patch_map" >/dev/null
  patch --dry-run -p1 -d "$src_dir" -i "$patch_delay" >/dev/null
}
trap restore_sources EXIT

cp "$artifact_dir/kernel-lockup-trace.config" "$out_dir/.config"
"$src_dir/scripts/config" --file "$out_dir/.config" \
  --enable PSTORE \
  --enable PSTORE_RAM \
  --enable PSTORE_CONSOLE \
  --enable PSTORE_PMSG
make -s -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 olddefconfig
for symbol in ARM64_PSEUDO_NMI SOFTLOCKUP_DETECTOR HARDLOCKUP_DETECTOR \
  HARDLOCKUP_DETECTOR_PERF DETECT_HUNG_TASK PSTORE_RAM PSTORE_CONSOLE PSTORE_PMSG; do
  grep -Fqx "CONFIG_${symbol}=y" "$out_dir/.config"
done

patch -p1 -d "$src_dir" -i "$patch_map"
applied_map=1
patch -p1 -d "$src_dir" -i "$patch_delay"
applied_delay=1
patch --dry-run -p1 -d "$src_dir" -i "$patch_short"
patch -p1 -d "$src_dir" -i "$patch_short"
applied_short=1
patch -p1 -d "$src_dir" -i "$patch_xbl"
applied_xbl=1
patch --dry-run -p1 -d "$src_dir" -i "$patch_pstore"
patch -p1 -d "$src_dir" -i "$patch_pstore"
applied_pstore=1
make -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 -j4 \
  Image.gz qcom/sdm845-xiaomi-polaris.dtb
install -m 0644 "$out_dir/arch/arm64/boot/Image.gz" "$variant_image"
install -m 0644 "$out_dir/arch/arm64/boot/dts/qcom/sdm845-xiaomi-polaris.dtb" "$variant_dtb"
install -m 0644 "$out_dir/.config" "$artifact_dir/kernel-pstore-trace.config"
sha256sum "$variant_image" "$variant_dtb" "$artifact_dir/kernel-pstore-trace.config"
printf 'Phone partition writes: none\n'
