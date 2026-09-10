"""Generate the frozen pilot matrix and report exact differences, without relabeling."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def differences(a, b, prefix=""):
    if type(a) is not type(b):
        return [prefix]
    if isinstance(a, dict):
        result = []
        for key in sorted(a.keys() | b.keys()):
            path = f"{prefix}/{key}"
            result += [path] if key not in a or key not in b else differences(a[key], b[key], path)
        return result
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{prefix}/length"]
        return [path for i, (x, y) in enumerate(zip(a, b)) for path in differences(x, y, f"{prefix}/{i}")]
    return [] if a == b else [prefix]


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    bench = Path(manifest["source_root"]) / "weird_captcha_gym"
    setup = load(bench / "shared_scripts/setup_task.py", "pilot_setup")
    materializer = load(bench / "tools/materialize_controlled_tasks.py", "pilot_materializer")
    seeds = manifest.get("fixed_seeds", [1, 17, 101])
    outputs = ROOT / "outputs" / "generation"
    outputs.mkdir(parents=True, exist_ok=False)
    results = {"schema_version": 1, "source_revision": manifest["source_revision"],
               "seeds": seeds, "profiles": [], "baseline_comparisons": [],
               "interaction_comparisons": [], "adjacent_comparisons": [],
               "limitations": "Exact JSON differences are diagnostics, not difficulty or equivalence judgments. Current default versus explicit baseline is not historical preservation evidence."}
    for case in manifest["cases"]:
        env = bench / "environments" / case["environment_id"]
        controls = json.loads((env / "controls.json").read_text())
        materializer.validate_controls(controls, env)
        mechanic = controls["mechanic_id"]
        base = json.loads((env / "tasks" / f"{mechanic}_seed_0001" / "task.json").read_text())
        tasks = {}
        for level in range(1, 6):
            for mode in ("simplified", "full"):
                task = materializer.controlled_task(base, mechanic_id=mechanic, level=level,
                    interaction=mode, profile=controls["difficulty"][str(level)],
                    task_dir_name=f"{mechanic}_d{level}_{mode}_seed_0001")
                tasks[level, mode] = task
        for seed in seeds:
            generated = {}
            for (level, mode), task in tasks.items():
                state = setup.generate_task_state(task, str(seed))
                repeated = setup.generate_task_state(task, str(seed))
                record = {"environment_id": case["environment_id"], "public_name": case["public_name"],
                          "difficulty": level, "interaction": mode, "seed": seed,
                          "deterministic": state == repeated, "public_sha256": digest(state[0]),
                          "truth_sha256": digest(state[1]), "parameters": controls["difficulty"][str(level)]["parameters"]}
                results["profiles"].append(record)
                generated[level, mode] = state
                destination = outputs / mechanic / f"d{level}_{mode}_seed{seed}"
                destination.mkdir(parents=True)
                for name, data in (("task", task), ("public_state", state[0]), ("ground_truth", state[1])):
                    (destination / f"{name}.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
            baseline = controls["baseline"]
            default = setup.generate_task_state(base, str(seed))
            explicit = generated[baseline["difficulty"], baseline["interaction"]]
            results["baseline_comparisons"].append({"environment_id": case["environment_id"], "seed": seed,
                "public_differing_paths": differences(default[0], explicit[0]),
                "truth_differing_paths": differences(default[1], explicit[1])})
            for level in range(1, 6):
                simple, full = generated[level, "simplified"], generated[level, "full"]
                results["interaction_comparisons"].append({"environment_id": case["environment_id"], "difficulty": level,
                    "seed": seed, "public_differing_paths": differences(simple[0], full[0]),
                    "truth_differing_paths": differences(simple[1], full[1])})
            for level in range(1, 5):
                for mode in ("simplified", "full"):
                    low, high = generated[level, mode], generated[level + 1, mode]
                    results["adjacent_comparisons"].append({"environment_id": case["environment_id"],
                        "lower": level, "higher": level+1, "interaction": mode, "seed": seed,
                        "public_differing_paths": differences(low[0], high[0]),
                        "truth_differing_paths": differences(low[1], high[1])})
        print(f"GENERATED {case['public_name']}: 30 configurations; deterministic={all(r['deterministic'] for r in results['profiles'] if r['environment_id']==case['environment_id'])}", flush=True)
    target = ROOT / "generation_checks.json"
    assert not target.exists(), "Preserve previous evidence"
    target.write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps({"profiles": len(results["profiles"]), "all_deterministic": all(r["deterministic"] for r in results["profiles"])}))


if __name__ == "__main__":
    main()
