from __future__ import annotations

import json
import math
import time
from pathlib import Path

from playwright.sync_api import expect


MECHANIC_ID="portal_freight_oversized_parcel"


def _read(path:Path)->dict:return json.loads(path.read_text(encoding="utf-8"))
def _shot(page,out_dir:Path,mechanic:str,name:str)->None:out_dir.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(out_dir/f"{mechanic}-{name}.png"),full_page=True)
def _wait_new(state_dir:Path,before:str)->None:
    deadline=time.time()+8
    while time.time()<deadline:
        if str(_read(state_dir/"ground_truth.json").get("challenge_id"))!=before:return
        time.sleep(.05)
    raise AssertionError("portal freight challenge did not regenerate")


def fail_once(page,state_dir:Path,out_dir:Path,mechanic:str)->None:
    if mechanic!=MECHANIC_ID:raise AssertionError(mechanic)
    before=str(_read(state_dir/"ground_truth.json")["challenge_id"]);page.locator("#freight-submit").click();_wait_new(state_dir,before)
    expect(page.locator(".portal-freight[data-fresh-failure='true']")).to_be_visible(timeout=8_000);expect(page.locator(".readout")).to_contain_text("FAIL");_shot(page,out_dir,mechanic,"fail-fresh-manifest")


def _screen_point(space:str,point:list[float],room:dict)->tuple[float,float]:
    rect={"A":(34.0,48.0,375.0,365.0),"B":(491.0,48.0,375.0,365.0)}[space]
    return rect[0]+float(point[0])/float(room["width"])*rect[2],rect[1]+float(point[2])/float(room["depth"])*rect[3]


def _canvas_point(page,x:float,y:float)->tuple[float,float]:
    box=page.locator("#freight-canvas").bounding_box()
    if box is None:raise AssertionError("portal freight canvas has no visible bounds")
    return box["x"]+x/900.0*box["width"],box["y"]+y/468.0*box["height"]


def _canvas_click(page,x:float,y:float,button:str="left")->None:
    point=_canvas_point(page,x,y);page.mouse.click(point[0],point[1],button=button)


def _canvas_drag(page,start:tuple[float,float],delta:tuple[float,float])->None:
    x,y=_canvas_point(page,*start);target=_canvas_point(page,start[0]+delta[0],start[1]+delta[1]);page.mouse.move(x,y);page.mouse.down();page.mouse.move(target[0],target[1],steps=5);page.mouse.up()


def _portal_matrix_vector(matrix:list[list[float]],vector:list[float])->list[float]:
    return [sum(float(matrix[row][column])*float(vector[column]) for column in range(3)) for row in range(3)]


def _direct_portals(page,truth:dict)->None:
    room=truth["room"]
    def inside(frame:dict)->list[float]:
        return [float(frame["origin"][index])+float(frame["normal"][index])*.12 for index in range(3)]
    _canvas_click(page,*_screen_point("A",inside(truth["solution"]["blue"]["frame"]),room))
    _canvas_click(page,*_screen_point("B",inside(truth["solution"]["orange"]["frame"]),room),button="right")
    linked=page.locator(".portal-freight").get_attribute("data-linked")
    if linked!="true":
        raise AssertionError(
            "direct portal placement did not link frames: "
            f"blue={page.locator('#blue-ledger').inner_text()!r}, "
            f"orange={page.locator('#orange-ledger').inner_text()!r}, linked={linked!r}"
        )


def _direct_rotate(page,truth:dict)->None:
    room,parcel=truth["room"],truth["parcel"]
    angle=float(parcel["initial_angle_deg"]);step=float(truth["controls"]["rotate_step_deg"]);delta=float(truth["solution"]["rotation_delta"])
    center=_screen_point("A",parcel["initial_center"],room)
    for _ in range(int(truth["solution"]["rotation_count"])):
        axis=(math.cos(math.radians(angle))*375.0/float(room["width"]),math.sin(math.radians(angle))*365.0/float(room["depth"]))
        length=max(1.0,math.hypot(*axis));perpendicular=(-axis[1]/length*34.0*(1 if delta>0 else -1),axis[0]/length*34.0*(1 if delta>0 else -1))
        _canvas_drag(page,center,perpendicular);angle+=delta


def _direct_push_point(truth:dict,center_x:float)->tuple[tuple[float,float],tuple[float,float]]:
    room,parcel=truth["room"],truth["parcel"]
    matrix=truth["solution"]["matrix"]
    for index in range(int(parcel["display_samples"])):
        x=center_x-float(parcel["length"])/2+float(parcel["length"])*index/(int(parcel["display_samples"])-1)
        point=[x,float(parcel["initial_center"][1]),float(parcel["initial_center"][2])]
        if x<=float(room["width"])+1e-8:
            return _screen_point("A",point,room),(30.0,0.0)
        mapped=[sum(float(matrix[row][column])*point[column] for column in range(3))+float(matrix[row][3]) for row in range(3)]
        vector=_portal_matrix_vector(matrix,[1.0,0.0,0.0])
        return _screen_point("B",mapped,room),(vector[0]*375.0/float(room["width"])*30.0,vector[2]*365.0/float(room["depth"])*30.0)
    raise AssertionError("portal freight parcel has no display sample")


def _solve_full(page,truth:dict,out_dir:Path,mechanic:str)->None:
    _direct_portals(page,truth)
    root=page.locator(".portal-freight");expect(root).to_have_attribute("data-linked","true");expect(page.locator("#matrix-ledger")).to_contain_text("DET +1");_shot(page,out_dir,mechanic,"linked-right-handed-frames")
    _direct_rotate(page,truth);_shot(page,out_dir,mechanic,"parcel-aligned-to-aperture")
    center_x=float(truth["parcel"]["initial_center"][0]);step=float(truth["controls"]["push_step"]);captured_split=False;evidence_split_ticks=max(3,int(truth["qualification"]["minimum_split_ticks"]))
    for _ in range(int(truth["solution"]["push_count"])):
        start,delta=_direct_push_point(truth,center_x);_canvas_drag(page,start,delta);center_x+=step
        split_ticks=int(page.locator("#split-ledger").text_content() or "0")
        if not captured_split and root.get_attribute("data-split")=="true" and split_ticks>=evidence_split_ticks:_shot(page,out_dir,mechanic,"parcel-spanning-both-frames");captured_split=True
    if not captured_split:raise AssertionError("parcel never visibly occupied both portal frames")


def solve(page,state_dir:Path,out_dir:Path,mechanic:str)->None:
    if mechanic!=MECHANIC_ID:raise AssertionError(mechanic)
    expect(page.locator('.portal-freight[data-active="true"]')).to_be_visible(timeout=8_000);truth=_read(state_dir/"ground_truth.json")
    interaction=str((truth.get("control_condition") or {}).get("interaction") or "simplified")
    if interaction=="full":_solve_full(page,truth,out_dir,mechanic)
    else:
        blue_aim=int(truth["solution"]["blue"]["aim_delta"])
        for _ in range(int(truth["solution"]["blue"]["aim_count"])):page.locator(f'[data-aim="{blue_aim}"]').click()
        page.locator('[data-fire="blue"]').click();page.locator('[data-portal-space="B"]').click();orange_aim=int(truth["solution"]["orange"]["aim_delta"])
        for _ in range(int(truth["solution"]["orange"]["aim_count"])):page.locator(f'[data-aim="{orange_aim}"]').click()
        page.locator('[data-fire="orange"]').click()
        root=page.locator(".portal-freight");expect(root).to_have_attribute("data-linked","true");expect(page.locator("#matrix-ledger")).to_contain_text("DET +1");_shot(page,out_dir,mechanic,"linked-right-handed-frames")
        delta=int(truth["solution"]["rotation_delta"])
        for _ in range(int(truth["solution"]["rotation_count"])):page.locator(f'[data-parcel-rotate="{delta}"]').click()
        _shot(page,out_dir,mechanic,"parcel-aligned-to-aperture")
        captured_split=False
        evidence_split_ticks=max(3,int(truth["qualification"]["minimum_split_ticks"]))
        for _ in range(int(truth["solution"]["push_count"])):
            page.locator(f'[data-parcel-push="{truth["controls"]["push_step"]}"]').click()
            split_ticks=int(page.locator("#split-ledger").text_content() or "0")
            if not captured_split and root.get_attribute("data-split")=="true" and split_ticks>=evidence_split_ticks:_shot(page,out_dir,mechanic,"parcel-spanning-both-frames");captured_split=True
        if not captured_split:raise AssertionError("parcel never visibly occupied both portal frames")
    root=page.locator(".portal-freight")
    expect(root).to_have_attribute("data-delivered","true");expect(root).to_have_attribute("data-collisions","0");expect(page.locator("#parcel-ledger")).to_have_text("RECEIVED")
    state={
        "linked":root.get_attribute("data-linked"),
        "delivered":root.get_attribute("data-delivered"),
        "split":int(page.locator("#split-ledger").inner_text() or "0"),
        "collisions":int(page.locator("#collision-ledger").inner_text() or "0"),
    }
    if state["linked"]!="true" or state["delivered"]!="true" or state["split"]<int(truth["qualification"]["minimum_split_ticks"]) or state["collisions"]!=0:raise AssertionError(f"freight qualification incomplete: {state}")
    _shot(page,out_dir,mechanic,"receiver-containment-green");page.locator("#freight-submit").click();expect(page.locator(".readout")).to_have_text("PASS",timeout=8_000)
