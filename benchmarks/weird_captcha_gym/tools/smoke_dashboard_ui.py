#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


BENCHMARK_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exercise and capture the CAPTCHA Bench visual dashboard.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8767")
    parser.add_argument("--out-dir", default=str(BENCHMARK_ROOT / "dashboard" / "evidence"))
    parser.add_argument("--exercise-reviews", action="store_true", help="Mutate the connected review ledger to test approve/revision persistence; use only with an isolated review path")
    return parser.parse_args()


def capture(page, output: Path, name: str, *, full_page: bool = True) -> None:
    page.screenshot(path=str(output / f"{name}.png"), full_page=full_page)


def main() -> None:
    args = parse_args()
    output = Path(args.out_dir)
    output.mkdir(parents=True, exist_ok=True)
    review_only_evidence = {
        "review-queue.png",
        "environment-review-revision.png",
        "environment-review-approved.png",
        "mobile-review-queue.png",
        "mobile-review-desk.png",
    }
    for name in (
        "observatory.png",
        "capability-filter.png",
        "capability-detail.png",
        "starred-shortlist.png",
        "shared-starred-shortlist.png",
        "environment-search.png",
        "environment-detail.png",
        "review-queue.png",
        "environment-review-revision.png",
        "environment-review-approved.png",
        "mobile-review-queue.png",
        "mobile-review-desk.png",
        "evaluation-preview.png",
        "live-sessions-empty.png",
        "interaction-five-built.png",
        "interaction-five-detail.png",
        "interaction-six-built.png",
        "interaction-six-detail.png",
        "interaction-seven-built.png",
        "interaction-seven-detail.png",
        "interaction-eight-built.png",
        "interaction-eight-detail.png",
        "final-eleven-review-dossier.png",
        "roadmap-concepts.png",  # stale pre-promotion captures
        "roadmap-detail.png",
        "interaction-six-roadmap.png",
        "incubator-candidates.png",
        "incubator-detail.png",
        "incubator-built.png",
        "incubator-built-detail.png",
        "atlas-overview.png",
        "atlas-specimen.png",  # legacy flat-Atlas evidence name
        "atlas-item.png",
        "atlas-instances.png",
        "atlas-instance.png",
        "atlas-source.png",
        "atlas-compare.png",
        "mobile-environments.png",
        "mobile-atlas.png",
        "summary.json",
    ):
        if not args.exercise_reviews and name in review_only_evidence:
            continue
        (output / name).unlink(missing_ok=True)
    errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(args.base_url, wait_until="networkidle")
        expect(page.locator(".display-title")).to_contain_text("screenshot")
        expect(page.locator("#nav-environment-count")).to_have_text("75")
        expect(page.locator('[data-nav="atlas"]')).to_have_count(0)
        expect(page.locator('[data-nav="reviews"]')).to_be_visible()
        expect(page.locator(".specimen-card")).to_have_count(3)
        expect(page.locator(".capability-spectrum-grid button")).to_have_count(7)
        expect(page.locator(".atlas-home-portal")).to_have_count(0)
        expect(page.locator('[data-open-env="shadow_crime_lab_env"]')).to_have_count(1)
        expect(page.locator('[data-open-env="robot_art_critic_env"]')).to_have_count(1)
        capture(page, output, "observatory")

        stars_context = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        stars_page = stars_context.new_page()
        stars_page.on("pageerror", lambda exc: errors.append(f"stars: {exc}"))
        stars_page.goto(f"{args.base_url}/#/environments", wait_until="networkidle")
        expect(stars_page.locator(".environment-card")).to_have_count(75)
        domino_star = stars_page.locator('[data-open-env="domino_autopsy_env"] [data-star-environment="domino_autopsy_env"]')
        funeral_star = stars_page.locator('[data-open-env="funeral_ritual_env"] [data-star-environment="funeral_ritual_env"]')
        domino_star.click()
        funeral_star.focus()
        stars_page.keyboard.press("Enter")
        expect(stars_page.locator(".detail-page")).to_have_count(0)
        expect(domino_star).to_have_attribute("aria-pressed", "true")
        expect(funeral_star).to_have_attribute("aria-pressed", "true")
        expect(stars_page.locator('[data-action="share-stars"] [data-personal-star-count]')).to_have_text("2")
        expect(stars_page.locator('[data-action="toggle-star-filter"] b')).to_have_text("2")
        stored_stars = stars_page.evaluate("localStorage.getItem('captcha-bench-starred-environments:v1')")
        if json.loads(stored_stars or "[]") != ["domino_autopsy_env", "funeral_ritual_env"]:
            raise AssertionError(f"unexpected persisted stars: {stored_stars}")
        stars_page.locator('[data-action="toggle-star-filter"]').click()
        expect(stars_page.locator(".environment-card")).to_have_count(2)
        expect(stars_page.locator('[data-open-env="domino_autopsy_env"]')).to_have_count(1)
        expect(stars_page.locator('[data-open-env="funeral_ritual_env"]')).to_have_count(1)
        capture(stars_page, output, "starred-shortlist")
        stars_page.locator('[data-action="share-stars"]').click()
        share_url = stars_page.locator("#star-share-url").input_value()
        if not share_url.startswith("https://gym-anything.github.io/weird-cua-bench/?stars="):
            raise AssertionError(f"local dashboard produced a non-public shortlist URL: {share_url}")
        if "domino_autopsy_env" not in share_url or "funeral_ritual_env" not in share_url:
            raise AssertionError(f"shortlist URL omitted a star: {share_url}")
        stars_page.locator(".modal-close").click()
        stars_context.close()

        shared_stars_context = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        shared_stars_page = shared_stars_context.new_page()
        shared_stars_page.on("pageerror", lambda exc: errors.append(f"shared stars: {exc}"))
        shared_stars_page.goto(
            f"{args.base_url}/?stars=domino_autopsy_env,funeral_ritual_env#/environments",
            wait_until="networkidle",
        )
        expect(shared_stars_page.locator(".star-share-banner")).to_be_visible()
        expect(shared_stars_page.locator(".environment-card")).to_have_count(2)
        expect(shared_stars_page.locator('[data-action="toggle-star-filter"]')).to_be_disabled()
        expect(shared_stars_page.locator(".star-toggle-card")).to_have_count(2)
        expect(shared_stars_page.locator(".star-toggle-card").first).to_be_disabled()
        if shared_stars_page.evaluate("localStorage.getItem('captcha-bench-starred-environments:v1')") is not None:
            raise AssertionError("opening a shared shortlist overwrote personal browser stars")
        capture(shared_stars_page, output, "shared-starred-shortlist")
        shared_stars_page.locator('[data-action="save-shared-stars"]').click()
        expect(shared_stars_page.locator(".star-share-banner")).to_have_count(0)
        expect(shared_stars_page.locator(".environment-card")).to_have_count(2)
        if "stars=" in shared_stars_page.url:
            raise AssertionError(f"saving the shared shortlist left its query parameter behind: {shared_stars_page.url}")
        saved_shared_stars = shared_stars_page.evaluate("localStorage.getItem('captcha-bench-starred-environments:v1')")
        if json.loads(saved_shared_stars or "[]") != ["domino_autopsy_env", "funeral_ritual_env"]:
            raise AssertionError(f"shared shortlist did not save locally: {saved_shared_stars}")
        shared_stars_context.close()

        capability_page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        capability_page.on("pageerror", lambda exc: errors.append(f"capabilities: {exc}"))
        capability_page.goto(f"{args.base_url}/#/environments", wait_until="networkidle")
        expect(capability_page.locator(".capability-badge-card")).to_have_count(75)
        capability_page.locator("#capability-filter").select_option("adaptation_feedback")
        expect(capability_page.locator(".environment-card")).to_have_count(6)
        expect(capability_page.locator(".capability-badge-card b")).to_have_text(["A"] * 6)
        capture(capability_page, output, "capability-filter")
        capability_page.locator('[data-open-env="robot_art_critic_env"] .card-media').click()
        expect(capability_page.locator(".capability-panel")).to_be_visible()
        expect(capability_page.locator(".capability-primary h3")).to_have_text("Adaptation from feedback")
        expect(capability_page.locator(".capability-panel blockquote")).to_contain_text("Revise a drawing")
        expect(capability_page.locator(".capability-supporting span")).to_have_count(3)
        capture(capability_page, output, "capability-detail")
        capability_page.close()

        if args.exercise_reviews:
            expect(page.locator("#nav-review-count")).to_have_text("75")
            page.locator('[data-nav="reviews"]').click()
            expect(page.locator(".reviews-page")).to_be_visible()
            expect(page.locator(".review-ledger-stamp")).to_contain_text("0 / 75")
            expect(page.locator(".review-grid .environment-card")).to_have_count(75)
            expect(page.locator('.review-summary [data-review-filter="pending"] b')).to_have_text("75")
            capture(page, output, "review-queue")

            page.locator("#review-search").fill("domino")
            expect(page.locator(".review-grid .environment-card")).to_have_count(1)
            page.locator('.review-grid [data-open-env="domino_autopsy_env"] .card-media').click()
            expect(page.locator(".detail-title")).to_have_text("Domino Autopsy")
            expect(page.locator('[data-action="open-review-desk"]')).to_contain_text("Review · Pending")
            page.locator('[data-action="open-review-desk"]').click()
            expect(page.locator("#review-desk")).to_have_attribute("data-review-status", "pending")
            page.locator('[data-review-choice="looks_good"]').click()
            page.locator('#environment-review-form [name="note"]').fill("AUTOMATED UI FIXTURE — solution-film screening only; hands-on acceptance remains pending.")
            page.locator('#environment-review-form [type="submit"]').click()
            expect(page.locator("#review-desk")).to_have_attribute("data-review-status", "looks_good")
            expect(page.locator("#detail-review-state")).to_have_text("Looks good · hands-on pending")
            expect(page.locator("#nav-review-count")).to_have_text("75")
            page.locator('[data-review-choice="revision_requested"]').click()
            page.locator('#environment-review-form [name="note"]').fill("AUTOMATED UI FIXTURE — exercises revision feedback; this is not a human verdict.")
            page.locator(".detail-page").evaluate("node => { node.dataset.stabilityProbe = 'review-save'; }")
            page.locator('#environment-review-form [type="submit"]').click()
            expect(page.locator("#review-desk")).to_have_attribute("data-review-status", "revision_requested")
            expect(page.locator("#detail-review-state")).to_have_text("Needs revision")
            expect(page.locator(".detail-page")).to_have_attribute("data-stability-probe", "review-save")
            expect(page.locator(".review-history-wrap summary")).to_contain_text("2")
            page.locator("#review-desk").evaluate("node => node.scrollIntoView({block: 'start'})")
            page.wait_for_timeout(120)
            capture(page, output, "environment-review-revision", full_page=False)

            page.locator('[data-review-choice="approved"]').click()
            page.locator('#environment-review-form [name="note"]').fill("AUTOMATED UI FIXTURE — exercises approval persistence; this is not human evidence.")
            page.locator('#environment-review-form [type="submit"]').click()
            expect(page.locator("#review-desk")).to_have_attribute("data-review-status", "approved")
            expect(page.locator("#detail-review-state")).to_have_text("Approved")
            expect(page.locator('[data-action="open-review-desk"]')).to_contain_text("Review · Approved")
            expect(page.locator(".review-history-wrap summary")).to_contain_text("3")
            expect(page.locator("#nav-review-count")).to_have_text("74")
            page.locator("#review-desk").evaluate("node => node.scrollIntoView({block: 'start'})")
            page.wait_for_timeout(120)
            capture(page, output, "environment-review-approved", full_page=False)

            persisted = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
            persisted.on("pageerror", lambda exc: errors.append(f"review persistence: {exc}"))
            persisted.goto(f"{args.base_url}/#/environment/domino_autopsy_env", wait_until="networkidle")
            expect(persisted.locator("#review-desk")).to_have_attribute("data-review-status", "approved")
            expect(persisted.locator('#environment-review-form [name="note"]')).to_have_value("AUTOMATED UI FIXTURE — exercises approval persistence; this is not human evidence.")
            persisted.close()

            page.locator('[data-action="back-to-reviews"]').click()
            page.locator('[data-review-filter="approved"]').last.click()
            expect(page.locator(".review-grid .environment-card")).to_have_count(1)
            expect(page.locator('.review-grid .card-review[data-review-status="approved"]')).to_have_count(1)

        page.locator('[data-nav="environments"]').click()
        expect(page.locator("#environment-search")).to_be_visible()
        expect(page.locator("#review-filter")).to_be_visible()
        expect(page.locator(".environment-card")).to_have_count(75)
        expect(page.locator('#stage-filter option[value="concept"]')).to_have_count(0)
        expect(page.locator('#stage-filter option[value="scaffold"]')).to_have_count(0)
        page.locator(".environments-page").evaluate("node => { node.dataset.stabilityProbe = 'catalog'; }")
        page.locator("#environment-search").fill("domino")
        expect(page.locator(".environment-card")).to_have_count(1)
        expect(page.locator(".environment-card h3")).to_have_text("Domino Autopsy")
        expect(page.locator(".environments-page")).to_have_attribute("data-stability-probe", "catalog")
        if args.exercise_reviews:
            page.locator("#review-filter").select_option("approved")
            expect(page.locator(".environment-card")).to_have_count(1)
            expect(page.locator('.card-review[data-review-status="approved"]')).to_have_count(1)
            page.locator("#review-filter").select_option("revision_requested")
            expect(page.locator(".environment-card")).to_have_count(0)
            page.locator("#review-filter").select_option("all")
            expect(page.locator(".environment-card")).to_have_count(1)
        page.locator('[data-view="compact"]').click()
        expect(page.locator("#environment-grid")).to_have_class("environment-grid is-compact")
        expect(page.locator(".environments-page")).to_have_attribute("data-stability-probe", "catalog")
        capture(page, output, "environment-search")

        page.locator('.environment-card[data-open-env="domino_autopsy_env"] .card-media').click()
        expect(page.locator(".detail-title")).to_have_text("Domino Autopsy")
        expect(page.locator(".filmstrip button")).to_have_count(5)
        expect(page.locator(".launch-console")).to_contain_text("One-click browser play")
        page.locator(".detail-page").evaluate("node => { node.dataset.stabilityProbe = 'gallery'; }")
        page.locator(".filmstrip button").nth(1).click()
        expect(page.locator(".hero-frame-label")).to_contain_text("EVIDENCE FRAME 02")
        expect(page.locator("#modal-root")).to_be_empty()
        expect(page.locator(".detail-page")).to_have_attribute("data-stability-probe", "gallery")
        capture(page, output, "environment-detail")

        page.locator('[data-config-launch="domino_autopsy_env"]').first.click()
        expect(page.locator("#launch-mode")).to_have_value("browser")
        expect(page.locator('#launch-mode option[value="vnc"]')).to_have_count(1)
        expect(page.locator("#launch-form")).to_contain_text("real local UI and grader")
        page.locator(".modal-close").click()

        solution = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        solution.on("pageerror", lambda exc: errors.append(f"solution video: {exc}"))
        solution.goto(f"{args.base_url}/#/environment/semantic_drag_drop_absurdity_env", wait_until="networkidle")
        expect(solution.locator('[data-solution-video="semantic_drag_drop_absurdity"]')).to_be_visible()
        expect(solution.locator('.solution-reel source[type="video/mp4"]')).to_have_attribute(
            "src", "/media/evidence/reviewed_overhaul_v1/semantic_drag_drop_absurdity-walkthrough.mp4"
        )
        solution.locator(".solution-reel > summary").click()
        expect(solution.locator(".solution-reel")).to_have_attribute("open", "")
        solution.wait_for_function("document.querySelector('.solution-reel video').readyState >= 1")
        expect(solution.locator(".solution-reel video")).to_have_js_property("videoWidth", 1280)
        expect(solution.locator(".solution-reel video")).to_have_js_property("videoHeight", 720)
        solution.close()

        new_solution = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        new_solution.on("pageerror", lambda exc: errors.append(f"interaction seven solution video: {exc}"))
        new_solution.goto(f"{args.base_url}/#/environment/specular_lighthouse_relay_env", wait_until="networkidle")
        expect(new_solution.locator('[data-solution-video="specular_lighthouse_relay"]')).to_be_visible()
        expect(new_solution.locator('.solution-reel source[type="video/mp4"]')).to_have_attribute(
            "src", "/media/evidence/interaction_vii_viii_difficulty_v2/solution_videos/specular_lighthouse_relay-solution.mp4"
        )
        new_solution.locator(".solution-reel > summary").click()
        expect(new_solution.locator(".solution-reel")).to_have_attribute("open", "")
        new_solution.wait_for_function("document.querySelector('.solution-reel video').readyState >= 1")
        expect(new_solution.locator(".solution-reel video")).to_have_js_property("videoWidth", 1280)
        expect(new_solution.locator(".solution-reel video")).to_have_js_property("videoHeight", 720)
        expect(new_solution.locator(".solution-reel-notes")).to_contain_text("frozen · unchanged")
        new_solution.close()

        pending_solution = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        pending_solution.on("pageerror", lambda exc: errors.append(f"pending v3 solution video: {exc}"))
        pending_solution.goto(f"{args.base_url}/#/environment/impossible_ecology_env", wait_until="networkidle")
        expect(pending_solution.locator('[data-solution-video="impossible_ecology"]')).to_be_visible()
        expect(pending_solution.locator('.solution-reel source[type="video/mp4"]')).to_have_attribute(
            "src", "/media/evidence/pending_next_ten_v3/solution_videos/impossible_ecology-solution.mp4"
        )
        expect(pending_solution.locator("#review-desk")).to_have_attribute("data-review-status", "looks_good")
        pending_solution.locator(".solution-reel > summary").click()
        expect(pending_solution.locator(".solution-reel")).to_have_attribute("open", "")
        pending_solution.wait_for_function("document.querySelector('.solution-reel video').readyState >= 1")
        expect(pending_solution.locator(".solution-reel video")).to_have_js_property("videoWidth", 1280)
        expect(pending_solution.locator(".solution-reel video")).to_have_js_property("videoHeight", 720)
        expect(pending_solution.locator(".solution-reel-notes")).to_contain_text("frozen · unchanged")
        pending_solution.close()

        complete_coverage = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        complete_coverage.on("pageerror", lambda exc: errors.append(f"complete solution coverage: {exc}"))
        coverage_samples = (
            ("domino_autopsy", "foundational_seven_v1"),
            ("magnetic_stripe_purgatory", "remaining_modular_fourteen_v1"),
        )
        for mechanic_id, evidence_set in coverage_samples:
            complete_coverage.goto(
                f"{args.base_url}/#/environment/{mechanic_id}_env",
                wait_until="networkidle",
            )
            expect(complete_coverage.locator(f'[data-solution-video="{mechanic_id}"]')).to_be_visible()
            expect(complete_coverage.locator('.solution-reel source[type="video/mp4"]')).to_have_attribute(
                "src", f"/media/evidence/{evidence_set}/solution_videos/{mechanic_id}-solution.mp4"
            )
            complete_coverage.locator(".solution-reel > summary").click()
            complete_coverage.wait_for_function(
                "document.querySelector('.solution-reel video').readyState >= 1"
            )
            expect(complete_coverage.locator(".solution-reel video")).to_have_js_property("videoWidth", 1280)
            expect(complete_coverage.locator(".solution-reel video")).to_have_js_property("videoHeight", 720)
            expect(complete_coverage.locator(".solution-reel-notes")).to_contain_text("frozen · unchanged")
        complete_coverage.close()

        final_solution = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        final_solution.on("pageerror", lambda exc: errors.append(f"final eleven solution video: {exc}"))
        final_eleven = (
            ("shadow_crime_lab", "looks_good"),
            ("trajectory_catcher", "looks_good"),
            ("jigsaw_slider_alignment", "looks_good"),
            ("microgame_gauntlet", "looks_good"),
            ("minecraft_block_grid", "looks_good"),
            ("relation_prompt_grounding", "looks_good"),
            ("rorschach_fixed_rubric", "looks_good"),
            ("single_scene_split_boxes", "looks_good"),
            ("top_face_dice_arithmetic", "looks_good"),
            ("trace_shape_without_walls", "looks_good"),
            ("wizard_critter_capture", "looks_good"),
        )
        for index, (mechanic_id, review_status) in enumerate(final_eleven):
            final_solution.goto(
                f"{args.base_url}/#/environment/{mechanic_id}_env",
                wait_until="networkidle",
            )
            expect(final_solution.locator(f'[data-solution-video="{mechanic_id}"]')).to_be_visible()
            expect(final_solution.locator('.solution-reel source[type="video/mp4"]')).to_have_attribute(
                "src", f"/media/evidence/final_eleven_v1/solution_videos/{mechanic_id}-solution.mp4"
            )
            expect(final_solution.locator("#review-desk")).to_have_attribute(
                "data-review-status", review_status
            )
            final_solution.locator(".solution-reel > summary").click()
            final_solution.wait_for_function(
                "document.querySelector('.solution-reel video').readyState >= 1"
            )
            expect(final_solution.locator(".solution-reel video")).to_have_js_property("videoWidth", 1280)
            expect(final_solution.locator(".solution-reel video")).to_have_js_property("videoHeight", 720)
            expect(final_solution.locator(".solution-reel-notes")).to_contain_text("frozen · unchanged")
            if index == 0:
                capture(final_solution, output, "final-eleven-review-dossier")
        final_solution.close()

        page.locator('[data-open-eval="domino_autopsy_env"]').first.click()
        expect(page.locator("#eval-form")).to_be_visible()
        expect(page.locator('[name="preview_only"]')).to_be_checked()
        page.locator("#eval-model").fill("Qwen/Qwen3-VL-4B-Thinking")
        page.locator("#eval-form [type=submit]").click()
        expect(page.locator(".evaluations-page")).to_be_visible()
        expect(page.locator(".status-pill").filter(has_text="preview").first).to_be_visible()
        expect(page.locator(".eval-command").first).to_contain_text("weird_captcha_gym")
        page.locator(".evaluations-page").evaluate("node => { node.dataset.stabilityProbe = 'evaluation-poll'; }")
        eval_details = page.locator("[data-toggle-eval]").first
        eval_details.focus()
        page.wait_for_timeout(2100)
        expect(page.locator(".evaluations-page")).to_have_attribute("data-stability-probe", "evaluation-poll")
        expect(eval_details).to_be_focused()
        capture(page, output, "evaluation-preview")

        page.locator('[data-nav="sessions"]').click()
        expect(page.locator(".sessions-page")).to_be_visible()
        expect(page.locator(".empty-state")).to_contain_text("No specimens are awake")
        page.locator(".sessions-page").evaluate("node => { node.dataset.stabilityProbe = 'session-poll'; }")
        empty_launch = page.locator(".empty-state [data-action='open-launch-picker']")
        empty_launch.focus()
        page.wait_for_timeout(2100)
        expect(page.locator(".sessions-page")).to_have_attribute("data-stability-probe", "session-poll")
        expect(empty_launch).to_be_focused()
        capture(page, output, "live-sessions-empty")

        page.keyboard.press("Meta+k")
        expect(page.locator("#palette-input")).to_be_focused()
        page.locator("#palette-input").fill("funeral")
        expect(page.locator(".palette-item")).to_have_count(1)
        page.keyboard.press("Escape")

        interaction_five = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        interaction_five.on("pageerror", lambda exc: errors.append(f"interaction five: {exc}"))
        interaction_five.goto(f"{args.base_url}/#/environments", wait_until="networkidle")
        interaction_five.locator('[data-filter-group="Interaction V"]').click()
        expect(interaction_five.locator(".environment-card")).to_have_count(5)
        expect(interaction_five.locator(".quick-launch")).to_have_count(5)
        expect(interaction_five.locator('[data-open-env="photograph_eats_the_room_env"]')).to_have_count(1)
        expect(interaction_five.locator('[data-open-env="forced_perspective_moving_day_env"]')).to_have_count(1)
        capture(interaction_five, output, "interaction-five-built")
        interaction_five.locator('[data-open-env="photograph_eats_the_room_env"] .card-media').click()
        expect(interaction_five.locator(".detail-title")).to_have_text("The Photograph Eats the Room")
        expect(interaction_five.locator(".launch-console")).to_contain_text("WIRING REPLAY PASSED · HUMAN REVIEW PENDING")
        expect(interaction_five.locator("[data-config-launch]")).to_have_count(1)
        expect(interaction_five.locator(".archive-chip")).to_have_count(0)
        capture(interaction_five, output, "interaction-five-detail")
        interaction_five.close()

        interaction_six = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        interaction_six.on("pageerror", lambda exc: errors.append(f"interaction six: {exc}"))
        interaction_six.goto(f"{args.base_url}/#/environments", wait_until="networkidle")
        interaction_six.locator('[data-filter-group="Interaction VI"]').click()
        expect(interaction_six.locator(".environment-card")).to_have_count(5)
        expect(interaction_six.locator(".quick-launch")).to_have_count(5)
        expect(interaction_six.locator('[data-open-env="lidar_blacksite_env"]')).to_have_count(1)
        expect(interaction_six.locator('[data-open-env="portal_freight_oversized_parcel_env"]')).to_have_count(1)
        capture(interaction_six, output, "interaction-six-built")
        interaction_six.locator('[data-open-env="tomographic_baggage_surgery_env"] .card-media').click()
        expect(interaction_six.locator(".detail-title")).to_have_text("Tomographic Baggage Surgery")
        expect(interaction_six.locator(".launch-console")).to_contain_text("WIRING REPLAY PASSED · HUMAN REVIEW PENDING")
        expect(interaction_six.locator("[data-config-launch]")).to_have_count(1)
        expect(interaction_six.locator(".archive-chip")).to_have_count(0)
        capture(interaction_six, output, "interaction-six-detail")
        interaction_six.close()

        interaction_seven = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        interaction_seven.on("pageerror", lambda exc: errors.append(f"interaction seven: {exc}"))
        interaction_seven.goto(f"{args.base_url}/#/environments", wait_until="networkidle")
        interaction_seven.locator('[data-filter-group="Interaction VII"]').click()
        expect(interaction_seven.locator(".environment-card")).to_have_count(5)
        expect(interaction_seven.locator(".quick-launch")).to_have_count(5)
        expect(interaction_seven.locator('[data-open-env="specular_lighthouse_relay_env"]')).to_have_count(1)
        expect(interaction_seven.locator('[data-open-env="gravity_room_freight_env"]')).to_have_count(1)
        capture(interaction_seven, output, "interaction-seven-built")
        interaction_seven.locator('[data-open-env="orbital_docking_customs_env"] .card-media').click()
        expect(interaction_seven.locator(".detail-title")).to_have_text("Orbital Docking Customs")
        expect(interaction_seven.locator(".launch-console")).to_contain_text("WIRING REPLAY PASSED · HUMAN REVIEW PENDING")
        expect(interaction_seven.locator("[data-config-launch]")).to_have_count(1)
        expect(interaction_seven.locator('[data-solution-video="orbital_docking_customs"]')).to_be_visible()
        capture(interaction_seven, output, "interaction-seven-detail")
        interaction_seven.close()

        interaction_eight = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        interaction_eight.on("pageerror", lambda exc: errors.append(f"interaction eight: {exc}"))
        interaction_eight.goto(f"{args.base_url}/#/environments", wait_until="networkidle")
        interaction_eight.locator('[data-filter-group="Interaction VIII"]').click()
        expect(interaction_eight.locator(".environment-card")).to_have_count(5)
        expect(interaction_eight.locator(".quick-launch")).to_have_count(5)
        expect(interaction_eight.locator('[data-open-env="floodgate_archive_rescue_env"]')).to_have_count(1)
        expect(interaction_eight.locator('[data-open-env="marionette_checkpoint_env"]')).to_have_count(1)
        capture(interaction_eight, output, "interaction-eight-built")
        interaction_eight.locator('[data-open-env="pheromone_dispatch_env"] .card-media').click()
        expect(interaction_eight.locator(".detail-title")).to_have_text("Pheromone Dispatch")
        expect(interaction_eight.locator(".launch-console")).to_contain_text("WIRING REPLAY PASSED · HUMAN REVIEW PENDING")
        expect(interaction_eight.locator("[data-config-launch]")).to_have_count(1)
        expect(interaction_eight.locator('[data-solution-video="pheromone_dispatch"]')).to_be_visible()
        capture(interaction_eight, output, "interaction-eight-detail")
        interaction_eight.close()

        incubator = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        incubator.on("pageerror", lambda exc: errors.append(f"incubator: {exc}"))
        incubator.goto(f"{args.base_url}/#/environments", wait_until="networkidle")
        incubator.locator("#stage-filter").select_option("built")
        incubator.locator('[data-filter-group="Incubator"]').click()
        expect(incubator.locator(".environment-card")).to_have_count(23)
        expect(incubator.locator(".quick-launch")).to_have_count(23)
        expect(incubator.locator('[data-open-env="insider_trading_captcha_env"]')).to_have_count(1)
        expect(incubator.locator('[data-open-env="thirty_year_time_wheel_env"]')).to_have_count(1)
        capture(incubator, output, "incubator-built")
        incubator.locator('[data-open-env="insider_trading_captcha_env"] .card-media').click()
        expect(incubator.locator(".detail-title")).to_have_text("Insider Trading CAPTCHA")
        expect(incubator.locator(".launch-console")).to_contain_text("WIRING REPLAY PASSED · HUMAN REVIEW PENDING")
        expect(incubator.locator("[data-config-launch]")).to_have_count(1)
        expect(incubator.locator(".roadmap-chip")).to_have_count(0)
        expect(incubator.locator(".detail-page")).to_have_css("opacity", "1")
        capture(incubator, output, "incubator-built-detail")
        incubator.close()

        mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        mobile.on("pageerror", lambda exc: errors.append(f"mobile: {exc}"))
        mobile.goto(f"{args.base_url}/#/environments", wait_until="networkidle")
        expect(mobile.locator("#environment-search")).to_be_visible()
        mobile.locator(".mobile-nav-toggle").click()
        expect(mobile.locator("body")).to_have_class("nav-open")
        expect(mobile.locator(".sidebar")).to_have_css("transform", "matrix(1, 0, 0, 1, 0, 0)")
        capture(mobile, output, "mobile-environments", full_page=False)
        mobile.close()

        if args.exercise_reviews:
            mobile_review = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
            mobile_review.on("pageerror", lambda exc: errors.append(f"mobile review: {exc}"))
            mobile_review.goto(f"{args.base_url}/#/reviews", wait_until="networkidle")
            expect(mobile_review.locator(".review-ledger-stamp")).to_contain_text("1 / 75")
            expect(mobile_review.locator(".review-filter-tabs")).to_be_visible()
            capture(mobile_review, output, "mobile-review-queue", full_page=False)
            mobile_review.goto(f"{args.base_url}/#/environment/domino_autopsy_env", wait_until="networkidle")
            expect(mobile_review.locator('[data-action="open-review-desk"]')).to_contain_text("Review · Approved")
            mobile_review.locator('[data-action="open-review-desk"]').click()
            mobile_review.locator("#review-desk").evaluate("node => window.scrollTo({top: window.scrollY + node.getBoundingClientRect().top - 73, behavior: 'instant'})")
            mobile_review.wait_for_timeout(180)
            expect(mobile_review.locator("#review-desk")).to_have_attribute("data-review-status", "approved")
            capture(mobile_review, output, "mobile-review-desk", full_page=False)
            mobile_review.close()
        browser.close()

    if errors:
        raise AssertionError(f"dashboard browser errors: {errors}")
    summary = {
        "ok": True,
        "screenshots": sorted(path.name for path in output.glob("*.png")),
        "checks": [
            "catalog-derived stats",
            *([
                "persistent human review queue",
                "revision request with required feedback",
                "approval transition with immutable decision history",
                "review persistence across browser pages",
                "review save without page-level reconstruction",
                "responsive review queue and decision desk",
                "review status filtering on the environment catalog",
            ] if args.exercise_reviews else []),
            "personal star persistence and keyboard-safe card controls",
            "starred-only catalog filtering",
            "public shortlist URL generation",
            "shared shortlist isolation and save-to-personal flow",
            "seven-capability observatory overview",
            "primary capability badges on all 75 environments",
            "primary capability filtering",
            "environment capability rationale and supporting labels",
            "environment search",
            "catalog controls without page reconstruction",
            "screenshot detail gallery",
            "gallery swap without page-level transition",
            "dual-format Semantic Drag-Drop solution playback",
            "seven foundational frozen-contract solution reels",
            "fourteen remaining modular frozen-contract solution reels",
            "ten frozen-contract Interaction VII–VIII solution reels",
            "ten frozen-contract pending-v3 solution reels with looks-good review state",
            "eleven frozen-contract final-cohort reels with looks-good review state",
            "safe evaluation command preview",
            "poll-stable evaluation focus",
            "live-session empty state",
            "poll-stable session focus",
            "command palette",
            "Survey-free navigation and Observatory",
            "local-browser-first launch controls with preserved VNC mode",
            "zero concept and scaffold cards",
            "five launchable Interaction V builds and evidence dossier",
            "five launchable Interaction VI builds and evidence dossier",
            "five launchable Interaction VII builds and evidence dossier",
            "five launchable Interaction VIII builds and evidence dossier",
            "twenty-three launchable Incubator builds",
            "Incubator built dossier",
            "responsive navigation",
        ],
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
