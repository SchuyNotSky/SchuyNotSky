"""
AuditLogger — attached to a GameState, records every event.

Usage:
    logger = AuditLogger(game_id="abc123", output_dir="game_logs/")
    game.audit = logger          # attach to game
    ...
    logger.save()                # write JSON + text report on completion
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .events import EventType, make_event

if TYPE_CHECKING:
    from ..engine.game import GameState

LOGS_DIR = Path(__file__).parent.parent.parent / "game_logs"


class AuditLogger:
    def __init__(
        self,
        game_id: Optional[str] = None,
        output_dir: Optional[Path | str] = None,
        verbose: bool = False,
    ):
        self.game_id = game_id or str(uuid.uuid4())[:12]
        self.output_dir = Path(output_dir) if output_dir else LOGS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose

        self.events: List[Dict] = []
        self.metadata: Dict[str, Any] = {
            "game_id": self.game_id,
            "created_at": datetime.now().isoformat(),
            "players": [],
            "commanders": {},
            "seed": None,
            "result": {},
        }
        # Life total snapshots per turn: {turn: {player_id: life}}
        self._life_history: Dict[int, Dict[str, int]] = {}
        # Hand size per turn
        self._hand_history: Dict[int, Dict[str, int]] = {}
        # Current turn/phase cache (updated by game hooks)
        self._current_turn = 0
        self._current_phase = "SETUP"

    # ------------------------------------------------------------------
    # Core event recording
    # ------------------------------------------------------------------

    def record(self, event_type: EventType, player_id: Optional[str] = None,
               player_name: Optional[str] = None, **kwargs) -> Dict:
        event = make_event(
            event_type,
            turn=self._current_turn,
            phase=self._current_phase,
            player_id=player_id,
            player_name=player_name,
            **kwargs,
        )
        self.events.append(event)
        if self.verbose:
            self._print_event(event)
        return event

    # ------------------------------------------------------------------
    # Convenience recorders (called from game.py hooks)
    # ------------------------------------------------------------------

    def game_start(self, players: list, commanders: Optional[Dict] = None, seed: Optional[int] = None):
        """
        players: list of dicts with keys id, name, is_human
        commanders: {player_id: [card_name, ...]}
        """
        self.metadata["players"] = players
        self.metadata["commanders"] = commanders or {}
        self.record(EventType.GAME_START,
                    players=[p["name"] for p in players],
                    commanders=commanders or {})

    def game_end(self, winner_name: Optional[str], winner_id: Optional[str],
                 win_condition: str, total_turns: int):
        self.metadata["result"] = {
            "winner": winner_name,
            "winner_id": winner_id,
            "win_condition": win_condition,
            "total_turns": total_turns,
            "ended_at": datetime.now().isoformat(),
        }
        # Top-level aliases used by analysis/report.py
        self.metadata["winner_name"] = winner_name
        self.metadata["win_condition"] = win_condition
        self.metadata["total_turns"] = total_turns
        self.record(EventType.GAME_END, winner=winner_name,
                    win_condition=win_condition, total_turns=total_turns)

    def opening_hand(self, player_id: str, player_name: str, cards: list):
        """cards: list of card name strings."""
        self.record(EventType.OPENING_HAND, player_id=player_id,
                    player_name=player_name,
                    cards=cards,
                    count=len(cards))

    def turn_start(self, turn: int, player_id: str, player_name: str,
                   life_totals: Dict[str, int], hand_sizes: Dict[str, int]):
        self._current_turn = turn
        self._current_phase = "UNTAP"
        self._life_history[turn] = dict(life_totals)
        self._hand_history[turn] = dict(hand_sizes)
        self.record(EventType.TURN_START, player_id=player_id,
                    player_name=player_name,
                    life_totals=life_totals,
                    hand_sizes=hand_sizes)

    def phase_start(self, phase: str, player_id: str):
        self._current_phase = phase
        self.record(EventType.PHASE_START, player_id=player_id, phase_name=phase)

    def spell_cast(self, player_id: str, player_name: str, card_name: str,
                   mana_cost: str, cmc: int, card_types: list,
                   targets: Optional[list] = None, x_value: int = 0):
        self.record(EventType.SPELL_CAST, player_id=player_id,
                    player_name=player_name, card_name=card_name,
                    mana_cost=mana_cost, cmc=cmc, card_types=card_types,
                    targets=targets or [], x_value=x_value)

    def spell_resolve(self, card_name: str, controller_id: str, controller_name: str):
        self.record(EventType.SPELL_RESOLVE, player_id=controller_id,
                    player_name=controller_name, card_name=card_name)

    def spell_countered(self, card_name: str, controller_id: str,
                        countered_by: str, countered_by_player: str):
        self.record(EventType.SPELL_COUNTERED, player_id=controller_id,
                    card_name=card_name, countered_by_spell=countered_by,
                    countered_by_player=countered_by_player)

    def land_played(self, player_id: str, player_name: str, land_name: str,
                    card_types: Optional[list] = None):
        self.record(EventType.LAND_PLAYED, player_id=player_id,
                    player_name=player_name, card_name=land_name,
                    card_types=card_types or [])

    def card_drawn(self, player_id: str, player_name: str,
                   card_name: str, source: str = "draw step"):
        self.record(EventType.CARD_DRAWN, player_id=player_id,
                    player_name=player_name, card_name=card_name, source=source)

    def cards_drawn_bulk(self, player_id: str, player_name: str,
                         cards: list, source: str):
        for c in cards:
            self.card_drawn(player_id, player_name, c.name, source=source)

    def card_discarded(self, player_id: str, player_name: str,
                       card_name: str, reason: str = "hand size"):
        self.record(EventType.CARD_DISCARDED, player_id=player_id,
                    player_name=player_name, card_name=card_name, reason=reason)

    def life_change(self, player_id: str, player_name: str,
                    old_life: int, new_life: int, source: str, is_damage: bool = False):
        delta = new_life - old_life
        etype = EventType.DAMAGE_DEALT if is_damage and delta < 0 else (
            EventType.LIFE_LOST if delta < 0 else EventType.LIFE_GAINED
        )
        self.record(etype, player_id=player_id, player_name=player_name,
                    old_life=old_life, new_life=new_life,
                    delta=delta, source=source)

    def permanent_etb(self, player_id: str, player_name: str, card_name: str,
                      card_types: list):
        self.record(EventType.PERMANENT_ETB, player_id=player_id,
                    player_name=player_name, card_name=card_name,
                    card_types=card_types)

    def permanent_dies(self, player_id: str, player_name: str,
                       card_name: str, reason: str = "state-based"):
        self.record(EventType.PERMANENT_DIES, player_id=player_id,
                    player_name=player_name, card_name=card_name, reason=reason)

    def attackers_declared(self, player_id: str, player_name: str,
                           attacks: list):
        """attacks: list of {attacker, defending_player}"""
        self.record(EventType.ATTACKERS_DECLARED, player_id=player_id,
                    player_name=player_name, attacks=attacks)

    def blockers_declared(self, player_id: str, player_name: str,
                          blocks: list):
        self.record(EventType.BLOCKERS_DECLARED, player_id=player_id,
                    player_name=player_name, blocks=blocks)

    def combat_damage(self, attacker: str, attacker_player: str,
                      defender: str, defender_player: str,
                      damage: int, is_commander: bool = False):
        self.record(EventType.COMBAT_DAMAGE,
                    player_id=attacker_player,
                    attacker=attacker, attacker_player=attacker_player,
                    defender=defender, defender_player=defender_player,
                    damage=damage, is_commander=is_commander)

    def tutor_decision(self, player_id: str, player_name: str,
                       spell_name: str, chosen_card: str,
                       candidates: list, reason: str):
        self.record(EventType.AI_TUTOR_CHOICE, player_id=player_id,
                    player_name=player_name, tutor_spell=spell_name,
                    chosen=chosen_card, candidates=candidates, reason=reason)

    def ai_decision(self, player_id: str, player_name: str,
                    action: str, card_name: str,
                    score: Optional[int] = None,
                    alternatives: Optional[list] = None,
                    reasoning: str = ""):
        self.record(EventType.AI_DECISION, player_id=player_id,
                    player_name=player_name, action=action,
                    card_name=card_name, score=score,
                    alternatives=alternatives or [],
                    reasoning=reasoning)

    def ai_counter_eval(self, player_id: str, player_name: str,
                        target_spell: str, decision: str, reason: str):
        self.record(EventType.AI_COUNTER_EVAL, player_id=player_id,
                    player_name=player_name, target_spell=target_spell,
                    decision=decision, reason=reason)

    def priority_pass(self, player_id: str, player_name: str):
        self.record(EventType.AI_PASS_PRIORITY, player_id=player_id,
                    player_name=player_name)

    def win_condition(self, player_id: str, player_name: str,
                      condition: str, turn: Optional[int] = None,
                      phase: Optional[str] = None, details: str = ""):
        self.record(EventType.WIN_CONDITION, player_id=player_id,
                    player_name=player_name, condition=condition, details=details)

    def player_lost(self, player_id: str, player_name: str, reason: str,
                    turn: Optional[int] = None, phase: Optional[str] = None):
        self.record(EventType.PLAYER_LOST, player_id=player_id,
                    player_name=player_name, reason=reason)

    def library_exiled(self, player_id: str, player_name: str,
                       count: int, source: str):
        self.record(EventType.LIBRARY_EXILED, player_id=player_id,
                    player_name=player_name, count=count, source=source)

    # ------------------------------------------------------------------
    # Save to disk
    # ------------------------------------------------------------------

    def save(self, game: Optional["GameState"] = None) -> Path:
        """Write full JSON log and human-readable text report."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = self.output_dir / f"game_{self.game_id}_{ts}"

        # Build final payload
        payload = {
            "metadata": self.metadata,
            "life_history": self._life_history,
            "hand_history": self._hand_history,
            "events": self.events,
            "summary": self._build_summary(),
        }

        # JSON log
        json_path = base.with_suffix(".json")
        json_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Human-readable text report
        txt_path = base.with_suffix(".txt")
        txt_path.write_text(self._build_text_report(payload), encoding="utf-8")

        print(f"\n[Audit] Game log saved:")
        print(f"  JSON → {json_path}")
        print(f"  Text → {txt_path}")
        return json_path

    # ------------------------------------------------------------------
    # Summary and report builders
    # ------------------------------------------------------------------

    def _build_summary(self) -> Dict:
        """Aggregate key stats from events."""
        spells_cast: Dict[str, Dict[str, int]] = {}  # player_id → {card: count}
        counters_by: Dict[str, int] = {}
        life_swings: Dict[str, int] = {}  # player_id → total damage taken
        tutors: Dict[str, List] = {}
        win_cond = None

        for ev in self.events:
            pid = ev.get("player_id", "?")
            etype = ev.get("type")

            if etype == EventType.SPELL_CAST:
                spells_cast.setdefault(pid, {})
                cn = ev.get("card_name", "?")
                spells_cast[pid][cn] = spells_cast[pid].get(cn, 0) + 1

            elif etype == EventType.SPELL_COUNTERED:
                cb = ev.get("countered_by_player", "?")
                counters_by[cb] = counters_by.get(cb, 0) + 1

            elif etype in (EventType.DAMAGE_DEALT, EventType.LIFE_LOST):
                delta = abs(ev.get("delta", 0))
                life_swings[pid] = life_swings.get(pid, 0) + delta

            elif etype == EventType.AI_TUTOR_CHOICE:
                tutors.setdefault(pid, []).append({
                    "turn": ev.get("turn"),
                    "tutor": ev.get("tutor_spell"),
                    "fetched": ev.get("chosen"),
                    "reason": ev.get("reason", ""),
                })

            elif etype == EventType.WIN_CONDITION:
                win_cond = {
                    "player": ev.get("player_name"),
                    "condition": ev.get("condition"),
                    "turn": ev.get("turn"),
                    "details": ev.get("details", ""),
                }

        return {
            "win_condition": win_cond,
            "spells_cast_by_player": spells_cast,
            "counterspells_used": counters_by,
            "total_damage_taken": life_swings,
            "tutor_decisions": tutors,
            "total_events": len(self.events),
        }

    def _build_text_report(self, payload: Dict) -> str:
        lines = []
        meta = payload["metadata"]
        summary = payload["summary"]

        lines.append("=" * 70)
        lines.append(f"  MTG cEDH Game Audit Report")
        lines.append(f"  Game ID : {meta['game_id']}")
        lines.append(f"  Date    : {meta['created_at'][:19]}")
        lines.append(f"  Seed    : {meta.get('seed', 'N/A')}")
        lines.append("=" * 70)

        # Players
        lines.append("\nPLAYERS")
        lines.append("-" * 40)
        for p in meta.get("players", []):
            role = "Human" if p.get("is_human") else "AI"
            lines.append(f"  {p['name']:25s} [{role}]  ({p['id']})")

        # Result
        result = meta.get("result", {})
        lines.append("\nRESULT")
        lines.append("-" * 40)
        if result.get("winner"):
            lines.append(f"  Winner       : {result['winner']}")
            lines.append(f"  Win condition: {result.get('win_condition', '?')}")
            lines.append(f"  Total turns  : {result.get('total_turns', '?')}")
        else:
            lines.append("  No winner (draw / timeout)")

        # Win condition detail
        wc = summary.get("win_condition")
        if wc:
            lines.append(f"\n  {wc['player']} won on turn {wc['turn']} via {wc['condition']}")
            if wc.get("details"):
                lines.append(f"  Detail: {wc['details']}")

        # Life history
        lines.append("\nLIFE TOTALS BY TURN")
        lines.append("-" * 40)
        life_hist = payload.get("life_history", {})
        player_names = {p["id"]: p["name"] for p in meta.get("players", [])}
        turns_list = sorted(life_hist.keys(), key=int)
        if turns_list:
            header = f"  {'Turn':>5}  " + "  ".join(
                f"{player_names.get(pid, pid):>12}" for pid in sorted(life_hist[turns_list[0]])
            )
            lines.append(header)
            for t in turns_list:
                row = f"  {t:>5}  " + "  ".join(
                    f"{life_hist[t].get(pid, '?'):>12}"
                    for pid in sorted(life_hist[turns_list[0]])
                )
                lines.append(row)

        # Spells cast
        lines.append("\nSPELLS CAST")
        lines.append("-" * 40)
        for pid, spells in summary.get("spells_cast_by_player", {}).items():
            pname = player_names.get(pid, pid)
            total = sum(spells.values())
            lines.append(f"  {pname} ({total} total):")
            for card, cnt in sorted(spells.items(), key=lambda x: -x[1]):
                lines.append(f"    {cnt:>3}x  {card}")

        # Counterspells
        counters = summary.get("counterspells_used", {})
        if counters:
            lines.append("\nCOUNTERSPELLS USED")
            lines.append("-" * 40)
            for pid, cnt in sorted(counters.items(), key=lambda x: -x[1]):
                pname = player_names.get(pid, pid)
                lines.append(f"  {pname:25s} {cnt} counter(s)")

        # Tutor decisions
        tutors = summary.get("tutor_decisions", {})
        if tutors:
            lines.append("\nTUTOR DECISIONS")
            lines.append("-" * 40)
            for pid, decisions in tutors.items():
                pname = player_names.get(pid, pid)
                lines.append(f"  {pname}:")
                for d in decisions:
                    lines.append(
                        f"    Turn {d['turn']:>2}: {d['tutor']:30s} → fetched {d['fetched']}"
                        + (f"  [{d['reason']}]" if d.get("reason") else "")
                    )

        # Turn-by-turn event digest
        lines.append("\nTURN-BY-TURN DIGEST")
        lines.append("-" * 40)
        current_turn = None
        for ev in payload["events"]:
            t = ev.get("turn", 0)
            etype = ev.get("type", "")
            pname = ev.get("player_name", ev.get("player_id", "?"))

            if t != current_turn:
                current_turn = t
                lines.append(f"\n  --- Turn {t} ---")

            line = _format_event_line(ev, player_names)
            if line:
                lines.append(f"    {line}")

        lines.append("\n" + "=" * 70)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Verbose print
    # ------------------------------------------------------------------

    def _print_event(self, event: Dict):
        line = _format_event_line(event, {})
        if line:
            print(f"  [AUDIT T{event.get('turn',0)}] {line}")


def _format_event_line(ev: Dict, player_names: Dict) -> str:
    """Format a single event as a readable line."""
    etype = ev.get("type", "")
    pname = ev.get("player_name") or player_names.get(ev.get("player_id", ""), ev.get("player_id", "?"))

    if etype == EventType.SPELL_CAST:
        targets = ev.get("targets", [])
        t_str = f" → {targets}" if targets else ""
        return f"{pname} casts {ev['card_name']} [{ev.get('mana_cost','')}]{t_str}"
    elif etype == EventType.SPELL_COUNTERED:
        return f"{ev['card_name']} countered by {ev.get('countered_by_spell','?')} ({ev.get('countered_by_player','?')})"
    elif etype == EventType.SPELL_RESOLVE:
        return f"{ev['card_name']} resolves"
    elif etype == EventType.LAND_PLAYED:
        return f"{pname} plays {ev['card_name']}"
    elif etype == EventType.CARD_DRAWN:
        return f"{pname} draws {ev['card_name']} ({ev.get('source','')})"
    elif etype == EventType.CARD_DISCARDED:
        return f"{pname} discards {ev['card_name']} ({ev.get('reason','')})"
    elif etype == EventType.PERMANENT_ETB:
        return f"{ev['card_name']} enters the battlefield under {pname}'s control"
    elif etype == EventType.PERMANENT_DIES:
        return f"{ev['card_name']} dies ({ev.get('reason','')})"
    elif etype == EventType.DAMAGE_DEALT:
        return f"{pname} takes {abs(ev.get('delta',0))} damage from {ev.get('source','?')} ({ev.get('old_life','?')} → {ev.get('new_life','?')} life)"
    elif etype == EventType.LIFE_LOST:
        return f"{pname} loses {abs(ev.get('delta',0))} life ({ev.get('old_life','?')} → {ev.get('new_life','?')})"
    elif etype == EventType.LIFE_GAINED:
        return f"{pname} gains {ev.get('delta',0)} life ({ev.get('old_life','?')} → {ev.get('new_life','?')})"
    elif etype == EventType.ATTACKERS_DECLARED:
        attacks = ev.get("attacks", [])
        if attacks:
            return f"{pname} attacks: {attacks}"
    elif etype == EventType.AI_TUTOR_CHOICE:
        return f"[AI] {pname} tutors {ev.get('tutor_spell','?')} → fetches {ev.get('chosen','?')} | reason: {ev.get('reason','')}"
    elif etype == EventType.AI_DECISION:
        return f"[AI] {pname} {ev.get('action','?')} {ev.get('card_name','?')} (score={ev.get('score','?')}) | {ev.get('reasoning','')}"
    elif etype == EventType.WIN_CONDITION:
        return f"*** {pname} WINS via {ev.get('condition','?')} — {ev.get('details','')} ***"
    elif etype == EventType.PLAYER_LOST:
        return f"*** {pname} loses — {ev.get('reason','?')} ***"
    elif etype == EventType.LIBRARY_EXILED:
        return f"{pname}'s library exiled ({ev.get('count',0)} cards) by {ev.get('source','?')}"
    elif etype == EventType.TURN_START:
        totals = ev.get("life_totals", {})
        total_str = " | ".join(f"{player_names.get(k,k)}: {v}" for k, v in totals.items())
        return f"Turn {ev.get('turn')} begins — {pname} active | Life: {total_str}"
    return ""
