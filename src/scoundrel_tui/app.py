from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageOps
from rich import box
from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.widgets import Static
from textual_image.renderable import halfcell, sixel, tgp


ROOT = Path(__file__).resolve().parents[2]
ASSET_ROOT = ROOT / "assets" / "scoundrel"
MAX_HEALTH = 20
ART_CACHE = ROOT / ".cache" / "scoundrel-art"
DEFAULT_IMAGE_CELL_WIDTH_PX = 10
DEFAULT_IMAGE_CELL_HEIGHT_PX = 20
ITEM_CARD_ART_SCALE = 0.375
SHELL_HORIZONTAL_MARGIN = 9
STORY_IMAGES = {
    "welcome": ASSET_ROOT / "story" / "entry" / "trow_story_06-Temple_in_the_Deep.webp",
    "death": ASSET_ROOT / "story" / "death" / "trow_story_02-The_Fall.jpg",
    "win": ASSET_ROOT / "story" / "win" / "trow_intro_10.jpg",
}


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


@dataclass
class GameState:
    dungeon: list[Card] = field(default_factory=list)
    room: list[Card | None] = field(default_factory=lambda: [None, None, None, None])
    discard: list[Card] = field(default_factory=list)
    weapon: Card | None = None
    weapon_stack: list[Card] = field(default_factory=list)
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
    log: list[str] = field(default_factory=list)

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
            self.log.append(f"You bind yourself to {card.title}. The old blade is discarded.")
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
            self.log.append("The last card remains in place as the room breathes again.")
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
BARE_HANDS_IMAGE = WEAPON_ASSET_FOLDER / "00-fist-human.png"


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


class ScoundrelApp(App[None]):
    CSS = """
    Screen {
        layers: base overlay;
        background: #070909;
        color: #d8cdb9;
    }

    #shell {
        layer: base;
        margin: 0 __SHELL_HORIZONTAL_MARGIN__;
        padding: 1 0;
        layout: vertical;
    }

    #overlay-host {
        layer: overlay;
        width: 100%;
        height: 100%;
        align: center middle;
    }

    #overlay {
        width: 82;
        height: 24;
    }

    #main {
        height: 1fr;
        layout: vertical;
    }

    #status {
        height: 3;
        width: 1fr;
    }

    #room {
        height: 1fr;
        width: 1fr;
    }

    #message {
        height: 2;
        width: 1fr;
    }

    #footer {
        height: 3;
        width: 1fr;
    }
    """.replace("__SHELL_HORIZONTAL_MARGIN__", str(SHELL_HORIZONTAL_MARGIN))

    BINDINGS = [
        Binding("1", "take(0)", "Slot 1"),
        Binding("2", "take(1)", "Slot 2"),
        Binding("3", "take(2)", "Slot 3"),
        Binding("4", "take(3)", "Slot 4"),
        Binding("left", "move(-1)", "Left"),
        Binding("right", "move(1)", "Right"),
        Binding("enter", "take_selected", "Take"),
        Binding("w", "weapon", "Weapon"),
        Binding("b", "barehanded", "Bare"),
        Binding("a", "avoid", "Avoid"),
        Binding("p", "toggle_pixel_art", "Pixel Art"),
        Binding("n", "new_game", "New"),
        Binding("q", "quit", "Quit"),
    ]

    state: reactive[GameState] = reactive(GameState.fresh, recompose=False)
    pixel_art: reactive[bool] = reactive(False, recompose=False)
    overlay: reactive[str | None] = reactive(None, recompose=False)

    def compose(self) -> ComposeResult:
        with Container(id="shell"):
            with Vertical(id="main"):
                yield Static(id="status")
                yield Static(id="room")
                yield Static(id="message")
                yield Static(id="footer")
        with Container(id="overlay-host"):
            yield Static(id="overlay")

    def on_mount(self) -> None:
        self.refresh_board()
        self.call_after_refresh(self.refresh_board)
        self.set_timer(0.05, self.refresh_board)

    def on_resize(self, event: events.Resize) -> None:
        self.refresh_board()
        self.call_after_refresh(self.refresh_board)

    def action_toggle_pixel_art(self) -> None:
        self.state.confirm_new_game = False
        self.state.confirm_quit = False
        self.pixel_art = not self.pixel_art
        mode = "pixel" if self.pixel_art else "portrait"
        self.state.log.append(f"Artwork switched to {mode} mode.")
        self.refresh_board()

    def action_new_game(self) -> None:
        if self.state.game_over:
            self.state = GameState.fresh()
            self.overlay = None
        elif self.state.confirm_new_game:
            self.state = GameState.fresh()
            self.overlay = None
        else:
            self.state.confirm_new_game = True
            self.state.confirm_quit = False
            self.state.log.append("Press N again to abandon this run and start a new game.")
        self.refresh_board()

    def action_move(self, delta: int) -> None:
        if self.overlay:
            return
        self.state.confirm_new_game = False
        self.state.confirm_quit = False
        cards = self.state.room
        index = self.state.selected_slot
        for _ in range(4):
            index = (index + delta) % 4
            if cards[index] is not None:
                self.state.selected_slot = index
                break
        self.refresh_selection()

    def action_take_selected(self) -> None:
        self.action_take(self.state.selected_slot)

    def action_take(self, slot: int) -> None:
        self.state.take_slot(slot)
        self.refresh_board()

    def action_weapon(self) -> None:
        if self.overlay:
            return
        self.state.confirm_new_game = False
        self.state.confirm_quit = False
        slot = self.state.pending_monster_slot
        if slot is None:
            selected = self.state.selected_slot
            card = self.state.room[selected]
            if card and card.kind == "Monster" and self.state.can_use_weapon(card):
                self.state.resolve_slot(selected, use_weapon=True)
            else:
                self.state.log.append("Select a monster your weapon can fight.")
        else:
            self.state.resolve_slot(slot, use_weapon=True)
        self.refresh_board()

    def action_barehanded(self) -> None:
        if self.overlay:
            return
        self.state.confirm_new_game = False
        self.state.confirm_quit = False
        slot = self.state.pending_monster_slot
        if slot is None:
            selected = self.state.selected_slot
            card = self.state.room[selected]
            if card and card.kind == "Monster":
                self.state.resolve_slot(selected, use_weapon=False)
            else:
                self.state.log.append("Select a monster to fight barehanded.")
        else:
            self.state.resolve_slot(slot, use_weapon=False)
        self.refresh_board()

    def action_avoid(self) -> None:
        if self.overlay:
            return
        if not self.state.avoid_room():
            self.state.log.append("You cannot avoid this room right now.")
        self.refresh_board()

    def action_quit(self) -> None:
        if self.state.confirm_quit:
            self.exit()
            return
        self.overlay = None
        self.state.confirm_new_game = False
        self.state.confirm_quit = True
        self.state.log.append("Press Q again to quit.")
        self.refresh_board()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape" and self.state.pending_monster_slot is not None:
            self.state.confirm_new_game = False
            self.state.confirm_quit = False
            self.state.pending_monster_slot = None
            self.state.log.append("You steady yourself and reconsider the room.")
            self.refresh_selection()

    def refresh_board(self) -> None:
        if self.state.game_over:
            self.overlay = "win" if self.state.won else "death"
        self.query_one("#status", Static).update(self.render_status())
        self.query_one("#room", Static).update(self.render_room())
        self.query_one("#message", Static).update(self.render_message())
        self.query_one("#footer", Static).update(self.render_footer())
        self.refresh_overlay()

    def refresh_selection(self) -> None:
        self.query_one("#status", Static).update(self.render_status())
        self.query_one("#room", Static).update(self.render_room())
        self.query_one("#message", Static).update(self.render_message())
        self.query_one("#footer", Static).update(self.render_footer())
        self.refresh_overlay()

    def refresh_overlay(self) -> None:
        host = self.query_one("#overlay-host", Container)
        overlay = self.query_one("#overlay", Static)
        if not self.overlay:
            host.display = False
            overlay.update("")
            return
        host.display = True
        overlay.update(self.render_overlay(self.overlay))

    def render_overlay(self, kind: str) -> RenderableType:
        if kind == "win":
            title = Text("YOU WIN", style="bold #8df59b")
            message = Text(f"Escaped with {self.state.health} health.  Score {self.state.score}.  N starts a new run.", style="#d2b98d")
            border = "#71d083"
            image = STORY_IMAGES["win"]
        else:
            title = Text("YOU DIED", style="bold #f05d4f")
            message = Text(f"Final score {self.state.score}.  N starts a new run.  Q quits.", style="#d2b98d")
            border = "#f05d4f"
            image = STORY_IMAGES["death"]

        body = Group(
            Align.center(title),
            Align.center(card_image(image if image.exists() else None, width=58, height=16)),
            Align.center(message),
        )
        return Panel(body, border_style=border, box=box.SQUARE)

    def render_status(self) -> RenderableType:
        table = Table.grid(expand=False, padding=(0, 4))
        for _ in range(4):
            table.add_column(no_wrap=True)
        weapon = self.state.weapon.title if self.state.weapon else "Bare hands"
        condition = self.weapon_condition()
        remaining = len(self.state.dungeon) + sum(card is not None for card in self.state.room)
        table.add_row(
            self.status_label("Health"),
            self.status_label("Equipped weapon"),
            self.status_label("Weapon condition"),
            self.status_label("Remaining cards"),
        )
        table.add_row(
            self.health_status_value(),
            self.status_value(weapon, "#d8cdb9"),
            self.status_value(condition, "#d8cdb9"),
            self.status_value(str(remaining), "#d8cdb9"),
        )
        return Align.center(table, vertical="middle")

    def health_status_value(self) -> Text:
        health = max(0, self.state.health)
        return Text.assemble(
            (f"{health:>2}/{MAX_HEALTH} ", self.health_style(health)),
            self.health_bar(health, width=MAX_HEALTH),
            no_wrap=True,
            overflow="ellipsis",
        )

    def status_label(self, label: str) -> Text:
        return Text(label, style="#776f63", no_wrap=True, overflow="ellipsis")

    def status_value(self, value: str, value_style: str) -> Text:
        style = value_style if value_style.startswith("bold") else f"bold {value_style}"
        return Text(value, style=style, no_wrap=True, overflow="ellipsis")

    def weapon_condition(self) -> str:
        weapon = self.state.weapon
        if weapon is None:
            return "unarmed"
        if not self.state.weapon_stack:
            return "any monster"
        allowed = self.state.weapon_stack[-1].value - 1
        if allowed < 2:
            return "spent"
        return f"next ≤ {allowed}"

    def render_health(self) -> RenderableType:
        health = max(0, self.state.health)
        style = self.health_style(health)
        body = Group(
            Text(""),
            Align.center(Text.assemble((f"{health:>2}/{MAX_HEALTH}  ", style), self.health_bar(health, width=36))),
        )
        return Panel(body, title="VITALS", border_style=style)

    def health_style(self, health: int) -> str:
        if health > 10:
            return "#71d083"
        if health > 5:
            return "#f8b65a"
        return "bold #f05d4f"

    def health_bar(self, health: int, width: int = MAX_HEALTH) -> Text:
        current = max(0, min(MAX_HEALTH, health))
        default_target, bare_target, potion_target = self.health_preview_targets()
        bar = Text()
        for cell in range(width):
            index = min(MAX_HEALTH, (cell * MAX_HEALTH) // width + 1)
            if potion_target is not None and current < index <= potion_target:
                bar.append("▌", style="bold #b8ff7a")
            elif index <= current:
                if bare_target is not None and self.health_index_starts_here(cell, bare_target + 1, width):
                    bar.append("▏", style="bold #ffffff")
                elif default_target is not None and index > default_target:
                    bar.append("▌", style="bold #ff7a1a")
                else:
                    bar.append("█", style=self.health_style(current))
            else:
                bar.append("░", style="#3a3129")
        return bar

    def health_index_starts_here(self, cell: int, index: int, width: int) -> bool:
        if index < 1 or index > MAX_HEALTH:
            return False
        return (cell * MAX_HEALTH) // width + 1 == index and (cell == 0 or ((cell - 1) * MAX_HEALTH) // width + 1 < index)

    def health_preview_targets(self) -> tuple[int | None, int | None, int | None]:
        card = self.state.room[self.state.selected_slot]
        if not card or self.state.game_over:
            return None, None, None
        if card.kind == "Potion":
            if self.state.used_potion:
                return None, None, None
            return None, None, min(MAX_HEALTH, self.state.health + card.value)
        if card.kind == "Monster" and self.state.can_use_weapon(card) and self.state.weapon:
            weapon_damage = max(0, card.value - self.state.weapon.value)
            return max(0, self.state.health - weapon_damage), max(0, self.state.health - card.value), None
        if card.kind == "Monster":
            return max(0, self.state.health - card.value), None, None
        return None, None, None

    def render_weapon(self) -> RenderableType:
        table = Table.grid(expand=True)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        card = self.state.weapon
        if not card:
            bare_art = Text("No weapon equipped", style="#604c37") if self.pixel_art else card_image(BARE_HANDS_IMAGE if BARE_HANDS_IMAGE.exists() else None, width=12, height=8)
            weapon_body = Group(
                Text("Bare hands  damage 0", style="#8e7151"),
                bare_art,
            )
            border = "#604c37"
        else:
            limit_damage = self.state.weapon_stack[-1].value - 1 if self.state.weapon_stack else card.value
            effective_damage = min(card.value, limit_damage)
            weapon_body = Group(
                Text(f"{card.title}  damage {effective_damage}", style="bold #95c7ff"),
                card_image(asset_for(card, pixel=self.pixel_art), width=12, height=8),
            )
            border = "#5aa6d6"
        rows = []
        for monster in self.state.weapon_stack[-6:]:
            rows.append(Text(f"{monster.title:<3} slain value {monster.value}", style="#d9a15c"))
        if not rows:
            rows.append(Text("No monsters on the blade.", style="#8e7151"))
        limit = "Any monster" if not self.state.weapon_stack else f"Next must be ≤ {self.state.weapon_stack[-1].value - 1}"
        stack_body = Group(Text(limit, style="#f8d27d"), *rows)
        table.add_row(weapon_body, stack_body)
        return Panel(table, title="WEAPON", border_style=border)

    def render_room(self) -> RenderableType:
        card_width, _, _, _ = self.card_dimensions()
        table = Table.grid(expand=False)
        for _ in range(4):
            table.add_column(width=card_width + 3)
        cells = [self.card_panel(index, card) for index, card in enumerate(self.state.room)]
        table.add_row(*cells)
        return Align.center(table, vertical="middle")

    def card_dimensions(self) -> tuple[int, int, int, int]:
        fallback_width, fallback_height = self.estimated_room_size()
        try:
            room_size = self.query_one("#room", Static).size
            room_width, room_height = room_size.width, room_size.height
            if room_width < 120 or room_height < 28:
                room_width, room_height = fallback_width, fallback_height
        except Exception:
            room_width, room_height = fallback_width, fallback_height

        room_inner_width = max(96, room_width - 2)
        card_width = max(25, (room_inner_width - 12) // 4)
        card_height = max(24, room_height - 2)

        image_width = max(15, card_width - 8)
        image_height = max(10, card_height - 12)
        return card_width, card_height, image_width, image_height

    def estimated_room_size(self) -> tuple[int, int]:
        outer_width = self.size.width - (SHELL_HORIZONTAL_MARGIN * 2)
        return max(96, outer_width - 2), max(26, self.size.height - 10)

    def card_panel(self, index: int, card: Card | None) -> RenderableType:
        selected = index == self.state.selected_slot
        pending = index == self.state.pending_monster_slot
        card_width, card_height, image_width, image_height = self.card_dimensions()
        if card is None:
            body = self.fixed_card_body(
                [
                    card_spacer(image_width, image_height),
                    Align.center(Text("empty", style="#323232")),
                ],
                card_width,
                card_height,
            )
            return Panel(
                body,
                title=f" {index + 1} ",
                subtitle=" ",
                border_style="#2c3030",
                box=box.SQUARE,
                width=card_width,
                height=card_height,
                expand=False,
            )
        path = asset_for(card, pixel=self.pixel_art)
        label = Text(f"{card.title}", style=f"bold {self.kind_color(card)}")
        kind = Text(card.kind.upper(), style="#71685c")
        parts: list[RenderableType] = [
            label,
            kind,
            card_art(card, path, width=image_width, height=image_height),
            Align.center(Text(self.card_action_text(card), style="#c6b9a2")),
        ]
        body = self.fixed_card_body(parts, card_width, card_height)
        border = "bold #f1e5c8" if selected else self.kind_color(card)
        if pending:
            border = "#ffffff"
        title = f" {index + 1} "
        return Panel(
            body,
            title=title,
            subtitle=self.slot_hint(card),
            border_style=border,
            box=box.SQUARE,
            width=card_width,
            height=card_height,
            expand=False,
        )

    def card_action_text(self, card: Card) -> str:
        if card.kind == "Potion":
            if self.state.used_potion:
                return "discarded this room"
            healed = min(MAX_HEALTH - self.state.health, card.value)
            return f"heal {healed}"
        if card.kind == "Weapon":
            return f"equip value {card.value}"
        if self.state.can_use_weapon(card) and self.state.weapon:
            damage = max(0, card.value - self.state.weapon.value)
            return f"monster damage {damage}"
        return f"take {card.value} damage"

    def fixed_card_body(self, parts: list[RenderableType], card_width: int, card_height: int) -> RenderableType:
        return Align.center(
            Group(*parts),
            vertical="middle",
            width=card_width - 2,
            height=card_height - 2,
        )

    def kind_color(self, card: Card) -> str:
        if card.kind == "Monster":
            return "#f05d4f"
        if card.kind == "Weapon":
            return "#74b7e8"
        return "#71d083"

    def slot_hint(self, card: Card) -> str:
        if card.kind == "Monster":
            if self.state.can_use_weapon(card):
                return "W/B"
            return "bare"
        return "take"

    def render_message(self) -> RenderableType:
        warning = self.selected_warning()
        if self.state.confirm_new_game:
            text = Text("Press N again to abandon this run and start a new game.", style="bold #c9a86a")
        elif self.state.confirm_quit:
            text = Text("Press Q again to quit.", style="bold #c9a86a")
        elif self.state.game_over:
            result = "Escaped" if self.state.won else "Fell in the dungeon"
            text = Text(f"{result}. Score {self.state.score}.", style="#c9a86a")
        elif self.state.pending_monster_slot is not None:
            card = self.state.room[self.state.pending_monster_slot]
            assert card is not None
            damage = max(0, card.value - (self.state.weapon.value if self.state.weapon else 0))
            text = Text(f"{card.title}: W uses weapon for {damage} damage, B fights bare for {card.value}.", style="#d8cdb9")
        elif warning:
            text = Text(warning, style="bold #d9695d")
        elif self.state.log:
            text = Text(self.state.log[-1], style="#777064")
        else:
            text = Text("")
        return Align.center(text, vertical="middle")

    def render_footer(self) -> RenderableType:
        art = "pixel" if self.pixel_art else "portrait"
        shortcuts = Text.assemble(
            ("[1-4]", "#9e8454"),
            (" take   ", "#595959"),
            ("[←/→]", "#9e8454"),
            (" select   ", "#595959"),
            ("[Enter]", "#9e8454"),
            (" take selected   ", "#595959"),
            ("[A]", "#9e8454"),
            (" avoid   ", "#595959"),
            ("[W/B]", "#9e8454"),
            (" weapon/bare   ", "#595959"),
            ("[P]", "#9e8454"),
            (f" {art}   ", "#595959"),
            ("[N]", "#9e8454"),
            (" new   ", "#595959"),
            ("[Q]", "#9e8454"),
            (" quit", "#595959"),
        )
        return Align.center(shortcuts, vertical="middle")

    def render_prompt(self) -> RenderableType:
        shortcut_hint = Group(
            Text("1-4 / Enter  take", style="#7a6548"),
            Text("← / →        select", style="#6d5940"),
            Text("A            avoid", style="#6d5940"),
            Text("W / B        weapon / bare", style="#6d5940"),
            Text(f"P            art: {'pixel' if self.pixel_art else 'portrait'}", style="#6d5940"),
            Text("N            new", style="#6d5940"),
            Text("Q            quit", style="#6d5940"),
        )
        warning = self.selected_warning()
        warning_line = Text(warning, style="bold #f05d4f") if warning else Text("")
        if self.state.confirm_new_game:
            return Panel(
                Group(
                    Text("Start a new game? Press N again to confirm.", style="bold #f8d27d"),
                    Text("Any other gameplay key cancels.", style="#9f8664"),
                    Text(""),
                    shortcut_hint,
                ),
                border_style="#f8d27d",
                title="HELP",
            )
        if self.state.confirm_quit:
            return Panel(
                Group(
                    Text("Quit Scoundrel? Press Q again to confirm.", style="bold #f8d27d"),
                    Text("Any gameplay key cancels.", style="#9f8664"),
                    Text(""),
                    shortcut_hint,
                ),
                border_style="#f8d27d",
                title="HELP",
            )
        if self.state.game_over:
            result = "ESCAPED" if self.state.won else "FELL IN THE DARK"
            return Panel(
                Group(
                    Text(f"{result}  Score {self.state.score}.", style="bold #f8d27d"),
                    Text(""),
                    shortcut_hint,
                ),
                border_style="#f8d27d",
                title="HELP",
            )
        if self.state.pending_monster_slot is not None:
            card = self.state.room[self.state.pending_monster_slot]
            assert card is not None
            damage = max(0, card.value - (self.state.weapon.value if self.state.weapon else 0))
            return Panel(
                Group(
                    Text(f"{card.title}: W uses weapon for {damage} damage, B fights bare for {card.value}.", style="bold #ffffff"),
                    Text(""),
                    shortcut_hint,
                ),
                border_style="#ffffff",
                title="HELP",
            )
        left = 3 - self.state.turn_taken
        avoid = "available" if not self.state.avoided_last_room and self.state.turn_taken == 0 else "locked"
        return Panel(
            Group(
                Text(f"Take {left} more card(s). Avoid room: {avoid}.", style="#f2dfb2"),
                warning_line,
                Text(""),
                shortcut_hint,
            ),
            border_style="#604c37",
            title="HELP",
        )

    def selected_warning(self) -> str:
        card = self.state.room[self.state.selected_slot]
        if not card or card.kind != "Monster":
            return ""
        default_uses_weapon = self.state.can_use_weapon(card)
        damage = max(0, card.value - self.state.weapon.value) if default_uses_weapon and self.state.weapon else card.value
        if damage >= self.state.health:
            method = "with weapon" if default_uses_weapon else "barehanded"
            return f"Warning: taking {card.title} {method} deals {damage} damage and will kill you."
        if default_uses_weapon and card.value >= self.state.health:
            return f"Barehanded warning: {card.title} deals {card.value} damage and will kill you."
        return ""

    def render_log(self) -> RenderableType:
        lines = [Text(line, style="#d2b98d") for line in self.state.log[-6:]]
        return Panel(Group(*lines), title="TABLE TALK", border_style="#604c37")

    def render_dungeon(self) -> RenderableType:
        room_count = sum(card is not None for card in self.state.room)
        body = Group(
            Text(f"Dungeon {len(self.state.dungeon):>2}", style="bold #f8d27d"),
            Text(f"Room    {room_count:>2}", style="#d2b98d"),
            Text(f"Discard {len(self.state.discard):>2}", style="#8e7151"),
        )
        return Panel(body, title="PILES", border_style="#7d6244")

def main() -> None:
    ScoundrelApp().run()


if __name__ == "__main__":
    main()
