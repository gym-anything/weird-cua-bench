"""Privileged oracle for Timber Knot Release.

It reads the generated solution only to choose ordinary visible mouse input;
the browser still performs every selection, drag, collision check, and submit.
"""
from __future__ import annotations

import json
from pathlib import Path
from playwright.sync_api import expect


def fail_once(page, out_dir):
    before = page.locator(".timber-knot").get_attribute("data-challenge-id")
    page.locator("#tk-start").click(force=True)
    page.locator("#tk-submit").click(force=True)
    expect(page.locator(".timber-knot")).not_to_have_attribute("data-challenge-id", before, timeout=30_000)
    page.screenshot(path=str(out_dir / "failure-fresh.png"))
    assert page.evaluate("timberKnotModel.events.length === 0 && !timberKnotModel.started")


def _drag_piece(page, piece_id, direction):
    data = page.evaluate("""([id, direction]) => {
        const p = window.timberKnotModel.pieces.find(x => x.id === id);
        const c = window.TimberKnotModel.center(window.timberKnotModel, p);
        const v = window.TimberKnotModel.axisVector(window.timberKnotModel, p.axis);
        const centers = window.timberKnotModel.pieces
            .filter(q => !window.timberKnotModel.released.has(q.id) && q.id !== id)
            .map(q => window.TimberKnotModel.center(window.timberKnotModel, q));
        const candidates = [c];
        for (const radius of [12, 24, 36, 48, 60]) for (let i = 0; i < 24; i++) {
            const angle = i * Math.PI / 12;
            const x = c[0] + Math.cos(angle) * radius;
            const y = c[1] + Math.sin(angle) * radius;
            if (x >= 6 && x <= 894 && y >= 6 && y <= 554) candidates.push([x, y]);
        }
        // The browser's visible-beam hit test chooses the nearest projected
        // center.  Maximize the nearest-other minus target distance so a
        // crowded isometric knot remains reachable by an ordinary drag.
        const score = point => centers.length
            ? Math.min(...centers.map(q => Math.hypot(point[0] - q[0], point[1] - q[1]))) - Math.hypot(point[0] - c[0], point[1] - c[1])
            : Infinity;
        const start = candidates.reduce((best, point) => score(point) > score(best) ? point : best, c);
        const canvas = document.querySelector('.timber-knot canvas');
        const rect = canvas.getBoundingClientRect();
        const sx = rect.width / 900, sy = rect.height / 560;
        return {
            x: rect.left + start[0] * sx,
            y: rect.top + start[1] * sy,
            tx: rect.left + (start[0] + v[0] * direction * 42) * sx,
            ty: rect.top + (start[1] + v[1] * direction * 42) * sy,
        };
    }""", [piece_id, direction])
    page.mouse.move(data["x"], data["y"])
    page.mouse.down()
    page.mouse.move(data["tx"], data["ty"], steps=5)
    page.mouse.up()


def solve(page, state_dir, out_dir):
    public = json.loads((Path(state_dir) / "public_state.json").read_text())
    truth = json.loads((Path(state_dir) / "ground_truth.json").read_text())
    full = (public.get("control_condition") or {}).get("interaction") == "full"
    page.screenshot(path=str(out_dir / "initial.png"))
    page.locator("#tk-start").click(force=True)
    shot = False
    if full:
        for event in truth["solution"]:
            before = page.evaluate("timberKnotModel.events.length")
            _drag_piece(page, event["piece"], event["direction"])
            after = page.evaluate("timberKnotModel.events")
            assert len(after) == before + 1 and after[-1].get("kind") == "move" and after[-1].get("piece") == event["piece"], after[-3:]
            if not shot:
                page.screenshot(path=str(out_dir / "active-shift.png"))
                shot = True
    else:
        for event in truth["solution"]:
            page.locator(f'[data-select="{event["piece"]}"]').click(force=True)
            page.locator(f'[data-step="{event["piece"]}"]').click(force=True)
            if not shot:
                page.screenshot(path=str(out_dir / "active-shift.png"))
                shot = True
    assert page.evaluate("timberKnotModel.released.size === timberKnotModel.pieces.length"), "oracle did not release every beam"
    page.screenshot(path=str(out_dir / "solved-before-submit.png"))
    page.locator("#tk-submit").click(force=True)
    expect(page.locator(".tk-readout")).to_have_attribute("data-status", "passed", timeout=30_000)
    page.screenshot(path=str(out_dir / "pass.png"))
