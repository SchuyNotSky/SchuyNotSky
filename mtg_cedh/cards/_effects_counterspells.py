"""Counterspell card effects."""
from __future__ import annotations
from ..engine.mana import ManaCost, Color


def register_counterspell_effects(reg: dict):

    def _counter_top(game, player, log_name):
        top = game.stack.peek()
        if top:
            top.countered = True
            game.log(f"{player.name} counters {top.name} with {log_name}.")
            return True
        game.log(f"{log_name}: nothing on stack to counter.")
        return False

    # --- Counterspell ---
    def counterspell(card, game, player, x=0, targets=None):
        target = targets[0] if targets else game.stack.peek()
        if target and not getattr(target, 'uncounterable', False):
            target.countered = True
            game.log(f"{player.name} counters {target.name} with Counterspell.")
    reg["counterspell"] = {"cast_effect": counterspell}

    # --- Force of Will ---
    def force_of_will(card, game, player, x=0, targets=None):
        target = targets[0] if targets else game.stack.peek()
        if not target:
            return
        # Alt cost: exile a blue card from hand, pay 1 life
        blue_in_hand = [c for c in player.hand.cards()
                        if Color.BLUE in c.data.colors and c is not card]
        if blue_in_hand:
            exile_card = blue_in_hand[0]
            player.hand.remove(exile_card)
            game.exile.add(exile_card)
            player.lose_life(1)
            game.log(f"{player.name} casts Force of Will (alt cost), exiling {exile_card.name}.")
        if not getattr(target, 'uncounterable', False):
            target.countered = True
            game.log(f"{player.name} counters {target.name} with Force of Will.")
    reg["force of will"] = {"cast_effect": force_of_will}

    # --- Force of Negation ---
    def force_of_negation(card, game, player, x=0, targets=None):
        target = targets[0] if targets else game.stack.peek()
        if not target:
            return
        # Can only be cast on opponent's turn (not during your turn) for free
        active = game.active_player()
        is_own_turn = active and active.player_id == player.player_id
        if not is_own_turn:
            blue_in_hand = [c for c in player.hand.cards()
                            if Color.BLUE in c.data.colors and c is not card]
            if blue_in_hand:
                exile_card = blue_in_hand[0]
                player.hand.remove(exile_card)
                game.exile.add(exile_card)
                game.log(f"{player.name} casts Force of Negation (free), exiling {exile_card.name}.")
        if not getattr(target, 'uncounterable', False):
            target.countered = True
            game.log(f"{player.name} counters {target.name} with Force of Negation.")
    reg["force of negation"] = {"cast_effect": force_of_negation}

    # --- Fierce Guardianship ---
    def fierce_guardianship(card, game, player, x=0, targets=None):
        target = targets[0] if targets else game.stack.peek()
        if not target:
            return
        # Free if you control your commander
        from ..engine.card import CardType
        has_commander = any(
            c.data.is_legendary and c.data.is_commander_eligible
            for c in game.battlefield.permanents_controlled_by(player.player_id)
        )
        if has_commander:
            game.log(f"{player.name} casts Fierce Guardianship (free — controls commander).")
        if not getattr(target, 'uncounterable', False):
            target.countered = True
            game.log(f"{player.name} counters {target.name} with Fierce Guardianship.")
    reg["fierce guardianship"] = {"cast_effect": fierce_guardianship}

    # --- Deflecting Swat ---
    def deflecting_swat(card, game, player, x=0, targets=None):
        # Free if you control your commander; redirects a spell or ability
        has_commander = any(
            c.data.is_legendary and c.data.is_commander_eligible
            for c in game.battlefield.permanents_controlled_by(player.player_id)
        )
        if has_commander:
            game.log(f"{player.name} casts Deflecting Swat (free).")
        top = game.stack.peek()
        if top:
            top.countered = True
            game.log(f"{player.name} redirects/counters {top.name} with Deflecting Swat.")
    reg["deflecting swat"] = {"cast_effect": deflecting_swat}

    # --- Pact of Negation ---
    def pact_of_negation(card, game, player, x=0, targets=None):
        target = targets[0] if targets else game.stack.peek()
        if target and not getattr(target, 'uncounterable', False):
            target.countered = True
            game.log(f"{player.name} counters {target.name} with Pact of Negation (pay {'{3}{U}{U}'} next upkeep).")
        # Register upkeep payment
        player._pact_of_negation_pending = True
    def pact_upkeep_check(card, game, player):
        if getattr(player, '_pact_of_negation_pending', False):
            cost = ManaCost(generic=3, pips={Color.BLUE: 2})
            if player.mana_pool.pay(cost):
                player._pact_of_negation_pending = False
                game.log(f"{player.name} pays for Pact of Negation.")
            else:
                player.lost = True
                game.log(f"{player.name} cannot pay for Pact of Negation and loses!")
    reg["pact of negation"] = {
        "cast_effect": pact_of_negation,
        "triggered_abilities": [{"trigger": "upkeep", "effect": pact_upkeep_check}],
    }

    # --- Mental Misstep ---
    def mental_misstep(card, game, player, x=0, targets=None):
        target = targets[0] if targets else game.stack.peek()
        if target and target.source and target.source.data.cmc == 1:
            target.countered = True
            game.log(f"{player.name} Mental Missteps {target.name}.")
        else:
            game.log(f"Mental Misstep: target is not CMC 1.")
    reg["mental misstep"] = {"cast_effect": mental_misstep}

    # --- Flusterstorm ---
    def flusterstorm(card, game, player, x=0, targets=None):
        target = targets[0] if targets else game.stack.peek()
        if target and not getattr(target, 'uncounterable', False):
            target.countered = True
            game.log(f"{player.name} Flusterstorms {target.name}.")
    reg["flusterstorm"] = {"cast_effect": flusterstorm}

    # --- Swan Song ---
    def swan_song(card, game, player, x=0, targets=None):
        target = targets[0] if targets else game.stack.peek()
        if not target:
            return
        from ..engine.card import CardType as CT
        if target.source and CT.CREATURE not in target.source.data.card_types:
            target.countered = True
            game.log(f"{player.name} Swan Songs {target.name}.")
            # Give opponent a 2/2 Bird token
            ctrl = game.get_player(target.controller_id)
            if ctrl:
                from ..engine.effects import create_token
                create_token(ctrl, game, "Bird", 2, 2, [], ["Bird"], {})
    reg["swan song"] = {"cast_effect": swan_song}

    # --- Dovin's Veto ---
    def dovins_veto(card, game, player, x=0, targets=None):
        target = targets[0] if targets else game.stack.peek()
        if not target:
            return
        from ..engine.card import CardType as CT
        if target.source and CT.CREATURE not in target.source.data.card_types:
            target.countered = True
            game.log(f"{player.name} Dovin's Vetos {target.name} (uncounterable).")
    reg["dovin's veto"] = {"cast_effect": dovins_veto}

    # --- Mana Drain ---
    def mana_drain(card, game, player, x=0, targets=None):
        target = targets[0] if targets else game.stack.peek()
        if not target:
            return
        cmc = target.source.data.cmc if target.source else 0
        if not getattr(target, 'uncounterable', False):
            target.countered = True
            game.log(f"{player.name} Mana Drains {target.name}.")
            # Add colorless equal to CMC next turn (simplified: add now)
            player.mana_pool.add(Color.COLORLESS, cmc)
            game.log(f"{player.name} adds {cmc} colorless mana from Mana Drain.")
    reg["mana drain"] = {"cast_effect": mana_drain}

    # --- Spell Pierce ---
    def spell_pierce(card, game, player, x=0, targets=None):
        target = targets[0] if targets else game.stack.peek()
        if not target:
            return
        from ..engine.card import CardType as CT
        if target.source and CT.CREATURE not in target.source.data.card_types:
            # Counter unless controller pays 2
            ctrl = game.get_player(target.controller_id)
            cost = ManaCost(generic=2)
            if ctrl and not ctrl.mana_pool.can_pay(cost):
                target.countered = True
                game.log(f"{player.name} Spell Pierces {target.name} (opponent can't pay {{2}}).")
            else:
                game.log(f"Spell Pierce: {target.controller_id} pays {{2}}.")
    reg["spell pierce"] = {"cast_effect": spell_pierce}

    # --- Arcane Denial ---
    def arcane_denial(card, game, player, x=0, targets=None):
        target = targets[0] if targets else game.stack.peek()
        if target and not getattr(target, 'uncounterable', False):
            target.countered = True
            game.log(f"{player.name} Arcane Denials {target.name}.")
            # Controller draws 2 at start of next turn (simplified: draw now)
            ctrl = game.get_player(target.controller_id)
            if ctrl:
                from ..engine.effects import draw_cards
                draw_cards(ctrl, 2, game)
            # Caster draws 1
            from ..engine.effects import draw_cards
            draw_cards(player, 1, game)
    reg["arcane denial"] = {"cast_effect": arcane_denial}
