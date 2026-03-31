"""Protection, hate pieces, and stax card effects."""
from __future__ import annotations
from ..engine.mana import Color


def register_protection_effects(reg: dict):

    # --- Silence ---
    def silence_effect(card, game, player, x=0, targets=None):
        target = targets[0] if targets else None
        if not target:
            opps = game.opponents_of(player.player_id)
            target = opps[0] if opps else None
        if target:
            target._silenced_until_eot = True
            game.log(f"{player.name} casts Silence: {target.name} cannot cast spells this turn.")
    reg["silence"] = {"cast_effect": silence_effect}

    # --- Orim's Chant ---
    def orims_chant(card, game, player, x=0, targets=None):
        target = targets[0] if targets else None
        if not target:
            opps = game.opponents_of(player.player_id)
            target = opps[0] if opps else None
        if target:
            target._silenced_until_eot = True
        game.log(f"{player.name} casts Orim's Chant.")
    reg["orim's chant"] = {"cast_effect": orims_chant}

    # --- Veil of Summer ---
    def veil_of_summer(card, game, player, x=0, targets=None):
        player._veiled_this_turn = True
        game.log(f"{player.name} casts Veil of Summer: spells can't be countered by blue/black this turn.")
        from ..engine.effects import draw_cards
        draw_cards(player, 1, game)
    reg["veil of summer"] = {"cast_effect": veil_of_summer}

    # --- Autumn's Veil ---
    def autumns_veil(card, game, player, x=0, targets=None):
        player._veiled_this_turn = True
        game.log(f"{player.name} casts Autumn's Veil.")
    reg["autumn's veil"] = {"cast_effect": autumns_veil}

    # --- Grand Abolisher ---
    def abolisher_etb(card, game, player):
        game.log(f"{player.name} controls Grand Abolisher: opponents can't cast spells during your turn.")
    reg["grand abolisher"] = {"etb_effect": abolisher_etb}

    # --- Drannith Magistrate ---
    def magistrate_etb(card, game, player):
        game.log(f"{player.name} controls Drannith Magistrate: opponents can't cast from anywhere except hand.")
    reg["drannith magistrate"] = {"etb_effect": magistrate_etb}

    # --- Collector Ouphe ---
    def ouphe_etb(card, game, player):
        game.log(f"{player.name} controls Collector Ouphe: activated abilities of artifacts don't work.")
    reg["collector ouphe"] = {"etb_effect": ouphe_etb}

    # --- Null Rod ---
    def null_rod_etb(card, game, player):
        game.log(f"{player.name} controls Null Rod: activated abilities of artifacts don't work.")
    reg["null rod"] = {"etb_effect": null_rod_etb}

    # --- Cursed Totem ---
    def cursed_totem_etb(card, game, player):
        game.log(f"{player.name} controls Cursed Totem: creatures can't activate abilities.")
    reg["cursed totem"] = {"etb_effect": cursed_totem_etb}

    # --- Thalia, Guardian of Thraben ---
    def thalia_etb(card, game, player):
        game.log(f"{player.name} controls Thalia: noncreature spells cost {{1}} more.")
    reg["thalia, guardian of thraben"] = {"etb_effect": thalia_etb}

    # --- Tymna the Weaver (commander draw ability) ---
    def tymna_end_step(card, game, player):
        if card.controller_id != player.player_id:
            return
        # Count opponents dealt combat damage this turn
        damaged = getattr(player, '_damaged_opponents_this_turn', 0)
        if damaged > 0:
            player.lose_life(damaged)
            from ..engine.effects import draw_cards
            draw_cards(player, damaged, game)
            game.log(f"Tymna: {player.name} pays {damaged} life to draw {damaged} card(s).")
            player._damaged_opponents_this_turn = 0
    reg["tymna the weaver"] = {
        "triggered_abilities": [{"trigger": "end_step", "effect": tymna_end_step}],
    }

    # --- Thrasios, Triton Hero (activated card draw) ---
    def thrasios_activate(card, game, player, x=0, targets=None):
        from ..engine.effects import draw_cards
        top = player.library.peek_top(1)
        if top:
            top_card = top[0]
            from ..engine.card import CardType
            if CardType.LAND in top_card.data.card_types:
                player.library.remove(top_card)
                game.move_to_battlefield(top_card, player.player_id)
                game.log(f"Thrasios: {player.name} puts {top_card.name} onto battlefield.")
            else:
                player.library.remove(top_card)
                player.hand.add(top_card)
                game.log(f"Thrasios: {player.name} draws {top_card.name}.")
    reg["thrasios, triton hero"] = {
        "activated_abilities": [
            {"name": "Thrasios scry/draw",
             "cost": {"tap": True, "mana": __import__(
                 'mtg_cedh.engine.mana', fromlist=['ManaCost']
             ).ManaCost(pips={
                 __import__('mtg_cedh.engine.mana', fromlist=['Color']).Color.BLUE: 1,
                 __import__('mtg_cedh.engine.mana', fromlist=['Color']).Color.GREEN: 1,
             })},
             "effect": thrasios_activate},
        ],
    }

    # --- Kraum, Ludevic's Opus ---
    def kraum_trigger(card, game, player):
        """Draw when an opponent casts their second spell in a turn."""
        pass  # tracked in game.py via _spells_cast_by_opponents
    reg["kraum, ludevic's opus"] = {}
