"""Win condition card effects."""
from __future__ import annotations
from ..engine.effects import (
    thassas_oracle_etb, consult_effect, dramatic_reversal_effect
)


def register_wincon_effects(reg: dict):

    # --- Thassa's Oracle ---
    reg["thassa's oracle"] = {"etb_effect": thassas_oracle_etb}

    # --- Demonic Consultation ---
    def demonic_consultation(card, game, player, x=0, targets=None):
        name = targets[0] if targets else _ai_consult_target(player, game)
        consult_effect(player, game, name)
    reg["demonic consultation"] = {"cast_effect": demonic_consultation}

    # --- Tainted Pact ---
    def tainted_pact(card, game, player, x=0, targets=None):
        """
        Exile cards one at a time. If you name a card, stop when you hit it.
        Stops on the first duplicate name (standard Tainted Pact rule).
        In Oracle combo context: name a card not in deck to exile whole library.
        """
        name = targets[0] if targets else _ai_consult_target(player, game)
        seen_names = set()
        found = None
        cards_to_exile = []

        for lib_card in player.library.cards():
            player.library.remove(lib_card)
            if lib_card.name.lower() == name.lower():
                found = lib_card
                player.hand.add(lib_card)
                game.log(f"Tainted Pact finds {lib_card.name}.")
                break
            if lib_card.name in seen_names:
                # Hit a duplicate — stop, keep this card
                player.hand.add(lib_card)
                game.log(f"Tainted Pact stops at second copy of {lib_card.name}.")
                break
            seen_names.add(lib_card.name)
            game.exile.add(lib_card)
            cards_to_exile.append(lib_card.name)

        game.log(f"Tainted Pact exiled {len(cards_to_exile)} cards.")
        if not found:
            # Exile rest of library (Oracle combo line)
            remaining = player.library.exile_all()
            for c in remaining:
                game.exile.add(c)
            game.log(f"Tainted Pact: library fully exiled ({len(remaining)} more cards).")
    reg["tainted pact"] = {"cast_effect": tainted_pact}

    # --- Isochron Scepter ---
    def isochron_etb(card, game, player):
        # Imprint: exile an instant with CMC <= 2 from hand
        eligible = [c for c in player.hand.cards()
                    if _is_instant(c) and c.data.cmc <= 2]
        if eligible:
            if player.is_human:
                game.log(f"[IMPRINT] Choose a card to imprint (eligible: {[c.name for c in eligible]})")
                imprinted = eligible[0]  # CLI will handle actual choice in full version
            else:
                # AI: prefer Dramatic Reversal, then best instant
                imprinted = _ai_scepter_imprint(eligible, player, game)
            player.hand.remove(imprinted)
            game.exile.add(imprinted)
            card.counters["imprinted_name"] = imprinted.name
            game.log(f"{player.name} imprints {imprinted.name} under Isochron Scepter.")
        else:
            game.log(f"{player.name} has no eligible card to imprint (Isochron Scepter).")

    def isochron_activate(card, game, player, x=0, targets=None):
        imprinted_name = card.counters.get("imprinted_name")
        if not imprinted_name:
            game.log("Isochron Scepter: nothing imprinted.")
            return
        # Find the imprinted card data and copy its effect
        from ..cards.loader import get_card_data
        imprinted_data = get_card_data(imprinted_name)
        if imprinted_data and imprinted_data.cast_effect:
            game.log(f"{player.name} copies {imprinted_name} from Isochron Scepter.")
            imprinted_data.cast_effect(card, game, player, x_value=x, targets=targets)
        else:
            game.log(f"Isochron Scepter copies {imprinted_name} (no effect defined).")

    reg["isochron scepter"] = {
        "etb_effect": isochron_etb,
        "activated_abilities": [
            {"name": "Isochron Scepter copy",
             "cost": {"tap": True, "mana": __import__('mtg_cedh.engine.mana', fromlist=['ManaCost']).ManaCost(generic=2)},
             "effect": isochron_activate},
        ],
    }

    # --- Dramatic Reversal ---
    def dramatic_reversal(card, game, player, x=0, targets=None):
        dramatic_reversal_effect(game, player.player_id)
    reg["dramatic reversal"] = {"cast_effect": dramatic_reversal}

    # --- Underworld Breach ---
    def breach_etb(card, game, player):
        game.log(f"{player.name} controls Underworld Breach: escape costs enabled.")
        # Mark: cards in GY can be escaped (cast from GY for CMC+exile 3 from GY)
        card.counters["breach_active"] = 1

    def breach_end_step(card, game, player):
        if card.controller_id == player.player_id:
            game.move_to_graveyard(card)
            game.log("Underworld Breach exiles itself at end of turn.")

    reg["underworld breach"] = {
        "etb_effect": breach_etb,
        "triggered_abilities": [{"trigger": "end_step", "effect": breach_end_step}],
    }

    # --- Brain Freeze ---
    def brain_freeze(card, game, player, x=0, targets=None):
        target_player = targets[0] if targets else None
        if not target_player:
            opps = game.opponents_of(player.player_id)
            target_player = opps[0] if opps else None
        if not target_player:
            return
        storm_count = getattr(game, '_spells_this_turn', 1)
        mill_amount = 3 * storm_count
        milled = target_player.library.mill(mill_amount)
        for c in milled:
            target_player.graveyard.add(c)
        game.log(f"Brain Freeze (storm={storm_count}): {target_player.name} mills {mill_amount} cards.")
        if len(target_player.library) == 0:
            target_player.lost = True
            game.log(f"{target_player.name} has no cards left in library and loses!")
    reg["brain freeze"] = {"cast_effect": brain_freeze}

    # --- Flash ---
    def flash_effect(card, game, player, x=0, targets=None):
        # Put a creature from hand onto battlefield (without paying mana cost)
        # In cEDH: Flash + Protean Hulk = search for creatures totalling 6 power
        creature_name = targets[0] if targets else _ai_flash_target(player, game)
        if not creature_name:
            return
        creature = player.hand.find_by_name(creature_name) if hasattr(player.hand, 'find_by_name') else None
        if not creature:
            creature = player.hand.find_by_name(creature_name)
        if creature and _is_creature(creature):
            player.hand.remove(creature)
            game.log(f"{player.name} uses Flash to put {creature.name} onto battlefield.")
            game.move_to_battlefield(creature, player.player_id)
        else:
            game.log(f"Flash: {creature_name} not in hand or not a creature.")
    reg["flash"] = {"cast_effect": flash_effect}

    # --- Protean Hulk ---
    def hulk_death(card, game, player):
        """When Protean Hulk dies: search for creatures totalling power <= 6."""
        game.log(f"Protean Hulk dies! {player.name} searches for creatures with total power <= 6.")
        found = _ai_hulk_pile(player, game)
        for name in found:
            c = player.library.find_by_name(name)
            if c:
                player.library.remove(c)
                game.log(f"Hulk finds {name}.")
                game.move_to_battlefield(c, player.player_id)
        player.library.shuffle()
    reg["protean hulk"] = {"ltb_effect": hulk_death}

    # --- Najeela, the Blade-Blossom (combat trigger) ---
    def najeela_attack_trigger(card, game, player, x=0, targets=None):
        """Whenever a Warrior attacks, create a 1/1 white Warrior token."""
        from ..engine.effects import create_token
        from ..engine.card import Keyword as KW
        create_token(player, game, "Warrior", 1, 1, [], ["Warrior"],
                     {KW.VIGILANCE, KW.HASTE})

    def najeela_activate(card, game, player, x=0, targets=None):
        """WUBRG: untap all attacking creatures, after combat take extra combat."""
        if not game.najeela_activated_this_combat:
            game.najeela_activated_this_combat = True
            from ..engine.card import CardType as CT
            for c in game.battlefield.creatures_controlled_by(player.player_id):
                if any(a.attacker is c for a in game.combat.attackers):
                    c.untap()
            game.log(f"{player.name} activates Najeela: extra combat phase!")
            game._extra_combat = True

    reg["najeela, the blade-blossom"] = {
        "activated_abilities": [
            {"name": "Najeela extra combat",
             "cost": {"mana": _wubrg_cost()},
             "effect": najeela_activate},
        ],
    }

    # --- Kenrith, the Returned King ---
    def kenrith_haste(card, game, player, x=0, targets=None):
        target = targets[0] if targets else None
        if target:
            from ..engine.card import Keyword as KW
            target._added_keywords.add(KW.HASTE)
            game.log(f"{player.name} gives {target.name} haste (Kenrith).")
    def kenrith_draw(card, game, player, x=0, targets=None):
        target = targets[0] if targets else player
        if hasattr(target, 'draw'):
            from ..engine.effects import draw_cards
            target.gain_life(2)
            draw_cards(target, 1, game)
    def kenrith_reanimate(card, game, player, x=0, targets=None):
        target = targets[0] if targets else None
        if not target:
            return
        if hasattr(target, 'graveyard'):
            gy = target
            creatures = gy.cards_of_type(_ct())
            if creatures:
                c = creatures[0]
                gy.remove(c)
                game.move_to_battlefield(c, player.player_id)
    reg["kenrith, the returned king"] = {
        "activated_abilities": [
            {"name": "Kenrith haste",
             "cost": {"mana": __import__('mtg_cedh.engine.mana', fromlist=['ManaCost']).ManaCost(pips={__import__('mtg_cedh.engine.mana', fromlist=['Color']).Color.RED: 1})},
             "effect": kenrith_haste},
            {"name": "Kenrith draw",
             "cost": {"mana": __import__('mtg_cedh.engine.mana', fromlist=['ManaCost']).ManaCost(generic=3, pips={__import__('mtg_cedh.engine.mana', fromlist=['Color']).Color.GREEN: 1, __import__('mtg_cedh.engine.mana', fromlist=['Color']).Color.BLUE: 1})},
             "effect": kenrith_draw},
        ],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ai_consult_target(player, game) -> str:
    """AI chooses what to name for Consultation/Tainted Pact."""
    # If Oracle is in hand, consult for something not in deck to exile library
    oracle_in_hand = player.hand.find_by_name("Thassa's Oracle")
    if oracle_in_hand:
        return "__exile_all__"  # triggers full exile in consult_effect
    # Otherwise tutor for Oracle
    return "Thassa's Oracle"

def _is_instant(card) -> bool:
    from ..engine.card import CardType
    return CardType.INSTANT in card.data.card_types

def _is_creature(card) -> bool:
    from ..engine.card import CardType
    return CardType.CREATURE in card.data.card_types

def _ai_scepter_imprint(eligible, player, game):
    """AI picks best card to imprint under Isochron Scepter."""
    priority = ["dramatic reversal", "brainstorm", "counterspell",
                "mental misstep", "swan song", "brainstorm"]
    for name in priority:
        for c in eligible:
            if c.name.lower() == name:
                return c
    return eligible[0]

def _ai_flash_target(player, game) -> str:
    priority = ["Protean Hulk", "Thassa's Oracle", "Grand Abolisher"]
    for name in priority:
        c = player.hand.find_by_name(name)
        if c:
            return name
    return ""

def _ai_hulk_pile(player, game):
    """Return the creature names to search for with Hulk trigger."""
    # Classic Hulk piles:
    # Karmic Guide (2/2) + Reveillark (3/4) = 5 total or other combos
    # For simulation: just grab the win con creatures
    options = [
        ["Thassa's Oracle"],
        ["Karmic Guide", "Viscera Seer"],
    ]
    for pile in options:
        if all(player.library.find_by_name(n) for n in pile):
            return pile
    return []

def _wubrg_cost():
    from ..engine.mana import ManaCost, Color
    return ManaCost(pips={
        Color.WHITE: 1, Color.BLUE: 1, Color.BLACK: 1,
        Color.RED: 1, Color.GREEN: 1
    })

def _ct():
    from ..engine.card import CardType
    return CardType.CREATURE
