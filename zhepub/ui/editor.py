"""代码编辑器：行号、当前行高亮、XHTML/CSS 语法高亮。"""

from __future__ import annotations

import re

from PyQt6.QtCore import QRect, QRegularExpression, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PyQt6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from .themes import DEFAULT_THEME, editor_palette, syntax_palette

_ASTRAL_RE = re.compile("[\U00010000-\U0010ffff]")


def py_to_qt(text: str, index: int) -> int:
    """Python 字符串下标 -> Qt 文本位置（UTF-16 单元）。"""
    head = text[:index]
    return index + len(_ASTRAL_RE.findall(head))


def qt_to_py(text: str, pos: int) -> int:
    """Qt 文本位置（UTF-16 单元）-> Python 字符串下标。"""
    if not _ASTRAL_RE.search(text):
        return pos
    units = 0
    for i, ch in enumerate(text):
        if units >= pos:
            return i
        units += 2 if ord(ch) > 0xFFFF else 1
    return len(text)


def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    f.setFontItalic(italic)
    return f


def _build_formats(syntax: dict) -> dict:
    """根据 syntax palette 构建全部 QTextCharFormat。"""
    return {
        "tag": _fmt(syntax["tag"], bold=True),
        "attr": _fmt(syntax["attr"]),
        "value": _fmt(syntax["value"]),
        "entity": _fmt(syntax["entity"]),
        "special": _fmt(syntax["special"]),
        "comment": _fmt(syntax["comment"], italic=True),
    }


# CSS 规则定义：(regex, group, format_key)，主题切换时用新 format 重建 RULES。
_CSS_RULE_DEFS = [
    (QRegularExpression(r"^[^{}:;]+(?=\{)|^[^{}:;]+,\s*$"), 0, "tag"),
    (QRegularExpression(r"([\w-]+)\s*:(?!\w)"), 1, "attr"),
    (QRegularExpression(r"@[\w-]+"), 0, "entity"),
    (QRegularExpression(r"#[0-9a-fA-F]{3,8}\b|\b\d+(\.\d+)?(px|em|rem|pt|%|ex|vh|vw)?\b"),
     0, "entity"),
    (QRegularExpression(r"\"[^\"]*\"|'[^']*'"), 0, "value"),
]


def apply_theme(name: str) -> None:
    """把主题应用到所有高亮器类的格式属性。

    现有编辑器实例需调用 ``CodeEditor.apply_theme`` 触发重高亮与重绘。
    """
    fmts = _build_formats(syntax_palette(name))
    _Highlighter.comment_format = fmts["comment"]
    XhtmlHighlighter.tag_format = fmts["tag"]
    XhtmlHighlighter.attr_format = fmts["attr"]
    XhtmlHighlighter.value_format = fmts["value"]
    XhtmlHighlighter.entity_format = fmts["entity"]
    XhtmlHighlighter.special_format = fmts["special"]
    CssHighlighter.RULES = [
        (regex, fmts[key], group) for (regex, group, key) in _CSS_RULE_DEFS
    ]


class _Highlighter(QSyntaxHighlighter):
    COMMENT_START = QRegularExpression("")
    COMMENT_END = QRegularExpression("")
    comment_format = _fmt("#8a8a8a", italic=True)  # 初始占位，apply_theme 后会被覆盖

    def rules(self, text: str) -> None:  # pragma: no cover - 子类实现
        raise NotImplementedError

    def apply(self, regex: QRegularExpression, text: str, fmt: QTextCharFormat, group: int = 0):
        it = regex.globalMatch(text)
        while it.hasNext():
            m = it.next()
            self.setFormat(m.capturedStart(group), m.capturedLength(group), fmt)

    def highlightBlock(self, text: str) -> None:
        self.rules(text)
        # 跨行注释
        self.setCurrentBlockState(0)
        start = 0
        if self.previousBlockState() != 1:
            m = self.COMMENT_START.match(text)
            start = m.capturedStart() if m.hasMatch() else -1
        while start >= 0:
            end_m = self.COMMENT_END.match(text, start + 2)
            if end_m.hasMatch():
                length = end_m.capturedEnd() - start
            else:
                self.setCurrentBlockState(1)
                length = len(text) - start
            self.setFormat(start, length, self.comment_format)
            m = self.COMMENT_START.match(text, start + length)
            start = m.capturedStart() if m.hasMatch() else -1


class XhtmlHighlighter(_Highlighter):
    COMMENT_START = QRegularExpression("<!--")
    COMMENT_END = QRegularExpression("-->")
    TAG_RE = QRegularExpression(r"<[^>]*>?|^[^<]*>")
    NAME_RE = QRegularExpression(r"</?[A-Za-z][\w:.-]*|/?>")
    ATTR_RE = QRegularExpression(r"\s([A-Za-z_:][\w:.-]*)\s*=")
    VALUE_RE = QRegularExpression(r"=\s*(\"[^\"]*\"?|'[^']*'?)")
    ENTITY_RE = QRegularExpression(r"&[#\w]+;")
    SPECIAL_RE = QRegularExpression(r"<[?!][^>]*>")

    # 颜色在 apply_theme() 时按当前主题填充
    tag_format = _fmt("#1d4ed8", bold=True)
    attr_format = _fmt("#9333ea")
    value_format = _fmt("#15803d")
    entity_format = _fmt("#c2410c")
    special_format = _fmt("#6b7280")

    def rules(self, text: str) -> None:
        it = self.TAG_RE.globalMatch(text)
        while it.hasNext():
            m = it.next()
            tag = m.captured(0)
            base = m.capturedStart()
            for regex, fmt, group in (
                (self.NAME_RE, self.tag_format, 0),
                (self.ATTR_RE, self.attr_format, 1),
                (self.VALUE_RE, self.value_format, 1),
            ):
                sub = regex.globalMatch(tag)
                while sub.hasNext():
                    s = sub.next()
                    self.setFormat(base + s.capturedStart(group), s.capturedLength(group), fmt)
        self.apply(self.ENTITY_RE, text, self.entity_format)
        self.apply(self.SPECIAL_RE, text, self.special_format)


class CssHighlighter(_Highlighter):
    COMMENT_START = QRegularExpression(r"/\*")
    COMMENT_END = QRegularExpression(r"\*/")
    # apply_theme() 会按主题重建此列表
    RULES: list = []

    def rules(self, text: str) -> None:
        for regex, fmt, group in self.RULES:
            self.apply(regex, text, fmt, group)


# 模块加载时按默认主题填充高亮器配色
apply_theme(DEFAULT_THEME)


class _LineNumberArea(QWidget):
    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_width(), 0)

    def paintEvent(self, event) -> None:
        self.editor.paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self, resource, text: str, parent=None):
        super().__init__(parent)
        self.resource = resource
        self._theme_name = DEFAULT_THEME
        pal = editor_palette(DEFAULT_THEME)
        self._line_number_bg = pal["line_number_bg"]
        self._line_number_fg = pal["line_number_fg"]
        self._current_line_bg = pal["current_line_bg"]
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setFamilies([font.family(), "Consolas", "Microsoft YaHei UI", "PingFang SC",
                          "Noto Sans Mono CJK SC"])
        font.setPointSize(11)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 2)
        self._numbers = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_margin)
        self.updateRequest.connect(self._update_numbers)
        self.cursorPositionChanged.connect(self._highlight_line)
        if resource.category == "style":
            self.highlighter = CssHighlighter(self.document())
        else:
            self.highlighter = XhtmlHighlighter(self.document())
        self.setPlainText(text)
        self.document().setModified(False)
        self._update_margin()
        self._highlight_line()

    # ---------------------------------------------------------------- 主题
    def apply_theme(self, name: str) -> None:
        """切换本编辑器配色：行号区、当前行高亮；并触发高亮器重高亮。"""
        self._theme_name = name
        pal = editor_palette(name)
        self._line_number_bg = pal["line_number_bg"]
        self._line_number_fg = pal["line_number_fg"]
        self._current_line_bg = pal["current_line_bg"]
        self.highlighter.rehighlight()
        self._numbers.update()
        self._highlight_line()

    # ---------------------------------------------------------------- 行号
    def line_number_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_margin(self, *_):
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _update_numbers(self, rect, dy):
        if dy:
            self._numbers.scroll(0, dy)
        else:
            self._numbers.update(0, rect.y(), self._numbers.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_margin()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._numbers.setGeometry(QRect(cr.left(), cr.top(), self.line_number_width(), cr.height()))

    def paint_line_numbers(self, event) -> None:
        painter = QPainter(self._numbers)
        painter.fillRect(event.rect(), QColor(self._line_number_bg))
        painter.setPen(QColor(self._line_number_fg))
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        width = self._numbers.width() - 6
        height = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(0, top, width, height, Qt.AlignmentFlag.AlignRight, str(number + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            number += 1

    def _highlight_line(self) -> None:
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(QColor(self._current_line_bg))
        sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        sel.cursor = self.textCursor()
        sel.cursor.clearSelection()
        self.setExtraSelections([sel])

    # ---------------------------------------------------------------- 编辑辅助
    def keyPressEvent(self, event) -> None:
        # 回车时保持上一行的缩进
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers():
            line = self.textCursor().block().text()
            indent = line[: len(line) - len(line.lstrip(" \t"))]
            super().keyPressEvent(event)
            if indent:
                self.insertPlainText(indent)
            return
        super().keyPressEvent(event)

    def goto_line(self, line: int) -> None:
        block = self.document().findBlockByNumber(max(line, 1) - 1)
        if block.isValid():
            self.setTextCursor(QTextCursor(block))
            self.centerCursor()
        self.setFocus()

    def py_position(self) -> int:
        return qt_to_py(self.toPlainText(), self.textCursor().position())

    def select_py_range(self, start: int, end: int) -> None:
        text = self.toPlainText()
        cursor = self.textCursor()
        cursor.setPosition(py_to_qt(text, start))
        cursor.setPosition(py_to_qt(text, end), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)
        self.centerCursor()

    def selected_py_range(self) -> tuple[int, int]:
        text = self.toPlainText()
        c = self.textCursor()
        return qt_to_py(text, c.selectionStart()), qt_to_py(text, c.selectionEnd())

    def replace_text(self, text: str) -> None:
        """替换全部内容，但保留撤销记录、光标和滚动位置。"""
        if text == self.toPlainText():
            return
        pos = self.textCursor().position()
        scroll = self.verticalScrollBar().value()
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(text)
        cursor.endEditBlock()
        cursor = self.textCursor()
        cursor.setPosition(min(pos, len(self.toPlainText())))
        self.setTextCursor(cursor)
        self.verticalScrollBar().setValue(scroll)
