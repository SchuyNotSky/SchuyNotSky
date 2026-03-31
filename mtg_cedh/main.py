"""
MTG cEDH Simulator — Entry Point

Usage:
    python -m mtg_cedh.main                   # Interactive menu
    python -m mtg_cedh.main --mode ai         # AI vs AI (watch a game)
    python -m mtg_cedh.main --mode human      # Human vs 3 AI
    python -m mtg_cedh.main --decks thrasios_tymna najeela kenrith tivit
    python -m mtg_cedh.main --prefetch        # Pre-cache all Scryfall data
    python -m mtg_cedh.main --list-decks      # Show saved decks
    python -m mtg_cedh.main --add-deck <id> <file>  # Register a deck file
    python -m mtg_cedh.main --turns 15        # Set max turns (default 20)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .engine.player import Player
from .engine.game import GameState
from .engine.card import Card
from .decks.storage import (
    list_decks, get_deck_path, save_deck_file,
    create_placeholder_decks, print_deck_list,
)
from .decks.loader import load_deck_file, make_card_instances, prefetch_deck
from .ai.cedh_ai import make_ai


# ---------------------------------------------------------------------------
# Game setup
# ---------------------------------------------------------------------------

def setup_players(
    deck_configs: List[Tuple[str, str, bool]]
) -> Tuple[List[Player], Dict[str, List[Card]], Dict[str, List[Card]]]:
    """
    Build Player objects, load decks, return (players, deck_map, commander_map).
    deck_configs: [(player_name, deck_id, is_human), ...]
    """
    players = []
    deck_map: Dict[str, List[Card]] = {}
    commander_map: Dict[str, List[Card]] = {}

    for i, (p_name, deck_id, is_human) in enumerate(deck_configs):
        player_id = f"p{i+1}"
        player = Player(player_id=player_id, name=p_name, is_human=is_human)

        # Load deck
        deck_path = get_deck_path(deck_id)
        if not deck_path:
            print(f"[!] Deck '{deck_id}' not found. Run --prefetch or --list-decks first.")
            sys.exit(1)

        print(f"  Loading deck '{deck_id}' for {p_name} …")
        commander_data_list, deck_data_list = load_deck_file(deck_path)

        # Create card instances
        deck_map[player_id] = make_card_instances(deck_data_list, player_id)
        commander_map[player_id] = make_card_instances(commander_data_list, player_id)

        # Attach AI if not human
        if not is_human:
            player.ai = make_ai(player_id, deck_id)

        players.append(player)
        print(f"  {p_name}: {len(deck_map[player_id])} cards + {len(commander_map[player_id])} commander(s)")

    return players, deck_map, commander_map


def run_game(
    deck_configs: List[Tuple[str, str, bool]],
    max_turns: int = 20,
    seed: Optional[int] = None,
):
    """Run a single game with the given deck configurations."""
    import random
    if seed is None:
        seed = random.randint(0, 999999)
    print(f"\n  Seed: {seed}")

    players, deck_map, commander_map = setup_players(deck_configs)

    game = GameState(players=players, seed=seed)
    game.setup_game(deck_map, commander_map)
    game.run_game(max_turns=max_turns)

    return game


# ---------------------------------------------------------------------------
# Simulation mode (AI vs AI, multiple games)
# ---------------------------------------------------------------------------

def run_simulation(
    deck_configs: List[Tuple[str, str, bool]],
    num_games: int = 10,
    max_turns: int = 20,
):
    """Run multiple AI vs AI games and print win statistics."""
    import random
    win_counts: Dict[str, int] = {}
    draw_count = 0

    for g_num in range(1, num_games + 1):
        print(f"\n{'='*40}")
        print(f"  Game {g_num}/{num_games}")
        print(f"{'='*40}")
        game = run_game(deck_configs, max_turns=max_turns)

        if game.winner:
            name = game.winner.name
            win_counts[name] = win_counts.get(name, 0) + 1
        else:
            draw_count += 1

    print(f"\n{'='*50}")
    print(f"  SIMULATION RESULTS ({num_games} games)")
    print(f"{'='*50}")
    for name, wins in sorted(win_counts.items(), key=lambda x: -x[1]):
        pct = wins / num_games * 100
        print(f"  {name:30s} {wins:3d} wins  ({pct:.1f}%)")
    if draw_count:
        print(f"  {'Draws/Timeouts':30s} {draw_count:3d}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def interactive_menu():
    """Simple interactive menu for first-time users."""
    print("\n" + "="*55)
    print("  MTG cEDH Simulator")
    print("="*55)

    decks = list_decks()
    if not decks:
        print("\n  No decks found. Creating placeholder deck files …")
        create_placeholder_decks()
        decks = list_decks()

    print(f"\n  Available decks ({len(decks)}):")
    for i, d in enumerate(decks):
        print(f"    [{i}] {d['name']}")
        if d.get('description'):
            print(f"        {d['description']}")

    print("\n  Modes:")
    print("    [1] Human vs 3 AI")
    print("    [2] AI vs AI (watch)")
    print("    [3] Run simulation (N games, stats)")
    print("    [4] Pre-fetch Scryfall data for a deck")
    print("    [5] Add a deck from file")
    print("    [q] Quit")

    choice = input("\n  Choose mode > ").strip()

    if choice == "q":
        sys.exit(0)
    elif choice == "1":
        _menu_human_game(decks)
    elif choice == "2":
        _menu_ai_game(decks)
    elif choice == "3":
        _menu_simulation(decks)
    elif choice == "4":
        _menu_prefetch(decks)
    elif choice == "5":
        _menu_add_deck()
    else:
        print("  Unknown choice.")


def _menu_human_game(decks):
    print("\n  Select your deck:")
    for i, d in enumerate(decks):
        print(f"    [{i}] {d['name']}")
    human_idx = int(input("  Your deck > ").strip())
    human_deck = decks[human_idx]

    ai_decks = [d for i, d in enumerate(decks) if i != human_idx][:3]
    while len(ai_decks) < 3:
        ai_decks.append(ai_decks[0])  # pad with duplicates if fewer than 3

    your_name = input("  Your name > ").strip() or "Human"
    configs = [(your_name, human_deck['id'], True)]
    for i, d in enumerate(ai_decks):
        configs.append((f"AI-{d['name'][:12]}", d['id'], False))

    turns = input("  Max turns (default 20) > ").strip()
    max_turns = int(turns) if turns.isdigit() else 20
    run_game(configs, max_turns=max_turns)


def _menu_ai_game(decks):
    print("\n  Select 4 decks for AI vs AI (enter 4 numbers separated by spaces):")
    for i, d in enumerate(decks):
        print(f"    [{i}] {d['name']}")
    raw = input("  Decks > ").strip()
    indices = [int(x) for x in raw.split() if x.isdigit() and int(x) < len(decks)]
    if len(indices) < 4:
        indices = indices + [0] * (4 - len(indices))

    configs = [(f"AI-{decks[idx]['name'][:12]}", decks[idx]['id'], False)
               for idx in indices[:4]]
    turns = input("  Max turns (default 20) > ").strip()
    max_turns = int(turns) if turns.isdigit() else 20
    run_game(configs, max_turns=max_turns)


def _menu_simulation(decks):
    print("\n  Select 4 decks (enter 4 numbers):")
    for i, d in enumerate(decks):
        print(f"    [{i}] {d['name']}")
    raw = input("  Decks > ").strip()
    indices = [int(x) for x in raw.split() if x.isdigit() and int(x) < len(decks)]
    if len(indices) < 4:
        indices = indices + [0] * (4 - len(indices))

    configs = [(f"AI-{decks[idx]['name'][:12]}", decks[idx]['id'], False)
               for idx in indices[:4]]
    num_raw = input("  Number of games (default 10) > ").strip()
    num_games = int(num_raw) if num_raw.isdigit() else 10
    run_simulation(configs, num_games=num_games)


def _menu_prefetch(decks):
    print("\n  Select deck to pre-fetch:")
    for i, d in enumerate(decks):
        print(f"    [{i}] {d['name']}")
    idx = int(input("  Deck > ").strip())
    deck = decks[idx]
    path = get_deck_path(deck['id'])
    if path:
        prefetch_deck(path)
    else:
        print(f"  Deck file not found for '{deck['id']}'.")


def _menu_add_deck():
    path = input("  Path to deck list file > ").strip()
    deck_id = input("  Short ID (e.g. my_thrasios) > ").strip()
    name = input("  Display name > ").strip()
    commander = input("  Commander name(s) > ").strip()
    save_deck_file(path, deck_id, name=name, commander=commander)
    print(f"  Deck '{deck_id}' added.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MTG cEDH Simulator")
    parser.add_argument("--mode", choices=["human", "ai", "sim"],
                        help="Game mode: human|ai|sim")
    parser.add_argument("--decks", nargs="+", metavar="DECK_ID",
                        help="Deck IDs to use (in seat order)")
    parser.add_argument("--human-seat", type=int, default=0,
                        help="Which seat is the human player (0-indexed, default 0)")
    parser.add_argument("--turns", type=int, default=20,
                        help="Maximum turns per game (default 20)")
    parser.add_argument("--games", type=int, default=10,
                        help="Number of games for simulation mode (default 10)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducibility")
    parser.add_argument("--prefetch", action="store_true",
                        help="Pre-fetch Scryfall data for all registered decks")
    parser.add_argument("--list-decks", action="store_true",
                        help="List all registered decks")
    parser.add_argument("--add-deck", nargs=2, metavar=("DECK_ID", "FILE"),
                        help="Register a deck list file")
    parser.add_argument("--init", action="store_true",
                        help="Create placeholder deck files and exit")
    args = parser.parse_args()

    # Ensure placeholder decks exist
    create_placeholder_decks()

    if args.init:
        print("Placeholder deck files created in mtg_cedh/decks/lists/")
        print("Fill them in with your deck lists, then run --prefetch.")
        return

    if args.list_decks:
        decks = list_decks()
        print(f"\nRegistered decks ({len(decks)}):")
        for d in decks:
            print(f"  {d['id']:25s} {d['name']}")
            if d.get('commander'):
                print(f"  {'':25s} Commander: {d['commander']}")
        return

    if args.add_deck:
        deck_id, file_path = args.add_deck
        save_deck_file(file_path, deck_id)
        print(f"Deck '{deck_id}' registered.")
        return

    if args.prefetch:
        decks = list_decks()
        for d in decks:
            path = get_deck_path(d['id'])
            if path:
                prefetch_deck(path)
        return

    if args.mode is None:
        interactive_menu()
        return

    # Build configs from --decks flag
    decks = list_decks()
    deck_ids = args.decks or [d['id'] for d in decks[:4]]

    if len(deck_ids) < 4:
        deck_ids = (deck_ids * 4)[:4]

    configs = []
    for i, deck_id in enumerate(deck_ids[:4]):
        is_human = (args.mode == "human" and i == args.human_seat)
        p_name = "Human" if is_human else f"AI-{deck_id[:12]}"
        configs.append((p_name, deck_id, is_human))

    if args.mode == "sim":
        run_simulation(configs, num_games=args.games, max_turns=args.turns)
    else:
        run_game(configs, max_turns=args.turns, seed=args.seed)


if __name__ == "__main__":
    main()
