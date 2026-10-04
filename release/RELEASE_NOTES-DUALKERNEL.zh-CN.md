# Polaris Ubuntu 26.04.1 双内核预览版

面向小米 MIX 2S（`polaris`）的当前 Ubuntu ARM64 快照：Linux 7.2.8 在 `boot` 分区供正常开机，Linux 6.1 在 `recovery` 分区供音量上＋电源启动，两者共用原 `userdata` 上的 Ubuntu ext4。**这是双 Linux 内核入口，不是 Android／Ubuntu 双系统。**

当前原设备的 `boot` 前 22,077,440 字节与发布的 7.2.8 镜像校验值一致，`recovery` 前 19,853,312 字节与发布的 6.1 镜像校验值一致。正常启动 7.2.8 后，用户确认 GNOME 桌面与触摸可用；随后通过音量上＋电源进入 6.1 recovery 桌面，串口也确认内核为 `6.1-sdm845`。

双内核的好处是可在同一套 Ubuntu 用户空间上比较驱动表现，并在主内核不能启动时尝试 6.1 recovery 诊断或回退，无须维护两份系统。代价是两个内核共享 userdata，软件或文件系统损坏会同时影响两边；原 Android recovery 也被替换。它不会让 Android 与 Ubuntu 共存。

公开 rootfs 以已审计的 v0.1.0 公开 Ubuntu 26.04.1 快照（SHA-256 `0055cbad6f7ed24d0bbba32d887ba3cb1062ba3dd09eb606d9a9e4ad399496ce`）为底座，补入当前 7.2.8 所需的 zram 模块、启动脚本与服务。它**不是手机此刻 userdata 的逐文件快照**；新安装的双内核启动尚未在第二台手机上验证。归档不含个人主目录、账户密码哈希、网络凭据、SSH 主机密钥、1Panel 数据或 QQ、ChatGPT、Clash Verge 等可选应用。首次安装须自行设置 `polaris` 密码。归档不是整机备份，也不是可用 `fastboot flash userdata` 直接刷入的镜像。

已在原设备上分别观察到桌面、触摸、屏幕键盘、Wi-Fi、GPU 渲染、扬声器和蜂窝数据等功能；并非每一项都在本次正式刷入后重新验证。7.2.8 正常重启后，6 GiB LZ4 zram 交换空间自动启用。zram 是压缩内存交换空间，不会增加 6 GiB 物理内存。

**已知重要问题：**7.2.8 和 6.1 都曾在 Clash Verge、ChatGPT、QQ、浏览器或其他负载下发生整机卡死，日志中有 RCU 停顿。7.2.8 的这类问题仍未解决；本版只适合实验和适配开发。相机、通话音频、短信、蓝牙配对与长期稳定性尚未完成验证。两个内核共享同一个 userdata，根文件系统受损时不能依赖 6.1 recovery 自动恢复。

本次尝试从 7.2.8 运行态连续导出 rootfs 时触发了 CPU 5 的 RCU 停顿；从 6.1 recovery 再次限速导出也失去响应。两份未完成的归档均已丢弃，因此改用上述已脱敏底座进行确定性的主机构建。这个故障说明大量读取也可能触发当前内核问题。新归档通过必需文件、私人路径、登录配置、已知 Wi-Fi 凭据和解压完整性检查，但尚未在手机上重新刷入启动。

刷写、备份、首次设置密码、双内核按键、优势与限制详见附件 [`INSTALL-DUALKERNEL.zh-CN.md`](https://github.com/FanzhouStudio/-mix2s-Linux/blob/main/release/INSTALL-DUALKERNEL.zh-CN.md)。下载后运行 `sha256sum -c SHA256SUMS-DUALKERNEL`。本项目不是小米、Ubuntu 或 Kali 的官方发行版。

7.2.8 基于 [Linux 稳定版 v7.2.8](https://cdn.kernel.org/pub/linux/kernel/v7.x/linux-7.2.8.tar.xz)，当前运行配置作为 `polaris-linux-7.2.8-running.config` 附上；zram 模块后来单独按相同内核版本构建，因此基础内核配置中没有内建 zram。设备补丁、构建脚本和适配记录见本仓库 `diagnostics/`。6.1 启动镜像来自 Kali NetHunter Pro 的 SDM845 工作，相关源码项目为 [Mobian sdm845-linux](https://salsa.debian.org/Mobian-team/devices/kernels/sdm845-linux)。Ubuntu 用户空间包的许可文件保留在归档 `/usr/share/doc/` 中。
