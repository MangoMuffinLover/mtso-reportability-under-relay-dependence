#!/usr/bin/env python3
"""Exact finite-state pilot for MTSO-style reported coverage.

The pilot separates two cases:

1. A shared exogenous hazard jointly determines each route's reportable set,
   but that set does not depend on which other routes are selected.
2. A route's reportability depends on whether another selected route provides
   a relay, creating selection-dependent complementarity.

All expectations are evaluated exactly with rational arithmetic.  The script
enumerates every route subset and every diminishing-returns inequality.
"""

from __future__ import annotations

from fractions import Fraction
from itertools import combinations
import json


ROUTES = ("A", "B", "C", "D")


def powerset(items):
    for size in range(len(items) + 1):
        for subset in combinations(items, size):
            yield frozenset(subset)


SUBSETS = tuple(powerset(ROUTES))


# One shared hazard state is sampled for the whole team.  Outcomes are therefore
# correlated across routes, while each route's reportable set remains fixed once
# the state is known.
EXOGENOUS_STATES = {
    "clear": {
        "prob": Fraction(1, 2),
        "sets": {
            "A": {"t1", "t2"},
            "B": {"t2", "t3"},
            "C": {"t3", "t4"},
            "D": {"t1", "t4"},
        },
    },
    "west_blackout": {
        "prob": Fraction(1, 5),
        "sets": {
            "A": set(),
            "B": {"t3"},
            "C": {"t3", "t4"},
            "D": {"t4"},
        },
    },
    "east_blackout": {
        "prob": Fraction(1, 5),
        "sets": {
            "A": {"t1", "t2"},
            "B": {"t2"},
            "C": set(),
            "D": {"t1"},
        },
    },
    "global_blackout": {
        "prob": Fraction(1, 10),
        "sets": {route: set() for route in ROUTES},
    },
}


def expected_exogenous_coverage(selected):
    total = Fraction(0)
    for state in EXOGENOUS_STATES.values():
        covered = set()
        for route in selected:
            covered |= state["sets"][route]
        total += state["prob"] * len(covered)
    return total


def relay_delivered_coverage(selected):
    """Selection-dependent delivery with B acting as a relay.

    A locally detects t1 but needs B to deliver it.  D locally detects t3 and
    also needs B.  C self-delivers t2.  B alone delivers no target report.
    """

    delivered = set()
    if "C" in selected:
        delivered.add("t2")
    if {"A", "B"}.issubset(selected):
        delivered.add("t1")
    if {"D", "B"}.issubset(selected):
        delivered.add("t3")
    return Fraction(len(delivered))


def diminishing_returns_audit(value_fn):
    violations = []
    minimum_slack = None
    checked = 0
    for small in SUBSETS:
        for large in SUBSETS:
            if not small.issubset(large):
                continue
            for element in ROUTES:
                if element in large:
                    continue
                small_gain = value_fn(small | {element}) - value_fn(small)
                large_gain = value_fn(large | {element}) - value_fn(large)
                slack = small_gain - large_gain
                checked += 1
                minimum_slack = slack if minimum_slack is None else min(minimum_slack, slack)
                if slack < 0:
                    violations.append(
                        {
                            "small": sorted(small),
                            "large": sorted(large),
                            "element": element,
                            "gain_from_small": str(small_gain),
                            "gain_from_large": str(large_gain),
                            "slack": str(slack),
                        }
                    )
    return {
        "inequalities_checked": checked,
        "minimum_slack": str(minimum_slack),
        "violation_count": len(violations),
        "violations": violations,
    }


def value_table(value_fn):
    return {
        "{" + ",".join(sorted(subset)) + "}": str(value_fn(subset))
        for subset in SUBSETS
    }


def main():
    result = {
        "route_count": len(ROUTES),
        "subset_count": len(SUBSETS),
        "shared_exogenous_hazard": {
            "values": value_table(expected_exogenous_coverage),
            "audit": diminishing_returns_audit(expected_exogenous_coverage),
        },
        "selection_dependent_relay": {
            "values": value_table(relay_delivered_coverage),
            "audit": diminishing_returns_audit(relay_delivered_coverage),
        },
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
