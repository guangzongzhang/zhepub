import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

from zhepub.book import Book  # noqa: E402
from zhepub.ui.editor import CodeEditor, py_to_qt, qt_to_py  # noqa: E402
from zhepub.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes)
    book = Book.new("测试")
    sec = book.resources["Text/Section0001.xhtml"]
    sec.set_text(sec.text().replace("<p></p>", "<p>第一段English</p>\n<h2>第二节</h2>\n<p>第二段</p>"))
    path = tmp_path / "t.epub"
    book.save(path)
    w = MainWindow(str(path))
    w.settings.clear()
    w.show()
    yield w
    w.book.modified = False
    for e in w.editors():
        e.document().setModified(False)
    w.close()


def test_utf16_conversion():
    text = "a𠀀b"
    assert py_to_qt(text, 2) == 3
    assert qt_to_py(text, 3) == 2


def test_open_edit_preview_save(window, tmp_path):
    editor = window.current_editor()
    assert isinstance(editor, CodeEditor)
    assert window.browser.topLevelItemCount() >= 3
    text = editor.toPlainText()
    editor.select_py_range(text.index("第二段") + 3, text.index("第二段") + 3)
    editor.insertPlainText("修改")
    assert window.is_dirty()
    window.update_preview()
    assert "第二段修改" in window.preview.toPlainText()
    assert window._save_to(tmp_path / "out.epub")
    assert not window.is_dirty()
    assert "第二段修改" in Book.open(tmp_path / "out.epub").resources["Text/Section0001.xhtml"].text()


def test_split_merge_toc_validate(window):
    editor = window.current_editor()
    text = editor.toPlainText()
    editor.select_py_range(text.index("<h2>"), text.index("<h2>"))
    window.split_at_cursor()
    assert len(window.book.spine) == 2
    new = window.current_editor().resource
    assert "<h2>第二节</h2>" in new.text()
    assert "第二节" not in window.book.resources["Text/Section0001.xhtml"].text()

    window.sync_editors()
    from zhepub.toc import generate_toc, write_toc
    entries, _ = generate_toc(window.book)
    write_toc(window.book, entries)
    window.reload_editors()
    window.refresh_toc()
    assert window.toc_tree.topLevelItemCount() == 1
    assert window.toc_tree.topLevelItem(0).child(0).text(0) == "第二节"

    window.validate()
    assert window.issues.topLevelItem(0).text(3) == "没有发现问题。"

    window.merge_with_previous()
    assert len(window.book.spine) == 1
    assert "第二节" in window.text_for("Text/Section0001.xhtml")


def test_find_replace(window):
    p = re.compile("段", re.M)
    assert window.count_matches(p, "all") == "共找到 2 处，分布在 1 个文件中。"
    assert window.find(p, "current") == ""
    editor = window.current_editor()
    assert editor.textCursor().selectedText() == "段"
    msg = window.replace_current(p, lambda m: "节", "current")
    assert msg.startswith("已替换 1 处")
    assert window.replace_all(p, lambda m: "节", "text") == "已替换 1 处，涉及 1 个文件。"
    assert "段" not in editor.toPlainText()


def test_rename_and_cover(window):
    img = window.book.add_resource("Images/图.png", b"\x89PNG\r\n")
    window.set_cover(img.href)
    window.sync_editors()
    window.book.rename_resource("Styles/style.css", "Styles/main.css")
    window.reload_editors()
    assert "../Styles/main.css" in window.current_editor().toPlainText()


def test_chinese_tool_on_current_file(window, monkeypatch):
    from zhepub.xhtml_tools import add_cjk_latin_spacing
    editor = window.current_editor()
    editor.replace_text(add_cjk_latin_spacing(editor.toPlainText()))
    assert "第一段 English" in editor.toPlainText()
    editor.undo()
    assert "第一段English" in editor.toPlainText()
