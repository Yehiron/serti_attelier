#!/usr/bin/env python3
"""Build the frontend icons from the official wine and gold transparent PNGs."""

import argparse
import base64
from io import BytesIO
from pathlib import Path

from PIL import Image


def load_mark(path: Path) -> Image.Image:
    with Image.open(path) as source:
        mark = source.convert("RGBA")
    bounds = mark.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError(f"Source has no visible pixels: {path}")
    return mark.crop(bounds)


def render(mark: Image.Image, size: int, margin: float = 0.06,
           background=(0, 0, 0, 0)) -> Image.Image:
    # Margin is measured per side; preserve the original monogram proportions.
    available = max(1, round(size * (1 - 2 * margin)))
    scale = available / max(mark.size)
    dimensions = tuple(max(1, round(length * scale)) for length in mark.size)
    resized = mark.resize(dimensions, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), background)
    canvas.alpha_composite(resized, ((size - resized.width) // 2,
                                     (size - resized.height) // 2))
    return canvas


def embedded_png(mark: Image.Image) -> str:
    stream = BytesIO()
    render(mark, 128).save(stream, format="PNG", optimize=True)
    return base64.b64encode(stream.getvalue()).decode("ascii")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wine_source", type=Path)
    parser.add_argument("gold_source", type=Path)
    args = parser.parse_args()
    wine, gold = load_mark(args.wine_source), load_mark(args.gold_source)
    output = Path(__file__).resolve().parents[1] / "public"
    output.mkdir(parents=True, exist_ok=True)

    # Supply each ICO frame explicitly so 16px can use its own minimal margin.
    frames = [render(wine, size, 0 if size == 16 else 0.06)
              for size in (16, 32, 48)]
    frames[-1].save(output / "favicon.ico", format="ICO",
                    sizes=[(16, 16), (32, 32), (48, 48)],
                    append_images=frames[:-1])
    for size in (32, 192):
        render(wine, size).save(output / f"icon-{size}.png", optimize=True)
    render(wine, 180, 0.14, "#ead9cb").convert("RGB").save(
        output / "apple-touch-icon.png", optimize=True)

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
<style>.gold{{display:none}}@media (prefers-color-scheme:dark){{.wine{{display:none}}.gold{{display:inline}}}}</style>
<image class="wine" width="64" height="64" href="data:image/png;base64,{embedded_png(wine)}"/>
<image class="gold" width="64" height="64" href="data:image/png;base64,{embedded_png(gold)}"/>
</svg>
'''
    if len(svg.encode("utf-8")) >= 40_000:
        raise ValueError("SVG exceeds the 40 KB size budget")
    (output / "favicon.svg").write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
