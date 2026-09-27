"""主窗口：书籍浏览器、编辑区、预览、目录、校验结果。"""

from __future__ import annotations

import posixpath
import re
from html import escape
from pathlib import Path

from PyQt6.QtCore import QByteArray, QSettings, Qt, QTimer
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QFontDatabase,
    QImage,
    QKeySequence,
    QPixmap,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStyle,
    QTabWidget,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..book import CATEGORY_NAMES, Book, EpubError, relative_url
from ..toc import generate_toc, read_toc, write_toc
from ..xhtml_tools import (
    SplitError,
    add_cjk_latin_spacing,
    book_from_txt,
    count_words,
    fullwidth_punctuation,
    merge_resources,
    opencc_converter,
    read_text_file,
    split_resource,
    strip_paragraph_leading_spaces,
)
from .dialogs import (
    AIQueryDialog,
    AISettingsDialog,
    FindReplaceDialog,
    InsertImageDialog,
    MetadataDialog,
    SyntaxHelpDialog,
    TxtImportDialog,
)
from . import editor as _editor_module
from .editor import CodeEditor
from .preview import Preview
from .themes import DEFAULT_THEME, list_themes, render_qss

APP_NAME = "EPUB 中文编辑器"
HREF_ROLE = Qt.ItemDataRole.UserRole
EPUB_FILTER = "EPUB 电子书 (*.epub)"
_BLOCK_RE = re.compile(r"^(\s*)<(p|div|h[1-6])\b([^>]*)>(.*)</\2>(\s*)$")
PARAGRAPH_SEP = chr(0x2029)  # QTextCursor.selectedText() 用它表示换行
THEME_LABELS = {"light": "浅色", "dark": "深色", "eye": "护眼"}


class ResourceView(QScrollArea):
    """图片、字体等非文本文件的查看页。"""

    def __init__(self, resource, parent=None):
        super().__init__(parent)
        self.resource = resource
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        size = f"{len(resource.data) / 1024:.1f} KB"
        info = QLabel()
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if resource.category == "image":
            image = QImage.fromData(QByteArray(resource.data))
            if image.isNull():
                info.setText(f"{resource.href}\n{size}\n（无法显示此图片）")
            else:
                pic = QLabel()
                pic.setPixmap(QPixmap.fromImage(image))
                pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(pic)
                info.setText(f"{resource.href}    {image.width()} × {image.height()} 像素    {size}")
        elif resource.category == "font":
            fid = QFontDatabase.addApplicationFontFromData(QByteArray(resource.data))
            families = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
            if families:
                sample = QLabel("永和九年，岁在癸丑，暮春之初\n天地玄黄 宇宙洪荒\nABCDEFG abcdefg 0123456789")
                sample.setFont(QFont(families[0], 24))
                sample.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(sample)
                info.setText(f"{resource.href}    字体：{'、'.join(families)}    {size}")
            else:
                info.setText(f"{resource.href}\n{size}\n（无法加载此字体）")
        else:
            info.setText(f"{resource.href}\n{resource.media_type}\n{size}\n（此类型文件无法编辑）")
        layout.addWidget(info)
        self.setWidget(body)


class MainWindow(QMainWindow):
    def __init__(self, path: str | None = None):
        super().__init__()
        self.settings = QSettings("zhepub", "zhepub")
        self.book: Book = Book.new()
        self.preview_href = ""
        self.last_match = None
        self.find_dialog: FindReplaceDialog | None = None
        self.ai_dialog: AIQueryDialog | None = None
        self.toolbar: QToolBar | None = None
        self._fullscreen = False
        self._fs_saved: dict | None = None
        self.resize(1400, 860)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        self._build_docks()
        self._build_actions()
        self._build_menus()
        self._build_toolbar()

        self.pos_label = QLabel()
        self.count_label = QLabel()
        self.statusBar().addPermanentWidget(self.count_label)
        self.statusBar().addPermanentWidget(self.pos_label)

        self.preview_timer = QTimer(self, singleShot=True, interval=400)
        self.preview_timer.timeout.connect(self.update_preview)
        self.setAcceptDrops(True)

        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self.settings.value("state")
        if state is not None:
            self.restoreState(state)

        # 应用保存的主题
        theme = self.settings.value("theme", DEFAULT_THEME, type=str)
        if theme not in THEME_LABELS:
            theme = DEFAULT_THEME
        self.apply_theme(theme, persist=False)

        if path and self.open_path(path):
            return
        self._set_book(Book.new())

    # ================================================================ 界面搭建
    def _build_docks(self) -> None:
        self.browser = QTreeWidget()
        self.browser.setHeaderHidden(True)
        self.browser.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.browser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.browser.customContextMenuRequested.connect(self._browser_menu)
        self.browser.itemActivated.connect(self._on_browser_activated)
        self.browser_dock = self._dock("书籍浏览器", "browser", self.browser,
                                       Qt.DockWidgetArea.LeftDockWidgetArea)

        self.preview = Preview()
        self.preview.text_for = self.text_for
        self.preview.link_activated.connect(lambda href, frag: self.open_resource(href, fragment=frag))
        self.preview_dock = self._dock("预览", "preview", self.preview,
                                       Qt.DockWidgetArea.RightDockWidgetArea)
        self.preview_dock.visibilityChanged.connect(lambda v: v and self.preview_timer.start(0))

        toc_panel = QWidget()
        toc_layout = QVBoxLayout(toc_panel)
        toc_layout.setContentsMargins(0, 0, 0, 0)
        self.toc_tree = QTreeWidget()
        self.toc_tree.setHeaderHidden(True)
        self.toc_tree.itemActivated.connect(self._on_toc_activated)
        toc_layout.addWidget(self.toc_tree)
        row = QHBoxLayout()
        gen = QPushButton("从标题生成目录")
        gen.clicked.connect(self.generate_toc)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh_toc)
        row.addWidget(gen)
        row.addWidget(refresh)
        toc_layout.addLayout(row)
        self.toc_dock = self._dock("目录", "toc", toc_panel, Qt.DockWidgetArea.RightDockWidgetArea)
        self.tabifyDockWidget(self.preview_dock, self.toc_dock)
        self.preview_dock.raise_()

        self.issues = QTreeWidget()
        self.issues.setHeaderLabels(["级别", "文件", "行", "说明"])
        self.issues.setRootIsDecorated(False)
        self.issues.setColumnWidth(0, 60)
        self.issues.setColumnWidth(1, 220)
        self.issues.setColumnWidth(2, 50)
        self.issues.itemActivated.connect(self._on_issue_activated)
        self.issues_dock = self._dock("校验结果", "issues", self.issues,
                                      Qt.DockWidgetArea.BottomDockWidgetArea)
        self.issues_dock.hide()

    def _dock(self, title, name, widget, area) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        return dock

    def _action(self, text, slot, shortcut=None, tip=None, icon=None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(lambda *_: slot())
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if tip:
            action.setStatusTip(tip)
        if icon is not None:
            action.setIcon(self.style().standardIcon(icon))
        return action

    def _build_actions(self) -> None:
        sp = QStyle.StandardPixmap
        a = self._action
        self.act_new = a("新建(&N)", self.new_book, QKeySequence.StandardKey.New, icon=sp.SP_FileIcon)
        self.act_open = a("打开(&O)…", self.open_dialog, QKeySequence.StandardKey.Open,
                          icon=sp.SP_DialogOpenButton)
        self.act_import_txt = a("导入 TXT(&T)…", self.import_txt,
                                tip="把 TXT 小说按章节标题拆分成 EPUB")
        self.act_save = a("保存(&S)", self.save, QKeySequence.StandardKey.Save,
                          icon=sp.SP_DialogSaveButton)
        self.act_save_as = a("另存为(&A)…", self.save_as, "Ctrl+Shift+S")
        self.act_quit = a("退出(&Q)", self.close, "Ctrl+Q")

        self.act_undo = a("撤销", lambda: self._editor_call("undo"), QKeySequence.StandardKey.Undo)
        self.act_redo = a("重做", lambda: self._editor_call("redo"), QKeySequence.StandardKey.Redo)
        self.act_find = a("查找与替换(&F)…", self.show_find, QKeySequence.StandardKey.Find,
                          icon=sp.SP_FileDialogContentsView)
        self.act_find_next = a("查找下一个", lambda: self._find_again(False), "F3")
        self.act_find_prev = a("查找上一个", lambda: self._find_again(True), "Shift+F3")
        self.act_goto = a("跳转到行(&G)…", self.goto_line, "Ctrl+G")

        self.act_insert_image = a("插入图片(&I)…", self.insert_image, "Ctrl+Shift+I")
        self.act_split = a("在光标处拆分章节", self.split_at_cursor, "Ctrl+Return",
                           tip="把光标之后的内容移到一个新的文件中")
        self.act_merge = a("与上一章节合并", self.merge_with_previous,
                           tip="把当前文件的内容追加到阅读顺序中的上一个文件末尾")
        self.act_new_section = a("新建空白章节", self.add_section)
        self.act_new_css = a("新建样式表", self.add_stylesheet)
        self.act_add_files = a("添加现有文件…", self.add_existing_files)

        self.heading_actions = [
            a(f"标题 {n}", lambda n=n: self.set_block_tag(f"h{n}"), f"Ctrl+{n}") for n in range(1, 7)
        ]
        self.act_paragraph = a("正文段落", lambda: self.set_block_tag("p"), "Ctrl+0")
        self.act_bold = a("加粗", lambda: self.wrap_inline("strong"), "Ctrl+B")
        self.act_italic = a("斜体", lambda: self.wrap_inline("em"), "Ctrl+I")

        self.act_metadata = a("元数据(&M)…", self.edit_metadata, "F8")
        self.act_toc = a("从标题生成目录", self.generate_toc, "Ctrl+T")
        self.act_validate = a("校验电子书", self.validate, "F7", icon=sp.SP_DialogApplyButton)
        self.act_count = a("字数统计", self.show_word_count)
        self.act_spacing = a("中英文之间加空格", lambda: self.apply_tool(add_cjk_latin_spacing,
                                                                  "中英文之间加空格"))
        self.act_punct = a("半角标点转全角", lambda: self.apply_tool(fullwidth_punctuation,
                                                               "半角标点转全角"))
        self.act_indent = a("删除段首空格", lambda: self.apply_tool(strip_paragraph_leading_spaces,
                                                              "删除段首空格"))
        self.act_s2t = a("简体转繁体", lambda: self.apply_opencc("s2t", "简体转繁体"))
        self.act_t2s = a("繁体转简体", lambda: self.apply_opencc("t2s", "繁体转简体"))
        self.act_about = a("关于", self.about)

        # 帮助菜单中的语法查询
        self.act_help_xhtml = a("XHTML 语法详解…", lambda: self._show_syntax_help("xhtml"))
        self.act_help_css = a("CSS 语法详解…", lambda: self._show_syntax_help("css"))

        # AI 菜单
        self.act_ai_query = a("AI 查询…", lambda: self.show_ai_query(), "Ctrl+Shift+Q",
                              tip="打开 AI 查询窗口，可附加当前选区")
        self.act_ai_explain = a("用 AI 解释当前选区", self.ai_explain_selection, "Ctrl+Shift+E",
                                tip="把当前选中的代码片段发给 AI 解释")
        self.act_ai_settings = a("AI 设置…", self.show_ai_settings,
                                  tip="配置 AI 供应商、endpoint、API Key")

        # 主题切换（视图菜单，互斥）
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        self.act_themes: dict[str, QAction] = {}
        for name in list_themes():
            act = QAction(f"{THEME_LABELS[name]}模式", self)
            act.setCheckable(True)
            act.setChecked(name == DEFAULT_THEME)
            act.triggered.connect(lambda checked=False, n=name: self.apply_theme(n))
            self._theme_group.addAction(act)
            self.act_themes[name] = act

        # 全屏写作模式
        self.act_fullscreen = a("全屏写作模式", self.toggle_fullscreen, "F11",
                                tip="隐藏菜单栏/工具栏/dock，专注写作；ESC 或 F11 退出")

    def _build_menus(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu("文件(&F)")
        m.addActions([self.act_new, self.act_open])
        self.recent_menu = m.addMenu("最近打开")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        m.addAction(self.act_import_txt)
        m.addSeparator()
        m.addActions([self.act_save, self.act_save_as])
        m.addSeparator()
        m.addAction(self.act_quit)

        m = mb.addMenu("编辑(&E)")
        m.addActions([self.act_undo, self.act_redo])
        m.addSeparator()
        m.addActions([self.act_find, self.act_find_next, self.act_find_prev, self.act_goto])

        m = mb.addMenu("插入(&I)")
        m.addAction(self.act_insert_image)
        m.addSeparator()
        m.addActions([self.act_split, self.act_merge])
        m.addSeparator()
        m.addActions([self.act_new_section, self.act_new_css, self.act_add_files])

        m = mb.addMenu("格式(&O)")
        m.addActions(self.heading_actions)
        m.addAction(self.act_paragraph)
        m.addSeparator()
        m.addActions([self.act_bold, self.act_italic])

        m = mb.addMenu("工具(&T)")
        m.addActions([self.act_metadata, self.act_toc, self.act_validate, self.act_count])
        zh = m.addMenu("中文排版")
        zh.addActions([self.act_spacing, self.act_punct, self.act_indent])
        zh.addSeparator()
        zh.addActions([self.act_s2t, self.act_t2s])

        m = mb.addMenu("视图(&V)")
        for dock in (self.browser_dock, self.preview_dock, self.toc_dock, self.issues_dock):
            m.addAction(dock.toggleViewAction())
        m.addSeparator()
        theme_menu = m.addMenu("界面主题")
        for name in list_themes():
            theme_menu.addAction(self.act_themes[name])
        m.addSeparator()
        m.addAction(self.act_fullscreen)

        m = mb.addMenu("AI(&A)")
        m.addAction(self.act_ai_query)
        m.addAction(self.act_ai_explain)
        m.addSeparator()
        m.addAction(self.act_ai_settings)

        m = mb.addMenu("帮助(&H)")
        m.addAction(self.act_help_xhtml)
        m.addAction(self.act_help_css)
        m.addSeparator()
        m.addAction(self.act_about)

    def _build_toolbar(self) -> None:
        tb = self.addToolBar("工具栏")
        tb.setObjectName("toolbar")
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        tb.addActions([self.act_new, self.act_open, self.act_save])
        tb.addSeparator()
        tb.addActions([self.act_find, self.act_validate])
        tb.addSeparator()
        for act in (self.act_metadata, self.act_toc, self.act_split, self.act_insert_image):
            tb.addAction(act)
        self.toolbar = tb

    # ================================================================ 主题 / 全屏
    def apply_theme(self, name: str, persist: bool = True) -> None:
        """切换界面主题：QSS、编辑器高亮配色、行号区、当前行高亮。"""
        if name not in THEME_LABELS:
            name = DEFAULT_THEME
        _editor_module.apply_theme(name)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(render_qss(name))
        for editor in self.editors():
            editor.apply_theme(name)
        if persist:
            self.settings.setValue("theme", name)
        self.act_themes[name].setChecked(True)
        self.statusBar().showMessage(f"已切换到 {THEME_LABELS[name]}模式", 3000)

    def toggle_fullscreen(self) -> None:
        if not self._fullscreen:
            self._fs_saved = {
                "menubar": self.menuBar().isVisible(),
                "toolbar": self.toolbar.isVisible() if self.toolbar else False,
                "statusbar": self.statusBar().isVisible(),
                "docks": {dock.objectName(): dock.isVisible()
                          for dock in self.findChildren(QDockWidget)},
            }
            self.menuBar().hide()
            if self.toolbar:
                self.toolbar.hide()
            for dock in self.findChildren(QDockWidget):
                dock.hide()
            self.statusBar().hide()
            self.showFullScreen()
            self._fullscreen = True
        else:
            self.showNormal()
            if self._fs_saved:
                self.menuBar().setVisible(self._fs_saved["menubar"])
                if self.toolbar:
                    self.toolbar.setVisible(self._fs_saved["toolbar"])
                for dock in self.findChildren(QDockWidget):
                    name = dock.objectName()
                    if name in self._fs_saved["docks"]:
                        dock.setVisible(self._fs_saved["docks"][name])
                self.statusBar().setVisible(self._fs_saved["statusbar"])
                self._fs_saved = None
            self._fullscreen = False
            self.statusBar().showMessage("已退出全屏写作模式。", 3000)

    def keyPressEvent(self, event) -> None:
        if self._fullscreen and event.key() == Qt.Key.Key_Escape:
            self.toggle_fullscreen()
            return
        super().keyPressEvent(event)

    # ================================================================ 状态
    def is_dirty(self) -> bool:
        return self.book.modified or any(e.document().isModified() for e in self.editors())

    def update_title(self) -> None:
        name = self.book.path.name if self.book.path else "未命名.epub"
        self.setWindowModified(self.is_dirty())
        self.setWindowTitle(f"{name}[*] - {APP_NAME}")

    def editors(self) -> list[CodeEditor]:
        return [w for w in self._tab_widgets() if isinstance(w, CodeEditor)]

    def _tab_widgets(self) -> list[QWidget]:
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def current_editor(self) -> CodeEditor | None:
        w = self.tabs.currentWidget()
        return w if isinstance(w, CodeEditor) else None

    def current_resource(self):
        w = self.tabs.currentWidget()
        return getattr(w, "resource", None)

    def editor_for(self, href: str) -> CodeEditor | None:
        res = self.book.resources.get(href)
        return next((e for e in self.editors() if e.resource is res), None)

    def text_for(self, href: str) -> str:
        editor = self.editor_for(href)
        if editor is not None:
            return editor.toPlainText()
        res = self.book.resources.get(href)
        return res.text() if res else ""

    def sync_editors(self) -> None:
        """把编辑器中的修改写回书中。"""
        for editor in self.editors():
            if editor.document().isModified():
                editor.resource.set_text(editor.toPlainText())
                editor.document().setModified(False)
                self.book.modified = True

    def reload_editors(self) -> None:
        """书中内容被整体修改后，让已打开的编辑器与之同步。"""
        for i in range(self.tabs.count() - 1, -1, -1):
            w = self.tabs.widget(i)
            res = w.resource
            if self.book.resources.get(res.href) is not res:
                self.tabs.removeTab(i)
                w.deleteLater()
                continue
            self.tabs.setTabText(i, res.filename)
            self.tabs.setTabToolTip(i, res.href)
            if isinstance(w, CodeEditor):
                w.replace_text(res.text())
                w.document().setModified(False)
        self.update_title()
        self.preview_timer.start(0)

    def _set_book(self, book: Book) -> None:
        while self.tabs.count():
            w = self.tabs.widget(0)
            self.tabs.removeTab(0)
            w.deleteLater()
        self.book = book
        self.preview_href = ""
        self.last_match = None
        self.preview.clear_document()
        self.issues.clear()
        self.refresh_browser()
        self.refresh_toc()
        docs = [r for r in book.text_documents() if not r.is_nav]
        if docs:
            self.open_resource(docs[0].href)
        if book.load_warnings:
            self.issues.clear()
            for msg in book.load_warnings:
                QTreeWidgetItem(self.issues, ["警告", "", "", msg])
            self.issues_dock.show()
        self.update_title()

    # ================================================================ 书籍浏览器
    def refresh_browser(self) -> None:
        selected = {it.data(0, HREF_ROLE) for it in self.browser.selectedItems()}
        self.browser.clear()
        cover = self.book.cover_href()
        spine = {s.href for s in self.book.spine}
        folder_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        file_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        for cat, label in CATEGORY_NAMES.items():
            if cat == "text":
                items = self.book.text_documents()
            else:
                items = sorted(self.book.by_category(cat), key=lambda r: r.href.lower())
            if not items and cat not in ("text", "style", "image"):
                continue
            top = QTreeWidgetItem(self.browser, [f"{label}（{len(items)}）"])
            top.setIcon(0, folder_icon)
            top.setData(0, HREF_ROLE, None)
            top.setData(0, HREF_ROLE + 1, cat)
            for res in items:
                name = res.filename
                if res.href == cover:
                    name += "  〔封面〕"
                if res.is_nav:
                    name += "  〔导航〕"
                item = QTreeWidgetItem(top, [name])
                item.setIcon(0, file_icon)
                item.setData(0, HREF_ROLE, res.href)
                item.setToolTip(0, f"{res.href}\n{res.media_type}")
                if cat == "text" and res.href not in spine and not res.is_nav:
                    item.setForeground(0, QColor("#9ca3af"))
                    item.setToolTip(0, f"{res.href}\n不在阅读顺序中")
                if res.href in selected:
                    item.setSelected(True)
            top.setExpanded(cat in ("text", "style", "image"))

    def selected_hrefs(self) -> list[str]:
        return [h for it in self.browser.selectedItems() if (h := it.data(0, HREF_ROLE))]

    def _on_browser_activated(self, item: QTreeWidgetItem) -> None:
        href = item.data(0, HREF_ROLE)
        if href:
            self.open_resource(href)

    def _browser_menu(self, pos) -> None:
        item = self.browser.itemAt(pos)
        hrefs = self.selected_hrefs()
        menu = QMenu(self)
        if hrefs:
            res = self.book.resources[hrefs[0]]
            menu.addAction("打开", lambda: [self.open_resource(h) for h in hrefs])
            if len(hrefs) == 1:
                menu.addAction("重命名…", lambda: self.rename_resource(hrefs[0]))
            menu.addAction("删除", lambda: self.delete_resources(hrefs))
            if len(hrefs) == 1 and res.category == "text" and self.book.spine_index(res.href) >= 0:
                menu.addSeparator()
                menu.addAction("上移", lambda: self.move_resource(hrefs[0], -1))
                menu.addAction("下移", lambda: self.move_resource(hrefs[0], 1))
            if len(hrefs) == 1 and res.category == "text" and self.book.spine_index(res.href) < 0 \
                    and not res.is_nav:
                menu.addAction("加入阅读顺序", lambda: self.add_to_spine(hrefs[0]))
            if len(hrefs) == 1 and res.category == "image":
                menu.addSeparator()
                menu.addAction("设为封面", lambda: self.set_cover(hrefs[0]))
            menu.addSeparator()
        cat = item.data(0, HREF_ROLE + 1) if item and not item.data(0, HREF_ROLE) else None
        if cat in (None, "text"):
            menu.addAction(self.act_new_section)
        if cat in (None, "style"):
            menu.addAction(self.act_new_css)
        menu.addAction(self.act_add_files)
        menu.exec(self.browser.viewport().mapToGlobal(pos))

    def rename_resource(self, href: str) -> None:
        old_name = posixpath.basename(href)
        name, ok = QInputDialog.getText(self, "重命名", "新的文件名：", text=old_name)
        name = name.strip()
        if not ok or not name or name == old_name:
            return
        if "/" in name or "\\" in name:
            QMessageBox.warning(self, "重命名", "文件名中不能包含 / 或 \\。")
            return
        if posixpath.splitext(name)[1].lower() != posixpath.splitext(old_name)[1].lower():
            answer = QMessageBox.question(self, "重命名", "修改了扩展名，文件类型可能无法识别。仍要继续吗？")
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.sync_editors()
        try:
            self.book.rename_resource(href, posixpath.join(posixpath.dirname(href), name))
        except EpubError as e:
            QMessageBox.warning(self, "重命名", str(e))
            return
        self.reload_editors()
        self.refresh_browser()
        self.refresh_toc()
        self.statusBar().showMessage(f"已重命名为 {name}，并更新了所有链接。", 5000)

    def delete_resources(self, hrefs: list[str]) -> None:
        names = "\n".join(hrefs[:15]) + ("\n…" if len(hrefs) > 15 else "")
        answer = QMessageBox.question(self, "删除", f"确定要从书中删除以下文件吗？\n\n{names}")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.sync_editors()
        for href in hrefs:
            self.book.remove_resource(href)
        self.reload_editors()
        self.refresh_browser()
        self.refresh_toc()

    def move_resource(self, href: str, delta: int) -> None:
        if self.book.move_in_spine(href, delta):
            self.refresh_browser()
            self.update_title()

    def add_to_spine(self, href: str) -> None:
        from ..book import SpineItem

        self.book.spine.append(SpineItem(href))
        self.book.modified = True
        self.refresh_browser()
        self.update_title()

    def set_cover(self, href: str) -> None:
        self.book.set_cover(href)
        self.refresh_browser()
        self.update_title()
        self.statusBar().showMessage(f"已将 {posixpath.basename(href)} 设为封面。", 5000)

    def add_section(self) -> None:
        self.sync_editors()
        cur = self.current_resource()
        after = cur.href if cur is not None and cur.category == "text" else None
        res = self.book.new_section(after_href=after)
        self.refresh_browser()
        self.open_resource(res.href)

    def add_stylesheet(self) -> None:
        res = self.book.add_resource("Styles/style.css", b"")
        self.refresh_browser()
        self.open_resource(res.href)

    def add_existing_files(self, file_filter: str = "所有文件 (*)") -> list[str]:
        paths, _ = QFileDialog.getOpenFileNames(self, "添加现有文件", self._last_dir(), file_filter)
        return self._add_paths(paths)

    def _add_paths(self, paths: list[str]) -> list[str]:
        if not paths:
            return []
        self.settings.setValue("last_dir", str(Path(paths[0]).parent))
        self.sync_editors()
        added = []
        for p in paths:
            try:
                added.append(self.book.add_file(p).href)
            except OSError as e:
                QMessageBox.warning(self, "添加文件", f"无法读取 {p}：{e}")
        self.refresh_browser()
        self.update_title()
        if len(added) == 1:
            self.open_resource(added[0])
        return added

    # ================================================================ 标签页
    def open_resource(self, href: str, line: int | None = None, fragment: str = "") -> None:
        res = self.book.resources.get(href)
        if res is None:
            self.statusBar().showMessage(f"书中没有这个文件：{href}", 5000)
            return
        widget = next((w for w in self._tab_widgets() if w.resource is res), None)
        if widget is None:
            if res.is_text:
                widget = CodeEditor(res, res.text())
                widget.textChanged.connect(self._on_text_changed)
                widget.cursorPositionChanged.connect(self._update_cursor_label)
                widget.document().modificationChanged.connect(lambda *_: self.update_title())
            else:
                widget = ResourceView(res)
            index = self.tabs.addTab(widget, res.filename)
            self.tabs.setTabToolTip(index, res.href)
        self.tabs.setCurrentWidget(widget)
        if isinstance(widget, CodeEditor):
            if line:
                widget.goto_line(line)
            elif fragment:
                m = re.search(r"""\bid\s*=\s*["']%s["']""" % re.escape(fragment), widget.toPlainText())
                if m:
                    widget.goto_line(widget.toPlainText().count("\n", 0, m.start()) + 1)
            widget.setFocus()
        if fragment:
            self.update_preview()
            self.preview.scrollToAnchor(fragment)

    def close_tab(self, index: int) -> None:
        w = self.tabs.widget(index)
        if isinstance(w, CodeEditor) and w.document().isModified():
            w.resource.set_text(w.toPlainText())
            self.book.modified = True
        self.tabs.removeTab(index)
        w.deleteLater()
        self.update_title()

    def _on_tab_changed(self, _index: int) -> None:
        self._update_cursor_label()
        self.preview_timer.start(0)

    def _on_text_changed(self) -> None:
        self.preview_timer.start()

    def _update_cursor_label(self) -> None:
        editor = self.current_editor()
        if editor is None:
            self.pos_label.setText("")
            return
        c = editor.textCursor()
        self.pos_label.setText(f"  行 {c.blockNumber() + 1}，列 {c.positionInBlock() + 1}  ")

    def update_preview(self) -> None:
        editor = self.current_editor()
        if editor is not None and editor.resource.category == "text":
            text = editor.toPlainText()
            han, words = count_words(text)
            self.count_label.setText(f"  汉字 {han}  单词 {words}  ")
            self.preview_href = editor.resource.href
            if self.preview_dock.isVisible():
                self.preview.show_document(self.book, self.preview_href, text)
        elif editor is not None and editor.resource.category == "style":
            self.count_label.setText("")
            if self.preview_href in self.book.resources and self.preview_dock.isVisible():
                self.preview.show_document(self.book, self.preview_href,
                                           self.text_for(self.preview_href))
        else:
            self.count_label.setText("")
            if self.tabs.count() == 0:
                self.preview.clear_document()

    # ================================================================ 文件
    def _last_dir(self) -> str:
        return self.settings.value("last_dir", str(Path.home()))

    def maybe_save(self) -> bool:
        if not self.is_dirty():
            return True
        answer = QMessageBox.question(
            self, APP_NAME, "当前电子书有未保存的修改，是否保存？",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Discard

    def new_book(self) -> None:
        if self.maybe_save():
            self._set_book(Book.new())

    def open_dialog(self) -> None:
        if not self.maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, "打开电子书", self._last_dir(), EPUB_FILTER)
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> bool:
        if Path(path).suffix.lower() == ".txt":
            return self.import_txt(path)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            book = Book.open(path)
        except EpubError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "打开失败", str(e))
            return False
        QApplication.restoreOverrideCursor()
        self.settings.setValue("last_dir", str(Path(path).parent))
        self._add_recent(path)
        self._set_book(book)
        return True

    def import_txt(self, path: str | None = None) -> bool:
        if path is None:
            if not self.maybe_save():
                return False
            path, _ = QFileDialog.getOpenFileName(self, "导入 TXT", self._last_dir(),
                                                  "文本文件 (*.txt)")
            if not path:
                return False
        try:
            text = read_text_file(path)
        except OSError as e:
            QMessageBox.critical(self, "导入失败", str(e))
            return False
        dialog = TxtImportDialog(text, Path(path).stem, self)
        if dialog.exec() != TxtImportDialog.DialogCode.Accepted:
            return False
        book = book_from_txt(text, dialog.title.text().strip() or Path(path).stem,
                             dialog.pattern.text())
        book.modified = True
        self.settings.setValue("last_dir", str(Path(path).parent))
        self._set_book(book)
        self.statusBar().showMessage(f"已导入 {len(book.spine)} 个章节，请保存为 EPUB。", 8000)
        return True

    def save(self) -> bool:
        if self.book.path is None:
            return self.save_as()
        return self._save_to(self.book.path)

    def save_as(self) -> bool:
        default = str(Path(self._last_dir()) / f"{self.book.title or '未命名'}.epub")
        if self.book.path:
            default = str(self.book.path)
        path, _ = QFileDialog.getSaveFileName(self, "另存为", default, EPUB_FILTER)
        if not path:
            return False
        if not path.lower().endswith(".epub"):
            path += ".epub"
        return self._save_to(Path(path))

    def _save_to(self, path: Path) -> bool:
        self.sync_editors()
        try:
            self.book.save(path)
        except EpubError as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return False
        self.settings.setValue("last_dir", str(path.parent))
        self._add_recent(str(path))
        self.update_title()
        self.statusBar().showMessage(f"已保存到 {path}", 5000)
        return True

    def _add_recent(self, path: str) -> None:
        recent = [p for p in self.settings.value("recent", [], type=list) if p != path]
        self.settings.setValue("recent", [path] + recent[:9])

    def _fill_recent(self) -> None:
        self.recent_menu.clear()
        recent = [p for p in self.settings.value("recent", [], type=list) if Path(p).exists()]
        if not recent:
            self.recent_menu.addAction("（无）").setEnabled(False)
        for p in recent:
            self.recent_menu.addAction(p, lambda p=p: self.maybe_save() and self.open_path(p))

    def closeEvent(self, event) -> None:
        if not self.maybe_save():
            event.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("state", self.saveState())
        event.accept()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        books = [p for p in paths if p.lower().endswith((".epub", ".txt"))]
        if books:
            if self.maybe_save():
                self.open_path(books[0])
        else:
            self._add_paths(paths)

    # ================================================================ 编辑
    def _editor_call(self, name: str) -> None:
        editor = self.current_editor()
        if editor is not None:
            getattr(editor, name)()

    def _text_editor(self) -> CodeEditor | None:
        editor = self.current_editor()
        if editor is None or editor.resource.category != "text":
            self.statusBar().showMessage("请先打开一个 HTML 文本文件。", 4000)
            return None
        return editor

    def goto_line(self) -> None:
        editor = self.current_editor()
        if editor is None:
            return
        line, ok = QInputDialog.getInt(self, "跳转到行", "行号：",
                                       editor.textCursor().blockNumber() + 1, 1, editor.blockCount())
        if ok:
            editor.goto_line(line)

    def set_block_tag(self, tag: str) -> None:
        editor = self._text_editor()
        if editor is None:
            return
        cursor = editor.textCursor()
        selected = cursor.selectedText()
        if selected and PARAGRAPH_SEP not in selected:
            cursor.insertText(f"<{tag}>{selected}</{tag}>")
            return
        block = cursor.block()
        m = _BLOCK_RE.match(block.text())
        if not m:
            self.statusBar().showMessage("光标所在行不是单独的段落或标题，请先选中要设置的文字。", 5000)
            return
        bc = QTextCursor(block)
        bc.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        bc.insertText(f"{m.group(1)}<{tag}{m.group(3)}>{m.group(4)}</{tag}>{m.group(5)}")

    def wrap_inline(self, tag: str) -> None:
        editor = self._text_editor()
        if editor is None:
            return
        cursor = editor.textCursor()
        selected = cursor.selectedText().replace(PARAGRAPH_SEP, "\n")
        cursor.insertText(f"<{tag}>{selected}</{tag}>")
        if not selected:
            cursor.movePosition(QTextCursor.MoveOperation.Left, n=len(tag) + 3)
            editor.setTextCursor(cursor)

    def insert_image(self) -> None:
        editor = self._text_editor()
        if editor is None:
            return
        dialog = InsertImageDialog(
            self.book, self,
            add_callback=lambda: self.add_existing_files("图片 (*.jpg *.jpeg *.png *.gif *.webp *.svg)"),
        )
        # 添加图片可能打开了新标签页，这里记住原来的编辑器
        if dialog.exec() != InsertImageDialog.DialogCode.Accepted or not dialog.selected_href():
            return
        self.tabs.setCurrentWidget(editor)
        src = relative_url(editor.resource.href, dialog.selected_href())
        editor.insertPlainText(f'<img alt="{escape(dialog.alt.text())}" src="{escape(src)}"/>')
        editor.setFocus()

    def split_at_cursor(self) -> None:
        editor = self._text_editor()
        if editor is None:
            return
        self.sync_editors()
        href = editor.resource.href
        try:
            new_href = split_resource(self.book, href, editor.toPlainText(), editor.py_position())
        except SplitError as e:
            QMessageBox.information(self, "拆分章节", str(e))
            return
        self.reload_editors()
        self.refresh_browser()
        self.refresh_toc()
        self.open_resource(new_href)
        self.statusBar().showMessage(f"已拆分出 {posixpath.basename(new_href)}。", 5000)

    def merge_with_previous(self) -> None:
        editor = self._text_editor()
        if editor is None:
            return
        href = editor.resource.href
        index = self.book.spine_index(href)
        if index <= 0:
            QMessageBox.information(self, "合并章节", "当前文件前面没有可合并的章节。")
            return
        prev = self.book.spine[index - 1].href
        answer = QMessageBox.question(
            self, "合并章节",
            f"把 {posixpath.basename(href)} 合并到 {posixpath.basename(prev)} 末尾，并删除前者？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.sync_editors()
        try:
            merge_resources(self.book, prev, href, self.text_for(prev), self.text_for(href))
        except SplitError as e:
            QMessageBox.warning(self, "合并章节", str(e))
            return
        self.reload_editors()
        self.refresh_browser()
        self.refresh_toc()
        self.open_resource(prev)

    # ================================================================ 查找替换
    def show_find(self) -> None:
        if self.find_dialog is None:
            self.find_dialog = FindReplaceDialog(self)
        editor = self.current_editor()
        self.find_dialog.set_find_text(editor.textCursor().selectedText() if editor else "")
        self.find_dialog.show()
        self.find_dialog.raise_()
        self.find_dialog.activateWindow()

    def _find_again(self, backwards: bool) -> None:
        if self.find_dialog is None or not self.find_dialog.find_edit.currentText():
            self.show_find()
        elif backwards:
            self.find_dialog.find_previous()
        else:
            self.find_dialog.find_next()

    def _scope_resources(self, scope: str) -> list:
        if scope == "current":
            res = self.current_resource()
            return [res] if res is not None and res.is_text else []
        if scope == "text":
            return self.book.text_documents()
        if scope == "style":
            return self.book.by_category("style")
        rest = [r for r in self.book.resources.values() if r.is_text and r.category != "text"]
        return self.book.text_documents() + rest

    @staticmethod
    def _search(pattern: re.Pattern, text: str, start: int, end: int, backwards: bool):
        """在 text 中查找：向后从 end 开始，向前找 start 之前的最后一处。"""
        if backwards:
            last = None
            for m in pattern.finditer(text):
                if m.start() >= start:
                    break
                last = m
            return last
        m = pattern.search(text, end)
        if m is not None and m.start() == m.end() == end and start == end:
            m = pattern.search(text, end + 1) if end < len(text) else None
        return m

    def find(self, pattern: re.Pattern, scope: str, backwards: bool = False) -> str:
        files = self._scope_resources(scope)
        if not files:
            return "当前范围内没有可搜索的文件。"
        editor = self.current_editor()
        current = editor.resource if editor is not None else None
        start_index = -1 if not backwards else 0
        if current is not None and any(r is current for r in files):
            start_index = next(i for i, r in enumerate(files) if r is current)
            s, e = editor.selected_py_range()
            m = self._search(pattern, editor.toPlainText(), s, e, backwards)
            if m is not None:
                self._select_match(editor, m)
                return ""
        step = -1 if backwards else 1
        for k in range(1, len(files) + 1):
            res = files[(start_index + k * step) % len(files)]
            text = self.text_for(res.href)
            m = self._search(pattern, text, len(text), len(text), True) if backwards \
                else pattern.search(text)
            if m is not None:
                self.open_resource(res.href)
                self._select_match(self.current_editor(), m)
                wrapped = (start_index + k * step) >= len(files) or (start_index + k * step) < 0 \
                    or res is current
                return "已从另一端继续查找。" if wrapped else ""
        return "未找到。"

    def _select_match(self, editor: CodeEditor, m: re.Match) -> None:
        editor.select_py_range(m.start(), m.end())
        self.last_match = (editor.resource, m.start(), m.end())

    def replace_current(self, pattern: re.Pattern, repl, scope: str) -> str:
        editor = self.current_editor()
        if editor is not None and self.last_match is not None \
                and self.last_match[0] is editor.resource \
                and editor.selected_py_range() == self.last_match[1:]:
            start, end = self.last_match[1:]
            m = pattern.search(editor.toPlainText(), start)
            if m is not None and m.span() == (start, end):
                editor.textCursor().insertText(repl(m))
                self.last_match = None
                result = self.find(pattern, scope)
                return "已替换 1 处。" + (result if result else "")
        return self.find(pattern, scope)

    def replace_all(self, pattern: re.Pattern, repl, scope: str) -> str:
        total = files = 0
        for res in self._scope_resources(scope):
            text = self.text_for(res.href)
            new, n = pattern.subn(repl, text)
            if not n:
                continue
            total += n
            files += 1
            editor = self.editor_for(res.href)
            if editor is not None:
                editor.replace_text(new)
            else:
                res.set_text(new)
                self.book.modified = True
        self.last_match = None
        self.update_title()
        self.preview_timer.start(0)
        return f"已替换 {total} 处，涉及 {files} 个文件。" if total else "未找到。"

    def count_matches(self, pattern: re.Pattern, scope: str) -> str:
        counts = [(res, sum(1 for _ in pattern.finditer(self.text_for(res.href))))
                  for res in self._scope_resources(scope)]
        total = sum(n for _, n in counts)
        files = sum(1 for _, n in counts if n)
        return f"共找到 {total} 处，分布在 {files} 个文件中。"

    # ================================================================ 工具
    def edit_metadata(self) -> None:
        if MetadataDialog(self.book, self).exec():
            self.refresh_browser()
            self.update_title()

    def refresh_toc(self) -> None:
        self.toc_tree.clear()

        def add(parent, entries):
            for e in entries:
                item = QTreeWidgetItem(parent, [e.title or "（无标题）"])
                item.setData(0, HREF_ROLE, e.target)
                item.setToolTip(0, e.target)
                add(item, e.children)

        add(self.toc_tree, read_toc(self.book))
        self.toc_tree.expandAll()

    def _on_toc_activated(self, item: QTreeWidgetItem) -> None:
        target = item.data(0, HREF_ROLE) or ""
        href, _, frag = target.partition("#")
        if href:
            self.open_resource(href, fragment=frag)

    def generate_toc(self) -> None:
        level, ok = QInputDialog.getInt(
            self, "生成目录", "把以下级别以内的标题（h1~hN）加入目录，N =",
            int(self.settings.value("toc_level", 3)), 1, 6)
        if not ok:
            return
        self.settings.setValue("toc_level", level)
        self.sync_editors()
        entries, skipped = generate_toc(self.book, level)
        write_toc(self.book, entries)
        self.reload_editors()
        self.refresh_browser()
        self.refresh_toc()
        self.toc_dock.show()
        self.toc_dock.raise_()
        msg = f"目录已生成，共 {sum(1 for _ in self._iter_toc())} 项。"
        if skipped:
            QMessageBox.warning(self, "生成目录", msg + "\n以下文件格式有错误，已跳过：\n"
                                + "\n".join(skipped) + "\n\n可以用“校验电子书”（F7）查看具体错误。")
        else:
            self.statusBar().showMessage(msg, 5000)

    def _iter_toc(self):
        it = QTreeWidgetItemIterator(self.toc_tree)
        while it.value():
            yield it.value()
            it += 1

    def validate(self) -> None:
        self.sync_editors()
        issues = self.book.validate()
        self.issues.clear()
        for issue in issues:
            item = QTreeWidgetItem(self.issues, [issue.level, issue.href,
                                                 str(issue.line) if issue.line else "", issue.message])
            item.setForeground(0, QColor("#dc2626" if issue.level == "错误" else "#d97706"))
            item.setData(0, HREF_ROLE, (issue.href, issue.line))
        if not issues:
            QTreeWidgetItem(self.issues, ["", "", "", "没有发现问题。"])
        self.issues_dock.show()
        errors = sum(1 for i in issues if i.level == "错误")
        self.statusBar().showMessage(f"校验完成：{errors} 个错误，{len(issues) - errors} 个警告。", 8000)

    def _on_issue_activated(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, HREF_ROLE)
        if data and data[0] in self.book.resources:
            self.open_resource(data[0], line=data[1] or None)

    def show_word_count(self) -> None:
        han = words = 0
        for res in self.book.text_documents():
            if res.is_nav:
                continue
            h, w = count_words(self.text_for(res.href))
            han += h
            words += w
        lines = [f"全书（{len(self.book.spine)} 个章节）：汉字 {han:,}，西文单词 {words:,}"]
        editor = self.current_editor()
        if editor is not None and editor.resource.category == "text":
            h, w = count_words(editor.toPlainText())
            lines.insert(0, f"当前文件：汉字 {h:,}，西文单词 {w:,}")
        QMessageBox.information(self, "字数统计", "\n".join(lines))

    def apply_tool(self, fn, name: str) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(name)
        box.setText(f"要对哪些文件执行“{name}”？\n（只修改正文文字，不会改动标签。可以撤销当前文件中的修改。）")
        current_btn = box.addButton("当前文件", QMessageBox.ButtonRole.AcceptRole)
        all_btn = box.addButton("全部 HTML 文件", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is current_btn:
            editor = self._text_editor()
            if editor is not None:
                editor.replace_text(fn(editor.toPlainText()))
        elif box.clickedButton() is all_btn:
            self.sync_editors()
            changed = 0
            for res in self.book.text_documents():
                if res.is_nav:
                    continue
                text = res.text()
                new = fn(text)
                if new != text:
                    res.set_text(new)
                    changed += 1
            if changed:
                self.book.modified = True
            self.reload_editors()
            self.statusBar().showMessage(f"“{name}”完成，修改了 {changed} 个文件。", 6000)

    def apply_opencc(self, config: str, name: str) -> None:
        fn = opencc_converter(config)
        if fn is None:
            QMessageBox.information(
                self, name,
                "繁简转换需要 OpenCC，请先安装：\n\npip install opencc-python-reimplemented",
            )
            return
        self.apply_tool(fn, name)

    def about(self) -> None:
        QMessageBox.about(
            self, f"关于 {APP_NAME}",
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>一款在本地运行的 EPUB 电子书编辑器，针对中文书籍的编辑习惯做了优化。</p>"
            "<p>界面与工作方式参考了开源 EPUB 编辑器 "
            "<a href='https://github.com/Sigil-Ebook/Sigil'>Sigil</a>："
            "书籍浏览器、代码视图、实时预览、目录生成、元数据编辑、查找替换与校验。</p>"
            "<p>内置 XHTML/CSS 语法帮助；菜单栏 AI 可调用国产大模型查询。</p>",
        )

    # ============================================================ 语法帮助 / AI
    def _show_syntax_help(self, kind: str) -> None:
        dlg = SyntaxHelpDialog(kind, self)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def show_ai_query(self, preset_text: str = "") -> None:
        if self.ai_dialog is None:
            self.ai_dialog = AIQueryDialog(self)
        if preset_text:
            self.ai_dialog.set_question(preset_text)
        self.ai_dialog.show()
        self.ai_dialog.raise_()
        self.ai_dialog.activateWindow()

    def show_ai_settings(self) -> None:
        AISettingsDialog(self.settings, self).exec()

    def ai_explain_selection(self) -> None:
        editor = self.current_editor()
        snippet = ""
        if editor is not None:
            text = editor.textCursor().selectedText()
            if text:
                snippet = text.replace(PARAGRAPH_SEP, "\n")
        if snippet:
            lang = "css" if editor.resource.category == "style" else "xhtml"
            preset = f"请解释以下 {lang.upper()} 代码的含义和作用，如有可改进之处请指出：\n\n```{lang}\n{snippet}\n```"
        else:
            preset = ""
        self.show_ai_query(preset_text=preset)
