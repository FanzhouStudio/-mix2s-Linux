# Polaris Ubuntu 26.04.1 / Linux 6.1 预览版

这是小米 MIX 2S (`polaris`) 当前可启动配置的公开快照：`6.1-sdm845` recovery 镜像，以及去除个人资料和私人应用后的 Ubuntu 26.04.1 ARM64 rootfs。发布为 **Pre-release**。

发布的 recovery 镜像前 19,853,312 字节与当前手机 `PARTNAME=recovery` 分区的对应内容 SHA-256 一致。公开 rootfs 是根据当前系统整理的无个人凭据版本，因此不是逐字节备份；**公开版清理后的首次安装流程尚未在另一台设备上验证**。

已在原设备上确认：GNOME 桌面、触摸和屏幕键盘、2.4 GHz Wi-Fi、蓝牙控制器识别、内置扬声器、充电状态和中国电信蜂窝数据。部分服务仍依赖现有 Android `modem`、`vendor`、`dsp` 固件分区。

**重要限制：**此内核在 QQ、ChatGPT、Clash Verge 和部分浏览器／高 I/O 场景下可能整机卡死，日志捕获到 RCU CPU 停顿；目前没有可靠修复。麦克风、通话音频、短信、相机、蓝牙配对和长期稳定性未验证。公开 rootfs 不含 QQ、ChatGPT、Clash Verge、1Panel 或个人配置。

刷入前请阅读 [中文安装与回退说明](https://github.com/FanzhouStudio/-mix2s-Linux/blob/v0.1.0-preview.1/release/INSTALL.zh-CN.md)。目前的安装方式占用整个原 `userdata`；保留 Android `boot` **不等于已实现双系统共存**。独立分区共存方案仍需开发和验证。

可选启动方式：已准备好 Ubuntu 根分区后，可用 `fastboot boot` 仅从内存临时启动；确认后再选择 `fastboot flash recovery` 安装到 recovery。两种方式都不会自动建立 Android／Ubuntu 双系统；格式化 `userdata` 前必须自行备份 Android 数据。

下载后运行 `sha256sum -c SHA256SUMS`。此项目不是小米、Ubuntu 或 Kali 的官方发行版。

内核 payload 来自 Kali NetHunter Pro 2024.3 SDM845 镜像中的 `linux-image-6.1-sdm845`，包版本 `6.1.69+sdm845-1`；该包标记的源码项目为 [Mobian sdm845-linux](https://salsa.debian.org/Mobian-team/devices/kernels/sdm845-linux)。本项目在此基础上适配了 Polaris 的设备树、initramfs 与 Ubuntu 启动方式。Ubuntu 用户空间软件包的许可文件保留在 rootfs 的 `/usr/share/doc/` 中。
