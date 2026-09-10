"""Compare unmodified JS layout functions with the independent Python grader.

The browser function closure is exported only into a separate Node VM for this
diagnostic, never injected into the task page or written back to puzzle source.
"""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
NODE_DRIVER = r"""
const fs = require('fs');
const vm = require('vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const source = fs.readFileSync(input.javascript_path, 'utf8');
const end = source.lastIndexOf('})();');
if (end < 0) throw new Error('missing expected closure terminator');
const injected = source.slice(0, end) +
  'globalThis.audit = {solveLayout, raster, similarity, setModel: value => {model = value;}};\n' + source.slice(end);
const sandbox = {window: {}};
vm.runInNewContext(injected, sandbox, {timeout: 5000});
const output = input.rows.map(row => {
  sandbox.audit.setModel({frames: row.frames, items: row.items});
  const boxes = sandbox.audit.solveLayout(row.config);
  return {name: row.name, boxes, score: sandbox.audit.similarity(sandbox.audit.raster(row.target_layout), sandbox.audit.raster(boxes))};
});
process.stdout.write(JSON.stringify(output));
"""


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    bench = Path(manifest["source_root"]) / "weird_captcha_gym"
    grader_path = bench / "shared_runtime/server/incubator_graders/reflow_vitrine.py"
    spec = importlib.util.spec_from_file_location("primary_reflow_grader", grader_path)
    grader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grader)
    requests, truths = [], {}
    for folder in sorted((ROOT / "outputs/generation/reflow_vitrine").glob("d*_full_seed*")):
        truth = json.loads((folder / "ground_truth.json").read_text())
        truths[folder.name] = truth
        for kind in ("initial", "target"):
            requests.append({"name": folder.name + ":" + kind, "frames": truth["frames"], "items": truth["items"],
                             "config": truth[kind + "_config"], "target_layout": truth["target_layout"]})
    completed = subprocess.run(["node", "-e", NODE_DRIVER], input=json.dumps({
        "javascript_path": str(bench / "shared_runtime/app/mechanics/reflow_vitrine.js"), "rows": requests,
    }), text=True, capture_output=True, timeout=30, check=True)
    actual = json.loads(completed.stdout)
    rows = []
    for request, js in zip(requests, actual, strict=True):
        boxes = grader._layout(request["frames"], request["items"], request["config"])
        score = grader._ssim(grader._raster(request["target_layout"]), grader._raster(boxes))
        differences = []
        for node, box in boxes.items():
            delta = {key: {"python": box[key], "javascript": js["boxes"][node][key]} for key in ("x", "y", "w", "h") if abs(box[key] - js["boxes"][node][key]) > 1e-8}
            if delta:
                differences.append({"node": node, "differences": delta})
        rows.append({"configuration": request["name"], "python_similarity": score, "javascript_similarity": js["score"],
                     "similarity_disagrees_beyond_grader_tolerance": abs(score - round(js["score"], 8)) > 0.00001,
                     "layout_differences": differences})
    failures = []
    for path in sorted((ROOT / "outputs/browser").glob("042*seed1_solve/state/attempts.jsonl")):
        for line in path.read_text().splitlines():
            payload = json.loads(line)
            name = path.parent.parent.name
            level = name.split("_d", 1)[1].split("_", 1)[0]
            truth = truths[f"d{level}_full_seed1"]
            failures.append({"check": name, "submitted_config_equals_generated_target": payload["final_config"] == truth["target_config"],
                             "submitted_similarity": payload["similarity"], "server_grade": payload.get("server_grade")})
    result = {"schema_version": 1, "source_revision": manifest["source_revision"],
              "scope": "Read-only pure-function diagnostic over 15 frozen worlds, target and initial configurations; not an agent run or a modified task.",
              "rows": rows, "original_browser_failures": failures}
    (ROOT / "reflow_layout_checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"configurations": len(rows), "mismatches": [row for row in rows if row["similarity_disagrees_beyond_grader_tolerance"]], "original_failures": failures}, indent=2))


if __name__ == "__main__":
    main()
