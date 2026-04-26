from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum

from scoundrel_tui.config import MAX_HEALTH


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


def _card_list() -> list[Card]:
    return []


def _room_slots() -> list[Card | None]:
    return [None, None, None, None]


def _message_log() -> list[str]:
    return []


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


@dataclass
class GameState:
    dungeon: list[Card] = field(default_factory=_card_list)
    room: list[Card | None] = field(default_factory=_room_slots)
    discard: list[Card] = field(default_factory=_card_list)
    weapon: Card | None = None
    weapon_stack: list[Card] = field(default_factory=_card_list)
    health: int = MAX_HEALTH
    turn_taken: int = 0
    used_potion: bool = False
    avoided_last_room: bool = False
    game_over: bool = False
    won: bool = False
    score: int = 0
    selected_slot: int = 0
    pending_monster_slot: int | None = None
    confirm_new_game: bool = False
    confirm_quit: bool = False
    banner_tick: int = 0
    log: list[str] = field(default_factory=_message_log)

    @classmethod
    def fresh(cls) -> GameState:
        cards = [Card(suit, value) for suit in (Suit.CLUBS, Suit.SPADES) for value in range(2, 15)]
        cards += [Card(Suit.DIAMONDS, value) for value in range(2, 11)]
        cards += [Card(Suit.HEARTS, value) for value in range(2, 11)]
        random.shuffle(cards)
        state = cls(dungeon=cards)
        state.log.append("The dungeon opens. Four cards form the first room.")
        state.fill_room()
        return state

    def fill_room(self) -> None:
        for index, card in enumerate(self.room):
            if card is None and self.dungeon:
                self.room[index] = self.dungeon.pop(0)
        self.turn_taken = 0
        self.used_potion = False
        self.pending_monster_slot = None
        if not any(self.room) and not self.dungeon:
            self.finish(True)
        self.normalize_selection()

    def normalize_selection(self) -> None:
        if self.room[self.selected_slot] is not None:
            return
        for index, card in enumerate(self.room):
            if card is not None:
                self.selected_slot = index
                return

    def avoid_room(self) -> bool:
        self.confirm_new_game = False
        self.confirm_quit = False
        if self.avoided_last_room or self.turn_taken or self.pending_monster_slot is not None:
            return False
        cards = [card for card in self.room if card is not None]
        if len(cards) < 4:
            return False
        self.dungeon.extend(cards)
        self.room = [None, None, None, None]
        self.avoided_last_room = True
        self.log.append("You slip past the room. It sinks to the bottom of the dungeon.")
        self.fill_room()
        return True

    def take_slot(self, slot: int) -> None:
        self.confirm_new_game = False
        self.confirm_quit = False
        if self.game_over or self.pending_monster_slot is not None:
            return
        if slot < 0 or slot >= 4 or self.room[slot] is None:
            self.log.append("That place on the table is empty.")
            return
        card = self.room[slot]
        assert card is not None
        self.resolve_slot(slot, use_weapon=card.kind == "Monster" and self.can_use_weapon(card))

    def resolve_slot(self, slot: int, *, use_weapon: bool) -> None:
        self.confirm_new_game = False
        self.confirm_quit = False
        card = self.room[slot]
        if card is None:
            return
        self.room[slot] = None
        self.pending_monster_slot = None
        if card.kind == "Weapon":
            if self.weapon:
                self.discard.append(self.weapon)
                self.discard.extend(self.weapon_stack)
            self.weapon = card
            self.weapon_stack = []
            self.log.append(f"You bind yourself to {card.title}. The old weapon is discarded.")
        elif card.kind == "Potion":
            if self.used_potion:
                self.discard.append(card)
                self.log.append(f"{card.title} shatters unused. Only one potion works per room.")
            else:
                healed = min(MAX_HEALTH - self.health, card.value)
                self.health += healed
                self.used_potion = True
                self.discard.append(card)
                self.log.append(f"{card.title} restores {healed} health.")
        elif use_weapon and self.weapon:
            damage = max(0, card.value - self.weapon.value)
            self.health -= damage
            self.weapon_stack.append(card)
            self.log.append(f"{self.weapon.title} bites into {card.title}. You take {damage} damage.")
        else:
            self.health -= card.value
            self.discard.append(card)
            self.log.append(f"You fight {card.title} barehanded and take {card.value} damage.")
        self.normalize_selection()
        if self.health <= 0:
            self.finish(False)
            return
        self.turn_taken += 1
        self.avoided_last_room = False
        if self.turn_taken >= 3 or sum(card is not None for card in self.room) <= 1:
            self.log.append("The last card remains in place as the room fills up again.")
            self.fill_room()
        elif not any(self.room) and not self.dungeon:
            self.finish(True)

    def can_use_weapon(self, monster: Card) -> bool:
        if self.weapon is None:
            return False
        if not self.weapon_stack:
            return True
        return monster.value < self.weapon_stack[-1].value

    def finish(self, won: bool) -> None:
        self.game_over = True
        self.won = won
        if won:
            self.score = self.health
            self.log.append(f"You escape the dungeon with {self.health} health.")
        else:
            remaining_monsters = [
                card
                for card in [*self.dungeon, *(card for card in self.room if card)]
                if card.kind == "Monster"
            ]
            self.score = self.health - sum(card.value for card in remaining_monsters)
            self.log.append(f"You fall. Final score: {self.score}.")


__all__ = [
    "Card",
    "GameState",
    "RANK_NAMES",
    "SUIT_GLYPHS",
    "SUIT_STYLE",
    "Suit",
]
