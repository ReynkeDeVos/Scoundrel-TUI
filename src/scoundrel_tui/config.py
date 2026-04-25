from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSET_ROOT = ROOT / "assets" / "scoundrel"
MAX_HEALTH = 20
ART_CACHE = ROOT / ".cache" / "scoundrel-art"
DEFAULT_IMAGE_CELL_WIDTH_PX = 10
DEFAULT_IMAGE_CELL_HEIGHT_PX = 20
ITEM_CARD_ART_SCALE = 0.375
SHELL_HORIZONTAL_MARGIN = 9
DEATH_STORY_IMAGES = tuple(sorted((ASSET_ROOT / "story" / "death").glob("*")))
WELCOME_MESSAGES = (
    "The dungeon opens. Choose carefully.",
    "Four cards wait in the dark.",
    "Steel, blood, and luck decide the way forward.",
    "The room is quiet. The deck is not.",
)
STORY_IMAGES = {
    "welcome": ASSET_ROOT / "story" / "entry" / "trow_story_06-Temple_in_the_Deep.avif",
    "death": ASSET_ROOT / "story" / "death" / "trow_story_02-The_Fall.avif",
    "win": ASSET_ROOT / "story" / "win" / "trow_intro_10.avif",
}

__all__ = [
    "ART_CACHE",
    "ASSET_ROOT",
    "DEFAULT_IMAGE_CELL_HEIGHT_PX",
    "DEFAULT_IMAGE_CELL_WIDTH_PX",
    "DEATH_STORY_IMAGES",
    "ITEM_CARD_ART_SCALE",
    "MAX_HEALTH",
    "ROOT",
    "SHELL_HORIZONTAL_MARGIN",
    "STORY_IMAGES",
    "WELCOME_MESSAGES",
]
