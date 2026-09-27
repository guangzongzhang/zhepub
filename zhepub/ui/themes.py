"""界面主题：深色 / 浅色 / 护眼三套配色，包含 QSS 与编辑器配色。

每个主题包含三块配色：
1. ``qss`` —— 应用到 QApplication 的全局样式表（菜单、dock、状态栏等）
2. ``editor`` —— 编辑器本地配色：行号区背景/前景、当前行高亮背景
3. ``syntax`` —— 语法高亮配色：tag / attr / value / entity / special / comment
"""

from __future__ import annotations

# 全局 QSS 模板：占位符 ${bg} / ${fg} / ${alt} / ${accent} / ${border} / ${disabled}
# 由每个主题替换。Fusion 风格下用 QSS 覆盖关键控件颜色。
# 不用 str.format()，避免 QSS 自带的 { } 冲突。
_QSS_TEMPLATE = """
QWidget {
    background-color: ${bg};
    color: ${fg};
}
QMenuBar, QMenuBar::item {
    background: ${bg};
    color: ${fg};
}
QMenuBar::item:selected { background: ${alt}; }
QMenu, QMenu::item {
    background: ${bg};
    color: ${fg};
}
QMenu::item:selected, QMenu::item:disabled { background: ${alt}; }
QMenu::separator { height: 1px; background: ${border}; }
QToolBar {
    background: ${bg};
    border: none;
    spacing: 2px;
}
QStatusBar { background: ${bg}; color: ${fg}; }
QDockWidget::title {
    background: ${alt};
    color: ${fg};
    padding: 2px 6px;
    border: none;
}
QTreeWidget, QTreeWidget::item {
    background: ${bg};
    color: ${fg};
    border: 1px solid ${border};
}
QTreeWidget::item:selected { background: ${accent}; color: ${fg}; }
QTabWidget::pane { border: 1px solid ${border}; }
QTabBar::tab {
    background: ${bg};
    color: ${fg};
    padding: 4px 10px;
    border: 1px solid ${border};
}
QTabBar::tab:selected { background: ${alt}; }
QPlainTextEdit, QTextEdit, QTextBrowser {
    background: ${editor_bg};
    color: ${fg};
    border: 1px solid ${border};
    selection-background-color: ${accent};
}
QPushButton {
    background: ${alt};
    color: ${fg};
    border: 1px solid ${border};
    padding: 4px 12px;
}
QPushButton:hover { background: ${accent}; }
QPushButton:disabled { color: ${disabled}; }
QInputDialog QLineEdit, QLineEdit {
    background: ${editor_bg};
    color: ${fg};
    border: 1px solid ${border};
    selection-background-color: ${accent};
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: ${bg};
    border: none;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: ${alt};
    border-radius: 3px;
    min-height: 20px;
    min-width: 20px;
}
QScrollBar::handle:hover { background: ${accent}; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QHeaderView::section { background: ${alt}; color: ${fg}; }
QMessageBox, QDialog { background: ${bg}; color: ${fg}; }
QListWidget, QListWidget::item { background: ${bg}; color: ${fg}; }
QListWidget::item:selected { background: ${accent}; }
QSplitter::handle { background: ${border}; }
QSplitter::handle:hover { background: ${accent}; }
"""

THEMES = {
    "light": {
        "qss_vars": {
            "bg": "#ffffff",
            "fg": "#1f2937",
            "alt": "#f3f4f6",
            "accent": "#dbeafe",
            "border": "#e5e7eb",
            "disabled": "#9ca3af",
            "editor_bg": "#ffffff",
        },
        "editor": {
            "line_number_bg": "#f3f4f6",
            "line_number_fg": "#9ca3af",
            "current_line_bg": "#fef9c3",
        },
        "syntax": {
            "tag": "#1d4ed8",
            "attr": "#9333ea",
            "value": "#15803d",
            "entity": "#c2410c",
            "special": "#6b7280",
            "comment": "#8a8a8a",
        },
    },
    "dark": {
        "qss_vars": {
            "bg": "#1e1e2e",
            "fg": "#cdd6f4",
            "alt": "#313244",
            "accent": "#45475a",
            "border": "#45475a",
            "disabled": "#6c7086",
            "editor_bg": "#11111b",
        },
        "editor": {
            "line_number_bg": "#181825",
            "line_number_fg": "#6c7086",
            "current_line_bg": "#3a2e00",
        },
        "syntax": {
            "tag": "#89b4fa",
            "attr": "#cba6f7",
            "value": "#a6e3a1",
            "entity": "#fab387",
            "special": "#7f849c",
            "comment": "#6c7086",
        },
    },
    "eye": {
        "qss_vars": {
            "bg": "#f5ecd9",
            "fg": "#3d3324",
            "alt": "#e8d9b6",
            "accent": "#d4b896",
            "border": "#cdb88a",
            "disabled": "#9a8c66",
            "editor_bg": "#fbf3e0",
        },
        "editor": {
            "line_number_bg": "#ede0c2",
            "line_number_fg": "#8c7a55",
            "current_line_bg": "#f0e2bf",
        },
        "syntax": {
            "tag": "#1e5b8c",
            "attr": "#8a4f8a",
            "value": "#2d6e3e",
            "entity": "#a8551e",
            "special": "#6a5d3a",
            "comment": "#9a8c66",
        },
    },
}

DEFAULT_THEME = "light"


def render_qss(theme_name: str) -> str:
    """根据主题名生成 QSS。"""
    spec = THEMES.get(theme_name) or THEMES[DEFAULT_THEME]
    qss = _QSS_TEMPLATE
    for key, value in spec["qss_vars"].items():
        qss = qss.replace("${" + key + "}", value)
    return qss


def editor_palette(theme_name: str) -> dict:
    """返回编辑器本地配色（行号区、当前行高亮）。"""
    spec = THEMES.get(theme_name) or THEMES[DEFAULT_THEME]
    return spec["editor"]


def syntax_palette(theme_name: str) -> dict:
    """返回语法高亮配色。"""
    spec = THEMES.get(theme_name) or THEMES[DEFAULT_THEME]
    return spec["syntax"]


def list_themes() -> list[str]:
    return list(THEMES.keys())
