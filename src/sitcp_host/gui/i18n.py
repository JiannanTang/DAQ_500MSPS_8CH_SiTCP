"""Small runtime translation layer for the two supported UI languages."""

from __future__ import annotations

import re

from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDockWidget,
    QLabel,
    QLineEdit,
    QTabWidget,
    QWidget,
)

_language = "zh"

_ZH_TO_EN = {
    "设备连接": "Device Connection",
    "● 未连接": "● Disconnected",
    "● 正在连接": "● Connecting",
    "● 已连接": "● Connected",
    "● 正在断开": "● Disconnecting",
    "● 请输入设备 IP": "● Enter device IP",
    "● 连接失败": "● Connection Failed",
    "超时": "Timeout",
    "重试": "Retries",
    "连接": "Connect",
    "连接中...": "Connecting...",
    "断开": "Disconnect",
    "未连接": "Disconnected",
    "连接失败": "Connection Failed",
    "请输入设备 IP": "Enter device IP",
    "等待连接设备": "Waiting for device connection",
    "就绪": "Ready",
    "准备执行": "Preparing",
    "完成": "Complete",
    "已断开": "Disconnected",
    "一键 CFG 完成": "One-click CFG complete",
    "8 通道 · 500 MSPS ADC · SiTCP 硬件 TCP": (
        "8-channel · 500 MSPS ADC · SiTCP hardware TCP"
    ),
    "运行状态": "Live Status",
    "状态寄存器按原始值显示；尚无固件定义的编码和温度换算系数。": (
        "Registers are read in one batch; JESD indicators use the firmware's "
        "expected state values."
    ),
    "自动刷新": "Auto refresh",
    "立即刷新": "Refresh now",
    "刷新中...": "Refreshing...",
    "芯片温度": "Chip Temperature",
    "Xilinx XADC 12 bit 码值换算": "Converted from 12-bit Xilinx XADC code",
    "JESD204B 同步状态": "JESD204B Sync State",
    "JESD204B 复位状态": "JESD204B Reset State",
    "正常值 0x11": "Expected value 0x11",
    "正常值 0x10": "Expected value 0x10",
    "状态读取说明": "Status Read Notes",
    "每次刷新通过一个 RBCP 请求读取 0x0108-0x010B 共 4 字节：温度占前 2 字节，随后是 JESD 同步状态和复位状态。": (
        "Each refresh reads 4 bytes at 0x0108-0x010B in one RBCP request: "
        "temperature uses the first 2 bytes, followed by JESD sync and reset states."
    ),
    "尚未读取": "Not read yet",
    "设备离线": "Device offline",
    "● 正常": "● Normal",
    "● 异常": "● Fault",
    "实时采集": "Live Acquisition",
    "配置寄存器": "Configuration",
    "原始访问": "Raw Access",
    "TCP 数据流未配置": "TCP data stream not configured",
    "TCP 端口": "TCP Port",
    "显示": "Display",
    "码值": "Code",
    "电压 (mV)": "Voltage (mV)",
    "● 未采集": "● Idle",
    "● 正在连接数据流": "● Connecting data stream",
    "● 正在采集": "● Acquiring",
    "● 正在停止": "● Stopping",
    "● 已停止": "● Stopped",
    "● 数据流错误": "● Data stream error",
    "开始采集": "Start Acquisition",
    "停止采集": "Stop Acquisition",
    "文件名": "Filename",
    "留空自动命名": "Leave blank for automatic naming",
    "目录": "Directory",
    "选择目录": "Choose Directory",
    "存盘时暂停波形": "Pause Plots While Recording",
    "波形：实时": "Plots: Live",
    "波形：实时（存盘时暂停）": "Plots: Live (pause while recording)",
    "波形：存盘中已暂停": "Plots: Paused during recording",
    "开始存盘": "Start Recording",
    "停止存盘": "Stop Recording",
    "未存盘": "Not recording",
    "已有存盘任务正在运行": "A recording task is already active",
    "存盘目录为空": "Capture directory is empty",
    "吞吐率": "Throughput",
    "帧率": "Frame Rate",
    "采样率": "Sample Rate",
    "累计帧": "Total Frames",
    "本次存盘": "Recording Size",
    "通道帧计数：尚未收到数据": "Channel frames: no data received",
    "最近触发：--": "Latest trigger: --",
    "等待数据": "Waiting for data",
    "尚无触发数据": "No trigger data",
    "已更新": "Updated",
    "波形可选择显示码值（原始值减 8192）或电压 mV，电压公式为 (code-8192) × 1800 / 16384。存盘保存完整帧的原始字节；协议没有同步字，因此文件也从完整帧边界开始。": (
        "Plot values as raw code (sample - 8192) or voltage in mV using "
        "(code-8192) × 1800 / 16384. Recording stores complete raw frame bytes; "
        "the protocol has no sync word, so files begin on frame boundaries."
    ),
    "触发与设备配置": "Trigger and Device Configuration",
    "统一管理触发通道、触发模式、时钟、ADC 和 JESD 参数。": (
        "Configure trigger channels and modes, clocking, ADC, and JESD settings."
    ),
    "一键 CFG": "One-click CFG",
    "读取全部寄存器": "Read All Registers",
    "触发模式": "Trigger Mode",
    "五种模式互斥，选择后立即写入 trigger_mode 寄存器。": (
        "Five exclusive modes; selection is written to trigger_mode immediately."
    ),
    "独立模式": "Independent",
    "单通道广播": "Single-channel Broadcast",
    "双通道符合": "Two-channel Coincidence",
    "外部触发": "External Trigger",
    "软件触发": "Software Trigger",
    "当前模式：--": "Current mode: --",
    "所有通道统一设置": "Shared Channel Settings",
    "把同一组阈值、长度和偏移写入 CH0-CH7。": (
        "Apply one threshold, length, and offset set to CH0-CH7."
    ),
    "阈值 (0-16383)": "Threshold (0-16383)",
    "长度 (0-255)": "Length (0-255)",
    "偏移 (0-255)": "Offset (0-255)",
    "应用到所有通道": "Apply to All Channels",
    "清空触发缓存": "Clear Trigger Buffer",
    "切换触发模式或修改通道触发长度后，清空固件触发模块缓存。": (
        "Clear the firmware trigger buffer after changing trigger mode or channel lengths."
    ),
    "当前值未读取": "Current value not read",
    "读取本通道": "Read Channel",
    "写入本通道": "Write Channel",
    "其他触发参数": "Other Trigger Settings",
    "时钟与 ADC": "Clock and ADC",
    "触发通道": "Trigger Channels",
    "外部触发延迟": "External Trigger Delay",
    "系统复位": "System Reset",
    "AD9528 复位": "AD9528 Reset",
    "配置 AD9528": "Configure AD9528",
    "配置 AD9694": "Configure AD9694",
    "AD9694 Power Down": "AD9694 Power Down",
    "开始 JESD204B 同步": "Start JESD204B Sync",
    "JESD 状态读取": "Read JESD Status",
    "通道触发边沿": "Channel Trigger Edge",
    "符合触发展宽": "Coincidence Pulse Width",
    "符合通道 A": "Coincidence Channel A",
    "符合通道 B": "Coincidence Channel B",
    "触发缓存清空": "Clear Trigger Buffer",
    "AD9694：正常工作": "AD9694: Normal",
    "AD9694：Power Down": "AD9694: Power Down",
    "读取": "Read",
    "写入": "Write",
    "读取中...": "Reading...",
    "正在读取...": "Reading...",
    "读取失败": "Read failed",
    "触发通道（可多选）": "Trigger Channels (multi-select)",
    "触发通道边沿（勾选=上升沿）": (
        "Trigger Edges (checked = rising edge)"
    ),
    "原始寄存器读取": "Raw Register Read",
    "按固件允许的地址空间直接读取字节，用于核对端序和调试协议。当前页面只允许读，不提供任意地址写入。": (
        "Read bytes directly from firmware-approved address spaces for byte-order "
        "verification and protocol debugging. This page is read-only."
    ),
    "地址": "Address",
    "长度": "Length",
    "读取结果会显示在这里": "Read results appear here",
    "地址格式无效，请使用十进制或 0x 前缀的十六进制": (
        "Invalid address; use decimal or a 0x-prefixed hexadecimal value"
    ),
    "地址必须是 32 位无符号整数": "Address must be a 32-bit unsigned integer",
    "选择原始数据保存目录": "Choose Raw Data Directory",
    "两态开关：正常写入 0x0，Power Down 写入 0x3。": (
        "Two-state control: write 0x0 for normal, 0x3 for power-down."
    ),
    "勾选后，存盘期间暂停曲线刷新；TCP 接收和原始数据写入继续运行。": (
        "Pause plot redraws during recording; TCP reception and raw writes continue."
    ),
    "；鼠标按下写入 1，抬起写入 0。": (
        "; mouse press writes 1, release writes 0."
    ),
    "；范围 0x0-0x": "; range 0x0-0x",
    "配置加载失败": "Configuration Load Failed",
    "通信日志": "Communication Log",
    "亮色主题": "Light Theme",
    "暗色主题": "Dark Theme",
    "数据端口可配置": "Data port configurable",
    "RBCP UDP 4660  ·  数据端口可配置": (
        "RBCP UDP 4660  ·  Data port configurable"
    ),
    "CFG：待执行": "CFG: Ready",
    "外部触发延迟 (0x0-0xFF)": "External Trigger Delay (0x0-0xFF)",
    "符合触发展宽 (0x0-0xF)": "Coincidence Pulse Width (0x0-0xF)",
    "符合通道 A (0x0-0x7)": "Coincidence Channel A (0x0-0x7)",
    "符合通道 B (0x0-0x7)": "Coincidence Channel B (0x0-0x7)",
}

_EN_TO_ZH = {english: chinese for chinese, english in _ZH_TO_EN.items()}

_DYNAMIC_ZH_TO_EN = (
    (
        re.compile(r"^RBCP UDP (\d+)  ·  数据端口可配置$"),
        r"RBCP UDP \1  ·  Data port configurable",
    ),
    (re.compile(r"^CH(\d+) 触发参数$"), r"CH\1 Trigger Settings"),
    (re.compile(r"^当前：(0x[0-9A-F]+)$"), r"Current: \1"),
    (re.compile(r"^当前模式：(0x[0-9A-F]+)$"), r"Current mode: \1"),
    (
        re.compile(r"^阈值 (.+)  长度 (.+)  偏移 (.+)$"),
        r"Threshold \1  Length \2  Offset \3",
    ),
    (re.compile(r"^通道帧计数：(.*)$"), r"Channel frames: \1"),
    (re.compile(r"^最近触发：(.*)$"), r"Latest trigger: \1"),
    (re.compile(r"^数据端点 (.+)$"), r"Data endpoint \1"),
    (re.compile(r"^正在保存：(.+)$"), r"Recording: \1"),
    (re.compile(r"^已保存：(.+) \(([^,]+), (\d+) 帧\)$"), r"Saved: \1 (\2, \3 frames)"),
    (re.compile(r"^保存异常：(.+) \(([^,]+), (\d+) 帧\)$"), r"Save error: \1 (\2, \3 frames)"),
    (re.compile(r"^存盘错误：(.+)$"), r"Recording error: \1"),
    (re.compile(r"^采集错误：(.+)$"), r"Acquisition error: \1"),
    (re.compile(r"^CFG：(.+)$"), r"CFG: \1"),
    (re.compile(r"^CFG (\d+)/(\d+)：(.+) 完成$"), r"CFG \1/\2: \3 complete"),
    (re.compile(r"^CFG 失败：(.+)，(.+)$"), r"CFG failed at \1: \2"),
    (re.compile(r"^最近更新：(.+)$"), r"Last updated: \1"),
    (re.compile(r"^正在连接 (.+) \.\.\.$"), r"Connecting to \1 ..."),
    (re.compile(r"^已连接 (.+)$"), r"Connected to \1"),
    (re.compile(r"^状态已更新，温度原始值 (.+)$"), r"Status updated; raw temperature \1"),
    (re.compile(r"^已写入 (.+)$"), r"Wrote \1"),
    (re.compile(r"^正在接收 (.+) 数据流$"), r"Receiving data stream from \1"),
    (re.compile(r"^数据流错误：(.+)$"), r"Data stream error: \1"),
    (re.compile(r"^软件触发模式：已自动触发 (\d+) 次$"), r"Software trigger mode: \1 automatic triggers"),
    (re.compile(r"^软件触发失败：(.+)$"), r"Software trigger failed: \1"),
    (re.compile(r"^已保存：(.+)$"), r"Saved: \1"),
    (re.compile(r"^存盘异常：(.+)$"), r"Save error: \1"),
    (re.compile(r"^(.+) 失败：(.+)$"), r"\1 failed: \2"),
    (re.compile(r"^(.+) 失败$"), r"\1 failed"),
)

_DYNAMIC_EN_TO_ZH = (
    (
        re.compile(r"^RBCP UDP (\d+)  ·  Data port configurable$"),
        r"RBCP UDP \1  ·  数据端口可配置",
    ),
    (re.compile(r"^CH(\d+) Trigger Settings$"), r"CH\1 触发参数"),
    (re.compile(r"^Current: (0x[0-9A-F]+)$"), r"当前：\1"),
    (re.compile(r"^Current mode: (0x[0-9A-F]+)$"), r"当前模式：\1"),
    (
        re.compile(r"^Threshold (.+)  Length (.+)  Offset (.+)$"),
        r"阈值 \1  长度 \2  偏移 \3",
    ),
    (re.compile(r"^Channel frames: (.*)$"), r"通道帧计数：\1"),
    (re.compile(r"^Latest trigger: (.*)$"), r"最近触发：\1"),
    (re.compile(r"^Data endpoint (.+)$"), r"数据端点 \1"),
    (re.compile(r"^Recording: (.+)$"), r"正在保存：\1"),
    (re.compile(r"^Saved: (.+) \(([^,]+), (\d+) frames\)$"), r"已保存：\1 (\2, \3 帧)"),
    (re.compile(r"^Save error: (.+) \(([^,]+), (\d+) frames\)$"), r"保存异常：\1 (\2, \3 帧)"),
    (re.compile(r"^Recording error: (.+)$"), r"存盘错误：\1"),
    (re.compile(r"^Acquisition error: (.+)$"), r"采集错误：\1"),
    (re.compile(r"^CFG: (.+)$"), r"CFG：\1"),
    (re.compile(r"^CFG (\d+)/(\d+): (.+) complete$"), r"CFG \1/\2：\3 完成"),
    (re.compile(r"^CFG failed at (.+): (.+)$"), r"CFG 失败：\1，\2"),
    (re.compile(r"^Last updated: (.+)$"), r"最近更新：\1"),
    (re.compile(r"^Connecting to (.+) \.\.\.$"), r"正在连接 \1 ..."),
    (re.compile(r"^Connected to (.+)$"), r"已连接 \1"),
    (re.compile(r"^Status updated; raw temperature (.+)$"), r"状态已更新，温度原始值 \1"),
    (re.compile(r"^Wrote (.+)$"), r"已写入 \1"),
    (re.compile(r"^Receiving data stream from (.+)$"), r"正在接收 \1 数据流"),
    (re.compile(r"^Data stream error: (.+)$"), r"数据流错误：\1"),
    (re.compile(r"^Software trigger mode: (\d+) automatic triggers$"), r"软件触发模式：已自动触发 \1 次"),
    (re.compile(r"^Software trigger failed: (.+)$"), r"软件触发失败：\1"),
    (re.compile(r"^Saved: (.+)$"), r"已保存：\1"),
    (re.compile(r"^Save error: (.+)$"), r"存盘异常：\1"),
    (re.compile(r"^(.+) failed: (.+)$"), r"\1 失败：\2"),
    (re.compile(r"^(.+) failed$"), r"\1 失败"),
)


def set_language(language: str) -> None:
    global _language
    _language = "en" if language == "en" else "zh"


def language() -> str:
    return _language


def tx(text: str) -> str:
    if _language == "en":
        if text in _ZH_TO_EN:
            return _ZH_TO_EN[text]
        for pattern, replacement in _DYNAMIC_ZH_TO_EN:
            if pattern.fullmatch(text):
                return pattern.sub(replacement, text)
        return text

    if text in _EN_TO_ZH:
        return _EN_TO_ZH[text]
    for pattern, replacement in _DYNAMIC_EN_TO_ZH:
        if pattern.fullmatch(text):
            return pattern.sub(replacement, text)
    return text


def _tx_tooltip(text: str) -> str:
    source_map = _ZH_TO_EN if _language == "en" else _EN_TO_ZH
    result = text
    for source, target in sorted(
        source_map.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        result = result.replace(source, target)
    return result


def translate_widget_tree(root: QWidget) -> None:
    for widget in root.findChildren(QWidget):
        if widget.objectName() == "LanguageSelector":
            continue
        if isinstance(widget, (QLabel, QAbstractButton)):
            text = widget.text()
            translated = tx(text)
            if translated != text:
                widget.setText(translated)
        elif isinstance(widget, QLineEdit):
            placeholder = widget.placeholderText()
            translated = tx(placeholder)
            if translated != placeholder:
                widget.setPlaceholderText(translated)
        elif isinstance(widget, QComboBox):
            for index in range(widget.count()):
                text = widget.itemText(index)
                translated = tx(text)
                if translated != text:
                    widget.setItemText(index, translated)
        tooltip = widget.toolTip()
        translated = _tx_tooltip(tooltip)
        if translated != tooltip:
            widget.setToolTip(translated)

    for tabs in root.findChildren(QTabWidget):
        for index in range(tabs.count()):
            text = tabs.tabText(index)
            translated = tx(text)
            if translated != text:
                tabs.setTabText(index, translated)
    for dock in root.findChildren(QDockWidget):
        title = dock.windowTitle()
        translated = tx(title)
        if translated != title:
            dock.setWindowTitle(translated)

