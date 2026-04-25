from __future__ import annotations

from rich import box
from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.widgets import Static

from scoundrel_tui.assets import BARE_HANDS_IMAGE, STORY_IMAGES, asset_for
from scoundrel_tui.cards import Card, MAX_HEALTH
from scoundrel_tui.images import card_art, card_image, card_spacer


class ScoundrelRenderer:
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
        table = Table.grid(expand=True)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        weapon = self.state.weapon.title if self.state.weapon else "Bare hands"
        condition = self.weapon_condition()
        remaining = len(self.state.dungeon) + sum(card is not None for card in self.state.room)
        table.add_row(
            self.status_item("Health:", f"{max(0, self.state.health)}/{MAX_HEALTH}", self.health_style(self.state.health)),
            self.status_item("Equipped weapon:", weapon, "#d8cdb9"),
            self.status_item("Weapon condition:", condition, "#d8cdb9"),
            self.status_item("Remaining cards:", str(remaining), "#d8cdb9"),
        )
        return Align.center(table, vertical="middle")

    def status_item(self, label: str, value: str, value_style: str) -> Text:
        style = value_style if value_style.startswith("bold") else f"bold {value_style}"
        return Text.assemble((label, "#776f63"), ("  ", "#776f63"), (value, style))

    def weapon_condition(self) -> str:
        weapon = self.state.weapon
        if weapon is None:
            return "-"
        if not self.state.weapon_stack:
            return f"{weapon.value}/{weapon.value}"
        allowed = max(0, self.state.weapon_stack[-1].value - 1)
        return f"{min(weapon.value, allowed)}/{weapon.value}"

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
        return max(96, self.size.width - 6), max(26, self.size.height - 10)

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


__all__ = ["ScoundrelRenderer"]
