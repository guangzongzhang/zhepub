"""生成应用图标：assets/icon.png 与 assets/icon.ico。

图案：蓝色圆角方块上一本打开的书，书页上是 </> 代码标记，右下角一枚写着“编”的红色印章。
运行：python build_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 1024  # 先按大尺寸绘制，再缩小，边缘更平滑
OUT = Path(__file__).parent / "assets"
FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def vertical_gradient(size, top, bottom) -> Image.Image:
    w, h = size
    grad = Image.new("RGBA", size)
    px = grad.load()
    for y in range(h):
        t = y / (h - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,)
        for x in range(w):
            px[x, y] = color
    return grad


def draw_icon() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # 背景：深蓝渐变圆角方块
    margin, radius = 40, 200
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((margin, margin, S - margin, S - margin), radius, fill=255)
    img.paste(vertical_gradient((S, S), (37, 99, 235), (30, 58, 138)), (0, 0), mask)

    # 书本阴影
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.polygon([(170, 330), (512, 390), (854, 330), (854, 800), (512, 860), (170, 800)],
               fill=(0, 0, 0, 110))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(24)), (0, 18))

    d = ImageDraw.Draw(img)
    # 书页：左右两页，中间书脊略低，形成打开的书的形状
    left = [(170, 300), (330, 270), (512, 340), (512, 830), (330, 770), (170, 790)]
    right = [(854, 300), (694, 270), (512, 340), (512, 830), (694, 770), (854, 790)]
    d.polygon(left, fill=(248, 250, 252))
    d.polygon(right, fill=(241, 245, 249))
    # 书页底边（书的厚度）
    d.line([(170, 790), (330, 770), (512, 830), (694, 770), (854, 790)], fill=(203, 213, 225), width=14)
    d.line([(512, 340), (512, 830)], fill=(203, 213, 225), width=8)

    # 左页：几行文字
    for i, y in enumerate(range(420, 720, 70)):
        x2 = 440 if i % 3 != 2 else 380
        d.line([(225, y - (i * 4)), (x2, y + 20 - (i * 4))], fill=(148, 163, 184), width=22)

    # 右页：</> 代码标记
    code_color = (37, 99, 235)
    d.line([(640, 470), (580, 540), (640, 610)], fill=code_color, width=30, joint="curve")
    d.line([(740, 470), (800, 540), (740, 610)], fill=code_color, width=30, joint="curve")
    d.line([(710, 450), (670, 630)], fill=(234, 88, 12), width=26)

    # 右下角：红色印章“编”
    seal = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(seal).rounded_rectangle((640, 640, 920, 920), 48, fill=(0, 0, 0, 120))
    img.alpha_composite(seal.filter(ImageFilter.GaussianBlur(16)), (0, 10))
    d.rounded_rectangle((640, 640, 920, 920), 48, fill=(220, 38, 38))
    d.rounded_rectangle((662, 662, 898, 898), 34, outline=(254, 226, 226), width=8)
    f = font(190)
    box = d.textbbox((0, 0), "编", font=f)
    tw, th = box[2] - box[0], box[3] - box[1]
    d.text((780 - tw / 2 - box[0], 780 - th / 2 - box[1]), "编", font=f, fill=(255, 255, 255))
    return img


def main() -> None:
    OUT.mkdir(exist_ok=True)
    icon = draw_icon()
    icon.resize((512, 512), Image.Resampling.LANCZOS).save(OUT / "icon.png")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icon.save(OUT / "icon.ico", sizes=sizes)
    print(f"已生成 {OUT / 'icon.png'} 和 {OUT / 'icon.ico'}")


if __name__ == "__main__":
    main()
