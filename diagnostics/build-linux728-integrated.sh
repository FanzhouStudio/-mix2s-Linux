#!/usr/bin/env bash
# Rebuild the proven 7.2.8 display kernel with Polaris audio and late-load
# Wi-Fi/modem support. Build artifacts only; this never touches phone storage.
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src_dir="$repo_dir/src"
out_dir="$repo_dir/../out-linux728-polaris-candidate"
artifact_dir="$repo_dir/artifacts/linux728-polaris-candidate"
module_dir="$artifact_dir/modules-integrated"
patch_map="$repo_dir/diagnostics/patches/0009-linux728-polaris-xbl-iommu-after-attach.patch"
patch_delay="$repo_dir/diagnostics/patches/0008-linux728-polaris-defer-msm-drm.patch"
patch_short="$repo_dir/diagnostics/patches/0010-linux728-polaris-drm-delay-5s.patch"
patch_xbl="$repo_dir/diagnostics/patches/0006-linux728-polaris-xbl-framebuffer-reserve.patch"
patch_audio="$repo_dir/diagnostics/patches/0012-linux728-polaris-audio-dt.patch"
patch_tas="$repo_dir/diagnostics/patches/0013-linux728-tas2559-kbuild.patch"
patch_peripherals="$repo_dir/diagnostics/patches/0014-linux728-polaris-adsp-wifi-quirk.patch"

[[ -f "$src_dir/Makefile" && -f "$out_dir/.config" ]]
available_blocks=$(stat -f -c %a "$out_dir")
block_size=$(stat -f -c %S "$out_dir")
(( available_blocks * block_size > 1610612736 )) || {
  echo 'Less than 1.5 GiB free; refusing to rebuild the kernel' >&2
  exit 1
}
patch --dry-run -p1 -d "$src_dir" -i "$patch_map" >/dev/null
patch --dry-run -p1 -d "$src_dir" -i "$patch_tas" >/dev/null
[[ ! -e "$src_dir/sound/soc/codecs/tas2559.c" && ! -e "$src_dir/sound/soc/codecs/tas2559.h" ]]

applied=()
restore_sources() {
  local i
  for ((i=${#applied[@]}-1; i>=0; i--)); do
    patch -R -p1 -d "$src_dir" -i "${applied[i]}"
  done
  rm -f "$src_dir/sound/soc/codecs/tas2559.c" "$src_dir/sound/soc/codecs/tas2559.h"
  patch --dry-run -p1 -d "$src_dir" -i "$patch_map" >/dev/null
  patch --dry-run -p1 -d "$src_dir" -i "$patch_tas" >/dev/null
}
trap restore_sources EXIT

cp "$repo_dir/diagnostics/ports/tas2559/tas2559.c" "$src_dir/sound/soc/codecs/tas2559.c"
cp "$repo_dir/diagnostics/ports/tas2559/tas2559.h" "$src_dir/sound/soc/codecs/tas2559.h"
for p in "$patch_tas" "$patch_map" "$patch_delay" "$patch_short" "$patch_xbl" "$patch_audio" "$patch_peripherals"; do
  patch --dry-run -p1 -d "$src_dir" -i "$p" >/dev/null
  patch -p1 -d "$src_dir" -i "$p"
  applied+=("$p")
done

cp "$artifact_dir/kernel-lockup-trace.config" "$out_dir/.config"
"$src_dir/scripts/config" --file "$out_dir/.config" \
  --enable SOUND --enable SND --enable SND_SOC --enable SND_SOC_QCOM \
  --enable QUOTA --enable QFMT_V2 \
  --enable QCOM_APR --enable QCOM_PD_MAPPER \
  --enable SLIMBUS --enable SLIM_QCOM_NGD_CTRL \
  --enable SOUNDWIRE --enable SOUNDWIRE_QCOM \
  --enable MFD_WCD934X --enable SND_SOC_WCD934X \
  --enable SND_SOC_SDM845 \
  --module SND_SOC_TAS2559 \
  --module RESET_QCOM_PDC --module QCOM_RMTFS_MEM --module QCOM_IPA
make -s -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 olddefconfig
for symbol in QUOTA QFMT_V2 SOUND SND SND_SOC SND_SOC_QCOM QCOM_APR QCOM_PD_MAPPER \
  SLIMBUS SLIM_QCOM_NGD_CTRL SOUNDWIRE SOUNDWIRE_QCOM \
  MFD_WCD934X SND_SOC_WCD934X SND_SOC_SDM845; do
  grep -Fqx "CONFIG_${symbol}=y" "$out_dir/.config" || {
    echo "Required integrated driver did not become built-in: $symbol" >&2
    exit 1
  }
done
for symbol in SND_SOC_TAS2559 RESET_QCOM_PDC QCOM_RMTFS_MEM QCOM_IPA RMNET OVERLAY_FS; do
  grep -Fqx "CONFIG_${symbol}=m" "$out_dir/.config" || {
    echo "Required late module missing: $symbol" >&2
    exit 1
  }
done

make -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 -j4 \
  Image.gz qcom/sdm845-xiaomi-polaris.dtb \
  drivers/reset/reset-qcom-pdc.ko \
  drivers/soc/qcom/rmtfs_mem.ko \
  drivers/net/ipa/ipa.ko \
  drivers/net/ethernet/qualcomm/rmnet/rmnet.ko \
  sound/soc/codecs/snd-soc-tas2559.ko \
  fs/overlayfs/overlay.ko

install -d -m 0755 "$module_dir"
install -m 0644 "$out_dir/arch/arm64/boot/Image.gz" "$artifact_dir/Image-xbl-iommu-integrated.gz"
install -m 0644 "$out_dir/arch/arm64/boot/dts/qcom/sdm845-xiaomi-polaris.dtb" "$artifact_dir/sdm845-xiaomi-polaris-integrated.dtb"
install -m 0644 "$out_dir/.config" "$artifact_dir/kernel-integrated.config"
for module in \
  drivers/reset/reset-qcom-pdc.ko \
  drivers/soc/qcom/rmtfs_mem.ko \
  drivers/net/ipa/ipa.ko \
  drivers/net/ethernet/qualcomm/rmnet/rmnet.ko \
  sound/soc/codecs/snd-soc-tas2559.ko \
  fs/overlayfs/overlay.ko; do
  install -m 0644 "$out_dir/$module" "$module_dir/${module##*/}"
done
sha256sum "$artifact_dir/Image-xbl-iommu-integrated.gz" \
  "$artifact_dir/sdm845-xiaomi-polaris-integrated.dtb" \
  "$artifact_dir/kernel-integrated.config" "$module_dir"/*.ko
printf 'Phone partition writes: none\n'
