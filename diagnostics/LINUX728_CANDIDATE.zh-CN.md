# Linux 7.2.8 Polaris 候选内核

此候选内核只在 Ubuntu-Max 主机编译；当前手机 recovery 中的 `6.1-sdm845` 不变。

## 为什么要换内核

6.1 的串口记录在浏览器视频、ChatGPT/QQ 启动、`dpkg-deb` 解压等不同负载下都出现 RCU 停顿。浏览器记录还指出 RCU 线程的定时唤醒未发生；解压记录里的 CPU 6 停在 `clear_page`。这说明底层调度、计时器、中断、内存管理或固件交互需要排查；RCU 报警本身不能锁定故障源。

## 来源与适配

- 源码：kernel.org 的 `linux-7.2.8.tar.xz`，SHA-256 `12e8d5a973d1ad7c5a5c69882e4022b131ed715db7003fdcd760ddf8c3e51941`。
- 基础配置：此前 7.2.8 候选的 `artifacts/kernel.config`。对照 `artifacts/kali61-extracted.config` 保留 DRM、触摸、USB ACM、Wi-Fi 和 Qualcomm 平台支持。
- JDI 面板：保留先前的 NT35596S 初始化补丁，只为 Polaris 对应的面板启用 `prepare_prev_first`。这个顺序来自已运行的 6.16.7 面板修补记录；其他 NT36672A 面板不受影响。
- 固件路径：Polaris 设备树继续使用已运行的 6.1 系统中的 `qcom/sdm845/polaris/` 和 `qca/polaris/` 路径，避免当前 rootfs 找不到固件。没有回退 7.2.8 的其他设备树供电定义。
- UFS：将 `SCSI_UFS_QCOM`、`PHY_QCOM_QMP` 和 `PHY_QCOM_QMP_UFS` 编入内核，以便早期发现 userdata。
- 版本后缀为 `7.2.8-polaris`，便于与系统现有的 `6.1-sdm845` 区分。

在项目目录执行 `bash diagnostics/build-linux728-polaris-candidate.sh`。脚本不会写入手机。成功编译的 `7.2.8-polaris` 产物另存于 `artifacts/linux728-polaris-candidate/`：

| 文件 | SHA-256 |
| --- | --- |
| `Image.gz` | `6ccdad11f83aaef27468aac164832f68ca2bde6e3971451c17d14b8211ae922e` |
| `sdm845-xiaomi-polaris.dtb` | `ceebbaeab7d770d85b8c78c6095e2b4486c05f4cec8c7baedc3f86ffc5c60801` |
| `kernel.config` | `43bffcb26a25830a764e5af948f4aca9ada5cd31f06cc6cf23d9fb8c42200b20` |

`python3 diagnostics/build-linux728-ramboot.py` 已将上述内核和 DTB 放入已启动过的 Android boot v0/recovery 布局，并复用原 6.1 initramfs。所得 `artifacts/linux728-polaris-candidate/polaris-linux728-ramboot.img` 为 25,767,936 字节，SHA-256 `e1108d48657fa16019c0d264f7a599e39fadcd3d73457dc5f0f214ea54c9c404`。它只适合作为以后 `fastboot boot` 的临时启动候选；不应刷入分区。原 initramfs 中的 6.1 模块不能用于 7.2.8，因此 Wi-Fi、音频等功能还需要另配匹配模块。

编译和打包成功仍不能证明手机能启动，也不能证明 RCU 卡死已消失。后续需临时启动，确认显示、USB、UFS、触摸、Wi-Fi、音频和复现负载。旧版 7.2.8 临时镜像曾未可靠启动。
