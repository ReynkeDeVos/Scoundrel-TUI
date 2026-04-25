from __future__ import annotations

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.widgets import Static

from scoundrel_tui.game import GameState
from scoundrel_tui.rendering import ScoundrelRenderer


class ScoundrelApp(ScoundrelRenderer, App[None]):
    CSS = """
    Screen {
        layers: base overlay;
        background: #070909;
        color: #d8cdb9;
    }

    #shell {
        layer: base;
        padding: 1 2;
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
        height: 4;
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
    """

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


def main() -> None:
    ScoundrelApp().run()


__all__ = ["ScoundrelApp", "main"]
