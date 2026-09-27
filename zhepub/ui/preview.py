"""预览面板：用 QTextBrowser 渲染 XHTML，图片与样式表从书中读取。"""

from __future__ import annotations

import re

from PyQt6.QtCore import QByteArray, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QImage, QTextDocument
from PyQt6.QtWidgets import QTextBrowser

from ..book import is_external, resolve

_XML_DECL_RE = re.compile(r"^\s*<\?xml[^>]*\?>")


class Preview(QTextBrowser):
    # 点击了书内链接：(目标文件, 锚点)
    link_activated = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._on_anchor)
        self.book = None
        self.href = ""
        self.text_for = None  # 回调：href -> 当前文本（包括编辑器中未保存的修改）

    def show_document(self, book, href: str, text: str) -> None:
        same = href == self.href and book is self.book
        scroll = self.verticalScrollBar().value()
        self.book, self.href = book, href
        self.document().clear()  # 清掉已缓存的图片与样式
        self.setHtml(_XML_DECL_RE.sub("", text))
        if same:
            self.verticalScrollBar().setValue(scroll)

    def clear_document(self) -> None:
        self.book, self.href = None, ""
        self.clear()

    def loadResource(self, rtype, url: QUrl):
        rtype = getattr(rtype, "value", rtype)
        raw = url.toString(QUrl.ComponentFormattingOption.FullyEncoded)
        if self.book is not None and raw and not is_external(raw):
            path = resolve(self.href, raw)
            res = self.book.resources.get(path)
            if res is not None:
                if rtype == QTextDocument.ResourceType.StyleSheetResource.value:
                    return self.text_for(path) if self.text_for else res.text()
                if rtype == QTextDocument.ResourceType.ImageResource.value:
                    image = QImage.fromData(QByteArray(res.data))
                    limit = self.viewport().width() - 40
                    if not image.isNull() and limit > 50 and image.width() > limit:
                        image = image.scaledToWidth(limit)
                    return image
                return QByteArray(res.data)
        return super().loadResource(rtype, url)

    def _on_anchor(self, url: QUrl) -> None:
        raw = url.toString(QUrl.ComponentFormattingOption.FullyEncoded)
        if raw.startswith("#"):
            self.scrollToAnchor(raw[1:])
        elif is_external(raw):
            QDesktopServices.openUrl(url)
        elif self.href:
            self.link_activated.emit(resolve(self.href, raw), raw.partition("#")[2])
