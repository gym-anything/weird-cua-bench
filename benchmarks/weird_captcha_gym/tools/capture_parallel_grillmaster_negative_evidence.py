#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "weird_captcha_gym"
GRADER_PATH = (
    BENCHMARK
    / "shared_runtime"
    / "server"
    / "incubator_graders"
    / "parallel_grillmaster.py"
)
HELPERS_PATH = BENCHMARK / "shared_runtime" / "verifier_helpers.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture Grillmaster signed-witness rejection evidence."
    )
    parser.add_argument("--exported-result", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decision(
    grader,
    helpers,
    payload: dict[str, Any],
    truth: dict[str, Any],
    public: dict[str, Any],
) -> dict[str, Any]:
    return {
        "grader": grader.grade(payload, truth, public),
        "verifier": helpers.verify_external_mechanic(
            {
                "result": payload,
                "ground_truth": truth,
                "public_state": public,
            },
            "parallel_grillmaster",
        ),
    }


def synthetic_claim(
    result: dict[str, Any],
    truth: dict[str, Any],
) -> dict[str, Any]:
    targets = truth["targets"]
    starts = {
        food_id: index * 20.0
        for index, food_id in enumerate(targets)
    }
    actions = []
    for food_id in targets:
        actions.append(
            {
                "sequence": len(actions) + 1,
                "kind": "start",
                "food_id": food_id,
                "input_source": "food_drag",
                "t_ms": starts[food_id],
            }
        )
    for timestamp, food_id in sorted(
        (
            starts[food_id] + float(target["target_ms"]),
            food_id,
        )
        for food_id, target in targets.items()
    ):
        actions.append(
            {
                "sequence": len(actions) + 1,
                "kind": "serve",
                "food_id": food_id,
                "input_source": "food_drag",
                "t_ms": timestamp,
            }
        )
    return {
        "mechanic_id": result["mechanic_id"],
        "task_id": result["task_id"],
        "challenge_id": result["challenge_id"],
        "durations_ms": {
            food_id: target["target_ms"]
            for food_id, target in targets.items()
        },
        "actions": actions,
    }


def main() -> None:
    args = parse_args()
    exported = json.loads(
        args.exported_result.read_text(encoding="utf-8")
    )
    result = exported["result"]
    truth = exported["ground_truth"]
    public = exported["public_state"]
    grader = load_module("grillmaster_negative_grader", GRADER_PATH)
    helpers = load_module("grillmaster_negative_helpers", HELPERS_PATH)

    synthetic = synthetic_claim(result, truth)
    tampered_source = copy.deepcopy(result)
    tampered_source["trusted_witness"]["actions"][0][
        "input_source"
    ] = "grill_proxy_controls"
    tampered_route = copy.deepcopy(result)
    tampered_route["trusted_witness"]["actions"][0][
        "witnessed_route"
    ] = "simplified_proxy"
    unbound_key = copy.deepcopy(result)
    modulus = unbound_key["trusted_witness"]["public_key"]["n_hex"]
    unbound_key["trusted_witness"]["public_key"]["n_hex"] = (
        modulus[:-1] + ("0" if modulus[-1] != "0" else "1")
    )
    stale = copy.deepcopy(result)
    stale["challenge_id"] = "stale-challenge"

    output = {
        "source_export": str(args.exported_result),
        "accepted_server_attested_result": decision(
            grader,
            helpers,
            result,
            truth,
            public,
        ),
        "synthetic_perfect_client_timestamps_and_source": decision(
            grader,
            helpers,
            synthetic,
            truth,
            public,
        ),
        "tampered_signed_input_source": decision(
            grader,
            helpers,
            tampered_source,
            truth,
            public,
        ),
        "tampered_signed_endpoint_route": decision(
            grader,
            helpers,
            tampered_route,
            truth,
            public,
        ),
        "witness_public_key_not_bound_to_hidden_challenge": decision(
            grader,
            helpers,
            unbound_key,
            truth,
            public,
        ),
        "stale_challenge": decision(
            grader,
            helpers,
            stale,
            truth,
            public,
        ),
        "boundary": (
            "The synthetic case reproduces the former perfect caller-authored "
            "timestamps/source attack. The accepted case is a live browser "
            "result containing server-clocked, route-derived, signed actions."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
