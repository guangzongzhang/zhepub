"""新建文件用的模板。"""

from __future__ import annotations

from html import escape

OPF = """<?xml version="1.0" encoding="utf-8"?>
<package version="3.0" unique-identifier="BookId" xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">{identifier}</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:language>{language}</dc:language>
  </metadata>
  <manifest>
  </manifest>
  <spine>
  </spine>
</package>
"""

DEFAULT_CSS = """/* 中文排版默认样式 */
body {
  font-family: "Songti SC", "SimSun", "Noto Serif CJK SC", "Source Han Serif SC", serif;
  line-height: 1.8;
  text-align: justify;
  margin: 0 0.5em;
}

h1, h2, h3, h4, h5, h6 {
  font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
  text-align: center;
  line-height: 1.4;
  margin: 1.5em 0 1em;
}

h1 { font-size: 1.6em; }
h2 { font-size: 1.4em; }
h3 { font-size: 1.2em; }

p {
  text-indent: 2em;
  margin: 0 0 0.4em;
}

img {
  max-width: 100%;
}
"""


def xhtml(title: str, body: str, language: str = "zh-CN", stylesheets: list[str] = ()) -> str:
    links = "".join(
        f'  <link href="{escape(href)}" rel="stylesheet" type="text/css"/>\n' for href in stylesheets
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!DOCTYPE html>\n"
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"'
        f' xml:lang="{escape(language)}" lang="{escape(language)}">\n'
        "<head>\n"
        f"  <title>{escape(title, quote=False)}</title>\n"
        f"{links}"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )
