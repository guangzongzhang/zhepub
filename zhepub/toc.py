"""目录（TOC）：读取 nav/NCX、根据标题自动生成、写回 nav.xhtml 与 toc.ncx。"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from html import escape
from urllib.parse import unquote

from lxml import etree

from .book import NS, Book, parse_xml, relative_url, resolve, xml_parser

XHTML = "{%s}" % NS["xhtml"]
EPUB_TYPE = "{%s}type" % NS["epub"]
_HEADING_RE = re.compile(r"^h([1-6])$")


@dataclass
class TocEntry:
    title: str
    target: str  # 相对 OPF 目录的路径，可带 #锚点
    children: list[TocEntry] = field(default_factory=list)

    @property
    def href(self) -> str:
        return self.target.split("#", 1)[0]

    @property
    def fragment(self) -> str:
        return self.target.partition("#")[2]


def _local(tag) -> str:
    return etree.QName(tag).localname if isinstance(tag, str) else ""


def _text(el) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def _target(base_href: str, url: str) -> str:
    frag = url.partition("#")[2]
    path = resolve(base_href, url)
    return f"{path}#{unquote(frag)}" if frag else path


# ---------------------------------------------------------------------- 读取
def read_toc(book: Book) -> list[TocEntry]:
    nav = book.nav_resource()
    if nav is not None:
        try:
            entries = _read_nav(nav.href, etree.fromstring(nav.data, xml_parser(recover=True)))
            if entries:
                return entries
        except etree.XMLSyntaxError:
            pass
    ncx = book.ncx_resource()
    if ncx is not None:
        try:
            return _read_ncx(ncx.href, etree.fromstring(ncx.data, xml_parser(recover=True)))
        except etree.XMLSyntaxError:
            pass
    return []


def _find_toc_nav(root):
    navs = [el for el in root.iter() if _local(el.tag) == "nav"]
    for el in navs:
        if "toc" in (el.get(EPUB_TYPE) or "").split():
            return el
    return navs[0] if navs else None


def _read_nav(base: str, root) -> list[TocEntry]:
    nav = _find_toc_nav(root)
    if nav is None:
        return []
    ol = next((c for c in nav if _local(c.tag) == "ol"), None)
    return _read_ol(base, ol) if ol is not None else []


def _read_ol(base: str, ol) -> list[TocEntry]:
    entries = []
    for li in ol:
        if _local(li.tag) != "li":
            continue
        label = next((c for c in li if _local(c.tag) in ("a", "span")), None)
        sub = next((c for c in li if _local(c.tag) == "ol"), None)
        href = label.get("href", "") if label is not None else ""
        entry = TocEntry(_text(label) if label is not None else "", _target(base, href) if href else "")
        if sub is not None:
            entry.children = _read_ol(base, sub)
        entries.append(entry)
    return entries


def _read_ncx(base: str, root) -> list[TocEntry]:
    nav_map = next((el for el in root.iter() if _local(el.tag) == "navMap"), None)
    return _read_nav_points(base, nav_map) if nav_map is not None else []


def _read_nav_points(base: str, parent) -> list[TocEntry]:
    entries = []
    for point in parent:
        if _local(point.tag) != "navPoint":
            continue
        label = next((el for el in point.iter() if _local(el.tag) == "text"), None)
        content = next((c for c in point if _local(c.tag) == "content"), None)
        src = content.get("src", "") if content is not None else ""
        entry = TocEntry(_text(label) if label is not None else "", _target(base, src) if src else "")
        entry.children = _read_nav_points(base, point)
        entries.append(entry)
    return entries


# ---------------------------------------------------------------------- 生成
def generate_toc(book: Book, max_level: int = 3) -> tuple[list[TocEntry], list[str]]:
    """根据书脊中各文件的 h1~h{max_level} 生成目录。

    文件中第一个标题直接链接到文件本身；其余标题若没有 id，会自动添加。
    返回 (目录, 因格式错误而跳过的文件列表)。
    """
    roots: list[TocEntry] = []
    stack: list[tuple[int, TocEntry]] = []
    skipped: list[str] = []
    for res in book.text_documents():
        if res.is_nav or book.spine_index(res.href) < 0:
            continue
        try:
            tree = parse_xml(res.data).getroottree()
        except etree.XMLSyntaxError:
            skipped.append(res.href)
            continue
        existing_ids = {el.get("id") for el in tree.iter() if el.get("id")}
        changed = False
        first = True
        counter = 0
        for el in tree.iter():
            m = _HEADING_RE.match(_local(el.tag))
            if not m or int(m.group(1)) > max_level:
                continue
            title = _text(el)
            if not title:
                continue
            level = int(m.group(1))
            if first:
                target = res.href
            else:
                hid = el.get("id")
                if not hid:
                    while True:
                        counter += 1
                        hid = f"heading_{counter}"
                        if hid not in existing_ids:
                            break
                    existing_ids.add(hid)
                    el.set("id", hid)
                    changed = True
                target = f"{res.href}#{hid}"
            first = False
            entry = TocEntry(title, target)
            while stack and stack[-1][0] >= level:
                stack.pop()
            (stack[-1][1].children if stack else roots).append(entry)
            stack.append((level, entry))
        if changed:
            res.data = etree.tostring(tree, encoding="utf-8", xml_declaration=True)
            book.modified = True
    return roots, skipped


# ---------------------------------------------------------------------- 写回
def write_toc(book: Book, entries: list[TocEntry]) -> None:
    if not entries and book.spine:
        entries = [TocEntry(book.title or "开始", book.spine[0].href)]
    lang = book.language or "zh-CN"

    if book.is_epub3:
        nav = book.nav_resource()
        if nav is None:
            nav = book.add_resource("Text/nav.xhtml", b"", properties="nav")
        nav.set_text(_build_nav(nav.href, nav.data, entries, lang))

    ncx = book.ncx_resource()
    if ncx is None and not book.is_epub3:
        ncx = book.add_resource("toc.ncx", b"")
    if ncx is not None:
        ncx.set_text(_build_ncx(book, ncx.href, entries))
    book.modified = True


def _ol_html(base: str, entries: list[TocEntry], indent: str) -> str:
    lines = [f"{indent}<ol>"]
    for e in entries:
        frag = f"#{e.fragment}" if e.fragment else ""
        link = f'<a href="{escape(relative_url(base, e.href) + frag)}">{escape(e.title, quote=False)}</a>'
        if e.children:
            lines.append(f"{indent}  <li>{link}")
            lines.append(_ol_html(base, e.children, indent + "    "))
            lines.append(f"{indent}  </li>")
        else:
            lines.append(f"{indent}  <li>{link}</li>")
    lines.append(f"{indent}</ol>")
    return "\n".join(lines)


def _build_nav(href: str, old: bytes, entries: list[TocEntry], lang: str) -> str:
    ol = _ol_html(href, entries, "    ")
    # 尽量保留原导航文档中的其他部分（如 landmarks），只替换 toc
    if old.strip():
        try:
            tree = etree.fromstring(old, xml_parser()).getroottree()
            nav = _find_toc_nav(tree.getroot())
            if nav is not None:
                for child in list(nav):
                    if _local(child.tag) == "ol":
                        nav.remove(child)
                new_ol = etree.fromstring(
                    f'<wrap xmlns="{NS["xhtml"]}">{ol}</wrap>'.encode("utf-8"), xml_parser()
                )[0]
                new_ol.tail = "\n  "
                nav.append(new_ol)
                return etree.tostring(tree, encoding="utf-8", xml_declaration=True).decode("utf-8")
        except etree.XMLSyntaxError:
            pass
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!DOCTYPE html>\n"
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"'
        f' lang="{escape(lang)}" xml:lang="{escape(lang)}">\n'
        "<head>\n  <title>目录</title>\n</head>\n<body>\n"
        '  <nav epub:type="toc" id="toc">\n    <h1>目录</h1>\n'
        f"{ol}\n"
        "  </nav>\n</body>\n</html>\n"
    )


def _build_ncx(book: Book, href: str, entries: list[TocEntry]) -> str:
    order = 0

    def depth(items: list[TocEntry]) -> int:
        return 1 + max((depth(e.children) for e in items), default=0) if items else 0

    def points(items: list[TocEntry], indent: str) -> str:
        nonlocal order
        out = []
        for e in items:
            order += 1
            frag = f"#{e.fragment}" if e.fragment else ""
            src = escape(relative_url(href, e.href) + frag)
            out.append(f'{indent}<navPoint id="navPoint-{order}" playOrder="{order}">')
            out.append(f"{indent}  <navLabel><text>{escape(e.title, quote=False)}</text></navLabel>")
            out.append(f'{indent}  <content src="{src}"/>')
            if e.children:
                out.append(points(e.children, indent + "  "))
            out.append(f"{indent}</navPoint>")
        return "\n".join(out)

    uid = book.identifier or f"urn:uuid:{uuid.uuid4()}"
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
        "  <head>\n"
        f'    <meta name="dtb:uid" content="{escape(uid)}"/>\n'
        f'    <meta name="dtb:depth" content="{max(depth(entries), 1)}"/>\n'
        '    <meta name="dtb:totalPageCount" content="0"/>\n'
        '    <meta name="dtb:maxPageNumber" content="0"/>\n'
        "  </head>\n"
        f"  <docTitle><text>{escape(book.title or '未命名', quote=False)}</text></docTitle>\n"
        "  <navMap>\n"
        f"{points(entries, '    ')}\n"
        "  </navMap>\n"
        "</ncx>\n"
    )


def flatten(entries: list[TocEntry]):
    for e in entries:
        yield e
        yield from flatten(e.children)

