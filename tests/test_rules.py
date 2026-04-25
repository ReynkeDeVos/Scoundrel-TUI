from PIL import Image
from rich.console import Console
from textual.geometry import Size
from textual_image.renderable import tgp

from scoundrel_tui.app import (
    Card,
    BARE_HANDS_IMAGE,
    GameState,
    MONSTER_PORTRAITS,
    PIXEL_MONSTER_PORTRAITS,
    PIXEL_POTION_IMAGES,
    PIXEL_WEAPON_IMAGES,
    POTION_IMAGES,
    ScoundrelApp,
    SHELL_HORIZONTAL_MARGIN,
    STORY_IMAGES,
    Suit,
    WEAPON_IMAGES,
    asset_for,
    cached_terminal_image,
    fitted_image,
)


def test_deck_setup_matches_scoundrel_pdf() -> None:
    state = GameState.fresh()
    cards = [*state.dungeon, *[card for card in state.room if card]]

    assert len(cards) == 44
    assert sum(card.kind == "Monster" for card in cards) == 26
    assert sum(card.kind == "Weapon" for card in cards) == 9
    assert sum(card.kind == "Potion" for card in cards) == 9


def test_room_slots_stay_stable_until_refill() -> None:
    state = GameState(
        dungeon=[Card(Suit.HEARTS, 2), Card(Suit.DIAMONDS, 4), Card(Suit.CLUBS, 5)],
        room=[Card(Suit.DIAMONDS, 5), Card(Suit.HEARTS, 3), Card(Suit.SPADES, 4), Card(Suit.CLUBS, 8)],
    )

    state.take_slot(0)
    assert state.room[0] is None
    assert state.room[1:] == [Card(Suit.HEARTS, 3), Card(Suit.SPADES, 4), Card(Suit.CLUBS, 8)]

    state.take_slot(1)
    assert state.room[0] is None
    assert state.room[1] is None
    assert state.room[2:] == [Card(Suit.SPADES, 4), Card(Suit.CLUBS, 8)]

    state.take_slot(2)
    assert state.room == [Card(Suit.HEARTS, 2), Card(Suit.DIAMONDS, 4), Card(Suit.CLUBS, 5), Card(Suit.CLUBS, 8)]


def test_weapon_stack_restricts_future_monsters() -> None:
    state = GameState(
        dungeon=[],
        room=[Card(Suit.DIAMONDS, 5), Card(Suit.SPADES, 9), Card(Suit.CLUBS, 10), Card(Suit.HEARTS, 2)],
    )
    state.take_slot(0)
    state.take_slot(1)
    state.resolve_slot(1, use_weapon=True)

    assert state.health == 16
    assert state.can_use_weapon(Card(Suit.CLUBS, 8))
    assert not state.can_use_weapon(Card(Suit.CLUBS, 9))
    assert not state.can_use_weapon(Card(Suit.CLUBS, 10))


def test_taking_monster_uses_weapon_by_default_when_possible() -> None:
    state = GameState(
        dungeon=[],
        room=[Card(Suit.DIAMONDS, 5), Card(Suit.SPADES, 9), Card(Suit.CLUBS, 4), Card(Suit.HEARTS, 2)],
    )

    state.take_slot(0)
    state.take_slot(1)

    assert state.health == 16
    assert state.weapon_stack == [Card(Suit.SPADES, 9)]


def test_monster_portraits_are_mapped_by_suit_and_value() -> None:
    assert asset_for(Card(Suit.CLUBS, 2)).name.startswith("02-")
    assert asset_for(Card(Suit.CLUBS, 13)).name.startswith("13-")
    assert asset_for(Card(Suit.CLUBS, 14)).name.startswith("14-")
    assert asset_for(Card(Suit.SPADES, 2)).name.startswith("02-")
    assert asset_for(Card(Suit.SPADES, 13)).name.startswith("13-")
    assert asset_for(Card(Suit.SPADES, 14)).name.startswith("14-")

    for suit, portraits in MONSTER_PORTRAITS.items():
        assert set(portraits) == set(range(2, 15))
        for value, path in portraits.items():
            assert path.exists(), f"{suit} {value} portrait missing: {path}"


def test_weapon_and_potion_images_are_mapped_by_value() -> None:
    assert BARE_HANDS_IMAGE.exists()
    assert set(WEAPON_IMAGES) == set(range(2, 11))
    assert set(POTION_IMAGES) == set(range(2, 11))
    assert asset_for(Card(Suit.DIAMONDS, 2)).name.startswith("02-")
    assert asset_for(Card(Suit.DIAMONDS, 10)).name.startswith("10-")
    assert asset_for(Card(Suit.HEARTS, 2)).name.startswith("02-")
    assert asset_for(Card(Suit.HEARTS, 10)).name.startswith("10-")

    for value, path in {**WEAPON_IMAGES, **POTION_IMAGES}.items():
        assert path.exists(), f"value {value} item image missing: {path}"


def test_all_card_images_can_be_loaded_and_fitted() -> None:
    paths = [
        BARE_HANDS_IMAGE,
        *WEAPON_IMAGES.values(),
        *POTION_IMAGES.values(),
        *(path for portraits in MONSTER_PORTRAITS.values() for path in portraits.values()),
        *PIXEL_WEAPON_IMAGES.values(),
        *PIXEL_POTION_IMAGES.values(),
        *(path for portraits in PIXEL_MONSTER_PORTRAITS.values() for path in portraits.values()),
    ]
    assert len(paths) == 89

    for path in paths:
        with Image.open(path) as image:
            image.verify()
        fitted = fitted_image(str(path), 378, 576)
        with Image.open(fitted) as image:
            assert image.size == (378, 576)


def test_scaled_item_art_keeps_full_card_canvas() -> None:
    full = fitted_image(str(WEAPON_IMAGES[2]), 378, 576)
    scaled = fitted_image(str(WEAPON_IMAGES[2]), 378, 576, 0.5)

    with Image.open(full) as image:
        assert image.size == (378, 576)
    with Image.open(scaled) as image:
        assert image.size == (378, 576)


def test_terminal_images_are_reused_between_room_renders(monkeypatch) -> None:
    monkeypatch.setenv("SCOUNDREL_IMAGE_MODE", "kitty")
    cached_terminal_image.cache_clear()
    calls = []
    monkeypatch.setattr(tgp, "_send_tgp_message", lambda **kwargs: calls.append(kwargs))
    app = ScoundrelApp()
    app._size = Size(220, 60)
    app.state = GameState(
        room=[
            Card(Suit.CLUBS, 8),
            Card(Suit.SPADES, 13),
            Card(Suit.DIAMONDS, 5),
            Card(Suit.HEARTS, 6),
        ],
    )
    console = Console(width=220, record=True)

    console.print(app.render_room())
    first_render_calls = len(calls)
    console.print(app.render_room())
    second_render_calls = len(calls) - first_render_calls

    assert first_render_calls > 0
    assert second_render_calls == 0


def test_pixel_art_assets_are_mapped_by_value() -> None:
    assert set(PIXEL_WEAPON_IMAGES) == set(range(2, 11))
    assert set(PIXEL_POTION_IMAGES) == set(range(2, 11))
    for portraits in PIXEL_MONSTER_PORTRAITS.values():
        assert set(portraits) == set(range(2, 15))

    assert asset_for(Card(Suit.CLUBS, 2), pixel=True).parent.name.startswith("pixel-")
    assert asset_for(Card(Suit.SPADES, 14), pixel=True).parent.name.startswith("pixel-")
    assert asset_for(Card(Suit.DIAMONDS, 10), pixel=True).parent.name.startswith("pixel-")
    assert asset_for(Card(Suit.HEARTS, 10), pixel=True).parent.name.startswith("pixel-")


def test_story_overlay_assets_are_available() -> None:
    assert set(STORY_IMAGES) == {"welcome", "death", "win"}
    for path in STORY_IMAGES.values():
        assert path.exists()
        with Image.open(path) as image:
            image.verify()


def test_story_overlays_render_expected_titles(monkeypatch) -> None:
    monkeypatch.setenv("SCOUNDREL_IMAGE_MODE", "off")
    app = ScoundrelApp()
    console = Console(width=120, record=True)

    for kind, title in [("death", "YOU DIED"), ("win", "YOU WIN")]:
        console.begin_capture()
        console.print(app.render_overlay(kind))
        assert title in console.end_capture()


def test_only_one_potion_heals_per_room() -> None:
    state = GameState(
        dungeon=[Card(Suit.SPADES, 2), Card(Suit.CLUBS, 2), Card(Suit.DIAMONDS, 2)],
        room=[Card(Suit.HEARTS, 8), Card(Suit.HEARTS, 5), Card(Suit.CLUBS, 2), Card(Suit.SPADES, 3)],
        health=10,
    )

    state.take_slot(0)
    state.take_slot(1)

    assert state.health == 18
    assert state.used_potion


def test_card_panels_render_with_identical_height(monkeypatch) -> None:
    monkeypatch.setenv("SCOUNDREL_IMAGE_MODE", "off")
    app = ScoundrelApp()
    app._size = Size(220, 60)
    app.state = GameState(
        room=[Card(Suit.CLUBS, 8), Card(Suit.DIAMONDS, 5), Card(Suit.HEARTS, 6), None],
    )
    console = Console(width=220, record=True)

    heights = []
    for index, card in enumerate(app.state.room):
        lines = console.render_lines(app.card_panel(index, card), console.options.update(width=60))
        heights.append(len(lines))

    assert len(set(heights)) == 1


def test_weapon_stack_panel_shows_highest_allowed_next_value() -> None:
    app = ScoundrelApp()
    app.state = GameState(weapon=Card(Suit.DIAMONDS, 5), weapon_stack=[Card(Suit.SPADES, 4)])
    console = Console(width=100, record=True)

    console.print(app.render_weapon())
    rendered = console.export_text()
    assert "damage 3" in rendered
    assert "Next must be ≤ 3" in rendered


def test_weapon_damage_display_never_exceeds_base_value() -> None:
    app = ScoundrelApp()
    app.state = GameState(weapon=Card(Suit.DIAMONDS, 5), weapon_stack=[Card(Suit.SPADES, 12)])
    console = Console(width=100, record=True)

    console.print(app.render_weapon())
    rendered = console.export_text()
    assert "damage 5" in rendered
    assert "damage 11" not in rendered
    assert "Next must be ≤ 11" in rendered


def test_status_weapon_condition_uses_scoundrel_limit() -> None:
    app = ScoundrelApp()

    app.state = GameState()
    assert app.weapon_condition() == "unarmed"

    app.state = GameState(weapon=Card(Suit.DIAMONDS, 5))
    assert app.weapon_condition() == "any monster"

    app.state = GameState(weapon=Card(Suit.DIAMONDS, 5), weapon_stack=[Card(Suit.SPADES, 4)])
    assert app.weapon_condition() == "next ≤ 3"


def test_status_health_bar_shows_selected_card_preview() -> None:
    app = ScoundrelApp()
    app.state = GameState(
        room=[Card(Suit.CLUBS, 9), None, None, None],
        weapon=Card(Suit.DIAMONDS, 5),
        weapon_stack=[Card(Suit.SPADES, 10)],
        health=12,
    )

    line = app.health_status_value()
    assert line.plain == "12/20 ███▏████▌▌▌▌░░░░░░░░"
    styles = {span.style for span in line.spans}
    assert "bold #ff7a1a" in styles
    assert "bold #ffffff" in styles
    assert "#71d083" in styles


def test_status_row_renders_as_two_lines() -> None:
    app = ScoundrelApp()
    app.state = GameState(
        room=[Card(Suit.CLUBS, 9), Card(Suit.DIAMONDS, 5), Card(Suit.HEARTS, 6), Card(Suit.SPADES, 4)],
        health=20,
    )
    console = Console(width=100, record=True)

    console.print(app.render_status())
    lines = [line for line in console.export_text().splitlines() if line.strip()]

    assert len(lines) == 2
    assert "Health" in lines[0]
    assert "Equipped weapon" in lines[0]
    assert "Weapon condition" in lines[0]
    assert "Remaining cards" in lines[0]
    assert "20/20" in lines[1]


def test_estimated_room_size_accounts_for_shell_margin() -> None:
    app = ScoundrelApp()
    app._size = Size(180, 50)

    width, height = app.estimated_room_size()

    assert width == 180 - (SHELL_HORIZONTAL_MARGIN * 2) - 2
    assert height == 40


def test_monster_cards_label_effective_damage_as_monster_damage(monkeypatch) -> None:
    monkeypatch.setenv("SCOUNDREL_IMAGE_MODE", "off")
    app = ScoundrelApp()
    app._size = Size(220, 60)
    app.state = GameState(
        room=[Card(Suit.CLUBS, 9), None, None, None],
        weapon=Card(Suit.DIAMONDS, 5),
    )
    console = Console(width=80, record=True)

    console.print(app.card_panel(0, app.state.room[0]))
    rendered = console.export_text()
    assert "monster damage 4" in rendered
    assert "weapon damage" not in rendered


def test_selected_card_panel_contains_visible_selected_label(monkeypatch) -> None:
    monkeypatch.setenv("SCOUNDREL_IMAGE_MODE", "off")
    app = ScoundrelApp()
    app._size = Size(220, 60)
    app.state = GameState(
        room=[Card(Suit.CLUBS, 9), Card(Suit.DIAMONDS, 5), None, None],
        selected_slot=1,
    )
    console = Console(width=80, record=True)

    console.print(app.card_panel(1, app.state.room[1]))

    assert "SELECTED" in console.export_text()


def test_quit_requires_confirmation() -> None:
    app = ScoundrelApp()
    app.refresh_board = lambda: None

    app.action_quit()

    assert app.state.confirm_quit
    console = Console(width=100, record=True)
    console.print(app.render_prompt())
    assert "Press Q again to confirm" in console.export_text()


def test_health_preview_uses_marker_segments() -> None:
    app = ScoundrelApp()
    app.state = GameState(
        room=[Card(Suit.CLUBS, 9), None, None, None],
        weapon=Card(Suit.DIAMONDS, 5),
        weapon_stack=[Card(Suit.SPADES, 10)],
        health=12,
    )

    line = app.render_health().renderable.renderables[1].renderable
    assert line.plain == "12/20  ██████▏████████▌▌▌▌▌▌▌░░░░░░░░░░░░░░"
    styles = {span.style for span in line.spans}
    assert "bold #ff7a1a" in styles
    assert "bold #ffffff" in styles
    assert "#71d083" in styles


def test_zero_damage_weapon_preview_only_marks_barehand_position() -> None:
    app = ScoundrelApp()
    app.state = GameState(
        room=[Card(Suit.CLUBS, 5), None, None, None],
        weapon=Card(Suit.DIAMONDS, 7),
        weapon_stack=[Card(Suit.SPADES, 14)],
        health=13,
    )

    line = app.render_health().renderable.renderables[1].renderable
    assert "▌" not in line.plain
    assert "▏" in line.plain
    styles = {span.style for span in line.spans}
    assert "bold #ffffff" in styles
    assert "#71d083" in styles
