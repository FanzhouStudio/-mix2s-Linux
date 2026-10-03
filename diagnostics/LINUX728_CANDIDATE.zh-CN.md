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
- 首次诊断所需的 `USB_CONFIGFS`、USB PHY、WLED 背光、LAB/IBB 面板供电也编入内核。第三版关闭内建 `g_serial`，启用 `U_SERIAL_CONSOLE`，由 init 建立单一 ConfigFS ACM gadget，并把 `ttyGS0` 用作内核日志控制台。
- 版本后缀为 `7.2.8-polaris`，便于与系统现有的 `6.1-sdm845` 区分。

在项目目录执行 `bash diagnostics/build-linux728-polaris-candidate.sh`。脚本不会写入手机。成功编译的 `7.2.8-polaris` 产物另存于 `artifacts/linux728-polaris-candidate/`：

| 文件 | SHA-256 |
| --- | --- |
| `Image.gz` | `73413149af951e973ed200e1945a5c88a78ee3ff07e99340f816ed844baf5b57` |
| `sdm845-xiaomi-polaris.dtb` | `ceebbaeab7d770d85b8c78c6095e2b4486c05f4cec8c7baedc3f86ffc5c60801` |
| `kernel.config` | `5b40ccc38de58e94d99e0b035836dd15a3c3e5151a6e96cb6321b2a181e74f56` |

旧的 `polaris-linux728-ramboot.img` 复用了 6.1 的持久系统 initramfs，已不作为首次测试镜像。7.2.8 不能加载其中的 6.1 模块。

本轮使用 `python3 diagnostics/build-linux728-readonly-diag.py` 制作 RAM-only 镜像，不挂载 userdata，发现的存储块设备设为只读。第三版镜像 `artifacts/linux728-polaris-candidate/polaris-linux728-readonly-diag.img` 为 17,715,200 字节，SHA-256 `8f05ca618f4aaa7a742c7b52abe972aa0b2efe3d47c83be8ab0cbeebdcbe9c92`。首次镜像通过 `fastboot boot` 启动后，Ubuntu-Max 曾读到 USB ACM 制造商 `Linux 7.2.8-polaris with dwc3-gadget`，证明内核至少启动到 gadget 枚举。手机灰屏后黑屏；尚未观察到诊断 init 的串口输出。第二版修正了 init 与内建 `g_serial` 抢 UDC 的问题，但手机仍黑屏；Ubuntu-Max 只记录到两次未完成的 USB 连接，VMware 报设备无法识别。

第三版于 2026-10-04 使用 `fastboot boot` 临时启动。手机纯黑屏，但 Ubuntu-Max 枚举出 `0525:a4a7`、产品 `Linux 7.2.8 RAM-only`、序列号 `polaris-linux728-diag`、`ttyACM0`，确认已运行到诊断 init 中的 ConfigFS ACM 绑定。主机的旧 udev 规则只匹配 `polaris-diag-v8`，所以串口节点仍为 `root:dialout`、模式 `0660`，当前会话尚不能读取内核日志。需先授权当前串口，才能根据显示子系统的实际错误做补丁；仅凭黑屏不能确定面板驱动是唯一原因。

编译和打包成功仍不能证明手机能启动，也不能证明 RCU 卡死已消失。后续需临时启动，确认显示、USB、UFS、触摸、Wi-Fi、音频和复现负载。旧版 7.2.8 临时镜像曾未可靠启动。
