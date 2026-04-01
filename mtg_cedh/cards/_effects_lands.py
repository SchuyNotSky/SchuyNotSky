"""Land card effects: fetches, shocks, duals, utility lands."""
from __future__ import annotations
from ..engine.mana import Color, ManaCost
from ..engine.card import CardType


def register_land_effects(reg: dict):

    # --- Command Tower ---
    def command_tower_tap(card, game, player, x=0, targets=None):
        color = targets[0] if targets else _pick_needed_color(player, game)
        player.mana_pool.add(color, 1)
        game.log(f"{player.name} taps Command Tower for {color.value}.")
    reg["command tower"] = {
        "tap_mana": None,
        "tap_mana_choice": True,
        "activated_abilities": [{"name": "Command Tower", "cost": {"tap": True},
                                  "effect": command_tower_tap}],
    }

    # --- Ancient Tomb ---
    def ancient_tomb_tap(card, game, player, x=0, targets=None):
        player.mana_pool.add(Color.COLORLESS, 2)
        player.take_damage(2, source=card)
        game.log(f"{player.name} taps Ancient Tomb for {{2}} (takes 2 damage).")
    reg["ancient tomb"] = {
        "tap_mana": None,
        "activated_abilities": [{"name": "Ancient Tomb", "cost": {"tap": True},
                                  "effect": ancient_tomb_tap}],
    }

    # --- City of Traitors ---
    def city_tap(card, game, player, x=0, targets=None):
        player.mana_pool.add(Color.COLORLESS, 2)
        game.log(f"{player.name} taps City of Traitors for {{2}}.")
    def city_etb(card, game, player):
        # Sacrifice if you play another land (handled in game logic check)
        pass
    reg["city of traitors"] = {
        "tap_mana": None,
        "etb_effect": city_etb,
        "activated_abilities": [{"name": "City of Traitors", "cost": {"tap": True},
                                  "effect": city_tap}],
    }

    # --- Fetch lands (all 10) ---
    _register_fetch_lands(reg)

    # --- Shock lands ---
    _register_shock_lands(reg)

    # --- Original dual lands ---
    _register_dual_lands(reg)

    # --- Exotic Orchard ---
    def exotic_tap(card, game, player, x=0, targets=None):
        color = targets[0] if targets else _pick_needed_color(player, game)
        player.mana_pool.add(color, 1)
        game.log(f"{player.name} taps Exotic Orchard for {color.value}.")
    reg["exotic orchard"] = {
        "tap_mana": None,
        "tap_mana_choice": True,
        "activated_abilities": [{"name": "Exotic Orchard", "cost": {"tap": True},
                                  "effect": exotic_tap}],
    }

    # --- Cavern of Souls ---
    def cavern_tap(card, game, player, x=0, targets=None):
        color = targets[0] if targets else _pick_needed_color(player, game)
        player.mana_pool.add(color, 1)
        game.log(f"{player.name} taps Cavern of Souls for {color.value} (uncounterable mana).")
    reg["cavern of souls"] = {
        "tap_mana": None,
        "tap_mana_choice": True,
        "activated_abilities": [{"name": "Cavern of Souls", "cost": {"tap": True},
                                  "effect": cavern_tap}],
    }

    # --- Gemstone Caverns ---
    def caverns_etb(card, game, player):
        # If not the first player, you may exile a card from hand to put a luck counter on it
        active = game.active_player()
        if active and active.player_id != player.player_id:
            hand = player.hand.cards()
            if hand:
                discarded = hand[0]
                player.hand.remove(discarded)
                game.exile.add(discarded)
                card.counters["luck"] = 1
                game.log(f"{player.name} exiles {discarded.name} for Gemstone Caverns luck counter.")
    def caverns_tap(card, game, player, x=0, targets=None):
        if card.counters.get("luck"):
            color = targets[0] if targets else _pick_needed_color(player, game)
            player.mana_pool.add(color, 1)
        else:
            player.mana_pool.add(Color.COLORLESS, 1)
        game.log(f"{player.name} taps Gemstone Caverns.")
    reg["gemstone caverns"] = {
        "etb_effect": caverns_etb,
        "tap_mana": None,
        "activated_abilities": [{"name": "Gemstone Caverns", "cost": {"tap": True},
                                  "effect": caverns_tap}],
    }

    # --- Urborg, Tomb of Yawgmoth ---
    def urborg_etb(card, game, player):
        game.log(f"Urborg, Tomb of Yawgmoth: all lands are now Swamps as well.")
    reg["urborg, tomb of yawgmoth"] = {"etb_effect": urborg_etb}


def _register_fetch_lands(reg: dict):
    """Register all 10 Onslaught/Zendikar fetch lands."""
    fetches = {
        "polluted delta":     ([Color.BLUE, Color.BLACK], ["Island","Swamp"]),
        "flooded strand":     ([Color.WHITE, Color.BLUE], ["Plains","Island"]),
        "bloodstained mire":  ([Color.BLACK, Color.RED],  ["Swamp","Mountain"]),
        "wooded foothills":   ([Color.RED, Color.GREEN],  ["Mountain","Forest"]),
        "windswept heath":    ([Color.GREEN, Color.WHITE], ["Forest","Plains"]),
        "misty rainforest":   ([Color.GREEN, Color.BLUE],  ["Forest","Island"]),
        "scalding tarn":      ([Color.BLUE, Color.RED],   ["Island","Mountain"]),
        "marsh flats":        ([Color.WHITE, Color.BLACK], ["Plains","Swamp"]),
        "arid mesa":          ([Color.WHITE, Color.RED],   ["Plains","Mountain"]),
        "verdant catacombs":  ([Color.BLACK, Color.GREEN], ["Swamp","Forest"]),
    }
    for name, (colors, subtypes) in fetches.items():
        def make_fetch(fetch_colors, fetch_subtypes):
            def fetch_tap(card, game, player, x=0, targets=None):
                player.take_damage(1)
                card_zone = card.zone
                game.battlefield.remove(card)
                # Search for a land with one of the fetch subtypes
                found = None
                for lib_card in player.library.cards():
                    if any(s in lib_card.data.subtypes for s in fetch_subtypes):
                        found = lib_card
                        break
                if found:
                    player.library.remove(found)
                    game.move_to_battlefield(found, player.player_id)
                    found.tapped = True
                    player.library.shuffle()
                    game.log(f"{player.name} fetches {found.name} (takes 1 damage).")
                else:
                    game.log(f"{player.name} fetches but finds no valid land.")
            return fetch_tap
        reg[name] = {
            "tap_mana": None,
            "activated_abilities": [{"name": f"{name.title()} fetch",
                                      "cost": {"tap": True, "life": 1},
                                      "effect": make_fetch(colors, subtypes)}],
        }


def _register_shock_lands(reg: dict):
    """Register all 10 Ravnica shock lands."""
    shocks = {
        "watery grave":       ([Color.BLUE, Color.BLACK],   ["Island", "Swamp"]),
        "steam vents":        ([Color.BLUE, Color.RED],     ["Island", "Mountain"]),
        "hallowed fountain":  ([Color.WHITE, Color.BLUE],   ["Plains", "Island"]),
        "overgrown tomb":     ([Color.BLACK, Color.GREEN],  ["Swamp", "Forest"]),
        "stomping ground":    ([Color.RED, Color.GREEN],    ["Mountain", "Forest"]),
        "sacred foundry":     ([Color.RED, Color.WHITE],    ["Mountain", "Plains"]),
        "godless shrine":     ([Color.WHITE, Color.BLACK],  ["Plains", "Swamp"]),
        "temple garden":      ([Color.GREEN, Color.WHITE],  ["Forest", "Plains"]),
        "breeding pool":      ([Color.GREEN, Color.BLUE],   ["Forest", "Island"]),
        "blood crypt":        ([Color.BLACK, Color.RED],    ["Swamp", "Mountain"]),
    }
    for name, (colors, subtypes) in shocks.items():
        def make_shock(shock_colors, shock_subtypes):
            def shock_etb(card, game, player):
                # May pay 2 life to enter untapped
                if player.life > 8:  # AI always pays if above threshold
                    player.take_damage(2)
                    game.log(f"{player.name} pays 2 life for {card.name} to enter untapped.")
                else:
                    card.tapped = True
                    game.log(f"{card.name} enters tapped (no life paid).")
            def shock_tap(card, game, player, x=0, targets=None):
                for c in shock_colors:
                    player.mana_pool.add(c, 1)
                game.log(f"{player.name} taps {card.name} for {'+'.join(c.value for c in shock_colors)}.")
            return shock_etb, shock_tap
        etb, tap_fn = make_shock(colors, subtypes)
        reg[name] = {
            "etb_effect": etb,
            "tap_mana": None,
            "activated_abilities": [{"name": f"{name.title()} tap",
                                      "cost": {"tap": True},
                                      "effect": tap_fn}],
        }


def _register_dual_lands(reg: dict):
    """Register the 10 original dual lands (always enter untapped)."""
    duals = {
        "underground sea":  [Color.BLUE, Color.BLACK],
        "volcanic island":  [Color.BLUE, Color.RED],
        "tundra":           [Color.WHITE, Color.BLUE],
        "bayou":            [Color.BLACK, Color.GREEN],
        "savannah":         [Color.GREEN, Color.WHITE],
        "taiga":            [Color.RED, Color.GREEN],
        "scrubland":        [Color.WHITE, Color.BLACK],
        "plateau":          [Color.RED, Color.WHITE],
        "tropical island":  [Color.GREEN, Color.BLUE],
        "badlands":         [Color.BLACK, Color.RED],
    }
    for name, colors in duals.items():
        def make_dual(dual_colors):
            def dual_tap(card, game, player, x=0, targets=None):
                for c in dual_colors:
                    player.mana_pool.add(c, 1)
                game.log(f"{player.name} taps {card.name} for {'+'.join(c.value for c in dual_colors)}.")
            return dual_tap
        reg[name] = {
            "tap_mana": None,
            "activated_abilities": [{"name": f"{name.title()} tap",
                                      "cost": {"tap": True},
                                      "effect": make_dual(colors)}],
        }


def _pick_needed_color(player, game) -> Color:
    """Pick the color this player needs most for their hand."""
    from ..engine.card import CardType as CT
    color_needs = {c: 0 for c in Color if c != Color.GENERIC}
    for card in player.hand.cards():
        if CT.LAND not in card.data.card_types:
            for c, n in card.data.mana_cost.pips.items():
                color_needs[c] = color_needs.get(c, 0) + n
    if any(v > 0 for v in color_needs.values()):
        return max(color_needs, key=lambda c: color_needs[c])
    return Color.COLORLESS
