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
- 第四版根据串口中的延迟探测记录，将 DSI 所需的 `REGULATOR_QCOM_REFGEN`、触摸屏 I²C 所需的 `QCOM_GPI_DMA` 从模块改为内建。第六版给 MSM fbdev 的 CPU 映射缓冲区补上 `FBINFO_VIRTFB` 标记。
- 首次诊断所需的 `USB_CONFIGFS`、USB PHY、WLED 背光、LAB/IBB 面板供电也编入内核。第三版关闭内建 `g_serial`，启用 `U_SERIAL_CONSOLE`，由 init 建立单一 ConfigFS ACM gadget，并把 `ttyGS0` 用作内核日志控制台。
- 版本后缀为 `7.2.8-polaris`，便于与系统现有的 `6.1-sdm845` 区分。

在项目目录执行 `bash diagnostics/build-linux728-polaris-candidate.sh`。脚本不会写入手机。成功编译的 `7.2.8-polaris` 产物另存于 `artifacts/linux728-polaris-candidate/`：

| 文件 | SHA-256 |
| --- | --- |
| `Image.gz` | `1be5e1f71353485e8df8a574f6c26a3bd541df33231a98e02c973dc6837a9b48` |
| `sdm845-xiaomi-polaris.dtb` | `ceebbaeab7d770d85b8c78c6095e2b4486c05f4cec8c7baedc3f86ffc5c60801` |
| `kernel.config` | `bc58e7b1301e0d110a1179c4351e174e8bf11f198fc23b87cabbc2ee57a49042` |

旧的 `polaris-linux728-ramboot.img` 复用了 6.1 的持久系统 initramfs，已不作为首次测试镜像。7.2.8 不能加载其中的 6.1 模块。

本轮使用 `python3 diagnostics/build-linux728-readonly-diag.py` 制作 RAM-only 镜像，不挂载 userdata，发现的存储块设备设为只读。第七版镜像 `artifacts/linux728-polaris-candidate/polaris-linux728-readonly-diag.img` 为 17,752,064 字节，SHA-256 `6f5b0a1fabd7f9503f3cbd479aca09bcc3e670f3f9ae437d91a9c69127fec11b`；实机测试结果见下文。首次镜像通过 `fastboot boot` 启动后，Ubuntu-Max 曾读到 USB ACM 制造商 `Linux 7.2.8-polaris with dwc3-gadget`，证明内核至少启动到 gadget 枚举。手机灰屏后黑屏；尚未观察到诊断 init 的串口输出。第二版修正了 init 与内建 `g_serial` 抢 UDC 的问题，但手机仍黑屏；Ubuntu-Max 只记录到两次未完成的 USB 连接，VMware 报设备无法识别。

第三版于 2026-10-04 使用 `fastboot boot` 临时启动。手机纯黑屏，但 Ubuntu-Max 枚举出 `0525:a4a7`、产品 `Linux 7.2.8 RAM-only`、序列号 `polaris-linux728-diag`、`ttyACM0`，确认已运行到诊断 init 中的 ConfigFS ACM 绑定。授权串口后，`dmesg` 明确报告 `ae94000.dsi` 在等待 `ff1000.regulator`；`CONFIG_REGULATOR_QCOM_REFGEN=m`，最小诊断系统没有相应模块。另有 `a98000.i2c` 等待 DMA，而 `CONFIG_QCOM_GPI_DMA=m`；Polaris 触摸屏位于这个 I²C 控制器。第四版把这两个依赖编入内核，再观察 DRM 注册和面板初始化结果。

第四版启动后，REFGEN 和 GPI DMA 的延迟探测消失，Synaptics S3330 注册成功。`msm-mdss` 在约 11 秒因依赖探测超时 `-110` 而未自动绑定；系统运行后手动通过 sysfs 绑定 `msm-mdss` 成功，DRM 注册了 `card0-DSI-1`、1080×2160 的 `msmdrmfb`。绑定期间发生大量 SID `0x880`/`0xc88` 的 ARM SMMU 翻译故障和 WLED OVP 中断警告；当时用户看到纯黑屏且没有背光。仅解除 `fb0/blank` 并不能证明显示输出正常。第五版只调整诊断镜像的启动参数为 `fw_devlink=off deferred_probe_timeout=60`，并从现有 Ubuntu rootfs 纳入已校验的 `a630_gmu.bin`、`a630_sqe.fw`，以排除缺失 GPU 固件并测试启动顺序。持续的 SMMU 故障也需要单独分析，不能把 DRM 注册等同于显示可用。

第五版于 2026-10-04 通过 `fastboot boot` 临时启动，DRM 自动绑定、`card0-DSI-1` 注册，GPU 能加载 SQE 和 GMU 固件，但缺少设备树指定的 `qcom/sdm845/polaris/a630_zap.mbn`，报告 `gpu hw init failed: -2`。SMMU 的 SID `0x880`/`0xc88` 故障仍大量出现；fbcon 还报告 `sys_imageblit: framebuffer is not in virtual address space`。用户看到完全黑屏，未见背光。第六版将项目中已保存并校验的 ZAP 固件纳入 initramfs，另给 MSM fbdev 的 CPU 映射缓冲区设置 `FBINFO_VIRTFB`；这两个修正能排除明确的固件缺失和 fbdev 警告，但尚不能保证 DSI 面板、WLED 或 SMMU 正常。

第六版经 `fastboot boot` 临时启动后，用户看到短暂背光，随后全黑且 USB 设备无法识别。Ubuntu-Max 仅记录到 Fastboot USB 断开，没有第六版 ACM 枚举，因此拿不到本次内核日志。它同时改变了 GPU ZAP 固件和 fbdev 标记，不能将失效单独归因于某一项。第七版恢复为不纳入 ZAP 固件，只保留 fbdev 标记修正；打包器保留显式 `--include-zap-firmware` 参数供将来单独测试。

第七版于 2026-10-04 临时启动后，用户看到纯黑屏。重新把 USB 接入 Ubuntu-Max 后，`0525:a4a7` ACM 正常枚举，串口确认内核 `7.2.8-polaris`、`card0-DSI-1` 和 `fb0` 存在。`sys_imageblit` / `sys_fillrect` 的虚拟地址警告消失，说明 fbdev 标记修正生效；但 GPU 仍缺 ZAP 固件，SID `0x880`/`0xc88` 的 SMMU 故障及 DSI FIFO 错误 `status=4` 仍出现。背光类设备报告 2048/4095，PMI8998 WLED 寄存器 `d808=02`、`d810=02` 显示过压故障；将亮度设为 0 后两寄存器归零、模块关闭，低亮度重新开启又报告故障。

回到可亮屏的 6.1 recovery 后，用户确认桌面和背光正常。亮度同为 2048/4095，WLED 配置寄存器 `d846=80`、`d84d=02`、`d946=f0`、四个灯串 `d950/d960/d970/d980=80` 与 7.2 相同，但故障位 `d808=d810=00`。LAB/IBB 均显示已启用且为 4.6 V；6.1 内核日志没有 7.2 的显示 SMMU 故障或 DSI FIFO 错误。XBL 显示缓冲区 `0x9d400000` 的另行保留实验未进入当前可用的 recovery，不能把该保留视为已验证修复。下一轮应针对 DPU/SMMU 接管和 DSI 初始化的版本差异做单项实验；不要仅提高 WLED 过压阈值。

下一项单变量实验：6.16.7 的 `dpu_use_virtual_planes` 默认关闭，7.2.8 默认开启；两版 DPU 初始化会因此选用不同的平面分配路径。已生成 `artifacts/linux728-polaris-candidate/polaris-linux728-legacy-dpu-diag.img`，SHA-256 `0f84f2f3466f1cf497d1fd6fe1bb433be59a57c6ce9feffcdfb88b425080bcd4`。它与第七版使用同一内核、DTB 和 initramfs，只在启动参数中加入 `msm.dpu_use_virtual_planes=0`，仍不挂载或刷写手机分区。应通过 `fastboot boot` 测试，并用串口核对 `/proc/cmdline`、DSI/FIFO、SMMU 与背光状态。下面记录实机结果；即使亮屏，也不能据此认定 RCU 卡死或日常稳定性已解决。

该镜像已由 `fastboot boot` 临时启动，`/proc/cmdline` 证实 `msm.dpu_use_virtual_planes=0` 生效，但手机仍完全黑屏。DSI 时钟与可亮屏的 6.1 相同：pixel 153297998 Hz、byte 114973498 Hz、byte-intf 57486749 Hz、escape 19200000 Hz。内核仍在 1.39 秒左右报告 SID `0x880`/`0xc88` 对 `0x9d4...` 的 SMMU 翻译故障及 `dsi_err_worker: status=4`；6.39 秒已有 239405 条 SMMU 回调被抑制。WLED 在 7.67 秒的 `wled_ovp_work` 中触发重复 `enable_irq` 警告；PMIC 的 `d808=d810=02` 同时记录 OVP 状态，两者需分别分析。`fb0` 于 7.77 秒注册。虚拟显示平面默认值和时钟数值都不能单独解释故障，后续需检查旧扫描缓冲区在 SMMU 接管前后是否仍被 DPU 读取，以及面板/背光启用顺序。此结果不能外推为 7.2.8 日常可用。

第九版单变量候选：此前能亮屏的 postmarketOS 6.16.7 Polaris DTB 含 `framebuffer@9d400000`、`no-map`、长度 `0x02400000`，7.2.8 第七版 DTB 缺此节点；故障 IOVA 恰落在该 XBL 显示缓冲区。`diagnostics/build-linux728-xbl-reserved-dtb.sh` 只给设备树增加该保留项。反编译对比确认新旧 DTB 仅多此节点，内核 `Image.gz`、initramfs 与第七版相同。RAM-only 镜像 `artifacts/linux728-polaris-candidate/polaris-linux728-xbl-reserved-diag.img` 的 SHA-256 为 `252368f844dcd6e1c21e3d2ccb84b850c5cbc6f45d0c18271667d1d3427af77d`。应仅用 `fastboot boot` 试验；观察保留项是否出现在 `/proc/device-tree`，并对比 SMMU 故障数量、DSI、WLED 和屏幕状态。保留物理内存本身不等于在 IOMMU 中建立映射，因此不能预设故障会消失。

第九版已通过 `fastboot boot` 临时启动，USB ACM 可用，但用户确认屏幕仍纯黑。运行时设备树和内核日志均确认 `0x9d400000..0x9f7fffff` 的 36 MiB `no-map` 保留区生效。显示控制器仍于约 1.36 秒产生 SID `0x880`/`0xc88`、`fsr=0x402`、IOVA `0x9d4...` 的 SMMU 翻译故障；1.386 秒有 `dsi_err_worker: status=4`，6.365 秒仍密集报错，7.65 秒进入 `wled_ovp_work`，7.749 秒才注册 `fb0`。仅保留物理区不足以解决显示故障。下一步应对照可亮屏内核，追查 DRM 接管旧扫描缓冲区与显示 IOMMU domain 绑定的先后顺序；旧缓冲区继续被读取只是待验证假设，不能视为既定根因。保留当前可用的 6.1 recovery，不刷写第九版。

第十版候选在第九版的同一保留区上，只为 Polaris 的 MDSS IOMMU domain 在接入设备前建立 `0x9d400000..0x9f7fffff` 的只读恒等映射。改动位于 `diagnostics/patches/0007-linux728-polaris-xbl-display-iommu-map.patch`；构建脚本会在编译后还原上游源文件。镜像 `artifacts/linux728-polaris-candidate/polaris-linux728-xbl-iommu-diag.img` 的 SHA-256 为 `6bc2b947cca1ed6a3a5fbb1d21805396ddac8f8576ba07a05d49cecc8cad4505`，仍是只读内存诊断，不挂载 userdata，不刷写分区。该实验应先确认日志出现映射成功，再比较 SID `0x880`/`0xc88` 故障、DSI FIFO 和背光；即使故障消失，也还需实际亮屏和稳定性验证。目前尚未在手机上启动。

第九版黑屏后，用户已重启回现有 Linux 桌面；USB ACM 重新枚举，串口 `uname -r` 确认为 `6.1-sdm845`。当前 recovery 未改动。

第十版已在 Fastboot 设备 `product: polaris` 上执行 `fastboot boot`，发送 17,752,064 字节镜像及 Booting 均返回 `OKAY`；设备的 `max-download-size` 为 805,306,368 字节。用户观察到有背光但无文字，VMware 报新 USB 无法识别；Ubuntu-Max 只记录到 Fastboot USB 断开，没有新 USB ACM 枚举。无法读取新内核日志，也无法确认映射代码是否执行。该版本没有达到可用显示或可诊断串口状态，不能刷写；有背光不能视为显示修复成功。下一轮需先恢复可靠的早期日志通道，再判断是否应继续此映射方案。

用户已重启回原 Linux 桌面，USB ACM 重新出现，串口 `uname -r` 再次确认为 `6.1-sdm845`。第十一版只针对诊断可见性：将 Polaris 上 MSM DRM 的注册延后 45 秒，让现有 initramfs 有机会先建立 USB ACM，然后仍执行第十版的显示 IOMMU 映射。延迟注册函数及其调用链已移出 `__init` 段；重新编译无 section mismatch 警告。诊断镜像 `artifacts/linux728-polaris-candidate/polaris-linux728-xbl-iommu-serial-first.img` 为 17,752,064 字节，SHA-256 `04c87439efc2d0d58902be3feafcd4a5efe102d107e9525cedd66c35558fa0c8`。这不是修复候选，尚未在手机上启动；只应由 `fastboot boot` 从内存测试，不得刷写 recovery。

第十一版已通过 `fastboot boot` 临时启动。用户观察到短暂背光黑屏、随后背光熄灭。USB 重连后 Ubuntu-Max 枚举 `0525:a4a7`，串口 `uname -r` 确认为 `7.2.8-polaris`。日志显示 0.28 秒计划延后 DRM，46.06 秒开始注册；46.08 秒 DSI PLL 锁定失败，46.105 秒在设备接入前调用 `iommu_map()` 返回 `-19`（`ENODEV`），因此根本没有建立 XBL IOMMU 映射。该错误使 DRM 初始化失败，46.108 秒又在 `dpu_kms_destroy`/`drm_atomic_private_obj_fini` 的错误清理路径触发内核 Oops；原映射假设仍未得到验证。日志存于 `diagnostics/logs/serial-linux728-xbl-iommu-serial-first-20261004-1322.log`。不能把本轮背光或 PLL 故障解释为映射方案有效；延迟 45 秒本身也可能改变 DSI 电源状态。第十一版不可刷写。

用户自行重启回 Linux 桌面，串口再次确认 `6.1-sdm845`。第十二版：`diagnostics/patches/0009-linux728-polaris-xbl-iommu-after-attach.patch` 将只读恒等映射改到 `iommu_attach_device()` 成功之后，失败只记录警告并继续；`diagnostics/patches/0010-linux728-polaris-drm-delay-5s.patch` 将串口优先窗口从 45 秒缩为 5 秒，以减少迟注册对 DSI 供电状态的影响。镜像 `artifacts/linux728-polaris-candidate/polaris-linux728-xbl-iommu-after-attach.img` 为 17,756,160 字节，SHA-256 `6b7c4f20740af3de61390d2ddc0939dab75f61c992a7ff54e40e0c22b9b22821`。仍仅供 `fastboot boot` 临时诊断，不能刷写。

第十二版已在 2026-10-04 从内存启动并保持运行。串口确认内核 `7.2.8-polaris`，`iommu_attach_device()` 后打印 `diagnostic XBL display IOMMU read map installed after attach`；DRM 注册 `card0-DSI-1`，`msmdrmfb` 模式为 1080×2160，Synaptics S3330 触摸设备也已注册。用户确认屏幕持续显示诊断文字、背光稳定，并能看到运行中新增的 `DISPLAY CHECK 728-42`，证明帧缓冲正在主动刷新。运行约 500 秒时，`fb0/blank=0`，内核日志中 `Unhandled context fault` 与 `dsi_err_worker` 均为 0 条；PMIC WLED 故障寄存器 `d808=d810=00`。这说明此前的黑屏、SMMU 故障及过压现象在此组合下没有复现，但不能单独证明只读 IOMMU 映射是唯一原因。

本轮仍只有 BusyBox 诊断界面，没有切换 Ubuntu rootfs；GPU 报 `gpu hw init failed: -2`，因为最小 initramfs 尚未包含 `a630_zap.mbn`。早期另有一次 DSI PLL 锁定警告，之后显示持续正常。触摸仅确认内核设备注册，尚未验证 GNOME 交互；Wi-Fi、音频、蜂窝和 RCU 压力负载也未验证。后续应保持 6.1 recovery 不变，先构建带匹配 7.2 模块与 GPU 固件的只读 Ubuntu RAM 覆盖层，用 `fastboot boot` 继续验证。

下一轮 Ubuntu 覆盖层诊断镜像为 `artifacts/linux728-polaris-candidate/polaris-linux728-ubuntu-overlay-diag.img`，18,718,720 字节，SHA-256 `05f202cfaec5d9570e36e546d6db6f595928379a0892c8a9296663c9fc0f5cb9`。与已亮屏的第十二版相比，内核、DTB、启动参数的哈希完全相同，只替换 initramfs：加入版本匹配的 `overlay.ko` 与 `diagnostics/init-linux728-overlay`。GPU ZAP 固件仍不加入，以免同时改变图形驱动变量。启动后默认仍停在 RAM 诊断；只有串口手动创建 `/run/start-ubuntu-overlay` 才会把 userdata 以 `ext4 ro,noload` 挂载，并用最多 2 GiB 的 tmpfs 做写入上层。启动前会再次把块设备设置为只读并检查 `blockdev --getro`。原 6.1 recovery 和 userdata 内容不会因该测试镜像被刷写。镜像不作为正式升级包发布。

该覆盖层镜像已于 2026-10-04 通过 `fastboot boot` 实机启动：诊断文字、USB ACM 和 DRM 正常，`Unhandled context fault` 与 `dsi_err_worker` 均为 0。手动触发后 `overlay.ko` 加载成功，userdata 以 `ro,noload` 挂载，根目录为 `overlay`，`blockdev --getro /dev/sda21` 返回 1；systemd 启动 Ubuntu 26.04.1 至 `graphical.target`，GNOME、触摸和屏幕键盘可操作。起初桌面卡顿，GNOME 日志显示硬件 EGL 初始化失败；原因是启动时 `/run/vendor` 未挂载，rootfs 的 `a630_zap.mbn` 符号链接指向不存在的文件。手动只读挂载 vendor 后，`eglinfo -B -p surfaceless` 显示 `freedreno / FD630`；重启 GDM 后，新 GNOME 日志显示取得高优先级 EGL 上下文，用户确认流畅度改善。此后 GPU 初始化失败计数不再增加，显示 SMMU 和 RCU 停顿仍为 0。

本轮还发现切换根目录后，诊断 init 的两个后台子进程留在旧根目录中空转，分别累计消耗约四分之一 CPU；在当前内存系统中结束它们后，GNOME 和串口服务仍正常。第十四版镜像 `artifacts/linux728-polaris-candidate/polaris-linux728-ubuntu-overlay-vendor-diag.img`（SHA-256 `8025d51c398546f0919d9165152c8b82ff88c8e860152aedfbb5a25a784a362f`）沿用同一内核和 DTB，只在 initramfs 中提前只读挂载 vendor、结束旧后台子进程，并恢复已配置的 USB 串口序列号。它仍只供 `fastboot boot`，尚未实机验证；Wi-Fi、音频及高负载稳定性仍待验证，不能刷写为正式升级。
