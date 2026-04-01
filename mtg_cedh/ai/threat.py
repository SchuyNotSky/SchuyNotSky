"""
ThreatAssessment — scores stack items and game states from a given player's perspective.

Used by the AI to make principled game-theory decisions about whether to pass
priority, respond with interaction, or let something resolve.

Scores are integers 0–100:
  0   = completely irrelevant
  30  = worth noting but not responding to
  50  = would respond if free (Force of Will, Fierce Guardianship)
  70  = respond with any counterspell we have
  85  = must respond — let this resolve and we almost certainly lose
  100 = instant loss if this resolves and we don't have a win response
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Dict, List

if TYPE_CHECKING:
    from ..engine.game import GameState
    from ..engine.zones import StackItem
    from ..engine.player import Player


# ---------------------------------------------------------------------------
# Threat category constants (usable in profiles for counter_threshold)
# ---------------------------------------------------------------------------
THREAT_IRRELEVANT    = 0
THREAT_LOW           = 20
THREAT_NOTABLE       = 35
THREAT_MEDIUM        = 50
THREAT_HIGH          = 70
THREAT_CRITICAL      = 85
THREAT_LETHAL        = 100


# ---------------------------------------------------------------------------
# Per-card threat tables
# ---------------------------------------------------------------------------

# Win conditions: resolving these directly ends the game for the controller
_WIN_CON_THREATS = {
    "thassa's oracle":         100,
    "thassa's oracle etb":     100,
    "demonic consultation":     90,   # sets up win on next action
    "tainted pact":             90,
    "ad nauseam":               80,   # huge card advantage, enables win same turn
    "underworld breach":        75,
    "flash":                    95,   # combo enabler, almost always kills
    "protean hulk":             85,
    "timetwister":              55,
    "windfall":                 40,
    "najeela, the blade-blossom": 65, # can activate for infinite combats
}

# Tutors: don't let opponents assemble their combo
_TUTOR_THREATS = {
    "demonic tutor":            72,
    "vampiric tutor":           70,
    "imperial seal":            68,
    "mystical tutor":           65,
    "merchant scroll":          60,
    "lim-dul's vault":          62,
    "gamble":                   55,
    "enlightened tutor":        58,
    "worldly tutor":            55,
    "sensei's divining top":    30,   # low urgency on its own
}

# Mass disruption: hurt everyone including us — worth countering for the table
_DISRUPTION_THREATS = {
    "cyclonic rift":            75,   # overloaded: wipes our board
    "toxic deluge":             65,
    "pernicious deed":          60,
    "chain of vapor":           45,
    "cyclonic rift (overload)": 80,
}

# Free/efficient spells opponents use to counter our stuff
_INTERACTION_THREATS = {
    "force of will":            40,
    "fierce guardianship":      40,
    "deflecting swat":          35,
    "pact of negation":         45,
    "mana drain":               45,
    "counterspell":             45,
    "flusterstorm":             35,
    "swan song":                35,
    "spell pierce":             30,
}

# Fast mana: if opponent gets ahead early it's dangerous
_MANA_THREATS = {
    "sol ring":     25,
    "mana crypt":   28,
    "mana vault":   25,
    "jeweled lotus": 35,  # free commander on turn 1 is threatening
    "dark ritual":  20,
    "cabal ritual": 22,
}


def _lookup_base_threat(spell_name: str) -> int:
    """Look up base threat score from all tables."""
    name = spell_name.lower()
    for table in [_WIN_CON_THREATS, _TUTOR_THREATS, _DISRUPTION_THREATS,
                  _INTERACTION_THREATS, _MANA_THREATS]:
        if name in table:
            return table[name]
    return THREAT_LOW  # default: anything on the stack is at least notable


# ---------------------------------------------------------------------------
# Context modifiers
# ---------------------------------------------------------------------------

def _context_multiplier(
    item: "StackItem",
    viewer: "Player",
    game: "GameState",
) -> float:
    """
    Apply context modifiers to the base threat score.
    Returns a float multiplier (0.5–2.0).
    """
    multiplier = 1.0
    controller_id = item.controller_id

    # Don't assess our own spells as threats to ourselves
    if controller_id == viewer.player_id:
        return 0.0

    name = (item.source.name if item.source else item.name).lower()

    # Consulting with Oracle in hand = certain kill unless countered
    if name == "demonic consultation" or name == "tainted pact":
        ctrl = game.get_player(controller_id)
        if ctrl:
            oracle_in_hand = any(c.name.lower() == "thassa's oracle"
                                 for c in ctrl.hand.cards())
            oracle_on_bf = game.battlefield.find_by_name(
                "Thassa's Oracle", controller_id) is not None
            if oracle_in_hand or oracle_on_bf:
                multiplier = 2.0  # bump to 100 effectively

    # Tutor is scarier if opponent already has combo pieces
    if name in _TUTOR_THREATS:
        ctrl = game.get_player(controller_id)
        if ctrl:
            oracle_held = any(c.name.lower() in ("thassa's oracle", "isochron scepter",
                                                   "dramatic reversal")
                              for c in ctrl.hand.cards())
            if oracle_held:
                multiplier = 1.4

    # Early turns: fast mana is more dangerous
    if name in _MANA_THREATS and game.turn_number <= 2:
        multiplier = 1.5

    # If we're ahead, less incentive to spend resources
    if viewer.life >= 35 and game.turn_number <= 3:
        multiplier *= 0.9

    # If we're behind (opponent near winning line), be more defensive
    ctrl = game.get_player(controller_id)
    if ctrl and ctrl.life <= 5:
        multiplier *= 1.3  # low-life opponent may be desperate combo attempt

    return multiplier


# ---------------------------------------------------------------------------
# Main threat assessment API
# ---------------------------------------------------------------------------

def assess_threat(
    item: "StackItem",
    viewer: "Player",
    game: "GameState",
    extra_context: Optional[Dict] = None,
) -> int:
    """
    Score how threatening a stack item is to `viewer`.
    Returns 0–100.
    """
    if item.controller_id == viewer.player_id:
        return 0  # our own spells are not a threat to us

    spell_name = item.source.name if item.source else item.name
    base = _lookup_base_threat(spell_name)
    mult = _context_multiplier(item, viewer, game)
    score = min(100, int(base * mult))
    return score


def assess_stack_threat(
    viewer: "Player",
    game: "GameState",
) -> int:
    """
    Return the maximum threat score of anything currently on the stack
    from viewer's perspective.
    """
    if game.stack.is_empty():
        return 0
    return max(assess_threat(item, viewer, game) for item in game.stack.items())


# ---------------------------------------------------------------------------
# Game theory: "should I pass or respond?"
# ---------------------------------------------------------------------------

class PriorityDecision:
    """
    Encapsulates the game-theory reasoning for a priority window.
    Attributes are set after `evaluate()` and can be inspected by
    the AI or audit trail.
    """

    def __init__(
        self,
        viewer: "Player",
        game: "GameState",
        stack_threat: int,
        has_counterspell: bool,
        has_free_counter: bool,
        owns_stack_top: bool,
    ):
        self.viewer = viewer
        self.game = game
        self.stack_threat = stack_threat
        self.has_counterspell = has_counterspell
        self.has_free_counter = has_free_counter
        self.owns_stack_top = owns_stack_top

        # Will be set by evaluate()
        self.should_respond: bool = False
        self.reason: str = ""

    def evaluate(
        self,
        counter_hard_threshold: int = THREAT_HIGH,
        counter_free_threshold: int = THREAT_MEDIUM,
    ) -> "PriorityDecision":
        """
        Decide whether to respond or pass.

        counter_hard_threshold: threat score at which we spend any resource to counter
        counter_free_threshold: threat score at which we'd use a free counter
        """
        if self.owns_stack_top:
            self.should_respond = False
            self.reason = "own spell on stack; pass to let it resolve"
            return self

        if self.game.split_second_active:
            self.should_respond = False
            self.reason = "split second active; cannot respond"
            return self

        if self.stack_threat >= THREAT_LETHAL:
            self.should_respond = True
            self.reason = f"lethal threat (score={self.stack_threat}); must counter"
            return self

        if self.stack_threat >= counter_hard_threshold and self.has_counterspell:
            self.should_respond = True
            self.reason = f"high threat (score={self.stack_threat}); using hard counter"
            return self

        if self.stack_threat >= counter_free_threshold and self.has_free_counter:
            self.should_respond = True
            self.reason = f"medium threat (score={self.stack_threat}); using free counter"
            return self

        self.should_respond = False
        self.reason = (
            f"threat={self.stack_threat} below thresholds "
            f"(hard={counter_hard_threshold}, free={counter_free_threshold}); passing"
        )
        return self


def evaluate_priority_window(
    viewer: "Player",
    game: "GameState",
    counter_hard_threshold: int = THREAT_HIGH,
    counter_free_threshold: int = THREAT_MEDIUM,
    has_counterspell: bool = False,
    has_free_counter: bool = False,
) -> PriorityDecision:
    """
    Full game-theory evaluation of a priority window.
    Returns a PriorityDecision object with `should_respond` and `reason`.
    """
    top = game.stack.peek()
    stack_threat = assess_threat(top, viewer, game) if top else 0
    owns_stack_top = (top is not None and top.controller_id == viewer.player_id)

    decision = PriorityDecision(
        viewer=viewer,
        game=game,
        stack_threat=stack_threat,
        has_counterspell=has_counterspell,
        has_free_counter=has_free_counter,
        owns_stack_top=owns_stack_top,
    )
    return decision.evaluate(counter_hard_threshold, counter_free_threshold)
