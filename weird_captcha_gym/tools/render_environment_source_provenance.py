#!/usr/bin/env python3
"""Render the source-provenance table for every benchmark environment."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from weird_captcha_gym.dashboard.catalog import build_catalog  # noqa: E402


PROVENANCE_ROOT = REPO_ROOT / "weird_captcha_gym" / "shared_runtime" / "assets" / "provenance"
COLLECTION_ROOT = REPO_ROOT.parent / "research" / "collection"
OUTPUT = REPO_ROOT / "weird_captcha_gym" / "docs" / "environment-source-provenance.md"

SOURCE_ALIASES = {
    "CaptchaWare": "captchaware",
    "nextgen-captchas": "nextgen-captchas-benchmark",
    "opencaptchaworld": "opencaptchaworld-benchmark",
}

PREFERRED_EVIDENCE = {
    "captcha-rpg": "notes.md",
    "captchaware": "microgames.md",
    "github-henryamatsu-im-not-a-robot": "raw/extracted-mechanics.json",
    "github-nicholasdejesse-captcha-game": "raw/extracted-mechanics.json",
    "github-ttuples-simplecaptcha": "raw/extracted-mechanics.json",
    "logic-captcha-media-examples-2024": "raw/prompt-seeds.json",
    "modrinth-evil-captcha": "raw/extracted-mechanics.json",
    "neal-im-not-a-robot": "mechanics.md",
    "nextgen-captchas-benchmark": "notes.md",
    "opencaptchaworld-benchmark": "notes.md",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def source_parts(anchor: str) -> tuple[str | None, str | None]:
    if anchor.startswith(("https://", "http://")):
        return None, None
    prefix = "research/collection/sources/"
    normalized = anchor[len(prefix):] if anchor.startswith(prefix) else anchor
    base, separator, detail = normalized.partition("/")
    return SOURCE_ALIASES.get(base, base), detail if separator else None


def local_source_href(slug: str) -> str:
    relative = PREFERRED_EVIDENCE.get(slug, "notes.md")
    path = COLLECTION_ROOT / "sources" / slug / relative
    if not path.is_file():
        raise FileNotFoundError(path)
    return f"../../../research/collection/sources/{slug}/{relative}"


def external_label(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    suffix = path.rsplit("/", 1)[-1] if path else parsed.netloc
    return f"{parsed.netloc} / {suffix}"


def render_source(anchor: str, source_catalog: dict[str, dict]) -> str:
    if anchor.startswith(("https://", "http://")):
        return f"[{markdown_cell(external_label(anchor))}]({anchor})"

    slug, detail = source_parts(anchor)
    if slug not in source_catalog:
        raise KeyError(f"unresolved source anchor: {anchor}")
    source = source_catalog[slug]
    detail_label = f" — `{markdown_cell(detail)}`" if detail else ""
    collected = f"[collected evidence]({local_source_href(slug)})"
    original = f"[original source]({source['primary_url']})"
    return f"**{markdown_cell(source['title'])}**{detail_label}<br>{collected} · {original}"


def provenance_index() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for path in sorted(PROVENANCE_ROOT.glob("*.json")):
        text = path.read_text(errors="replace")
        for environment in build_catalog()["environments"]:
            if environment["mechanic_id"] in text:
                result.setdefault(environment["mechanic_id"], []).append(path.name)
    return result


def main() -> None:
    environments = build_catalog()["environments"]
    source_catalog = {row["slug"]: row for row in read_jsonl(COLLECTION_ROOT / "catalog.jsonl")}
    provenance = provenance_index()

    assert len(environments) == 75
    assert len({environment["id"] for environment in environments}) == 75

    lines = [
        "# Source Provenance for All 75 Environments",
        "",
        "This table records the source of every implemented Weird CUA Bench environment. Each row is generated from that environment's checked-in `metadata.source_anchors`; the task JSON link exposes the exact stored anchors. Local evidence links open the archived survey material, original-source links come from the frozen source catalog, and transformation-manifest links record how the source idea became the benchmark environment.",
        "",
        "A source anchor identifies inspiration or lineage. Several environments deliberately transform one source idea into a different interaction, and composite rows combine multiple sources. The table therefore documents provenance rather than claiming that an environment is a direct copy.",
        "",
        "| # | Benchmark environment | Exact stored anchor(s) | Source link(s) | Checked-in provenance |",
        "| ---: | --- | --- | --- | --- |",
    ]

    for index, environment in enumerate(environments, 1):
        anchors = list(environment.get("source_anchors") or [])
        if not anchors:
            raise ValueError(f"missing source anchors: {environment['id']}")
        task = environment["tasks"][0]
        task_path = (
            f"../environments/{environment['id']}/tasks/{task['id']}/task.json"
        )
        manifest_names = provenance.get(environment["mechanic_id"], [])
        if not manifest_names:
            raise ValueError(f"missing provenance manifest: {environment['id']}")
        manifests = " · ".join(
            f"[manifest]({f'../shared_runtime/assets/provenance/{name}'})" for name in manifest_names
        )
        source_links = "<br>".join(render_source(anchor, source_catalog) for anchor in anchors)
        exact_anchors = "<br>".join(f"`{markdown_cell(anchor)}`" for anchor in anchors)
        lines.append(
            f"| {index} | **{markdown_cell(environment['title'])}**<br>`{environment['id']}` | "
            f"{exact_anchors} | {source_links} | [task metadata]({task_path}) · {manifests} |"
        )

    lines.extend(
        [
            "",
            "## Validation",
            "",
            "The renderer fails if the benchmark does not contain exactly 75 unique environments, any environment has no source anchor, a survey source slug cannot be resolved, a selected local evidence file is absent, or an environment has no checked-in transformation manifest.",
            "",
            "The 75 environments are later expanded into difficulty, interaction, and real-time configurations. Those controls do not change the source provenance recorded here.",
            "",
        ]
    )

    OUTPUT.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
