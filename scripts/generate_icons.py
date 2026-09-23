#!/usr/bin/env python3

from pathlib import Path

from PIL import Image, ImageDraw


def scaled(value: float, factor: int) -> int:
    return round(value * factor)


def rounded_rect(draw, box, radius, fill, factor):
    draw.rounded_rectangle(
        tuple(scaled(value, factor) for value in box),
        radius=scaled(radius, factor),
        fill=fill,
    )


def render_icon(size: int) -> Image.Image:
    supersample = 16
    canvas_size = size * supersample
    factor = canvas_size / 256
    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    rounded_rect(draw, (8, 8, 248, 248), 56, "#00b982", factor)
    rounded_rect(draw, (112, 18, 144, 56), 16, "#ffffff", factor)
    rounded_rect(draw, (116, 40, 140, 98), 7, "#ffffff", factor)
    rounded_rect(draw, (104, 44, 152, 74), 10, "#ffffff", factor)
    rounded_rect(draw, (82, 83, 174, 213), 28, "#ffffff", factor)
    rounded_rect(draw, (111, 52, 145, 60), 4, "#c8f3e4", factor)
    rounded_rect(draw, (97, 128, 159, 204), 18, "#087b60", factor)
    rounded_rect(draw, (98, 137, 158, 151), 6, "#149474", factor)

    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output_dir = root / "packaging" / "build-assets" / "icons"
    output_dir.mkdir(parents=True, exist_ok=True)
    render_icon(256).save(output_dir / "icon_256.png", "PNG", optimize=True)
    render_icon(64).save(output_dir / "icon_64.png", "PNG", optimize=True)


if __name__ == "__main__":
    main()
