# Xiaomi MIX 2S（polaris）Ubuntu 26.04.1 预览版安装说明

本发布包适用于 **Xiaomi MIX 2S，设备代号 `polaris`，ARM64，已解锁 Bootloader**。内核为已在本机启动的 `6.1-sdm845`，启动镜像放在 `recovery` 分区；Ubuntu 根文件系统放在原 `userdata` 分区。请先读完本页，再操作分区。

## 发布文件

- `polaris-ubuntu-26.04.1-kernel-6.1-audio-recovery.img`：当前已验证可启动 GNOME、触摸和扬声器的 Android recovery 格式镜像。它不是 7.x 内核。
- `polaris-ubuntu-26.04.1-rootfs-arm64.tar.zst`：从当前系统导出的公开版 Ubuntu 26.04.1 ARM64 根文件系统。个人文件、网络密码、账号密钥、日志、QQ、ChatGPT、Clash Verge 和 1Panel 安装数据已排除。它不是整机备份，也不是可直接刷入的 ext4 镜像。
- `SHA256SUMS`：下载后校验两个文件。

公开版没有默认登录密码。**在首次启动前，必须在恢复环境中给 `polaris` 设置自己的密码。** GNOME 自动登录已关闭，sudo 需要该密码。首次登录时如屏幕键盘没有出现，请准备 USB 键盘。

## 已知风险与备份

当前 6.1 内核仍会在 QQ、ChatGPT、Clash Verge、Firefox 视频和部分高 I/O 操作中发生整机 RCU 卡死。本发布版是适配预览，不适合作为可靠日常主机。Wi-Fi、GNOME 触摸、屏幕键盘、扬声器和中国电信数据连接已在原设备上运行；其他设备个体、冷启动次数、通话音频、相机和蓝牙配对未验证。

安装步骤会**格式化整个 `userdata` 分区，清除 Android 应用及文件**。`boot` 分区不会写入，但 Android 的数据分区不再存在，不能据此认为 Android 仍可正常启动。刷写 `recovery` 会覆盖原恢复环境。先在自己设备上备份 `userdata`、`recovery`、`boot`、`dtbo` 和 `vbmeta`，并确认有可用的恢复方法；本发布包不包含你手机原有的 Android 数据或 OEM 分区。

在开发机当前启动中，`userdata` 的 GPT 名称对应 `/dev/sda21`，`recovery` 对应 `/dev/sda19`，但安装说明使用分区名称而非固定 `/dev/sda*` 编号，避免不同环境映射变化。

运行时仍需手机现有的 `modem`、`vendor` 和 `dsp` 固件分区。不要擦除这些分区，也不要锁回 Bootloader。

## 安装选项 A：原 `userdata` 专用于 Ubuntu

这是当前手机上已验证的分区布局。需要一个能运行 `adb shell`、`mke2fs`（或 `mkfs.ext4`）、`mount`、`tar`、`chroot` 的 ARM64 恢复环境，以及主机上的 Android Platform Tools 和 `zstd`。可以从 [TWRP 官方 polaris 下载页](https://dl.twrp.me/polaris/)取得恢复镜像，先通过 `fastboot boot` 临时启动；本项目不重新分发 TWRP。不同恢复环境的块设备别名可能不同；**先确认 `userdata` 指向正确分区**。TWRP 的旧内核可只读查看本机现有 Ubuntu ext4，但因较新的 ext4 特性无法将其挂为可写；以下格式化命令仅用于全新安装，不适用于修复现有分区。

1. 在主机校验下载文件：

   ```sh
   sha256sum -c SHA256SUMS
   fastboot getvar product
   fastboot getvar unlocked
   fastboot getvar partition-size:recovery
   ```

   `product` 必须为 `polaris`。如果不能确认设备身份和解锁状态，停止安装。

2. 从能提供 root `adb shell` 的恢复环境启动。检查并备份原分区后，卸载 Android 的 `/data`，再格式化原 `userdata`。下列命令是**清空用户数据**的步骤：

   ```sh
   adb shell 'readlink -f /dev/block/by-name/userdata'
   adb shell 'umount /data 2>/dev/null || true; mke2fs -t ext4 -F -L POLARIS_UBUNTU /dev/block/by-name/userdata'
   adb shell 'mkdir -p /mnt/ubuntu && mount -t ext4 /dev/block/by-name/userdata /mnt/ubuntu'
   ```

3. 从主机以二进制流解压到手机。恢复环境的 `tar` 必须能读取 POSIX PAX tar，并以 root 身份保留归档中的数字 UID/GID 和权限：

   ```sh
   set -o pipefail
   zstd -dc polaris-ubuntu-26.04.1-rootfs-arm64.tar.zst | adb shell -T 'tar -xpf - -C /mnt/ubuntu'
   adb shell 'test -x /mnt/ubuntu/usr/lib/systemd/systemd && test -f /mnt/ubuntu/etc/polaris-ubuntu-rootfs && echo ROOTFS_OK'
   ```

   只有管道返回成功、且出现 `ROOTFS_OK` 才继续。**不要用 `fastboot flash userdata` 刷这个 tar 包**；本机的 Bootloader 曾对较大的 sparse userdata 镜像只写入前段，造成根文件系统不完整。

4. 在恢复环境中设置本机账户密码。`passwd` 会在终端交互输入，不要把密码写进命令行或 Release 评论：

   ```sh
   adb shell 'mount --bind /dev /mnt/ubuntu/dev; mount -t proc proc /mnt/ubuntu/proc'
   adb shell -t 'chroot /mnt/ubuntu /usr/bin/passwd polaris'
   adb shell 'umount /mnt/ubuntu/proc; umount /mnt/ubuntu/dev; sync; umount /mnt/ubuntu'
   ```

5. 回到 Fastboot 后，可选两种启动方式：

   - **临时验证**：`fastboot boot polaris-ubuntu-26.04.1-kernel-6.1-audio-recovery.img`。不写入 `recovery`，重启后失效。
   - **安装到 recovery**：`fastboot flash recovery polaris-ubuntu-26.04.1-kernel-6.1-audio-recovery.img`，然后 `fastboot reboot recovery`。之后通常用音量上＋电源进入 Ubuntu；音量下＋电源进入 Fastboot。

首次启动后在 GNOME 中自行连接 Wi-Fi，并检查时区、电池和音频。系统更新前先备份；不要把普通 Ubuntu 内核包当作这台手机的可启动内核。

## 选项 B：与 Android 共存

**本发布包目前不支持可切换的 Android／Ubuntu 双系统。** 只保留 Android `boot` 分区不够：本版 initramfs 按 GPT 名称查找 `userdata` 并要求它是 Ubuntu ext4 根分区；Android 也需要自己的 `userdata`，通常还涉及加密和数据初始化。当前手机的原 Android `userdata` 已被 Ubuntu 替换。

理论上的共存方案需要先为 Ubuntu 准备独立 ext4 分区，再修改并验证 initramfs，让它按明确的 PARTUUID 挂载该分区，同时保留可启动的 Android `userdata`、`boot` 和固件分区。**这些分区变更及对应启动镜像尚未实现或验证，本 Release 不提供共存刷写命令。** 如果双系统是必须条件，请不要执行选项 A。

另一条研究路线是参照 [Kali NetHunter Pro 的 rootfs 镜像 loop 挂载实现](https://gitlab.com/kalilinux/nethunter/build-scripts/kali-nethunter-pro/-/tree/main/devices/qcom/initramfs-tools/scripts/init-premount)，从 Android 可访问的存储加载 Ubuntu 镜像；但当前 initramfs 没有这段逻辑，Android 数据加密方式也需先确认。这同样是后续适配工作，不是本版安装选项。

## 回退

临时 `fastboot boot` 只需重启。已经刷入 `recovery` 时，可用你自己的恢复镜像备份刷回 `recovery`。**这不会恢复已格式化的 Android `userdata`**；要回 Android，仍需恢复你的 Android 数据备份或按可信的原厂恢复流程重新安装。出现启动文字但无法进入桌面时，不要反复格式化；先从 Fastboot 临时启动诊断环境读取日志。
