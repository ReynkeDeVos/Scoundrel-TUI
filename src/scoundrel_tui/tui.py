from __future__ import annotations

import random
from pathlib import Path

from PIL import Image
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

from scoundrel_tui.artwork import (
    BARE_HANDS_IMAGE,
    asset_for,
    card_art,
    card_image,
    card_spacer,
)
from scoundrel_tui.config import (
    DEFAULT_WIN_FLAVOR_TEXTS,
    DEATH_STORY_IMAGES,
    ENTRY_STORY_IMAGES,
    MAX_HEALTH,
    SHELL_HORIZONTAL_MARGIN,
    STORY_IMAGES,
    WELCOME_MESSAGES,
    WIN_FLAVOR_TEXTS,
    WIN_STORY_IMAGES,
)
from scoundrel_tui.game import Card, GameState, Suit

__all__ = ["ScoundrelApp", "main"]

DUNGEON_BLACK = "#070909"
PARCHMENT_TEXT = "#d8cdb9"
PARCHMENT_BRIGHT = "#f1e5c8"
PARCHMENT_MUTED = "#d2b98d"
ASH_LABEL = "#8f8679"
ASH_LOG = "#9f9688"
EMBER_GOLD = "#f8d27d"
BRASS_BORDER = "#b8a06d"
COPPER_LABEL = "#9e8454"
DULL_COPPER = "#604c37"
MONSTER_RED = "#f05d4f"
LETHAL_RED = "#ff3b30"
WARNING_RED = "#d9695d"
WEAPON_BLUE = "#74b7e8"
WEAPON_FOCUS_BLUE = "#95c7ff"
WEAPON_BORDER_BLUE = "#5aa6d6"
POTION_GREEN = "#71d083"
WIN_GREEN = "#8df59b"
POTION_PREVIEW_GREEN = "#b8ff7a"
DANGER_ORANGE = "#ff7a1a"
DAMAGE_AMBER = "#d9a15c"
EMPTY_BORDER = "#2c3030"
DEAD_CELL = "#323232"
QUIET_TEXT = "#595959"
INACTIVE_MARK = "#4b4540"
CARD_META = "#71685c"
ACTION_TEXT = "#c6b9a2"
CONFIRM_TEXT = "#c9a86a"
OVERLAY_MIN_WIDTH = 82
OVERLAY_MIN_HEIGHT = 24
OVERLAY_MAX_WIDTH = 100
OVERLAY_MAX_HEIGHT = 30
OVERLAY_EDGE_GUTTER = 4
OVERLAY_VERTICAL_GUTTER = 2
OVERLAY_MIN_IMAGE_HEIGHT = 11
OVERLAY_MAX_IMAGE_HEIGHT = 16
OVERLAY_MIN_LANDSCAPE_IMAGE_WIDTH = 58
OVERLAY_MAX_LANDSCAPE_IMAGE_WIDTH = 74


class ScoundrelApp(App[None]):
    CSS = """
    Screen {
        layers: base overlay;
        background: __DUNGEON_BLACK__;
        color: __PARCHMENT_TEXT__;
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
        width: __OVERLAY_MIN_WIDTH__;
        height: __OVERLAY_MIN_HEIGHT__;
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
    """.replace("__SHELL_HORIZONTAL_MARGIN__", str(SHELL_HORIZONTAL_MARGIN)).replace(
        "__DUNGEON_BLACK__", DUNGEON_BLACK
    ).replace("__PARCHMENT_TEXT__", PARCHMENT_TEXT).replace(
        "__OVERLAY_MIN_WIDTH__", str(OVERLAY_MIN_WIDTH)
    ).replace("__OVERLAY_MIN_HEIGHT__", str(OVERLAY_MIN_HEIGHT))

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
        Binding("q", "request_quit", "Quit"),
    ]

    state: reactive[GameState] = reactive(GameState.fresh, recompose=False)
    pixel_art: reactive[bool] = reactive(False, recompose=False)
    overlay: reactive[str | None] = reactive("welcome", recompose=False)

    def __init__(self) -> None:
        super().__init__()
        self.welcome_message = random.choice(WELCOME_MESSAGES)
        self.overlay_images: dict[str, Path] = {}
        self.overlay_flavors: dict[str, str] = {}
        self.set_overlay("welcome")

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
        self.refresh_overlay()
        self.call_after_refresh(self.refresh_board)
        self.call_after_refresh(self.refresh_overlay)

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
            self.set_overlay(None)
        elif self.state.confirm_new_game:
            self.state = GameState.fresh()
            self.set_overlay(None)
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
        if self.overlay == "welcome":
            self.set_overlay(None)
            self.refresh_board()
            return
        if self.overlay:
            return
        self.action_take(self.state.selected_slot)

    def action_take(self, slot: int) -> None:
        if self.overlay == "welcome":
            self.set_overlay(None)
            self.refresh_board()
            return
        if self.overlay:
            return
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

    def action_request_quit(self) -> None:
        self.request_quit()

    def request_quit(self) -> None:
        if self.overlay == "welcome":
            self.exit()
            return
        if self.state.game_over:
            self.exit()
            return
        if self.state.confirm_quit:
            self.exit()
            return
        self.set_overlay(None)
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
            self.set_overlay("win" if self.state.won else "death")
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
        overlay_width, overlay_height = self.overlay_dimensions()
        overlay.styles.width = overlay_width
        overlay.styles.height = overlay_height
        overlay.update(self.render_overlay(self.overlay))

    def render_overlay(self, kind: str) -> RenderableType:
        title, kicker, message, metric, action, border, title_style = self.overlay_copy(kind)
        image = self.overlay_image(kind)
        image_width, image_height = self.overlay_image_size(image)
        footer: list[RenderableType] = [Align.center(Text(message, style=PARCHMENT_MUTED, justify="center")), Text("")]
        if metric:
            footer.append(Align.center(Text(metric, style=f"bold {EMBER_GOLD}", justify="center")))
            footer.append(Text(""))
        footer.append(Align.center(self.overlay_action_text(action)))

        body = Group(
            Text(""),
            *self.overlay_heading(kicker),
            Align.center(Text(title, style=title_style)),
            Text(""),
            Align.center(
                card_image(image if image.exists() else None, width=image_width, height=image_height),
                vertical="middle",
                width=image_width,
                height=image_height,
            ),
            Text(""),
            *footer,
            Text(""),
        )
        return Panel(body, border_style=border, box=box.SQUARE)

    def overlay_heading(self, kicker: str) -> list[RenderableType]:
        if not kicker:
            return []
        return [Align.center(Text(kicker, style=ASH_LABEL))]

    def overlay_action_text(self, action: str) -> Text:
        if action.startswith("[Enter]"):
            return Text.assemble(
                ("[Enter]", COPPER_LABEL),
                (" begin   ", QUIET_TEXT),
                ("[Q]", COPPER_LABEL),
                (" quit", QUIET_TEXT),
                no_wrap=True,
                overflow="ellipsis",
            )
        return Text.assemble(
            ("[N]", COPPER_LABEL),
            (" new run   ", QUIET_TEXT),
            ("[Q]", COPPER_LABEL),
            (" quit", QUIET_TEXT),
            no_wrap=True,
            overflow="ellipsis",
        )

    def overlay_dimensions(self) -> tuple[int, int]:
        width = min(OVERLAY_MAX_WIDTH, max(OVERLAY_MIN_WIDTH, self.size.width - OVERLAY_EDGE_GUTTER))
        height = min(OVERLAY_MAX_HEIGHT, max(OVERLAY_MIN_HEIGHT, self.size.height - OVERLAY_VERTICAL_GUTTER))
        return width, height

    def overlay_copy(self, kind: str) -> tuple[str, str, str, str, str, str, str]:
        if kind == "welcome":
            return (
                "WELCOME TO THE DUNGEON",
                "Scoundrel",
                self.welcome_message,
                "",
                "[Enter] begin   [Q] quit",
                BRASS_BORDER,
                f"bold {PARCHMENT_BRIGHT}",
            )
        if kind == "win":
            return (
                "YOU WIN",
                "",
                f"The Orb is yours. {self.win_flavor_text()}",
                f"SCORE {self.state.score}",
                "[N] new run   [Q] quit",
                POTION_GREEN,
                f"bold {WIN_GREEN}",
            )
        return (
            "YOU DIED",
            "",
            "The dungeon keeps its debt. Remaining monsters are counted against you.",
            f"FINAL SCORE {self.state.score}",
            "[N] new run   [Q] quit",
            MONSTER_RED,
            f"bold {MONSTER_RED}",
        )

    def set_overlay(self, kind: str | None) -> None:
        if kind and kind != self.overlay:
            self.overlay_images[kind] = self.random_story_image(kind)
            self.overlay_flavors.pop(kind, None)
        self.overlay = kind

    def overlay_image(self, kind: str) -> Path:
        if kind not in self.overlay_images:
            self.overlay_images[kind] = self.random_story_image(kind)
        return self.overlay_images[kind]

    def random_story_image(self, kind: str) -> Path:
        pool = {
            "welcome": ENTRY_STORY_IMAGES,
            "death": DEATH_STORY_IMAGES,
            "win": WIN_STORY_IMAGES,
        }.get(kind, ())
        if pool:
            return random.choice(pool)
        return STORY_IMAGES[kind]

    def win_flavor_text(self) -> str:
        if "win" not in self.overlay_flavors:
            image = self.overlay_image("win")
            pool = WIN_FLAVOR_TEXTS.get(image.stem, DEFAULT_WIN_FLAVOR_TEXTS)
            self.overlay_flavors["win"] = random.choice(pool)
        return self.overlay_flavors["win"]

    def overlay_image_size(self, image: Path) -> tuple[int, int]:
        overlay_width, overlay_height = self.overlay_dimensions()
        image_height = min(
            OVERLAY_MAX_IMAGE_HEIGHT,
            max(OVERLAY_MIN_IMAGE_HEIGHT, overlay_height - 14),
        )
        landscape_width = min(
            OVERLAY_MAX_LANDSCAPE_IMAGE_WIDTH,
            max(OVERLAY_MIN_LANDSCAPE_IMAGE_WIDTH, overlay_width - 26),
        )
        try:
            with Image.open(image) as loaded:
                width, height = loaded.size
        except OSError:
            return landscape_width, image_height
        if height > width:
            return round(image_height * 1.6), image_height
        return landscape_width, image_height

    def death_overlay_image(self) -> Path:
        return self.overlay_image("death")

    def render_status(self) -> RenderableType:
        table = Table.grid(expand=False, padding=(0, 6))
        for _ in range(4):
            table.add_column(no_wrap=True)
        weapon = self.state.weapon.title if self.state.weapon else "Bare hands"
        condition = self.weapon_condition()
        remaining = len(self.state.dungeon) + sum(card is not None for card in self.state.room)
        table.add_row(
            self.status_section("Health", self.health_status_value()),
            self.weapon_status_section(weapon, condition),
            self.status_section("Elite kills", self.strong_kills_status_value()),
            self.status_section("Remaining cards", self.status_value(str(remaining), "#d8cdb9")),
        )
        return Align.center(table, vertical="middle")

    def status_section(self, label: str, value: RenderableType) -> RenderableType:
        table = Table.grid(expand=False)
        table.add_column(no_wrap=True)
        table.add_row(self.status_label(label))
        table.add_row(value)
        return table

    def weapon_status_section(self, weapon: str, condition: str) -> RenderableType:
        table = Table.grid(expand=False, padding=(0, 1))
        for _ in range(2):
            table.add_column(no_wrap=True)
        table.add_row(
            self.status_label("Equipped weapon"),
            self.status_label("Weapon condition"),
        )
        table.add_row(
            self.weapon_status_value(weapon),
            self.status_value(condition, "#d8cdb9"),
        )
        return table

    def health_status_value(self) -> Text:
        health = max(0, self.state.health)
        style = self.health_style(health)
        value_style = style if style.startswith("bold") else f"bold {style}"
        return Text.assemble(
            (f"{health:>2}/{MAX_HEALTH} ", value_style),
            self.health_bar(health, width=MAX_HEALTH),
            no_wrap=True,
            overflow="ellipsis",
        )

    def status_label(self, label: str) -> Text:
        return Text(label, style=f"bold {ASH_LABEL}", no_wrap=True, overflow="ellipsis")

    def status_value(self, value: str, value_style: str) -> Text:
        style = value_style if value_style.startswith("bold") else f"bold {value_style}"
        return Text(value, style=style, no_wrap=True, overflow="ellipsis")

    def strong_kills_status_value(self) -> RenderableType:
        slain = self.strong_monsters_killed()
        table = Table.grid(expand=False)
        table.add_column(no_wrap=True)
        table.add_row(self.strong_kill_row(slain, suit=Suit.CLUBS))
        table.add_row(self.strong_kill_row(slain, suit=Suit.SPADES))
        return table

    def strong_kill_row(self, slain: list[Card], *, suit: Suit, prefix: str = "") -> Text:
        symbols: list[tuple[str, str]] = []
        if prefix:
            symbols.append((prefix, f"bold {PARCHMENT_TEXT}"))
        slain_values = {card.value for card in slain if card.suit == suit}
        for value in (14, 13, 12, 11):
            card = Card(suit, value)
            style = f"strike bold {DAMAGE_AMBER}" if value in slain_values else f"bold {INACTIVE_MARK}"
            symbols.append((self.elite_kill_symbol(card), style))
        symbols.append((" ", INACTIVE_MARK))
        return Text.assemble(*symbols, no_wrap=True, overflow="ellipsis")

    def elite_kill_symbol(self, card: Card) -> str:
        suit_glyphs = {
            Suit.CLUBS: "♧",
            Suit.SPADES: "♤",
        }
        return f"{card.rank}{suit_glyphs[card.suit]}"

    def strong_monsters_killed(self) -> list[Card]:
        killed = [
            card
            for card in [*self.state.discard, *self.state.weapon_stack]
            if card.kind == "Monster" and card.value in (14, 13, 12, 11)
        ]
        return sorted(killed, key=lambda card: (-card.value, card.suit.value))

    def weapon_status_value(self, weapon: str) -> RenderableType:
        table = Table.grid(expand=False, padding=(0, 1))
        table.add_column(width=3)
        table.add_column(no_wrap=True)
        table.add_row(
            card_image(self.equipped_weapon_image(), width=3, height=1, content_scale=1.0),
            self.status_value(weapon, "#d8cdb9"),
        )
        return table

    def equipped_weapon_image(self) -> Path | None:
        if self.state.weapon:
            return asset_for(self.state.weapon, pixel=False)
        return BARE_HANDS_IMAGE

    def weapon_condition(self) -> str:
        weapon = self.state.weapon
        if weapon is None:
            return "unarmed"
        if not self.state.weapon_stack:
            return "any monster"
        allowed = self.state.weapon_stack[-1].value - 1
        if allowed < 2:
            return "broken"
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
            return POTION_GREEN
        if health > 5:
            return "#f8b65a"
        return f"bold {MONSTER_RED}"

    def health_bar(self, health: int, width: int = MAX_HEALTH) -> Text:
        current = max(0, min(MAX_HEALTH, health))
        default_target, bare_target, potion_target = self.health_preview_targets()
        bar = Text()
        for cell in range(width):
            index = min(MAX_HEALTH, (cell * MAX_HEALTH) // width + 1)
            if potion_target is not None and current < index <= potion_target:
                bar.append("▌", style=f"bold {POTION_PREVIEW_GREEN}")
            elif index <= current:
                if bare_target is not None and self.health_index_starts_here(cell, bare_target + 1, width):
                    bar.append("▏", style=f"bold {PARCHMENT_BRIGHT}")
                elif default_target is not None and index > default_target:
                    bar.append("▌", style=f"bold {DANGER_ORANGE}")
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
        rows: list[RenderableType] = []
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
        table = Table.grid(expand=False, padding=(0, 1))
        for _ in range(4):
            table.add_column(width=card_width + 4)
        cells = [self.card_cell(index, card) for index, card in enumerate(self.state.room)]
        table.add_row(*cells)
        return Align.center(table, vertical="middle")

    def card_cell(self, index: int, card: Card | None) -> RenderableType:
        selected = index == self.state.selected_slot and card is not None
        return self.card_panel(index, card, selected=selected)

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
        card_width = max(25, (room_inner_width - 26) // 4)
        card_height = max(24, room_height - 2)

        image_width = max(15, card_width - 8)
        image_height = max(10, card_height - 12)
        return card_width, card_height, image_width, image_height

    def estimated_room_size(self) -> tuple[int, int]:
        outer_width = self.size.width - (SHELL_HORIZONTAL_MARGIN * 2)
        return max(96, outer_width - 2), max(26, self.size.height - 10)

    def card_panel(self, index: int, card: Card | None, *, selected: bool = False) -> RenderableType:
        pending = index == self.state.pending_monster_slot
        card_width, card_height, image_width, image_height = self.card_dimensions()
        if card is None:
            body = self.fixed_card_body(
                [
                    card_spacer(image_width, image_height),
                    Align.center(Text("empty", style=DEAD_CELL)),
                ],
                card_width,
                card_height,
            )
            return Panel(
                body,
                title=f" {index + 1} ",
                subtitle=" ",
                border_style=EMPTY_BORDER,
                box=box.SQUARE,
                width=card_width,
                height=card_height,
                expand=True,
            )
        path = asset_for(card, pixel=self.pixel_art)
        label = Text.assemble(
            (card.title, f"bold {self.kind_color(card)}"),
            ("  ", CARD_META),
            (card.kind.upper(), CARD_META),
        )
        parts: list[RenderableType] = [
            label,
        ]
        parts.extend(
            [
                card_art(card, path, width=image_width, height=image_height),
                Align.center(self.card_action_text(card)),
            ]
        )
        body = self.fixed_card_body(parts, card_width, card_height)
        border = self.selection_border_style(card) if selected else self.card_border_style(card)
        if pending:
            border = f"bold {PARCHMENT_BRIGHT}"
        title = f" {index + 1} {'◆' if selected else ' '} "
        return Panel(
            body,
            title=title,
            subtitle=self.slot_hint(card, selected=selected),
            border_style=border,
            box=box.SQUARE,
            width=card_width,
            height=card_height,
            expand=True,
        )

    def card_border_style(self, card: Card) -> str:
        if card.kind == "Monster":
            return self.monster_damage_style(card)
        return self.kind_color(card)

    def selection_border_style(self, card: Card | None) -> str:
        if card and self.card_is_lethal(card):
            return f"bold {LETHAL_RED}"
        return f"bold {PARCHMENT_BRIGHT}"

    def monster_damage_style(self, card: Card) -> str:
        damage = self.default_card_damage(card)
        if damage <= 0:
            return POTION_GREEN
        if damage >= self.state.health:
            return f"bold {LETHAL_RED}"
        health = max(1, self.state.health)
        ratio = damage / health
        if ratio >= 0.5:
            return DANGER_ORANGE
        if ratio >= 0.25:
            return DAMAGE_AMBER
        return BRASS_BORDER

    def default_card_damage(self, card: Card) -> int:
        if card.kind != "Monster":
            return 0
        if self.state.can_use_weapon(card) and self.state.weapon:
            return max(0, card.value - self.state.weapon.value)
        return card.value

    def card_is_lethal(self, card: Card) -> bool:
        return card.kind == "Monster" and self.default_card_damage(card) >= self.state.health

    def card_action_text(self, card: Card) -> Text:
        if card.kind == "Potion":
            if self.state.used_potion:
                return Text("SPENT  one potion per room", style=ACTION_TEXT, no_wrap=True, overflow="ellipsis")
            healed = min(MAX_HEALTH - self.state.health, card.value)
            return Text.assemble(
                ("HEAL ", f"bold {POTION_GREEN}"),
                (f"+{healed}", f"bold {POTION_GREEN}"),
                (f" / {card.value}", CARD_META),
                no_wrap=True,
                overflow="ellipsis",
            )
        if card.kind == "Weapon":
            return Text.assemble(
                ("EQUIP ", f"bold {WEAPON_BLUE}"),
                (str(card.value), f"bold {WEAPON_FOCUS_BLUE}"),
                no_wrap=True,
                overflow="ellipsis",
            )
        if self.state.can_use_weapon(card) and self.state.weapon:
            damage = max(0, card.value - self.state.weapon.value)
            style = self.monster_damage_style(card)
            return Text.assemble(
                ("DMG ", style if style.startswith("bold") else f"bold {style}"),
                (str(damage), style if style.startswith("bold") else f"bold {style}"),
                ("  weapon", CARD_META),
                no_wrap=True,
                overflow="ellipsis",
            )
        style = self.monster_damage_style(card)
        value_style = style if style.startswith("bold") else f"bold {style}"
        return Text.assemble(
            ("DMG ", value_style),
            (str(card.value), value_style),
            ("  bare", CARD_META),
            no_wrap=True,
            overflow="ellipsis",
        )

    def fixed_card_body(self, parts: list[RenderableType], card_width: int, card_height: int) -> RenderableType:
        return Align.center(
            Group(*parts),
            vertical="middle",
            width=card_width - 2,
            height=card_height - 2,
        )

    def kind_color(self, card: Card) -> str:
        if card.kind == "Monster":
            return MONSTER_RED
        if card.kind == "Weapon":
            return WEAPON_BLUE
        return POTION_GREEN

    def slot_hint(self, card: Card, *, selected: bool = False) -> str:
        if selected and self.card_is_lethal(card):
            return "LETHAL"
        if card.kind == "Monster":
            if self.state.can_use_weapon(card):
                return "W/B"
            return "bare"
        return "take"

    def render_message(self) -> RenderableType:
        warning = self.selected_warning()
        if self.state.confirm_new_game:
            text = Text("Press N again to abandon this run and start a new game.", style=f"bold {CONFIRM_TEXT}")
        elif self.state.confirm_quit:
            text = Text("Press Q again to quit.", style=f"bold {CONFIRM_TEXT}")
        elif self.state.game_over:
            result = "Escaped" if self.state.won else "Fell in the dungeon"
            text = Text(f"{result}. Score {self.state.score}.", style=CONFIRM_TEXT)
        elif self.state.pending_monster_slot is not None:
            card = self.state.room[self.state.pending_monster_slot]
            assert card is not None
            damage = max(0, card.value - (self.state.weapon.value if self.state.weapon else 0))
            text = Text(
                f"FIGHT {card.title}: W damage {damage}, B damage {card.value}. Esc cancels.",
                style=f"bold {PARCHMENT_TEXT}",
            )
        elif warning:
            text = Text(warning, style=f"bold {WARNING_RED}")
        elif self.state.log:
            text = Text(self.state.log[-1], style=f"bold {ASH_LOG}")
        else:
            text = Text("")
        return Align.center(text, vertical="middle")

    def render_footer(self) -> RenderableType:
        art = "pixel" if self.pixel_art else "portrait"
        avoid = "open" if not self.state.avoided_last_room and self.state.turn_taken == 0 else "locked"
        shortcuts = Text.assemble(
            ("[1-4]", COPPER_LABEL),
            (" take   ", QUIET_TEXT),
            ("[←/→]", COPPER_LABEL),
            (" select   ", QUIET_TEXT),
            ("[Enter]", COPPER_LABEL),
            (" take   ", QUIET_TEXT),
            ("[A]", COPPER_LABEL),
            (f" avoid:{avoid}   ", QUIET_TEXT),
            ("[W/B]", COPPER_LABEL),
            (" weapon/bare   ", QUIET_TEXT),
            ("[P]", COPPER_LABEL),
            (f" {art}   ", QUIET_TEXT),
            ("[N]", COPPER_LABEL),
            (" new   ", QUIET_TEXT),
            ("[Q]", COPPER_LABEL),
            (" quit", QUIET_TEXT),
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
                    Text(
                        f"{card.title}: W uses weapon for {damage} damage, B fights bare for {card.value}.",
                        style=f"bold {PARCHMENT_BRIGHT}",
                    ),
                    Text(""),
                    shortcut_hint,
                ),
                border_style=PARCHMENT_BRIGHT,
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
            return f"LETHAL {card.title}: {damage} damage {method}."
        if default_uses_weapon and card.value >= self.state.health:
            return f"BAREHAND LETHAL {card.title}: {card.value} damage."
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
