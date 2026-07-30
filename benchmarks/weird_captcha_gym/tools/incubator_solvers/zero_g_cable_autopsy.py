from __future__ import annotations

import json
import math
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID = "zero_g_cable_autopsy"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(page, out_dir: Path, mechanic: str, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True);page.screenshot(path=str(out_dir/f"{mechanic}-{name}.png"),full_page=True)


def _wait_new(state_dir: Path, before: str) -> None:
    deadline=time.time()+8
    while time.time()<deadline:
        if str(_read(state_dir/"ground_truth.json").get("challenge_id"))!=before:return
        time.sleep(.05)
    raise AssertionError("zero-g challenge did not regenerate")


def fail_once(page,state_dir:Path,out_dir:Path,mechanic:str)->None:
    if mechanic!=MECHANIC_ID:raise AssertionError(mechanic)
    before=str(_read(state_dir/"ground_truth.json")["challenge_id"])
    if page.locator(".cable-autopsy").get_attribute("data-interaction") == "full":
        page.keyboard.press("Enter")
    else:
        page.locator("#cable-submit").click()
    _wait_new(state_dir,before)
    expect(page.locator(".cable-autopsy[data-fresh-failure='true']")).to_be_visible(timeout=8_000);expect(page.locator(".readout")).to_contain_text("FAIL");_shot(page,out_dir,mechanic,"fail-fresh-autopsy")


def _normalize(value:list[float])->list[float]:
    size=math.sqrt(sum(item*item for item in value));return [item/size for item in value]


def _sub(a:list[float],b:list[float])->list[float]:return [a[i]-b[i] for i in range(3)]
def _dot(a:list[float],b:list[float])->float:return sum(a[i]*b[i] for i in range(3))


def _project(point:list[float],camera:dict,canvas:dict)->tuple[float,float]:
    yaw=math.radians(camera["yaw_deg"]);pitch=math.radians(camera["pitch_deg"]);target=camera["target"];distance=camera["distance"]
    eye=[target[0]+distance*math.cos(pitch)*math.sin(yaw),target[1]+distance*math.sin(pitch),target[2]+distance*math.cos(pitch)*math.cos(yaw)]
    forward=_normalize(_sub(target,eye));right=_normalize([forward[2],0,-forward[0]]);up=_normalize([right[1]*forward[2]-right[2]*forward[1],right[2]*forward[0]-right[0]*forward[2],right[0]*forward[1]-right[1]*forward[0]])
    relative=_sub(point,eye);depth=_dot(relative,forward);focal=canvas["width"]/(2*math.tan(math.radians(camera["fov_deg"]/2)))
    return canvas["width"]/2+_dot(relative,right)/depth*focal,canvas["height"]/2-_dot(relative,up)/depth*focal


def _canvas_click(page,truth:dict,node_index:int)->None:
    canvas=page.locator("#cable-canvas");box=canvas.bounding_box()
    if not box:raise AssertionError("cable canvas missing")
    px,py=_project(truth["nodes"][node_index],truth["initial_camera"],truth["canvas"])
    page.mouse.click(box["x"]+px/truth["canvas"]["width"]*box["width"],box["y"]+py/truth["canvas"]["height"]*box["height"])


def _move(page,gripper:str,axis:str,direction:int,count:int,interaction:str)->None:
    if interaction == "full":
        page.keyboard.press("Digit1" if gripper == "A" else "Digit2")
        key = {
            ("x", -1): "KeyA", ("x", 1): "KeyD", ("y", -1): "KeyS",
            ("y", 1): "KeyW", ("z", -1): "KeyQ", ("z", 1): "KeyE",
        }[(axis, direction)]
        for _ in range(count):
            page.keyboard.press(key)
        return
    page.locator(f'[data-gripper-select="{gripper}"]').click()
    for _ in range(count):page.locator(f'[data-gripper-move="{axis}:{direction}"]').click()


def solve(page,state_dir:Path,out_dir:Path,mechanic:str)->None:
    if mechanic!=MECHANIC_ID:raise AssertionError(mechanic)
    root=page.locator('.cable-autopsy[data-active="true"]');expect(root).to_be_visible(timeout=8_000);truth=_read(state_dir/"ground_truth.json")
    interaction=root.get_attribute("data-interaction") or "simplified"
    if interaction == "full":
        canvas=page.locator("#cable-canvas");box=canvas.bounding_box()
        if not box:raise AssertionError("cable canvas missing")
        page.mouse.move(box["x"]+box["width"]*.72,box["y"]+box["height"]*.28)
        page.mouse.down();page.mouse.move(box["x"]+box["width"]*.80,box["y"]+box["height"]*.20);page.mouse.up()
        page.mouse.move(box["x"]+box["width"]*.80,box["y"]+box["height"]*.20)
        page.mouse.down();page.mouse.move(box["x"]+box["width"]*.72,box["y"]+box["height"]*.28);page.mouse.up()
    else:
        for selector in ('[data-orbit="yaw:15"]','[data-orbit="pitch:10"]'):page.locator(selector).click()
    _shot(page,out_dir,mechanic,"orbited-depth-inspection")
    if interaction == "full":
        page.keyboard.press("Digit1")
    else:
        for selector in ('[data-orbit="pitch:-10"]','[data-orbit="yaw:-15"]'):page.locator(selector).click()
        page.locator('[data-gripper-select="A"]').click()
    _canvas_click(page,truth,0)
    if interaction == "full":
        page.keyboard.press("KeyX")
        expect(page.locator("#gripper-A-status")).to_have_text("FREE")
        page.keyboard.press("Digit1")
        _canvas_click(page,truth,0)
        page.keyboard.press("Backspace")
        expect(page.locator("#gripper-A-status")).to_have_text("FREE")
        expect(page.locator("#gripper-B-status")).to_have_text("FREE")
        _shot(page,out_dir,mechanic,"direct-recovery-bindings")
        page.keyboard.press("Digit1")
        _canvas_click(page,truth,0)
    if interaction == "full":page.keyboard.press("Digit2")
    else:page.locator('[data-gripper-select="B"]').click()
    _canvas_click(page,truth,len(truth["nodes"])-1)
    expect(page.locator("#gripper-A-status")).to_contain_text("NODE 0");expect(page.locator("#gripper-B-status")).to_contain_text(f"NODE {len(truth['nodes']) - 1}");_shot(page,out_dir,mechanic,"dual-grippers-attached")
    up=int(truth["solution"]["up_moves"])
    for _ in range(up):_move(page,"A","y",1,1,interaction);_move(page,"B","y",1,1,interaction)
    _shot(page,out_dir,mechanic,"cable-lifted-clear")
    outward=int(truth["solution"]["outward_moves"])
    for _ in range(outward):_move(page,"A","x",-1,1,interaction);_move(page,"B","x",1,1,interaction)
    for _ in range(2):
        if interaction == "full":page.keyboard.press("Space")
        else:page.locator("#cable-settle").click()
    root=page.locator(".cable-autopsy");expect(root).to_have_attribute("data-ring-count",str(len(truth["rings"])));expect(root).to_have_attribute("data-alarm","false");expect(root).to_have_attribute("data-clear","true")
    state=page.evaluate("() => ({rings:[...document.querySelectorAll('[data-ring-ledger]')].map(x=>x.dataset.passed), alarm:document.getElementById('alarm-ledger').dataset.alarm, clear:document.querySelector('.cable-autopsy').dataset.clear})")
    if state!={"rings":["true"]*len(truth["rings"]),"alarm":"false","clear":"true"}:raise AssertionError(f"autopsy not clear: {state}")
    _shot(page,out_dir,mechanic,"solved-topology-clean")
    if interaction == "full":page.keyboard.press("Enter")
    else:page.locator("#cable-submit").click()
    expect(page.locator(".readout")).to_have_text("PASS",timeout=8_000)
