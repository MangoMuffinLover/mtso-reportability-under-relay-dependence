#!/usr/bin/env python3
"""Exact MTSO-aligned candidate-path reportability experiment.

The experiment holds a small risky path library fixed and compares:

1. expected weighted visitation (the MTSO-style objective),
2. expected coverage of fixed exogenous reportable sets, and
3. expected delivered coverage when reports require selected relay paths.

Every route subset and every diminishing-returns inequality is enumerated
exactly with rational arithmetic.  This is a structural mechanism test, not a
reproduction of the algorithms or experiments in Jorgensen and Pavone (2024).
"""

from __future__ import annotations

import csv
import json
from fractions import Fraction
from itertools import combinations
from math import dist
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent
ROUTES = ("central", "diagonal", "east_relay", "east_scout", "west_relay", "west_scout")
K = 3
SURVIVAL_THRESHOLD = Fraction(4, 5)
COMM_RANGE = 2.2
BASE = (0.0, 0.0)

# All paths start at BASE and terminate at (0, 6).  Coordinates are used only
# for the relay-delivery objective; the candidate-path ground set is frozen.
PATHS = {
    "east_scout": ((0, 0), (2, 0), (4, 0), (3, 3), (0, 6)),
    "east_relay": ((0, 0), (1, 0), (2, 0), (1.5, 3), (0, 6)),
    "west_scout": ((0, 0), (-2, 0), (-4, 0), (-3, 3), (0, 6)),
    "west_relay": ((0, 0), (-1, 0), (-2, 0), (-1.5, 3), (0, 6)),
    "central": ((0, 0), (0, 1), (0, 2), (0, 4), (0, 6)),
    "diagonal": ((0, 0), (1, 1), (1.5, 1.5), (1, 4), (0, 6)),
}

# route -> tuple[(time, target), ...]
DETECTIONS = {
    "east_scout": ((2, "east"),),
    "east_relay": (),
    "west_scout": ((2, "west"),),
    "west_relay": (),
    "central": ((2, "central"),),
    "diagonal": ((2, "central"), (2, "diagonal")),
}

TARGET_WEIGHTS = {
    "east": Fraction(3),
    "west": Fraction(3),
    "central": Fraction(1),
    "diagonal": Fraction(1),
}

# Shared scenario draws correlate outcomes across routes.  active_until is the
# last reached waypoint; a value of 1 prevents a t=2 detection.  The fixed
# backbone field defines per-route reportability without reference to which
# other candidate paths are selected.
SCENARIOS = {
    "clear": {
        "prob": Fraction(1, 2),
        "active_until": {},
        "radio_off": frozenset(),
        "fixed_backbone": frozenset({"east_scout", "west_scout", "central", "diagonal"}),
    },
    "east_storm": {
        "prob": Fraction(3, 20),
        "active_until": {"east_scout": 1},
        "radio_off": frozenset(),
        "fixed_backbone": frozenset({"west_scout", "central", "diagonal"}),
    },
    "west_storm": {
        "prob": Fraction(3, 20),
        "active_until": {"west_scout": 1},
        "radio_off": frozenset(),
        "fixed_backbone": frozenset({"east_scout", "central", "diagonal"}),
    },
    "relay_shadow": {
        "prob": Fraction(1, 10),
        "active_until": {},
        "radio_off": frozenset({"east_relay", "west_relay"}),
        "fixed_backbone": frozenset({"central", "diagonal"}),
    },
    "global_blackout": {
        "prob": Fraction(1, 10),
        "active_until": {},
        "radio_off": frozenset(ROUTES),
        "fixed_backbone": frozenset(),
    },
}


def powerset(items):
    for size in range(len(items) + 1):
        for subset in combinations(items, size):
            yield frozenset(subset)


SUBSETS = tuple(powerset(ROUTES))


def weighted(targets) -> Fraction:
    return sum((TARGET_WEIGHTS[target] for target in targets), Fraction(0))


def active_until(route: str, scenario: dict) -> int:
    return int(scenario["active_until"].get(route, len(PATHS[route]) - 1))


def visited_by_route(route: str, scenario: dict) -> frozenset[str]:
    stop = active_until(route, scenario)
    return frozenset(target for time, target in DETECTIONS[route] if time <= stop)


def visit_value_in_scenario(selected, scenario) -> Fraction:
    targets = set()
    for route in selected:
        targets.update(visited_by_route(route, scenario))
    return weighted(targets)


def fixed_report_value_in_scenario(selected, scenario) -> Fraction:
    targets = set()
    for route in selected:
        if route in scenario["fixed_backbone"]:
            targets.update(visited_by_route(route, scenario))
    return weighted(targets)


def connected_to_base(carrier: str, selected, scenario, time: int) -> bool:
    """Return whether carrier has a same-time radio chain to the fixed base."""
    live = [
        route
        for route in selected
        if route not in scenario["radio_off"] and time <= active_until(route, scenario)
    ]
    if carrier not in live:
        return False

    positions = {route: PATHS[route][time] for route in live}
    seen = {"BASE"}
    frontier = ["BASE"]
    while frontier:
        node = frontier.pop()
        node_position = BASE if node == "BASE" else positions[node]
        for route, position in positions.items():
            if route not in seen and dist(node_position, position) <= COMM_RANGE:
                seen.add(route)
                frontier.append(route)
    return carrier in seen


def relay_report_value_in_scenario(selected, scenario) -> Fraction:
    delivered = set()
    for route in selected:
        stop = active_until(route, scenario)
        for detection_time, target in DETECTIONS[route]:
            if detection_time > stop:
                continue
            # The detecting robot retains its report and may deliver later if a
            # selected, surviving synchronous relay chain becomes available.
            if any(
                connected_to_base(route, selected, scenario, time)
                for time in range(detection_time, stop + 1)
            ):
                delivered.add(target)
    return weighted(delivered)


def expected_value(selected, scenario_value_fn) -> Fraction:
    return sum(
        (scenario["prob"] * scenario_value_fn(selected, scenario) for scenario in SCENARIOS.values()),
        Fraction(0),
    )


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
                gain_small = value_fn(small | {element}) - value_fn(small)
                gain_large = value_fn(large | {element}) - value_fn(large)
                slack = gain_small - gain_large
                checked += 1
                minimum_slack = slack if minimum_slack is None else min(minimum_slack, slack)
                if slack < 0:
                    violations.append(
                        {
                            "small": sorted(small),
                            "large": sorted(large),
                            "element": element,
                            "gain_small": str(gain_small),
                            "gain_large": str(gain_large),
                            "slack": str(slack),
                        }
                    )
    return {
        "inequalities_checked": checked,
        "violation_count": len(violations),
        "minimum_slack": str(minimum_slack),
        "first_five_violations": violations[:5],
    }


def greedy(value_fn, rank=K):
    selected = frozenset()
    trace = []
    for _ in range(rank):
        choices = []
        for route in ROUTES:
            if route in selected:
                continue
            gain = value_fn(selected | {route}) - value_fn(selected)
            choices.append((gain, route))
        gain, route = max(choices, key=lambda item: (item[0], tuple(-ord(c) for c in item[1])))
        selected = selected | {route}
        trace.append({"route": route, "gain": str(gain), "value": str(value_fn(selected))})
    return selected, value_fn(selected), trace


def optimum(value_fn, rank=K):
    feasible = [subset for subset in SUBSETS if len(subset) <= rank]
    return max(feasible, key=lambda subset: (value_fn(subset), tuple(sorted(subset))))


def survival_probability(route: str) -> Fraction:
    return sum(
        (scenario["prob"] for scenario in SCENARIOS.values() if active_until(route, scenario) == len(PATHS[route]) - 1),
        Fraction(0),
    )


# A generic detector-relay bundle lift.  Selecting bundles makes each bundle's
# reportable set fixed, restoring a coverage objective.  But forbidding reuse
# of a physical route yields a set-packing family that can fail matroid exchange.
BUNDLE_RESOURCES = {
    "bundle_12": frozenset({"r1", "r2"}),
    "bundle_23": frozenset({"r2", "r3"}),
    "bundle_34": frozenset({"r3", "r4"}),
}
BUNDLE_TARGETS = {
    "bundle_12": frozenset({"a"}),
    "bundle_23": frozenset({"b"}),
    "bundle_34": frozenset({"c"}),
}


def bundle_feasible(selected) -> bool:
    used = set()
    for bundle in selected:
        resources = BUNDLE_RESOURCES[bundle]
        if used & resources:
            return False
        used.update(resources)
    return True


def bundle_exchange_audit():
    bundles = tuple(BUNDLE_RESOURCES)
    feasible = [subset for subset in powerset(bundles) if bundle_feasible(subset)]
    violations = []
    for small in feasible:
        for large in feasible:
            if len(small) >= len(large):
                continue
            augmenting = [element for element in large - small if bundle_feasible(small | {element})]
            if not augmenting:
                violations.append({"small": sorted(small), "large": sorted(large)})
    return {
        "feasible_sets": len(feasible),
        "exchange_violation_count": len(violations),
        "witness": violations[0] if violations else None,
    }


def bundle_coverage_audit():
    bundles = tuple(BUNDLE_RESOURCES)
    subsets = tuple(powerset(bundles))

    def value(selected):
        covered = set()
        for bundle in selected:
            covered.update(BUNDLE_TARGETS[bundle])
        return Fraction(len(covered))

    checked = 0
    violations = 0
    minimum_slack = None
    for small in subsets:
        for large in subsets:
            if not small.issubset(large):
                continue
            for element in bundles:
                if element in large:
                    continue
                slack = (value(small | {element}) - value(small)) - (value(large | {element}) - value(large))
                checked += 1
                minimum_slack = slack if minimum_slack is None else min(minimum_slack, slack)
                violations += int(slack < 0)
    return {
        "inequalities_checked": checked,
        "violation_count": violations,
        "minimum_slack": str(minimum_slack),
    }


def main():
    objectives = {
        "expected_visitation": lambda selected: expected_value(selected, visit_value_in_scenario),
        "fixed_reportable_sets": lambda selected: expected_value(selected, fixed_report_value_in_scenario),
        "selection_dependent_relays": lambda selected: expected_value(selected, relay_report_value_in_scenario),
    }

    survival = {route: survival_probability(route) for route in ROUTES}
    assert all(probability >= SURVIVAL_THRESHOLD for probability in survival.values())
    assert sum((scenario["prob"] for scenario in SCENARIOS.values()), Fraction(0)) == 1

    result = {
        "route_count": len(ROUTES),
        "subset_count": len(SUBSETS),
        "uniform_matroid_rank": K,
        "survival_threshold": str(SURVIVAL_THRESHOLD),
        "route_survival_probabilities": {route: str(probability) for route, probability in survival.items()},
        "objectives": {},
        "bundle_lift": {
            "coverage_audit": bundle_coverage_audit(),
            "resource_no_reuse_exchange_audit": bundle_exchange_audit(),
        },
    }

    summary_rows = []
    for name, value_fn in objectives.items():
        audit = diminishing_returns_audit(value_fn)
        greedy_set, greedy_value, trace = greedy(value_fn)
        optimal_set = optimum(value_fn)
        optimal_value = value_fn(optimal_set)
        ratio = greedy_value / optimal_value if optimal_value else Fraction(1)
        result["objectives"][name] = {
            "audit": audit,
            "greedy_set": sorted(greedy_set),
            "greedy_value": str(greedy_value),
            "greedy_trace": trace,
            "optimal_set": sorted(optimal_set),
            "optimal_value": str(optimal_value),
            "greedy_to_optimal_ratio": str(ratio),
        }
        summary_rows.append(
            {
                "objective": name,
                "inequalities_checked": audit["inequalities_checked"],
                "violations": audit["violation_count"],
                "minimum_slack": audit["minimum_slack"],
                "greedy_value": float(greedy_value),
                "optimal_value": float(optimal_value),
                "greedy_to_optimal_ratio": float(ratio),
            }
        )

    (ROOT / "mtso_aligned_results.json").write_text(json.dumps(result, indent=2) + "\n")
    with (ROOT / "mtso_aligned_summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)

    labels = [row["objective"].replace("_", "\n") for row in summary_rows]
    greedy_values = [row["greedy_value"] for row in summary_rows]
    optimal_values = [row["optimal_value"] for row in summary_rows]
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(8.2, 4.6), constrained_layout=True)
    ax.bar([i - 0.18 for i in x], greedy_values, width=0.36, label="Lexicographic greedy", color="#3b82f6")
    ax.bar([i + 0.18 for i in x], optimal_values, width=0.36, label="Exact optimum", color="#f97316")
    ax.set_xticks(list(x), labels)
    ax.set_ylabel("Expected weighted reward")
    ax.set_title("Same candidate paths; report-delivery model changes structure")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.savefig(ROOT / "mtso_aligned_objectives.png", dpi=180)
    plt.close(fig)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
