"""
CLI interface for human player actions.
Called by game.py whenever a human player needs to make a decision.
"""
from __future__ import annotations
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..engine.player import Player
    from ..engine.game import GameState
    from ..engine.card import Card
    from ..engine.combat import AttackAssignment, BlockAssignment


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_game_state(player: "Player", game: "GameState"):
    """Print a full snapshot of the game state for the human player."""
    print("\n" + "=" * 60)
    print(f"  TURN {game.turn_number}  |  Phase: {game.phase.name}")
    print("=" * 60)

    # Show all players
    for p in game.players:
        marker = ">>> " if p.player_id == player.player_id else "    "
        hand_count = len(p.hand) if p.player_id == player.player_id else f"{len(p.hand)} cards"
        lib = len(p.library)
        gy = len(p.graveyard)
        lost = " [LOST]" if p.lost else (" [WON]" if p.won else "")
        print(f"{marker}{p.name:20s}  Life:{p.life:3d}  Hand:{hand_count}  "
              f"Lib:{lib:3d}  GY:{gy:2d}{lost}")

    # Show human's hand
    print(f"\n  YOUR HAND ({len(player.hand)} cards):")
    for i, c in enumerate(player.hand.cards()):
        cost = str(c.data.mana_cost)
        types = c.data.type_line()
        pt = f" {c.power}/{c.toughness}" if c.power is not None else ""
        print(f"    [{i}] {c.name:35s} {cost:10s} {types}{pt}")

    # Show battlefield
    bf_mine = game.battlefield.permanents_controlled_by(player.player_id)
    if bf_mine:
        print(f"\n  YOUR BATTLEFIELD ({len(bf_mine)} permanents):")
        for c in bf_mine:
            tap = "[T]" if c.tapped else "   "
            sick = "(sick)" if c.summoning_sick else "      "
            pt = f" {c.power}/{c.toughness}" if c.power is not None else ""
            counters = f" {c.counters}" if c.counters else ""
            print(f"    {tap} {sick} {c.name:35s}{pt}{counters}")

    for opp in game.opponents_of(player.player_id):
        opp_bf = game.battlefield.permanents_controlled_by(opp.player_id)
        if opp_bf:
            print(f"\n  {opp.name}'s BATTLEFIELD ({len(opp_bf)} permanents):")
            for c in opp_bf:
                tap = "[T]" if c.tapped else "   "
                pt = f" {c.power}/{c.toughness}" if c.power is not None else ""
                print(f"    {tap} {c.name:35s}{pt}")

    # Show stack
    if not game.stack.is_empty():
        print(f"\n  STACK (top first):")
        for item in game.stack.items():
            print(f"    → {item.name} (by {game.get_player(item.controller_id).name if game.get_player(item.controller_id) else item.controller_id})")

    # Show mana pool
    pool = player.mana_pool
    if pool.total() > 0:
        print(f"\n  MANA POOL: {pool}")

    print()


def print_commanders(game: "GameState"):
    """Show all commanders."""
    print("\n  COMMANDERS:")
    for player in game.players:
        cmds = game.command_zone.commanders_for(player.player_id)
        if cmds:
            for c in cmds:
                tax = game.commander_cast_count.get(player.player_id, {}).get(c.name, 0)
                tax_str = f" (tax: +{tax*2})" if tax > 0 else ""
                print(f"    {player.name}: {c.name}{tax_str}")


# ---------------------------------------------------------------------------
# Priority action
# ---------------------------------------------------------------------------

def prompt_priority_action(
    player: "Player", active_player: "Player",
    game: "GameState", is_active: bool, is_main: bool
) -> bool:
    """
    Ask the human player what to do with priority.
    Returns True if an action was taken.
    """
    print_game_state(player, game)
    print_commanders(game)

    is_your_turn = player.player_id == active_player.player_id
    turn_str = "YOUR TURN" if is_your_turn else f"{active_player.name}'s turn"
    print(f"  [{turn_str} | {game.phase.name}]  Your priority.")
    print()

    actions = _build_action_list(player, active_player, game, is_active, is_main)

    print("  Actions:")
    print("    [p] Pass priority")
    for i, (label, _) in enumerate(actions):
        print(f"    [{i}] {label}")
    print()

    while True:
        raw = input("  > ").strip().lower()
        if raw in ("p", "pass", ""):
            return False

        if raw.isdigit():
            idx = int(raw)
            if 0 <= idx < len(actions):
                label, action_fn = actions[idx]
                result = action_fn()
                return result if result is not None else True

        # Handle "cast N" or "play N"
        if raw.startswith("cast ") or raw.startswith("play "):
            parts = raw.split(" ", 1)
            if len(parts) > 1:
                name = parts[1]
                card = player.hand.find_by_name(name)
                if card:
                    from ..engine.card import CardType
                    if CardType.LAND in card.data.card_types:
                        return game.play_land(card, player)
                    else:
                        return game.cast_spell(card, player)

        # "tap N" to tap a mana source
        if raw.startswith("tap "):
            name = raw[4:].strip()
            card = game.battlefield.find_by_name(name, player.player_id)
            if card and not card.tapped:
                player.produce_mana_from_permanent(card)
                return True

        # "info N" to show card info
        if raw.startswith("info "):
            name = raw[5:].strip()
            _show_card_info(name, player, game)
            continue

        print("  Invalid input. Try a number, 'p' to pass, 'cast <name>', 'tap <name>', or 'info <name>'.")


def _build_action_list(player, active_player, game, is_active, is_main):
    """Build list of available actions as (label, callable) tuples."""
    from ..engine.card import CardType, Keyword
    actions = []

    hand = player.hand.cards()

    # Play land
    if is_active and is_main and player.lands_played_this_turn < player.max_lands_per_turn:
        lands = [c for c in hand if CardType.LAND in c.data.card_types]
        for land in lands:
            def make_land_fn(l=land):
                def play():
                    return game.play_land(l, player)
                return play
            actions.append((f"Play land: {land.name}", make_land_fn()))

    # Cast spells
    for card in hand:
        if CardType.LAND in card.data.card_types:
            continue
        is_instant = (CardType.INSTANT in card.data.card_types or
                      card.has_keyword(Keyword.FLASH))
        can_cast_timing = is_instant or (is_active and is_main)
        if can_cast_timing and player.mana_pool.can_pay(card.data.mana_cost):
            def make_cast_fn(c=card):
                def cast():
                    targets = _prompt_targets(c, player, game)
                    x_val = _prompt_x(c)
                    return game.cast_spell(c, player, x_value=x_val, targets=targets)
                return cast
            cost = str(card.data.mana_cost)
            actions.append((f"Cast {card.name} {cost}", make_cast_fn()))

    # Tap mana sources
    mana_sources = game.battlefield.untapped_mana_sources(player.player_id)
    if mana_sources:
        def tap_all():
            for src in game.battlefield.untapped_mana_sources(player.player_id):
                if src.data.tap_mana:
                    player.produce_mana_from_permanent(src)
                elif src.data.tap_mana_choice:
                    from ..engine.mana import Color
                    player.produce_mana_from_permanent(src, Color.COLORLESS)
            print(f"  Mana pool: {player.mana_pool}")
            return False  # tapping mana doesn't consume an action
        actions.append((f"Tap all mana sources ({len(mana_sources)} available)", tap_all))

    # Activate battlefield abilities
    for card in game.battlefield.permanents_controlled_by(player.player_id):
        for i, abil in enumerate(card.data.activated_abilities):
            cost = abil.get("cost", {})
            name = abil.get("name", f"{card.name} ability")
            can_activate = True
            if cost.get("tap") and card.tapped:
                can_activate = False
            if cost.get("mana") and not player.mana_pool.can_pay(cost["mana"]):
                can_activate = False
            if can_activate:
                def make_abil_fn(c=card, idx=i):
                    def activate():
                        return game.activate_ability(c, idx, player)
                    return activate
                actions.append((f"Activate: {name}", make_abil_fn()))

    return actions


def _prompt_targets(card, player, game):
    """Ask human for targets if the card needs them."""
    from ..engine.card import CardType
    # Check if card needs a target (simplified: check oracle text for "target")
    if "target" in card.data.oracle_text.lower():
        opponents = game.opponents_of(player.player_id)
        all_permanents = game.battlefield.cards()
        print(f"\n  {card.name} needs a target.")
        print("  Options:")
        print("    [p] No target / self")
        choices = []
        for opp in opponents:
            print(f"    [p{opp.player_id[:4]}] Player: {opp.name} (life: {opp.life})")
        idx = 0
        for perm in all_permanents:
            ctrl = game.get_player(perm.controller_id)
            name = ctrl.name if ctrl else "?"
            print(f"    [{idx}] {perm.name} (ctrl: {name})")
            choices.append(perm)
            idx += 1

        raw = input("  Target > ").strip()
        if raw.isdigit() and int(raw) < len(choices):
            return [choices[int(raw)]]
        # Check for player target
        for opp in opponents:
            if raw.lower() in opp.name.lower() or raw.lower() in opp.player_id:
                return [opp]
    return []


def _prompt_x(card) -> int:
    """Ask human for X value if the card uses X."""
    if "{x}" in str(card.data.mana_cost).lower() or card.data.mana_cost.x_count > 0:
        raw = input(f"  X value for {card.name}? > ").strip()
        try:
            return int(raw)
        except ValueError:
            return 0
    return 0


def _show_card_info(name: str, player, game):
    """Print oracle text for a named card."""
    # Search hand, battlefield, GY
    all_cards = (player.hand.cards() +
                 game.battlefield.cards() +
                 player.graveyard.cards())
    for c in all_cards:
        if name.lower() in c.name.lower():
            print(str(c.data))
            return
    print(f"  Card '{name}' not found nearby.")


# ---------------------------------------------------------------------------
# Declare attackers / blockers
# ---------------------------------------------------------------------------

def prompt_declare_attackers(
    player: "Player", opponents: list, game: "GameState"
) -> list:
    from ..engine.combat import AttackAssignment
    from ..engine.card import CardType

    creatures = game.battlefield.creatures_controlled_by(player.player_id)
    can_attack = [c for c in creatures if c.can_attack()]

    if not can_attack:
        return []

    print(f"\n  DECLARE ATTACKERS")
    print("  Creatures that can attack:")
    for i, c in enumerate(can_attack):
        pt = f"{c.power}/{c.toughness}"
        print(f"    [{i}] {c.name} {pt}")
    print("  Opponents:")
    for i, opp in enumerate(opponents):
        print(f"    [{chr(ord('a')+i)}] {opp.name} (life: {opp.life})")
    print("  Enter pairs like '0a 1a' or press Enter to not attack.")

    raw = input("  Attackers > ").strip()
    assignments = []

    if not raw:
        return []

    opp_map = {chr(ord('a')+i): opp for i, opp in enumerate(opponents)}

    for token in raw.split():
        if len(token) >= 2:
            try:
                att_idx = int(token[:-1])
                opp_key = token[-1]
                if att_idx < len(can_attack) and opp_key in opp_map:
                    assignments.append(AttackAssignment(
                        attacker=can_attack[att_idx],
                        defending_player_id=opp_map[opp_key].player_id,
                    ))
            except ValueError:
                pass

    return assignments


def prompt_declare_blockers(
    player: "Player", attackers: list, game: "GameState"
) -> list:
    from ..engine.combat import BlockAssignment
    creatures = game.battlefield.creatures_controlled_by(player.player_id)
    can_block = [c for c in creatures if c.can_block()]

    if not can_block or not attackers:
        return []

    my_attackers = [a for a in attackers if a.defending_player_id == player.player_id]
    if not my_attackers:
        return []

    print(f"\n  DECLARE BLOCKERS (as {player.name})")
    print("  Attackers:")
    for i, a in enumerate(my_attackers):
        pt = f"{a.attacker.power}/{a.attacker.toughness}"
        ctrl = game.get_player(a.attacker.controller_id)
        print(f"    [{i}] {a.attacker.name} {pt} (from {ctrl.name if ctrl else '?'})")
    print("  Your blockers:")
    for i, c in enumerate(can_block):
        pt = f"{c.power}/{c.toughness}"
        print(f"    [{chr(ord('a')+i)}] {c.name} {pt}")
    print("  Enter pairs like '0a' (attacker 0 blocked by creature a). Press Enter to not block.")

    raw = input("  Blockers > ").strip()
    assignments = []

    if not raw:
        return []

    blocker_map = {chr(ord('a')+i): c for i, c in enumerate(can_block)}

    for token in raw.split():
        if len(token) >= 2:
            try:
                att_idx = int(token[:-1])
                blk_key = token[-1]
                if att_idx < len(my_attackers) and blk_key in blocker_map:
                    assignments.append(BlockAssignment(
                        blocker=blocker_map[blk_key],
                        blocked_attacker=my_attackers[att_idx].attacker,
                    ))
            except ValueError:
                pass

    return assignments


# ---------------------------------------------------------------------------
# Discard
# ---------------------------------------------------------------------------

def prompt_discard(player: "Player", game: "GameState"):
    """Ask human player to discard a card."""
    hand = player.hand.cards()
    print(f"\n  DISCARD (hand size {len(hand)}, max {player.must_discard_to})")
    for i, c in enumerate(hand):
        print(f"    [{i}] {c.name}")
    while True:
        raw = input("  Discard > ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 0 <= idx < len(hand):
                player.discard(hand[idx])
                print(f"  Discarded {hand[idx].name}.")
                return
        print("  Invalid choice.")
