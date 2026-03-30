"""
Mana system: colors, costs, pools, and payment logic.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Color(Enum):
    WHITE = "W"
    BLUE = "U"
    BLACK = "B"
    RED = "R"
    GREEN = "G"
    COLORLESS = "C"  # true colorless (Wastes, etc.)
    GENERIC = "X"    # generic/any mana in costs (not stored in pool)


# Color identity shorthand for parsing
COLOR_MAP = {c.value: c for c in Color if c != Color.GENERIC}


@dataclass
class ManaCost:
    """
    Represents a mana cost, e.g. {2}{U}{B}.
    generic: amount of any-color mana required
    pips: dict of Color -> count for colored pips
    phyrexian: dict of Color -> count for phyrexian pips (pay 2 life instead)
    hybrid: list of frozenset pairs (e.g. {W/U})
    x_count: number of X in the cost (variable generic)
    """
    generic: int = 0
    pips: Dict[Color, int] = field(default_factory=dict)
    phyrexian: Dict[Color, int] = field(default_factory=dict)
    hybrid: List[frozenset] = field(default_factory=list)
    x_count: int = 0

    @classmethod
    def free(cls) -> "ManaCost":
        return cls()

    @classmethod
    def parse(cls, cost_str: str) -> "ManaCost":
        """
        Parse a cost string like '{2}{U}{B}', '1UB', '{W/U}', '{X}{R}'.
        Handles: generic numerals, color pips, hybrid (W/U), phyrexian (W/P),
        colorless {C}, X.
        """
        if not cost_str or cost_str in ("0", "{0}"):
            return cls()
        cost = cls()
        # Normalize: remove outer braces then split tokens
        tokens = []
        s = cost_str.strip()
        if "{" in s:
            # tokenize by braces
            import re
            tokens = re.findall(r"\{([^}]+)\}", s)
            # Also handle bare numerals before first brace
            prefix = s.split("{")[0]
            if prefix.isdigit():
                cost.generic += int(prefix)
        else:
            # bare format: e.g. "2UB" or "WW"
            import re
            for tok in re.findall(r"([0-9]+|[WUBRGCX])", s.upper()):
                tokens.append(tok)

        for tok in tokens:
            tok = tok.upper()
            if tok.isdigit():
                cost.generic += int(tok)
            elif tok == "X":
                cost.x_count += 1
            elif "/" in tok:
                parts = tok.split("/")
                if parts[1] == "P":
                    # Phyrexian
                    c = COLOR_MAP.get(parts[0])
                    if c:
                        cost.phyrexian[c] = cost.phyrexian.get(c, 0) + 1
                else:
                    # Hybrid
                    pair = frozenset(COLOR_MAP[p] for p in parts if p in COLOR_MAP)
                    cost.hybrid.append(pair)
            elif tok in COLOR_MAP:
                c = COLOR_MAP[tok]
                cost.pips[c] = cost.pips.get(c, 0) + 1

        return cost

    @property
    def cmc(self) -> int:
        """Converted mana cost (ignores X)."""
        return (
            self.generic
            + sum(self.pips.values())
            + sum(self.phyrexian.values())
            + len(self.hybrid)
        )

    @property
    def color_identity(self) -> frozenset:
        colors: set = set(self.pips.keys())
        for pair in self.hybrid:
            colors |= pair
        colors.discard(Color.COLORLESS)
        return frozenset(colors)

    def __str__(self) -> str:
        parts = []
        if self.x_count:
            parts.append("{X}" * self.x_count)
        if self.generic:
            parts.append(f"{{{self.generic}}}")
        for c, n in self.pips.items():
            parts.append(f"{{{c.value}}}" * n)
        for pair in self.hybrid:
            vals = "/".join(c.value for c in pair)
            parts.append(f"{{{vals}}}")
        for c, n in self.phyrexian.items():
            parts.append(f"{{{c.value}/P}}" * n)
        return "".join(parts) or "{0}"


@dataclass
class ManaPool:
    """A player's current mana pool."""
    pool: Dict[Color, int] = field(default_factory=lambda: {c: 0 for c in Color if c != Color.GENERIC})

    def add(self, color: Color, amount: int = 1):
        if color == Color.GENERIC:
            color = Color.COLORLESS
        self.pool[color] = self.pool.get(color, 0) + amount

    def add_any(self, amount: int):
        """Add generic (any) mana as colorless for now; AI will assign colors."""
        self.pool[Color.COLORLESS] = self.pool.get(Color.COLORLESS, 0) + amount

    def total(self) -> int:
        return sum(self.pool.values())

    def colored_total(self) -> int:
        return sum(v for c, v in self.pool.items() if c not in (Color.COLORLESS, Color.GENERIC))

    def empty(self):
        for c in self.pool:
            self.pool[c] = 0

    def can_pay(self, cost: ManaCost, x_value: int = 0) -> bool:
        """Check if this pool can pay the given cost."""
        available = dict(self.pool)
        total_available = sum(available.values())
        needed_generic = cost.generic + x_value

        # Pay colored pips first
        for color, count in cost.pips.items():
            have = available.get(color, 0)
            if have < count:
                return False
            available[color] -= count
            total_available -= count

        # Pay hybrid pips (pick cheaper option)
        for pair in cost.hybrid:
            paid = False
            for color in pair:
                if available.get(color, 0) >= 1:
                    available[color] -= 1
                    total_available -= 1
                    paid = True
                    break
            if not paid:
                if total_available >= 1:
                    # pay with any
                    for c in available:
                        if available[c] > 0:
                            available[c] -= 1
                            total_available -= 1
                            break
                else:
                    return False

        # Pay phyrexian (assume paying mana, not life, for simplicity)
        for color, count in cost.phyrexian.items():
            have = available.get(color, 0)
            if have < count:
                return False
            available[color] -= count
            total_available -= count

        # Pay generic with remaining mana
        return total_available >= needed_generic

    def pay(self, cost: ManaCost, x_value: int = 0) -> bool:
        """Attempt to pay cost from pool. Returns True if successful."""
        if not self.can_pay(cost, x_value):
            return False
        needed_generic = cost.generic + x_value

        # Pay colored pips
        for color, count in cost.pips.items():
            self.pool[color] -= count

        # Pay hybrid (greedy: prefer the color with most)
        for pair in cost.hybrid:
            best = max(pair, key=lambda c: self.pool.get(c, 0))
            self.pool[best] -= 1

        # Pay phyrexian
        for color, count in cost.phyrexian.items():
            self.pool[color] -= count

        # Pay generic: drain colorless first, then colored
        for color in [Color.COLORLESS] + [c for c in Color if c not in (Color.COLORLESS, Color.GENERIC)]:
            if needed_generic <= 0:
                break
            drain = min(self.pool.get(color, 0), needed_generic)
            self.pool[color] -= drain
            needed_generic -= drain

        return True

    def __repr__(self) -> str:
        parts = [f"{c.value}:{v}" for c, v in self.pool.items() if v > 0]
        return f"ManaPool({', '.join(parts) or 'empty'})"
