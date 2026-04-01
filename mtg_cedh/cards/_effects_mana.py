"""Mana-producing card effects: mana rocks, rituals, fast mana."""
from __future__ import annotations
from ..engine.mana import Color, ManaCost


def register_mana_effects(reg: dict):
    # --- Sol Ring ---
    def sol_ring_tap(card, game, player, x=0, targets=None):
        player.mana_pool.add(Color.COLORLESS, 2)
        game.log(f"{player.name} taps Sol Ring for {{2}}.")
    reg["sol ring"] = {
        "tap_mana": None,
        "activated_abilities": [{"name": "Sol Ring mana", "cost": {"tap": True},
                                  "effect": sol_ring_tap}],
    }

    # --- Mana Crypt ---
    def mana_crypt_tap(card, game, player, x=0, targets=None):
        player.mana_pool.add(Color.COLORLESS, 2)
        game.log(f"{player.name} taps Mana Crypt for {{2}}.")
    def mana_crypt_upkeep(card, game, player):
        import random
        if random.random() < 0.5:
            player.take_damage(3)
            game.log(f"Mana Crypt deals 3 damage to {player.name} (coin flip lost).")
    reg["mana crypt"] = {
        "tap_mana": None,
        "activated_abilities": [{"name": "Mana Crypt mana", "cost": {"tap": True},
                                  "effect": mana_crypt_tap}],
        "triggered_abilities": [{"trigger": "upkeep", "effect": mana_crypt_upkeep}],
    }

    # --- Mana Vault ---
    def mana_vault_tap(card, game, player, x=0, targets=None):
        player.mana_pool.add(Color.COLORLESS, 3)
        game.log(f"{player.name} taps Mana Vault for {{3}}.")
    def mana_vault_untap(card, game, player, x=0, targets=None):
        cost = ManaCost(generic=4)
        if player.mana_pool.pay(cost):
            card.untap()
            game.log(f"{player.name} pays {{4}} to untap Mana Vault.")
    def mana_vault_upkeep(card, game, player):
        if card.tapped:
            player.take_damage(1)
            game.log(f"Mana Vault deals 1 damage to {player.name} (still tapped).")
    reg["mana vault"] = {
        "tap_mana": None,
        "activated_abilities": [
            {"name": "Mana Vault mana", "cost": {"tap": True}, "effect": mana_vault_tap},
            {"name": "Mana Vault untap", "cost": {"mana": ManaCost(generic=4)}, "effect": mana_vault_untap},
        ],
        "triggered_abilities": [{"trigger": "upkeep", "effect": mana_vault_upkeep}],
    }

    # --- Grim Monolith ---
    def grim_tap(card, game, player, x=0, targets=None):
        player.mana_pool.add(Color.COLORLESS, 3)
        game.log(f"{player.name} taps Grim Monolith for {{3}}.")
    def grim_untap(card, game, player, x=0, targets=None):
        cost = ManaCost(generic=4)
        if player.mana_pool.pay(cost):
            card.untap()
            game.log(f"{player.name} pays {{4}} to untap Grim Monolith.")
    reg["grim monolith"] = {
        "tap_mana": None,
        "activated_abilities": [
            {"name": "Grim Monolith mana", "cost": {"tap": True}, "effect": grim_tap},
            {"name": "Grim Monolith untap", "cost": {"mana": ManaCost(generic=4)}, "effect": grim_untap},
        ],
    }

    # --- Basalt Monolith ---
    def basalt_tap(card, game, player, x=0, targets=None):
        player.mana_pool.add(Color.COLORLESS, 3)
        game.log(f"{player.name} taps Basalt Monolith for {{3}}.")
    def basalt_untap(card, game, player, x=0, targets=None):
        cost = ManaCost(generic=3)
        if player.mana_pool.pay(cost):
            card.untap()
            game.log(f"{player.name} pays {{3}} to untap Basalt Monolith.")
    reg["basalt monolith"] = {
        "tap_mana": None,
        "activated_abilities": [
            {"name": "Basalt Monolith mana", "cost": {"tap": True}, "effect": basalt_tap},
            {"name": "Basalt Monolith untap", "cost": {"mana": ManaCost(generic=3)}, "effect": basalt_untap},
        ],
    }

    # --- Lotus Petal ---
    def lotus_petal_effect(card, game, player, x=0, targets=None):
        color = targets[0] if targets else Color.COLORLESS
        player.mana_pool.add(color, 1)
        game.move_to_graveyard(card)
        game.log(f"{player.name} sacrifices Lotus Petal for 1 mana.")
    reg["lotus petal"] = {
        "cast_effect": None,
        "activated_abilities": [{"name": "Lotus Petal", "cost": {"sacrifice": "self"},
                                  "effect": lotus_petal_effect}],
    }

    # --- Lion's Eye Diamond ---
    def led_effect(card, game, player, x=0, targets=None):
        color = targets[0] if targets else Color.COLORLESS
        player.discard_hand()
        player.mana_pool.add(color, 3)
        game.move_to_graveyard(card)
        game.log(f"{player.name} activates LED: discards hand, adds 3 mana.")
    reg["lion's eye diamond"] = {
        "activated_abilities": [{"name": "Lion's Eye Diamond",
                                  "cost": {"sacrifice": "self"},
                                  "effect": led_effect}],
    }

    # --- Jeweled Lotus ---
    def jeweled_lotus_effect(card, game, player, x=0, targets=None):
        color = targets[0] if targets else Color.COLORLESS
        player.mana_pool.add(color, 3)
        game.move_to_graveyard(card)
        game.log(f"{player.name} sacrifices Jeweled Lotus for 3 commander-color mana.")
    reg["jeweled lotus"] = {
        "activated_abilities": [{"name": "Jeweled Lotus",
                                  "cost": {"sacrifice": "self"},
                                  "effect": jeweled_lotus_effect}],
    }

    # --- Dark Ritual ---
    def dark_ritual_effect(card, game, player, x=0, targets=None):
        player.mana_pool.add(Color.BLACK, 3)
        game.log(f"{player.name} casts Dark Ritual: adds {{B}}{{B}}{{B}}.")
    reg["dark ritual"] = {"cast_effect": dark_ritual_effect}

    # --- Cabal Ritual ---
    def cabal_ritual_effect(card, game, player, x=0, targets=None):
        # Threshold: 7+ cards in GY = 5 black
        gy_count = len(player.graveyard)
        amount = 5 if gy_count >= 7 else 3
        player.mana_pool.add(Color.BLACK, amount)
        game.log(f"{player.name} casts Cabal Ritual: adds {amount} {{B}} (threshold={'yes' if gy_count>=7 else 'no'}).")
    reg["cabal ritual"] = {"cast_effect": cabal_ritual_effect}

    # --- Elvish Spirit Guide ---
    def esg_effect(card, game, player, x=0, targets=None):
        # Exile from hand to add G
        if player.hand.remove(card):
            game.exile.add(card)
            player.mana_pool.add(Color.GREEN, 1)
            game.log(f"{player.name} exiles Elvish Spirit Guide for {{G}}.")
    reg["elvish spirit guide"] = {
        "activated_abilities": [{"name": "Elvish Spirit Guide",
                                  "cost": {},
                                  "effect": esg_effect}],
    }

    # --- Simian Spirit Guide ---
    def ssg_effect(card, game, player, x=0, targets=None):
        if player.hand.remove(card):
            game.exile.add(card)
            player.mana_pool.add(Color.RED, 1)
            game.log(f"{player.name} exiles Simian Spirit Guide for {{R}}.")
    reg["simian spirit guide"] = {
        "activated_abilities": [{"name": "Simian Spirit Guide",
                                  "cost": {},
                                  "effect": ssg_effect}],
    }

    # --- Chrome Mox ---
    def chrome_mox_etb(card, game, player):
        # Imprint: exile a nonartifact, nonland from hand
        hand_cards = [c for c in player.hand.cards()
                      if CardType.ARTIFACT not in c.data.card_types
                      and CardType.LAND not in c.data.card_types]
        if hand_cards and not player.is_human:
            # AI: imprint lowest-value card
            imprinted = min(hand_cards, key=lambda c: c.data.cmc)
            player.hand.remove(imprinted)
            game.exile.add(imprinted)
            card.counters["imprinted_color"] = list(imprinted.data.colors)
            game.log(f"{player.name} imprints {imprinted.name} under Chrome Mox.")
    def chrome_mox_tap(card, game, player, x=0, targets=None):
        colors = card.counters.get("imprinted_color", [])
        if colors:
            from ..engine.mana import Color as C
            player.mana_pool.add(colors[0], 1)
            game.log(f"{player.name} taps Chrome Mox for 1 mana.")
        else:
            game.log(f"Chrome Mox has no imprinted card.")
    reg["chrome mox"] = {
        "etb_effect": chrome_mox_etb,
        "activated_abilities": [{"name": "Chrome Mox mana", "cost": {"tap": True},
                                  "effect": chrome_mox_tap}],
    }

    # --- Mox Diamond ---
    def mox_diamond_etb(card, game, player):
        # Discard a land or sacrifice
        land_in_hand = [c for c in player.hand.cards()
                        if CardType.LAND in c.data.card_types]
        if land_in_hand:
            discard_land = land_in_hand[0]
            player.hand.remove(discard_land)
            player.graveyard.add(discard_land)
            game.log(f"{player.name} discards {discard_land.name} for Mox Diamond.")
        else:
            game.move_to_graveyard(card)
            game.log(f"{player.name} has no land to discard; Mox Diamond sacrificed.")
    def mox_diamond_tap(card, game, player, x=0, targets=None):
        color = targets[0] if targets else Color.COLORLESS
        player.mana_pool.add(color, 1)
        game.log(f"{player.name} taps Mox Diamond for 1 mana.")
    reg["mox diamond"] = {
        "etb_effect": mox_diamond_etb,
        "tap_mana_choice": True,
        "activated_abilities": [{"name": "Mox Diamond mana", "cost": {"tap": True},
                                  "effect": mox_diamond_tap}],
    }
