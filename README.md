# EPUB 中文编辑器（zhepub）

一款在本地运行的 EPUB 电子书编辑器，界面和工作方式参考了开源编辑器
[Sigil](https://github.com/Sigil-Ebook/Sigil)，并针对中文书籍做了优化。

## 安装与运行

需要 Python 3.10 及以上版本。

```bash
pip install -r requirements.txt
python run.py                 # 启动编辑器
python run.py 某本书.epub      # 直接打开一本书
python run.py 某部小说.txt     # 导入 TXT
```

繁简转换是可选功能，需要另外安装：`pip install opencc-python-reimplemented`

## 功能

| 功能 | 说明 |
| --- | --- |
| 书籍浏览器 | 按文本、样式、图片、字体等分类显示全部文件；右键可重命名、删除、调整阅读顺序、设为封面 |
| 代码视图 | XHTML/CSS 语法高亮、行号、当前行高亮、回车自动缩进 |
| 实时预览 | 边写边看，会应用书中的样式表和图片；点击书内链接可跳转 |
| 重命名自动改链接 | 重命名或移动文件时，全书中指向它的 `href`/`src`/`url()` 会一起更新 |
| 拆分与合并章节 | `Ctrl+Enter` 在光标处拆分，在段落中间拆分也能保证标签闭合；锚点链接会自动指向新文件 |
| 目录 | 根据 h1~h6 自动生成多级目录，同时写入 EPUB 3 的 nav 和 EPUB 2 的 NCX |
| 元数据 | 书名、作者、语言、标识符、出版社、简介、封面等 |
| 查找替换 | 支持正则表达式，可以只查当前文件，也可以查全部 HTML、全部 CSS |
| 校验 | 检查 XML 格式错误、失效的链接和锚点、大小写不一致、未被引用的文件、缺少的元数据等；双击结果跳到出错行 |
| 中文排版 | 中英文之间加空格、半角标点转全角、删除段首空格、简繁转换（只修改正文，不动标签） |
| 导入 TXT | 自动识别“第X章 / 第X卷 / 序章 / 番外”等章节标题，编码支持 UTF-8 和 GBK |
| 字数统计 | 分别统计汉字数和西文单词数 |
| 语法帮助 | 帮助菜单中内置 XHTML / CSS 语法命令详解，可搜索，随时查询 |
| AI 查询 | 菜单栏新增 AI 菜单，可调用通义千问 / DeepSeek / 智谱 GLM / 月之暗面 Kimi / 文心大模型，支持把当前选区代码发给 AI 解释 |

## 常用快捷键

`Ctrl+S` 保存 · `Ctrl+F` 查找替换 · `F3` / `Shift+F3` 查找下一个/上一个 · `Ctrl+G` 跳转到行 ·
`Ctrl+1`~`Ctrl+6` 设为标题 · `Ctrl+0` 设为正文段落 · `Ctrl+B` 加粗 · `Ctrl+Enter` 拆分章节 ·
`Ctrl+T` 生成目录 · `F7` 校验 · `F8` 元数据 · `Ctrl+Shift+Q` AI 查询 · `Ctrl+Shift+E` 用 AI 解释当前选区

## 说明

- 保存时先写入临时文件再替换原文件，保存失败不会损坏原书；`mimetype` 放在压缩包第一位且不压缩，符合 EPUB 规范。
- 文本文件统一以 UTF-8 保存。清单之外的文件（如 `META-INF/encryption.xml`）会原样保留。
- 预览使用 Qt 自带的富文本引擎，复杂的 CSS 排版可能和阅读器里的效果不完全一致。

## 测试

```bash
pip install pytest
python -m pytest
```

## 打包成 exe

`dist\EPUB中文编辑器.exe` 是单文件程序，不需要安装 Python，可以直接复制到其他 Windows 电脑上运行。
把 `.epub` 文件拖到 exe 上即可直接打开。

重新打包（需要先 `pip install pyinstaller pillow`）：双击 `build.bat`，或者运行

```bash
python build_icon.py                            # 生成 assets/icon.ico
python -m PyInstaller zhepub.spec --noconfirm   # 生成 dist/EPUB中文编辑器.exe
```
