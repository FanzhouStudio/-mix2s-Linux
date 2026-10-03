#!/usr/bin/env bash
# Host-only DTB variant. Does not access or flash the phone.
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src_dir="$repo_dir/src"
out_dir="$repo_dir/../out-linux728-polaris-candidate"
dts="$src_dir/arch/arm64/boot/dts/qcom/sdm845-xiaomi-polaris.dts"
patch_file="$repo_dir/diagnostics/patches/0006-linux728-polaris-xbl-framebuffer-reserve.patch"
output="$repo_dir/artifacts/linux728-polaris-candidate/sdm845-xiaomi-polaris-xbl-reserved.dtb"

[[ -f "$src_dir/Makefile" && -f "$out_dir/.config" ]]
if grep -Fq 'framebuffer@9d400000 {' "$dts"; then
  printf 'Refusing to alter an already patched source tree\n' >&2
  exit 1
fi
patch -p1 -d "$src_dir" -i "$patch_file"
restore_base_dtb() {
  patch -R -p1 -d "$src_dir" -i "$patch_file"
  make -s -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 -j4 \
    qcom/sdm845-xiaomi-polaris.dtb
}
trap restore_base_dtb EXIT
grep -Fqx $'\t\t\treg = <0 0x9d400000 0 0x02400000>;' "$dts"
make -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 -j4 \
  qcom/sdm845-xiaomi-polaris.dtb
install -m 0644 "$out_dir/arch/arm64/boot/dts/qcom/sdm845-xiaomi-polaris.dtb" "$output"
sha256sum "$output"
printf 'Phone partition writes: none\n'
