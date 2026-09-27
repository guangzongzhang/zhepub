import zipfile

import pytest

from zhepub.book import Book, EpubError, relative_url, rewrite_urls
from zhepub.toc import flatten, generate_toc, read_toc, write_toc
from zhepub.xhtml_tools import (
    SplitError,
    add_cjk_latin_spacing,
    book_from_txt,
    count_words,
    fullwidth_punctuation,
    merge_resources,
    split_resource,
    split_txt_chapters,
    split_xhtml,
    strip_paragraph_leading_spaces,
)


def doc(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title>'
        '<link href="../Styles/style.css" rel="stylesheet" type="text/css"/></head>\n'
        f"<body>\n{body}\n</body>\n</html>\n"
    )


def test_new_book_roundtrip(tmp_path):
    book = Book.new("测试书")
    path = tmp_path / "测试.epub"
    book.save(path)
    with zipfile.ZipFile(path) as zf:
        first = zf.infolist()[0]
        assert first.filename == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED
    again = Book.open(path)
    assert again.title == "测试书"
    assert again.language == "zh-CN"
    assert again.identifier.startswith("urn:uuid:")
    assert [s.href for s in again.spine] == ["Text/Section0001.xhtml"]
    assert again.nav_resource() is not None
    assert again.validate() == []


def test_open_rejects_non_epub(tmp_path):
    bad = tmp_path / "x.epub"
    bad.write_text("hello")
    with pytest.raises(EpubError):
        Book.open(bad)


def test_rewrite_urls_handles_moves():
    text = '<a href="b.xhtml#x">x</a><img src="../Images/a%20b.png"/><a href="http://x.com/a">'
    out = rewrite_urls(text, "Text/a.xhtml", "Text/sub/a.xhtml",
                       lambda t, f: {"Images/a b.png": "Images/c.png"}.get(t, t))
    assert 'href="../b.xhtml#x"' in out
    assert 'src="../../Images/c.png"' in out
    assert 'href="http://x.com/a"' in out
    assert relative_url("Text/a.xhtml", "Styles/s.css") == "../Styles/s.css"


def test_rename_updates_references(tmp_path):
    book = Book.new("书")
    img = book.add_resource("Images/封面.png", b"\x89PNG")
    sec = book.resources["Text/Section0001.xhtml"]
    sec.set_text(doc('<p><img src="../Images/%E5%B0%81%E9%9D%A2.png" alt=""/></p>'))
    css = book.resources["Styles/style.css"]
    css.set_text('body { background: url("../Images/封面.png"); }')
    book.set_cover(img.href)
    book.rename_resource("Images/封面.png", "Images/cover.png")
    assert 'src="../Images/cover.png"' in sec.text()
    assert 'url("../Images/cover.png")' in css.text()
    assert book.cover_href() == "Images/cover.png"
    book.rename_resource("Styles/style.css", "Styles/main.css")
    assert 'href="../Styles/main.css"' in sec.text()
    book.save(tmp_path / "a.epub")
    assert Book.open(tmp_path / "a.epub").cover_href() == "Images/cover.png"


def test_metadata_edit():
    book = Book.new("书")
    book.set_dc("creator", ["张三", "李四"])
    book.set_dc("identifier", ["isbn:123"])
    assert book.get_dc("creator") == ["张三", "李四"]
    assert book.identifier == "isbn:123"
    book.set_dc("creator", [])
    assert book.get_dc("creator") == []


def test_validate_finds_problems():
    book = Book.new("书")
    sec = book.resources["Text/Section0001.xhtml"]
    sec.set_text(doc('<p><a href="missing.xhtml">x</a><a href="#nope">y</a></p>'))
    book.add_resource("Text/bad.xhtml", doc("<p>unclosed").encode())
    msgs = [i.message for i in book.validate()]
    assert any("不存在：missing.xhtml" in m for m in msgs)
    assert any("XML 格式错误" in m for m in msgs)


def test_generate_toc_nested_and_ids():
    book = Book.new("书")
    sec = book.resources["Text/Section0001.xhtml"]
    sec.set_text(doc("<h1>第一章</h1><p>a</p><h2>第一节</h2><h2 id='s2'>第二节</h2>"))
    entries, skipped = generate_toc(book)
    assert skipped == []
    assert entries[0].title == "第一章" and entries[0].target == "Text/Section0001.xhtml"
    assert [c.target for c in entries[0].children] == [
        "Text/Section0001.xhtml#heading_1",
        "Text/Section0001.xhtml#s2",
    ]
    assert 'id="heading_1"' in sec.text()
    assert sec.text().startswith("<?xml")
    assert "<!DOCTYPE html>" in sec.text()
    write_toc(book, entries)
    assert [e.title for e in flatten(read_toc(book))] == ["第一章", "第一节", "第二节"]
    assert "navPoint" not in (book.ncx_resource().text() if book.ncx_resource() else "")
    assert book.validate() == []


def test_split_in_middle_of_paragraph():
    source = doc('<div class="c"><p id="a">前半<b>粗体</b>后半</p><p id="z">末段</p></div>')
    pos = source.index("后半")
    first, second, moved = split_xhtml(source, pos)
    assert '<p id="a">前半<b>粗体</b></p></div>' in first
    assert '<div class="c"><p>后半</p><p id="z">末段</p></div>' in second
    assert moved == {"z"}
    with pytest.raises(SplitError):
        split_xhtml(source, source.index("<body>") + 7)


def test_split_and_merge_resources_fix_links():
    book = Book.new("书")
    sec = book.resources["Text/Section0001.xhtml"]
    text = doc('<p><a href="#z">跳</a></p><p id="z">后</p>')
    sec.set_text(text)
    other = book.new_section(title="二", body='<p><a href="Section0001.xhtml#z">回</a></p>')
    new_href = split_resource(book, sec.href, text, text.index('<p id="z">'))
    assert [s.href for s in book.spine][:2] == [sec.href, new_href]
    assert 'href="Section0001_2.xhtml#z"' in sec.text()
    assert 'href="Section0001_2.xhtml#z"' in other.text()
    assert book.validate() == [] or all(i.level == "警告" for i in book.validate())

    merge_resources(book, sec.href, new_href, sec.text(), book.resources[new_href].text())
    assert new_href not in book.resources
    assert 'href="Section0001.xhtml#z"' in other.text()
    assert '<p id="z">后</p>' in sec.text()


def test_chinese_tools():
    src = doc("<p>使用Python3开发,很好.等等...</p><pre>a,b</pre>")
    spaced = add_cjk_latin_spacing(src)
    assert "使用 Python3 开发" in spaced
    assert "<title>t</title>" in spaced
    punct = fullwidth_punctuation(src)
    assert "开发，很好。等等……" in punct
    assert "<pre>a,b</pre>" in punct
    assert strip_paragraph_leading_spaces("<p>　　正文</p><p>&nbsp; x</p>") == "<p>正文</p><p>x</p>"
    assert count_words(doc("<p>中文字 two words</p>")) == (3, 2)


def test_txt_import():
    text = "书名\n\n第一卷 开端\n第一章 起\n　　第一段\n第二段\n第2章 承\n内容\n"
    chapters = split_txt_chapters(text)
    assert [c[0] for c in chapters] == ["", "第一卷 开端", "第一章 起", "第2章 承"]
    book = book_from_txt(text, "小说")
    assert len(book.spine) == 4
    toc = read_toc(book)
    assert [e.title for e in toc] == ["前言", "第一卷 开端"]
    assert [e.title for e in toc[1].children] == ["第一章 起", "第2章 承"]
    assert "<p>第一段</p>" in book.resources[book.spine[2].href].text()
    assert book.validate() == []


def test_html_entities_are_tolerated():
    book = Book.new("书")
    sec = book.resources["Text/Section0001.xhtml"]
    sec.set_text(doc("<h1>第一章&nbsp;开始</h1><h2>小节&mdash;一</h2>"))
    issues = book.validate()
    assert [i.level for i in issues] == ["警告"]
    assert "&nbsp;" in issues[0].message
    entries, skipped = generate_toc(book)
    assert skipped == []
    assert entries[0].title == "第一章 开始"
    # 生成目录时文件被重新序列化，实体已变成真实字符
    assert "&nbsp;" not in sec.text()
    assert book.validate() == []


def test_rename_updates_guide(tmp_path):
    from lxml import etree

    from zhepub.book import OPF, NS

    book = Book.new("书")
    guide = etree.SubElement(book.opf_root, OPF + "guide")
    etree.SubElement(guide, OPF + "reference", type="text", href="Text/Section0001.xhtml#a")
    book.rename_resource("Text/Section0001.xhtml", "Text/正文.xhtml")
    ref = book.opf_root.find("opf:guide/opf:reference", NS)
    assert ref.get("href") == "Text/%E6%AD%A3%E6%96%87.xhtml#a"
    book.save(tmp_path / "g.epub")
    again = Book.open(tmp_path / "g.epub")
    assert again.opf_root.find("opf:guide/opf:reference", NS) is not None
