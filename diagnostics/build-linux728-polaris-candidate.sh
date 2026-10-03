#!/usr/bin/env bash
# Host-only kernel build. This script does not access or flash the phone.
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src_dir="$repo_dir/src"
out_dir="$repo_dir/../out-linux728-polaris-candidate"
config_tool="$src_dir/scripts/config"

printf '%s  %s\n' \
  '12e8d5a973d1ad7c5a5c69882e4022b131ed715db7003fdcd760ddf8c3e51941' \
  "$repo_dir/downloads/linux-7.2.8.tar.xz" | sha256sum -c -
printf '%s  %s\n' \
  '136241a63d8b00e705c9a38132707cac299e2aa068d0be64abe5d889ba0abcce' \
  "$repo_dir/diagnostics/patches/0000-linux728-nt35596s-v4.patch" | sha256sum -c -

if [[ ! -f "$src_dir/Makefile" ]]; then
  mkdir -p "$src_dir"
  tar -xJf "$repo_dir/downloads/linux-7.2.8.tar.xz" \
    --strip-components=1 -C "$src_dir"
  patch -p1 -d "$src_dir" \
    -i "$repo_dir/diagnostics/patches/0000-linux728-nt35596s-v4.patch"
  patch -p1 -d "$src_dir" \
    -i "$repo_dir/diagnostics/patches/0003-linux728-polaris-panel-order.patch"
  patch -p1 -d "$src_dir" \
    -i "$repo_dir/diagnostics/patches/0004-linux728-polaris-firmware-paths.patch"
fi

[[ $(sed -n '2p' "$src_dir/Makefile") == 'VERSION = 7' ]]
[[ $(sed -n '3p' "$src_dir/Makefile") == 'PATCHLEVEL = 2' ]]
[[ $(sed -n '4p' "$src_dir/Makefile") == 'SUBLEVEL = 8' ]]
panel_source="$src_dir/drivers/gpu/drm/panel/panel-novatek-nt36672a.c"
grep -Fqx $'\t.prepare_prev_first = true,' "$panel_source"
grep -Fqx $'\tpinfo->base.prepare_prev_first = desc->prepare_prev_first;' "$panel_source"
grep -Fqx $'\tfirmware-name = "qcom/sdm845/polaris/cdsp.mbn";' \
  "$src_dir/arch/arm64/boot/dts/qcom/sdm845-xiaomi-polaris.dts"

mkdir -p "$out_dir"
cp "$repo_dir/artifacts/kernel.config" "$out_dir/.config"
"$config_tool" --file "$out_dir/.config" \
  --set-str LOCALVERSION '-polaris' \
  --disable LOCALVERSION_AUTO \
  --enable SCSI_UFS_QCOM \
  --enable PHY_QCOM_QMP \
  --enable PHY_QCOM_QMP_UFS

make -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 olddefconfig
for symbol in SCSI_UFS_QCOM PHY_QCOM_QMP_UFS DRM_MSM USB_CONFIGFS_ACM; do
  grep -Fqx "CONFIG_${symbol}=y" "$out_dir/.config"
done
make -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 -j4 \
  Image.gz qcom/sdm845-xiaomi-polaris.dtb

release=$(make -s -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 kernelrelease)
[[ "$release" == '7.2.8-polaris' ]]
sha256sum \
  "$out_dir/arch/arm64/boot/Image.gz" \
  "$out_dir/arch/arm64/boot/dts/qcom/sdm845-xiaomi-polaris.dtb"
printf 'Kernel release: %s\nPhone partition writes: none\n' "$release"
