"""Kwadratowa plakietka z procentem — czytelna po zmniejszeniu do ikony w panelu."""

from __future__ import annotations

from pathlib import Path

import cairo

_COLORS = {
    "ok": (0.122, 0.561, 0.227),
    "mid": (0.659, 0.420, 0.0),
    "low": (0.776, 0.157, 0.157),
    "unknown": (0.290, 0.318, 0.376),
}


def tone_for(percent: int | None, threshold: int) -> str:
    if percent is None:
        return "unknown"
    if percent <= threshold:
        return "low"
    if percent < 50:
        return "mid"
    return "ok"


def draw_badge(
    percent: int | None,
    tone: str,
    path: Path,
    size: int = 64,
    text: str | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surface)
    red, green, blue = _COLORS.get(tone, _COLORS["unknown"])

    ctx.set_source_rgba(0, 0, 0, 0)
    ctx.paint()

    radius = size * 0.22
    _rounded(ctx, 1, 1, size - 2, size - 2, radius)
    ctx.set_source_rgb(red, green, blue)
    ctx.fill_preserve()
    ctx.set_source_rgba(1, 1, 1, 0.9)
    ctx.set_line_width(max(2, size * 0.04))
    ctx.stroke()

    label = text if text is not None else ("—" if percent is None else str(percent))
    ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    if text is not None or percent is None:
        font = size * 0.42
    elif percent >= 100:
        font = size * 0.34
    else:
        font = size * 0.46
    ctx.set_font_size(font)
    extents = ctx.text_extents(label)
    while extents.width > size * 0.82 and font > size * 0.18:
        font *= 0.85
        ctx.set_font_size(font)
        extents = ctx.text_extents(label)
    x = (size - extents.width) / 2 - extents.x_bearing
    y = (size - extents.height) / 2 - extents.y_bearing
    ctx.set_source_rgb(1, 1, 1)
    ctx.move_to(x, y)
    ctx.show_text(label)

    surface.write_to_png(str(path))
    return path


def _rounded(ctx: cairo.Context, x: float, y: float, width: float, height: float, radius: float) -> None:
    radius = min(radius, width / 2, height / 2)
    ctx.new_sub_path()
    ctx.arc(x + width - radius, y + radius, radius, -3.14159 / 2, 0)
    ctx.arc(x + width - radius, y + height - radius, radius, 0, 3.14159 / 2)
    ctx.arc(x + radius, y + height - radius, radius, 3.14159 / 2, 3.14159)
    ctx.arc(x + radius, y + radius, radius, 3.14159, 3 * 3.14159 / 2)
    ctx.close_path()
