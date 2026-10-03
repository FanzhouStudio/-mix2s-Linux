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
- 首次诊断所需的 `USB_CONFIGFS`、USB PHY、WLED 背光、LAB/IBB 面板供电也编入内核。内建 `g_serial` 会先占用 UDC，诊断 init 复用其 `/dev/ttyGS0`。
- 版本后缀为 `7.2.8-polaris`，便于与系统现有的 `6.1-sdm845` 区分。

在项目目录执行 `bash diagnostics/build-linux728-polaris-candidate.sh`。脚本不会写入手机。成功编译的 `7.2.8-polaris` 产物另存于 `artifacts/linux728-polaris-candidate/`：

| 文件 | SHA-256 |
| --- | --- |
| `Image.gz` | `6e735574b19a72ad9ea460819d0dd67b9f6a74d428ef83cc3be5e1869eca292c` |
| `sdm845-xiaomi-polaris.dtb` | `ceebbaeab7d770d85b8c78c6095e2b4486c05f4cec8c7baedc3f86ffc5c60801` |
| `kernel.config` | `b884767f957239084246021e1f7f15c31611f2bcbde9e474b6aa9d196aeab7a9` |

旧的 `polaris-linux728-ramboot.img` 复用了 6.1 的持久系统 initramfs，已不作为首次测试镜像。7.2.8 不能加载其中的 6.1 模块。

本轮使用 `python3 diagnostics/build-linux728-readonly-diag.py` 制作 RAM-only 镜像，不挂载 userdata，发现的存储块设备设为只读。镜像 `artifacts/linux728-polaris-candidate/polaris-linux728-readonly-diag.img` 为 17,715,200 字节；第二版 SHA-256 `b60cdf9899f6128c9ac45a78bb6ad1a12d922e32e125a87f72a079974b0b7a27`。首次镜像通过 `fastboot boot` 启动后，Ubuntu-Max 曾读到 USB ACM 制造商 `Linux 7.2.8-polaris with dwc3-gadget`，证明内核至少启动到 gadget 枚举。手机灰屏后黑屏；尚未观察到诊断 init 的串口输出。第二版修正了 init 与内建 `g_serial` 抢 UDC 的问题，但手机仍黑屏；Ubuntu-Max 只记录到两次未完成的 USB 连接，VMware 报设备无法识别。当前不能确认第二版是否进入 init，也不能把故障归因于某个具体驱动。需回到已安装的 6.1 recovery。后续如要继续 7.2.8，先建立可用的早期日志通道，再做最小差异的设备树/面板试验。

编译和打包成功仍不能证明手机能启动，也不能证明 RCU 卡死已消失。后续需临时启动，确认显示、USB、UFS、触摸、Wi-Fi、音频和复现负载。旧版 7.2.8 临时镜像曾未可靠启动。
