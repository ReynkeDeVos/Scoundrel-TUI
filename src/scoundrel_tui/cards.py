from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

MAX_HEALTH = 20


class Suit(str, Enum):
    CLUBS = "clubs"
    SPADES = "spades"
    DIAMONDS = "diamonds"
    HEARTS = "hearts"


SUIT_GLYPHS = {
    Suit.CLUBS: "♣",
    Suit.SPADES: "♠",
    Suit.DIAMONDS: "♦",
    Suit.HEARTS: "♥",
}

SUIT_STYLE = {
    Suit.CLUBS: "monster",
    Suit.SPADES: "monster",
    Suit.DIAMONDS: "weapon",
    Suit.HEARTS: "potion",
}

RANK_NAMES = {11: "J", 12: "Q", 13: "K", 14: "A"}


@dataclass(frozen=True)
class Card:
    suit: Suit
    value: int

    @property
    def rank(self) -> str:
        return RANK_NAMES.get(self.value, str(self.value))

    @property
    def kind(self) -> str:
        if self.suit in (Suit.CLUBS, Suit.SPADES):
            return "Monster"
        if self.suit == Suit.DIAMONDS:
            return "Weapon"
        return "Potion"

    @property
    def title(self) -> str:
        return f"{self.rank}{SUIT_GLYPHS[self.suit]}"

    @property
    def style(self) -> str:
        return SUIT_STYLE[self.suit]


__all__ = [
    "Card",
    "MAX_HEALTH",
    "RANK_NAMES",
    "SUIT_GLYPHS",
    "SUIT_STYLE",
    "Suit",
]
