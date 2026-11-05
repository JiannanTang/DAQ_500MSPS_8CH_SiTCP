# DAQ_500MSPS_8CH_SiTCP

面向 8 通道 500 MSPS ADC 硬件的 SiTCP 上位机。当前完成 RBCP 慢控、寄存器配置、TCP ADC 数据采集、增量帧解析、实时波形和原始数据存盘。

## 工程结构

```text
DAQ_500MSPS_8CH_SiTCP/
├── config/
│   └── registers.toml       # 设备地址、端口、寄存器表
├── reference/               # FPGA 代码和 SiTCP 手册
├── src/sitcp_host/
│   ├── core/
│   │   ├── rbcp.py          # RBCP 报文编解码和校验
│   │   ├── registers.py     # 配置与寄存器模型
│   │   ├── device.py        # 高层寄存器读写
│   │   ├── framing.py       # 64 bit ADC 流增量解析
│   │   └── storage.py       # 原始帧队列和后台写盘
│   ├── transport/
│   │   ├── rbcp_udp.py      # UDP 请求、超时、重试和 ID 匹配
│   │   └── tcp_data.py      # TCP ADC 数据流 socket
│   ├── testing/
│   │   └── fake_rbcp.py     # 无硬件开发用的模拟设备
│   ├── gui/
│   │   ├── main_window.py    # 主窗口和线程协调
│   │   ├── worker.py         # 后台 RBCP 工作对象
│   │   ├── data_worker.py    # 后台 TCP 采集线程
│   │   ├── theme.py          # 界面样式
│   │   └── widgets/          # 连接、状态、波形、寄存器、原始读取
│   └── cli.py               # 命令行探针
├── docs/
│   ├── data_frame.md        # TCP 数据帧格式与样例解析
│   └── raw_capture.md       # 原始数据文件与存盘行为
└── tests/                   # 协议、TCP/UDP 和 GUI 测试
```

使用 `src` 布局可以避免测试或脚本误导入当前目录中的同名文件，也便于以后用 PyInstaller 打包。新增模块应遵守以下边界：

- `core` 不导入 Qt，也不创建网络 socket。
- `transport` 只处理网络收发，不解释具体业务页面。
- 后续 `gui` 只调用 `core/device.py` 等高层接口，不直接拼 RBCP 报文。
- 后续 `tcp` 数据模块独立于 RBCP，帧解析不能放进 UI 回调。

## 环境

要求 Python 3.11 或更新版本。桌面界面使用 PySide6；RBCP 核心和命令行本身不依赖 Qt。

```powershell
python -m pip install -e .
```

也可以不安装，只在当前终端添加源码路径：

```powershell
$env:PYTHONPATH = (Join-Path $PWD 'src')
python -m sitcp_host.cli list
```

Windows 下也可以直接使用项目脚本，无需安装：

```powershell
.\scripts\run_gui.ps1
.\scripts\run_tests.ps1
.\scripts\run_fake_device.ps1 --port 4660
```

如果 PowerShell 禁止执行 `.ps1` 脚本，可直接在项目根目录运行：

```powershell
.\run_gui.cmd
.\DAQ_500MSPS_8CH_SiTCP.cmd
```

也可以只对这一次启动临时绕过执行策略：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_gui.ps1
```

## 桌面界面

```powershell
sitcp-host
daq500m
```

也可以直接运行：

```powershell
python -m sitcp_host
```

界面启动后使用默认设备地址，点击“连接”即可。网络操作在独立 `QThread` 中执行，状态默认每秒刷新。配置页不会在连接时自动写入任何值；普通参数由明确的写入按钮提交，瞬时控制则在鼠标按下和抬起时分别发送有效值和 `0`。

标题栏右侧的“亮色主题/暗色主题”按钮可以在白底黑字和暗底白字之间切换。主题选择会保存在本机设置中，波形背景、坐标轴和曲线颜色也会同步切换。

标题栏的“中文 / English”选择器可以实时切换界面语言，不需要重启。连接、状态、采集、配置、原始访问和工具提示会一起切换，语言选择同样会保存到本机设置。

连接成功后切到“实时采集”，TCP 端口默认为 `24`，可以在“开始采集”之前修改，修改后的值会保存到本机设置。界面以 2×4 网格显示 8 个独立 ADC 波形，横轴按 500 MSPS 换算为纳秒，每个采样点间隔 `2 ns`，并显示吞吐率、帧率、采样率、各通道帧数。

ADC 波形可选择两种显示方式：

- 码值：`原始值 - 8192`，纵轴使用整数
- 电压：`(code - 8192) * 1800 / 16384`，单位为 mV，纵轴保留 1 位小数

采集启动后可以单独点击“开始存盘”和“停止存盘”。存盘线程只写入完整帧的原始 TCP 字节，并生成同名 `.json` 元数据。默认目录是 `captures/`，也可从界面选择其他目录。文件名可直接输入；留空时自动使用时间和 IP 命名，输入名称会自动补 `.bin` 和 `.json` 扩展名，同名文件不会被覆盖。文件格式见 [docs/raw_capture.md](docs/raw_capture.md)。

“存盘时暂停波形”是一个可勾选按钮。启用后，存盘期间暂停 ADC 样本解码和 Qt 曲线重绘，TCP 帧边界扫描、帧计数和批量原始数据写入仍继续运行。停止存盘后，收到新帧时恢复波形刷新。

配置页现在采用专用控件：

- “时钟与 ADC”和“JESD204B”两个控制卡片位于页面顶部。
- 触发模式、其他触发参数和全通道统一设置依次排列在通道参数卡片之前。
- 触发模式使用 5 个互斥按钮，只能选择一个模式，当前模式以蓝色高亮。
- 软件触发模式会自动每 100 ms 发送一次软件触发脉冲；停止使用该模式后自动停止。
- CH0-CH7 各有阈值、长度和偏移输入框，可单独读取、写入。
- “所有通道统一设置”可把同一组参数写入全部 8 个通道。
- 触发通道和触发边沿均使用 CH0-CH7 复选框；边沿复选框勾选表示上升沿，未勾选表示下降沿。
- 所有数值设置旁标注了允许范围。
- 瞬时控制按钮在按下时写入有效值 `1`，抬起时写入 `0`。
- 瞬时按钮的文字直接显示在按钮中央，不再采用左侧标签加右侧按钮的布局。
- `sys_rst` 和 `ad9528_reset` 当前均为高有效，执行“按下 `1`、抬起 `0`”。
- `trigger_buffer_clear`（地址 `0x0030`）是高有效瞬时按钮，位于实时采集页“开始存盘”按钮右侧；切换触发模式或改变各通道触发长度后可用来清空固件触发缓存。
- AD9694 Power Down 使用两态开关：正常写入 `0x0`，掉电写入 `0x3`。
- JESD204B 同步状态 `0x11` 和复位状态 `0x10` 分别显示绿色指示灯，其他状态显示红色。
- 所有数字输入框不再响应鼠标滚轮，避免滚动页面时误改参数。
- 下拉框具有与当前主题匹配的底色和文字色，不会出现白底白字。

配置页顶部提供“一键 CFG”按钮，按以下顺序执行：

```text
系统复位
AD9528 复位
配置 AD9528
配置 AD9694
开始 JESD204B 同步
读取 JESD 状态
```

每一步仍保留独立按钮。一键流程在后台 RBCP 线程中顺序执行，每个步骤完成后等待 10 ms 再执行下一步，并在通信日志中记录进度。

每次寄存器写入都会在日志中显示 `WRITE REQUEST`、`WRITE`、`READBACK REQUEST` 和最终 `READ` 结果。回读在写入完成后单独发起，因此即使硬件回读值与写入值不同，日志也不会丢失。

温度按 Xilinx XADC 12 bit 传递函数换算：

```text
Temperature(°C) = raw * 503.975 / 4096 - 273.15
```

数据帧的字段定义、长度计算和样例解析见 [docs/data_frame.md](docs/data_frame.md)。

## Windows EXE 打包

双击或在命令行运行：

```powershell
.\build_exe.cmd
```

构建脚本会创建独立的打包环境、生成 one-dir 版本、自动执行 exe 启动自检，并输出：

```text
dist\DAQ_500MSPS_8CH_SiTCP\DAQ_500MSPS_8CH_SiTCP.exe
dist\DAQ_500MSPS_8CH_SiTCP\config\registers.toml
dist\DAQ_500MSPS_8CH_SiTCP\captures\
dist\DAQ_500MSPS_8CH_SiTCP-0.14.0-win64.zip
```

one-dir 发布时必须整体保留目录，不能只复制 `DAQ_500MSPS_8CH_SiTCP.exe`。其他电脑不需要安装 Python、PySide6 或 NumPy，解压 zip 后直接运行 exe。

## 使用命令行探针

默认读取 `config/registers.toml` 中的设备地址 `192.168.10.16:4660`。实际地址不同则修改配置，或在命令中覆盖：

```powershell
sitcp-probe list
sitcp-probe --host 192.168.10.16 status
sitcp-probe --host 192.168.10.16 read temperature
sitcp-probe --host 192.168.10.16 read 0x010A --length 1
sitcp-probe --host 192.168.10.16 smoke --yes
```

显式写寄存器和脉冲式控制都需要 `--yes`：

```powershell
sitcp-probe write trigger_mode 0 --yes
sitcp-probe pulse software_trigger --yes
```

`momentary=true` 的寄存器不能通过普通写命令保持为 1，只能使用 `pulse`，避免复位、配置启动或软件触发一直有效。

`smoke` 会对未映射的配置暂存地址 `0x007F` 写入测试值、回读校验并恢复原值，不会改动触发、时钟、ADC 或复位配置。

## 无硬件测试

终端一启动模拟设备：

```powershell
sitcp-fake-device --host 127.0.0.1 --port 4660
```

终端二验证完整 UDP 链路：

```powershell
sitcp-probe --host 127.0.0.1 --port 4660 status
```

运行自动化测试：

```powershell
$env:PYTHONPATH = (Join-Path $PWD 'src')
python -m unittest discover -s tests -v
```

## 当前约定

- RBCP 命令头为大端地址；8 通道阈值、温度和 64 位时间的数据按小端解释。
- UDP 请求严格串行，ACK 会校验来源、ID、命令、地址和长度。
- 默认每次超时 800 ms，最多重试 2 次。
- 配置寄存器可能没有 FPGA 复位初值，因此程序不会在连接时自动写入任何配置。
- `0x00000080-0x000000FF`、`0x00000180-0x000001FF` 和未映射地址都会被主机端拒绝。
- TCP 帧长度为 `16 + length * 8` 字节，包含 `length * 4` 个 ADC 样本。
- 当前数据协议没有魔数或校验。解析器要求连接从包头开始；发现保留位或 ADC 高两位异常时会停止采集。
