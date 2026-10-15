"""
관제 여섯 화면의 데이터 — 실시간 관제 · 격리 목록 대조 · 이벤트 로그 · 재생 비교 · 피드백 · 히트맵 · 통계.

화면(web/static)은 시안 그대로의 HTML 이고, 여기 있는 함수가 control/ 의 기능을 불러 JSON 으로 돌려준다.
판단은 전부 control/ · monitor_engine/ 에 있다 — 여기는 모양만 바꾼다.
"""
from __future__ import annotations

import shutil
import tempfile
import time
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from control import detfp, eventlog, feedback, isolation, quality, replay, scenes, stats
from control.common import (DOCGEN_SPACE, clock_text, dashboard, frame_file, load_config, load_control_events,
                            package, ruleset_status, system_now, zone_name, zones)
from control.session import RULESETS, SESSION

router = APIRouter(prefix="/api")

KIND_T = {"gate": "작업 전 게이트", "accident": "사고", "info": "참고", "stage": "3축 판정", "check": "모드 규칙(영상)"}


def hm(t) -> str:
    return f"{t:%H:%M}" if t else ""


def _cams() -> list[dict]:
    return list(package().cameras.values())


def _cam_polys(cam: dict, scene: dict | None) -> list[dict]:
    """카메라 자리 그림의 구역 — 지금 세션의 영상 장면에 그린 구역(같은 카메라)만. 카메라 기본 구역은 쓰지 않는다 (10/8)."""
    polys = (scene.get("polygons") or []) if scene and scene.get("camera") == cam["camera_id"] else []
    return [{"label": p.get("label") or p.get("name"), "type": p.get("type"), "points": p.get("points")}
            for p in polys if p.get("space", "image") == "image"]


# ====================================================================== 공통 — 메뉴 · 머리글
def _schedule_meta(pkg, key: str) -> dict:
    """시나리오 한 개 — 영상 장면 목록. 실시간 관제는 시나리오 타임라인을 넣지 않는다(재생 비교 전용)."""
    sc = pkg.scenario(key)
    return {"key": key, "title": sc.title, "video_check": bool(sc.data.get("video_check")),
            "scenes": [{"name": x["name"], "camera": x.get("camera"), "own": bool(x.get("polygons")),
                        "video": x.get("video") or ""} for x in sc.scenes()],
            "videos": scenes.video_list(key)}       # 시연 설정의 영상 목록 — 영상마다 묶고 최근 올린 순


@router.get("/meta")
def meta():
    """화면을 처음 열 때 한 번 — 구역 · 카메라 · 스케줄 · 규칙셋 · 버튼 · 작업 종류 · 담당자."""
    from safety_docs.config import load_profile, load_staff, staff_label, use_sample_data
    from safety_docs.voice import KINDS, STATES
    from safety_docs.compliance import load_obligations
    pkg = package()
    cfg = load_config()
    demo = dashboard().get("demo", {})
    pip = isolation.piping()
    keys = pkg.scenario_keys()
    sched0 = demo.get("schedule") if demo.get("schedule") in keys else ""
    focus = demo.get("focus_zone") if demo.get("focus_zone") in zones() else (zones()[0] if zones() else None)
    prof = load_profile()
    return {
        "package": pkg.root.name, "site_name": prof.get("site_name", ""), "sample": use_sample_data(),
        "zones": [{"id": z, "name": zone_name(z), "cams": [c["camera_id"] for c in _cams() if c.get("zone") == z],
                   "piping": bool(pip.get(z, {}).get("lines")), "equip": pip.get(z, {}).get("equipment") or "",
                   "lines": [x["line_id"] for x in pip.get(z, {}).get("lines", [])]} for z in zones()],
        "cams_total": len(pkg.cameras),
        "zone_types": [{"key": k, "label": v["label"], "color": v["color"], "builtin": v["builtin"]} for k, v in scenes.all_types().items()],
        "schedules": [_schedule_meta(pkg, k) for k in keys],
        "rulesets": [{"key": k, "label": v} for k, v in RULESETS.items()] + [{"key": i, "label": f"{i}만"} for i in pkg.change_ids()],
        "work_types": [k for k in cfg["work_types"] if not k.startswith("_")],
        "live": {"schedule": sched0, "scene": (demo.get("scene") or "") if sched0 else "",
                 "ruleset": cfg["live"].get("ruleset", "docgen")},
        # 3축 신호 버튼 (10/8) — 패키지 buttons.json 에서 group 이 있는 것만. 누르면 지금 시각으로 엔진에 들어간다
        "buttons": [{"key": k, "label": b.get("label") or b["signal"], "group": b["group"], "zone": b.get("zone") or ""}
                    for k, b in pkg.buttons.items() if b.get("group")],
        "fp_reasons": quality.FP_REASONS, "dets": [{"key": k, "label": v} for k, v in quality.DET.items()],
        # 오탐 · 미탐 처리 방식 (10/8 오후) — 첫 번째가 기본값
        "fp_actions": {k: [{"v": v, "t": t} for v, t in xs] for k, xs in detfp.ACTIONS.items()},
        "miss_actions": [{"v": v, "t": t} for v, t in quality.MISS_ACTIONS],
        "focus_zone": focus,
        "staff": [{"id": p["id"], "label": staff_label(p), "name": p["name"]} for p in load_staff()],
        "voice": {"kinds": KINDS, "states": STATES},
        "profile": {"industry": prof.get("industry", ""), "workers": prof.get("workers", 0),
                    "hazardous": bool(prof.get("hazardous_agents"))},
        "industries": ["1차 금속 제조업", "기타 제조업"],
        "duty_cats": load_obligations()["categories"],
    }


_badge = {"t": 0.0, "v": {}}


def badges() -> dict:
    """메뉴 옆 숫자 — 3초에 한 번만 센다."""
    if time.time() - _badge["t"] < 3:
        return _badge["v"]
    from safety_docs.assessment import list_assessments
    from safety_docs.config import load_events, load_profile, load_scales
    from safety_docs.corrective import list_correctives
    from safety_docs.handoff import list_handoffs
    from safety_docs.home import home_summary
    from safety_docs.voice import list_reports, voice_summary
    s = SESSION.snapshot()
    now = system_now()
    evs, as_of = load_events()
    prof = load_profile()
    from control.common import demo_day
    h = home_summary(evs, as_of, load_scales(), prof, demo_day())
    issued = {c["event_id"] for c in list_correctives()}
    by_id = {e["event_id"]: e for e in evs}
    todo = set()
    for ho in list_handoffs(include_auto=False):
        for i in ho.get("event_ids", []):
            e = by_id.get(i)
            if e and e.get("alerted") and e.get("level") in ("경보", "최고 경보") and i not in issued:
                todo.add(i)
    v = {"live": sum(1 for st in s["zones"].values() if st["alerting"] and st["level"] != "정상"),
         "iso": sum(1 for p in isolation.ptws() if isolation.view(p)["kind"] in ("crit", "warn")),
         "feedback": len(feedback.active(now)) + len(feedback.pending()),
         "home": h["cards"][0]["num"],
         "docs": len(todo),
         "voice": voice_summary(list_reports())["open"] + sum(1 for ra in list_assessments() if ra["state"] == "worker_pending")}
    _badge.update(t=time.time(), v=v)
    return v


@router.get("/status")
def status():
    """머리글 · 메뉴 숫자 · 경보 팝업 — 화면이 2초마다 읽는다."""
    s = SESSION.snapshot()
    rs = ruleset_status()
    on = [(z, st["modes"]) for z, st in s["zones"].items() if st["modes"]]
    alarms = []
    for z, st in s["zones"].items():
        if st["alerting"] and st["level"] != "정상":
            alarms.append({"key": f"{z}|{st['level']}|{st['since']:%H%M%S}" if st.get("since") else f"{z}|{st['level']}",
                           "zone": z, "name": zone_name(z), "level": st["level"], "row": st.get("row"),
                           "since": hm(st.get("since")), "reason": st.get("reason") or st.get("violation") or "",
                           "rule": st.get("rule") or "", "title": st.get("title") or "",
                           "response": st.get("response") or "", "adj": s["adjust"].get(z, {}).get("adj_ids", [])})
    order = {"최고 경보": 3, "경보": 2, "주의": 1}
    alarms.sort(key=lambda a: -order.get(a["level"], 0))
    incidents = [{"key": r["event_id"], "id": r["event_id"], "kind": r["kind"], "zone": r.get("zone"),
                  "name": zone_name(r.get("zone")), "t": r["ts"][11:16], "reason": r.get("reason") or r.get("violation_type") or ""}
                 for r in s["rows"] if r.get("kind") in ("gate", "accident")]
    return {"now": s["now"].isoformat(timespec="seconds"), "sid": s["sid"], "running": s["running"], "speed": s["speed"],
            "modes_on": sum(len(x) for _, x in on), "zones_on": len(on),
            "ruleset": {"version": rs["version"], "ids": rs["ids"]}, "feedback_mode": feedback.mode(),
            "video": bool(s.get("video")), "scene": (s.get("scene") or {}).get("name") or "",   # 머리줄 '영상' 칩
            "badges": badges(), "alarms": alarms, "incidents": incidents}


# ====================================================================== 1. 실시간 관제
def _axes(st: dict) -> list[dict]:
    out = []
    for name, a in (st.get("axes") or {}).items():
        out.append({"name": name, "state": a.state, "tone": a.tone, "why": list(dict.fromkeys(a.why)),
                    "why_not": list(a.why_not[:2])})
    return out


def _judge(st: dict) -> list[dict]:
    t = st.get("tdef")
    if not t:
        return []
    hit = st.get("row") if st.get("computed") != "정상" else None
    vio = st.get("violation")
    rows = []
    for r in t.get("rows", []) + [t.get("default", {})]:
        n = r.get("row")
        # 같은 번호의 줄이 둘 이상이면(예: 7번 '축적 단독' · '허가 · 측정이 끝난 점화원') 위반 이름까지 맞는 줄만 칠한다
        same_n = n is not None and n == hit
        rows.append({"n": n, "label": r.get("label") or r.get("violation") or "그 외", "level": r.get("level", "정상"),
                     "violation": r.get("violation") or "",
                     "hit": same_n and (not vio or not r.get("violation") or r.get("violation") == vio)})
    return rows


def _ptw_cards(zone: str) -> list[dict]:
    out = []
    for p in sorted((p for p in isolation.ptws() if p["zone"] == zone), key=lambda x: x.get("start", ""), reverse=True)[:3]:
        v = isolation.view(p)
        out.append({"id": p["ptw_id"], "work": p["work"], "type": p.get("type", ""), "kind": v["kind"], "tag": v["tag"],
                    "clear": v["clear"], "when": f"{p.get('start', '')[5:16].replace('T', ' ')} ~ {p.get('end', '')[11:16]}"})
    return out


def _causes_view(causes, violation=None) -> list[dict] | None:
    """세부 원인 (STEP 03-3 보완) — 화면에 쓸 모양. causes 가 없으면 None (원인을 따지지 않는 줄 · 과거 기록)."""
    if causes is None:
        return None
    return [{"code": c.get("code"), "label": c.get("label"), "point": c.get("point"), "detail": c.get("detail"),
             "t": (c.get("ts") or "")[11:16], "value": c.get("value"), "limit": c.get("limit"), "sub": c.get("sub_label")}
            for c in causes]


def _ev_title(e: dict) -> str:
    """최근 기록 줄 이름 — 짧은 줄 이름 + 세부 원인. 세부 원인 필드가 없는 기록은 내부 코드 그대로 (과거 기록 호환)."""
    t, aware = e.get("title"), e.get("causes") is not None
    if not t and e.get("kind", "stage") == "stage" and e.get("row"):
        rows = package().rules_base.get("judgments", {}).get(e.get("table") or "폭발", {}).get("rows", [])
        hit = next((r for r in rows if r.get("row") == e["row"] and r.get("violation") == e.get("violation_type")), None)
        if hit and hit.get("causes"):                  # 원인을 남기는 줄인데 이 기록에는 원인 필드가 없다 = 과거 기록
            t, aware = hit.get("short") or hit.get("label"), True
    if not t or not aware:
        return t or ""
    cs = e.get("causes")
    if cs is None:
        return t + " · 세부 원인 미확인"
    labels = list(dict.fromkeys(f"{c.get('label')}" + (f" {c['point']}" if c.get("point") else "") for c in cs))
    return t + (" · " + ", ".join(labels) if labels else "")


def _ev_row(e: dict) -> dict:
    return {"title": _ev_title(e), "id": e["event_id"], "ts": e["ts"], "date": e["ts"][:10], "time": e["ts"][11:16], "zone": e.get("zone") or "",
            "mode": e.get("mode") or "-", "type": e.get("violation_type") or (e.get("reason") or "")[:30],
            "level": e.get("computed_level") or e.get("level"), "alerted": bool(e.get("alerted")),
            "kind": e.get("kind", "stage"), "adj": e.get("adj_id"), "fp": bool(e.get("false_positive")),
            "src": e.get("_src", ""), "frame": bool(e.get("frame_path")), "clip": bool(e.get("clip_path")),
            # 데이터 공간 · 시험/운영/시연 구분 (10/14) — 그 전에 남은 기록은 구분값이 없다('미기록')
            "run_kind": e.get("run_kind") or ("예시" if e.get("_src") == "샘플" else "미기록"), "space": e.get("data_space") or ""}


@router.get("/live")
def live():
    from web.api_docs import adhoc_count
    s = SESSION.snapshot()
    now = s["now"]
    m = s["meta"]
    zs = []
    for z, st in s["zones"].items():
        cams = [c["camera_id"] for c in _cams() if c.get("zone") == z]
        zs.append({"id": z, "name": zone_name(z), "level": st["level"], "computed": st["computed"],
                   "alerting": st["alerting"], "row": st.get("row"), "since": hm(st.get("since")), "rule": st.get("rule") or "",
                   "reason": st.get("reason") or "", "violation": st.get("violation") or "", "modes": st["modes"],
                   "people": st["people"], "ppe": st.get("ppe"), "present": bool(st.get("present")), "response": st.get("response") or "",
                   "table": st.get("table"), "axes": _axes(st), "judge": _judge(st), "cams": cams,
                   "ptws": _ptw_cards(z), "adj": s["adjust"].get(z, {}),
                   "ignition": any((f, z) in s["on"] for f in ("ignition_manual",)),
                   "faults": st.get("faults") or [], "reliability": st.get("reliability"),
                   "title": st.get("title") or "", "causes": _causes_view(st.get("causes"), st.get("violation")),
                   "equip": isolation.piping().get(z, {}).get("equipment") or "",
                   "piping": bool(isolation.piping().get(z, {}).get("lines")),
                   "polys": [q for c in _cams() if c.get("zone") == z for q in _cam_polys(c, s["scene"])]})
    if s["sid"]:
        today = [_ev_row(r) for r in s["rows"]]
        log_src = "이 세션"
    else:
        today = [_ev_row(e) for e in load_control_events() if e["_ts"].date() == now.date()]
        log_src = "오늘 기록"
    rows = s["rows"]
    counts = {"alerts": sum(1 for r in rows if r.get("kind") in ("stage", "check") and r.get("alerted")
                            and r.get("level") in ("경보", "최고 경보")),
              "adhoc": adhoc_count(), "gates": sum(1 for r in rows if r.get("kind") == "gate")}
    scene = s["scene"]
    return {"now": now.isoformat(timespec="seconds"), "sid": s["sid"], "running": s["running"], "speed": s["speed"],
            "video": s["video"], "video_note": s["video_note"],
            "video_pos": [round(x, 1) for x in s["video_pos"]] if s["video_pos"] else None,
            "scene": {"name": scene.get("name"), "camera": scene.get("camera"),
                      "zone": next((c.get("zone") for c in _cams() if c["camera_id"] == scene.get("camera")), None),
                      "video": scene.get("video") or "", "started": s["scene_started"],
                      "own": bool(scene.get("polygons"))} if scene else None,
            "meta": {"schedule": m.get("schedule", ""), "schedule_title": m.get("schedule_title", ""),
                     "ruleset": m.get("ruleset", ""), "rules_label": m.get("rules_label", ""),
                     "start": clock_text(m.get("start")), "scene": m.get("scene", "")},
            "zones": zs, "events": list(reversed(today))[:200], "log_src": log_src,
            "notes": [{"t": f"{t:%H:%M:%S}", "msg": msg} for t, msg in s["notes"][:14]],
            "counts": counts, "frames": sorted(s["frames"]),
            "dets": s.get("dets", []), "det_fp": s.get("det_fp", [])}         # 실시간 탐지 오탐 (10/8)


@router.get("/live/stream/{cam}")
def live_stream(cam: str):
    """
    영상이 도는 동안 그 카메라 화면을 끊김 없이 보낸다 (MJPEG — <img> 하나로 영상처럼 보인다).
    예전에는 화면이 1초마다 사진 한 장(/live/frame)을 받아서 영상이 사진 넘김처럼 보였다.
    영상이 끝나고 3초가 지나면 스트림을 닫는다 — 브라우저는 마지막 프레임을 그대로 보여 준다.
    """
    def gen():
        last, idle = -1, 0.0
        while True:
            no, b = SESSION.frame_no, SESSION.frames.get(cam)
            if b is not None and no != last:
                last, idle = no, 0.0
                yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(b)).encode() + b"\r\n\r\n" + b + b"\r\n")
                continue
            time.sleep(0.02)
            idle = 0.0 if SESSION.video is not None else idle + 0.02
            if idle > 3:
                return
    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


@router.get("/live/frame/{cam}")
def live_frame(cam: str):
    b = SESSION.frames.get(cam)
    if not b:
        return Response(status_code=404)
    return Response(b, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


# ====================================================================== 데이터 공간 (10/14 — dataspace.py)
@router.get("/dataspace")
def dataspace_status():
    """조회 공간 · 다음 세션 저장 공간 · 지금 세션이 기록 중인 공간 · 공간마다 연결 상태와 실제 경로."""
    import dataspace
    d = dataspace.status()
    d["session"] = ({"sid": SESSION.sid, "space": SESSION.space, "run_kind": SESSION.run_kind,
                     "label": dataspace.info(SESSION.space)["label"], "root": dataspace.info(SESSION.space)["root"],
                     "dir": str(SESSION.out_dir) if SESSION.out_dir else ""} if SESSION.sid else None)
    return d


@router.post("/dataspace/view")
def dataspace_view(body: dict):
    """조회 공간 바꾸기 — 저장 공간(새 세션 · 지금 세션)은 바뀌지 않는다."""
    import dataspace
    dataspace.set_view(str(body.get("key") or ""))
    return {**dataspace_status(), "msg": f"조회 공간 — {dataspace.info(dataspace.view_key())['label']}"}


@router.post("/dataspace/write")
def dataspace_write(body: dict):
    """다음에 시작하는 세션의 저장 공간 · 구분값. 지금 돌고 있는 세션은 끝날 때까지 원래 공간에 기록한다."""
    import dataspace
    dataspace.set_write(str(body.get("key") or ""), body.get("run_kind") or None)
    i = dataspace.info(dataspace.write_key())
    msg = f"새 세션 저장 — {i['label']} · {dataspace.write_run_kind()} ({i['root']})"
    if SESSION.sid and SESSION.space != dataspace.write_key():
        msg += f". 지금 세션 {SESSION.sid} 은 끝날 때까지 '{dataspace.info(SESSION.space)['label']}'에 기록한다"
    return {**dataspace_status(), "msg": msg}


def _input_space_guard(what: str):
    """격리 목록 대조 화면은 조회 공간을 보여 준다 — 입력은 저장 공간과 같은 공간을 볼 때만 받는다 (다른 공간에 섞여 들어가지 않게)."""
    import dataspace
    target = SESSION.space if SESSION.sid else dataspace.write_key()
    if dataspace.view_key() != target:
        raise ValueError(f"{what}은(는) 기록 중인 공간 '{dataspace.info(target)['label']}'을(를) 조회할 때만 넣는다 — "
                         f"지금 조회 공간은 '{dataspace.info(dataspace.view_key())['label']}'")


@router.post("/live/session")
def live_session(body: dict):
    SESSION.reset(body.get("schedule") or None, body.get("ruleset") or "docgen", body.get("scene") or None)
    SESSION.start()
    m = SESSION.meta
    return {"msg": f"새 세션 {SESSION.sid} — {m['schedule_title']} · 규칙 {m['rules_label']} · {clock_text(m['start'])} 부터"
                   + (f" · 영상 장면 '{body.get('scene')}'" if body.get("scene") else "")
                   + f" · 저장 {m.get('data_space_label')} · {m.get('run_kind')}",
            "sid": SESSION.sid, "space": SESSION.space, "dir": str(SESSION.out_dir)}


# ====================================================================== 영상 장면 — 영상 올리기 · 구역 그리기
@router.get("/scene/options")
def scene_options(schedule: str):
    return scenes.options(schedule)


@router.post("/scene/upload")
async def scene_upload(schedule: str = Form(...), file: UploadFile = File(...)):
    d = scenes.save_upload(schedule, file.filename or "", file.file)
    return {**d, "msg": f"영상을 올렸다 — {d['file']} ({d['w']}×{d['h']}" + (f" · {d['seconds']:g}초" if d.get("seconds") else "") + ")"}


@router.get("/scene/frame")
def scene_frame(video: str, schedule: str = ""):
    jpg, _ = scenes.first_frame(scenes.resolve_video(video, schedule or None))
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/scene/info")
def scene_info(video: str, schedule: str = ""):
    _, info = scenes.first_frame(scenes.resolve_video(video, schedule or None))
    return info


@router.post("/scene/save")
def scene_save(body: dict):
    d = scenes.save_scene(body)
    SESSION.refresh_scene(body.get("schedule") or "", d.get("name"), body.get("orig") or None)
    return d


@router.post("/scene/type")
def scene_type(body: dict):
    """구역 종류 더하기 · 고치기 (관리자) — 패키지 zone_types.json"""
    return scenes.save_type(body)


@router.post("/scene/type/remove")
def scene_type_remove(body: dict):
    return scenes.remove_type(body)


@router.post("/scene/camera")
def scene_camera(body: dict):
    """카메라 한 대 더하기 — 패키지 cameras/<id>.json (기본 구역 없이)"""
    return scenes.save_camera(body)


@router.post("/scene/camera/remove")
def scene_camera_remove(body: dict):
    return scenes.remove_camera(body)


@router.post("/scene/remove")
def scene_remove(body: dict):
    d = scenes.remove_scene(body)
    SESSION.refresh_scene(body.get("schedule") or "", None, body.get("name"))
    return d


@router.get("/scene/video/records")
def scene_video_records(schedule: str, video: str):
    """삭제 확인 창 — 이 영상으로 돌린 세션 · 관제 기록 수"""
    return scenes.video_records(schedule, video)


@router.post("/scene/video/remove")
def scene_video_remove(body: dict):
    """
    영상 목록에서 영상 하나 지우기 — 그 영상을 쓰는 장면을 빼고, 다른 스케줄도 안 쓰면 파일까지 지운다.
    records=true 면 그 영상으로 돌린 세션의 관제 기록도 같이 지운다.
    """
    busy = None
    if SESSION.video is not None and SESSION.scene:
        busy = scenes._video_key(SESSION.scene.get("video"), (SESSION.meta or {}).get("schedule") or None)
    if body.get("records") and SESSION.sid and busy is None:
        # 지울 기록이 지금 열린 세션 것이면 — 세션을 닫고(기록 없이 미리 보기로) 폴더를 지운다
        info = scenes.video_records(body.get("schedule") or "", body.get("video") or "")
        if SESSION.sid in info["sids"]:
            m = SESSION.meta
            SESSION.pause()
            SESSION.reset(m.get("schedule") or None, m.get("ruleset", "docgen"), None, record=False)
    d = scenes.remove_video(body, busy=busy)
    for name in d["removed"]:
        SESSION.refresh_scene(body.get("schedule") or "", None, name)
    return d


@router.post("/live/play")
def live_play(body: dict):
    if not SESSION.sid:
        return live_session(body)
    if SESSION.running:
        SESSION.pause()
        return {"msg": "멈췄다 — 판정이 선다. 기록은 그대로다."}
    SESSION.start()
    return {"msg": f"계속 — 지금 시각부터 · 세션 {SESSION.sid}"}


@router.post("/live/scene-now")
def live_scene_now(body: dict):
    """
    고른 영상 장면을 지금 관제 화면에 튼다. 세션이 없거나 스케줄 · 장면이 다르면 새 세션부터 시작한다.
    fresh=true(영상 목록의 ▶ 세션 시작)면 늘 새 세션으로 처음부터 다시 돈다.
    """
    if not body.get("scene"):
        raise ValueError("영상을 고른다 — 시연 설정의 영상 목록")
    m = SESSION.meta
    fresh = bool(body.get("fresh")) or not SESSION.sid or (m.get("schedule") or "") != (body.get("schedule") or "") \
        or (m.get("scene") or "") != body["scene"]
    if fresh:
        live_session(body)
    msg = SESSION.play_scene_now()
    return {"msg": ("새 세션 " + SESSION.sid + " · " if fresh else "") + msg, "sid": SESSION.sid}


@router.post("/live/press")
def live_press(body: dict):
    """3축 신호 버튼 (10/8) — 패키지 buttons.json 의 신호 하나를 지금 시각으로 넣는다. 구역 = 버튼의 zone, 없으면 화면에서 고른 구역."""
    key = str(body.get("key") or "")
    b = package().buttons.get(key)
    if not b:
        raise ValueError(f"없는 버튼 ‘{key}’")
    zone = b.get("zone") or body.get("zone") or None          # 구역이 비어 있는 버튼은 화면에서 고른 구역으로
    notes = SESSION.press(key, zone)
    label = b.get("label") or b["signal"]
    extra = f" — {notes[0]}" if notes and not notes[0].startswith(label) else ""
    return {"msg": f"{clock_text(SESSION.clock())} {zone} {label}{extra}"}


@router.post("/live/stop-order")
def live_stop_order(body: dict):
    """작업중지 지시 — 관제실이 지시한 시각을 기록으로 남긴다 (방송 설비와의 연동은 아직 없다)."""
    zone = body.get("zone")
    ev = SESSION.stop_order(zone)
    return {"msg": f"{zone} 작업중지 지시 기록 — {ev['event_id']} ({ev['ts'][11:19]}). 방송 설비 연동은 아직 없어 현장 전달은 무전 · 전화로 한다."}


@router.post("/live/handoff")
def live_handoff(body: dict):
    ids = body.get("event_ids") or None
    ho = SESSION.handoff(ids)
    return {"handoff_id": ho["handoff_id"], "msg": f"{ho['handoff_id']} — 감지 {len(ho['event_ids'])}건 넘김", "space": SESSION.space}


@router.post("/live/corrective")
def live_corrective():
    """시정지시서 초안으로 — 이 세션의 마지막 경보 이상 기록을 넘기고 번호를 돌려준다."""
    rows = [r for r in (SESSION.log.rows if SESSION.sid and SESSION.log else [])
            if r.get("kind") in ("stage", "check") and r.get("alerted") and r.get("level") in ("경보", "최고 경보")]
    if not rows:
        return {"event_id": None, "space": SESSION.space}
    SESSION.handoff([rows[-1]["event_id"]], source="실시간 관제 · 시정지시서")
    return {"event_id": rows[-1]["event_id"], "space": SESSION.space}


# ====================================================================== 2. 격리 목록 대조
_new_ptws: set[str] = set()


def _ptw_row(p: dict, v: dict | None = None) -> dict:
    v = v or isolation.view(p)
    return {"id": p["ptw_id"], "zone": p["zone"], "zname": zone_name(p["zone"]), "work": p["work"], "type": p.get("type", ""),
            "work_type": p.get("work_type") or p.get("type", ""), "start": p.get("start", ""), "end": p.get("end", ""),
            "kind": v["kind"], "tag": v["tag"], "open": v["open"], "new": p["ptw_id"] in _new_ptws,
            "source": p.get("source", ""), "phase": v["phase"], "active": v["active"], "target": v["target"],
            "gate": v["gate"], "clear": v["clear"], "verdict": v["verdict"][0],
            "wait": sum(v["waiting"].values()), "simops": len(v["simops"])}


@router.get("/iso")
def iso_list():
    """허가서 목록 + 맨 위 KPI 네 개 — KPI 는 활성 허가서(오늘 예정 + 진행 중) 전체 기준."""
    ps = sorted(isolation.ptws(), key=lambda x: x.get("start", ""), reverse=True)
    ps.sort(key=lambda x: x["ptw_id"] not in _new_ptws)          # 방금 등록한 것이 맨 앞
    now = system_now()
    views = [(p, isolation.view(p, now=now)) for p in ps]
    act = [(p, v) for p, v in views if v["active"]]
    tgt = [(p, v) for p, v in act if v["target"]]
    wb = {k: sum(v["waiting"][k] for _, v in tgt) for k in ("blind", "gas", "purge")}
    kpi = {"active": len(act), "run": sum(1 for _, v in act if v["phase"] == "진행 중"),
           "plan": sum(1 for _, v in act if v["phase"] == "예정"),
           "gate": sum(1 for _, v in tgt if v["gate"]),
           "gate_ids": [p["ptw_id"] for p, v in tgt if v["gate"]],
           "notclear": sum(1 for _, v in tgt if v["clear"] != "인정"),
           "nontarget": len(act) - len(tgt),
           "wait": sum(wb.values()), "wait_by": wb,
           "zones": sorted({p["zone"] for p, _ in act})}
    return {"now": now.strftime("%H:%M"), "date": now.strftime("%Y-%m-%d"), "kpi": kpi,
            "ptws": [_ptw_row(p, v) for p, v in views]}


@router.get("/iso/{ptw_id}")
def iso_detail(ptw_id: str):
    p = next((x for x in isolation.ptws() if x["ptw_id"] == ptw_id), None)
    if not p:
        raise KeyError(f"없는 작업허가서: {ptw_id}")
    v = isolation.view(p)
    lines = [{"line_id": ln["line_id"], "name": ln["name"], "fluid": ln.get("fluid", ""), "hazard": bool(ln.get("hazard_source")),
              "in_list": ln["in_list"], "blind": ln["blind"], "by_step": bool(ln.get("blind_by_step")),
              "undone": bool(ln.get("blind_undone")), "last": ln.get("blind_last"),
              "target": ln["line_id"] in v["blind_targets"],
              "row": ln.get("row") or {}} for ln in v["check"]["lines"]]
    hist = isolation.history(v)
    ev = isolation.engine_vars()
    from safety_docs.ptw import form_summary
    from web.api_docs import file_url
    return {"ptw": {k: p.get(k) for k in ("ptw_id", "type", "zone", "work", "work_type", "start", "end", "supervisor",
                                          "workers", "source", "registered_at")},
            "zname": zone_name(p["zone"]), "equipment": v["check"]["equipment"], "has_pid": v["check"]["has_pid"],
            "lines": lines, "extra": v["check"]["extra"], "no_list": v["no_list"], "miss": len(v["miss"]),
            "miss_ids": [ln["line_id"] + " " + ln["name"] for ln in v["miss"]],
            "pend": [ln["line_id"] for ln in v["pend"]], "meas": v["meas"], "purge_min": v["purge_min"],
            "purge_need": v["purge_need"], "lel_max": v["lel_max"], "kind": v["kind"], "tag": v["tag"], "bar": v["bar"],
            "clear": v["clear"], "open": v["open"],
            "steps": [{"t": s["ts"][11:16], "kind": s["kind"], "line_id": s.get("line_id"), "value": s.get("value"),
                       "by": s.get("by")} for s in v["steps"]],
            # 화면 개편 (10/6)
            "now": v["now"].strftime("%H:%M"), "phase": v["phase"], "active": v["active"], "target": v["target"],
            "gate": v["gate"], "verdict": {"title": v["verdict"][0], "desc": v["verdict"][1]},
            "conds": v["conds"], "all_ok": v["all_ok"], "waiting": v["waiting"],
            "blind_targets": v["blind_targets"], "blind_wait": v["blind_wait"], "purge": v["purge"],
            "valid_min": v["valid_min"], "simops": v["simops"], "history": hist,
            "doc": file_url(p.get("document_file")), "form": form_summary(p),      # 공통 양식 작성본 (10/8)
            "engine": bool(SESSION.sid),
            "basis": {"purge_need": v["purge_need"], "lel_max": v["lel_max"], "valid_min": v["valid_min"],
                      "invalidated_by": ev.get("measure_invalidated_by") or [],
                      "rules_label": (SESSION.meta.get("rules_label") if SESSION.sid else "") or ""}}


@router.post("/iso/check")
def iso_check(body: dict):
    zone, no_list = body.get("zone"), bool(body.get("no_list"))
    rows = None if no_list else isolation.parse_csv(body.get("csv") or "")
    if not no_list and not rows:
        raise ValueError("격리 목록 CSV 를 올리거나 붙여넣는다. 목록이 없으면 ‘목록 없이 등록’을 켠다")
    chk = isolation.cross_check(zone, rows)
    if not chk["has_pid"]:
        raise ValueError(f"{zone} 에는 배관 계통도가 등록돼 있지 않아 대조할 수 없다. 사업장 패키지 site.json 의 piping 에 먼저 넣는다.")
    return {"lines": [{"line_id": x["line_id"], "name": x["name"], "in_list": x["in_list"], "blind": x["blind"]}
                      for x in chk["lines"]], "extra": chk["extra"], "no_list": no_list}


@router.get("/iso-sample")
def iso_sample(zone: str):
    wts = [k for k in load_config()["work_types"] if not k.startswith("_")]
    day = system_now().date().isoformat()
    return {"work_type": wts[0] if wts else "", "start": f"{day}T13:00", "end": f"{day}T17:00",
            "work": f"{zone_name(zone)} 연결 배관 격리 후 정비", "supervisor": "김정비", "workers": 3,
            "csv": isolation.sample_csv(zone)}


@router.post("/iso/ptw-docx")
async def iso_ptw_docx(file: UploadFile = File(...)):
    """
    작업허가서 파일(작업허가서_양식(공통).docx 를 채운 것) → 등록 창 칸 (10/13).
    읽기만 한다 — 등록은 사람이 '등록'을 눌러서 한다. 올린 파일은 증빙으로 남겨 두고 등록할 때 허가서에 붙인다.
    """
    import hashlib

    from control.ptw_docx import read_ptw_docx
    _input_space_guard("작업허가서 파일")
    raw = await file.read()
    if not (file.filename or "").lower().endswith(".docx"):
        raise ValueError("워드 파일(.docx)을 올린다 — 작업허가서_양식(공통)을 채운 것")
    r = read_ptw_docx(raw)
    d = isolation.RECORD_DIR / "ptw_docx"
    d.mkdir(parents=True, exist_ok=True)
    token = hashlib.sha1(raw).hexdigest()[:16]
    (d / f"{token}.docx").write_bytes(raw)
    return {**r, "token": token, "filename": file.filename}


@router.post("/iso/register")
def iso_register(body: dict):
    _input_space_guard("작업허가서 등록")
    extra = body.get("extra") or None
    tok = str(body.get("docx_token") or "")
    if extra is not None and tok.isalnum():
        src = isolation.RECORD_DIR / "ptw_docx" / f"{tok}.docx"
        if src.exists():
            extra = {**extra, "docx_file": str(src.relative_to(isolation.RECORD_DIR.parent.parent).as_posix())}
    r = isolation.register(body.get("zone"), body.get("work_type"), (body.get("start") or "").strip(),
                           (body.get("end") or "").strip(), body.get("work") or "", body.get("supervisor") or "",
                           body.get("workers") or None, body.get("csv"), bool(body.get("no_list")),
                           ptw_id=body.get("ptw_id") or None, extra=extra)
    p, chk = r["ptw"], r["check"]
    _new_ptws.add(p["ptw_id"])
    v = isolation.view(p)
    msg = f"{p['ptw_id']} 등록됨 — 대조 결과: {v['tag']}"
    if chk["extra"]:
        msg += f" · 계통도에 없는 줄 {len(chk['extra'])}건"
    if r["engine_notes"]:
        msg += ". 관제 엔진에 신호로 들어갔고 문서 자동화의 작업허가서 점검에도 넘어갔다."
    elif not SESSION.sid:
        msg += ". 문서 자동화의 작업허가서 점검에 넘어갔다. 실시간 세션이 돌지 않아 엔진에는 넣지 않았다."
    else:
        msg += ". 관제 엔진과 문서 자동화에 같이 넘어갔다."
    return {"ptw_id": p["ptw_id"], "msg": msg}


@router.post("/iso/step")
def iso_step(body: dict):
    _input_space_guard("단계 입력")
    p = next((x for x in isolation.ptws() if x["ptw_id"] == body.get("ptw_id")), None)
    if not p:
        raise ValueError("작업허가서를 고른다")
    by = (body.get("by") or "").strip()
    if not by:
        raise ValueError("입력자 이름을 적는다 — 단계 입력 기록에 남는다")
    kind, line, value, note = body.get("kind"), body.get("line_id"), body.get("value"), body.get("note") or ""
    notes = isolation.step(p, kind, line, None if value in (None, "") else str(value), by, note)
    what = {"blind": f"{line} 맹판 설치 완료", "blind_undo": f"{line} 맹판 설치 취소(정정)",
            "gas": f"{line} 가스 측정 " + ("실패 기록" if isolation.is_gas_fail(value) else f"LEL {value}%"), "purge_start": "퍼지 시작", "purge_end": "퍼지 종료",
            "purge": f"퍼지 {value}분"}[kind]
    tail = (" · 엔진: " + " · ".join(notes)) if notes else ("" if SESSION.sid else " · 세션이 돌지 않아 엔진에는 넣지 않았다 (기록만)")
    return {"msg": f"{p['ptw_id']} {what} 입력 · {by}{tail}"}


# ====================================================================== 3. 이벤트 로그
def _filter(evs, f: dict) -> list[dict]:
    """거르기 · 검색은 control/eventlog.py — '보이는 경보 이상 넘기기'도 같은 조건을 쓴다."""
    return [ev for ev, _ in eventlog.filter_events(evs, f or {})]


# 이벤트 로그 (10/6 배치) — 위쪽 필터 한 줄 + 상세 필터, 왼쪽 이벤트 목록(카드 줄), 오른쪽 선택 이벤트 상세.
# 거르기는 control/eventlog.py 한 곳 — '보이는 경보 이상 넘기기'가 같은 조건으로 넘긴다. 조건은 '적용'을 눌러야 반영된다(화면 쪽).
KIND_BADGE = {"stage": "3축 판정", "check": "영상 규칙", "gate": "작업 전 차단", "accident": "사고", "info": "참고"}


def _row_label(e: dict) -> str:
    """판정표 줄 이름 (예: '점화원 + 축적(또는 LEL 10%), 발생 해제 아님') — 3축 판정 기록에만. 사고 · 게이트는 근거 문장 앞부분."""
    if e.get("kind", "stage") == "stage" and e.get("row"):
        rows = package().rules_base.get("judgments", {}).get(e.get("table") or "", {}).get("rows", [])
        hit = next((r for r in rows if r.get("row") == e["row"] and r.get("violation") == e.get("violation_type")), None)
        if hit:
            return hit.get("label", "")
    if e.get("kind") in ("gate", "accident"):
        return (e.get("reason") or "")[:40]
    return ""


def _gate_labels() -> dict:
    return {g["id"]: g.get("label", g["id"]) for g in package().rules_base.get("gates", [])}


def _log_row(e: dict, gates: dict) -> dict:
    vt = e.get("violation_type") or ""
    sub = " · ".join(x for x in [e.get("mode") or "", _row_label(e)] if x)
    return {**_ev_row(e), "cat": eventlog.cat_of(e), "title": vt.replace("_", " ") or (e.get("reason") or "")[:30],
            "badge": KIND_BADGE.get(e.get("kind", "stage"), ""), "sub": sub or "-", "zname": zone_name(e.get("zone")),
            "rule": eventlog.rule_source(e, gates), "rs": eventlog.ruleset_short(e),
            "src_t": "예시 데이터" if eventlog.src_kind(e) == "sample" else "실시간 세션"}


@router.post("/log")
def log_rows(body: dict):
    all_ = load_control_events()
    gates = _gate_labels()
    base = eventlog.filter_events(all_, body, ignore_cat=True)           # 건수 칩은 묶음(cat)을 고르기 전 기준
    hits = [(e, h) for e, h in base if not body.get("cat") or eventlog.cat_of(e) == body["cat"]]
    hits = eventlog.sort_events(hits, body.get("sort") if body.get("sort") in eventlog.SORTS else "new")
    evs = [ev for ev, _ in hits]
    modes = sorted({ev.get("mode") or "-" for ev in all_})
    na = sum(1 for ev in evs if ev.get("alerted") and ev.get("kind", "stage") in ("stage", "check"))
    ns = sum(1 for ev in evs if not ev.get("alerted") and ev.get("kind", "stage") in ("stage", "check"))
    extra = 0
    if str(body.get("period", "14")) != "all" and eventlog.detail_on(body):
        extra = len(eventlog.filter_events(all_, body, ignore_period=True)) - len(evs)
    return {"rows": [{**_log_row(e, gates), "hit": h} for e, h in hits], "n": len(evs), "total": len(all_),
            "alerts": na, "shadow": ns, "modes": modes, "cats": eventlog.cat_counts([e for e, _ in base]),
            "extra": max(0, extra), "tokens": eventlog.tokens(body.get("q")), "facets": eventlog.facets(all_)}


def _event(eid: str) -> dict:
    ev = next((x for x in load_control_events() if x["event_id"] == eid), None)
    if not ev:
        raise KeyError(f"없는 이벤트: {eid}")
    return ev


def _ev_axes(ev: dict) -> list[dict]:
    """판정 근거의 축 상태 그대로 (확인 · 가능 · 해제 · 미등록 · ● · ○) + 판정표에 적힌 무게(tone)."""
    ax = ev.get("axes") or {}
    if not ax:
        return []
    table = package().rules_base.get("judgments", {}).get(ev.get("table") or "", {})
    tone = {a["name"]: {s["state"]: s.get("tone", "") for s in a.get("states", [])} for a in table.get("axes", [])}
    return [{"name": k, "state": v, "tone": tone.get(k, {}).get(v, "")} for k, v in ax.items()]


def _stop_order(ev: dict, evs: list[dict]) -> dict | None:
    """실제로 내린 작업중지 지시 — 같은 출처(세션) · 같은 구역에서 이 기록 뒤에 남은 '작업중지_지시' 참고 기록."""
    for x in evs:
        if (x.get("kind") == "info" and x.get("violation_type") == "작업중지_지시" and x.get("_src") == ev.get("_src")
                and x.get("zone") == ev.get("zone") and x["_ts"] >= ev["_ts"]):
            return {"t": x["ts"][11:19], "id": x["event_id"]}
    return None


def _clip_window(ev: dict) -> str:
    """전후 클립 구간 — 엔진 설정(detect.json event.clip_pre_s · clip_post_s) 기준. 영상이 짧으면 있는 만큼만 남는다."""
    cfg = package().detect.get("event", {})
    pre, post = cfg.get("clip_pre_s"), cfg.get("clip_post_s")
    if pre is None or post is None:
        return "전후 클립"
    t = ev["_ts"]
    return f"전후 {pre + post:g}초 ({t - timedelta(seconds=pre):%H:%M:%S} ~ {t + timedelta(seconds=post):%H:%M:%S}, 설정 기준)"


@router.get("/event/{eid}")
def event_detail(eid: str):
    evs = load_control_events()
    ev = next((x for x in evs if x["event_id"] == eid), None)
    if not ev:
        raise KeyError(f"없는 이벤트: {eid}")
    clip = _clip_file(ev)
    return {**_log_row(ev, _gate_labels()), "zname": zone_name(ev.get("zone")), "reason": ev.get("reason") or "", "row": ev.get("row"),
            "response": ev.get("response") or "", "ruleset": ev.get("ruleset") or "", "kind_t": KIND_T.get(ev.get("kind"), ""),
            "clip_path": ev.get("clip_path") or "", "has_frame": frame_file(ev) is not None, "has_clip": clip is not None,
            "clip_window": _clip_window(ev) if clip is not None else "",
            "fp_by": ev.get("fp_by", ""), "fp_note": ev.get("fp_note", ""), "fp_cat": ev.get("fp_cat", ""), "ts_full": ev["ts"].replace("T", " "),
            "conf": quality.conf_rows(ev),
            "tag": eventlog.tag_text(ev), "axes": _ev_axes(ev), "stop": _stop_order(ev, evs),
            # 10/14 — 영상 안 위치 · 추적 번호 · 증빙 파일 실제 경로 · 데이터 공간
            "video_t": ev.get("video_t"), "track_id": ev.get("track_id"),
            "frame_file": str(frame_file(ev) or ""), "clip_file": str(clip or ""),
            "space_label": _space_label(ev.get("data_space"))}


def _space_label(key) -> str:
    import dataspace
    try:
        return dataspace.info(key or dataspace.view_key())["label"]
    except Exception:  # noqa: BLE001
        return str(key or "")


def _clip_file(ev: dict) -> Path | None:
    cp = ev.get("clip_path")
    if not cp:
        return None
    p = Path(str(cp).replace("\\", "/"))          # 윈도에서 남긴 경로(frames\\x.jpg)도 읽는다
    if not p.is_absolute():
        p = Path(ev.get("_base") or DOCGEN_SPACE.real()) / p
    return p if p.exists() else None


@router.get("/event/{eid}/frame")
def event_frame(eid: str):
    f = frame_file(_event(eid))
    return FileResponse(f) if f else Response(status_code=404)


@router.get("/event/{eid}/clip")
def event_clip(eid: str):
    f = _clip_file(_event(eid))
    return FileResponse(f, media_type="video/mp4") if f else Response(status_code=404)


@router.post("/log/fp")
def log_fp(body: dict):
    from safety_docs.handoff import mark_false_positive
    eid, by = body.get("event_id"), (body.get("by") or "").strip()
    if not eid:
        raise ValueError("표에서 이벤트를 고른다")
    undo = bool(body.get("undo"))
    cat, reason = str(body.get("cat") or "").strip(), str(body.get("reason") or "").strip()
    if not undo:                         # 오탐 사유는 고정 목록에서 — 기타는 사유를 직접 적는다 (10/8)
        if cat not in quality.FP_REASONS:
            raise ValueError("오탐 사유를 고른다")
        if cat == "기타" and not reason:
            raise ValueError("기타를 골랐으면 사유를 적는다")
    mark_false_positive(eid, by, reason, undo=undo, cat="" if undo else cat)
    return {"msg": f"{eid} 오탐 표시{' 취소' if undo else ' · ' + cat} · {by} — 위험성평가 집계 · 통계에서 "
                   f"{'다시 들어간다' if undo else '빠진다'}. 오탐을 근거로 한 완화는 사람이 승인한다."}


@router.post("/live/det-fp")
def live_det_fp(body: dict):
    """
    실시간 관제 영상에서 지금 잡힌 탐지 하나를 오탐으로 고른다 (10/8, control/detfp.py).
    사람은 영상 끝까지, 보호구 미착용은 그 사람의 그 보호구만, 물체(불꽃)는 같은 자리를 정해진 시간 동안 판정에서 뺀다.
    """
    ref, by = str(body.get("ref") or ""), (body.get("by") or "").strip()
    cat, reason = str(body.get("cat") or "").strip(), str(body.get("reason") or "").strip()
    if not ref:
        raise ValueError("오탐으로 고를 탐지를 고른다")
    if not by:
        raise ValueError("표시자 이름이 필요하다")
    if cat not in quality.FP_REASONS:
        raise ValueError("오탐 사유를 고른다")
    if cat == "기타" and not reason:
        raise ValueError("기타를 골랐으면 사유를 적는다")
    row = SESSION.mark_det_fp(ref, body.get("xyxy"), by=by, cat=cat, note=reason, target=body.get("target"),
                              action=str(body.get("action") or "record"), confirm=bool(body.get("confirm")),
                              snap_id=str(body.get("snap_id") or ""))
    seen = (row.get("seen_at") or "")[11:19]
    return {**row, "msg": f"{row['target']}" + (f" (탐지 {seen})" if seen else "") + f" 오탐 · {row['action_label']} · {cat} · {by}. "
                          "탐지 신뢰도 화면의 탐지 오탐 기록 · 히트맵 · 통계에 들어간다"}


@router.post("/live/snapshot")
def live_snapshot(body: dict):
    """
    탐지 오탐 · 미탐 창을 여는 순간 그 화면을 고정한다 (10/8 오후). 창 맨 위 그림 = /api/live/snapshot/{snap_id}.jpg
    저장할 때 snap_id 를 같이 보내면 이 순간의 그림이 이미지 로그로 남는다(저장을 누른 순간이 아니라).
    """
    return SESSION.pin_snapshot("fp" if body.get("purpose") == "fp" else "miss")


@router.get("/live/snapshot/{snap_id}/img")
def live_snapshot_part(snap_id: str, key: str = "now", kind: str = "view"):
    """등록 창의 '저장될 이미지 로그' 미리 보기 — 고른 탐지의 관제 화면 · 원본 · 박스 둘레 (10/8 오후)."""
    b = SESSION.pins.image(snap_id, key, kind)
    if not b:
        return Response(status_code=404)
    return Response(b, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/live/snapshot/{snap_id}.jpg")
def live_snapshot_img(snap_id: str):
    b = SESSION.pins.view(snap_id)
    if not b:
        return Response(status_code=404)
    return Response(b, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/live/det-fp/alarm")
def live_det_fp_alarm():
    """탐지 오탐 창을 열 때 — 영상 카메라 구역이 지금 경보 이상인가 (판정을 끄는 처리에 확인을 받는다)."""
    zone = ((SESSION.video.camera or {}).get("zone") if SESSION.video else "") or SESSION.cam_zone
    return {"zone": zone, "alarm": SESSION.zone_alarm(zone)}


@router.post("/live/det-fp/clear")
def live_det_fp_clear(body: dict):
    """오탐 처리 해제. undo=True 면 잘못 고른 것 — 기록도 취소한다."""
    dfp_id, by = str(body.get("dfp_id") or ""), (body.get("by") or "").strip()
    if not dfp_id:
        raise ValueError("해제할 오탐 처리를 고른다")
    if not by:
        raise ValueError("해제한 사람 이름이 필요하다")
    undo = bool(body.get("undo"))
    SESSION.clear_det_fp(dfp_id, by=by, undo_record=undo)
    return {"msg": f"{dfp_id} 오탐 처리 해제{' · 기록 취소' if undo else ' (기록은 남김)'} — 다음 탐지부터 다시 판정한다"}


# ====================================================================== 탐지 신뢰도 — 판정 기준 · 오탐 · 미탐 (10/8)
@router.get("/quality")
def quality_view():
    return {"criteria": quality.criteria(), "impact": quality.impact(), "history": quality.criteria_history(),
            "missed": quality.list_missed()[:100], "reports": quality.eval_reports(),
            "det_fp": [{**r, "zname": zone_name(r.get("zone"))} for r in detfp.list_records()[:100]],   # 실시간 탐지 오탐 기록 (10/8)
            "suggest": quality.suggestions(system_now())}                                                 # 기준 조정 제안 (10/8 오후)


@router.post("/det-fp/undo")
def det_fp_undo(body: dict):
    """탐지 오탐 기록 취소 — 잘못 고른 것. 실시간 관제에서 아직 빼고 있으면 그것도 멈춘다."""
    dfp_id, by = str(body.get("dfp_id") or ""), (body.get("by") or "").strip()
    if not by:
        raise ValueError("취소한 사람 이름이 필요하다")
    if dfp_id not in {r["dfp_id"] for r in detfp.list_records()}:
        raise ValueError(f"없는 탐지 오탐 기록 — {dfp_id}")
    SESSION.clear_det_fp(dfp_id, by=by, undo_record=True)
    return {"msg": f"{dfp_id} 탐지 오탐 기록 취소"}


@router.post("/quality/criteria")
def quality_criteria(body: dict):
    return quality.set_criteria(body.get("changes") or {}, str(body.get("by") or ""), str(body.get("reason") or ""))


@router.post("/missed")
def missed_add(body: dict):
    """
    미탐 등록 + 처리 (10/8 오후). action = now(지금 판정에 반영 + 증거) · evidence(증거 저장) · record(기록만).
    처리는 등록 뒤에 한다 — 처리가 실패해도 미탐 기록은 남고, 실패 사유가 기록에 붙는다.
    """
    action = str(body.get("action") or "record")
    if action != "record" and not SESSION.sid:
        raise ValueError("세션이 돌 때만 판정 반영 · 증거 저장을 할 수 있다 — '기록만'으로 등록한다")
    r = quality.add_missed(body)
    head = f"{r['miss_id']} 미탐 등록 — {r['zone']} · {quality.DET[r['det']]} · {r['ts'][11:19]}"
    try:
        res = SESSION.handle_missed(r, action, str(body.get("snap_id") or ""))
    except Exception as ex:  # noqa: BLE001 — 기록은 남기고 실패를 알린다
        quality.missed_result(r["miss_id"], {"error": str(ex)[:200]})
        raise ValueError(f"{head} · 처리 실패: {ex}") from ex
    extra = {k: v for k, v in res.items() if k != "action"}
    if extra:                                    # 처리 결과 · 이미지 경로 (기록만이어도 영상이 돌면 이미지가 남는다)
        quality.missed_result(r["miss_id"], extra)
    tail = {"now": res.get("result", "판정에 반영"), "evidence": "증거 저장" + (" (클립 · 프레임)" if res.get("clip_path") else " (프레임)" if res.get("frame_path") else " — 영상이 없어 증거가 없다"),
            "record": "기록만"}[action]
    return {**r, **res, "msg": f"{head} · {tail}. 탐지 신뢰도 화면의 미탐 기록 · 히트맵 · 통계에 들어간다"}


@router.get("/dataset/{kind}/{name}")
def dataset_image(kind: str, name: str):
    """오탐 · 미탐 이미지 로그 (control/records/dataset) — 탐지 신뢰도 화면의 썸네일 · 크게 보기."""
    from control.dataset import image_path
    p = image_path(f"dataset/{kind}/{name}")
    if p is None:
        return Response(status_code=404)
    return Response(p.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})


@router.post("/missed/undo")
def missed_undo(body: dict):
    quality.undo_missed(str(body.get("miss_id") or ""), str(body.get("by") or ""))
    return {"msg": f"{body.get('miss_id')} 미탐 등록 취소"}


def _for_handoff(evs: list[dict]) -> list[dict]:
    out = []
    for ev in evs:
        r = {k: v for k, v in ev.items() if not k.startswith("_") and k not in ("fp_by",)}
        f = frame_file(ev)
        r["frame_path"] = str(f) if f else None
        c = _clip_file(ev)
        if c:
            r["clip_path"] = str(c)
        out.append(r)
    return out


def handoff_events(eids: list[str], source: str) -> str:
    from safety_docs.handoff import receive
    evs = [x for x in load_control_events() if x["event_id"] in set(eids)]
    if not evs:
        raise ValueError("넘길 이벤트가 없다")
    return receive(_for_handoff(evs), source=source)["handoff_id"]


@router.post("/log/handoff")
def log_handoff(body: dict):
    if body.get("event_ids"):
        hid = handoff_events(body["event_ids"], body.get("source") or "이벤트 로그 · 한 건")
        return {"handoff_id": hid}
    evs = _filter(load_control_events(), body.get("filter") or {})
    evs = [x for x in evs if (x.get("alerted") and x.get("level") in ("경보", "최고 경보")) or x.get("kind") in ("gate", "accident")]
    if not evs:
        raise ValueError("보이는 목록에 경보 이상 · 게이트 · 사고가 없다")
    return {"handoff_id": handoff_events([x["event_id"] for x in evs], "이벤트 로그 · 보이는 경보 이상")}


@router.post("/log/corrective")
def log_corrective(body: dict):
    eid = body.get("event_id")
    ev = _event(eid)
    if not ev.get("alerted") or ev.get("kind", "stage") not in ("stage", "check"):
        raise ValueError("시정지시서는 경보로 울린 감지 기록으로 만든다 (무음 기록 · 게이트 · 사고는 아니다)")
    handoff_events([eid], "이벤트 로그 · 시정지시서")
    return {"event_id": eid}


# ====================================================================== 4. 재생 비교
# 규칙셋 이름은 v 번호로 통일(기본 규칙 v1 · 개정 규칙 v2), 기대 결과 대조는 개정 후(마지막 variant) 기준.
# 시스템 판정(정상 · 주의 · 경보 · 최고 경보 · 작업 전 차단)과 현장 결과(사고 발생 · 사고 없음)는 따로 낸다.
def _variant(name: str, v: dict) -> dict:
    sm = v["summary"]
    return {"name": name, "label": v["label"], "changes": v["changes"], "gate": sm["gate"], "top": sm["top"],
            "result": sm["result"], "text": sm["text"]}


def _key_expect(res: dict) -> str:
    """기대 핵심 — 개정 후 기대 결과 중 게이트 · 최고 단계 · 사고 항목만 짧게."""
    sc = replay.package().scenario(res["key"])
    ex = (sc.variants().get(res["expect_basis"]) or {}).get("expect", [])
    out = []
    for x in ex:
        if "gate" in x:
            out.append(f"{x['at']} 작업 전 차단")
        elif x.get("level") == "최고 경보":
            out.append(f"{x['at']} 최고 경보")
        elif "accident" in x:
            out.append(f"{x['at']} 사고 {'발생' if x['accident'] else '없음'}")
    return " · ".join(out)


@router.get("/replay")
def replay_list(force: int = 0):
    out = []
    for k in replay.scenario_keys():
        res = replay.run(k, bool(force))
        ok, n = replay.score(res)
        out.append({"key": k, "title": res["title"], "zone": res["zone"], "zname": zone_name(res["zone"]), "table": res["table"],
                    "summary": res["summary"] or res["basis"], "example": res["example"], "ok": ok, "n": n})
    return {"scenarios": out}


@router.get("/replay/{key}")
def replay_detail(key: str):
    res = replay.run(key)
    ok, n = replay.score(res)
    names = list(res["variants"])
    basis = res["variants"][res["expect_basis"]]
    rows = replay.merged_rows(res)
    return {"key": key, "title": res["title"], "zone": res["zone"], "zname": zone_name(res["zone"]), "table": res["table"],
            "basis": res["basis"], "purpose": res["purpose"] or res["basis"], "summary": res["summary"], "example": res["example"],
            "docs": res["docs"], "key_expect": _key_expect(res), "ok": ok, "n": n, "times": res["times"],
            "variants": [_variant(k, v) for k, v in res["variants"].items()],
            "rows": [{"t": r["t"], "what": r["what"] or "(시간 경과)", "label": r["label"], "source": r["source"], "notes": r["notes"],
                      "cells": [r["cells"].get(nm) or {} for nm in names]} for r in rows],
            "expect_label": basis["label"],
            "expect": [{"ok": c, "msg": replay.expect_text(msg)} for c, msg in basis["checks"]]}



@router.get("/replay/{key}/at")
def replay_at(key: str, t: str):
    res = replay.run(key)
    out = []
    for name, v in res["variants"].items():
        st = replay.state_at(res, name, t)
        sm = v["summary"]
        out.append({"name": name, "label": v["label"], "level": st["level"], "row": st.get("row"), "modes": st.get("modes", []),
                    "axes": " · ".join(f"{k} {v2}" for k, v2 in st.get("axes", {}).items()),
                    "gate": sm["gate"] if sm["gate"] and sm["gate"]["t"] <= t else None,
                    "result": sm["result"] if sm["result"]["t"] and sm["result"]["t"] <= t else None})
    return {"t": t, "states": out}


@router.post("/replay/import")
async def replay_import(files: list[UploadFile] = File(...)):
    """불러오기 — zip(시나리오 폴더째) 또는 json(scenario.json, 같이 고른 timeline.csv · 입력 문서)."""
    got = [(f.filename or "", await f.read()) for f in files]
    zips = [g for g in got if g[0].lower().endswith(".zip")]
    if zips:
        if len(got) > 1:
            raise ValueError("zip 은 한 개만 올린다 (시나리오 폴더를 통째로 묶은 것)")
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(zips[0][1])
            path = tmp.name
        try:
            key = replay.import_zip(path, zips[0][0])
        finally:
            Path(path).unlink(missing_ok=True)
    elif any(g[0].lower().endswith(".json") for g in got):
        key = replay.import_json(got)
    else:
        raise ValueError("zip 또는 json 파일을 고른다")
    return {"key": key, "msg": f"불러옴 — {key} · 사업장 패키지 scenarios/ 에 저장했다"}


@router.post("/replay/{key}/handoff")
def replay_handoff(key: str, body: dict):
    from safety_docs.handoff import receive
    res = replay.run(key)
    name = body.get("variant")
    v = res["variants"].get(name)
    if not v:
        raise ValueError("넘길 규칙셋 결과를 고른다")
    mark = replay.handoff_mark(res, name)
    ho = receive(v["run"]["log"].rows, source=f"재생 비교 · {res['title']} · {v['label']}", base_dir=v["out_dir"], replay=mark)
    return {"handoff_id": ho["handoff_id"], "mark": mark["text"]}


# ====================================================================== 5. 피드백 · 조정 로그
HIST_T = {"applied": "적용", "pending": "승인 대기로 생성", "rejected": "거부", "expired": "만료", "reverted": "되돌림"}


def _adj_card(a: dict, now) -> dict:
    k, lab = feedback.current_label(a, now)
    ac = a.get("action") or {}
    return {"adj_id": a["adj_id"], "state": a["state"], "state_key": k, "state_label": lab,
            "zone": a["zone"], "zname": zone_name(a["zone"]), "mode": a.get("mode") or "", "violation_type": a.get("violation_type") or "",
            "action": feedback.action_text(a), "reason": feedback.reason_text(a),
            "level_before": ac.get("before"), "level_after": ac.get("after"),
            "zone_rule": bool(ac.get("enable_zone_rule")), "notify": bool(ac.get("notify_manager")),
            "start": (a.get("applied_at") or a["ts"]).replace("T", " "), "expires_at": a["expires_at"],
            "expires": a["expires_at"][5:16].replace("T", " "), "ts": a["ts"][5:16].replace("T", " "),
            "severe": (a.get("reason") or {}).get("type") == "severe", "feedback_mode": a.get("feedback_mode", ""),
            "evidence": a.get("evidence_event_ids") or [],
            "history": [{"ts": (h.get("ts") or "").replace("T", " ")[:16],
                         "state": ("승인 — 적용" if i and h.get("state") == "applied" else HIST_T.get(h.get("state"), h.get("state"))),
                         "actor": h.get("actor") or "system", "note": h.get("note") or ""} for i, h in enumerate(a.get("history", []))],
            "sample": bool(a.get("sample"))}


def _live_rules() -> dict:
    m = SESSION.meta or {}
    return {"sid": SESSION.sid, "applied": m.get("applied") or [], "label": m.get("rules_label", ""), "ruleset": m.get("ruleset", "")}


@router.get("/feedback")
def feedback_view():
    from web.api_docs import _ra
    now = system_now()
    act = feedback.active(now)
    pend = feedback.pending()
    counts = feedback.zone_counts(now)
    rs = ruleset_status()
    cfg = feedback.config()
    sp = cfg["spike"]
    short = [("중대", f"중대성 {cfg['severe']['severity']}등급 1건", "1단 즉시"),
             ("급증", f"{sp['window_h']}시간 ≥ {sp['baseline_days']}일 평균 × {sp['ratio']:g}, 최소 {sp['min_count']}건", "1단"),
             ("신규", "기준선 0건인 조합의 첫 발생", "1단")]
    long_ = [("승격", f"같은 구역 {cfg['promote']['within_days']}일 안에 조정 {cfg['promote']['count']}회", "2단"),
             ("절대 기준", f"주간 {cfg['absolute']['weekly_count']}건 초과 또는 위험도 {cfg['absolute']['risk_score']} 이상", "2단"),
             ("오탐 과다", f"오탐 표시 {cfg['false_positive']['ratio'] * 100:.0f}% 초과 (최소 {cfg['false_positive']['min_count']}건)", "2단 (완화 제안)"),
             ("급감", f"기준선의 {cfg['drop']['ratio'] * 100:.0f}% 이하", "카메라 점검 알림")]
    live = _live_rules()
    rcs = feedback.rule_changes_view(_ra.get("drafts") or [], live)
    long_wait = [r for r in rcs if r["phase"] in ("draft", "worker")]
    last = rs.get("last") or {}
    return {"now": now.isoformat(timespec="seconds"),
            "kpis": {"active": len(act), "active_zones": list(dict.fromkeys(a["zone"] for a in act)), "pending": len(pend),
                     "long_wait": len(long_wait), "long_wait_ids": [r["id"] for r in long_wait],
                     "n14": sum(counts.values()), "trend": feedback.trend(now),
                     "version": rs["version"], "ids": rs["ids"], "last_ts": (last.get("ts") or "").replace("T", " ")[:16],
                     "mode": feedback.mode(), "live_rules": live["label"]},
            "open": [_adj_card(a, now) for a in sorted(act + pend, key=lambda a: a["ts"], reverse=True)],
            "rcs": rcs,
            "proposals": [{**p, "ts": (p.get("ts") or "").replace("T", " ")[:16], "zname": zone_name(p.get("zone"))}
                          for p in feedback.proposals(now)],
            "zone_counts": [{"zone": z, "name": zone_name(z), "n": counts.get(z, 0)} for z in zones() if counts.get(z)],
            "criteria": short + long_, "criteria_short": short, "criteria_long": long_,
            "expire_h": cfg["expire_h"], "promote": cfg["promote"], "max_up": cfg["auto_actions"]["alert_level"]["max_up"],
            "log": feedback.log_rows(now), "zones": [{"id": z, "name": zone_name(z)} for z in zones()]}


@router.post("/feedback/rule")
def feedback_rule(body: dict):
    """긴 루프 — 변경안 하나 반려 · 반려 취소. 기록은 문서 자동화 쪽(rule_rejections.jsonl)에 남아 위험성평가 화면에도 보인다."""
    rid, act = body.get("rule_id") or "", body.get("action")
    actor, role, note = body.get("actor") or "", body.get("role") or "관리자", body.get("note") or ""
    if act == "reject":
        r = feedback.reject_rule_change(rid, actor, role, note)
        msg = f"{rid} 반려 — {r['ra_id']} · {actor} · 사유: {note}. 확정해도 이 변경안은 규칙셋에 올리지 않는다"
    elif act == "restore":
        r = feedback.restore_rule_change(rid, actor, role, note)
        msg = f"{rid} 반려 취소 — {r['ra_id']} 근로자 확인을 다시 기다린다"
    else:
        raise ValueError(act)
    _badge["t"] = 0
    return {"msg": msg}


@router.post("/feedback/mode")
def feedback_mode(body: dict):
    new = body.get("mode")
    if new == feedback.mode():
        return {"msg": "이미 그 방식이다"}
    feedback.set_mode(new, body.get("actor") or "", body.get("note") or "", system_now())
    _badge["t"] = 0
    return {"msg": f"피드백 방식 → {'자동' if new == 'auto' else '승인형'} — 조정 로그에 남았다"}


@router.post("/feedback/act")
def feedback_act(body: dict):
    action, adj_id = body.get("action"), body.get("adj_id")
    actor, note = body.get("actor") or "", body.get("note") or ""
    now = system_now()
    if action == "revert":
        feedback.revert(adj_id, actor, note, now)
        msg = f"{adj_id} 되돌림 · {actor} · 사유: {note}"
    elif action == "approve":
        feedback.approve(adj_id, actor, now)
        msg = f"{adj_id} 승인 — 적용 · {actor}"
    elif action == "reject":
        feedback.reject(adj_id, actor, note, now)
        msg = f"{adj_id} 거부 · {actor} · 사유: {note}"
    elif action == "promote":
        feedback.promote(adj_id, actor, note, now)
        msg = f"{adj_id} → 개정 제안으로 승격 · 문서 자동화 › 위험성평가에서 감소대책(규칙 변경)으로 확정한다"
    else:
        raise ValueError(action)
    _badge["t"] = 0
    return {"msg": msg}


@router.post("/feedback/eval")
def feedback_eval():
    new = feedback.evaluate(system_now())
    _badge["t"] = 0
    if not new:
        return {"msg": "이탈 조건에 걸린 새 조합이 없다 (만료 정리만 했다)"}
    return {"msg": "새 자동 조정 — " + " · ".join(f"{a['adj_id']} {a['zone']} {feedback.reason_text(a)}" for a in new)}


# ====================================================================== 6. 히트맵 · 통계
@router.get("/stats")
def stats_view(period: str = "14", src: str = "", zone: str = "", zbasis: str = "all", hbasis: str = "all"):
    """히트맵 · 통계 (10/6 배치) — 필터(기간 · 출처 · 구역)는 화면에서 '적용'을 눌러야 바뀐다. 카드 안 기준(전체 · 경보 이상 · 무음 기록)은 바로."""
    now = system_now()
    evs = load_control_events()
    v = stats.view(evs, now, period, src, zone, zbasis, hbasis)
    a, b, pa = stats._span(now, period)
    v["quality"] = quality.view(evs, a, b, pa, src, zone)          # 오탐 · 미탐 (10/8)
    has_sample = any(e.get("_src", "샘플") == "샘플" for e in evs)
    has_live = any(e.get("_src", "샘플") != "샘플" for e in evs)
    return {**v, "updated": now.isoformat(timespec="minutes"),
            "sources": ([{"v": "sample", "label": "예시 데이터"}] if has_sample else []) + ([{"v": "live", "label": "실시간 세션"}] if has_live else [])}
