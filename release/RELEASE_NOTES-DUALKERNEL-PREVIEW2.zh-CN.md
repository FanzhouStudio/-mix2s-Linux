# Polaris Ubuntu 26.04.1 双内核预览版补丁 2

适用于小米 MIX 2S（`polaris`）。本次仅更新 Linux 7.2.8 的 `boot` 镜像。Linux 6.1 的 `recovery` 和 Ubuntu 26.04.1 ARM64 rootfs 沿用 [预览版 1](https://github.com/FanzhouStudio/-mix2s-Linux/releases/tag/v0.2.0-preview.1) 的附件；下载这些旧附件时仍需按其 SHA-256 校验。两种内核共用一个 Ubuntu `userdata`，不是 Android／Ubuntu 双系统。

## 修复与设备验证

- 修正 initramfs 在切换到持久 Ubuntu 前无限等待 USB 诊断 shell 的问题。之前有一次已挂载 rootfs，却约 75 分钟后才进入 GNOME。
- 默认使用较安全的硬件启动路径：启动固件服务和音频 DSP，跳过曾使多个任务陷入不可中断等待的强制 Wi-Fi 驱动重绑，也不主动启动蜂窝基带。因而 **7.2.8 下 Wi-Fi 和蜂窝网络可能不可用**。
- 在原设备上用 `fastboot boot` 临时验证，再刷入 `boot`。正常重启后，7.2.8 在约 15 秒完成 initramfs 挂载与交接，随后进入 GNOME；用户确认桌面和触摸正常。测试期间未见 D 状态任务。`recovery` 和 `userdata` 没有因本补丁被刷写。

**仍是实验版。** 两种内核均有大型应用、浏览器或大量 I/O 下整机卡死的历史；本补丁修复的是启动等待和一条已观察到的驱动阻塞路径，不能证明长期稳定。6.1 在进入桌面后自行关机／重启的报告仍在排查。公开 rootfs 是基于已审计旧快照构建的脱敏归档，**不是当前手机 userdata 的逐文件备份**，新设备上的组合启动尚未验证。不要把 6.1 recovery 当作独立备份：两个内核共用同一分区。

## 已安装双内核系统的更新步骤

先备份自己的数据和现有 `boot` 镜像。将本 Release 的 `polaris-linux-7.2.8-boot.img` 与 `SHA256SUMS-PREVIEW2` 放在同一目录，核对：

```sh
sha256sum -c SHA256SUMS-PREVIEW2
fastboot getvar product
fastboot getvar unlocked
fastboot getvar partition-size:boot
```

只对已解锁且 `product` 为 `polaris` 的设备操作，`boot` 容量须大于镜像大小。先从内存验证桌面、触摸和 rootfs，再回 Fastboot 刷写：

```sh
fastboot boot polaris-linux-7.2.8-boot.img
# 验证完成并重新进入 Fastboot 后
fastboot flash boot polaris-linux-7.2.8-boot.img
fastboot reboot
```

**不要格式化已有 Ubuntu 的 `userdata`，也不要把 rootfs tar 包传给 `fastboot flash userdata`。** 正常开机进入 7.2.8；音量上＋电源进入 6.1 recovery；音量下＋电源进入 Fastboot。保留 6.1 镜像和设备的原始分区备份，以便失败时恢复。全新安装请阅读 [双内核安装说明](https://github.com/FanzhouStudio/-mix2s-Linux/blob/main/release/INSTALL-DUALKERNEL.zh-CN.md)，并使用预览版 1 的 recovery/rootfs 附件；该全新组合尚未在第二台设备上验证。
