"""
Effect resolution: ETB triggers, static effects, replacement effects, state-based actions.
All card effects are implemented as functions here that get registered in the card database.
"""
from __future__ import annotations
from typing import Callable, List, Optional, TYPE_CHECKING

from .card import CardType, Keyword
from .mana import Color

if TYPE_CHECKING:
    from .game import GameState
    from .card import Card
    from .player import Player


# ---------------------------------------------------------------------------
# State-Based Actions (SBAs) — checked continuously
# ---------------------------------------------------------------------------

def check_state_based_actions(game: "GameState") -> bool:
    """
    Check and apply all state-based actions. Returns True if any action was taken.
    Called after every game event and before any player gets priority.
    """
    changed = False

    # 1. Player with 0 or less life loses
    for player in game.players:
        if player.is_dead() and not player.lost:
            player.lost = True
            game.log(f"{player.name} has lost the game!")
            changed = True

    # 2. Creatures with damage >= toughness die
    to_die = []
    for card in game.battlefield.cards():
        if CardType.CREATURE not in card.data.card_types:
            continue
        if card.toughness is None:
            continue
        if card.has_keyword(Keyword.INDESTRUCTIBLE):
            continue
        if card.damage_taken >= card.toughness and card.toughness > 0:
            to_die.append(card)

    for card in to_die:
        game.move_to_graveyard(card)
        game.log(f"{card.name} dies from damage.")
        changed = True

    # 3. Creatures with toughness <= 0 die
    for card in game.battlefield.cards():
        if CardType.CREATURE not in card.data.card_types:
            continue
        if card.toughness is not None and card.toughness <= 0:
            if card not in to_die:
                game.move_to_graveyard(card)
                game.log(f"{card.name} dies (0 toughness).")
                changed = True

    # 4. Planeswalkers with 0 or less loyalty die
    for card in game.battlefield.cards():
        if CardType.PLANESWALKER not in card.data.card_types:
            continue
        if card.loyalty is not None and card.loyalty <= 0:
            game.move_to_graveyard(card)
            game.log(f"{card.name} leaves the battlefield (0 loyalty).")
            changed = True

    # 5. Legend rule: if two legendaries with the same name, controller chooses one to keep
    legend_map = {}
    for card in game.battlefield.cards():
        if not card.data.is_legendary:
            continue
        key = (card.controller_id, card.name)
        if key in legend_map:
            # Keep the one already there (or newer — for simplicity keep first)
            game.move_to_graveyard(card)
            game.log(f"Legend rule: {card.name} put into graveyard.")
            changed = True
        else:
            legend_map[key] = card

    # 6. Auras fall off if their enchanted permanent is gone
    for card in game.battlefield.cards():
        if CardType.ENCHANTMENT not in card.data.card_types:
            continue
        if not card.data.has_subtype("Aura"):
            continue
        if card.attached_to is None or card.attached_to not in game.battlefield.cards():
            owner = game.get_player(card.owner_id)
            if owner:
                game.move_to_graveyard(card)
            changed = True

    # 7. Equipment falls off destroyed creatures (equipment stays on BF, loses attachment)
    for card in game.battlefield.cards():
        if CardType.ARTIFACT not in card.data.card_types:
            continue
        if not card.data.has_subtype("Equipment"):
            continue
        if card.attached_to is not None and card.attached_to not in game.battlefield.cards():
            card.attached_to = None

    return changed


def apply_all_sbas(game: "GameState"):
    """Apply SBAs repeatedly until stable."""
    while check_state_based_actions(game):
        pass


# ---------------------------------------------------------------------------
# End-of-phase cleanup
# ---------------------------------------------------------------------------

def end_of_phase_cleanup(game: "GameState"):
    """Clear damage from creatures, empty mana pools, etc."""
    for card in game.battlefield.cards():
        card.damage_taken = 0  # damage wears off end of combat
    for player in game.players:
        player.mana_pool.empty()


def end_of_turn_cleanup(game: "GameState"):
    """End of turn: discard to hand size, remove 'until end of turn' effects."""
    active = game.active_player()
    if active:
        excess = active.hand.discard_to_size(active.must_discard_to)
        for c in excess:
            active.hand.remove(c)
            active.graveyard.add(c)
            game.log(f"{active.name} discards {c.name} (hand size).")


# ---------------------------------------------------------------------------
# Common effect helpers used by card implementations
# ---------------------------------------------------------------------------

def draw_cards(player: "Player", count: int, game: "GameState"):
    drawn = player.draw(count)
    if drawn:
        game.log(f"{player.name} draws {len(drawn)} card(s).")
    if player.lost:
        game.log(f"{player.name} tried to draw from an empty library and lost!")


def tutor_to_hand(player: "Player", card_name: str, game: "GameState") -> bool:
    """Search library for named card, put in hand, shuffle."""
    card = player.library.find_by_name(card_name)
    if card:
        player.library.remove(card)
        player.hand.add(card)
        player.library.shuffle()
        game.log(f"{player.name} tutors {card_name} to hand.")
        return True
    game.log(f"{player.name} tutors but {card_name} not found in library.")
    return False


def tutor_to_top(player: "Player", card_name: str, game: "GameState") -> bool:
    """Search library for named card, put on top, no shuffle."""
    card = player.library.find_by_name(card_name)
    if card:
        player.library.remove(card)
        player.library.add(card, "top")
        game.log(f"{player.name} tutors {card_name} to top of library.")
        return True
    return False


def create_token(
    player: "Player",
    game: "GameState",
    name: str,
    power: int,
    toughness: int,
    colors: list,
    subtypes: list,
    keywords: set = None,
) -> "Card":
    """Create a creature token and put it onto the battlefield."""
    from .card import Card, CardData, CardType, ManaCost
    from .mana import ManaCost as MC, Color
    data = CardData(
        name=name,
        mana_cost=MC.free(),
        card_types=[CardType.CREATURE],
        subtypes=subtypes,
        keywords=keywords or set(),
        power=power,
        toughness=toughness,
    )
    token = Card(data, player.player_id)
    token.controller_id = player.player_id
    game.battlefield.add(token)
    token.summoning_sick = True
    game.log(f"{player.name} creates a {power}/{toughness} {name} token.")
    return token


def counter_spell(game: "GameState", stack_item):
    """Counter a spell or ability on the stack."""
    if stack_item and not stack_item.countered:
        stack_item.countered = True
        game.log(f"{stack_item.name} is countered.")


def exile_card(card: "Card", game: "GameState", source_player_id: Optional[str] = None):
    """Move a card to exile from any zone."""
    zone = card.zone
    player = game.get_player(card.owner_id)
    if zone.value == "battlefield":
        game.battlefield.remove(card)
    elif player:
        if zone.value == "hand":
            player.hand.remove(card)
        elif zone.value == "graveyard":
            player.graveyard.remove(card)
        elif zone.value == "library":
            player.library.remove(card)
    # Put in shared exile or owner's exile
    game.exile.add(card)
    game.log(f"{card.name} is exiled.")


def bounce_to_hand(card: "Card", game: "GameState"):
    """Return a permanent from the battlefield to its owner's hand."""
    owner = game.get_player(card.owner_id)
    if owner:
        game.battlefield.remove(card)
        owner.hand.add(card)
        game.log(f"{card.name} is returned to {owner.name}'s hand.")


def destroy_permanent(card: "Card", game: "GameState"):
    """Destroy a permanent (respects indestructible)."""
    if card.has_keyword(Keyword.INDESTRUCTIBLE):
        game.log(f"{card.name} is indestructible and cannot be destroyed.")
        return False
    game.move_to_graveyard(card)
    return True


def add_mana_to_pool(player: "Player", color: Color, amount: int):
    player.mana_pool.add(color, amount)


def wheel_effect(game: "GameState", controller_id: str):
    """Each player discards hand and draws 7 (Wheel of Fortune / Windfall style)."""
    for player in game.players:
        discarded = player.discard_hand()
        game.log(f"{player.name} discards {len(discarded)} card(s) (wheel).")
    for player in game.players:
        draw_cards(player, 7, game)


def ad_nauseam_effect(player: "Player", game: "GameState"):
    """
    Reveal cards from top of library one at a time; put them in hand.
    Pay life equal to CMC. Stop when player chooses or would die.
    AI: stop when life would be unsafe for cEDH kill window.
    """
    revealed = []
    while True:
        if len(player.library) == 0:
            break
        card = player.library.peek_top(1)[0] if player.library.peek_top(1) else None
        if card is None:
            break
        cost = card.data.cmc
        if player.life - cost <= 1:  # AI stops at 1 life to maintain combo safety
            break
        player.library.draw()
        player.hand.add(card)
        player.lose_life(cost)
        revealed.append(card.name)
        game.log(f"{player.name} pays {cost} life for {card.name} (Ad Nauseam).")
    game.log(f"{player.name} gained {len(revealed)} cards from Ad Nauseam. Life: {player.life}")


def necropotence_draw(player: "Player", game: "GameState", count: int):
    """Necropotence: pay life to exile cards from top of library, at EOT put in hand."""
    # Simplified: immediate draw for simulation purposes
    if player.life - count < 1:
        count = player.life - 1
    if count <= 0:
        return
    player.lose_life(count)
    drawn = player.draw(count)
    game.log(f"{player.name} necro-draws {len(drawn)} for {count} life.")


def dramatic_reversal_effect(game: "GameState", controller_id: str):
    """Untap all nonland permanents you control."""
    player = game.get_player(controller_id)
    if not player:
        return
    untapped = 0
    for card in game.battlefield.permanents_controlled_by(controller_id):
        if CardType.LAND not in card.data.card_types and card.tapped:
            card.untap()
            untapped += 1
    game.log(f"{player.name} untaps {untapped} nonland permanent(s) (Dramatic Reversal).")


def isochron_scepter_imprint(card: "Card", game: "GameState", imprinted: "Card"):
    """Imprint a card under Isochron Scepter."""
    card.counters["imprinted"] = 1
    card.data.oracle_text = f"Imprinted: {imprinted.name}\n{card.data.oracle_text}"
    game.log(f"{imprinted.name} is imprinted under Isochron Scepter.")


def consult_effect(player: "Player", game: "GameState", card_name: str):
    """
    Demonic Consultation / Tainted Pact: name a card (or name next unique),
    exile cards from top until found, exile the rest of library.
    Primarily used with Thassa's Oracle to win.
    """
    library = player.library
    found = False
    exiled = []
    cards_list = library.cards()

    for card in cards_list:
        library.remove(card)
        if card.name.lower() == card_name.lower() and not found:
            # Found it — stop exiling, put it in hand
            player.hand.add(card)
            found = True
            game.log(f"Consultation finds {card_name}.")
            break
        else:
            game.exile.add(card)
            exiled.append(card.name)

    if not found:
        # Exile rest of library
        remaining = library.exile_all()
        for c in remaining:
            game.exile.add(c)
        game.log(f"Consultation did not find {card_name}. Library exiled.")

    game.log(f"{player.name} exiled {len(exiled)} card(s) from library.")


def thassas_oracle_etb(card: "Card", game: "GameState"):
    """
    ETB: look at top X cards (devotion to blue), put them back in any order.
    Win condition: if library is empty or you have higher devotion to blue
    than cards in library, you win.
    """
    player = game.get_player(card.controller_id)
    if not player:
        return

    # Count devotion to blue
    devotion = 0
    for c in game.battlefield.permanents_controlled_by(card.controller_id):
        devotion += c.data.mana_cost.pips.get(Color.BLUE, 0)

    library_count = len(player.library)
    game.log(f"Thassa's Oracle ETB: devotion={devotion}, library size={library_count}")

    if library_count <= devotion:
        player.won = True
        game.winner = player
        game.log(f"*** {player.name} WINS with Thassa's Oracle! ***")
        return

    # Otherwise look at top devotion cards (simplified: no action needed for sim)
    game.log(f"{player.name} looks at top {devotion} card(s) with Thassa's Oracle.")


def hermit_druid_effect(card: "Card", game: "GameState"):
    """
    Tap: reveal top cards until you hit a basic land, put it in hand,
    rest in graveyard. In decks with 0 basics, mills the whole deck.
    """
    player = game.get_player(card.controller_id)
    if not player:
        return
    card.tap()
    milled = []
    found_basic = False
    lib_cards = player.library.cards()
    for lib_card in lib_cards:
        player.library.remove(lib_card)
        if (CardType.LAND in lib_card.data.card_types and
                lib_card.data.has_subtype("Plains") or
                lib_card.data.has_subtype("Island") or
                lib_card.data.has_subtype("Swamp") or
                lib_card.data.has_subtype("Mountain") or
                lib_card.data.has_subtype("Forest")):
            player.hand.add(lib_card)
            found_basic = True
            game.log(f"Hermit Druid found {lib_card.name} (basic land).")
            break
        else:
            player.graveyard.add(lib_card)
            milled.append(lib_card.name)
    if not found_basic:
        game.log(f"Hermit Druid milled entire library ({len(milled)} cards)!")
    else:
        game.log(f"Hermit Druid milled {len(milled)} cards.")
