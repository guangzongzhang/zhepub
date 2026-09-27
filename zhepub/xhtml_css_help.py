"""XHTML 和 CSS 语法参考数据，供帮助对话框使用。

数据结构：{分类名: [条目, ...]}
每条至少包含 name / desc / example 三个字段。
"""

from __future__ import annotations

# ============================================================ XHTML
XHTML_REFERENCE: dict[str, list[dict]] = {
    "文档结构": [
        {
            "name": "<html>",
            "desc": "XHTML 根元素，必须声明 XML 命名空间。",
            "example": '<html xmlns="http://www.w3.org/1999/xhtml" lang="zh-CN">\n  ...\n</html>',
        },
        {
            "name": "<head>",
            "desc": "头部容器，包含元数据、样式表引用等不显示的内容。",
            "example": "<head>\n  <title>书名</title>\n  <link rel=\"stylesheet\" href=\"style.css\"/>\n</head>",
        },
        {
            "name": "<body>",
            "desc": "正文主体，所有可见内容放于此。",
            "example": "<body>\n  <h1>第一章</h1>\n  <p>……</p>\n</body>",
        },
        {
            "name": "<title>",
            "desc": "文档标题，EPUB 中通常作为章节显示名。",
            "example": "<title>第一章 初遇</title>",
        },
        {
            "name": "<meta>",
            "desc": "元数据，必须用 self-closing 形式。常用 http-equiv 声明内容类型。",
            "example": '<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>',
        },
        {
            "name": "<!DOCTYPE>",
            "desc": "XHTML 1.1 文档类型声明，EPUB 2 文件通常用此版本。",
            "example": '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">',
        },
        {
            "name": "<?xml?>",
            "desc": "XML 声明，必须是文件第一行，指定编码。",
            "example": '<?xml version="1.0" encoding="utf-8"?>',
        },
    ],
    "文本与段落": [
        {
            "name": "<p>",
            "desc": "段落，最常用的块级元素。",
            "example": "<p>这是一段正文。</p>",
        },
        {
            "name": "<br/>",
            "desc": "换行，self-closing。XHTML 必须用斜杠闭合。",
            "example": "第一行<br/>第二行",
        },
        {
            "name": "<h1> ~ <h6>",
            "desc": "六级标题，h1 最高。EPUB 目录通常基于 h1~h6 自动生成。",
            "example": "<h1>第一章</h1>\n<h2>1.1 节</h2>",
        },
        {
            "name": "<hr/>",
            "desc": "水平分隔线。",
            "example": "<p>上文</p>\n<hr/>\n<p>下文</p>",
        },
        {
            "name": "<blockquote>",
            "desc": "引用段落，浏览器默认缩进。",
            "example": "<blockquote>这是引用内容。</blockquote>",
        },
        {
            "name": "<pre>",
            "desc": "预格式化文本，保留空格和换行，常用于显示代码。",
            "example": "<pre>line1\n  line2</pre>",
        },
        {
            "name": "<span>",
            "desc": "通用行内容器，不带语义，配合 class 或 style 使用。",
            "example": '<span class="note">注释</span>',
        },
        {
            "name": "<div>",
            "desc": "通用块容器，不带语义，用于分组和布局。",
            "example": '<div class="chapter">\n  ...\n</div>',
        },
    ],
    "文本语义": [
        {
            "name": "<strong>",
            "desc": "重要内容，默认加粗。",
            "example": "<strong>注意</strong>：禁止转载",
        },
        {
            "name": "<em>",
            "desc": "强调内容，默认斜体。",
            "example": "<em>需要重点理解</em>",
        },
        {
            "name": "<b> / <i>",
            "desc": "纯样式加粗/斜体，HTML5 中保留了语义。EPUB 中建议优先用 strong/em。",
            "example": "<b>加粗</b> <i>斜体</i>",
        },
        {
            "name": "<u>",
            "desc": "下划线。",
            "example": "<u>带下划线的文字</u>",
        },
        {
            "name": "<s> / <del>",
            "desc": "删除线。",
            "example": "<s>原价 100</s> 现 50",
        },
        {
            "name": "<sub> / <sup>",
            "desc": "下标 / 上标，常用于公式或注释。",
            "example": "H<sub>2</sub>O · X<sup>2</sup>",
        },
        {
            "name": "<code>",
            "desc": "行内代码，等宽字体。",
            "example": "<code>&lt;p&gt;</code>",
        },
        {
            "name": "<cite>",
            "desc": "作品名引用，常斜体。",
            "example": "<cite>红楼梦</cite>",
        },
        {
            "name": "<q>",
            "desc": "行内短引用，浏览器自动加引号。",
            "example": "<q>他说</q>",
        },
        {
            "name": "<abbr>",
            "desc": "缩写，title 属性提供全称。",
            "example": '<abbr title="HyperText Markup Language">HTML</abbr>',
        },
    ],
    "链接与图片": [
        {
            "name": "<a>",
            "desc": "超链接或锚点。href 指向目标文件或 #id。",
            "example": '<a href="chapter2.xhtml">下一章</a>\n<a href="#section1">跳到本页锚点</a>',
        },
        {
            "name": "<img/>",
            "desc": "插入图片。alt 必填，提供替代文字。src 可以是书内相对路径。",
            "example": '<img alt="封面" src="../Images/cover.jpg"/>',
        },
        {
            "name": "<map> / <area>",
            "desc": "图像地图，定义可点击区域。",
            "example": '<map name="nav">\n  <area shape="rect" coords="0,0,50,50" href="a.xhtml"/>\n</map>',
        },
        {
            "name": "<figure> / <figcaption>",
            "desc": "HTML5 图表和题注。EPUB 3 支持。",
            "example": "<figure>\n  <img src=\"x.png\" alt=\"\"/>\n  <figcaption>图1</figcaption>\n</figure>",
        },
    ],
    "列表": [
        {
            "name": "<ul>",
            "desc": "无序列表，默认实心圆点。",
            "example": "<ul>\n  <li>第一项</li>\n  <li>第二项</li>\n</ul>",
        },
        {
            "name": "<ol>",
            "desc": "有序列表，默认阿拉伯数字。可用 start 指定起始号。",
            "example": '<ol start="1">\n  <li>第一章</li>\n  <li>第二章</li>\n</ol>',
        },
        {
            "name": "<li>",
            "desc": "列表项。",
            "example": "<li>内容</li>",
        },
        {
            "name": "<dl>",
            "desc": "定义列表，含术语和描述对。",
            "example": "<dl>\n  <dt>EPUB</dt>\n  <dd>电子书格式</dd>\n</dl>",
        },
        {
            "name": "<dt> / <dd>",
            "desc": "dl 中术语和描述。",
            "example": "<dt>术语</dt><dd>解释</dd>",
        },
    ],
    "表格": [
        {
            "name": "<table>",
            "desc": "表格容器。",
            "example": '<table border="1">\n  ...\n</table>',
        },
        {
            "name": "<tr>",
            "desc": "表格行。",
            "example": "<tr>\n  <td>A</td><td>B</td>\n</tr>",
        },
        {
            "name": "<td> / <th>",
            "desc": "单元格 / 表头单元格。th 默认居中加粗。",
            "example": "<tr>\n  <th>列1</th><th>列2</th>\n</tr>\n<tr>\n  <td>1</td><td>2</td>\n</tr>",
        },
        {
            "name": "<thead> / <tbody> / <tfoot>",
            "desc": "表头/表体/表脚分组。",
            "example": "<thead><tr><th>名</th></tr></thead>\n<tbody><tr><td>张三</td></tr></tbody>",
        },
        {
            "name": "colspan / rowspan",
            "desc": "单元格跨列 / 跨行属性。",
            "example": '<td colspan="2">合并两列</td>',
        },
        {
            "name": "<caption>",
            "desc": "表格标题，必须紧随 table 开始标签。",
            "example": "<table>\n  <caption>2026 销售</caption>\n  ...\n</table>",
        },
    ],
    "EPUB 专属": [
        {
            "name": "<a epub:type>",
            "desc": "EPUB 3 语义标注，需在 html 标签声明 epub 命名空间。",
            "example": '<html ... xmlns:epub="http://www.idpf.org/2007/ops">\n<a epub:type="noteref" href="#n1">1</a>',
        },
        {
            "name": "<aside epub:type>",
            "desc": "用于注解、脚注、扉页等 EPUB 语义结构。",
            "example": '<aside epub:type="footnote" id="n1">\n  <p>注解内容</p>\n</aside>',
        },
        {
            "name": "<nav epub:type>",
            "desc": "EPUB 3 导航，type 常见值：toc / landmarks / page-list。",
            "example": '<nav epub:type="toc">\n  <ol><li><a href="c1.xhtml">第一章</a></li></ol>\n</nav>',
        },
        {
            "name": "<header> / <footer>",
            "desc": "HTML5 页眉/页脚语义。",
            "example": "<header><h1>第一章</h1></header>",
        },
        {
            "name": "<section> / <article>",
            "desc": "HTML5 章节/文章语义结构。",
            "example": '<section class="chapter">\n  <h1>第一章</h1>\n  <p>……</p>\n</section>',
        },
    ],
    "通用属性": [
        {
            "name": "id",
            "desc": "元素唯一标识，作为锚点跳转目标。",
            "example": '<h2 id="section1">1.1 节</h2>',
        },
        {
            "name": "class",
            "desc": "样式类名，可多个空格分隔。",
            "example": '<p class="note warning">重要</p>',
        },
        {
            "name": "style",
            "desc": "内联样式，慎用，会覆盖外部 CSS。",
            "example": '<p style="text-indent:2em">首行缩进</p>',
        },
        {
            "name": "title",
            "desc": "提示文字，鼠标悬停显示。",
            "example": '<abbr title="扩展">XX</abbr>',
        },
        {
            "name": "lang / xml:lang",
            "desc": "语言代码，EPUB 用于繁简判断和朗读。",
            "example": '<span lang="en">hello</span>',
        },
        {
            "name": "dir",
            "desc": "文字方向：ltr / rtl。",
            "example": '<p dir="rtl">مرحبا</p>',
        },
    ],
    "字符与实体": [
        {
            "name": "&amp;",
            "desc": "& 字符，XHTML 中必须转义。",
            "example": "Tom &amp; Jerry",
        },
        {
            "name": "&lt; / &gt;",
            "desc": "< / > 字符，写代码示例时必须转义。",
            "example": "&lt;p&gt; 不是真的标签",
        },
        {
            "name": "&quot; / &apos;",
            "desc": "双引号 / 单引号。",
            "example": '&quot;引号&quot;',
        },
        {
            "name": "&nbsp;",
            "desc": "不换行空格。",
            "example": "前&nbsp;后",
        },
        {
            "name": "&#xxxx;",
            "desc": "Unicode 数字实体，常用中文标点。",
            "example": "&#8230;（省略号）· &#8212;（破折号）",
        },
        {
            "name": "<![CDATA[...]]>",
            "desc": "XML 原始字符区段，常用于脚本/样式内不被解析。",
            "example": "<style><![CDATA[ body { } ]]></style>",
        },
    ],
}


# ============================================================ CSS
CSS_REFERENCE: dict[str, list[dict]] = {
    "选择器": [
        {
            "name": "元素选择器",
            "desc": "按标签名选择，所有同名标签都生效。",
            "example": "p { color: black; }",
        },
        {
            "name": "类选择器 .",
            "desc": "按 class 选择，可多次复用。",
            "example": ".note { color: gray; }",
        },
        {
            "name": "ID 选择器 #",
            "desc": "按 id 选择，文档内唯一。",
            "example": "#cover { width: 100%; }",
        },
        {
            "name": "后代选择器 空格",
            "desc": "选择某元素内部的所有后代。",
            "example": "div p { font-size: 1em; }",
        },
        {
            "name": "子选择器 >",
            "desc": "只选择直接子元素。",
            "example": "ul > li { list-style: none; }",
        },
        {
            "name": "相邻兄弟 +",
            "desc": "选择紧邻前一个元素之后的同级元素。",
            "example": "h1 + p { margin-top: 0; }",
        },
        {
            "name": "通用兄弟 ~",
            "desc": "选择前一个元素之后的所有同级元素。",
            "example": "h1 ~ p { color: #333; }",
        },
        {
            "name": "属性选择器 []",
            "desc": "按属性值选择。",
            "example": "a[href^=\"http\"] { color: blue; }",
        },
        {
            "name": "伪类 :",
            "desc": "状态或位置选择。",
            "example": "a:hover { text-decoration: underline; }\np:first-child { font-weight: bold; }",
        },
        {
            "name": "伪元素 ::",
            "desc": "元素的某部分，CSS3 推荐双冒号。",
            "example": "p::first-letter { font-size: 2em; }\np::first-line { color: red; }",
        },
        {
            "name": "群组选择器 ,",
            "desc": "多个选择器共用规则。",
            "example": "h1, h2, h3 { color: navy; }",
        },
    ],
    "盒模型": [
        {
            "name": "width / height",
            "desc": "内容区宽高。EPUB 阅读器通常以 % 居多。",
            "example": "img { max-width: 100%; height: auto; }",
        },
        {
            "name": "max-width / min-width",
            "desc": "最大/最小宽度，常用于响应式图片。",
            "example": "figure { max-width: 100%; }",
        },
        {
            "name": "margin",
            "desc": "外边距，可写 1~4 个值（上 右 下 左）。",
            "example": "p { margin: 0 0 0.5em 0; }",
        },
        {
            "name": "padding",
            "desc": "内边距。",
            "example": "div { padding: 1em; }",
        },
        {
            "name": "border",
            "desc": "边框：宽度 样式 颜色。",
            "example": "img { border: 1px solid #ccc; }",
        },
        {
            "name": "border-radius",
            "desc": "圆角半径。",
            "example": ".cover { border-radius: 8px; }",
        },
        {
            "name": "box-sizing",
            "desc": "盒模型计算方式：content-box 默认 / border-box 含边框。",
            "example": "* { box-sizing: border-box; }",
        },
        {
            "name": "box-shadow",
            "desc": "阴影：水平偏移 垂直偏移 模糊 扩散 颜色。",
            "example": ".card { box-shadow: 0 2px 8px rgba(0,0,0,0.2); }",
        },
    ],
    "文本与字体": [
        {
            "name": "font-family",
            "desc": "字体族，多个用逗号分隔，最后通用名兜底。",
            "example": 'body { font-family: "Source Han Serif", "Songti SC", serif; }',
        },
        {
            "name": "font-size",
            "desc": "字号，推荐用 em 或 rem 以适配阅读器缩放。",
            "example": "p { font-size: 1em; }\nh1 { font-size: 1.6em; }",
        },
        {
            "name": "font-weight",
            "desc": "字重：normal / bold / 100-900。",
            "example": "strong { font-weight: 700; }",
        },
        {
            "name": "font-style",
            "desc": "字体样式：normal / italic / oblique。",
            "example": "em { font-style: italic; }",
        },
        {
            "name": "line-height",
            "desc": "行高，无单位值会按字号倍数继承。",
            "example": "p { line-height: 1.6; }",
        },
        {
            "name": "text-indent",
            "desc": "首行缩进。中文段落常用 2em。",
            "example": "p { text-indent: 2em; }",
        },
        {
            "name": "text-align",
            "desc": "对齐：left / right / center / justify。",
            "example": "h1 { text-align: center; }\np { text-align: justify; }",
        },
        {
            "name": "text-decoration",
            "desc": "下划线/删除线：none / underline / line-through。",
            "example": "a { text-decoration: none; }",
        },
        {
            "name": "letter-spacing / word-spacing",
            "desc": "字符间距 / 词间距。",
            "example": "h1 { letter-spacing: 0.1em; }",
        },
        {
            "name": "color",
            "desc": "文字颜色，可用十六进制、rgb、命名色。",
            "example": "p { color: #333; }\n.quote { color: rgb(80,80,80); }",
        },
        {
            "name": "white-space",
            "desc": "空白处理：normal / pre / nowrap / pre-wrap。",
            "example": "pre { white-space: pre-wrap; }",
        },
        {
            "name": "word-break / overflow-wrap",
            "desc": "断词换行，对长 URL/英文有用。",
            "example": "p { word-break: break-all; overflow-wrap: anywhere; }",
        },
    ],
    "颜色与背景": [
        {
            "name": "background-color",
            "desc": "背景色。",
            "example": "body { background-color: #fafafa; }",
        },
        {
            "name": "background-image",
            "desc": "背景图，可用 url() 引用书内图片。",
            "example": '.cover { background-image: url(../Images/bg.jpg); }',
        },
        {
            "name": "background-repeat",
            "desc": "重复方式：repeat / no-repeat / repeat-x / repeat-y。",
            "example": "div { background-repeat: no-repeat; }",
        },
        {
            "name": "background-size",
            "desc": "背景尺寸：cover 充满 / contain 完整显示。",
            "example": "div { background-size: cover; }",
        },
        {
            "name": "background-position",
            "desc": "背景位置，可用关键字或百分比。",
            "example": "div { background-position: center top; }",
        },
        {
            "name": "background 简写",
            "desc": "顺序：color image repeat position / size。",
            "example": "div { background: #fff url(bg.jpg) no-repeat center; }",
        },
        {
            "name": "opacity",
            "desc": "透明度 0~1。",
            "example": ".watermark { opacity: 0.3; }",
        },
        {
            "name": "rgba() / hsl()",
            "desc": "带透明度的颜色 / HSL 色彩。",
            "example": "p { color: rgba(0,0,0,0.7); }\nh1 { color: hsl(0, 80%, 50%); }",
        },
    ],
    "布局": [
        {
            "name": "display",
            "desc": "显示类型：block / inline / inline-block / none / flex / grid。",
            "example": "span { display: block; }\n.hidden { display: none; }",
        },
        {
            "name": "position",
            "desc": "定位：static / relative / absolute / fixed / sticky。",
            "example": ".badge { position: absolute; top: 0; right: 0; }",
        },
        {
            "name": "top / right / bottom / left",
            "desc": "定位偏移，需配合 position 非 static。",
            "example": ".tip { position: relative; top: -0.5em; }",
        },
        {
            "name": "z-index",
            "desc": "层叠顺序，数值大的在上。",
            "example": ".modal { z-index: 100; }",
        },
        {
            "name": "float",
            "desc": "浮动：left / right / none。常用于图文环绕。",
            "example": "img { float: left; margin-right: 1em; }",
        },
        {
            "name": "clear",
            "desc": "清除浮动：left / right / both。",
            "example": "p { clear: both; }",
        },
        {
            "name": "overflow",
            "desc": "溢出处理：visible / hidden / auto / scroll。",
            "example": "pre { overflow: auto; }",
        },
        {
            "name": "display: flex",
            "desc": "弹性布局，子元素沿主轴排列。",
            "example": ".row { display: flex; gap: 1em; }",
        },
        {
            "name": "flex-direction",
            "desc": "主轴方向：row / column / row-reverse / column-reverse。",
            "example": ".col { display: flex; flex-direction: column; }",
        },
        {
            "name": "justify-content",
            "desc": "主轴对齐：flex-start / center / space-between / space-around。",
            "example": ".row { justify-content: space-between; }",
        },
        {
            "name": "align-items",
            "desc": "交叉轴对齐：stretch / center / flex-start / flex-end。",
            "example": ".row { align-items: center; }",
        },
        {
            "name": "gap",
            "desc": "flex / grid 中项与项之间的间距。",
            "example": ".grid { display: grid; gap: 0.5em; }",
        },
        {
            "name": "display: grid",
            "desc": "网格布局。",
            "example": ".gallery { display: grid; grid-template-columns: repeat(3, 1fr); }",
        },
    ],
    "EPUB 分页与中文排版": [
        {
            "name": "page-break-before",
            "desc": "在元素前分页：always / auto / avoid。EPUB 章节首常用。",
            "example": "h1 { page-break-before: always; }",
        },
        {
            "name": "page-break-after",
            "desc": "在元素后分页。",
            "example": ".chapter-end { page-break-after: always; }",
        },
        {
            "name": "page-break-inside",
            "desc": "避免元素内部分页：avoid。",
            "example": "table { page-break-inside: avoid; }",
        },
        {
            "name": "@font-face",
            "desc": "嵌入字体，src 用 url() 指向书内字体文件。",
            "example": '@font-face {\n  font-family: "KaiTi";\n  src: url(../Fonts/kai.ttf) format("truetype");\n}',
        },
        {
            "name": "@page",
            "desc": "页面盒模型规则，可定义边距、页码等。EPUB 阅读器支持有限。",
            "example": "@page { margin: 2em; }",
        },
        {
            "name": "hanging-punctuation",
            "desc": "标点悬挂，中文段首句号/逗号可移到行框外。",
            "example": "p { hanging-punctuation: first; }",
        },
        {
            "name": "line-break / word-break",
            "desc": "中文/英文混排换行控制。",
            "example": "body { line-break: strict; word-break: keep-all; }",
        },
        {
            "name": "orphans / widows",
            "desc": "段落在分页时保留的最少行数。",
            "example": "p { orphans: 2; widows: 2; }",
        },
    ],
    "动画与过渡": [
        {
            "name": "transition",
            "desc": "过渡效果：属性 时长 缓动 延迟。",
            "example": "a { transition: color 0.3s ease; }",
        },
        {
            "name": "@keyframes",
            "desc": "定义关键帧动画。",
            "example": "@keyframes fadeIn {\n  from { opacity: 0; }\n  to { opacity: 1; }\n}",
        },
        {
            "name": "animation",
            "desc": "应用动画：name duration timing iteration。",
            "example": ".banner { animation: fadeIn 1s ease 1; }",
        },
        {
            "name": "transform",
            "desc": "变换：translate / rotate / scale / skew。",
            "example": ".icon { transform: rotate(15deg); }",
        },
    ],
    "单位与变量": [
        {
            "name": "em / rem",
            "desc": "相对字号：em 按父级 / rem 按根元素。",
            "example": "p { font-size: 1em; }\nh1 { font-size: 1.5rem; }",
        },
        {
            "name": "px",
            "desc": "绝对像素，EPUB 不推荐作为字号主单位。",
            "example": ".border { border-width: 1px; }",
        },
        {
            "name": "%",
            "desc": "百分比，相对父元素。",
            "example": "img { width: 100%; }",
        },
        {
            "name": "vh / vw",
            "desc": "视口高度 / 宽度的 1%。",
            "example": ".fullscreen { height: 100vh; }",
        },
        {
            "name": "--var / var()",
            "desc": "自定义属性和读取。",
            "example": ":root { --main: #333; }\np { color: var(--main); }",
        },
        {
            "name": "!important",
            "desc": "强制优先级，慎用，会破坏样式可维护性。",
            "example": ".pin { color: red !important; }",
        },
        {
            "name": "@media",
            "desc": "媒体查询，按屏幕尺寸/方向应用样式。",
            "example": "@media (max-width: 600px) {\n  p { font-size: 0.9em; }\n}",
        },
    ],
}


def get_reference(kind: str) -> dict[str, list[dict]]:
    """根据 kind 返回对应的参考数据。kind: 'xhtml' / 'css'。"""
    if kind == "xhtml":
        return XHTML_REFERENCE
    if kind == "css":
        return CSS_REFERENCE
    raise ValueError(f"未知参考类型：{kind}")
