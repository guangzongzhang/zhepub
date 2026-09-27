"""EPUB 书籍模型：读取、修改、保存。

一本书在内存中由以下部分组成：
- resources：清单（manifest）里的全部文件，按清单顺序保存，键为相对 OPF 目录的路径；
- spine：阅读顺序；
- opf_root：OPF 的 XML 树，只用来保存元数据等其余内容，清单与书脊在保存时重新生成；
- extra_files：压缩包中不在清单里的文件（如 META-INF 下的 encryption.xml），原样保留。
"""

from __future__ import annotations

import copy
import datetime as _dt
import html.entities
import os
import posixpath
import re
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

from lxml import etree

NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
    "ncx": "http://www.daisy.org/z3986/2005/ncx/",
    "xhtml": "http://www.w3.org/1999/xhtml",
    "epub": "http://www.idpf.org/2007/ops",
}
OPF = "{%s}" % NS["opf"]
DC = "{%s}" % NS["dc"]

MEDIA_TYPES = {
    ".xhtml": "application/xhtml+xml",
    ".html": "application/xhtml+xml",
    ".htm": "application/xhtml+xml",
    ".css": "text/css",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ncx": "application/x-dtbncx+xml",
    ".js": "application/javascript",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "video/mp4",
    ".smil": "application/smil+xml",
    ".xml": "application/xml",
    ".txt": "text/plain",
}

# 各类文件在新建/导入时默认放入的文件夹（相对 OPF 目录），与 Sigil 的习惯一致
FOLDERS = {
    "text": "Text",
    "style": "Styles",
    "image": "Images",
    "font": "Fonts",
    "audio": "Audio",
    "video": "Video",
    "misc": "Misc",
}

CATEGORY_NAMES = {
    "text": "文本",
    "style": "样式",
    "image": "图片",
    "font": "字体",
    "audio": "音频",
    "video": "视频",
    "misc": "其他",
}

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_ATTR_URL_RE = re.compile(
    r"""(?P<pre>\b(?:href|src|xlink:href|poster|data)\s*=\s*)(?P<q>["'])(?P<url>.*?)(?P=q)""",
    re.S,
)
_CSS_URL_RE = re.compile(r"""(?P<pre>url\(\s*)(?P<q>["']?)(?P<url>[^"')]*?)(?P=q)(?P<post>\s*\))""")
_CSS_IMPORT_RE = re.compile(r"""(?P<pre>@import\s+)(?P<q>["'])(?P<url>.*?)(?P=q)""")
_XML_DECL_ENC_RE = re.compile(r"""^(\s*<\?xml[^>]*?encoding\s*=\s*)(["'])[^"']*\2""")


class EpubError(Exception):
    """无法打开或保存 EPUB 时抛出，消息面向用户。"""


def guess_media_type(href: str) -> str:
    return MEDIA_TYPES.get(posixpath.splitext(href)[1].lower(), "application/octet-stream")


def category_of(media_type: str) -> str:
    mt = media_type.lower()
    if mt in ("application/xhtml+xml", "text/html"):
        return "text"
    if mt == "text/css":
        return "style"
    if mt.startswith("image/"):
        return "image"
    if mt.startswith("font/") or "font" in mt or mt in (
        "application/vnd.ms-opentype",
        "application/x-font-ttf",
    ):
        return "font"
    if mt.startswith("audio/"):
        return "audio"
    if mt.startswith("video/"):
        return "video"
    return "misc"


def decode_text(data: bytes) -> str:
    """解码文本文件。优先 UTF-8，其次按 XML 声明，最后按 GB18030（兼容 GBK/GB2312）。"""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    m = re.match(rb"""\s*<\?xml[^>]*encoding\s*=\s*["']([A-Za-z0-9_.-]+)["']""", data)
    if m:
        try:
            return data.decode(m.group(1).decode("ascii"))
        except (LookupError, UnicodeDecodeError):
            pass
    try:
        return data.decode("gb18030")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def is_external(url: str) -> bool:
    return bool(_SCHEME_RE.match(url)) or url.startswith("/")


def resolve(base_href: str, url: str) -> str:
    """把 base_href 所在文件中的相对链接解析为相对 OPF 目录的路径（去掉 # 片段）。"""
    path = unquote(url.split("#", 1)[0])
    return posixpath.normpath(posixpath.join(posixpath.dirname(base_href), path))


def relative_url(from_href: str, to_href: str) -> str:
    """从 from_href 所在文件指向 to_href 的相对链接（已做 URL 编码）。"""
    rel = posixpath.relpath(to_href, posixpath.dirname(from_href) or ".")
    return quote(rel, safe="/")


def rewrite_urls(text: str, old_base: str, new_base: str, remap) -> str:
    """重写 text 中所有本地链接。

    old_base / new_base：该文件改名前后的路径（相对 OPF 目录）；
    remap(target, fragment) -> 新的目标路径，用于目标文件改名或内容移动。
    未受影响的链接保持原样。
    """
    old_dir = posixpath.dirname(old_base)
    new_dir = posixpath.dirname(new_base) or "."

    def fix(url: str) -> str:
        if not url or url.startswith("#") or is_external(url):
            return url
        path, sep, frag = url.partition("#")
        if not path:
            return url
        target = posixpath.normpath(posixpath.join(old_dir, unquote(path)))
        new_target = remap(target, frag)
        if new_target == target and old_base == new_base:
            return url
        return quote(posixpath.relpath(new_target, new_dir), safe="/") + sep + frag

    def sub(m: re.Match) -> str:
        new = fix(m.group("url"))
        if new == m.group("url"):
            return m.group(0)
        post = m.groupdict().get("post") or ""
        return f"{m.group('pre')}{m.group('q')}{new}{m.group('q')}{post}"

    for regex in (_ATTR_URL_RE, _CSS_URL_RE, _CSS_IMPORT_RE):
        text = regex.sub(sub, text)
    return text


def find_urls(text: str) -> list[tuple[str, int]]:
    """列出 text 中的链接及其所在行号。"""
    out = []
    for regex in (_ATTR_URL_RE, _CSS_URL_RE, _CSS_IMPORT_RE):
        for m in regex.finditer(text):
            out.append((m.group("url"), text.count("\n", 0, m.start()) + 1))
    return out


def xml_parser(recover: bool = False) -> etree.XMLParser:
    # 不加载外部 DTD、不联网；XHTML 1.1 文件中的 &nbsp; 等实体保持不解析
    return etree.XMLParser(
        load_dtd=False, no_network=True, resolve_entities=False, recover=recover, huge_tree=True
    )


_ENTITY_RE = re.compile(r"&([A-Za-z][A-Za-z0-9]*);")
_XML_ENTITIES = {"amp", "lt", "gt", "quot", "apos"}


def html_entities_to_numeric(text: str) -> str:
    """把 &nbsp; 等 HTML 命名实体改写为数字形式，使其成为合法 XML。"""

    def sub(m: re.Match) -> str:
        name = m.group(1)
        if name in _XML_ENTITIES:
            return m.group(0)
        char = html.entities.html5.get(name + ";")
        return "".join(f"&#{ord(c)};" for c in char) if char else m.group(0)

    return _ENTITY_RE.sub(sub, text)


def parse_xml(data: bytes) -> etree._Element:
    """解析 XHTML/XML；若只是用了 HTML 命名实体（如 &nbsp;），自动兼容。"""
    try:
        return etree.fromstring(data, xml_parser())
    except etree.XMLSyntaxError as e:
        if "Entity" not in str(e):
            raise
    fixed = html_entities_to_numeric(decode_text(data))
    fixed = _XML_DECL_ENC_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}utf-8{m.group(2)}", fixed)
    return etree.fromstring(fixed.encode("utf-8"), xml_parser())


def uses_html_entities(text: str) -> list[str]:
    return sorted({m.group(1) for m in _ENTITY_RE.finditer(text) if m.group(1) not in _XML_ENTITIES})


def make_ncname(text: str) -> str:
    name = re.sub(r"[^\w.-]", "_", text)
    if not name or not (name[0].isalpha() or name[0] == "_"):
        name = "x" + name
    return name


@dataclass
class Resource:
    href: str  # 相对 OPF 目录，未编码的 POSIX 路径
    id: str
    media_type: str
    data: bytes
    properties: str = ""

    @property
    def category(self) -> str:
        return category_of(self.media_type)

    @property
    def filename(self) -> str:
        return posixpath.basename(self.href)

    @property
    def is_text(self) -> bool:
        mt = self.media_type
        return (
            self.category in ("text", "style")
            or mt.endswith("+xml")
            or mt.endswith("/xml")
            or mt.startswith("text/")
            or mt == "application/javascript"
        )

    @property
    def is_nav(self) -> bool:
        return "nav" in self.properties.split()

    def text(self) -> str:
        return decode_text(self.data)

    def set_text(self, text: str) -> None:
        # 统一以 UTF-8 保存，同步修正 XML 声明中的编码
        text = _XML_DECL_ENC_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}utf-8{m.group(2)}", text)
        self.data = text.encode("utf-8")


@dataclass
class SpineItem:
    href: str
    linear: bool = True
    properties: str = ""


@dataclass
class Issue:
    level: str  # "错误" 或 "警告"
    href: str
    line: int
    message: str


class Book:
    def __init__(self) -> None:
        self.path: Path | None = None
        self.opf_path = "OEBPS/content.opf"  # 压缩包内路径
        self.opf_root: etree._Element | None = None
        self.resources: dict[str, Resource] = {}
        self.spine: list[SpineItem] = []
        self.extra_files: dict[str, bytes] = {}
        self.load_warnings: list[str] = []
        self.modified = False

    # ------------------------------------------------------------------ 基本属性
    @property
    def version(self) -> str:
        return self.opf_root.get("version", "2.0") if self.opf_root is not None else "3.0"

    @property
    def is_epub3(self) -> bool:
        return self.version.startswith("3")

    @property
    def opf_dir(self) -> str:
        return posixpath.dirname(self.opf_path)

    def zip_path(self, href: str) -> str:
        return posixpath.normpath(posixpath.join(self.opf_dir, href)) if self.opf_dir else href

    def by_category(self, category: str) -> list[Resource]:
        return [r for r in self.resources.values() if r.category == category]

    def text_documents(self) -> list[Resource]:
        """文本文件：先按书脊顺序，再列出不在书脊中的。"""
        ordered = [self.resources[s.href] for s in self.spine if s.href in self.resources]
        seen = {r.href for r in ordered}
        ordered += [r for r in self.by_category("text") if r.href not in seen]
        return ordered

    def spine_index(self, href: str) -> int:
        for i, item in enumerate(self.spine):
            if item.href == href:
                return i
        return -1

    def nav_resource(self) -> Resource | None:
        return next((r for r in self.resources.values() if r.is_nav), None)

    def ncx_resource(self) -> Resource | None:
        return next(
            (r for r in self.resources.values() if r.media_type == "application/x-dtbncx+xml"),
            None,
        )

    # ------------------------------------------------------------------ 打开
    @classmethod
    def open(cls, path: str | os.PathLike) -> Book:
        book = cls()
        book.path = Path(path)
        try:
            zf = zipfile.ZipFile(book.path)
        except (zipfile.BadZipFile, OSError) as e:
            raise EpubError(f"无法打开文件（不是有效的 EPUB/ZIP）：{e}") from e
        with zf:
            names = {info.filename for info in zf.infolist() if not info.is_dir()}
            if "META-INF/container.xml" not in names:
                raise EpubError("缺少 META-INF/container.xml，不是有效的 EPUB。")
            try:
                container = etree.fromstring(zf.read("META-INF/container.xml"), xml_parser())
            except etree.XMLSyntaxError as e:
                raise EpubError(f"container.xml 解析失败：{e}") from e
            rootfile = container.find(".//container:rootfile", NS)
            if rootfile is None or not rootfile.get("full-path"):
                raise EpubError("container.xml 中没有找到 OPF 文件。")
            book.opf_path = rootfile.get("full-path")
            if book.opf_path not in names:
                raise EpubError(f"找不到 OPF 文件：{book.opf_path}")
            try:
                book.opf_root = etree.fromstring(zf.read(book.opf_path), xml_parser())
            except etree.XMLSyntaxError as e:
                raise EpubError(f"OPF 文件解析失败：{e}") from e

            manifest = book.opf_root.find("opf:manifest", NS)
            used = {"mimetype", "META-INF/container.xml", book.opf_path}
            id_to_href: dict[str, str] = {}
            for item in manifest.findall("opf:item", NS) if manifest is not None else []:
                raw = item.get("href", "")
                if not raw or is_external(raw):
                    book.load_warnings.append(f"忽略外部资源：{raw}")
                    continue
                href = posixpath.normpath(unquote(raw.split("#")[0]))
                zpath = book.zip_path(href)
                if zpath not in names:
                    book.load_warnings.append(f"清单中的文件不存在，已忽略：{href}")
                    continue
                rid = item.get("id") or make_ncname(posixpath.basename(href))
                book.resources[href] = Resource(
                    href=href,
                    id=rid,
                    media_type=item.get("media-type") or guess_media_type(href),
                    data=zf.read(zpath),
                    properties=item.get("properties", ""),
                )
                id_to_href[rid] = href
                used.add(zpath)

            spine = book.opf_root.find("opf:spine", NS)
            for ref in spine.findall("opf:itemref", NS) if spine is not None else []:
                href = id_to_href.get(ref.get("idref", ""))
                if href is None:
                    book.load_warnings.append(f"书脊引用了不存在的条目：{ref.get('idref')}")
                    continue
                book.spine.append(
                    SpineItem(href, ref.get("linear", "yes") != "no", ref.get("properties", ""))
                )

            for name in sorted(names - used):
                book.extra_files[name] = zf.read(name)
        return book

    # ------------------------------------------------------------------ 新建
    @classmethod
    def new(cls, title: str = "未命名", language: str = "zh-CN") -> Book:
        from . import templates

        book = cls()
        ident = f"urn:uuid:{uuid.uuid4()}"
        book.opf_root = etree.fromstring(
            templates.OPF.format(
                title=_xml_escape(title), language=language, identifier=ident
            ).encode("utf-8"),
            xml_parser(),
        )
        book.add_resource("Styles/style.css", templates.DEFAULT_CSS.encode("utf-8"))
        book.add_resource(
            "Text/Section0001.xhtml",
            templates.xhtml(title, f"<h1>{_xml_escape(title)}</h1>\n<p></p>", language,
                            ["../Styles/style.css"]).encode("utf-8"),
        )
        from .toc import write_toc

        write_toc(book, [])
        book.modified = False
        return book

    # ------------------------------------------------------------------ 保存
    def build_opf(self) -> bytes:
        root = copy.deepcopy(self.opf_root)
        for tag in ("manifest", "spine"):
            old = root.find(f"opf:{tag}", NS)
            if old is not None:
                attrs = dict(old.attrib)
                index = list(root).index(old)
                root.remove(old)
            else:
                attrs, index = {}, len(root)
            new = etree.Element(OPF + tag, attrs)
            new.text = "\n    "
            root.insert(index, new)

        manifest = root.find("opf:manifest", NS)
        for res in self.resources.values():
            attrs = {"id": res.id, "href": quote(res.href, safe="/"), "media-type": res.media_type}
            if res.properties:
                attrs["properties"] = res.properties
            etree.SubElement(manifest, OPF + "item", attrs).tail = "\n    "
        spine = root.find("opf:spine", NS)
        ncx = self.ncx_resource()
        if ncx is not None:
            spine.set("toc", ncx.id)
        else:
            spine.attrib.pop("toc", None)
        for item in self.spine:
            res = self.resources.get(item.href)
            if res is None:
                continue
            attrs = {"idref": res.id}
            if not item.linear:
                attrs["linear"] = "no"
            if item.properties:
                attrs["properties"] = item.properties
            etree.SubElement(spine, OPF + "itemref", attrs).tail = "\n    "
        for parent in (manifest, spine):
            if len(parent):
                parent[-1].tail = "\n  "

        guide = root.find("opf:guide", NS)
        if guide is not None:
            for ref in list(guide):
                href = posixpath.normpath(unquote(ref.get("href", "").split("#")[0]))
                if href not in self.resources:
                    guide.remove(ref)
            if not len(guide):
                root.remove(guide)

        if self.is_epub3:
            metadata = root.find("opf:metadata", NS)
            mod = metadata.find("opf:meta[@property='dcterms:modified']", NS)
            if mod is None:
                mod = etree.SubElement(metadata, OPF + "meta", {"property": "dcterms:modified"})
            mod.text = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return etree.tostring(root, encoding="utf-8", xml_declaration=True)

    def save(self, path: str | os.PathLike | None = None) -> None:
        target = Path(path) if path else self.path
        if target is None:
            raise EpubError("尚未指定保存位置。")
        container = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
            "  <rootfiles>\n"
            f'    <rootfile full-path="{self.opf_path}" media-type="application/oebps-package+xml"/>\n'
            "  </rootfiles>\n"
            "</container>\n"
        )
        opf = self.build_opf()
        # 先写临时文件再替换，避免保存失败时损坏原文件
        fd, tmp = tempfile.mkstemp(suffix=".epub", dir=str(target.parent))
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(zipfile.ZipInfo("mimetype"), b"application/epub+zip",
                            compress_type=zipfile.ZIP_STORED)
                zf.writestr("META-INF/container.xml", container)
                for name, data in self.extra_files.items():
                    if name != "META-INF/container.xml":
                        zf.writestr(name, data)
                zf.writestr(self.opf_path, opf)
                for res in self.resources.values():
                    zf.writestr(self.zip_path(res.href), res.data)
            os.replace(tmp, target)
        except OSError as e:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise EpubError(f"保存失败：{e}") from e
        self.path = target
        self.modified = False

    # ------------------------------------------------------------------ 资源管理
    def unique_id(self, base: str) -> str:
        base = make_ncname(base)
        ids = {r.id for r in self.resources.values()}
        ids |= {el.get("id") for el in self.opf_root.iter() if el.get("id")}
        rid, n = base, 1
        while rid in ids:
            n += 1
            rid = f"{base}_{n}"
        return rid

    def unique_href(self, href: str) -> str:
        stem, ext = posixpath.splitext(href)
        lowered = {h.lower() for h in self.resources}
        candidate, n = href, 1
        while candidate.lower() in lowered:
            n += 1
            candidate = f"{stem}_{n}{ext}"
        return candidate

    def add_resource(
        self,
        href: str,
        data: bytes,
        media_type: str | None = None,
        spine_index: int | None = None,
        properties: str = "",
    ) -> Resource:
        href = self.unique_href(posixpath.normpath(href))
        mt = media_type or guess_media_type(href)
        res = Resource(href, self.unique_id(posixpath.basename(href)), mt, data, properties)
        self.resources[href] = res
        if res.category == "text" and not res.is_nav:
            item = SpineItem(href)
            if spine_index is None:
                self.spine.append(item)
            else:
                self.spine.insert(spine_index, item)
        self.modified = True
        return res

    def add_file(self, path: str | os.PathLike) -> Resource:
        path = Path(path)
        mt = guess_media_type(path.name)
        folder = FOLDERS[category_of(mt)]
        return self.add_resource(f"{folder}/{path.name}", path.read_bytes(), mt)

    def new_section(self, after_href: str | None = None, title: str = "", body: str = "<p></p>"
                    ) -> Resource:
        from . import templates

        n = 1
        existing = {h.lower() for h in self.resources}
        while f"text/section{n:04d}.xhtml" in existing:
            n += 1
        href = f"Text/Section{n:04d}.xhtml"
        styles = [relative_url(href, r.href) for r in self.by_category("style")]
        text = templates.xhtml(title, body, self.language or "zh-CN", styles)
        index = self.spine_index(after_href) + 1 if after_href else None
        if index == 0:
            index = None
        return self.add_resource(href, text.encode("utf-8"), spine_index=index)

    def remove_resource(self, href: str) -> None:
        res = self.resources.pop(href, None)
        if res is None:
            return
        self.spine = [s for s in self.spine if s.href != href]
        metadata = self.opf_root.find("opf:metadata", NS)
        for meta in metadata.findall("opf:meta[@name='cover']", NS):
            if meta.get("content") == res.id:
                metadata.remove(meta)
        self.modified = True

    def rename_resource(self, old: str, new: str) -> Resource:
        """改名/移动文件，并更新全书中指向它的链接。"""
        new = posixpath.normpath(new)
        if old not in self.resources:
            raise KeyError(old)
        if new == old:
            return self.resources[old]
        if new.lower() in {h.lower() for h in self.resources if h != old}:
            raise EpubError(f"已存在同名文件：{new}")
        self.relocate({old: new})
        return self.resources[new]

    def relocate(self, mapping: dict[str, str], fragment_map=None) -> None:
        """批量改名并修正所有链接。

        mapping：旧路径 -> 新路径；
        fragment_map(target, fragment) -> 新目标路径或 None，用于拆分/合并文件时
        按锚点把链接指向内容的新位置。
        """

        def remap(target: str, frag: str) -> str:
            if fragment_map is not None and frag:
                moved = fragment_map(target, frag)
                if moved:
                    return moved
            return mapping.get(target, target)

        new_resources: dict[str, Resource] = {}
        for href, res in self.resources.items():
            new_href = mapping.get(href, href)
            if res.is_text:
                text = res.text()
                new_text = rewrite_urls(text, href, new_href, remap)
                if new_text != text:
                    res.set_text(new_text)
            res.href = new_href
            new_resources[new_href] = res
        self.resources = new_resources
        for item in self.spine:
            item.href = mapping.get(item.href, item.href)
        guide = self.opf_root.find("opf:guide", NS)
        for ref in guide if guide is not None else []:
            raw = ref.get("href", "")
            path, sep, frag = raw.partition("#")
            target = posixpath.normpath(unquote(path)) if path else ""
            new_target = remap(target, frag)
            if new_target != target:
                ref.set("href", quote(new_target, safe="/") + sep + frag)
        self.modified = True

    def move_in_spine(self, href: str, delta: int) -> bool:
        i = self.spine_index(href)
        j = i + delta
        if i < 0 or not 0 <= j < len(self.spine):
            return False
        self.spine[i], self.spine[j] = self.spine[j], self.spine[i]
        self.modified = True
        return True

    # ------------------------------------------------------------------ 元数据
    def _metadata(self) -> etree._Element:
        md = self.opf_root.find("opf:metadata", NS)
        if md is None:
            md = etree.Element(OPF + "metadata", nsmap={"dc": NS["dc"], "opf": NS["opf"]})
            self.opf_root.insert(0, md)
        return md

    def get_dc(self, name: str) -> list[str]:
        return [(el.text or "").strip() for el in self._metadata().findall(f"dc:{name}", NS)]

    def get_first(self, name: str) -> str:
        values = self.get_dc(name)
        return values[0] if values else ""

    def set_dc(self, name: str, values: list[str]) -> None:
        md = self._metadata()
        values = [v.strip() for v in values if v and v.strip()]
        existing = md.findall(f"dc:{name}", NS)
        if name == "identifier":
            # 保留被 unique-identifier 引用的那个元素，只改它的值
            uid = self.opf_root.get("unique-identifier")
            keep = next((el for el in existing if el.get("id") == uid), None)
            if keep is not None and values:
                keep.text = values[0]
                return
        insert_at = md.index(existing[0]) if existing else len(md)
        for el in existing:
            eid = el.get("id")
            if eid:
                for meta in md.findall(f"opf:meta[@refines='#{eid}']", NS):
                    md.remove(meta)
            md.remove(el)
        for i, value in enumerate(values):
            el = etree.Element(DC + name)
            el.text = value
            el.tail = "\n    "
            md.insert(insert_at + i, el)
        self.modified = True

    @property
    def title(self) -> str:
        return self.get_first("title")

    @property
    def language(self) -> str:
        return self.get_first("language")

    @property
    def identifier(self) -> str:
        uid = self.opf_root.get("unique-identifier")
        for el in self._metadata().findall("dc:identifier", NS):
            if el.get("id") == uid:
                return (el.text or "").strip()
        return self.get_first("identifier")

    def cover_href(self) -> str | None:
        for res in self.resources.values():
            if "cover-image" in res.properties.split():
                return res.href
        meta = self._metadata().find("opf:meta[@name='cover']", NS)
        if meta is not None:
            for res in self.resources.values():
                if res.id == meta.get("content"):
                    return res.href
        return None

    def set_cover(self, href: str) -> None:
        target = self.resources[href]
        for res in self.resources.values():
            props = [p for p in res.properties.split() if p != "cover-image"]
            if res is target and self.is_epub3:
                props.append("cover-image")
            res.properties = " ".join(props)
        md = self._metadata()
        meta = md.find("opf:meta[@name='cover']", NS)
        if meta is None:
            meta = etree.SubElement(md, OPF + "meta", {"name": "cover"})
        meta.set("content", target.id)
        self.modified = True

    # ------------------------------------------------------------------ 校验
    def validate(self) -> list[Issue]:
        issues: list[Issue] = []
        for name in ("title", "language", "identifier"):
            if not self.get_first(name):
                issues.append(Issue("错误", "content.opf", 0, f"元数据缺少 dc:{name}"))
        if not self.spine:
            issues.append(Issue("错误", "content.opf", 0, "书脊为空，没有可阅读的内容"))
        if self.is_epub3 and self.nav_resource() is None:
            issues.append(Issue("错误", "content.opf", 0, "EPUB 3 缺少导航文档（nav）"))

        ids_cache: dict[str, set[str] | None] = {}

        def ids_of(href: str) -> set[str] | None:
            if href not in ids_cache:
                try:
                    root = parse_xml(self.resources[href].data)
                    ids_cache[href] = {el.get("id") for el in root.iter() if el.get("id")}
                except etree.XMLSyntaxError:
                    ids_cache[href] = None
            return ids_cache[href]

        referenced: set[str] = set()
        spine_hrefs = {s.href for s in self.spine}
        for res in self.resources.values():
            if not res.is_text:
                continue
            text = res.text()
            if res.category == "text" or res.media_type in (
                "application/x-dtbncx+xml",
                "image/svg+xml",
            ):
                try:
                    parse_xml(res.data)
                except etree.XMLSyntaxError as e:
                    issues.append(Issue("错误", res.href, e.lineno or 0, f"XML 格式错误：{e.msg}"))
                else:
                    names = uses_html_entities(text)
                    if names and "DTD XHTML 1." not in text[:600]:
                        shown = "、".join(f"&{n};" for n in names[:5])
                        issues.append(Issue("警告", res.href, 0,
                                            f"使用了 XML 中未定义的 HTML 实体 {shown}，部分阅读器会报错"))
            if res.category == "text" and res.href not in spine_hrefs and not res.is_nav:
                issues.append(Issue("警告", res.href, 0, "文本文件不在书脊（阅读顺序）中"))
            for url, line in find_urls(text):
                if not url or url.startswith("#") or is_external(url):
                    continue
                target = resolve(res.href, url)
                referenced.add(target)
                if target not in self.resources:
                    hint = next((h for h in self.resources if h.lower() == target.lower()), None)
                    msg = f"链接的文件不存在：{url}"
                    if hint:
                        msg += f"（大小写不一致，实际为 {hint}）"
                    issues.append(Issue("错误", res.href, line, msg))
                    continue
                frag = url.partition("#")[2]
                if frag and self.resources[target].category == "text":
                    ids = ids_of(target)
                    if ids is not None and unquote(frag) not in ids:
                        issues.append(Issue("警告", res.href, line, f"锚点不存在：{url}"))
        cover = self.cover_href()
        for res in self.resources.values():
            if res.category in ("image", "font") and res.href not in referenced and res.href != cover:
                issues.append(Issue("警告", res.href, 0, "文件没有被任何地方引用"))
        return issues


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
