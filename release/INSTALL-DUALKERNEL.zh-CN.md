# 小米 MIX 2S（polaris）Ubuntu 26.04.1 双内核预览版安装说明

此包适用于**已解锁 Bootloader 的小米 MIX 2S，设备代号 `polaris`**。两个启动镜像共用同一个 Ubuntu ARM64 根文件系统：正常开机使用 `boot` 中的 Linux 7.2.8；音量上＋电源进入 `recovery` 中的 Linux 6.1。音量下＋电源进入 Fastboot。

**这里的“双内核”是 Ubuntu 的两个内核启动入口，不是 Android／Ubuntu 双系统。** 安装公开 rootfs 会格式化整个原 `userdata` 分区，删除原 Android 用户数据。两个内核访问同一套 Ubuntu 系统、用户文件和软件包。

## 附件与校验

| 文件 | 用途 |
| --- | --- |
| `polaris-linux-7.2.8-boot.img` | 正常开机使用的 7.2.8 Android boot 格式镜像 |
| `polaris-linux-6.1-recovery.img` | 按音量上＋电源进入的 6.1 recovery 格式镜像 |
| `polaris-ubuntu-26.04.1-dualkernel-rootfs-arm64.tar.zst` | 已清除个人数据的 Ubuntu rootfs tar 归档；不是可直接 fastboot 刷入的镜像 |
| `polaris-linux-7.2.8-running.config` | 当前运行内核从 `/proc/config.gz` 导出的配置，供源码对照；不刷入手机 |
| `SHA256SUMS-DUALKERNEL` | 上述四个文件的 SHA-256 校验值 |

把附件放在同一目录，运行 `sha256sum -c SHA256SUMS-DUALKERNEL`。刷写前确认 `fastboot getvar product` 返回 `polaris`、`fastboot getvar unlocked` 为 `yes`，并检查 `boot` 和 `recovery` 分区大小均能容纳相应镜像。不要锁回 Bootloader。

公开 rootfs 不含用户主目录内容、Wi-Fi 密码、SSH 主机密钥、1Panel 管理数据或 ChatGPT／QQ／Clash Verge。`polaris` 账户在归档中被锁定，GDM 自动登录已关闭；**首次启动前必须自行设置密码**。本包不是手机数据备份，也不包含 Android 原厂固件。

此归档由上一版已审计的公开 Ubuntu rootfs 加入当前 7.2.8 的 zram 模块及服务生成，并非本机现有 userdata 的逐文件镜像。两次直接读取现有系统都触发整机停顿；公开归档已做内容审计，但全新安装后的实际启动仍需使用者按下述临时启动步骤验证。

## 新安装：原 userdata 专用于 Ubuntu

此流程会清空 Android 的 `userdata`，并覆盖 `boot` 与 `recovery`。先在自己的设备上备份个人文件以及 `boot`、`recovery`、`userdata`、`dtbo`、`vbmeta`；确认 Fastboot 和可临时启动的恢复环境可用。保留原有 `vendor`、`modem`、`dsp` 等固件分区，不要擦除。

准备主机上的 Android Platform Tools、`zstd`，以及一个能以 root 运行 `adb shell`、`mke2fs`、`mount`、`tar`、`chroot` 的 ARM64 恢复环境。可从 [TWRP 官方 polaris 下载页](https://dl.twrp.me/polaris/)获取恢复镜像，用 `fastboot boot` 临时启动；本 Release 不分发 TWRP。恢复环境中的块设备编号可能不同，以下使用 GPT 分区名称，操作前必须确认其指向。

1. 进入 Fastboot，核对设备与镜像：

   ```sh
   sha256sum -c SHA256SUMS-DUALKERNEL
   fastboot getvar product
   fastboot getvar unlocked
   fastboot getvar partition-size:boot
   fastboot getvar partition-size:recovery
   ```

2. 临时启动恢复环境，通过 `adb shell` 确认 `userdata`。**只有备份完成并确认目标正确后**，卸载 `/data` 并格式化：

   ```sh
   adb shell 'readlink -f /dev/block/by-name/userdata'
   adb shell 'umount /data 2>/dev/null || true; mke2fs -t ext4 -F -L POLARIS_UBUNTU /dev/block/by-name/userdata'
   adb shell 'mkdir -p /mnt/ubuntu && mount -t ext4 /dev/block/by-name/userdata /mnt/ubuntu'
   ```

3. 从主机解压公开 rootfs。恢复环境的 tar 必须支持 PAX 格式并保留数字 UID/GID、权限和符号链接；用 `bash` 执行以便 `pipefail` 捕捉传输错误：

   ```sh
   set -o pipefail
   zstd -dc polaris-ubuntu-26.04.1-dualkernel-rootfs-arm64.tar.zst | adb shell -T 'tar -xpf - -C /mnt/ubuntu'
   adb shell 'test -x /mnt/ubuntu/usr/lib/systemd/systemd && test -f /mnt/ubuntu/etc/polaris-ubuntu-rootfs && echo ROOTFS_OK'
   ```

   只有管道成功结束并显示 `ROOTFS_OK` 才继续。**不要对 tar 包执行 `fastboot flash userdata`**；本项目曾遇到 Bootloader 对大 userdata 镜像只写入前段的问题。

4. 设置本机账户密码，卸载根分区：

   ```sh
   adb shell 'mount --bind /dev /mnt/ubuntu/dev; mount -t proc proc /mnt/ubuntu/proc'
   adb shell -t 'chroot /mnt/ubuntu /usr/bin/passwd polaris'
   adb shell 'umount /mnt/ubuntu/proc; umount /mnt/ubuntu/dev; sync; umount /mnt/ubuntu'
   ```

   密码由你在终端输入，不要写进命令行或 Release 评论。首次解锁若屏幕键盘未出现，请备好 USB 键盘。

5. 回到 Fastboot，先分别从内存试启动两个附件：

   ```sh
   fastboot boot polaris-linux-6.1-recovery.img
   # 返回 Fastboot 后：
   fastboot boot polaris-linux-7.2.8-boot.img
   ```

   检查版本、桌面、触摸及 `/` 是否为 `userdata` 上的 ext4。临时启动不写分区；每次测试后重新进入 Fastboot。若任何一次失败，保留当前分区，先收集日志。

6. 两次临时启动都成功后，先安装并验证 6.1 回退入口，再安装 7.2.8：

   ```sh
   fastboot flash recovery polaris-linux-6.1-recovery.img
   fastboot reboot recovery
   # 确认 6.1 Ubuntu 桌面可用，再返回 Fastboot：
   fastboot flash boot polaris-linux-7.2.8-boot.img
   fastboot reboot
   ```

   正常开机应进入 7.2.8；音量上＋电源应进入 6.1；音量下＋电源进入 Fastboot。首次启动后重新配置 Wi-Fi、时区等个人设置。

## 已有 Ubuntu userdata 的设备

如果已经在原 `userdata` 安装了本项目的 Ubuntu，并且 6.1 recovery 正常工作，**不要重新格式化 userdata 或解压公开 rootfs 覆盖自己的系统**。先备份现有 `boot`、`recovery` 和数据；从 Fastboot 用 `fastboot boot polaris-linux-7.2.8-boot.img` 临时验证共享 rootfs、桌面、触摸和 USB。只有验证通过，再考虑 `fastboot flash boot polaris-linux-7.2.8-boot.img`。旧 rootfs 未必具有新版附加模块或服务；临时启动成功也不能证明长期稳定。

旧恢复环境可能无法以读写方式挂载本项目较新的 ext4 userdata；遇到挂载失败时不要反复格式化现有分区。上述格式化命令仅用于全新安装。

## 双内核的实际价值与限制

| 启动入口 | 已确认 | 尚缺／仍需验证 |
| --- | --- | --- |
| `boot`：7.2.8 | 正常启动 GNOME、触摸；临时测试中曾观察到 GPU、Wi-Fi 与扬声器工作；正式启动后 zram 自动启用 | 持续读盘和部分大型应用仍可触发 RCU 卡死；固件功能未在本次刷入后全部复测 |
| `recovery`：6.1 | 刷入 7.2.8 后仍能用音量上＋电源进入 GNOME；此前验证了触摸、Wi-Fi、扬声器与蜂窝数据 | 也发生过大型应用或 I/O 卡死；相机、通话音频等仍不完整或未验证 |

- 7.2.8 是较新的主启动内核，当前设备已验证正常开机到 GNOME、触摸可用；6.1 放在 recovery，便于在 7.2.8 启动失败时进入 Ubuntu 做诊断和回退。
- 两个内核共用软件和个人文件，调试同一应用时不必复制两套 rootfs；也能在相同用户空间比较驱动表现。
- **它们不是两套独立系统。** userdata 损坏、错误的软件包升级或共享配置损坏可能同时影响两边。占用 recovery 也会替换原 Android 恢复环境。
- 7.2.8 与 6.1 均曾在大型应用、浏览器或高负载场景出现整机 RCU 停顿。此版是预览版，不能称为稳定日用。6.1 recovery 是回退内核，不保证能修复共享系统的问题。
- Wi-Fi、GPU、音频、蜂窝等依赖设备固件与内核模块；不同 ROM 固件组合尚未验证。相机、通话音频、短信、蓝牙配对等仍不完整或未经验证。
- Ubuntu 的普通 `apt` 更新不能替代适配过的手机内核、设备树和启动 ramdisk；升级前保留可启动镜像与数据备份。

## 不能与 Android 共存的原因与回退

当前 initramfs 按原 `userdata` 分区寻找 Ubuntu ext4。Android 也需要该分区，通常还涉及加密；仅把两个 Linux 内核分别放进 `boot` 和 `recovery`，**不会**保留一个可正常使用的 Android 系统。此 Release 不提供 Android／Ubuntu 共存刷写方案。

若 7.2.8 正常启动失败，使用音量上＋电源尝试 6.1；若 6.1 也不能启动，进入 Fastboot，用自己保存的原始分区备份恢复启动镜像，或临时 `fastboot boot` 诊断镜像。恢复原 Android 的 `boot`／`recovery` **不会恢复已经格式化的 Android userdata**；Android 数据必须依靠你自己的备份或可靠的原厂恢复流程。
