from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageOps
from rich.align import Align
from rich.console import RenderableType
from rich.text import Text
from textual_image.renderable import halfcell, sixel, tgp

from scoundrel_tui.assets import ART_CACHE, ROOT
from scoundrel_tui.cards import Card

DEFAULT_IMAGE_CELL_WIDTH_PX = 10
DEFAULT_IMAGE_CELL_HEIGHT_PX = 20
ITEM_CARD_ART_SCALE = 0.375


def enable_tmux_tgp_passthrough() -> None:
    if not os.environ.get("TMUX") or getattr(tgp, "_scoundrel_tmux_patch", False):
        return

    original_send = tgp._send_tgp_message

    def send_tgp_message_tmux(*, payload: str | None = None, **kwargs: int | str | None) -> None:
        import sys

        if not sys.__stdout__:
            raise tgp.TerminalError("sys.__stdout__ is None")

        parts = [
            tgp._TGP_MESSAGE_START,
            ",".join(f"{k}={v}" for k, v in kwargs.items() if v is not None),
            f";{payload}" if payload else "",
            tgp._TGP_MESSAGE_END,
        ]
        sequence = "".join(parts).replace("\x1b", "\x1b\x1b")
        sys.__stdout__.write(f"\x1bPtmux;\x1b{sequence}\x1b\\")
        sys.__stdout__.flush()

    tgp._send_tgp_message = send_tgp_message_tmux
    tgp._scoundrel_tmux_patch = True
    tgp._scoundrel_original_send_tgp_message = original_send


enable_tmux_tgp_passthrough()


def image_mode() -> str:
    requested = os.environ.get("SCOUNDREL_IMAGE_MODE", "kitty").lower()
    if requested in {"kitty", "tgp", "sixel", "halfcell", "off"}:
        return requested
    return "kitty"


def image_cell_pixels() -> tuple[int, int]:
    width = env_int("SCOUNDREL_IMAGE_CELL_WIDTH_PX", DEFAULT_IMAGE_CELL_WIDTH_PX)
    height = env_int("SCOUNDREL_IMAGE_CELL_HEIGHT_PX", DEFAULT_IMAGE_CELL_HEIGHT_PX)
    return max(4, width), max(8, height)


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def fitted_image(path: str, width_px: int, height_px: int, content_scale: float = 1.0) -> Path:
    source = Path(path)
    source_mtime_ns = source.stat().st_mtime_ns
    scale_id = int(content_scale * 100)
    return _fitted_image_cached(str(source), width_px, height_px, scale_id, source_mtime_ns)


@lru_cache(maxsize=512)
def _fitted_image_cached(path: str, width_px: int, height_px: int, scale_id: int, source_mtime_ns: int) -> Path:
    source = Path(path)
    source_id = str(source.relative_to(ROOT) if source.is_relative_to(ROOT) else source).replace("/", "__")
    target = ART_CACHE / f"{source_id}-{width_px}x{height_px}-s{scale_id}.png"
    if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    content_scale = scale_id / 100
    with Image.open(source) as image:
        image = image.convert("RGBA")
        fit_width = max(1, int(width_px * content_scale))
        fit_height = max(1, int(height_px * content_scale))
        fitted = ImageOps.contain(image, (fit_width, fit_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (width_px, height_px), (0, 0, 0, 0))
    canvas.alpha_composite(fitted, ((width_px - fitted.width) // 2, (height_px - fitted.height) // 2))
    canvas.save(target)
    return target


def card_image(path: Path | None, width: int = 18, height: int = 11, content_scale: float = 1.0) -> RenderableType:
    if path is None or image_mode() == "off":
        return Text("")
    cell_width_px, cell_height_px = image_cell_pixels()
    fitted = fitted_image(str(path), width * cell_width_px, height * cell_height_px, content_scale)
    mode = image_mode()
    fitted_mtime_ns = fitted.stat().st_mtime_ns
    return cached_terminal_image(str(fitted), mode, width, height, fitted_mtime_ns)


@lru_cache(maxsize=512)
def cached_terminal_image(path: str, mode: str, width: int, height: int, fitted_mtime_ns: int) -> RenderableType:
    fitted = Path(path)
    if mode in {"kitty", "tgp"}:
        return tgp.Image(fitted, width=width, height=height)
    if mode == "sixel":
        return sixel.Image(fitted, width=width, height=height)
    return halfcell.Image(fitted, width=width, height=height)


def transparent_image(width: int, height: int) -> Path:
    cell_width_px, cell_height_px = image_cell_pixels()
    pixel_width = max(1, width * cell_width_px)
    pixel_height = max(1, height * cell_height_px)
    target = ART_CACHE / f"transparent-{pixel_width}x{pixel_height}.png"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (pixel_width, pixel_height), (0, 0, 0, 0)).save(target)
    return target


def card_spacer(width: int, height: int) -> RenderableType:
    if image_mode() == "off":
        return Align.center(Text(""), width=width, height=height)
    return Align.center(
        card_image(transparent_image(width, height), width=width, height=height),
        vertical="middle",
        width=width,
        height=height,
    )


def card_art(card: Card, path: Path | None, width: int, height: int) -> RenderableType:
    content_scale = 1.0 if card.kind == "Monster" else ITEM_CARD_ART_SCALE
    return Align.center(
        card_image(path, width=width, height=height, content_scale=content_scale),
        vertical="middle",
        width=width,
        height=height,
    )


__all__ = [
    "DEFAULT_IMAGE_CELL_HEIGHT_PX",
    "DEFAULT_IMAGE_CELL_WIDTH_PX",
    "ITEM_CARD_ART_SCALE",
    "cached_terminal_image",
    "card_art",
    "card_image",
    "card_spacer",
    "enable_tmux_tgp_passthrough",
    "env_int",
    "fitted_image",
    "image_cell_pixels",
    "image_mode",
    "transparent_image",
]
