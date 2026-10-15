"""
문서 자동화 다섯 화면의 데이터 — 홈 · 의무 이행 관리 · 안전 문서(관제 인계 · 위험성평가 · 시정지시서 ·
작업허가서 점검 · 산업재해조사표) · 안전소통 · 기록.

계산 · 문장 생성 · 기록은 전부 docgen/safety_docs 에 있다. 여기는 그 함수를 불러 화면이 쓰는 JSON 으로 바꾼다.
원칙: 숫자는 코드, 문장은 AI 초안, 확정은 사람.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, Response

from safety_docs.accident import build_accident_facts, draft_accident_report
from safety_docs.accident_case import (ACC_TYPES, CAUSES, DOC_KEYS, EMPLOY, INFO_KEYS, SHIFT, STAGE_LABEL, STAGE_SHORT, STAGES,
                                       accident_stats, candidates, case_rows, change_stage, get_case, guess_type, is_target,
                                       save_case, stage_summary)
from safety_docs.archive import document_rows, effect_rows, revision_rows, ruleset_rows
from safety_docs.assessment import (build_rows, confirm_revision, draft_assessment, get_assessment, list_assessments,
                                    reject_revision, submit_for_review)
from safety_docs.compliance import alert_summary, build_schedule, done_list, mark_done
from safety_docs.config import (OUTPUT_DIR, load_documents, load_events, load_legal, load_piping, load_profile,
                                load_rulesets, load_scales, now, parse_date)
from safety_docs.corrective import apply_edits, draft_corrective_order, list_correctives, load_order, log_corrective, save_order
from safety_docs.export import (doc_mark, accident_form_docx, accident_report_docx, accident_zip, assessment_to_excel,
                                corrective_to_docx, ptw_to_docx)
from safety_docs.handoff import get_handoff, list_handoffs, make_correctives, receive_file, report_candidates
from safety_docs.home import home_summary
from safety_docs.llm import LLMClient
from safety_docs.ptw import check_ptw, draft_ptw_notes, list_ptws, load_isolation, log_ptw_check
from safety_docs.voice import list_reports, submit_report, update_report, voice_summary

router = APIRouter(prefix="/api")
MEASURE_RE = re.compile(r"^\[(공학적|관리적|보호구)(?:·(R\d+))?\]\s*(.+)$")
LEVEL_KIND = {"overdue": "crit", "urgent": "crit", "soon": "warn", "upcoming": "note", "ok": "mute"}
EMOJI = re.compile(r"^[🔴🟠🟡🟢⚪]\s*")


def _today():
    from control.common import demo_day
    return demo_day()


def _llm() -> LLMClient:
    return LLMClient()                  # 10/8 - mock 전용 (Claude · OpenAI 연결을 뺐다)


def file_url(path) -> str | None:
    """만든 문서 파일 → 내려받기 주소. docgen/outputs 안의 파일만 내준다."""
    if not path:
        return None
    name = Path(str(path).replace("\\", "/")).name
    return f"/api/file?name={name}" if (OUTPUT_DIR / name).exists() else None


@router.get("/file")
def get_file(name: str):
    p = OUTPUT_DIR / Path(name).name
    if not p.exists():
        return Response(status_code=404)
    return FileResponse(p, filename=p.name)


_adhoc = {"key": None, "n": 0}


def adhoc_count() -> int:
    """수시 위험성평가 제안 건수 — 넘어온 기록 · 오탐 표시가 바뀔 때만 다시 센다."""
    from safety_docs.config import FP_MARKS, MONITOR_EVENTS
    key = tuple(p.stat().st_mtime if p.exists() else 0 for p in (MONITOR_EVENTS, FP_MARKS))
    if key != _adhoc["key"]:
        evs, as_of = load_events()
        _, ad = build_rows(evs, as_of, load_scales(), load_profile().get("accidents"))
        _adhoc.update(key=key, n=len(ad))
    return _adhoc["n"]


def _zn(z: str) -> str:
    from control.common import zone_name
    return zone_name(z)


# ====================================================================== 홈
@router.get("/home")
def home():
    from control.common import load_control_events
    evs, as_of = load_events()
    prof = load_profile()
    h = home_summary(evs, as_of, load_scales(), prof, _today())
    go = {"안전 문서": ("docs", "ra"), "의무 이행 관리": ("duty", None), "안전소통": ("voice", None)}
    cards = [{"title": c["title"], "num": c["num"], "lines": [EMOJI.sub("", x) for x in c["lines"]],
              "go": go.get(c["go"], ("home", None))[0], "tab": go.get(c["go"], ("home", None))[1]} for c in h["cards"]]
    since = as_of - timedelta(days=14)
    ctl = [e for e in load_control_events() if since < e["_ts"] <= as_of]
    ras = list_assessments()
    cos = list_correctives()
    ev = h["evidence"]
    hos = [x for x in list_handoffs(include_auto=False) if (x["event_ids"] or x.get("duplicates")) and not x.get("replay")]
    return {"cards": cards,
            "zones": [{**z, "zname": _zn(z["zone"])} for z in h["zones"]],
            "evidence": {"events": ev["events"], "silent": ev["silent"], "alerts": ev["events"] - ev["silent"],
                         "days": ev["days"], "recorded": ev["recorded"], "gaps": ev["gaps"], "period": ev["period"],
                         "clips": sum(1 for e in ctl if e.get("clip_path")),
                         "gates": sum(1 for e in ctl if e.get("kind") == "gate"),
                         "confirmed": sum(1 for r in ras if r["state"] == "confirmed"), "correctives": len(cos)},
            "handoff": ({"id": hos[0]["handoff_id"], "source": hos[0]["source"], "n": len(hos),
                         "events": len(hos[0]["event_ids"]) + len(hos[0].get("duplicates", []))} if hos else None)}


# ====================================================================== 의무 이행 관리
def _profile(body: dict) -> dict:
    prof = load_profile()
    return {**prof, "industry": body.get("industry") or prof.get("industry"),
            "workers": int(body.get("workers") or prof.get("workers") or 0),
            "hazardous_agents": bool(body.get("hazardous", prof.get("hazardous_agents")))}


@router.post("/duty")
def duty(body: dict):
    evs, as_of = load_events()
    today = parse_date(body["today"]) if body.get("today") else _today()
    prof = _profile(body)
    _, adhoc = build_rows(evs, as_of, load_scales(), prof.get("accidents"))
    items, judged = build_schedule(prof, today, adhoc, as_of.date())
    cat = body.get("cat")
    if cat and cat != "전체":
        items = [it for it in items if it["category"] == cat]
    done = done_list(prof, [cat] if cat and cat != "전체" else None)
    return {"today": today.isoformat(), "summary": alert_summary(items),
            "items": [{"key": f"{it['ob_id']}||{it['ref']}", "status": EMOJI.sub("", it["status"]),
                       "kind": LEVEL_KIND.get(it["level"], "mute"), "level": it["level"], "name": it["name"],
                       "ref": it["ref"], "category": it["category"], "basis": it["basis"], "due": it["due"],
                       "retention": it["retention"].split(" — ")[0], "why": it["why"], "type": it["kind"]} for it in items],
            "judged": judged, "done": done}


@router.post("/duty/done")
def duty_done(body: dict):
    choice = body.get("key")
    if not choice:
        raise ValueError("이행 처리할 항목을 고른다")
    if not body.get("staff"):
        raise ValueError("담당자를 고른다")
    today = parse_date(body["today"]) if body.get("today") else _today()
    ob_id, ref = choice.split("||", 1)
    day = parse_date(body["day"], year=today.year) if str(body.get("day") or "").strip() else today
    row = mark_done(ob_id, day, body["staff"], ref, body.get("note") or "", today=today)
    return {"msg": f"이행 처리 — {row['done_date']} · {row['by']} ({row['by_dept']} · {row['by_position']})",
            "day": row["done_date"]}


@router.get("/norm-day")
def norm_day(value: str, today: str | None = None):
    t = parse_date(today) if today else _today()
    return {"day": parse_date(value, year=t.year).isoformat()}


# ====================================================================== 안전 문서 — 위험성평가
_ra = {"rows": [], "drafts": [], "file": None}


@router.get("/docs/ra")
def ra_calc():
    evs, as_of = load_events()
    rows, adhoc = build_rows(evs, as_of, load_scales(), load_profile().get("accidents"))
    _ra.update(rows=rows)
    return {"as_of": as_of.isoformat(timespec="minutes"),
            "rows": [{"i": i, "zone": r["zone"], "zname": _zn(r["zone"]), "mode": r["mode"], "type": r["violation_type"],
                      "count": r["count_used"], "base": r["base_count"], "recent": r["recent_count"], "adj": r["adj_count"],
                      "top": r["top_alert_count"], "likelihood": r["likelihood"], "l_label": r["likelihood_label"],
                      "severity": r["severity"], "score": r["score"], "grade": r["grade"], "adhoc": r["adhoc_reasons"]}
                     for i, r in enumerate(rows)],
            "adhoc": adhoc, "drafts": _drafts_json(), "file": file_url(_ra["file"]),
            "window": [rows[0]["window_from"], rows[0]["window_to"]] if rows else None}


def _measures_text(ms, rejected: dict | None = None) -> str:
    """감소대책 한 줄씩. rejected = 변경안 단위로 반려된 것(관제 › 피드백 · 조정 로그) — 그 줄 끝에 표시한다."""
    rej = rejected or {}

    def tail(m):
        r = rej.get(m.get("rule_id") or "")
        return f"  ← 규칙 변경 {m['rule_id']} 반려 ({r.get('name', '')} · {r.get('note', '')}) — 확정해도 규칙셋에 올리지 않는다" if r else ""
    return "\n".join(f"[{m['category']}{'·' + m['rule_id'] if m.get('rule_id') else ''}] {m['text']}{tail(m)}" for m in ms)


def _drafts_json() -> list[dict]:
    return [{"i": i, "zone": d["zone"], "zname": _zn(d["zone"]), "mode": d["mode"], "type": d["violation_type"],
             "likelihood": d["likelihood"], "severity": d["severity"], "score": d["score"], "grade": d["grade"],
             "event_ids": d.get("event_ids", []), "accident_ids": d.get("accident_ids", []),
             "unit_work": d.get("unit_work", ""), "hazard": d.get("hazard", ""), "cause": d.get("cause", ""),
             "current_measures": "\n".join(d.get("current_measures", [])), "measures": _measures_text(d.get("measures", [])),
             "legal_refs": "\n".join(d.get("legal_refs", [])),
             "check": "\n".join(filter(None, [d.get("check_needed", "")] + d.get("warnings", [])))}
            for i, d in enumerate(_ra["drafts"])]


@router.post("/docs/ra/draft")
def ra_draft(body: dict):
    if not _ra["rows"]:
        ra_calc()
    rows = _ra["rows"]
    pick = body.get("rows")                              # 고른 행만 (없으면 수시평가 제안 행, 그것도 없으면 전부)
    if pick:
        rows = [rows[i] for i in pick if 0 <= i < len(rows)]
    elif any(r["adhoc_reasons"] for r in rows):
        rows = [r for r in rows if r["adhoc_reasons"]]
    if not rows:
        raise ValueError("초안을 만들 행이 없다 — 관제 기록이 없다")
    rs = load_rulesets()
    drafts = draft_assessment(rows, rs, load_legal(), load_scales(), _llm())
    path = assessment_to_excel(drafts, OUTPUT_DIR / "위험성평가표_초안.xlsx", rulesets=rs, scales=load_scales())
    _ra.update(drafts=drafts, file=str(path))
    return {"drafts": _drafts_json(), "file": file_url(path)}


def _apply_edits(edits: list[dict]) -> list[dict]:
    """화면에서 고친 문장 칸을 초안에 되돌려 넣는다. 숫자 칸은 받지 않는다."""
    changes = load_rulesets().get("rule_changes", {})
    by_i = {int(x["i"]): x for x in edits or []}
    out = []
    for i, d in enumerate(_ra["drafts"]):
        x = by_i.get(i)
        if not x:
            out.append(d)
            continue
        measures = []
        for line in str(x.get("measures", "")).splitlines():
            line = line.strip()
            if not line:
                continue
            m = MEASURE_RE.match(line)
            rid = m.group(2) if m and m.group(2) in changes else ""
            measures.append({"category": m.group(1), "text": m.group(3), "rule_id": rid} if m
                            else {"category": "관리적", "text": line, "rule_id": ""})
        out.append({**d, "unit_work": str(x.get("unit_work", "")).strip(), "hazard": str(x.get("hazard", "")).strip(),
                    "cause": str(x.get("cause", "")).strip(),
                    "current_measures": [s for s in str(x.get("current_measures", "")).splitlines() if s.strip()],
                    "measures": measures, "legal_refs": [s for s in str(x.get("legal_refs", "")).splitlines() if s.strip()]})
    return out


@router.post("/docs/ra/sign")
def ra_sign(body: dict):
    if not _ra["drafts"]:
        raise ValueError("서명할 초안이 없다 — 자동 초안 생성을 먼저 누른다")
    ra = submit_for_review(_apply_edits(body.get("edits")), body.get("manager") or "", body.get("kind") or "수시",
                           body.get("note") or "")
    rs = load_rulesets()
    path = assessment_to_excel(ra["rows"], OUTPUT_DIR / f"위험성평가표_{ra['ra_id']}.xlsx", rulesets=rs,
                               scales=load_scales(), record=ra)
    rules = sorted({m["rule_id"] for r in ra["rows"] for m in r["measures"] if m.get("rule_id")})
    _ra.update(drafts=[], file=None)
    return {"ra_id": ra["ra_id"], "file": file_url(path),
            "msg": f"관리자 서명 완료 — {ra['ra_id']} ({ra['kind']}) · 근로자 확인 대기. 근로자 대표가 안전소통 › 근로자 확인에서 "
                   f"확인하면 확정된다. 확정되면 규칙 변경 {', '.join(rules) or '없음'}이 규칙셋에 반영된다."}


# ====================================================================== 안전 문서 — 시정지시서
@router.get("/docs/co")
def co_events():
    evs, _ = load_events(include_replay=True)
    issued = {c["event_id"]: c for c in list_correctives(include_replay=True)}
    xs = [x for x in evs if x.get("alerted", True) and not x.get("false_positive") and x.get("level") in ("경보", "최고 경보")]
    xs.sort(key=lambda x: x["ts"], reverse=True)
    real = [x for x in xs if not x.get("replay")] or xs    # 처음 고르는 것은 운영 기록에서
    default = next((x["event_id"] for x in real if x.get("level") == "최고 경보" and x.get("frame_path")),
                   real[0]["event_id"] if real else None)
    return {"events": [{"id": x["event_id"], "ts": x["ts"][5:16].replace("T", " "), "zone": x["zone"], "level": x.get("level"),
                        "type": x["violation_type"], "frame": bool(x.get("frame_path")), "handoff": x.get("handoff_id"),
                        "issued": (issued.get(x["event_id"]) or {}).get("doc_no"),
                        "replay": bool(x.get("replay"))} for x in xs], "default": default}


def _docgen_event(eid: str) -> dict:
    evs, _ = load_events(include_replay=True)
    ev = next((x for x in evs if x["event_id"] == eid), None)
    if not ev:
        raise KeyError(f"문서 자동화에 없는 이벤트: {eid} — 관제에서 넘겨야 보인다")
    return ev


def _frame_path(ev: dict) -> Path | None:
    from safety_docs.config import doc_file
    fp = ev.get("frame_path")
    if not fp:
        return None
    p = doc_file(fp)
    return p if p.exists() else None


@router.get("/docs/co/{eid}")
def co_event(eid: str):
    ev = _docgen_event(eid)
    issued = next((c for c in list_correctives(include_replay=True) if c["event_id"] == eid), None)
    return {"id": eid, "ts": ev["ts"].replace("T", " "), "zone": ev["zone"], "zname": _zn(ev["zone"]), "mode": ev.get("mode"),
            "type": ev["violation_type"], "level": ev.get("level"), "row": ev.get("row"), "reason": ev.get("reason", ""),
            "adj": ev.get("adj_id"), "clip": ev.get("clip_path"), "handoff": ev.get("handoff_id"),
            "source": ev.get("source", ""), "frame": _frame_path(ev) is not None,
            "replay": (ev.get("replay") or {}).get("text", ""),
            "issued": {"doc_no": issued["doc_no"], "deadline": issued["deadline_date"], "file": file_url(issued.get("file"))} if issued else None,
            # 만들어 둔 초안이 있으면 그대로 다시 열어 고친다 (10/8)
            "order": _order_json(o, issued.get("file")) if issued and (o := load_order(issued["doc_no"])) else None}


@router.get("/docs/co/{eid}/frame")
def co_frame(eid: str):
    p = _frame_path(_docgen_event(eid))
    return FileResponse(p) if p else Response(status_code=404)


def _order_json(o: dict, path) -> dict:
    return {"doc_no": o["doc_no"], "issued": o["issued"], "zone": o["event"]["zone"], "zname": o["zone_name"],
            "event_id": o["event"]["event_id"], "level": o["event"].get("level"), "type": o["event"]["violation_type"],
            "mode": o["event"].get("mode"), "rule_state": o["rule_state"], "same_recent": o["same_recent"],
            "severity": o["severity"], "severity_label": o["severity_label"], "deadline": o["deadline"], "deadline_date": o.get("deadline_date"),
            "clip": o["event"].get("clip_path"), "scene": o["scene"], "hazards": o["hazards"], "violation": o["violation"],
            "actions": o["actions"], "legal_refs": o["legal_refs"], "uncertain": o["uncertain"], "warnings": o["warnings"],
            "replay": o.get("replay_mark", ""), "file": file_url(path),
            "recipient": o.get("recipient", ""), "edited": o.get("edited")}


@router.post("/docs/co")
def co_make(body: dict):
    evs, as_of = load_events()
    ev = next((x for x in load_events(include_replay=True)[0] if x["event_id"] == body.get("event_id")), None)
    if not ev:
        raise ValueError("이벤트를 고른다")
    # 재생 비교 검증본도 운영 기록과 같은 기준으로 센다(같은 위반 최근 14일 = 운영 기록 + 이 한 건)
    order = draft_corrective_order(ev, evs + ([ev] if ev.get("replay") else []), load_rulesets(), load_legal(), load_scales(), _llm(), issued=as_of)
    with doc_mark(ev.get("run_kind")):
        path = corrective_to_docx(order, OUTPUT_DIR / f"시정지시서_{ev['event_id']}{'_재생검증본' if ev.get('replay') else ''}.docx")
    log_corrective(order, str(path))
    save_order(order)
    return _order_json(order, path)


@router.post("/docs/co/edit")
def co_edit(body: dict):
    """
    시정지시서 초안 고치기 (10/8) — 문장 칸(현장 상황 · 위험 기인물 · 위반 사항 · 시정 요구 · 확인 필요)과 수신자만 바뀐다.
    같은 문서번호로 워드를 다시 만들고 발행 기록에 새 줄을 남긴다(마지막 줄이 현재 판).
    """
    doc_no = str(body.get("doc_no") or "").strip()
    order = load_order(doc_no) if doc_no else None
    if order is None:
        raise ValueError("고칠 초안이 없다 — 먼저 ‘시정지시서 초안 생성’을 누른다")
    edits = {k: body[k] for k in ("scene", "hazards", "violation", "actions", "uncertain", "recipient", "deadline", "legal_refs") if k in body}
    order = apply_edits(order, edits, str(body.get("editor") or ""))
    if not order["actions"]:
        raise ValueError("시정 요구를 한 줄 이상 적는다 — [공학적] · [관리적] · [보호구] 로 시작")
    ev = order["event"]
    with doc_mark(ev.get("run_kind")):
        path = corrective_to_docx(order, OUTPUT_DIR / f"시정지시서_{ev['event_id']}{'_재생검증본' if ev.get('replay') else ''}.docx")
    log_corrective(order, str(path))
    save_order(order)
    return _order_json(order, path)


# ====================================================================== 안전 문서 — 작업허가서 점검
@router.get("/docs/ptw")
def ptw_list():
    return {"ptws": [{"id": p["ptw_id"], "type": p.get("type", ""), "zone": p["zone"], "work": p["work"]} for p in list_ptws()]}


@router.get("/docs/ptw/{pid}")
def ptw_show(pid: str):
    p = next((x for x in list_ptws() if x["ptw_id"] == pid), None)
    if not p:
        raise KeyError(f"없는 작업허가서: {pid}")
    try:
        iso = load_isolation(p)
    except (OSError, ValueError):
        iso = None
    p, iso, info = _with_steps(p, iso)
    from safety_docs.ptw import form_summary
    return {"ptw": {k: p.get(k) for k in ("ptw_id", "type", "zone", "work", "start", "end", "supervisor", "workers",
                                          "registered_at", "source", "fire_watch")},
            "zname": _zn(p["zone"]), "purge": (p.get("purge") or {}).get("minutes"), "iso": iso, "steps": info,
            # 공통 양식 작성본 (10/8) — 허가서 원본 워드 · 안전조치 요약
            "doc": file_url(p.get("document_file")), "form": form_summary(p)}


def _with_steps(p: dict, iso):
    """관제 격리 목록 대조의 단계 입력(맹판 · 측정 · 퍼지)을 얹은 사본 — 점검이 격리 화면과 같은 데이터를 읽는다.
    관제 모듈을 못 읽는 환경(문서 자동화만 따로 돌릴 때)이면 허가서 원본 그대로."""
    try:
        from control.isolation import with_steps
    except ImportError:
        return p, iso, {"steps": 0, "expired": [], "purge_state": ""}
    return with_steps(p, iso)


@router.post("/docs/ptw/{pid}")
def ptw_check(pid: str):
    ps = list_ptws()
    p = next((x for x in ps if x["ptw_id"] == pid), None)
    if not p:
        raise ValueError("작업허가서를 고른다")
    try:
        iso = load_isolation(p)
    except (OSError, ValueError):
        iso = None
    p, iso, info = _with_steps(p, iso)
    ps = [p if x["ptw_id"] == pid else x for x in ps]
    res = draft_ptw_notes(check_ptw(p, ps, load_piping(), load_rulesets(), iso), load_legal(), _llm())
    path = ptw_to_docx(res, OUTPUT_DIR / f"작업허가서점검_{pid}.docx")
    log_ptw_check(res, str(path))
    listed = {r.get("line_id"): r for r in res["iso_rows"]}
    return {"result": res["result"], "summary": res["summary"], "text_source": res["text_source"],
            "findings": [{"code": f["code"], "title": f["title"], "detail": f["detail"], "note": f["note"],
                          "legal_refs": f["legal_refs"]} for f in res["findings"]],
            "pid": [{"line_id": ln["line_id"], "name": ln["name"], "fluid": ln["fluid"], "listed": ln["line_id"] in listed,
                     "method": listed.get(ln["line_id"], {}).get("격리방법", "-"),
                     "blind": listed.get(ln["line_id"], {}).get("맹판설치", ""),
                     "gas": listed.get(ln["line_id"], {}).get("가스측정", "")} for ln in res["pid_lines"]],
            "file": file_url(path), "steps": info}


# ====================================================================== 안전 문서 — 산업재해조사표 · 사고조사보고서
# 10/13 개편 — 사고 한 건 = 기록 한 줄(accident_case.py). 재해 정보를 한 번 넣으면 두 문서에 같이 들어가고,
# 진행 상태(감지됨 → 내부 보고서 → 조사표 → 근로자대표 확인 → 제출)를 여기서 바꾼다. 두 문서는 원본 양식에 채운다.
def _control_accidents() -> list[dict]:
    """
    관제가 넘긴 사고 기록 (실시간 관제의 자동 · 버튼 인계 — 인계 기록의 others). 재생 비교 검증본은 뺀다.
    재해자 수 · 휴업일수는 아직 모른다(사람이 확인) — 그래서 '관제 기록'으로 따로 표시하고, 조사표 대상인지는 사람이 정한다.
    """
    seen, out = set(), []
    for h in list_handoffs(include_auto=True):          # 최근 것부터
        if h.get("replay"):
            continue
        for o in h.get("others", []):
            if o.get("kind") != "accident" or not o.get("ts"):
                continue
            key = (o.get("event_id"), o["ts"], o.get("zone"))
            if key in seen:
                continue
            seen.add(key)
            ts = str(o["ts"])
            out.append({"id": o.get("event_id") or f"ACC-{ts[:16]}", "date": ts[:10], "time": ts[11:16], "zone": o.get("zone"),
                        "summary": o.get("reason") or o.get("violation_type") or "사고", "type": o.get("violation_type") or "",
                        "from_control": True, "source": h.get("source", ""), "ptw_ids": [],
                        "injured": "", "lost_days": "", "frame_path": o.get("frame_path"),
                        # 10/14 A-06 — 초까지의 사고 시각(경과 · 사고 전후 구분) · 사고를 확정한 영상 기록 번호
                        "ts": ts, "event_ids": [o["source_event_id"]] if o.get("source_event_id") else [],
                        "run_kind": o.get("run_kind") or "", "data_space": o.get("data_space") or ""})
    out.sort(key=lambda a: (a["date"], a["time"]))
    return out


def _accs() -> list[dict]:
    """사고 목록 — 사업장 정보에 적은 사고 + 관제가 넘긴 사고 기록. 조사표 대상인지는 진행 상태에서 사람이 정한다(10/13)."""
    out = list(load_profile().get("accidents", []))
    have = {a["id"] for a in out}
    for a in _control_accidents():
        if a["id"] not in have:
            have.add(a["id"])
            out.append(a)
    return sorted(out, key=lambda a: (a["date"], a.get("time", "")))


def _acc(aid: str) -> dict:
    acc = next((a for a in _accs() if a["id"] == aid), None)
    if not acc:
        raise KeyError(f"없는 사고: {aid}")
    return acc


def _place(acc: dict) -> str:
    return f"{acc['zone']} {_zn(acc['zone'])}" if acc.get("zone") else ""


@router.get("/docs/acc")
def acc_list():
    try:                                    # 방금 관제에서 난 사고도 보이게 — 자동 인계를 기다리지 않고 지금 넘긴다
        from control.session import SESSION
        SESSION._flush()
    except Exception:  # noqa: BLE001 — 인계가 안 돼도 목록은 보인다
        pass
    rows = case_rows(_accs(), _zn)
    summ = stage_summary(rows, _today())
    ctrl = [r for r in rows if r["from_control"]]
    default = (ctrl or rows or [{}])[-1].get("id")
    return {"accidents": [{k: r[k] for k in ("id", "date", "time", "zone", "summary", "status", "status_label", "target",
                                             "from_control", "type", "due")} for r in rows],
            "default": default, "stages": summ["stages"],
            "soon": [{"id": r["id"], "zone": r["zone"], "zname": r["zname"], "type": r["type"], "status": r["status"],
                      "status_label": r["status_label"], "due": r["due"], "dday": r["dday"], "target": r["target"]}
                     for r in summ["soon"]]}


def _timeline(facts) -> list[dict]:
    return [{"t": t["ts"].replace("T", " ")[5:16], "src": t["src"], "what": t["what"],
             "kind": "hit" if t["src"].startswith("ACC") or t["src"] == facts["acc"]["id"] else ("shadow" if "무음" in t["what"] else "")}
            for t in facts["timeline"]]


def _photos(acc: dict, facts: dict, evs: list[dict]) -> list[dict]:
    """
    사고조사보고서의 사고현장 사진 (최대 2장) — 그 사고에 직접 묶인 프레임만 쓴다 (10/14 A-06).
      ① 사고 기록의 프레임(영상이 확정한 사고 = 그 순간 관제 프레임)  ② 사고에 묶인 기록(event_ids)의 프레임
    다른 위반 기록의 사진으로 대신하지 않는다 — 없으면 빈 칸('사고 장면 사진 미확보', 출력 후 붙인다).
    """
    from safety_docs.config import doc_file
    out = []
    if acc.get("frame_path") and doc_file(acc["frame_path"]).exists():
        out.append({"path": doc_file(acc["frame_path"]), "caption": f"{_place(acc)} 사고 순간 (관제 프레임)", "ts": acc.get("time", "")})
    by_id = {e["event_id"]: e for e in evs}
    ids = list(acc.get("event_ids") or [])
    for eid in ids:
        ev = by_id.get(eid)
        p = _frame_path(ev) if ev else None
        if p and all(x["path"] != p and x["path"].read_bytes() != p.read_bytes() for x in out):
            out.append({"path": p, "caption": f"{ev['ts'][11:16]} {ev['violation_type'].replace('_', ' ')}", "ts": ev["ts"][11:16]})
        if len(out) >= 2:
            break
    return out


def _acc_detail(acc: dict) -> dict:
    evs, _ = load_events()
    f = build_accident_facts(acc, evs, load_rulesets(), list_ptws())
    case = get_case(acc["id"])
    if not case.get("acc_type"):
        case["acc_type"] = guess_type(acc.get("type") or acc.get("summary", ""))
    if case.get("lost_days") in ("", None) and acc.get("lost_days") not in ("", None):
        case["lost_days"] = acc["lost_days"]
    if not case.get("fatal") and acc.get("fatal"):
        case["fatal"] = True
    files = case.get("files") or {}
    photos = _photos(acc, f, evs)
    return {"acc": {k: v for k, v in acc.items() if k != "frame_path"}, "zname": _zn(acc["zone"]), "place": _place(acc),
            "timeline": _timeline(f), "due": f["due"], "dday": (date.fromisoformat(f["due"]) - _today()).days,
            "case": case, "status": case.get("status") or "detected", "status_label": STAGE_LABEL.get(case.get("status") or "detected"),
            "target": is_target(case, acc), "stages": [{"key": k, "label": STAGE_SHORT[k]} for k, _ in STAGES],
            "photos": [{"i": i, "caption": p["caption"]} for i, p in enumerate(photos)],
            "candidates": candidates(case.get("acc_type") or "", case.get("causes") or []),
            "files": {"form": file_url(files.get("form")), "report": file_url(files.get("report")),
                      "form_name": Path(files["form"]).name if files.get("form") else "",
                      "report_name": Path(files["report"]).name if files.get("report") else "",
                      "ver": case.get("files_ver") or case.get("ver")},
            "options": {"types": ACC_TYPES, "employ": EMPLOY, "shift": SHIFT, "causes": CAUSES}}


@router.get("/docs/acc/{aid}")
def acc_show(aid: str):
    return _acc_detail(_acc(aid))


@router.get("/docs/acc/{aid}/photo/{i}")
def acc_photo(aid: str, i: int):
    acc = _acc(aid)
    evs, _ = load_events()
    photos = _photos(acc, build_accident_facts(acc, evs, load_rulesets(), list_ptws()), evs)
    return FileResponse(photos[i]["path"]) if 0 <= i < len(photos) else Response(status_code=404)


@router.post("/docs/acc/{aid}/save")
def acc_save(aid: str, body: dict):
    """
    재해 정보 · 문서 내용을 한 판으로 저장하고 두 문서(원본 양식)를 새로 만든다.
    경과 문장이 비어 있으면 관제 기록으로 초안을 만든다(accident.py — 원인은 단정하지 않는다). 원인 · 대책은 사람이 쓴다.
    """
    acc = _acc(aid)
    fields = {k: v for k, v in body.items() if k in INFO_KEYS + DOC_KEYS}
    merged = {**get_case(aid), **fields}
    evs, _ = load_events()
    facts = build_accident_facts(acc, evs, load_rulesets(), list_ptws())
    if not str(merged.get("narrative") or "").strip():
        fields["narrative"] = merged["narrative"] = draft_accident_report(facts, _llm())["narrative"]
    ver = int(get_case(aid).get("ver") or 0) + 1
    merged["measures"] = [m for m in merged.get("measures") or [] if str(m.get("text", "")).strip()]
    photos = _photos(acc, facts, evs)
    with doc_mark(acc.get("run_kind")):
        form = accident_form_docx(acc, merged, _place(acc), load_profile(), OUTPUT_DIR / f"산업재해조사표_{aid}_v{ver}.docx")
        report = accident_report_docx(acc, merged, _place(acc), [(p["path"], p["caption"]) for p in photos],
                                      OUTPUT_DIR / f"사고조사보고서_{aid}_v{ver}.docx")
    save_case(aid, fields, files={"form": str(form), "report": str(report)})
    return _acc_detail(acc)


@router.post("/docs/acc/{aid}/stage")
def acc_stage(aid: str, body: dict):
    """진행 상태 바꾸기 — next(다음 단계) · close(보고 대상 아님, 사유 필수) · reopen(다시 열기)."""
    change_stage(_acc(aid), body.get("action", ""), body.get("reason", ""))
    return _acc_detail(_acc(aid))


@router.get("/docs/acc/{aid}/zip")
def acc_zip(aid: str):
    files = get_case(aid).get("files") or {}
    # 저장된 경로는 이름만 쓴다 — 데이터 공간 폴더를 옮겨도 그 공간의 outputs 에서 찾는다 (10/14)
    paths = [OUTPUT_DIR / Path(str(p).replace("\\", "/")).name if p else None for p in (files.get("form"), files.get("report"))]
    if not all(p and Path(p).exists() for p in paths):
        raise ValueError("먼저 '저장하고 두 문서 초안 만들기'로 문서를 만든다")
    ver = get_case(aid).get("files_ver") or ""
    z = accident_zip(paths, OUTPUT_DIR / f"산업재해_{aid}_v{ver}.zip")
    return FileResponse(z, filename=z.name)


# ====================================================================== 기록 — 산업재해 기록 (10/13)
@router.get("/accident-stats")
def accident_stats_api(months: int = 12, zone: str = "", scope: str = "all"):
    rows = case_rows(_accs(), _zn)
    st = accident_stats(rows, _today(), months=max(1, min(int(months), 36)), zone=zone, scope=scope)
    st["zones"] = sorted({r["zone"] for r in rows if r["zone"]})
    st["zone_names"] = {z: _zn(z) for z in st["zones"]}
    st["updated"] = now().isoformat(timespec="minutes")
    # 10/14 — 이 공간의 사고 기록을 시험 · 운영 · 시연 구분값으로 센다 (집계 자체는 고른 데이터 공간의 사고 전부 — 화면에 구분을 같이 보인다)
    kinds: dict[str, int] = {}
    for a in _accs():
        k = a.get("run_kind") or ("사업장 정보" if not a.get("from_control") else "미기록")
        kinds[k] = kinds.get(k, 0) + 1
    st["run_kinds"] = kinds
    import dataspace
    st["data_space"] = dataspace.info(dataspace.current())["label"]
    return st


# ====================================================================== 안전 문서 — 관제 인계
@router.get("/docs/handoff")
def handoff_list():
    out = []
    for h in list_handoffs(include_auto=False):
        out.append({"id": h["handoff_id"], "source": h["source"], "ts": h["ts"].replace("T", " ")[:16],
                    "replay": bool(h.get("replay")),
                    "n": len(h["event_ids"]) + len(h.get("duplicates", [])),
                    "gates": sum(1 for o in h.get("others", []) if o["kind"] == "gate"),
                    "accidents": sum(1 for o in h.get("others", []) if o["kind"] == "accident")})
    return {"handoffs": out}


@router.get("/docs/handoff/{hid}")
def handoff_show(hid: str):
    if not get_handoff(hid):
        raise KeyError(f"없는 인계: {hid}")
    evs, as_of = load_events(include_replay=True)
    c = report_candidates(hid, evs, as_of, load_scales(), load_profile().get("accidents"))
    h = c["handoff"]
    return {"id": hid, "source": h["source"], "ts": h["ts"].replace("T", " "), "by": h.get("by", ""), "note": h.get("note", ""),
            "replay": (h.get("replay") or {}).get("text", ""),
            "received": len(h["event_ids"]), "duplicates": len(h.get("duplicates", [])), "warnings": h.get("warnings", []),
            "events": [{"id": x["event_id"], "t": x["ts"][5:16].replace("T", " "), "zone": x["zone"], "mode": x.get("mode") or "-",
                        "type": x["violation_type"], "level": x.get("level"), "alerted": x.get("alerted", True),
                        "why": (f"{x['row']}번 줄 · " if x.get("row") else "") + (x.get("reason") or ""),
                        "frame": bool(x.get("frame_path"))} for x in c["events"]],
            "corrective": [{"id": x["event_id"], "t": x["ts"][11:16], "zone": x["zone"], "type": x["violation_type"],
                            "level": x["level"], "frame": x["frame"], "issued": x["issued"]} for x in c["corrective"]],
            "adhoc": c["adhoc"],
            "gates": [{"t": g["ts"][11:16], "zone": g["zone"], "type": g.get("violation_type"), "reason": g.get("reason", "")}
                      for g in c["gates"]],
            "accidents": [{"t": a["ts"][11:16], "zone": a["zone"], "type": a.get("violation_type"), "reason": a.get("reason", "")}
                          for a in c["accidents"]]}


@router.post("/docs/handoff/{hid}/make")
def handoff_make(hid: str, body: dict):
    picked = body.get("event_ids") or []
    if not picked:
        raise ValueError("시정지시서를 만들 이벤트를 고른다")
    evs, as_of = load_events(include_replay=True)
    made = make_correctives(list(picked), evs, load_rulesets(), load_legal(), load_scales(), _llm(), issued=as_of)
    return {"made": [{"doc_no": m["doc_no"], "event_id": m["event_id"], "severity": m["severity"], "deadline": m["deadline"], "replay": m.get("replay", False),
                      "warnings": m["warnings"], "file": file_url(m["path"])} for m in made]}


@router.post("/docs/handoff/upload")
async def handoff_upload(file: UploadFile = File(...), base_dir: str = Form(""), source: str = Form("")):
    suffix = Path(file.filename or "events.jsonl").suffix or ".jsonl"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        path = tmp.name
    try:
        h = receive_file(path, source=source.strip() or f"엔진 결과 파일 · {file.filename}",
                         base_dir=base_dir.strip().strip('"') or None)
    finally:
        Path(path).unlink(missing_ok=True)
    return {"handoff_id": h["handoff_id"], "msg": f"{h['handoff_id']} — 감지 {len(h['event_ids'])}건 받음"
            + (f" · 이미 받은 {len(h['duplicates'])}건 건너뜀" if h["duplicates"] else "")}


# ====================================================================== 안전소통
@router.get("/voice")
def voice():
    reps = list_reports()
    s = voice_summary(reps)
    since = f"{_today() - timedelta(days=30)}"
    pend = [ra for ra in list_assessments() if ra["state"] == "worker_pending"]
    return {"summary": {"total": s["total"], "open": s["open"], "doing": sum(1 for r in reps if r["state"] == "조치 중"),
                        "done": s["done"], "rate": round(s["rate"]), "recent": sum(1 for r in reps if r["ts"][:10] >= since)},
            "reports": [{"id": r["report_id"], "ts": r["ts"].replace("T", " "), "kind": r["kind"], "zone": r["zone"],
                         "text": r["text"], "reporter": r.get("reporter") or "익명", "state": r["state"],
                         "action": r.get("action", ""), "by": r.get("by", "")} for r in reps],
            "pending": [{"id": ra["ra_id"], "kind": ra["kind"], "manager": ra["manager"], "n": len(ra["rows"])} for ra in pend]}


@router.get("/voice/ra/{ra_id}")
def voice_ra(ra_id: str):
    ra = get_assessment(ra_id)
    return {"id": ra_id, "kind": ra["kind"], "manager": ra["manager"],
            "rule_rejected": sorted(ra.get("rule_rejected", {})),
            "rows": [{"zone": r["zone"], "mode": r["mode"], "score": r["score"], "grade": r["grade"],
                      "hazard": r.get("hazard", ""), "measures": _measures_text(r.get("measures", []), ra.get("rule_rejected"))}
                     for r in ra["rows"]]}


@router.post("/voice/report")
def voice_submit(body: dict):
    r = submit_report(body.get("kind"), body.get("zone"), body.get("text") or "", body.get("reporter") or "")
    return {"msg": f"{r['report_id']} 접수 — {r['kind']} · {r['zone']}"}


@router.post("/voice/update")
def voice_update(body: dict):
    if not body.get("id"):
        raise ValueError("제보를 고른다")
    update_report(body["id"], body.get("state"), body.get("action") or "", body.get("by") or "")
    return {"msg": f"{body['id']} → {body.get('state')}"}


@router.post("/voice/confirm")
def voice_confirm(body: dict):
    ra_id = body.get("ra_id")
    if not ra_id:
        raise ValueError("확인할 평가를 고른다")
    ra = confirm_revision(ra_id, body.get("name") or "", body.get("note") or "")
    assessment_to_excel(ra["rows"], OUTPUT_DIR / f"위험성평가표_{ra_id}.xlsx", rulesets=load_rulesets(),
                        scales=load_scales(), record=ra)
    excluded = sorted(ra.get("rule_rejected", {}))
    rules = [i for i in sorted({m["rule_id"] for r in ra["rows"] for m in r["measures"] if m.get("rule_id")}) if i not in excluded]
    return {"msg": f"확정 — {ra_id} · 관리자 {ra['manager']} · 근로자 대표 {ra['worker_rep']}. "
                   + (f"규칙셋에 {', '.join(rules)} 반영 → 기록의 규칙셋 개정 이력" if rules else "규칙 변경 없음")
                   + (f" · 반려된 변경안 {', '.join(excluded)} 은 올리지 않았다" if excluded else "")}


@router.post("/voice/reject")
def voice_reject(body: dict):
    ra_id = body.get("ra_id")
    if not ra_id:
        raise ValueError("반려할 평가를 고른다")
    reject_revision(ra_id, "근로자 대표", body.get("name") or "", body.get("reason") or "")
    return {"msg": f"반려 — {ra_id} · 사유: {body.get('reason')}"}


# ====================================================================== 기록
@router.get("/archive")
def archive():
    evs, as_of = load_events()
    docs = load_documents()
    return {"docs": [{**d, "url": file_url(d.get("파일"))} for d in document_rows(docs)],
            "revisions": revision_rows(), "rulesets": ruleset_rows(load_rulesets()),
            "effects": effect_rows(evs, as_of, load_scales()),
            "retention": [{"name": d["name"], "years": d["retention_years"], "basis": d["retention_basis"],
                           "from": d["retention_from"], "statutory": d["statutory"]} for d in docs.values()]}


@router.post("/docs/upload-csv")
async def read_csv_upload(file: UploadFile = File(...)):
    """격리 목록 CSV 파일 → 글자 (UTF-8 · CP949)."""
    raw = await file.read()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return {"text": raw.decode(enc)}
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV 글자를 읽지 못했다 (UTF-8 또는 CP949)")

