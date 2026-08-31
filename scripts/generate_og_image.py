#!/usr/bin/env python3
"""生成社交分享图 frontend/public/og-image.png（1200x630）。

用法：
    pip install pillow
    python scripts/generate_og_image.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1200, 630
OUT = Path(__file__).resolve().parent.parent / "frontend" / "public" / "og-image.png"
FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"

TOP = (79, 70, 229)  # indigo-600 #4f46e5
BOTTOM = (49, 46, 129)  # indigo-900 #312e81
ACCENT = (165, 180, 252)  # indigo-300 #a5b4fc


def lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def main() -> None:
    img = Image.new("RGB", (WIDTH, HEIGHT), TOP)
    draw = ImageDraw.Draw(img, "RGBA")

    # 垂直渐变背景
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        draw.line([(0, y), (WIDTH, y)], fill=lerp(TOP, BOTTOM, t))

    # 装饰圆
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.ellipse((860, -220, 1320, 240), fill=(255, 255, 255, 18))
    odraw.ellipse((-180, 430, 220, 830), fill=(255, 255, 255, 14))
    img = Image.alpha_composite(img.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(img)

    # 顶部柱状图装饰（K 线风格）
    bar_specs = [(84, (255, 255, 255, 90)), (138, ACCENT + (150,)), (62, (255, 255, 255, 90)), (112, ACCENT + (150,))]
    bar_width, gap = 44, 24
    total_width = len(bar_specs) * bar_width + (len(bar_specs) - 1) * gap
    start_x = (WIDTH - total_width) // 2
    baseline = 220
    for i, (height, color) in enumerate(bar_specs):
        x0 = start_x + i * (bar_width + gap)
        draw.rounded_rectangle(
            (x0, baseline - height, x0 + bar_width, baseline),
            radius=10,
            fill=color,
        )

    # 主标题
    title_font = ImageFont.truetype(FONT_PATH, 100)
    draw.text((WIDTH // 2, 330), "投资工具箱", font=title_font, fill=(255, 255, 255, 255), anchor="mm")

    # 分隔线
    draw.rounded_rectangle((WIDTH // 2 - 90, 410, WIDTH // 2 + 90, 414), radius=2, fill=ACCENT + (220,))

    # 副标题
    sub_font = ImageFont.truetype(FONT_PATH, 40)
    draw.text(
        (WIDTH // 2, 456),
        "A股股东查询 · 微盘股筛选",
        font=sub_font,
        fill=(255, 255, 255, 225),
        anchor="mm",
    )

    # 网址
    url_font = ImageFont.truetype(FONT_PATH, 30)
    draw.text(
        (WIDTH // 2, 548),
        "www.cats789.fun",
        font=url_font,
        fill=(255, 255, 255, 170),
        anchor="mm",
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
