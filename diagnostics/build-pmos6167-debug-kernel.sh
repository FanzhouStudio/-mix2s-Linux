#!/usr/bin/env bash
# Build a host-only SDM845 diagnostic kernel with CPU-stall tracing support.
# Packaging and RAM-only booting are separate steps; never flash this output.
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src_dir="$repo_dir/../linux-sdm845-6.16.7-r0"
out_dir="$repo_dir/../out-pmos6167-rcu-debug"
source_tar="$repo_dir/downloads/linux-sdm845-6.16.7-r0.tar.gz"
base_config="$repo_dir/artifacts/pmos6167/kernel.config"
config_tool="$src_dir/scripts/config"

printf '%s  %s\n' \
  '803d2cf85b248c3da41a9c9178d69d211eccf5d1adb72acd5343e09cbb65782f727e579939287c91712c69a862bed7344a0e2bc893c2791a971b6fed95ec6f1a' \
  "$source_tar" | sha512sum -c -
printf '%s  %s\n' \
  'cca4392d651fbc95ebee97f4d890e72c982a27241c254cba88b8ea159427239f' \
  "$base_config" | sha256sum -c -

if [[ $(grep -Fxc $'\tpinfo->base.prepare_prev_first = true;' \
  "$src_dir/drivers/gpu/drm/panel/panel-novatek-nt35596s.c") != 1 ]]; then
  echo 'Verified Polaris panel fix is absent or duplicated' >&2
  exit 1
fi

mkdir -p "$out_dir"
cp "$base_config" "$out_dir/.config"
"$config_tool" --file "$out_dir/.config" \
  --enable ARM64_PSEUDO_NMI \
  --enable IRQSOFF_TRACER \
  --enable PREEMPT_TRACER
make -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 \
  KBUILD_BUILD_VERSION=4-postmarketos-qcom-sdm845 olddefconfig
for symbol in ARM64_PSEUDO_NMI IRQSOFF_TRACER PREEMPT_TRACER; do
  if ! grep -Fqx "CONFIG_${symbol}=y" "$out_dir/.config"; then
    echo "Requested $symbol was not enabled" >&2
    exit 1
  fi
done
make -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 \
  KBUILD_BUILD_VERSION=4-postmarketos-qcom-sdm845 -j2 Image.gz

release=$(make -s -C "$src_dir" O="$out_dir" ARCH=arm64 LLVM=1 kernelrelease)
if [[ "$release" != '6.16.7-sdm845' ]]; then
  echo "Kernel release mismatch: $release" >&2
  exit 1
fi
printf 'Diagnostic kernel: %s\nRelease: %s\nSHA256: ' \
  "$out_dir/arch/arm64/boot/Image.gz" "$release"
sha256sum "$out_dir/arch/arm64/boot/Image.gz"
printf '%s\n' 'Phone partition writes: none'
