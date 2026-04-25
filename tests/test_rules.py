from PIL import Image
from rich.console import Console
from textual.geometry import Size
from textual_image.renderable import tgp

from scoundrel_tui.app import (
    Card,
    BARE_HANDS_IMAGE,
    DEATH_STORY_IMAGES,
    ENTRY_STORY_IMAGES,
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
    WELCOME_MESSAGES,
    WIN_STORY_IMAGES,
    asset_for,
    cached_terminal_image,
    fitted_image,
    is_pixel_asset,
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


def test_pixel_art_scaling_uses_sharp_cache_variant() -> None:
    pixel_path = PIXEL_WEAPON_IMAGES[2]

    assert is_pixel_asset(pixel_path)
    sharp = fitted_image(str(pixel_path), 120, 120, sharp=True)
    smooth = fitted_image(str(pixel_path), 120, 120, sharp=False)

    assert sharp != smooth
    assert "nearest" in sharp.name
    assert "smooth" in smooth.name


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
    assert WELCOME_MESSAGES
    for path in STORY_IMAGES.values():
        assert path.exists()
        with Image.open(path) as image:
            image.verify()
    assert {path.parent.name for path in DEATH_STORY_IMAGES} == {"death"}
    assert len(DEATH_STORY_IMAGES) > 1
    assert {path.parent.name for path in ENTRY_STORY_IMAGES} == {"entry"}
    assert len(ENTRY_STORY_IMAGES) > 1
    assert {path.parent.name for path in WIN_STORY_IMAGES} == {"win"}
    assert WIN_STORY_IMAGES
    for path in [*DEATH_STORY_IMAGES, *ENTRY_STORY_IMAGES, *WIN_STORY_IMAGES]:
        with Image.open(path) as image:
            image.verify()


def test_story_overlay_images_use_folder_pools_and_stay_stable(monkeypatch) -> None:
    monkeypatch.setenv("SCOUNDREL_IMAGE_MODE", "off")
    app = ScoundrelApp()

    assert app.overlay_image("welcome") in set(ENTRY_STORY_IMAGES)

    app.set_overlay("death")
    death_image = app.death_overlay_image()
    assert death_image in set(DEATH_STORY_IMAGES)
    assert {app.death_overlay_image() for _ in range(10)} == {death_image}

    app.set_overlay("win")
    assert app.overlay_image("win") in set(WIN_STORY_IMAGES)


def test_portrait_story_images_use_vertical_overlay_slot() -> None:
    app = ScoundrelApp()

    assert app.overlay_image_size(WIN_STORY_IMAGES[0]) == (34, 22)


def test_enter_does_not_cycle_game_over_overlay_image(monkeypatch) -> None:
    monkeypatch.setenv("SCOUNDREL_IMAGE_MODE", "off")
    app = ScoundrelApp()
    app.refresh_board = lambda: None
    app.set_overlay("death")
    image = app.death_overlay_image()

    app.action_take_selected()

    assert app.overlay == "death"
    assert app.death_overlay_image() == image


def test_story_overlays_render_expected_titles(monkeypatch) -> None:
    monkeypatch.setenv("SCOUNDREL_IMAGE_MODE", "off")
    app = ScoundrelApp()
    console = Console(width=120, record=True)

    for kind, title in [("welcome", "WELCOME TO THE DUNGEON"), ("death", "YOU DIED"), ("win", "YOU WIN")]:
        console.begin_capture()
        console.print(app.render_overlay(kind))
        assert title in console.end_capture()


def test_welcome_overlay_is_initial_and_enter_dismisses_it() -> None:
    app = ScoundrelApp()
    app.refresh_board = lambda: None

    assert app.overlay == "welcome"
    assert app.welcome_message in WELCOME_MESSAGES

    app.action_take_selected()

    assert app.overlay is None


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
    console = Console(width=140, record=True)

    console.print(app.render_weapon())
    rendered = console.export_text()
    assert "damage 3" in rendered
    assert "Next must be ≤ 3" in rendered


def test_weapon_damage_display_never_exceeds_base_value() -> None:
    app = ScoundrelApp()
    app.state = GameState(weapon=Card(Suit.DIAMONDS, 5), weapon_stack=[Card(Suit.SPADES, 12)])
    console = Console(width=140, record=True)

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

    app.state = GameState(weapon=Card(Suit.DIAMONDS, 5), weapon_stack=[Card(Suit.CLUBS, 2)])
    assert app.weapon_condition() == "broken"


def test_status_strong_kills_counts_only_jack_or_higher_monsters() -> None:
    app = ScoundrelApp()
    app.state = GameState(
        discard=[
            Card(Suit.CLUBS, 14),
            Card(Suit.CLUBS, 13),
            Card(Suit.SPADES, 10),
            Card(Suit.DIAMONDS, 13),
            Card(Suit.SPADES, 11),
        ],
        weapon_stack=[Card(Suit.CLUBS, 12), Card(Suit.SPADES, 14), Card(Suit.SPADES, 4)],
    )

    console = Console(width=40, record=True)
    console.print(app.strong_kills_status_value())
    rendered = console.export_text()

    assert [line.rstrip() for line in rendered.splitlines()] == ["A♣ K♣ Q♣", "A♠ J♠"]
    assert "10♠" not in rendered
    assert "K♦" not in rendered

    row = app.strong_kill_row(app.strong_monsters_killed(), suit=Suit.CLUBS)
    assert any("strike" in str(span.style) for span in row.spans)


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


def test_status_row_renders_as_two_lines_when_images_are_off(monkeypatch) -> None:
    monkeypatch.setenv("SCOUNDREL_IMAGE_MODE", "off")
    app = ScoundrelApp()
    app.state = GameState(
        room=[Card(Suit.CLUBS, 9), Card(Suit.DIAMONDS, 5), Card(Suit.HEARTS, 6), Card(Suit.SPADES, 4)],
        health=20,
    )
    console = Console(width=140, record=True)

    console.print(app.render_status())
    lines = [line for line in console.export_text().splitlines() if line.strip()]

    assert len(lines) == 2
    assert "Health" in lines[0]
    assert "Equipped weapon" in lines[0]
    assert "Weapon condition" in lines[0]
    assert "Remaining cards" in lines[0]
    assert "20/20" in lines[1]


def test_equipped_weapon_status_uses_bare_hands_icon_by_default() -> None:
    app = ScoundrelApp()

    assert app.equipped_weapon_image() == BARE_HANDS_IMAGE


def test_equipped_weapon_status_uses_current_weapon_icon() -> None:
    app = ScoundrelApp()
    app.state = GameState(weapon=Card(Suit.DIAMONDS, 5))

    assert app.equipped_weapon_image() == WEAPON_IMAGES[5]


def test_equipped_weapon_status_ignores_pixel_art_mode() -> None:
    app = ScoundrelApp()
    app.pixel_art = True
    app.state = GameState(weapon=Card(Suit.DIAMONDS, 5))

    assert app.equipped_weapon_image() == WEAPON_IMAGES[5]
    assert app.equipped_weapon_image() != PIXEL_WEAPON_IMAGES[5]


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


def test_selected_card_panel_uses_quiet_selection_marker(monkeypatch) -> None:
    monkeypatch.setenv("SCOUNDREL_IMAGE_MODE", "off")
    app = ScoundrelApp()
    app._size = Size(220, 60)
    app.state = GameState(
        room=[Card(Suit.CLUBS, 9), Card(Suit.DIAMONDS, 5), None, None],
        selected_slot=1,
    )
    console = Console(width=80, record=True)

    console.print(app.card_cell(1, app.state.room[1]))
    rendered = console.export_text()

    assert "SELECTED" not in rendered
    assert "◆" in rendered
    assert "│ ┌" in rendered
    assert "┐ │" in rendered


def test_card_kind_appears_on_same_line_as_rank(monkeypatch) -> None:
    monkeypatch.setenv("SCOUNDREL_IMAGE_MODE", "off")
    app = ScoundrelApp()
    app._size = Size(220, 60)
    app.state = GameState(room=[Card(Suit.DIAMONDS, 2), None, None, None])
    console = Console(width=80, record=True)

    console.print(app.card_panel(0, app.state.room[0]))

    assert "2♦  WEAPON" in console.export_text()


def test_selected_and_unselected_card_cells_keep_same_height(monkeypatch) -> None:
    monkeypatch.setenv("SCOUNDREL_IMAGE_MODE", "off")
    app = ScoundrelApp()
    app._size = Size(220, 60)
    app.state = GameState(
        room=[Card(Suit.CLUBS, 9), Card(Suit.DIAMONDS, 5), None, None],
        selected_slot=1,
    )
    console = Console(width=80, record=True)

    selected = console.render_lines(app.card_cell(1, app.state.room[1]), console.options.update(width=80))
    unselected = console.render_lines(app.card_cell(0, app.state.room[0]), console.options.update(width=80))

    assert len(selected) == len(unselected)


def test_monster_border_style_tracks_default_health_damage() -> None:
    app = ScoundrelApp()
    app.state = GameState(
        room=[Card(Suit.CLUBS, 2), None, None, None],
        weapon=Card(Suit.DIAMONDS, 5),
        health=10,
    )

    assert app.monster_damage_style(Card(Suit.CLUBS, 2)) == "#71d083"
    app.state.weapon = None
    assert app.monster_damage_style(Card(Suit.CLUBS, 2)) == "#b8a06d"
    assert app.monster_damage_style(Card(Suit.CLUBS, 3)) == "#d9a15c"
    assert app.monster_damage_style(Card(Suit.CLUBS, 6)) == "#ff7a1a"
    assert app.monster_damage_style(Card(Suit.CLUBS, 10)) == "bold #ff3b30"


def test_selected_lethal_card_frame_shows_quiet_warning(monkeypatch) -> None:
    monkeypatch.setenv("SCOUNDREL_IMAGE_MODE", "off")
    app = ScoundrelApp()
    app._size = Size(220, 60)
    app.state = GameState(
        room=[Card(Suit.CLUBS, 10), None, None, None],
        health=10,
    )
    console = Console(width=80, record=True)

    console.print(app.card_cell(0, app.state.room[0]))

    assert "lethal" in console.export_text()


def test_quit_requires_confirmation() -> None:
    app = ScoundrelApp()
    app.refresh_board = lambda: None

    app.action_quit()

    assert app.state.confirm_quit
    console = Console(width=100, record=True)
    console.print(app.render_prompt())
    assert "Press Q again to confirm" in console.export_text()


def test_quit_exits_immediately_after_death() -> None:
    app = ScoundrelApp()
    exited = False

    def exit_once() -> None:
        nonlocal exited
        exited = True

    app.exit = exit_once
    app.state = GameState(game_over=True, won=False)

    app.action_quit()

    assert exited
    assert not app.state.confirm_quit


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
