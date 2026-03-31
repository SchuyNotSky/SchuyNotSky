"""Tutor card effects."""
from __future__ import annotations
from ..engine.card import CardType
from ..engine.mana import ManaCost


def register_tutor_effects(reg: dict):

    # --- Demonic Tutor ---
    def demonic_tutor(card, game, player, x=0, targets=None):
        name = targets[0] if targets else _ai_pick_tutor_target(player, game)
        if name:
            from ..engine.effects import tutor_to_hand
            tutor_to_hand(player, name, game)
    reg["demonic tutor"] = {"cast_effect": demonic_tutor}

    # --- Vampiric Tutor ---
    def vampiric_tutor(card, game, player, x=0, targets=None):
        name = targets[0] if targets else _ai_pick_tutor_target(player, game)
        if name:
            player.lose_life(2)
            from ..engine.effects import tutor_to_top
            tutor_to_top(player, name, game)
    reg["vampiric tutor"] = {"cast_effect": vampiric_tutor}

    # --- Imperial Seal ---
    def imperial_seal(card, game, player, x=0, targets=None):
        name = targets[0] if targets else _ai_pick_tutor_target(player, game)
        if name:
            player.lose_life(2)
            from ..engine.effects import tutor_to_top
            tutor_to_top(player, name, game)
    reg["imperial seal"] = {"cast_effect": imperial_seal}

    # --- Mystical Tutor ---
    def mystical_tutor(card, game, player, x=0, targets=None):
        name = targets[0] if targets else _ai_pick_instant_sorcery(player, game)
        if name:
            c = player.library.find_by_name(name)
            if c and (CardType.INSTANT in c.data.card_types or CardType.SORCERY in c.data.card_types):
                from ..engine.effects import tutor_to_top
                tutor_to_top(player, name, game)
            else:
                game.log(f"Mystical Tutor: {name} is not an instant or sorcery.")
    reg["mystical tutor"] = {"cast_effect": mystical_tutor}

    # --- Worldly Tutor ---
    def worldly_tutor(card, game, player, x=0, targets=None):
        name = targets[0] if targets else _ai_pick_creature(player, game)
        if name:
            c = player.library.find_by_name(name)
            if c and CardType.CREATURE in c.data.card_types:
                from ..engine.effects import tutor_to_top
                tutor_to_top(player, name, game)
    reg["worldly tutor"] = {"cast_effect": worldly_tutor}

    # --- Enlightened Tutor ---
    def enlightened_tutor(card, game, player, x=0, targets=None):
        name = targets[0] if targets else _ai_pick_artifact_enchantment(player, game)
        if name:
            c = player.library.find_by_name(name)
            if c and (CardType.ARTIFACT in c.data.card_types or CardType.ENCHANTMENT in c.data.card_types):
                from ..engine.effects import tutor_to_top
                tutor_to_top(player, name, game)
    reg["enlightened tutor"] = {"cast_effect": enlightened_tutor}

    # --- Merchant Scroll ---
    def merchant_scroll(card, game, player, x=0, targets=None):
        from ..engine.mana import Color
        name = targets[0] if targets else _ai_pick_blue_instant(player, game)
        if name:
            c = player.library.find_by_name(name)
            if c and CardType.INSTANT in c.data.card_types and Color.BLUE in c.data.colors:
                from ..engine.effects import tutor_to_hand
                tutor_to_hand(player, name, game)
    reg["merchant scroll"] = {"cast_effect": merchant_scroll}

    # --- Gamble ---
    def gamble(card, game, player, x=0, targets=None):
        import random
        name = targets[0] if targets else _ai_pick_tutor_target(player, game)
        if name:
            from ..engine.effects import tutor_to_hand
            tutor_to_hand(player, name, game)
            # Discard random card from hand
            if player.hand.cards():
                discarded = random.choice(player.hand.cards())
                player.discard(discarded)
                game.log(f"Gamble: {player.name} randomly discards {discarded.name}.")
    reg["gamble"] = {"cast_effect": gamble}

    # --- Intuition ---
    def intuition(card, game, player, x=0, targets=None):
        # Search for 3 cards, opponent picks 1 to go to hand, rest to GY
        names = targets[:3] if targets and len(targets) >= 3 else _ai_intuition_picks(player, game)
        found = [player.library.find_by_name(n) for n in names if player.library.find_by_name(n)]
        if not found:
            return
        for c in found:
            player.library.remove(c)
        player.library.shuffle()
        # Opponent picks one (AI: picks the best one for them / worst for us)
        opponents = game.opponents_of(player.player_id)
        if opponents:
            opp = opponents[0]
            chosen = found[0]  # simplified: opponent picks first (usually best)
            player.hand.add(chosen)
            for c in found:
                if c is not chosen:
                    player.graveyard.add(c)
            game.log(f"Intuition: {opp.name} chooses {chosen.name} for {player.name}'s hand.")
        else:
            player.hand.add(found[0])
    reg["intuition"] = {"cast_effect": intuition}

    # --- Lim-Dul's Vault ---
    def lim_duls_vault(card, game, player, x=0, targets=None):
        name = targets[0] if targets else _ai_pick_tutor_target(player, game)
        if not name:
            return
        target_card = player.library.find_by_name(name)
        if not target_card:
            game.log(f"Lim-Dul's Vault: {name} not found in library.")
            return
        life_paid = 0
        while True:
            top5 = player.library.peek_top(5)
            if target_card in top5:
                game.log(f"Lim-Dul's Vault: {name} is in top 5. Paid {life_paid} life.")
                break
            if player.life - 1 <= 0:
                break
            player.lose_life(1)
            life_paid += 1
            # Bottom the 5 and try again
            bottomed = player.library.mill(5)
            for c in reversed(bottomed):
                player.library.add(c, "bottom")
    reg["lim-dul's vault"] = {"cast_effect": lim_duls_vault}


# ---------------------------------------------------------------------------
# AI helpers for tutor targets
# ---------------------------------------------------------------------------

def _ai_pick_tutor_target(player, game) -> str:
    """AI decides what to tutor for based on game state."""
    if player.ai:
        return player.ai.choose_tutor_target(player, game)
    # Fallback priority list
    priority = [
        "Thassa's Oracle", "Demonic Consultation", "Tainted Pact",
        "Isochron Scepter", "Dramatic Reversal",
        "Ad Nauseam", "Necropotence",
        "Force of Will", "Counterspell",
        "Sol Ring", "Mana Crypt",
    ]
    for name in priority:
        if player.library.find_by_name(name):
            return name
    return ""

def _ai_pick_instant_sorcery(player, game) -> str:
    priority = [
        "Demonic Consultation", "Tainted Pact", "Dramatic Reversal",
        "Ad Nauseam", "Force of Will", "Counterspell", "Brainstorm",
    ]
    for name in priority:
        c = player.library.find_by_name(name)
        if c and (CardType.INSTANT in c.data.card_types or CardType.SORCERY in c.data.card_types):
            return name
    return ""

def _ai_pick_creature(player, game) -> str:
    priority = ["Thassa's Oracle", "Grand Abolisher", "Collector Ouphe",
                "Drannith Magistrate", "Thalia, Guardian of Thraben"]
    for name in priority:
        c = player.library.find_by_name(name)
        if c and CardType.CREATURE in c.data.card_types:
            return name
    return ""

def _ai_pick_artifact_enchantment(player, game) -> str:
    priority = ["Isochron Scepter", "Sol Ring", "Mana Crypt", "Rhystic Study",
                "Mystic Remora", "Necropotence", "Sylvan Library"]
    for name in priority:
        c = player.library.find_by_name(name)
        if c and (CardType.ARTIFACT in c.data.card_types or CardType.ENCHANTMENT in c.data.card_types):
            return name
    return ""

def _ai_pick_blue_instant(player, game) -> str:
    from ..engine.mana import Color
    priority = ["Force of Will", "Force of Negation", "Counterspell",
                "Fierce Guardianship", "Brainstorm", "Dramatic Reversal",
                "Pact of Negation", "Swan Song"]
    for name in priority:
        c = player.library.find_by_name(name)
        if c and CardType.INSTANT in c.data.card_types and Color.BLUE in c.data.colors:
            return name
    return ""

def _ai_intuition_picks(player, game):
    return [
        "Thassa's Oracle", "Demonic Consultation", "Brainstorm"
    ]
