"""Card draw and card advantage effects."""
from __future__ import annotations
from ..engine.effects import draw_cards, wheel_effect, ad_nauseam_effect


def register_draw_effects(reg: dict):

    # --- Brainstorm ---
    def brainstorm(card, game, player, x=0, targets=None):
        draw_cards(player, 3, game)
        # Put 2 back on top (AI: put back worst 2)
        hand = player.hand.cards()
        if len(hand) >= 2:
            to_put_back = _worst_two(hand, player, game)
            for c in to_put_back:
                player.hand.remove(c)
                player.library.add(c, "top")
            game.log(f"{player.name} puts {[c.name for c in to_put_back]} back on library (Brainstorm).")
    reg["brainstorm"] = {"cast_effect": brainstorm}

    # --- Ponder ---
    def ponder(card, game, player, x=0, targets=None):
        top3 = player.library.peek_top(3)
        game.log(f"{player.name} looks at top 3: {[c.name for c in top3]} (Ponder).")
        # AI: if top card is good, keep; else shuffle
        if top3 and _is_high_value(top3[0]):
            game.log(f"{player.name} keeps library order.")
        else:
            player.library.shuffle()
            game.log(f"{player.name} shuffles library.")
        draw_cards(player, 1, game)
    reg["ponder"] = {"cast_effect": ponder}

    # --- Preordain ---
    def preordain(card, game, player, x=0, targets=None):
        top2 = player.library.peek_top(2)
        game.log(f"{player.name} scries 2: {[c.name for c in top2]} (Preordain).")
        # AI: bottom any lands if we have mana, else keep
        for c in top2:
            if _is_low_value(c, player):
                player.library.remove(c)
                player.library.add(c, "bottom")
                game.log(f"{player.name} bottoms {c.name}.")
        draw_cards(player, 1, game)
    reg["preordain"] = {"cast_effect": preordain}

    # --- Gitaxian Probe ---
    def gitaxian_probe(card, game, player, x=0, targets=None):
        player.lose_life(2)
        # Look at target opponent's hand
        opps = game.opponents_of(player.player_id)
        if opps:
            opp = targets[0] if targets else opps[0]
            if hasattr(opp, 'hand'):
                hand_names = [c.name for c in opp.hand.cards()]
                game.log(f"{player.name} sees {opp.name}'s hand: {hand_names} (Gitaxian Probe).")
        draw_cards(player, 1, game)
    reg["gitaxian probe"] = {"cast_effect": gitaxian_probe}

    # --- Night's Whisper ---
    def nights_whisper(card, game, player, x=0, targets=None):
        draw_cards(player, 2, game)
        player.lose_life(2)
    reg["night's whisper"] = {"cast_effect": nights_whisper}

    # --- Sign in Blood ---
    def sign_in_blood(card, game, player, x=0, targets=None):
        target_player = targets[0] if targets else player
        if hasattr(target_player, 'draw'):
            draw_cards(target_player, 2, game)
            target_player.lose_life(2)
    reg["sign in blood"] = {"cast_effect": sign_in_blood}

    # --- Windfall ---
    def windfall(card, game, player, x=0, targets=None):
        # Each player discards hand, draws that many
        counts = {p.player_id: len(p.hand) for p in game.players}
        for p in game.players:
            p.discard_hand()
        for p in game.players:
            draw_cards(p, counts[p.player_id], game)
        game.log(f"Windfall: all players discard and redraw.")
    reg["windfall"] = {"cast_effect": windfall}

    # --- Timetwister ---
    def timetwister(card, game, player, x=0, targets=None):
        # Each player shuffles GY + hand into library, draws 7
        for p in game.players:
            cards_in_gy = p.graveyard.cards()
            for c in cards_in_gy:
                p.graveyard.remove(c)
                p.library.add(c, "bottom")
            hand_cards = p.hand.cards()
            for c in hand_cards:
                p.hand.remove(c)
                p.library.add(c, "bottom")
            p.library.shuffle()
        for p in game.players:
            draw_cards(p, 7, game)
        game.log(f"Timetwister: all players shuffle and draw 7.")
    reg["timetwister"] = {"cast_effect": timetwister}

    # --- Wheel of Fortune ---
    def wheel_of_fortune(card, game, player, x=0, targets=None):
        wheel_effect(game, player.player_id)
    reg["wheel of fortune"] = {"cast_effect": wheel_of_fortune}

    # --- Ad Nauseam ---
    def ad_nauseam_cast(card, game, player, x=0, targets=None):
        ad_nauseam_effect(player, game)
    reg["ad nauseam"] = {"cast_effect": ad_nauseam_cast}

    # --- Necropotence ---
    def necro_etb(card, game, player):
        game.log(f"{player.name} controls Necropotence: skips draw step, pay 1 life per card.")
    def necro_end_step(card, game, player):
        # AI: draw up to X cards at end step based on remaining life
        spend = min(player.life - 10, 5)  # keep 10 life buffer
        if spend > 0 and card.controller_id == player.player_id:
            player.lose_life(spend)
            draw_cards(player, spend, game)
            game.log(f"{player.name} Necro-draws {spend} cards (pays {spend} life).")
    reg["necropotence"] = {
        "etb_effect": necro_etb,
        "triggered_abilities": [{"trigger": "end_step", "effect": necro_end_step}],
    }

    # --- Sylvan Library ---
    def sylvan_library_upkeep(card, game, player):
        if card.controller_id != player.player_id:
            return
        # Draw 2 extra, then put back 2 OR pay 4 life per card kept
        draw_cards(player, 2, game)
        # AI: pay life to keep both if we have enough
        if player.life > 20:
            player.lose_life(8)
            game.log(f"{player.name} pays 8 life to keep both Sylvan Library draws.")
        else:
            # Put both back
            hand = player.hand.cards()
            if len(hand) >= 2:
                for c in hand[-2:]:
                    player.hand.remove(c)
                    player.library.add(c, "top")
                game.log(f"{player.name} puts 2 cards back on library (Sylvan Library).")
    reg["sylvan library"] = {
        "triggered_abilities": [{"trigger": "upkeep", "effect": sylvan_library_upkeep}],
    }

    # --- Rhystic Study ---
    def rhystic_study_trigger(card, game, player):
        # Triggered when an opponent casts a spell
        # This is a "cast trigger" — for simulation we handle it in game.py
        pass
    def rhystic_etb(card, game, player):
        game.log(f"{player.name} controls Rhystic Study: opponents must pay {{1}} or you draw.")
        # Register as a cast trigger
        if not hasattr(game, '_rhystic_controllers'):
            game._rhystic_controllers = []
        game._rhystic_controllers.append((player.player_id, card))
    reg["rhystic study"] = {"etb_effect": rhystic_etb}

    # --- Mystic Remora ---
    def remora_etb(card, game, player):
        game.log(f"{player.name} controls Mystic Remora.")
        card.counters["fade"] = 0
    def remora_upkeep(card, game, player):
        if card.controller_id != player.player_id:
            return
        card.counters["fade"] = card.counters.get("fade", 0) + 1
        cumulative_cost = card.counters["fade"]
        from ..engine.mana import ManaCost as MC
        cost = MC(generic=cumulative_cost)
        if player.mana_pool.pay(cost):
            game.log(f"{player.name} pays {{{cumulative_cost}}} for Mystic Remora cumulative upkeep.")
        else:
            game.move_to_graveyard(card)
            game.log(f"{player.name} sacrifices Mystic Remora (can't pay cumulative upkeep).")
    reg["mystic remora"] = {
        "etb_effect": remora_etb,
        "triggered_abilities": [{"trigger": "upkeep", "effect": remora_upkeep}],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_high_value(card) -> bool:
    """Is this card high-value enough to keep on top?"""
    high_value = {
        "thassa's oracle", "demonic consultation", "ad nauseam",
        "force of will", "counterspell", "demonic tutor",
        "vampiric tutor", "mana crypt", "sol ring",
    }
    return card.name.lower() in high_value

def _is_low_value(card, player) -> bool:
    """Is this card low enough value to scry to bottom?"""
    # Scry away lands if we have plenty
    from ..engine.card import CardType
    lands = [c for c in player.hand.cards() if CardType.LAND in c.data.card_types]
    if CardType.LAND in card.data.card_types and len(lands) >= 4:
        return True
    return False

def _worst_two(hand, player, game):
    """Pick the 2 worst cards in hand to put back (for Brainstorm)."""
    from ..engine.card import CardType
    # Priority: put back extra lands, then low-CMC basics, then high-CMC spells
    scored = []
    for c in hand:
        score = 0
        if CardType.LAND in c.data.card_types:
            lands = sum(1 for x in hand if CardType.LAND in x.data.card_types)
            score = 10 if lands > 3 else 5
        elif c.data.cmc > 5:
            score = 3
        else:
            score = c.data.cmc
        scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:2]]
