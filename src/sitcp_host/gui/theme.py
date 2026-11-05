"""Application-wide dark and light Qt themes."""

from __future__ import annotations

from string import Template

DARK_PALETTE = {
    "root": "#0C131B",
    "card": "#151F2B",
    "border": "#253446",
    "title": "#F7FAFC",
    "text": "#E8EEF5",
    "muted": "#8FA4BA",
    "detail": "#7D93A9",
    "online": "#46D39A",
    "offline": "#FF8A8A",
    "busy": "#F5C451",
    "input": "#0E1721",
    "input_border": "#2B3C50",
    "focus": "#398BFF",
    "button": "#1A2838",
    "button_hover": "#22354A",
    "button_pressed": "#142333",
    "button_border": "#30445B",
    "disabled_text": "#61758A",
    "disabled_bg": "#121C27",
    "disabled_border": "#202E3E",
    "tab_pane": "#111A24",
    "table_alt": "#141F2B",
    "grid": "#223143",
    "header": "#182535",
    "header_text": "#AFC0D2",
    "log": "#0A1118",
    "scrollbar": "#2B3D51",
}

LIGHT_PALETTE = {
    "root": "#F2F5F9",
    "card": "#FFFFFF",
    "border": "#D7E0EA",
    "title": "#14202B",
    "text": "#1D2935",
    "muted": "#647587",
    "detail": "#596B7D",
    "online": "#087A50",
    "offline": "#C52B3D",
    "busy": "#A56700",
    "input": "#FFFFFF",
    "input_border": "#C7D2DF",
    "focus": "#2274D4",
    "button": "#F7F9FC",
    "button_hover": "#EAF1F8",
    "button_pressed": "#DDE8F3",
    "button_border": "#C5D2E0",
    "disabled_text": "#8795A4",
    "disabled_bg": "#F2F5F8",
    "disabled_border": "#DFE5EC",
    "tab_pane": "#FFFFFF",
    "table_alt": "#F8FAFC",
    "grid": "#E1E7EF",
    "header": "#EAF0F6",
    "header_text": "#3F5062",
    "log": "#FFFFFF",
    "scrollbar": "#C4CFDB",
}

_STYLE_TEMPLATE = Template(
    """
QWidget {
    color: $text;
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}
QWidget#Root {
    background: $root;
}
QFrame#Card {
    background: $card;
    border: 1px solid $border;
    border-radius: 10px;
}
QLabel#Title {
    color: $title;
    font-size: 26px;
    font-weight: 700;
}
QLabel#Subtitle, QLabel#Muted {
    color: $muted;
}
QLabel#SectionTitle {
    color: $title;
    font-size: 16px;
    font-weight: 600;
}
QLabel#MetricValue {
    color: $title;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 24px;
    font-weight: 700;
}
QLabel#MetricDetail {
    color: $detail;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 11px;
}
QLabel#StateOnline {
    color: $online;
    font-weight: 600;
}
QLabel#StateOffline {
    color: $offline;
    font-weight: 600;
}
QLabel#StateBusy {
    color: $busy;
    font-weight: 600;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: $input;
    color: $text;
    border: 1px solid $input_border;
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: #2D7FF9;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: $focus;
}
QComboBox::drop-down {
    width: 22px;
    border: 0;
}
QComboBox QAbstractItemView {
    background: $input;
    color: $text;
    border: 1px solid $input_border;
    selection-background-color: #2D7FF9;
    selection-color: #FFFFFF;
    outline: 0;
}
QPushButton {
    background: $button;
    color: $text;
    border: 1px solid $button_border;
    border-radius: 6px;
    padding: 6px 12px;
}
QPushButton:hover {
    background: $button_hover;
    border-color: $focus;
}
QPushButton:pressed {
    background: $button_pressed;
}
QPushButton:checked {
    background: #2176E8;
    border-color: #58A6FF;
    color: #FFFFFF;
    font-weight: 600;
}
QPushButton:checked:hover {
    background: #3285F3;
    border-color: #7ABAFF;
}
QPushButton:disabled {
    color: $disabled_text;
    background: $disabled_bg;
    border-color: $disabled_border;
}
QPushButton#Primary {
    background: #2176E8;
    border-color: #2176E8;
    color: #FFFFFF;
    font-weight: 600;
}
QPushButton#Primary:hover {
    background: #3285F3;
    border-color: #3285F3;
}
QPushButton#Danger {
    color: $offline;
    border-color: $offline;
}
QTabWidget::pane {
    border: 1px solid $border;
    border-radius: 8px;
    background: $tab_pane;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: $muted;
    padding: 9px 18px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    color: $title;
    border-bottom: 2px solid $focus;
}
QTableWidget {
    background: $tab_pane;
    alternate-background-color: $table_alt;
    border: 0;
    gridline-color: $grid;
    selection-background-color: #2D7FF9;
}
QHeaderView::section {
    background: $header;
    color: $header_text;
    border: 0;
    border-bottom: 1px solid $border;
    padding: 7px;
    font-weight: 600;
}
QPlainTextEdit {
    background: $log;
    color: $text;
    border: 1px solid $border;
    border-radius: 6px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 11px;
    padding: 6px;
}
QCheckBox {
    color: $text;
    spacing: 7px;
}
QStatusBar {
    background: $log;
    color: $muted;
}
QDockWidget {
    color: $muted;
}
QDockWidget::title {
    background: $tab_pane;
    padding: 7px;
    border-bottom: 1px solid $border;
}
QScrollArea, QScrollArea > QWidget > QWidget {
    background: transparent;
}
QScrollBar:vertical {
    background: $input;
    width: 10px;
}
QScrollBar::handle:vertical {
    background: $scrollbar;
    border-radius: 4px;
    min-height: 24px;
}
QToolTip {
    background: $card;
    color: $text;
    border: 1px solid $border;
    padding: 5px;
}
"""
)

DARK_STYLE = _STYLE_TEMPLATE.substitute(DARK_PALETTE)
LIGHT_STYLE = _STYLE_TEMPLATE.substitute(LIGHT_PALETTE)
APP_STYLE = DARK_STYLE


def style_for_theme(theme: str) -> str:
    return LIGHT_STYLE if theme == "light" else DARK_STYLE


def chart_palette(theme: str) -> dict[str, object]:
    if theme == "light":
        return {
            "background": "#FFFFFF",
            "axis": "#536577",
            "grid": "#E2E8F0",
            "channels": (
                "#1F6FD0",
                "#C77800",
                "#138A55",
                "#CC3550",
                "#7650C7",
                "#0C8790",
                "#8A7400",
                "#9A43B8",
            ),
        }
    return {
        "background": "#111A24",
        "axis": "#7D93A9",
        "grid": "#223143",
        "channels": (
            "#4DA3FF",
            "#FFB454",
            "#51D88A",
            "#FF6B81",
            "#B48CFF",
            "#4ED5DB",
            "#E6D45B",
            "#E58BFF",
        ),
    }
