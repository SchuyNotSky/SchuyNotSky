"""Removal and interaction card effects."""
from __future__ import annotations
from ..engine.card import CardType
from ..engine.effects import bounce_to_hand, destroy_permanent, exile_card
from ..engine.mana import ManaCost, Color


def register_removal_effects(reg: dict):

    # --- Swords to Plowshares ---
    def swords(card, game, player, x=0, targets=None):
        target = _get_creature_target(targets, game, player)
        if not target:
            return
        power = target.power or 0
        ctrl = game.get_player(target.controller_id)
        exile_card(target, game)
        if ctrl:
            ctrl.gain_life(power)
        game.log(f"{player.name} exiles {target.name} with Swords to Plowshares ({ctrl.name if ctrl else '?'} gains {power} life).")
    reg["swords to plowshares"] = {"cast_effect": swords}

    # --- Path to Exile ---
    def path(card, game, player, x=0, targets=None):
        target = _get_creature_target(targets, game, player)
        if not target:
            return
        ctrl = game.get_player(target.controller_id)
        exile_card(target, game)
        if ctrl:
            # Opponent may search for a basic land
            basics = [c for c in ctrl.library.cards()
                      if CardType.LAND in c.data.card_types
                      and any(s in ["Plains","Island","Swamp","Mountain","Forest"]
                              for s in c.data.subtypes)]
            if basics:
                basic = basics[0]
                ctrl.library.remove(basic)
                game.move_to_battlefield(basic, ctrl.player_id)
                ctrl.library.shuffle()
                game.log(f"{ctrl.name} fetches a basic land from Path to Exile.")
        game.log(f"{player.name} exiles {target.name} with Path to Exile.")
    reg["path to exile"] = {"cast_effect": path}

    # --- Chain of Vapor ---
    def chain_of_vapor(card, game, player, x=0, targets=None):
        target = _get_nonland_target(targets, game, player)
        if not target:
            return
        bounce_to_hand(target, game)
        game.log(f"{player.name} bounces {target.name} with Chain of Vapor.")
        # Optional: sacrifice a land to copy
        # AI: skip the copy (too expensive in resources)
    reg["chain of vapor"] = {"cast_effect": chain_of_vapor}

    # --- Cyclonic Rift ---
    def cyclonic_rift(card, game, player, x=0, targets=None):
        overloaded = x == -1 or (targets and targets[0] == "overload")
        if overloaded:
            # Return all non-land permanents opponents control
            to_bounce = [
                c for c in game.battlefield.cards()
                if CardType.LAND not in c.data.card_types
                and c.controller_id != player.player_id
            ]
            for c in to_bounce:
                bounce_to_hand(c, game)
            game.log(f"{player.name} overloads Cyclonic Rift: bounces {len(to_bounce)} permanents!")
        else:
            target = _get_nonland_target(targets, game, player)
            if target:
                bounce_to_hand(target, game)
                game.log(f"{player.name} bounces {target.name} with Cyclonic Rift.")
    reg["cyclonic rift"] = {"cast_effect": cyclonic_rift}

    # --- Toxic Deluge ---
    def toxic_deluge(card, game, player, x=0, targets=None):
        minus = x if x > 0 else 3
        player.lose_life(minus)
        game.log(f"{player.name} pays {minus} life for Toxic Deluge (-{minus}/-{minus} to all creatures).")
        for c in list(game.battlefield.cards()):
            if CardType.CREATURE in c.data.card_types:
                c._toughness_mod -= minus
                c._power_mod -= minus
                if (c.toughness or 0) <= 0:
                    game.move_to_graveyard(c)
                    game.log(f"{c.name} dies to Toxic Deluge.")
    reg["toxic deluge"] = {"cast_effect": toxic_deluge}

    # --- Abrupt Decay ---
    def abrupt_decay(card, game, player, x=0, targets=None):
        target = _get_noncreature_target(targets, game, player, max_cmc=3)
        if not target:
            target = _get_creature_target(targets, game, player, max_cmc=3)
        if target:
            destroy_permanent(target, game)
            game.log(f"{player.name} destroys {target.name} with Abrupt Decay.")
    reg["abrupt decay"] = {"cast_effect": abrupt_decay}

    # --- Assassin's Trophy ---
    def assassins_trophy(card, game, player, x=0, targets=None):
        target = _get_any_permanent_target(targets, game, player)
        if not target:
            return
        ctrl = game.get_player(target.controller_id)
        destroy_permanent(target, game)
        if ctrl:
            basics = [c for c in ctrl.library.cards()
                      if CardType.LAND in c.data.card_types
                      and any(s in ["Plains","Island","Swamp","Mountain","Forest"]
                              for s in c.data.subtypes)]
            if basics:
                basic = basics[0]
                ctrl.library.remove(basic)
                game.move_to_battlefield(basic, ctrl.player_id)
                ctrl.library.shuffle()
        game.log(f"{player.name} destroys {target.name} with Assassin's Trophy.")
    reg["assassin's trophy"] = {"cast_effect": assassins_trophy}

    # --- Nature's Claim ---
    def natures_claim(card, game, player, x=0, targets=None):
        target = _get_artifact_enchantment_target(targets, game, player)
        if not target:
            return
        ctrl = game.get_player(target.controller_id)
        destroy_permanent(target, game)
        if ctrl:
            ctrl.gain_life(4)
        game.log(f"{player.name} destroys {target.name} with Nature's Claim.")
    reg["nature's claim"] = {"cast_effect": natures_claim}

    # --- Force of Vigor ---
    def force_of_vigor(card, game, player, x=0, targets=None):
        # Alt cost: exile green card from hand
        green_in_hand = [c for c in player.hand.cards()
                         if Color.GREEN in c.data.colors and c is not card]
        if green_in_hand:
            exile_c = green_in_hand[0]
            player.hand.remove(exile_c)
            game.exile.add(exile_c)
            game.log(f"{player.name} casts Force of Vigor (free), exiling {exile_c.name}.")
        # Destroy up to 2 artifacts/enchantments
        targets_list = targets[:2] if targets else []
        if not targets_list:
            targets_list = _find_two_artifacts_enchantments(game, player)
        for t in targets_list[:2]:
            destroy_permanent(t, game)
            game.log(f"Force of Vigor destroys {t.name}.")
    reg["force of vigor"] = {"cast_effect": force_of_vigor}

    # --- Winds of Abandon ---
    def winds_of_abandon(card, game, player, x=0, targets=None):
        overloaded = targets and targets[0] == "overload"
        if overloaded:
            opps_creatures = [
                c for c in game.battlefield.cards()
                if CardType.CREATURE in c.data.card_types
                and c.controller_id != player.player_id
            ]
            for c in opps_creatures:
                exile_card(c, game)
            for opp in game.opponents_of(player.player_id):
                basics = [c for c in opp.library.cards()
                          if CardType.LAND in c.data.card_types][:len(opps_creatures)]
                for b in basics:
                    opp.library.remove(b)
                    game.move_to_battlefield(b, opp.player_id)
                opp.library.shuffle()
            game.log(f"{player.name} overloads Winds of Abandon.")
        else:
            target = _get_creature_target(targets, game, player)
            if target:
                ctrl = game.get_player(target.controller_id)
                exile_card(target, game)
                if ctrl:
                    basics = [c for c in ctrl.library.cards()
                              if CardType.LAND in c.data.card_types][:1]
                    for b in basics:
                        ctrl.library.remove(b)
                        game.move_to_battlefield(b, ctrl.player_id)
                    ctrl.library.shuffle()
    reg["winds of abandon"] = {"cast_effect": winds_of_abandon}


# ---------------------------------------------------------------------------
# Target-selection helpers
# ---------------------------------------------------------------------------

def _get_creature_target(targets, game, player, max_cmc=None):
    if targets and hasattr(targets[0], 'data'):
        return targets[0]
    # AI: pick highest-threat opponent creature
    for opp in game.opponents_of(player.player_id):
        for c in game.battlefield.creatures_controlled_by(opp.player_id):
            if max_cmc is None or c.data.cmc <= max_cmc:
                return c
    return None

def _get_nonland_target(targets, game, player):
    if targets and hasattr(targets[0], 'data'):
        return targets[0]
    for opp in game.opponents_of(player.player_id):
        for c in game.battlefield.permanents_controlled_by(opp.player_id):
            if CardType.LAND not in c.data.card_types:
                return c
    return None

def _get_noncreature_target(targets, game, player, max_cmc=None):
    if targets and hasattr(targets[0], 'data'):
        t = targets[0]
        if CardType.CREATURE not in t.data.card_types:
            return t
    for opp in game.opponents_of(player.player_id):
        for c in game.battlefield.permanents_controlled_by(opp.player_id):
            if CardType.CREATURE not in c.data.card_types and CardType.LAND not in c.data.card_types:
                if max_cmc is None or c.data.cmc <= max_cmc:
                    return c
    return None

def _get_artifact_enchantment_target(targets, game, player):
    if targets and hasattr(targets[0], 'data'):
        return targets[0]
    for opp in game.opponents_of(player.player_id):
        for c in game.battlefield.permanents_controlled_by(opp.player_id):
            if CardType.ARTIFACT in c.data.card_types or CardType.ENCHANTMENT in c.data.card_types:
                return c
    return None

def _get_any_permanent_target(targets, game, player):
    if targets and hasattr(targets[0], 'data'):
        return targets[0]
    for opp in game.opponents_of(player.player_id):
        perms = game.battlefield.permanents_controlled_by(opp.player_id)
        if perms:
            return perms[0]
    return None

def _find_two_artifacts_enchantments(game, player):
    result = []
    for opp in game.opponents_of(player.player_id):
        for c in game.battlefield.permanents_controlled_by(opp.player_id):
            if CardType.ARTIFACT in c.data.card_types or CardType.ENCHANTMENT in c.data.card_types:
                result.append(c)
                if len(result) >= 2:
                    return result
    return result
