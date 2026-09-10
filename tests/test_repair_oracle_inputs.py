"""Oracle regressions: planning may be privileged; effects remain native UI."""
from unittest.mock import Mock
from pathlib import Path

import pytest

from weird_captcha_gym.tools.incubator_solvers.five_second_rule import _solve_flick
from weird_captcha_gym.tools.incubator_solvers.letter_rapids import _wait_output
from weird_captcha_gym.tools.incubator_solvers.ballast_lantern import _click_winch
from weird_captcha_gym.tools.verify_task_ui import check_solver_actions


@pytest.mark.parametrize('direction,vector', [('NORTH',(0,-1)),('EAST',(1,0)),('SOUTH',(0,1)),('WEST',(-1,0))])
@pytest.mark.parametrize('size', [(820,390),(1500,790),(690,400)])
def test_flick_uses_logical_field_travel(direction, vector, size):
    page = Mock()
    def locator(selector):
        node = Mock()
        node.bounding_box.return_value = (
            dict(x=10,y=20,width=size[0],height=size[1]) if selector=='.fsr-stage'
            else dict(x=300,y=200,width=80,height=90)
        )
        return node
    page.locator.side_effect = locator
    spec = dict(predicate=dict(target_id='cargo'),flick=dict(
        flick_direction=direction,min_travel_px=100,face_angle_deg=90,angle_tolerance_deg=15,
    ))
    _solve_flick(page,spec,'full')
    start,end = [call.args for call in page.mouse.move.call_args_list]
    logical = ((end[0]-start[0])*820/size[0],(end[1]-start[1])*390/size[1])
    assert logical == pytest.approx((vector[0]*124,vector[1]*124))
    page.mouse.down.assert_called_once_with()
    page.mouse.up.assert_called_once_with()
    page.evaluate.assert_not_called()


def test_letter_commit_wait_has_no_assertion_backoff():
    page = Mock()
    _wait_output(page,'ABC',1234)
    assert page.wait_for_function.call_args.kwargs == dict(arg='ABC',polling=5,timeout=1234)
    page.evaluate.assert_not_called()


@pytest.mark.parametrize('engaged', [False, True])
def test_ballast_terminal_race_keeps_input_native(engaged):
    page = Mock()
    button = page.locator.return_value
    button.bounding_box.return_value = dict(x=10, y=20, width=80, height=40)
    _click_winch(page, engaged)
    page.locator.assert_called_once_with('.ballast-haul' if engaged else '.ballast-coast')
    page.mouse.click.assert_called_once_with(50, 40)
    button.click.assert_not_called()
    page.evaluate.assert_not_called()


@pytest.mark.parametrize('action', [
    'page.locator("select").select_option("2")',
    'page.locator("input").fill("x")',
    'page.locator("input").set_checked(True)',
    'page.dispatch_event("button", "click")',
    'page.evaluate("document.querySelector(\'button\').click()")',
    'page.evaluate("WeirdCaptchaTime.runFor(100)")',
    'page.goto("https://example.invalid")',
    'page.reload()',
    'page.add_script_tag(content="doSomething()")',
])
def test_ui_harness_rejects_nonprimitive_oracle_effects(tmp_path, action):
    source=tmp_path/'oracle.py'
    source.write_text('def solve(page):\n    '+action+'\n')
    with pytest.raises(AssertionError):check_solver_actions(source)


def test_ui_harness_allows_privileged_reads_and_native_input(tmp_path):
    source=tmp_path/'oracle.py'
    source.write_text('def solve(page):\n    state=page.evaluate("model.state")\n    page.mouse.click(10,20)\n    page.keyboard.press("ArrowLeft")\n')
    check_solver_actions(source)


@pytest.mark.parametrize('mechanic', [
    'apothecary_dead_reckoning','cell_gatekeeper','cloudstep_caddie','facet_lantern',
    'lanternfin_dive','pearl_lattice','coordinates_by_another_name','crackglaze_crossing',
    'hearthlift_courier','lantern_loft','pocket_locksmith','reflow_vitrine','unlabeled_drawer',
    'cloudpost_circuit','concertina_courier','rayglass_vault','five_second_rule',
    'letter_rapids','clockbeat_catacomb','lampwrights_program',
])
def test_repaired_oracle_sources_pass_primitive_action_lint(mechanic):
    check_solver_actions(Path('weird_captcha_gym/tools/incubator_solvers')/(mechanic+'.py'))
