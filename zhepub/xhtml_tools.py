"""XHTML 文本处理：拆分/合并章节、字数统计、中文排版工具、TXT 导入。"""

from __future__ import annotations

import html
import posixpath
import re
from pathlib import Path

from .book import Book, decode_text, rewrite_urls

_TOKEN_RE = re.compile(
    r"<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>|<!.*?>"
    r"|<(?P<close>/?)(?P<name>[A-Za-z][\w:.-]*)(?P<attrs>(?:\s[^>]*?)?)(?P<self>/?)>",
    re.S,
)
_BODY_OPEN_RE = re.compile(r"<body\b[^>]*>", re.I)
_BODY_CLOSE_RE = re.compile(r"</body\s*>", re.I)
_ID_ATTR_RE = re.compile(r"""\s+id\s*=\s*(["']).*?\1""", re.S)
_ID_VALUE_RE = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""")
_SAME_DOC_LINK_RE = re.compile(r"""(\bhref\s*=\s*)(["'])#([^"']*)\2""")
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

CJK = r"㐀-䶿一-鿿豈-﫿\U00020000-\U0003134f"
_CJK_RE = re.compile(f"[{CJK}]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")


class SplitError(ValueError):
    pass


# ---------------------------------------------------------------------- 结构
def body_span(source: str) -> tuple[int, int]:
    """body 内容的起止位置（不含 body 标签本身）。"""
    m_open = _BODY_OPEN_RE.search(source)
    closes = list(_BODY_CLOSE_RE.finditer(source))
    if not m_open or not closes or closes[-1].start() < m_open.end():
        raise SplitError("文件中没有找到 <body> … </body>。")
    return m_open.end(), closes[-1].start()


def _open_elements(fragment: str) -> list[tuple[str, str]]:
    """扫描片段，返回片段末尾仍未闭合的元素 [(标签名, 开始标签原文)]。"""
    stack: list[tuple[str, str]] = []
    for m in _TOKEN_RE.finditer(fragment):
        name = m.group("name")
        if name is None:
            continue
        if m.group("close"):
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == name:
                    del stack[i:]
                    break
        elif not m.group("self") and name.lower() not in VOID_TAGS:
            stack.append((name, m.group(0)))
    return stack


def split_xhtml(source: str, pos: int) -> tuple[str, str, set[str]]:
    """在 pos 处把文档拆成两个完整的文档。

    光标所在的未闭合元素会在前半部分闭合、在后半部分重新打开（去掉 id），
    因此在段落中间拆分也能得到格式正确的两个文件。
    返回 (前半文档, 后半文档, 移到后半部分的 id 集合)。
    """
    start, end = body_span(source)
    if not start <= pos <= end:
        raise SplitError("光标不在 <body> 内。")
    # 光标落在标签或注释内部时，退到该标签之前
    for m in _TOKEN_RE.finditer(source, start, end):
        if m.start() < pos < m.end():
            pos = m.start()
            break
        if m.start() >= pos:
            break
    head_part, tail_part = source[start:pos], source[pos:end]
    if not head_part.strip():
        raise SplitError("光标之前没有内容，无需拆分。")
    if not tail_part.strip():
        raise SplitError("光标之后没有内容，无需拆分。")

    stack = _open_elements(head_part)
    closing = "".join(f"</{name}>" for name, _ in reversed(stack))
    reopening = "".join(_ID_ATTR_RE.sub("", tag) for _, tag in stack)
    first = source[:pos] + closing + "\n" + source[end:]
    second = source[:start] + "\n" + reopening + tail_part.lstrip("\n") + source[end:]
    moved = set(_ID_VALUE_RE.findall(tail_part))
    return first, second, moved


def body_content(source: str) -> str:
    start, end = body_span(source)
    return source[start:end]


def merge_xhtml(first: str, second: str) -> str:
    """把 second 的 body 内容追加到 first 的 body 末尾。"""
    _, end = body_span(first)
    return first[:end].rstrip() + "\n" + body_content(second).strip("\n") + "\n" + first[end:]


def split_resource(book: Book, href: str, text: str, pos: int) -> str:
    """拆分 href（当前内容为 text），返回新文件的路径。链接会被一并修正。"""
    first, second, moved = split_xhtml(text, pos)
    name = posixpath.basename(href)
    remaining = set(_ID_VALUE_RE.findall(first))
    res = book.resources[href]
    index = book.spine_index(href)
    new = book.add_resource(href, b"", spine_index=index + 1 if index >= 0 else None)
    new_name = posixpath.basename(new.href)

    # 同一文件内部的 #锚点 链接，在拆分后要指向另一个文件
    def fix_same_doc(doc: str, ids_elsewhere: set[str], other: str) -> str:
        def sub(m: re.Match) -> str:
            if m.group(3) in ids_elsewhere:
                return f"{m.group(1)}{m.group(2)}{other}#{m.group(3)}{m.group(2)}"
            return m.group(0)

        return _SAME_DOC_LINK_RE.sub(sub, doc)

    res.set_text(fix_same_doc(first, moved, new_name))
    new.set_text(fix_same_doc(second, remaining - moved, name))
    book.relocate(
        {}, fragment_map=lambda target, frag: new.href if target == href and frag in moved else None
    )
    return new.href


def merge_resources(book: Book, first_href: str, second_href: str, first_text: str,
                    second_text: str) -> None:
    """把 second 合并到 first 末尾并删除 second，指向 second 的链接改为指向 first。"""
    second_text = rewrite_urls(second_text, second_href, first_href, lambda t, f: t)
    merged = merge_xhtml(first_text, second_text)
    book.resources[first_href].set_text(merged)
    book.remove_resource(second_href)
    book.relocate({second_href: first_href})


# ---------------------------------------------------------------------- 统计
def visible_text(source: str) -> str:
    try:
        start, end = body_span(source)
        source = source[start:end]
    except SplitError:
        pass
    source = re.sub(r"<(script|style)\b.*?</\1\s*>", " ", source, flags=re.S | re.I)
    source = re.sub(r"<!--.*?-->", " ", source, flags=re.S)
    return html.unescape(re.sub(r"<[^>]+>", " ", source))


def count_words(source: str) -> tuple[int, int]:
    """返回 (汉字数, 西文单词数)。"""
    text = visible_text(source)
    return len(_CJK_RE.findall(text)), len(_LATIN_WORD_RE.findall(text))


# ---------------------------------------------------------------------- 中文排版
_SKIP_TAGS = {"script", "style", "pre", "code", "head", "title"}


def map_text_nodes(source: str, fn) -> str:
    """只对 body 中的文本内容应用 fn，标签、脚本、样式、代码块保持不变。"""
    try:
        start, end = body_span(source)
    except SplitError:
        start, end = 0, len(source)
    parts = []
    last = start
    skip_depth = 0
    for m in _TOKEN_RE.finditer(source, start, end):
        text = source[last:m.start()]
        parts.append(text if skip_depth else fn(text))
        parts.append(m.group(0))
        name = (m.group("name") or "").lower()
        if name in _SKIP_TAGS and not m.group("self"):
            skip_depth += -1 if m.group("close") else 1
            skip_depth = max(skip_depth, 0)
        last = m.end()
    tail = source[last:end]
    parts.append(tail if skip_depth else fn(tail))
    return source[:start] + "".join(parts) + source[end:]


_SPACE_CJK_LATIN = re.compile(f"([{CJK}])([A-Za-z0-9])")
_SPACE_LATIN_CJK = re.compile(f"([A-Za-z0-9%])([{CJK}])")


def add_cjk_latin_spacing(source: str) -> str:
    """在汉字与西文、数字之间加空格：「使用Python3开发」→「使用 Python3 开发」。"""

    def fn(text: str) -> str:
        text = _SPACE_CJK_LATIN.sub(r"\1 \2", text)
        return _SPACE_LATIN_CJK.sub(r"\1 \2", text)

    return map_text_nodes(source, fn)


_HALF_TO_FULL = {",": "，", ".": "。", "!": "！", "?": "？", ":": "：", ";": "；"}
_ELLIPSIS_RE = re.compile(f"(?<=[{CJK}])(?:\\.{{3,}}|…+|。{{3,}})")
_PUNCT_RE = re.compile(f"(?<=[{CJK}])([,.!?:;])(?![0-9A-Za-z])")


def fullwidth_punctuation(source: str) -> str:
    """把紧跟在汉字后的半角标点改为全角：「你好,世界.」→「你好，世界。」。"""

    def fn(text: str) -> str:
        text = _ELLIPSIS_RE.sub("……", text)
        return _PUNCT_RE.sub(lambda m: _HALF_TO_FULL[m.group(1)], text)

    return map_text_nodes(source, fn)


_P_LEADING_SPACE_RE = re.compile(
    r"(<p\b[^>]*>)(?:\s|　| |&nbsp;|&#160;|&#12288;|&#x3000;|&#xa0;)+", re.I
)


def strip_paragraph_leading_spaces(source: str) -> str:
    """删除段首的空格与全角空格（缩进应交给 CSS 的 text-indent）。"""
    return _P_LEADING_SPACE_RE.sub(r"\1", source)


def opencc_converter(config: str):
    """返回繁简转换函数；未安装 opencc 时返回 None。config 如 's2t'、't2s'。"""
    try:
        import opencc
    except ImportError:
        return None
    try:
        converter = opencc.OpenCC(config)
    except Exception:
        converter = opencc.OpenCC(config + ".json")
    return lambda source: map_text_nodes(source, converter.convert)


# ---------------------------------------------------------------------- TXT 导入
CHAPTER_PATTERN = (
    r"^[ \t　]*("
    r"第[0-9０-９零〇一二三四五六七八九十百千万两]+[章节回卷部集篇幕][^\n]{0,30}"
    r"|序章|序言|序|前言|楔子|引子|引言|后记|尾声|番外[^\n]{0,20}"
    r")[ \t　]*$"
)
_VOLUME_RE = re.compile(r"^第[0-9０-９零〇一二三四五六七八九十百千万两]+[卷部集]")


def read_text_file(path: str | Path) -> str:
    return decode_text(Path(path).read_bytes()).replace("\r\n", "\n").replace("\r", "\n")


def split_txt_chapters(text: str, pattern: str = CHAPTER_PATTERN) -> list[tuple[str, list[str]]]:
    regex = re.compile(pattern, re.M)
    chapters: list[tuple[str, list[str]]] = []
    title, lines = "", []
    for line in text.split("\n"):
        stripped = line.strip(" \t　")
        if stripped and regex.match(line):
            if title or any(lines):
                chapters.append((title, lines))
            title, lines = stripped, []
        elif stripped:
            lines.append(stripped)
    if title or lines:
        chapters.append((title, lines))
    return chapters


def book_from_txt(text: str, title: str, pattern: str = CHAPTER_PATTERN) -> Book:
    from .toc import generate_toc, write_toc

    book = Book.new(title)
    for href in [r.href for r in book.by_category("text") if not r.is_nav]:
        book.remove_resource(href)
    chapters = split_txt_chapters(text, pattern)
    if not chapters:
        chapters = [(title, [])]
    for i, (chapter_title, paragraphs) in enumerate(chapters):
        heading = chapter_title or ("前言" if i == 0 and len(chapters) > 1 else title)
        tag = "h1" if _VOLUME_RE.match(heading) else "h2"
        body = [f"<{tag}>{html.escape(heading, quote=False)}</{tag}>"]
        body += [f"<p>{html.escape(p, quote=False)}</p>" for p in paragraphs]
        book.new_section(title=heading, body="\n".join(body))
    entries, _ = generate_toc(book)
    write_toc(book, entries)
    return book
