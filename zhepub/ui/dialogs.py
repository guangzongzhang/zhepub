"""对话框：查找替换、元数据、插入图片、导入 TXT、
语法帮助、AI 查询、AI 设置。"""

from __future__ import annotations

import re

from PyQt6.QtCore import QByteArray, QSettings, QSize, Qt, QThread
from PyQt6.QtGui import QFont, QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..ai import AI_PROVIDERS, DEFAULT_PROVIDER, AIWorker, make_worker, resolve_config
from ..xhtml_css_help import get_reference
from ..xhtml_tools import CHAPTER_PATTERN, split_txt_chapters

SCOPES = [
    ("current", "当前文件"),
    ("text", "所有 HTML 文件"),
    ("style", "所有 CSS 文件"),
    ("all", "所有文本文件"),
]


class FindReplaceDialog(QDialog):
    """非模态的查找替换窗口，具体查找逻辑由主窗口完成。"""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("查找与替换")
        self.find_edit = QComboBox(editable=True)
        self.replace_edit = QComboBox(editable=True)
        for combo in (self.find_edit, self.replace_edit):
            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            combo.setMinimumWidth(360)
        self.regex_box = QCheckBox("正则表达式")
        self.case_box = QCheckBox("区分大小写")
        self.dotall_box = QCheckBox(". 匹配换行")
        self.scope_box = QComboBox()
        for key, label in SCOPES:
            self.scope_box.addItem(label, key)
        self.status = QLabel()
        self.status.setStyleSheet("color: #555")

        grid = QGridLayout(self)
        grid.addWidget(QLabel("查找："), 0, 0)
        grid.addWidget(self.find_edit, 0, 1, 1, 3)
        grid.addWidget(QLabel("替换为："), 1, 0)
        grid.addWidget(self.replace_edit, 1, 1, 1, 3)
        grid.addWidget(QLabel("范围："), 2, 0)
        grid.addWidget(self.scope_box, 2, 1)
        options = QHBoxLayout()
        for w in (self.regex_box, self.case_box, self.dotall_box):
            options.addWidget(w)
        grid.addLayout(options, 2, 2, 1, 2)
        buttons = QHBoxLayout()
        for text, slot in (
            ("查找下一个", self.find_next),
            ("查找上一个", self.find_previous),
            ("替换", self.replace),
            ("全部替换", self.replace_all),
            ("计数", self.count),
        ):
            b = QPushButton(text)
            b.clicked.connect(slot)
            b.setAutoDefault(False)
            buttons.addWidget(b)
        buttons.itemAt(0).widget().setDefault(True)
        grid.addLayout(buttons, 3, 0, 1, 4)
        grid.addWidget(self.status, 4, 0, 1, 4)

    def set_find_text(self, text: str) -> None:
        if text and "\n" not in text:
            self.find_edit.setCurrentText(text)
        self.find_edit.lineEdit().selectAll()
        self.find_edit.setFocus()

    def _remember(self, combo: QComboBox) -> None:
        text = combo.currentText()
        if text and combo.findText(text) < 0:
            combo.insertItem(0, text)
        combo.setCurrentText(text)

    def pattern(self) -> re.Pattern | None:
        text = self.find_edit.currentText()
        if not text:
            self.status.setText("请输入要查找的内容。")
            return None
        self._remember(self.find_edit)
        flags = re.M
        if not self.case_box.isChecked():
            flags |= re.I
        if self.dotall_box.isChecked():
            flags |= re.S
        try:
            return re.compile(text if self.regex_box.isChecked() else re.escape(text), flags)
        except re.error as e:
            self.status.setText(f"正则表达式错误：{e}")
            return None

    def replacement(self, match: re.Match) -> str:
        repl = self.replace_edit.currentText()
        if not self.regex_box.isChecked():
            return repl
        return match.expand(repl)

    def scope(self) -> str:
        return self.scope_box.currentData()

    def find_next(self) -> None:
        if (p := self.pattern()) is not None:
            self.status.setText(self.window.find(p, self.scope(), backwards=False))

    def find_previous(self) -> None:
        if (p := self.pattern()) is not None:
            self.status.setText(self.window.find(p, self.scope(), backwards=True))

    def replace(self) -> None:
        if (p := self.pattern()) is not None:
            self._remember(self.replace_edit)
            try:
                self.status.setText(self.window.replace_current(p, self.replacement, self.scope()))
            except (re.error, IndexError) as e:
                self.status.setText(f"替换内容有误：{e}")

    def replace_all(self) -> None:
        if (p := self.pattern()) is not None:
            self._remember(self.replace_edit)
            try:
                self.status.setText(self.window.replace_all(p, self.replacement, self.scope()))
            except (re.error, IndexError) as e:
                self.status.setText(f"替换内容有误：{e}")

    def count(self) -> None:
        if (p := self.pattern()) is not None:
            self.status.setText(self.window.count_matches(p, self.scope()))


class MetadataDialog(QDialog):
    LANGUAGES = ["zh-CN", "zh-TW", "zh-HK", "zh", "en", "ja", "ko"]

    def __init__(self, book, parent=None):
        super().__init__(parent)
        self.book = book
        self.setWindowTitle("元数据")
        self.setMinimumWidth(520)
        form = QFormLayout(self)
        self.title = QLineEdit(book.title)
        self.creators = QLineEdit("；".join(book.get_dc("creator")))
        self.creators.setPlaceholderText("多位作者用分号分隔")
        self.language = QComboBox(editable=True)
        self.language.addItems(self.LANGUAGES)
        self.language.setCurrentText(book.language or "zh-CN")
        self.identifier = QLineEdit(book.identifier)
        self.publisher = QLineEdit(book.get_first("publisher"))
        self.date = QLineEdit(book.get_first("date"))
        self.date.setPlaceholderText("如 2026 或 2026-09-27")
        self.subjects = QLineEdit("；".join(book.get_dc("subject")))
        self.subjects.setPlaceholderText("多个主题用分号分隔")
        self.rights = QLineEdit(book.get_first("rights"))
        self.description = QPlainTextEdit(book.get_first("description"))
        self.description.setFixedHeight(100)
        self.cover = QComboBox()
        self.cover.addItem("（无）", None)
        for res in book.by_category("image"):
            self.cover.addItem(res.href, res.href)
        current = book.cover_href()
        if current:
            self.cover.setCurrentIndex(max(self.cover.findData(current), 0))

        form.addRow("书名：", self.title)
        form.addRow("作者：", self.creators)
        form.addRow("语言：", self.language)
        form.addRow("标识符：", self.identifier)
        form.addRow("出版社：", self.publisher)
        form.addRow("出版日期：", self.date)
        form.addRow("主题：", self.subjects)
        form.addRow("版权：", self.rights)
        form.addRow("简介：", self.description)
        form.addRow("封面图片：", self.cover)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    @staticmethod
    def _split(text: str) -> list[str]:
        return [p.strip() for p in re.split(r"[;；]", text) if p.strip()]

    def _accept(self) -> None:
        if not self.title.text().strip():
            self.title.setFocus()
            self.title.setPlaceholderText("书名不能为空")
            return
        b = self.book
        b.set_dc("title", [self.title.text()])
        b.set_dc("creator", self._split(self.creators.text()))
        b.set_dc("language", [self.language.currentText()])
        if self.identifier.text().strip():
            b.set_dc("identifier", [self.identifier.text()])
        b.set_dc("publisher", [self.publisher.text()])
        b.set_dc("date", [self.date.text()])
        b.set_dc("subject", self._split(self.subjects.text()))
        b.set_dc("rights", [self.rights.text()])
        b.set_dc("description", [self.description.toPlainText()])
        cover = self.cover.currentData()
        if cover and cover != b.cover_href():
            b.set_cover(cover)
        b.modified = True
        self.accept()


class InsertImageDialog(QDialog):
    def __init__(self, book, parent=None, add_callback=None):
        super().__init__(parent)
        self.book = book
        self.add_callback = add_callback
        self.setWindowTitle("插入图片")
        self.resize(640, 460)
        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setIconSize(QSize(120, 120))
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setSpacing(8)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        self.alt = QLineEdit()
        self.alt.setPlaceholderText("替代文字（alt），可留空")
        add = QPushButton("从电脑添加图片…")
        add.clicked.connect(self._add)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.list)
        row = QHBoxLayout()
        row.addWidget(self.alt, 1)
        row.addWidget(add)
        layout.addLayout(row)
        layout.addWidget(buttons)
        self._fill()

    def _fill(self, select: str | None = None) -> None:
        self.list.clear()
        for res in self.book.by_category("image"):
            image = QImage.fromData(QByteArray(res.data))
            icon = QIcon(QPixmap.fromImage(image.scaled(
                120, 120, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))) if not image.isNull() else QIcon()
            item = QListWidgetItem(icon, res.filename)
            item.setData(Qt.ItemDataRole.UserRole, res.href)
            self.list.addItem(item)
            if res.href == select or self.list.currentItem() is None:
                self.list.setCurrentItem(item)

    def _add(self) -> None:
        if self.add_callback:
            added = self.add_callback()
            if added:
                self._fill(added[-1])

    def selected_href(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None


class TxtImportDialog(QDialog):
    def __init__(self, text: str, title: str, parent=None):
        super().__init__(parent)
        self.text = text
        self.setWindowTitle("导入 TXT")
        self.setMinimumWidth(560)
        self.title = QLineEdit(title)
        self.pattern = QLineEdit(CHAPTER_PATTERN)
        self.pattern.textChanged.connect(self._update)
        self.info = QPlainTextEdit()
        self.info.setReadOnly(True)
        self.info.setFixedHeight(180)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        form = QFormLayout(self)
        form.addRow("书名：", self.title)
        form.addRow("章节标题（正则）：", self.pattern)
        form.addRow("识别结果：", self.info)
        form.addRow(buttons)
        self._update()

    def _update(self) -> None:
        try:
            chapters = split_txt_chapters(self.text, self.pattern.text())
        except re.error as e:
            self.info.setPlainText(f"正则表达式错误：{e}")
            self.ok.setEnabled(False)
            return
        self.ok.setEnabled(True)
        titles = [t or "（开头无标题部分）" for t, _ in chapters]
        head = f"共识别 {len(chapters)} 个章节：\n"
        self.info.setPlainText(head + "\n".join(titles[:200]) + ("\n…" if len(titles) > 200 else ""))


# ============================================================ 语法帮助
class SyntaxHelpDialog(QDialog):
    """可搜索的 XHTML/CSS 语法查询窗口（非模态）。"""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.settings = QSettings("zhepub", "zhepub")
        title = "XHTML 语法详解" if kind == "xhtml" else "CSS 语法详解"
        self.setWindowTitle(title)
        self.resize(900, 600)

        self.search = QLineEdit()
        self.search.setPlaceholderText("输入关键字实时筛选，留空显示全部…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.itemActivated.connect(self._show_item)
        self.tree.itemClicked.connect(self._show_item)

        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(False)

        splitter = QSplitter()
        splitter.addWidget(self.tree)
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        close_btn.setDefault(True)

        top = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("搜索："))
        bar.addWidget(self.search, 1)
        top.addLayout(bar)
        top.addWidget(splitter, 1)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close_btn)
        top.addLayout(bottom)

        self._load()
        # 恢复窗口尺寸
        geom = self.settings.value(f"help_{kind}_geometry")
        if geom is not None:
            self.restoreGeometry(geom)
        splitter_state = self.settings.value(f"help_{kind}_splitter")
        if splitter_state is not None:
            splitter.restoreState(splitter_state)
        self._splitter = splitter

    def _load(self) -> None:
        self.tree.clear()
        self.reference = get_reference(self.kind)
        for category, items in self.reference.items():
            top = QTreeWidgetItem(self.tree, [category])
            top.setData(0, Qt.ItemDataRole.UserRole, None)
            for entry in items:
                child = QTreeWidgetItem(top, [entry["name"]])
                child.setData(0, Qt.ItemDataRole.UserRole, entry)
                child.setToolTip(0, entry.get("desc", ""))
            top.setExpanded(True)

    def _filter(self, text: str) -> None:
        text = text.strip().lower()
        it = self.tree.invisibleRootItem()
        for i in range(it.childCount()):
            cat = it.child(i)
            visible_in_cat = 0
            for j in range(cat.childCount()):
                child = cat.child(j)
                entry = child.data(0, Qt.ItemDataRole.UserRole) or {}
                name = (entry.get("name") or "").lower()
                desc = (entry.get("desc") or "").lower()
                match = not text or text in name or text in desc
                child.setHidden(not match)
                if match:
                    visible_in_cat += 1
            cat.setHidden(visible_in_cat == 0)
            cat.setExpanded(bool(text) and visible_in_cat > 0)

    def _show_item(self, item: QTreeWidgetItem) -> None:
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if not entry:
            return
        example = entry.get("example", "")
        # 转义并保留缩进
        esc = (example.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        html = (
            f"<h3>{entry['name']}</h3>"
            f"<p>{entry.get('desc', '')}</p>"
            f"<p><b>示例：</b></p>"
            f'<pre style="background:#f5f5f5; padding:8px; border:1px solid #ddd;'
            f' font-family: Consolas, \'Courier New\', monospace; white-space: pre-wrap;'
            f' word-wrap: break-word;">{esc}</pre>'
        )
        self.detail.setHtml(html)

    def closeEvent(self, event) -> None:
        self.settings.setValue(f"help_{self.kind}_geometry", self.saveGeometry())
        self.settings.setValue(f"help_{self.kind}_splitter", self._splitter.saveState())
        super().closeEvent(event)


# ============================================================ AI 设置
class AISettingsDialog(QDialog):
    """配置 AI 供应商、endpoint、model、API Key。"""

    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("AI 设置")
        self.setMinimumWidth(560)

        self.provider = QComboBox()
        for name in AI_PROVIDERS:
            self.provider.addItem(name, name)
        cur = self.settings.value("ai/provider", DEFAULT_PROVIDER, type=str)
        idx = self.provider.findData(cur)
        self.provider.setCurrentIndex(max(idx, 0))
        self.provider.currentIndexChanged.connect(self._apply_preset)

        self.endpoint = QLineEdit()
        self.model = QLineEdit()
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_key = QCheckBox("显示明文")
        self.show_key.toggled.connect(lambda on: self.api_key.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))

        self.hint = QLabel()
        self.hint.setStyleSheet("color: #888")
        self.hint.setWordWrap(True)
        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self._test_connection)
        self.test_status = QLabel()

        # 回填当前值
        config = resolve_config(self.settings)
        self.endpoint.setText(config["endpoint"])
        self.model.setText(config["model"])
        self.api_key.setText(config["api_key"])
        self._update_hint()

        form = QFormLayout(self)
        form.addRow("供应商：", self.provider)
        form.addRow("Endpoint：", self.endpoint)
        form.addRow("模型：", self.model)
        form.addRow("API Key：", self.api_key)
        row = QHBoxLayout()
        row.addWidget(self.show_key)
        row.addStretch(1)
        row.addWidget(self.test_btn)
        form.addRow("", row)
        form.addRow(self.hint)
        form.addRow(self.test_status)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _apply_preset(self) -> None:
        name = self.provider.currentData()
        preset = AI_PROVIDERS.get(name)
        if not preset:
            return
        self.endpoint.setText(preset["endpoint"])
        self.model.setText(preset["model"])
        self._update_hint()

    def _update_hint(self) -> None:
        name = self.provider.currentData()
        preset = AI_PROVIDERS.get(name, {})
        env = preset.get("env_key", "")
        if env:
            self.hint.setText(
                f"提示：也可设置环境变量 {env}，应用内填写会覆盖环境变量。"
            )

    def _accept(self) -> None:
        self.settings.setValue("ai/provider", self.provider.currentData())
        self.settings.setValue("ai/endpoint", self.endpoint.text().strip())
        self.settings.setValue("ai/model", self.model.text().strip())
        self.settings.setValue("ai/api_key", self.api_key.text().strip())
        self.accept()

    def _test_connection(self) -> None:
        # 临时写入设置再调用
        self.settings.setValue("ai/provider", self.provider.currentData())
        self.settings.setValue("ai/endpoint", self.endpoint.text().strip())
        self.settings.setValue("ai/model", self.model.text().strip())
        self.settings.setValue("ai/api_key", self.api_key.text().strip())
        self.test_status.setText("正在测试…")
        self.test_status.setStyleSheet("color: #555")
        self.test_btn.setEnabled(False)

        thread, worker = make_worker(self.settings, "你好，请回复「OK」两个字符确认连接正常。")
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        def on_done(ok: bool, msg: str) -> None:
            try:
                thread.quit()
                thread.wait(3000)
            except Exception:
                pass
            self.test_btn.setEnabled(True)
            if ok:
                self.test_status.setText("连接成功：" + msg[:80])
                self.test_status.setStyleSheet("color: #16a34a")
            else:
                self.test_status.setText("失败：" + msg)
                self.test_status.setStyleSheet("color: #dc2626")

        worker.finished.connect(lambda text: on_done(True, text))
        worker.failed.connect(lambda msg: on_done(False, msg))
        self._test_thread = thread  # 防止 GC
        self._test_worker = worker
        thread.start()


# ============================================================ AI 查询
def _markdown_to_html(md: str) -> str:
    """最简 Markdown 渲染：代码块、加粗、行内代码、列表、段落。"""
    lines = md.split("\n")
    out: list[str] = []
    in_code = False
    code_buf: list[str] = []
    code_lang = ""
    in_list = False

    def flush_code() -> None:
        nonlocal in_code, code_buf, code_lang
        if not in_code:
            return
        esc = "\n".join(code_buf).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        out.append(
            f'<pre style="background:#f5f5f5; padding:8px; border:1px solid #ddd;'
            f' font-family: Consolas, \'Courier New\', monospace;'
            f' white-space: pre-wrap; word-wrap: break-word;">{esc}</pre>'
        )
        in_code = False
        code_buf = []
        code_lang = ""

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in lines:
        if line.strip().startswith("```"):
            if in_code:
                flush_code()
            else:
                close_list()
                in_code = True
                code_lang = line.strip()[3:]
            continue
        if in_code:
            code_buf.append(line)
            continue
        stripped = line.strip()
        if not stripped:
            close_list()
            continue
        # 加粗、行内代码先转义再还原
        if stripped.startswith(("# ", "## ", "### ", "#### ")):
            close_list()
            level = len(stripped) - len(stripped.lstrip("#"))
            text = stripped[level:].strip()
            out.append(f"<h{min(level, 4)}>{_inline(text)}</h{min(level, 4)}>")
            continue
        if re.match(r"^[-*+] +", stripped):
            if not in_list:
                out.append("<ul>")
                in_list = True
            text = re.sub(r"^[-*+] +", "", stripped)
            out.append(f"<li>{_inline(text)}</li>")
            continue
        if re.match(r"^\d+\. +", stripped):
            text = re.sub(r"^\d+\. +", "", stripped)
            out.append(f"<p>{_inline(text)}</p>")
            continue
        close_list()
        out.append(f"<p>{_inline(stripped)}</p>")

    flush_code()
    close_list()
    return "\n".join(out)


def _inline(text: str) -> str:
    """处理行内 markdown：转义 + 加粗 + 行内代码。"""
    esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # 行内代码 `xxx`
    esc = re.sub(r"`([^`]+)`", r'<code style="background:#eee;padding:0 3px;">\1</code>', esc)
    # 加粗 **xxx**
    esc = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", esc)
    # 斜体 *xxx*
    esc = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", esc)
    return esc


class AIQueryDialog(QDialog):
    """非模态 AI 查询窗口。可附加当前选区作为上下文。"""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("AI 查询")
        self.resize(720, 640)
        self.settings = QSettings("zhepub", "zhepub")

        self.question = QPlainTextEdit()
        self.question.setPlaceholderText("在此输入问题，例如：\n如何让段落首行缩进 2 个汉字？\n如何让图片自适应屏幕宽度？")
        self.question.setFixedHeight(120)

        self.attach_box = QCheckBox("附加当前选区作为上下文（如果编辑器有选区）")
        self.attach_box.setChecked(True)

        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self._send)
        self.send_btn.setDefault(True)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self._stop)
        self.stop_btn.setEnabled(False)

        self.answer = QTextBrowser()
        self.answer.setOpenExternalLinks(True)

        self.status = QLabel()
        self.status.setStyleSheet("color: #888")

        top = QVBoxLayout(self)
        top.addWidget(QLabel("问题："))
        top.addWidget(self.question)
        opts = QHBoxLayout()
        opts.addWidget(self.attach_box)
        opts.addStretch(1)
        opts.addWidget(self.stop_btn)
        opts.addWidget(self.send_btn)
        top.addLayout(opts)
        top.addWidget(QLabel("回答："))
        top.addWidget(self.answer, 1)
        top.addWidget(self.status)

        self._thread = None
        self._worker = None

        geom = self.settings.value("ai_dialog_geometry")
        if geom is not None:
            self.restoreGeometry(geom)

    def set_question(self, text: str) -> None:
        self.question.setPlainText(text)
        self.question.setFocus()

    def _current_selection(self) -> str:
        editor = self.window.current_editor()
        if editor is None:
            return ""
        text = editor.textCursor().selectedText()
        if not text:
            return ""
        return text.replace(chr(0x2029), "\n")

    def _send(self) -> None:
        text = self.question.toPlainText().strip()
        if not text:
            self.status.setText("请先输入问题。")
            self.status.setStyleSheet("color: #dc2626")
            return
        context = self._current_selection() if self.attach_box.isChecked() else None
        if context:
            self.status.setText("已附加选区作为上下文，正在查询…")
        else:
            self.status.setText("正在查询…")
        self.status.setStyleSheet("color: #555")
        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.answer.setPlainText("")

        config = resolve_config(self.settings)
        if not config.get("api_key"):
            self._on_failed("未配置 API Key，请先到 AI > AI 设置 中填写。")
            return

        thread, worker = make_worker(self.settings, text, context)
        worker.moveToThread(thread)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        thread.started.connect(worker.run)
        # 旧线程先停掉
        if self._thread is not None:
            try:
                self._thread.quit()
                self._thread.wait(500)
            except Exception:
                pass
        self._thread = thread
        self._worker = worker
        thread.start()

    def _stop(self) -> None:
        self._on_failed("已取消。")

    def _on_finished(self, text: str) -> None:
        self.answer.setHtml(_markdown_to_html(text))
        self.status.setText("完成。")
        self.status.setStyleSheet("color: #16a34a")
        self._reset_buttons()

    def _on_failed(self, msg: str) -> None:
        self.answer.setPlainText(msg)
        self.status.setText("失败。")
        self.status.setStyleSheet("color: #dc2626")
        self._reset_buttons()

    def _reset_buttons(self) -> None:
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if self._thread is not None:
            try:
                self._thread.quit()
                self._thread.wait(500)
            except Exception:
                pass
            self._thread = None
            self._worker = None

    def closeEvent(self, event) -> None:
        self._stop()
        self.settings.setValue("ai_dialog_geometry", self.saveGeometry())
        super().closeEvent(event)
