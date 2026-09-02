from __future__ import annotations

import copy
import functools
import hashlib
import itertools
import random
from typing import Any


MECHANIC_ID = "unlabeled_drawer"
FEATURE_KEYS = (
    "hollow_core",
    "spined_rim",
    "paired_satellites",
    "crossed_veins",
    "balanced_arms",
    "banded_marks",
)
BASELINE_PARAMETERS = {
    "rule_family": "xor2",
    "feature_pool": 5,
    "probe_count": 4,
    "probe_bank_count": 7,
    "final_count": 6,
    "nuisance_strength": 0.5,
}
RULE_ARITY = {"literal": 1, "and2": 2, "xor2": 2, "majority3": 3, "paired4": 4}
DIAGNOSTIC_PATTERNS = {
    "literal": ((0,), (1,)),
    "and2": tuple(itertools.product((0, 1), repeat=2)),
    "xor2": tuple(itertools.product((0, 1), repeat=2)),
    "majority3": ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1)),
    "paired4": ((0, 0, 0, 0), (0, 0, 0, 1), (0, 0, 1, 0), (0, 1, 0, 1), (1, 0, 1, 1), (1, 1, 0, 0), (1, 1, 1, 0), (1, 1, 1, 1)),
}
FINAL_PATTERNS = {
    "literal": ((0,), (1,), (0,), (1,)),
    "and2": ((0, 0), (0, 1), (1, 0), (1, 1), (1, 1)),
    "xor2": ((0, 0), (0, 1), (1, 0), (1, 1), (0, 0), (0, 1)),
    "majority3": DIAGNOSTIC_PATTERNS["majority3"],
    "paired4": DIAGNOSTIC_PATTERNS["paired4"],
}


def _condition(task: dict[str, Any]) -> dict[str, Any] | None:
    value = task.get("_control_condition")
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _parameters(task: dict[str, Any]) -> dict[str, Any]:
    condition = _condition(task)
    if condition:
        return copy.deepcopy(condition["difficulty_parameters"])
    return copy.deepcopy(BASELINE_PARAMETERS)


def _validate(parameters: dict[str, Any]) -> None:
    family = parameters.get("rule_family")
    if family not in RULE_ARITY:
        raise ValueError("rule_family is invalid")
    integer_bounds = {
        "feature_pool": (1, 6),
        "probe_count": (2, 8),
        "probe_bank_count": (2, 12),
        "final_count": (4, 8),
    }
    for key, (low, high) in integer_bounds.items():
        value = parameters.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{key} must be an integer in [{low}, {high}]")
    if parameters["feature_pool"] < RULE_ARITY[family]:
        raise ValueError("feature_pool is smaller than the rule arity")
    if parameters["probe_count"] != len(DIAGNOSTIC_PATTERNS[family]):
        raise ValueError("probe_count does not match the diagnostic rule table")
    if parameters["probe_bank_count"] < parameters["probe_count"]:
        raise ValueError("probe_bank_count is smaller than the available test budget")
    if parameters["final_count"] != len(FINAL_PATTERNS[family]):
        raise ValueError("final_count does not match the final rule table")
    nuisance = parameters.get("nuisance_strength")
    if isinstance(nuisance, bool) or not isinstance(nuisance, (int, float)) or not 0 <= nuisance <= 1:
        raise ValueError("nuisance_strength must be in [0, 1]")


def evaluate_rule(features: list[bool] | tuple[bool, ...], rule: dict[str, Any]) -> bool:
    values = [bool(features[index]) ^ bool(invert) for index, invert in zip(rule["indices"], rule["invert"])]
    family = rule["family"]
    if family == "literal":
        return values[0]
    if family == "and2":
        return values[0] and values[1]
    if family == "xor2":
        return values[0] != values[1]
    if family == "majority3":
        return sum(values) >= 2
    if family == "paired4":
        return values[0] == values[1] and values[2] != values[3]
    raise ValueError(f"unsupported rule family {family!r}")


def _features_from_pattern(
    pattern: tuple[int, ...],
    rule: dict[str, Any],
    base: list[bool],
) -> list[bool]:
    features = list(base)
    for index, invert, bit in zip(rule["indices"], rule["invert"], pattern):
        features[index] = bool(bit) ^ bool(invert)
    return features


def _diagnostic_dimensions(
    specimens: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    family: str,
    feature_pool: int,
) -> tuple[int, ...] | None:
    """Return the visibly varying axes when cards form the profile's contrast table."""
    arity = RULE_ARITY[family]
    dimensions = tuple(
        index
        for index in range(feature_pool)
        if len({bool(specimen["features"][index]) for specimen in specimens}) > 1
    )
    if len(dimensions) != arity:
        return None
    projections = [
        tuple(bool(specimen["features"][index]) for index in dimensions)
        for specimen in specimens
    ]
    if len(set(projections)) != len(projections):
        return None
    target = {tuple(bool(value) for value in pattern) for pattern in DIAGNOSTIC_PATTERNS[family]}
    for order in itertools.permutations(range(arity)):
        for flips in itertools.product((False, True), repeat=arity):
            transformed = {
                tuple(projection[order[index]] ^ flips[index] for index in range(arity))
                for projection in projections
            }
            if transformed == target:
                return dimensions
    return None


def visible_probe_plans(
    probe_specimens: list[dict[str, Any]],
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Enumerate probe plans using card geometry only, never oracle outcomes or IDs."""
    family = str(parameters["rule_family"])
    feature_pool = int(parameters["feature_pool"])
    budget = int(parameters["probe_count"])
    plans: list[dict[str, Any]] = []
    for subset in itertools.combinations(probe_specimens, budget):
        dimensions = _diagnostic_dimensions(subset, family, feature_pool)
        if dimensions is not None:
            plans.append({
                "specimen_ids": [str(specimen["id"]) for specimen in subset],
                "feature_indices": list(dimensions),
            })
    return plans


def visible_rule_hypotheses(family: str, feature_indices: list[int] | tuple[int, ...]) -> list[dict[str, Any]]:
    """Return distinct rule functions over the axes identified by a visible contrast set."""
    dimensions = tuple(int(index) for index in feature_indices)
    arity = RULE_ARITY[family]
    if len(dimensions) != arity or len(set(dimensions)) != arity:
        raise ValueError("visible contrast dimensions do not match the rule family")
    all_vectors = list(itertools.product((False, True), repeat=len(FEATURE_KEYS)))
    distinct: dict[tuple[bool, ...], dict[str, Any]] = {}
    for indices in itertools.permutations(dimensions):
        for invert in itertools.product((False, True), repeat=arity):
            rule = {"family": family, "indices": list(indices), "invert": list(invert)}
            signature = tuple(evaluate_rule(vector, rule) for vector in all_vectors)
            distinct.setdefault(signature, rule)
    return list(distinct.values())


@functools.lru_cache(maxsize=None)
def full_rule_hypotheses(family: str, feature_pool: int) -> tuple[dict[str, Any], ...]:
    """Return every distinct advertised rule function for one difficulty profile."""
    arity = RULE_ARITY[family]
    pool_vectors = list(itertools.product((False, True), repeat=feature_pool))
    distinct: dict[tuple[bool, ...], dict[str, Any]] = {}
    for indices in itertools.permutations(range(feature_pool), arity):
        for invert in itertools.product((False, True), repeat=arity):
            rule = {"family": family, "indices": list(indices), "invert": list(invert)}
            signature = tuple(evaluate_rule(vector, rule) for vector in pool_vectors)
            distinct.setdefault(signature, rule)
    return tuple(distinct.values())


def universally_decodable_vectors(
    selected_probes: list[dict[str, Any]],
    parameters: dict[str, Any],
) -> list[tuple[bool, ...]]:
    """Find final vectors determined at every response leaf of a fixed visible plan."""
    hypotheses = full_rule_hypotheses(str(parameters["rule_family"]), int(parameters["feature_pool"]))
    branches: dict[tuple[bool, ...], list[dict[str, Any]]] = {}
    for rule in hypotheses:
        response = tuple(evaluate_rule(specimen["features"], rule) for specimen in selected_probes)
        branches.setdefault(response, []).append(rule)
    return [
        vector
        for vector in itertools.product((False, True), repeat=len(FEATURE_KEYS))
        if all(len({evaluate_rule(vector, rule) for rule in rules}) == 1 for rules in branches.values())
    ]


def _plan_branch_analysis(
    probe_specimens: list[dict[str, Any]],
    final_specimens: list[dict[str, Any]],
    parameters: dict[str, Any],
    plan: dict[str, Any],
    *,
    full_profile: bool,
) -> dict[str, Any]:
    by_id = {str(specimen["id"]): specimen for specimen in probe_specimens}
    selected = [by_id[specimen_id] for specimen_id in plan["specimen_ids"]]
    hypotheses = (
        full_rule_hypotheses(str(parameters["rule_family"]), int(parameters["feature_pool"]))
        if full_profile
        else visible_rule_hypotheses(str(parameters["rule_family"]), plan["feature_indices"])
    )
    branches: dict[tuple[bool, ...], set[tuple[bool, ...]]] = {}
    for rule in hypotheses:
        response = tuple(evaluate_rule(specimen["features"], rule) for specimen in selected)
        prediction = tuple(evaluate_rule(specimen["features"], rule) for specimen in final_specimens)
        branches.setdefault(response, set()).add(prediction)
    ambiguous = [
        {"response": list(response), "prediction_count": len(predictions)}
        for response, predictions in branches.items()
        if len(predictions) != 1
    ]
    return {"decisive": not ambiguous, "branch_count": len(branches), "branches": ambiguous}


def visible_policy_diagnostics(
    probe_specimens: list[dict[str, Any]],
    final_specimens: list[dict[str, Any]],
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Check every answer leaf for the first outcome-independent visible plan."""
    plans = visible_probe_plans(probe_specimens, parameters)
    if not plans:
        return {"decisive": False, "reason": "no visible contrast set", "plan": None, "branches": []}
    plan = plans[0]
    analysis = _plan_branch_analysis(
        probe_specimens, final_specimens, parameters, plan, full_profile=False
    )
    return {
        "decisive": analysis["decisive"],
        "reason": None if analysis["decisive"] else "a visible response branch leaves conflicting final predictions",
        "plan": plan,
        "branch_count": analysis["branch_count"],
        "branches": analysis["branches"],
    }


def full_profile_policy_diagnostics(
    probe_specimens: list[dict[str, Any]],
    final_specimens: list[dict[str, Any]],
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Audit the visible plan against every rule in the advertised profile."""
    plans = visible_probe_plans(probe_specimens, parameters)
    if not plans:
        return {"decisive": False, "reason": "no visible contrast set", "plan": None, "branches": []}
    plan = plans[0]
    analysis = _plan_branch_analysis(
        probe_specimens, final_specimens, parameters, plan, full_profile=True
    )
    return {
        "decisive": analysis["decisive"],
        "reason": None if analysis["decisive"] else "the full profile leaves conflicting final predictions",
        "plan": plan,
        "branch_count": analysis["branch_count"],
        "branches": analysis["branches"],
    }


def infer_visible_predictions(
    probe_specimens: list[dict[str, Any]],
    final_specimens: list[dict[str, Any]],
    parameters: dict[str, Any],
    specimen_ids: list[str],
    observed_outcomes: dict[str, bool],
) -> dict[str, bool]:
    """Infer finals from visible features plus answers that have already been returned."""
    if set(specimen_ids) != set(observed_outcomes):
        raise ValueError("visible inference requires one returned outcome per selected specimen")
    by_id = {str(specimen["id"]): specimen for specimen in probe_specimens}
    selected = [by_id[specimen_id] for specimen_id in specimen_ids]
    dimensions = _diagnostic_dimensions(
        selected,
        str(parameters["rule_family"]),
        int(parameters["feature_pool"]),
    )
    if dimensions is None:
        raise ValueError("selected specimens do not form a visible contrast set")
    hypotheses = [
        rule
        for rule in full_rule_hypotheses(
            str(parameters["rule_family"]), int(parameters["feature_pool"])
        )
        if all(
            evaluate_rule(by_id[specimen_id]["features"], rule) is bool(observed_outcomes[specimen_id])
            for specimen_id in specimen_ids
        )
    ]
    if not hypotheses:
        raise ValueError("returned outcomes contradict the visible rule family")
    predictions: dict[str, bool] = {}
    for specimen in final_specimens:
        values = {evaluate_rule(specimen["features"], rule) for rule in hypotheses}
        if len(values) != 1:
            raise ValueError(f"returned outcomes do not determine final specimen {specimen['id']}")
        predictions[str(specimen["id"])] = values.pop()
    return predictions


def _style(rng: random.Random, nuisance: float, serial_index: int) -> dict[str, Any]:
    rotation_span = 3 + 17 * nuisance
    scale_span = 0.02 + 0.12 * nuisance
    return {
        "rotation_deg": round(rng.uniform(-rotation_span, rotation_span), 3),
        "scale": round(1 + rng.uniform(-scale_span, scale_span), 4),
        "palette": rng.randrange(5),
        "paper": rng.randrange(4),
        "asymmetry_side": -1 if rng.random() < 0.5 else 1,
        "serial": f"{chr(65 + serial_index // 26)}{serial_index % 26 + 1:02d}",
    }


def _specimen(
    specimen_id: str,
    features: list[bool],
    rng: random.Random,
    nuisance: float,
    serial_index: int,
) -> dict[str, Any]:
    return {
        "id": specimen_id,
        "features": [bool(value) for value in features],
        "style": _style(rng, nuisance, serial_index),
    }


def _specimen_id(stable: str, phase: str, index: int) -> str:
    suffix = hashlib.sha256(f"{stable}:{phase}:{index}".encode("utf-8")).hexdigest()[:7]
    return f"{phase}-{index + 1}-{suffix}"


def _diagnostic_final_vectors(
    rng: random.Random,
    rule: dict[str, Any],
    family: str,
    excluded: set[tuple[bool, ...]],
    allowed: set[tuple[bool, ...]],
) -> list[list[bool]]:
    if family == "paired4":
        candidates = [list(bits) for bits in allowed if bits not in excluded]
        accepted = [bits for bits in candidates if evaluate_rule(bits, rule)]
        rejected = [bits for bits in candidates if not evaluate_rule(bits, rule)]
        rng.shuffle(accepted)
        rng.shuffle(rejected)
        count = len(FINAL_PATTERNS[family])
        accept_count = min(len(accepted), max(1, count // 2))
        reject_count = count - accept_count
        if reject_count > len(rejected):
            reject_count = len(rejected)
            accept_count = count - reject_count
        if accept_count < 1 or reject_count < 1 or accept_count > len(accepted) or accept_count + reject_count != count:
            raise ValueError("decodable paired rule does not provide a balanced final tray")
        selected = accepted[:accept_count] + rejected[:reject_count]
        rng.shuffle(selected)
        return selected
    selected: list[list[bool]] = []
    used = set(excluded)
    for pattern in FINAL_PATTERNS[family]:
        candidates = [
            list(bits)
            for bits in itertools.product((False, True), repeat=len(FEATURE_KEYS))
            if tuple(bool(bits[index]) ^ bool(invert) for index, invert in zip(rule["indices"], rule["invert"])) == pattern
            and tuple(bits) not in used
            and tuple(bits) in allowed
        ]
        rng.shuffle(candidates)
        if not candidates:
            raise ValueError("rule does not provide a fresh final diagnostic case")
        selected.append(candidates[0])
        used.add(tuple(candidates[0]))
    rng.shuffle(selected)
    return selected


def _stable_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    """Keep the original five-parameter world identity stable after adding the bank."""
    return {
        "rule_family": parameters["rule_family"],
        "feature_pool": parameters["feature_pool"],
        "probe_count": parameters["probe_count"],
        "final_count": parameters["final_count"],
        "nuisance_strength": parameters["nuisance_strength"],
    }


def generate(task: dict[str, Any], seed: str):
    parameters = _parameters(task)
    _validate(parameters)
    stable = hashlib.sha256(f"{MECHANIC_ID}:{seed}:{_stable_parameters(parameters)}".encode("utf-8")).hexdigest()
    rng = random.Random(int(stable[:16], 16))
    challenge_id = f"udr-{stable[:18]}"
    task_id = str(task.get("id") or "unlabeled_drawer")
    family = str(parameters["rule_family"])
    arity = RULE_ARITY[family]
    indices = rng.sample(range(int(parameters["feature_pool"])), arity)
    rule = {
        "family": family,
        "indices": indices,
        "invert": [bool(rng.getrandbits(1)) for _ in range(arity)],
    }

    patterns = list(DIAGNOSTIC_PATTERNS[family])
    shared_base = [bool(rng.getrandbits(1)) for _ in FEATURE_KEYS]
    probe_specimens: list[dict[str, Any]] = []
    probe_outcomes: dict[str, bool] = {}
    for index, pattern in enumerate(patterns):
        features = _features_from_pattern(pattern, rule, shared_base)
        specimen_id = _specimen_id(stable, "probe", index)
        specimen = _specimen(specimen_id, features, rng, float(parameters["nuisance_strength"]), index)
        probe_specimens.append(specimen)
        probe_outcomes[specimen_id] = evaluate_rule(features, rule)
    paired = list(zip(probe_specimens, patterns))
    rng.shuffle(paired)
    probe_specimens = [item[0] for item in paired]

    excluded = {tuple(item["features"]) for item in probe_specimens}
    decodable_vectors = set(universally_decodable_vectors(probe_specimens, parameters))
    final_vectors = _diagnostic_final_vectors(rng, rule, family, excluded, decodable_vectors)
    if len(final_vectors) != int(parameters["final_count"]):
        raise AssertionError("final rule table does not match the configured tray size")
    final_specimens: list[dict[str, Any]] = []
    final_outcomes: dict[str, bool] = {}
    for index, features in enumerate(final_vectors):
        specimen_id = _specimen_id(stable, "final", index)
        specimen = _specimen(
            specimen_id,
            features,
            rng,
            float(parameters["nuisance_strength"]),
            len(probe_specimens) + index,
        )
        final_specimens.append(specimen)
        final_outcomes[specimen_id] = evaluate_rule(features, rule)

    # Extra cards make calibration a choice rather than an exhaustive reveal.  A
    # player can locate a contrast table from visible feature variation alone; no
    # unrevealed answer or construction-order label is needed to choose it.
    used_vectors = excluded | {tuple(item["features"]) for item in final_specimens}
    decoy_vectors = [
        list(bits)
        for bits in itertools.product((False, True), repeat=len(FEATURE_KEYS))
        if tuple(bits) not in used_vectors
    ]
    bank_rng = random.Random(int(hashlib.sha256(f"{stable}:probe-bank".encode("utf-8")).hexdigest()[:16], 16))
    decoy_count = int(parameters["probe_bank_count"]) - len(probe_specimens)
    selected_decoys: list[list[bool]] | None = None
    for _attempt in range(2048):
        candidates = bank_rng.sample(decoy_vectors, decoy_count)
        candidate_bank = probe_specimens + [
            {"id": f"candidate-{index}", "features": features}
            for index, features in enumerate(candidates)
        ]
        plans = visible_probe_plans(candidate_bank, parameters)
        plans_are_safe = bool(plans) and all(
            set(plan["feature_indices"]) == set(rule["indices"])
            and _plan_branch_analysis(
                candidate_bank, final_specimens, parameters, plan, full_profile=True
            )["decisive"]
            for plan in plans
        )
        if plans_are_safe:
            selected_decoys = candidates
            break
    if selected_decoys is None:
        raise AssertionError("could not construct a visibly selectable probe bank")
    for offset, features in enumerate(selected_decoys):
        index = len(patterns) + offset
        specimen_id = _specimen_id(stable, "probe", index)
        specimen = _specimen(
            specimen_id,
            features,
            bank_rng,
            float(parameters["nuisance_strength"]),
            len(patterns) + len(final_specimens) + offset,
        )
        probe_specimens.append(specimen)
        probe_outcomes[specimen_id] = evaluate_rule(features, rule)
    if len(probe_specimens) != int(parameters["probe_bank_count"]):
        raise AssertionError("probe bank does not match the configured size")
    bank_rng.shuffle(probe_specimens)
    # Visible serials follow the shuffled rack rather than construction order,
    # so they cannot reveal which cards belong to the guaranteed diagnostic set.
    for index, specimen in enumerate(probe_specimens, 1):
        specimen["style"]["serial"] = f"P{index:02d}"
    for index, specimen in enumerate(final_specimens, 1):
        specimen["style"]["serial"] = f"F{index:02d}"

    policy = visible_policy_diagnostics(probe_specimens, final_specimens, parameters)
    if not policy["decisive"]:
        raise AssertionError(f"visible probe policy is not decisive: {policy}")
    full_policy = full_profile_policy_diagnostics(probe_specimens, final_specimens, parameters)
    if not full_policy["decisive"]:
        raise AssertionError(f"full-profile visible policy is not decisive: {full_policy}")

    if not ({True, False} <= set(probe_outcomes.values())):
        raise AssertionError("probe table must show both oracle outcomes")
    if not ({True, False} <= set(final_outcomes.values())):
        raise AssertionError("final tray must contain both drawer classes")

    condition = _condition(task)
    public_state = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "prompt": "The cabinet will answer, but it will not explain.",
        "probe_specimens": copy.deepcopy(probe_specimens),
        "final_specimens": copy.deepcopy(final_specimens),
        "runtime_probe_outcomes": copy.deepcopy(probe_outcomes),
        "parameters": copy.deepcopy(parameters),
        "feature_count": len(FEATURE_KEYS),
        "drop_regions": {
            "probe": [0.64, 0.20, 0.96, 0.82],
            "accept": [0.64, 0.20, 0.80, 0.91],
            "reject": [0.80, 0.20, 0.96, 0.91],
        },
        "source_regions": {
            "probe-rack": [0.02, 0.16, 0.62, 0.84],
            "final-rack": [0.02, 0.16, 0.62, 0.84],
        },
        "asset_manifest": str((task.get("metadata") or {}).get("asset_manifest") or "shared_runtime/assets/provenance/unlabeled_drawer_v0.json"),
        "status": "ready",
    }
    ground_truth = {
        "mechanic_id": MECHANIC_ID,
        "task_id": task_id,
        "challenge_id": challenge_id,
        "rule": copy.deepcopy(rule),
        "probe_specimens": copy.deepcopy(probe_specimens),
        "final_specimens": copy.deepcopy(final_specimens),
        "probe_outcomes": copy.deepcopy(probe_outcomes),
        "final_outcomes": copy.deepcopy(final_outcomes),
        "parameters": copy.deepcopy(parameters),
    }
    if condition is not None:
        public_state["control_condition"] = copy.deepcopy(condition)
        ground_truth["control_condition"] = copy.deepcopy(condition)
    return public_state, ground_truth
