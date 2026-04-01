"""
Cross-game analysis: aggregate statistics from multiple game audit logs.

Usage:
    from mtg_cedh.analysis.report import GameReport, load_game_logs, print_report
    logs = load_game_logs("game_logs/")
    report = GameReport(logs)
    print_report(report)

Or from CLI:
    python -m mtg_cedh.analysis.report game_logs/
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Log loading
# ---------------------------------------------------------------------------

def load_game_logs(log_dir: str) -> List[Dict]:
    """
    Load all JSON audit logs from a directory.
    Returns a list of game summary dicts (the 'summary' key from each log).
    """
    log_dir_path = Path(log_dir)
    summaries = []
    for f in sorted(log_dir_path.glob("game_*.json")):
        try:
            data = json.loads(f.read_text())
            summaries.append(data)
        except Exception as e:
            print(f"  [warn] Could not parse {f.name}: {e}")
    return summaries


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

class GameReport:
    """Aggregate statistics across multiple game audit logs."""

    def __init__(self, game_logs: List[Dict]):
        self.logs = game_logs
        self.num_games = len(game_logs)

        # Aggregated counters
        self.wins_by_player: Counter = Counter()            # player_name → win count
        self.wins_by_condition: Counter = Counter()         # win_condition → count
        self.win_turns: List[int] = []                      # turn numbers when game ended
        self.spells_by_player: Counter = Counter()          # player_name → total spells cast
        self.counterspells_by_player: Counter = Counter()   # player_name → total counters used
        self.most_countered_spells: Counter = Counter()     # spell_name → times countered
        self.tutor_targets: Counter = Counter()             # tutor_target → times chosen
        self.draws: int = 0                                 # games with no winner
        self.total_damage_by_player: Counter = Counter()    # player_name → total damage taken

        self._aggregate()

    def _aggregate(self):
        for log in self.logs:
            meta = log.get("metadata", {})
            summary = log.get("summary", {})
            events = log.get("events", [])

            winner = meta.get("winner_name")
            if winner:
                self.wins_by_player[winner] += 1
                self.wins_by_condition[meta.get("win_condition", "unknown")] += 1
            else:
                self.draws += 1

            turns = meta.get("total_turns", 0)
            if turns:
                self.win_turns.append(turns)

            # Spells cast per player {player_id: {card_name: count}}
            # Flatten to {player_id: total_count} for cross-game aggregation
            for pid, card_counts in summary.get("spells_cast_by_player", {}).items():
                if isinstance(card_counts, dict):
                    self.spells_by_player[pid] += sum(card_counts.values())
                else:
                    self.spells_by_player[pid] += int(card_counts)

            # Counterspells
            for pid, count in summary.get("counterspells_used", {}).items():
                self.counterspells_by_player[pid] += count

            # Damage taken
            for pid, dmg in summary.get("total_damage_taken", {}).items():
                self.total_damage_by_player[pid] += dmg

            # Tutor decisions (dict: {player_id: [{turn, tutor, fetched, reason}, ...]})
            tutor_data = summary.get("tutor_decisions", {})
            if isinstance(tutor_data, dict):
                all_decisions = [d for dlist in tutor_data.values() for d in dlist]
            else:
                all_decisions = tutor_data  # flat list fallback
            for td in all_decisions:
                target = td.get("fetched") or td.get("chosen") or td.get("target")
                if target:
                    self.tutor_targets[target] += 1

            # Most countered spells (scan events)
            for ev in events:
                if ev.get("type") == "SPELL_COUNTERED":
                    spell = ev.get("spell_name", "unknown")
                    self.most_countered_spells[spell] += 1

    # Derived stats
    def win_rate(self, player_name: str) -> float:
        if self.num_games == 0:
            return 0.0
        return self.wins_by_player[player_name] / self.num_games

    def avg_win_turn(self) -> float:
        if not self.win_turns:
            return 0.0
        return sum(self.win_turns) / len(self.win_turns)

    def all_players(self) -> List[str]:
        """Collect all player names seen across games."""
        players = set()
        for log in self.logs:
            for p in log.get("metadata", {}).get("players", []):
                players.add(p.get("name", "?"))
        return sorted(players)


# ---------------------------------------------------------------------------
# Text report
# ---------------------------------------------------------------------------

def print_report(report: GameReport, file=None):
    """Print a formatted multi-game analysis report."""
    out = file or sys.stdout

    def w(line=""):
        print(line, file=out)

    w("=" * 60)
    w("  MTG cEDH SIMULATOR — CROSS-GAME ANALYSIS")
    w("=" * 60)
    w(f"  Games analyzed : {report.num_games}")
    w(f"  Draws/Timeouts : {report.draws}")
    w(f"  Avg game length: {report.avg_win_turn():.1f} turns")
    w()

    # Win rates
    w("  WIN RATES")
    w("  " + "-" * 40)
    players = report.all_players()
    total_wins = sum(report.wins_by_player.values())
    for name in sorted(players, key=lambda n: -report.wins_by_player[n]):
        wins = report.wins_by_player[name]
        pct = report.win_rate(name) * 100
        bar_len = int(pct / 2)
        w(f"  {name:25s}  {wins:3d} wins  {pct:5.1f}%  {'█'*bar_len}")
    w()

    # Win conditions
    if report.wins_by_condition:
        w("  WIN CONDITIONS")
        w("  " + "-" * 40)
        for cond, cnt in report.wins_by_condition.most_common():
            w(f"  {cond:30s}  {cnt:3d} ({cnt/max(total_wins,1)*100:.1f}%)")
        w()

    # Spells cast
    if report.spells_by_player:
        w("  TOTAL SPELLS CAST (across all games)")
        w("  " + "-" * 40)
        for name, cnt in report.spells_by_player.most_common():
            avg = cnt / max(report.num_games, 1)
            w(f"  {name:25s}  {cnt:4d} total  ({avg:.1f}/game)")
        w()

    # Counterspells
    if report.counterspells_by_player:
        w("  COUNTERSPELLS USED")
        w("  " + "-" * 40)
        for name, cnt in report.counterspells_by_player.most_common():
            avg = cnt / max(report.num_games, 1)
            w(f"  {name:25s}  {cnt:4d} total  ({avg:.1f}/game)")
        w()

    # Most countered spells
    if report.most_countered_spells:
        w("  MOST COUNTERED SPELLS (top 10)")
        w("  " + "-" * 40)
        for spell, cnt in report.most_countered_spells.most_common(10):
            w(f"  {spell:35s}  {cnt:3d}x")
        w()

    # Top tutor targets
    if report.tutor_targets:
        w("  TOP TUTOR TARGETS (top 10)")
        w("  " + "-" * 40)
        for target, cnt in report.tutor_targets.most_common(10):
            w(f"  {target:35s}  {cnt:3d}x")
        w()

    # Damage taken
    if report.total_damage_by_player:
        w("  TOTAL DAMAGE TAKEN")
        w("  " + "-" * 40)
        for name, dmg in report.total_damage_by_player.most_common():
            avg = dmg / max(report.num_games, 1)
            w(f"  {name:25s}  {dmg:5d} total  ({avg:.1f}/game)")
        w()

    w("=" * 60)


def save_report(report: GameReport, output_path: str):
    """Save the text report to a file."""
    with open(output_path, "w") as f:
        print_report(report, file=f)
    print(f"  Report saved to: {output_path}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Aggregate MTG cEDH audit logs")
    parser.add_argument("log_dir", nargs="?", default="game_logs",
                        help="Directory containing game_*.json logs (default: game_logs)")
    parser.add_argument("--output", "-o", metavar="FILE",
                        help="Save text report to FILE")
    args = parser.parse_args()

    logs = load_game_logs(args.log_dir)
    if not logs:
        print(f"  No game logs found in '{args.log_dir}'.")
        sys.exit(1)

    report = GameReport(logs)
    print_report(report)

    if args.output:
        save_report(report, args.output)


if __name__ == "__main__":
    main()
