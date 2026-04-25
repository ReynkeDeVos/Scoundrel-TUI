from __future__ import annotations

from pathlib import Path

from scoundrel_tui.cards import Card, Suit

ROOT = Path(__file__).resolve().parents[2]
ASSET_ROOT = ROOT / "assets" / "scoundrel"
ART_CACHE = ROOT / ".cache" / "scoundrel-art"

STORY_IMAGES = {
    "welcome": ASSET_ROOT / "story" / "entry" / "trow_story_06-Temple_in_the_Deep.avif",
    "death": ASSET_ROOT / "story" / "death" / "trow_story_02-The_Fall.avif",
    "win": ASSET_ROOT / "story" / "win" / "trow_intro_10.avif",
}


def card_asset_map(folder: Path, values: range) -> dict[int, Path]:
    mapped: dict[int, Path] = {}
    for value in values:
        matches = sorted(path for path in folder.glob(f"{value:02}-*") if path.is_file())
        if matches:
            mapped[value] = matches[0]
    return mapped


def pixel_folder(folder: Path) -> Path:
    matches = sorted(path for path in folder.glob("pixel-*") if path.is_dir())
    return matches[0] if matches else folder


CLUBS_ASSET_FOLDER = ASSET_ROOT / "monsters" / "clubs"
SPADES_ASSET_FOLDER = ASSET_ROOT / "monsters" / "spades"
WEAPON_ASSET_FOLDER = ASSET_ROOT / "weapons"
POTION_ASSET_FOLDER = ASSET_ROOT / "potions"

MONSTER_PORTRAITS = {
    Suit.CLUBS: card_asset_map(CLUBS_ASSET_FOLDER, range(2, 15)),
    Suit.SPADES: card_asset_map(SPADES_ASSET_FOLDER, range(2, 15)),
}

PIXEL_MONSTER_PORTRAITS = {
    Suit.CLUBS: card_asset_map(pixel_folder(CLUBS_ASSET_FOLDER), range(2, 15)),
    Suit.SPADES: card_asset_map(pixel_folder(SPADES_ASSET_FOLDER), range(2, 15)),
}

WEAPON_IMAGES = card_asset_map(WEAPON_ASSET_FOLDER, range(2, 11))
POTION_IMAGES = card_asset_map(POTION_ASSET_FOLDER, range(2, 11))
PIXEL_WEAPON_IMAGES = card_asset_map(pixel_folder(WEAPON_ASSET_FOLDER), range(2, 11))
PIXEL_POTION_IMAGES = card_asset_map(pixel_folder(POTION_ASSET_FOLDER), range(2, 11))
BARE_HANDS_IMAGE = WEAPON_ASSET_FOLDER / "00-fist-human.avif"


def asset_for(card: Card, *, pixel: bool = False) -> Path | None:
    if card.kind == "Monster":
        portraits = PIXEL_MONSTER_PORTRAITS if pixel else MONSTER_PORTRAITS
        fallback = MONSTER_PORTRAITS[card.suit].get(card.value)
        path = portraits[card.suit].get(card.value, fallback)
    elif card.kind == "Weapon":
        path = (PIXEL_WEAPON_IMAGES if pixel else WEAPON_IMAGES).get(card.value, WEAPON_IMAGES.get(card.value))
    else:
        path = (PIXEL_POTION_IMAGES if pixel else POTION_IMAGES).get(card.value, POTION_IMAGES.get(card.value))
    return path if path and path.exists() else None


__all__ = [
    "ART_CACHE",
    "ASSET_ROOT",
    "BARE_HANDS_IMAGE",
    "CLUBS_ASSET_FOLDER",
    "MONSTER_PORTRAITS",
    "PIXEL_MONSTER_PORTRAITS",
    "PIXEL_POTION_IMAGES",
    "PIXEL_WEAPON_IMAGES",
    "POTION_ASSET_FOLDER",
    "POTION_IMAGES",
    "ROOT",
    "SPADES_ASSET_FOLDER",
    "STORY_IMAGES",
    "WEAPON_ASSET_FOLDER",
    "WEAPON_IMAGES",
    "asset_for",
    "card_asset_map",
    "pixel_folder",
]
