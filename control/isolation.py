"""
격리 목록 대조 — 관제의 입력 창구 (작업허가서 · 격리 목록 · 작업계획서는 여기서만 받는다)

  register()    작업허가서 등록 — 격리 목록 CSV 를 배관 계통도와 대조하고,
                ① 문서 자동화에 점검 대상으로 저장(docgen handoff.register_ptw)
                ② 실시간 세션이 돌고 있으면 엔진에 신호로 넣는다(작업 종류 → 모드 신호, 격리 목록 → 작업 전 게이트)
  step()        단계 입력 — 맹판 설치 완료 · 설치 취소(정정)(R2) · 가스 측정(R4) · 퍼지 시작 · 종료 · 분 기록(R4)
                control/records/isolation_steps.jsonl 에 추가만 하고(원래 값을 덮어쓰지 않는다), 세션이 돌면 엔진에도 넣는다
  view()        허가서 하나의 대조 결과 — 계통도 ↔ 목록 · 해제 조건 네 개 · 측정 유효시간 · 퍼지 진행 · 동시작업
  history()     이력 줄 (최근 순, 이전 값 · 시계 뒤 기록 표시)
  with_steps()  문서 자동화 작업허가서 점검이 같은 데이터를 읽게 — 허가서 원본에 단계 입력을 얹은 사본

격리 목록이 필요한 허가서는 정비 허가서뿐이다(화기 허가서는 '격리 비대상' — 대신 동시작업을 본다). 문서 자동화 점검과 같은 기준.
배관 계통도는 사업장 패키지 site.json 의 references.piping 이 원본이다(문서 자동화도 같은 것을 읽는다).
기준값: 퍼지 최소 시간 · LEL 기준 = 문서 자동화 config/rulesets.json 의 isolation 블록,
        측정 유효시간 = 사업장 패키지 rules.json 의 vars.gas_valid_min (엔진이 판정에 쓰는 값과 같다).
"""
from __future__ import annotations

import csv
import io
import math
from datetime import datetime, timedelta

from .common import RECORD_DIR, append_jsonl, load_config, read_jsonl

STEP_LOG = RECORD_DIR / "isolation_steps.jsonl"
YES = {"O", "○", "Y", "YES", "예", "완료", "TRUE", "1"}
COLS = ["line_id", "배관", "격리방법", "맹판설치", "벤트", "가스측정"]


def piping() -> dict:
    from safety_docs.config import load_piping
    return load_piping()


def iso_cfg() -> dict:
    from safety_docs.config import load_rulesets
    return load_rulesets().get("isolation", {})


def ptws() -> list[dict]:
    from safety_docs.ptw import list_ptws
    return list_ptws()


def steps(ptw_id: str | None = None) -> list[dict]:
    return [r for r in read_jsonl(STEP_LOG) if ptw_id is None or r.get("ptw_id") == ptw_id]


def parse_csv(text: str) -> list[dict]:
    text = (text or "").lstrip("﻿").strip()
    if not text:
        return []
    rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(io.StringIO(text))]
    if rows and "line_id" not in rows[0]:
        raise ValueError("첫 줄에 line_id 열이 없다 — 열: " + ", ".join(COLS))
    rows = [r for r in rows if r.get("line_id")]
    if not rows:
        raise ValueError("배관 줄이 하나도 없다")
    return rows


def sample_csv(zone: str) -> str:
    """예시 채우기 — 계통도의 마지막 줄을 일부러 뺀 목록 (누락이 어떻게 잡히는지 보이려고)."""
    lines = piping().get(zone, {}).get("lines", [])
    if not lines:
        return ""
    keep = lines[:-1] if len(lines) > 1 else lines
    out = [",".join(COLS)]
    for i, ln in enumerate(keep):              # 첫 줄만 맹판 설치 완료 — 나머지는 단계 입력으로 받는 모습을 보이려고
        out.append(f"{ln['line_id']},{ln['name']},맹판,{'O' if i == 0 else ''},O,{'O' if ln.get('hazard_source') else 'X'}")
    return "\n".join(out)


def cross_check(zone: str, rows: list[dict] | None) -> dict:
    """계통도 ↔ 목록. 계통도에만 있으면 누락(R1 게이트), 목록에만 있으면 계통도 확인 필요."""
    p = piping().get(zone, {})
    ref = p.get("lines", [])
    listed = {r.get("line_id"): r for r in (rows or [])}
    lines = []
    for ln in ref:
        r = listed.get(ln["line_id"])
        if rows is None:
            lines.append({**ln, "in_list": False, "blind": "none", "row": None})
        elif r is None:
            lines.append({**ln, "in_list": False, "blind": "valve", "row": None})
        else:
            done = r.get("격리방법", "맹판") == "맹판" and r.get("맹판설치", "").strip().upper() in YES
            method_valve = r.get("격리방법") and r.get("격리방법") != "맹판"
            lines.append({**ln, "in_list": True, "blind": "done" if done else ("valve" if method_valve else "pending"), "row": r})
    extra = [f"{r['line_id']} {r.get('배관', '')}".strip() for r in (rows or []) if r.get("line_id") not in {x["line_id"] for x in ref}]
    return {"equipment": p.get("equipment", zone), "lines": lines, "extra": extra, "has_pid": bool(ref)}


def next_ptw_id(day: str) -> str:
    d = day.replace("-", "")[:8]
    n = [int(s) for p in ptws() if p["ptw_id"].startswith(f"PTW-{d}-")
         for s in [p["ptw_id"].rsplit("-", 1)[1]] if s.isdigit()]       # 긴급 허가(PTW-…-E1) 같은 번호는 건너뛴다
    return f"PTW-{d}-{max(n, default=0) + 1:02d}"


def register(zone: str, work_type: str, start: str, end: str, work: str, supervisor: str, workers: int | None,
             csv_text: str | None, no_list: bool, ptw_id: str | None = None, extra: dict | None = None) -> dict:
    """
    작업허가서 등록 — 입력 창구 한 곳. 등록 결과와 엔진이 남긴 메모를 돌려준다.
    작업허가서 파일(.docx)로 채운 경우(10/13) ptw_id 는 허가서의 번호, extra 는 파일에서 읽은 퍼지 · 가스 측정 ·
    화재감시자 · 안전조치 확인 · 서명 등 — 문서 자동화의 작업허가서 점검이 그대로 읽는다(ptw_docx.py).
    """
    from safety_docs.handoff import register_ptw
    from .session import SESSION
    wt = load_config()["work_types"].get(work_type)
    if not wt:
        raise ValueError(f"작업 종류를 고른다 ({', '.join(k for k in load_config()['work_types'] if not k.startswith('_'))})")
    if not work.strip():
        raise ValueError("작업 내용을 적는다")
    try:
        t0, t1 = datetime.fromisoformat(start), datetime.fromisoformat(end)
    except ValueError:
        raise ValueError("시작 · 종료는 2026-10-12T13:00 모양으로") from None
    if t1 <= t0:
        raise ValueError("종료가 시작보다 늦어야 한다")
    rows = None if no_list else parse_csv(csv_text or "")
    if not no_list and not rows:
        raise ValueError("격리 목록 CSV 를 올리거나 붙여넣는다. 목록이 없으면 '목록 없이 등록'을 켠다")
    chk = cross_check(zone, rows)
    ptw = {"ptw_id": (ptw_id or "").strip() or next_ptw_id(start[:10]), "type": wt["ptw_type"], "zone": zone, "work": work.strip(),
           "work_type": work_type, "start": t0.isoformat(timespec="minutes"), "end": t1.isoformat(timespec="minutes"),
           "supervisor": supervisor.strip(), "workers": int(workers) if workers else None,
           "purge": None, "gas_tests": [], "fire_watch": None, "source": "관제 입력창"}
    if extra:                                    # 작업허가서 파일에서 읽은 값 (10/13)
        ptw.update({k: v for k, v in extra.items() if k not in ptw or ptw[k] in (None, [], "")})
        ptw["source"] = "관제 입력창 · 작업허가서 파일"
    rec = register_ptw(ptw, rows if rows is not None else None)
    notes = []
    if SESSION.sid:
        notes += SESSION.apply_signal(wt["signal"], zone, value=work_type, source="입력창", note=f"{rec['ptw_id']} {work}")
        if rows is not None:
            from safety_docs.config import doc_file
            path = doc_file(rec["isolation_list_file"])
            notes += SESSION.apply_signal("isolation_list", zone, value=str(path), source="입력창",
                                          note=f"{rec['ptw_id']} 격리 목록")
    return {"ptw": rec, "check": chk, "engine_notes": notes}


# ====================================================================== 단계 입력
def gas_fail_words() -> tuple:
    """
    가스 측정 실패를 적는 말 (STEP 02-10 B-3) — 사업장 패키지 신호 사전 gas_test.fail_words 와 같은 목록 하나를 쓴다.
    이 말만 숫자 대신 받는다. 빈칸 · 다른 글자 · nan · inf · 음수는 예전처럼 입력 오류로 거부한다.
    """
    try:
        from .common import package
        return tuple(package().signals.get("gas_test", {}).get("fail_words") or ())
    except Exception:  # noqa: BLE001 — 패키지를 못 읽으면 실패 입력을 받지 않는다(예전 동작)
        return ()


def is_gas_fail(v) -> bool:
    return v is not None and str(v).strip() in gas_fail_words() and str(v).strip() != ""


STEP_LABEL = {"blind": "맹판 설치 완료", "blind_undo": "맹판 설치 취소 (정정)", "gas": "가스 측정",
              "purge_start": "퍼지 시작", "purge_end": "퍼지 종료", "purge": "퍼지 시간 기록"}


def step(ptw: dict, kind: str, line_id: str | None, value: str | None, by: str, note: str = "") -> list[str]:
    """
    단계 입력 하나 — 기록은 추가만 한다(원래 값을 덮어쓰지 않는다. 화면은 마지막 기록을 현재값으로 읽는다).
      blind        맹판 설치 완료 (배관)            → 엔진 blind_installed
      blind_undo   맹판 설치 취소 · 정정 (배관, 사유) → 엔진 blind_removed (unmark)
      gas          가스 측정 LEL % (측정 지점 = 배관) → 엔진 gas_test
      purge_start  퍼지 시작                          → 엔진 purge_start
      purge_end    퍼지 종료                          → 엔진 purge_end
      purge        퍼지 시간을 분으로 나중에 적기       → 엔진 purge_start(거꾸로 계산) + purge_end
    실시간 세션이 돌면 같은 것을 엔진 신호로 넣는다. 시각은 관제의 '지금'(세션이 돌면 시연 시계).
    """
    from .session import SESSION
    if kind not in STEP_LABEL:
        raise ValueError(f"모르는 단계 입력: {kind}")
    if kind in ("blind", "blind_undo", "gas") and not line_id:
        raise ValueError("배관을 고른다")
    if kind == "blind_undo" and not (note or "").strip():
        raise ValueError("정정 사유를 적는다 — 왜 취소하는지 기록에 남는다")
    if kind == "gas" and is_gas_fail(value):
        value = str(value).strip()      # 측정 실패 기록 — 원래 말 그대로 남기고, 엔진에도 같은 값이 가스 측정으로 간다(엔진이 그 지점 실패 기록으로 남김)
    elif kind in ("gas", "purge"):
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise ValueError("숫자를 적는다 (가스 측정은 LEL %, 퍼지는 분)") from None
        if not math.isfinite(v):       # nan · inf · -inf · 1e309 — float() 는 통과하지만 측정값이 아니다 (10/13 K05 잔여 B · STEP 02-7)
            raise ValueError("유한한 숫자를 적는다 — 무한대 · NaN 은 측정값으로 쓰지 않는다")
        if v < 0:
            raise ValueError("0 이상")
    from .common import system_now
    now = system_now()     # 기록 시각 = 엔진에 넣는 측정 시각 — 같은 값 하나를 마이크로초까지 그대로 쓴다 (STEP 02-10 C-1)
    cur = view(ptw, with_simops=False)["purge"]
    if kind == "purge_start" and cur["state"] == "run":
        raise ValueError(f"퍼지가 이미 진행 중이다 ({cur['start']} 시작) — 끝나면 '퍼지 종료'를 넣는다")
    if kind == "purge_end" and cur["state"] != "run":
        raise ValueError("진행 중인 퍼지가 없다 — 먼저 '퍼지 시작'을 넣거나, 끝난 퍼지는 분으로 적는다")
    append_jsonl(STEP_LOG, {"ts": now.isoformat(timespec="microseconds"), "ptw_id": ptw["ptw_id"], "zone": ptw["zone"],
                            "kind": kind, "line_id": line_id, "value": value, "by": by.strip(),
                            **({"note": note.strip()} if note and note.strip() else {})})
    notes = []
    if SESSION.sid:
        z, pid = ptw["zone"], ptw["ptw_id"]
        if kind == "blind":
            notes += SESSION.apply_signal("blind_installed", z, line_id, source="입력창", note=f"{pid} 맹판 설치 완료")
        elif kind == "blind_undo":
            notes += SESSION.apply_signal("blind_removed", z, line_id, source="입력창", note=f"{pid} 맹판 설치 취소 — {note}")
        elif kind == "gas":
            notes += SESSION.apply_signal("gas_test", z, line_id, str(value), source="입력창", note=f"{pid} 가스 측정", ts=now)
        elif kind == "purge_start":
            notes += SESSION.apply_signal("purge_start", z, source="입력창", note=f"{pid} 퍼지 시작")
        elif kind == "purge_end":
            notes += SESSION.apply_signal("purge_end", z, source="입력창", note=f"{pid} 퍼지 종료")
        else:
            t = SESSION.clock()
            notes += SESSION.apply_signal("purge_start", z, source="입력창", ts=t - timedelta(minutes=float(value)),
                                          note=f"{pid} 퍼지 {value}분")
            notes += SESSION.apply_signal("purge_end", z, source="입력창", note=f"{pid} 퍼지 종료")
    return notes


# ====================================================================== 판정
def needs_isolation(ptw: dict) -> bool:
    """격리 목록이 필요한 허가서 — 정비 허가서. 화기 허가서는 받지 않는다 (문서 자동화 작업허가서 점검과 같은 기준)."""
    return ptw.get("type", "정비") == "정비"


def engine_vars() -> dict:
    """엔진이 지금 쓰는 규칙 값(사업장 패키지 rules.json vars + 켜진 개정안) — 측정 유효시간을 엔진과 같게 읽으려고."""
    try:
        from .common import package
        from .session import SESSION, resolve_ruleset
        pkg = package()
        ids = SESSION.meta.get("applied") if SESSION.sid else None
        if ids is None:
            ids, _ = resolve_ruleset(load_config().get("live", {}).get("ruleset", "docgen"), pkg)
        return pkg.rules(list(ids)).get("vars", {})
    except Exception:            # 패키지를 못 읽어도 격리 대조는 돈다 — 기본값으로
        return {}


def _dt(day: str, hhmm: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(f"{day}T{hhmm}") if hhmm else None
    except ValueError:
        return None


def phase(ptw: dict, now: datetime) -> tuple[str, bool]:
    """(예정 · 진행 중 · 종료, 활성 여부). 작업 전 게이트를 보는 화면이라 '오늘 시작 전'도 활성으로 본다."""
    try:
        t0, t1 = datetime.fromisoformat(ptw["start"]), datetime.fromisoformat(ptw["end"])
    except (KeyError, ValueError):
        return "시각 없음", False
    if now < t0:
        return "예정", t0.date() == now.date()
    if now <= t1:
        return "진행 중", True
    return "종료", False


def _records(ptw: dict, rows: list[dict] | None) -> list[dict]:
    """
    이 허가서에 대한 기록 전부 — 원래 값을 덮어쓰지 않고 그대로 늘어놓는다.
      격리 목록 기재(맹판 O) · 허가서 기재(가스 측정 · 퍼지 분) · 단계 입력(isolation_steps.jsonl)
    시각이 없는 기재값(ts=None)은 처음 상태로 본다.
    """
    day = (ptw.get("start") or "")[:10]
    out = []
    for r in rows or []:
        if r.get("격리방법", "맹판") == "맹판" and r.get("맹판설치", "").strip().upper() in YES:
            out.append({"ts": None, "kind": "blind", "line_id": r["line_id"], "value": "O", "by": "", "src": "격리 목록"})
    for g in ptw.get("gas_tests") or []:
        if g.get("line_id") and g.get("lel_pct") is not None:
            out.append({"ts": _dt(day, g.get("time")), "kind": "gas", "line_id": g["line_id"], "value": g["lel_pct"],
                        "by": g.get("by", ""), "src": "허가서"})
    pm = (ptw.get("purge") or {}).get("minutes")
    if pm is not None:
        out.append({"ts": None, "kind": "purge", "line_id": None, "value": pm, "by": "", "src": "허가서"})
    for s in steps(ptw["ptw_id"]):
        try:
            ts = datetime.fromisoformat(s["ts"])
        except (KeyError, ValueError):
            continue
        out.append({"ts": ts, "kind": s["kind"], "line_id": s.get("line_id"), "value": s.get("value"),
                    "by": s.get("by", ""), "src": "단계 입력", "note": s.get("note", "")})
    out.sort(key=lambda r: (r["ts"] is not None, r["ts"] or datetime.min))
    return out


def _mins(a: datetime, b: datetime) -> float:
    return round((b - a).total_seconds() / 60, 1)


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _gas_rank(v) -> float:
    """같은 시각 가스 기록끼리 고를 때의 순위 — 큰 값일수록 위. 숫자가 아니거나 유한하지 않은 값은 가장 위(기준 밖으로 본다)."""
    x = _num(v)
    return float("inf") if x is None or not math.isfinite(x) else x


def _bad_num(v) -> bool:
    """예전에 저장된 비정상 수치(inf · -inf · nan) — 숫자로는 읽히지만 측정값이 아니다. 기록은 그대로 두고 판정 · 화면에서만 가린다 (STEP 02-7)."""
    x = _num(v)
    return x is not None and not math.isfinite(x)


def simops(ptw: dict, all_ptws: list[dict] | None = None) -> list[dict]:
    """동시작업 — 시간이 겹치는 같은 · 인접 구역의 정비 ↔ 화기 허가 (문서 자동화 점검 SIMOPS 와 같은 기준)."""
    all_ptws = ptws() if all_ptws is None else all_ptws
    adj = piping().get("adjacent_zones", {}).get(ptw["zone"], [ptw["zone"]])
    out = []
    try:
        a0, a1 = datetime.fromisoformat(ptw["start"]), datetime.fromisoformat(ptw["end"])
    except (KeyError, ValueError):
        return out
    for o in all_ptws:
        if o["ptw_id"] == ptw["ptw_id"] or o["zone"] not in adj:
            continue
        try:
            b0, b1 = datetime.fromisoformat(o["start"]), datetime.fromisoformat(o["end"])
        except (KeyError, ValueError):
            continue
        if a0 < b1 and b0 < a1 and {ptw.get("type"), o.get("type")} == {"정비", "화기"}:
            out.append(o)
    return out


def view(ptw: dict, with_simops: bool = True, now: datetime | None = None) -> dict:
    """
    허가서 하나의 대조 결과 — 화면(계통도 · 목록 · 해제 조건 · 단계 입력 · 이력)이 그대로 쓴다.
    해제 조건 네 개: ① 목록 일치(R1) ② 맹판 설치 완료(R2) ③ 퍼지 시간(R4) ④ LEL 기준 이하 · 측정 유효(R4)
    기준값: 퍼지 분 · LEL = 문서 자동화 rulesets.json isolation, 측정 유효시간 = 사업장 패키지 rules.json vars.gas_valid_min
    관제의 '지금'(세션이 돌면 시연 시계)보다 뒤의 기록은 아직 일어나지 않은 것으로 보고 현재 상태에 넣지 않는다.
    """
    from safety_docs.ptw import load_isolation
    from .common import system_now
    now = now or system_now()
    try:
        rows = load_isolation(ptw)
    except (OSError, ValueError):
        rows = None
    target = needs_isolation(ptw)
    chk = cross_check(ptw["zone"], rows)
    cfg = iso_cfg()
    purge_cfg = cfg.get("purge", {})
    lel_max = purge_cfg.get("lel_max", 5)
    need = purge_cfg.get("min_minutes", 30)
    ev = engine_vars()
    valid_min = ev.get("gas_valid_min", 120)
    recs = _records(ptw, rows)
    for r in recs:
        r["future"] = r["ts"] is not None and r["ts"] > now
    cur = [r for r in recs if not r["future"]]
    st = steps(ptw["ptw_id"])

    # ---- 맹판 — 배관마다 마지막 기록이 현재값
    last_blind: dict[str, dict] = {}
    for r in cur:
        if r["kind"] in ("blind", "blind_undo") and r["line_id"]:
            last_blind[r["line_id"]] = r
    for ln in chk["lines"]:
        r = last_blind.get(ln["line_id"])
        if r and r["src"] == "단계 입력":
            if r["kind"] == "blind":
                ln["blind"], ln["blind_by_step"] = "done", True
            else:
                method_valve = ln.get("row") and ln["row"].get("격리방법") and ln["row"]["격리방법"] != "맹판"
                ln["blind"] = "valve" if (method_valve or not ln["in_list"]) else "pending"
                ln["blind_undone"] = True
        ln["blind_last"] = ({"t": r["ts"].strftime("%H:%M") if r["ts"] else "", "by": r["by"], "src": r["src"],
                             "kind": r["kind"]} if r else None)
    no_list = rows is None
    # 맹판 대상 — 목록에 적힌 배관 + 목록에 없는 가연물 배관 (밸브만 잠긴 가연물 배관도 해제 아님 · R2)
    blind_targets = [ln for ln in chk["lines"] if ln["in_list"] or ln.get("hazard_source")]
    blind_wait = [ln for ln in blind_targets if ln["blind"] != "done"]

    # ---- 가스 측정 — 가연물 배관이 측정 지점, 없으면 목록의 배관
    haz = [ln for ln in chk["lines"] if ln.get("hazard_source")]
    points = haz or [ln for ln in chk["lines"] if ln["in_list"]]
    last_gas: dict[str, dict] = {}
    for r in cur:
        if r["kind"] == "gas" and r["line_id"]:
            prev = last_gas.get(r["line_id"])
            # 같은 배관 · 같은 시각 기록이 둘 이상이면 큰 값(기준 초과 쪽)을 현재값으로 — 입력 순서와 상관없이 엔진과 같게 (10/13 K05 잔여 A)
            if prev is not None and prev["ts"] == r["ts"] and _gas_rank(prev["value"]) >= _gas_rank(r["value"]):
                continue
            last_gas[r["line_id"]] = r
    mrows = []
    for ln in points:
        r = last_gas.get(ln["line_id"])
        fail = bool(r) and is_gas_fail(r["value"])                      # 측정 실패 기록 (STEP 02-10 B-3)
        # 보완: 실패 전 마지막 숫자 기록이 기준 초과였으면 '위험 미해제'로 알린다 — 실패를 그 값으로 바꾸지는 않는다
        prev = None
        if fail:
            for q in cur:
                if q is r:
                    break
                if q["kind"] == "gas" and q["line_id"] == ln["line_id"] and not is_gas_fail(q["value"]) and not _bad_num(q["value"]) \
                        and _num(q["value"]) is not None:
                    prev = _num(q["value"])
        bad = bool(r) and _bad_num(r["value"])
        v = None if (bad or fail) else (_num(r["value"]) if r else None)
        age = _mins(r["ts"], now) if r and r["ts"] else None
        valid = age is not None and age <= valid_min
        ok = r is not None and v is not None and valid and v <= lel_max
        mrows.append({"point": f"{ln['line_id']} {'벤트' if ln['in_list'] else '하류'}", "line_id": ln["line_id"],
                      "time": r["ts"].strftime("%H:%M") if r and r["ts"] else "—",
                      "value": f"값 오류 ({r['value']})" if bad else ("측정 실패" if fail else (f"LEL {v:g}%" if v is not None else "—")),
                      "lel": v, "bad": bad, "fail": fail, "prev": prev, "prev_over": prev is not None and prev > lel_max,
                      "ok": ok, "measured": r is not None,
                      "valid": valid, "over": v is not None and v > lel_max,
                      "remain": round(valid_min - age) if valid else None, "by": r["by"] if r else "",
                      "src": r["src"] if r else ""})

    # ---- 퍼지 — 시작 · 종료(또는 분으로 적은 기록)를 순서대로 읽는다. 진행 중이면 지금까지 흐른 시간
    pg = {"state": "none", "minutes": None, "start": "", "by": "", "src": "", "t": ""}
    run_at = None
    for r in cur:
        if r["kind"] == "purge":
            pg.update(state="bad" if _bad_num(r["value"]) else "done", minutes=None if _bad_num(r["value"]) else _num(r["value"]),
                      start="", by=r["by"], src=r["src"], t=r["ts"].strftime("%H:%M") if r["ts"] else "")
            run_at = None
        elif r["kind"] == "purge_start":
            run_at = r["ts"]
            pg.update(state="run", minutes=0, start=r["ts"].strftime("%H:%M"), by=r["by"], src=r["src"], t=pg["start"])
        elif r["kind"] == "purge_end" and run_at is not None:
            pg.update(state="done", minutes=_mins(run_at, r["ts"]), by=r["by"] or pg["by"], t=r["ts"].strftime("%H:%M"))
            run_at = None
    if run_at is not None:
        pg["minutes"] = _mins(run_at, now)
    purge_min = pg["minutes"]
    purge_ok = purge_min is not None and purge_min >= need
    pg.update(need=need, ok=purge_ok)

    miss = [ln for ln in chk["lines"] if not ln["in_list"]] if not no_list else []
    pend = [ln for ln in chk["lines"] if ln["in_list"] and ln["blind"] != "done"]
    meas_bad = [m for m in mrows if not m["ok"]]

    # ---- 해제 조건 네 개
    def fmt(x):
        return "—" if x is None else f"{x:g}"
    if no_list:
        c1 = ("fail", "목록 미첨부")
    elif miss:
        c1 = ("fail", " · ".join(ln["line_id"] for ln in miss) + " 누락")
    elif chk["extra"]:
        c1 = ("fail", f"계통도 외 {len(chk['extra'])}건")
    else:
        c1 = ("ok", f"계통도 {len(chk['lines'])} · 목록 {len(chk['lines'])}")
    c2 = ("ok", f"{len(blind_targets)}/{len(blind_targets)} 설치") if not blind_wait else \
        ("fail", " · ".join(ln["line_id"] for ln in blind_wait[:3]) + (" 외" if len(blind_wait) > 3 else "") + " 대기")
    if purge_ok:
        c3 = ("ok", f"{fmt(purge_min)} / {need}분")
    elif pg["state"] == "run":
        c3 = ("run", f"{fmt(purge_min)} / {need}분")
    else:
        c3 = ("fail", "기록 오류 — 다시 기록" if pg["state"] == "bad" else (f"{fmt(purge_min)} / {need}분" if purge_min is not None else "미실시"))
    worst = max((m["lel"] for m in mrows if m["valid"] and m["lel"] is not None), default=None)
    if not mrows:
        c4 = ("na", "측정 지점 없음")
    elif not meas_bad:
        c4 = ("ok", f"전 지점 {len(mrows)}/{len(mrows)}")
    elif any(m["over"] and m["valid"] for m in mrows):
        c4 = ("fail", f"현재 {worst:g}%")
    elif any(m["bad"] for m in mrows):
        c4 = ("fail", "측정값 오류 — 재측정")
    elif any(m["fail"] for m in mrows):
        po = [m for m in mrows if m["fail"] and m["prev_over"]]
        c4 = ("fail", "측정 실패 " + " · ".join(m["line_id"] for m in mrows if m["fail"]) + " — 재측정"
              + (" (실패 전 " + " · ".join(f"{m['line_id']} {m['prev']:g}%" for m in po) + " 기준 초과 · 위험 미해제)" if po else ""))
    elif any(m["measured"] and not m["valid"] for m in mrows):
        c4 = ("fail", "측정 만료")
    else:
        c4 = ("fail", f"측정 {len(mrows) - len(meas_bad)}/{len(mrows)}지점")
    conds = [
        {"no": 1, "key": "list", "rule": "R1", "label": "목록 일치",
         "desc": "계통도의 모든 격리 대상이 목록에 들어 있어야 함", "state": c1[0], "value": c1[1]},
        {"no": 2, "key": "blind", "rule": "R2", "label": "맹판 설치 완료",
         "desc": "격리 대상 배관 모두 맹판 설치 — 밸브만 잠근 것은 해제 아님", "state": c2[0], "value": c2[1]},
        {"no": 3, "key": "purge", "rule": "R4", "label": f"퍼지 {need}분 충족",
         "desc": f"가스 치환을 위해 {need}분 이상 퍼지", "state": c3[0], "value": c3[1]},
        {"no": 4, "key": "lel", "rule": "R4", "label": f"LEL {lel_max:g}% 이하",
         "desc": f"가연물 배관 모든 지점 · 측정 후 {valid_min}분 안의 값", "state": c4[0], "value": c4[1]},
    ]
    waiting = {"blind": len(blind_wait), "gas": len(meas_bad), "purge": 0 if purge_ok else 1}
    all_ok = all(c["state"] == "ok" for c in conds)
    if not target:               # 화기 허가서 — 격리 해제 조건을 따지지 않는다
        conds, waiting, all_ok = [], {"blind": 0, "gas": 0, "purge": 0}, False
    gate = target and chk["has_pid"] and (no_list or bool(miss) or bool(chk["extra"]))

    # ---- 동시작업
    partners = []
    if with_simops:
        for o in simops(ptw):
            ov = view(o, with_simops=False, now=now)
            partners.append({"id": o["ptw_id"], "type": o.get("type", ""), "work": o.get("work", ""),
                             "when": f"{o.get('start', '')[11:16]}~{o.get('end', '')[11:16]}",
                             "target": ov["target"], "clear": ov["clear"]})

    # ---- 판정 · 화면 상태 (kind · tag · bar · clear 는 실시간 관제 화면도 쓴다)
    if not target:
        hot = [x for x in partners if x["target"] and x["clear"] != "인정"]
        if hot:
            st_ = ("note", "동시작업 주의",
                   f"격리 비대상(화기 허가) — 같은 시간 {hot[0]['id']} 격리가 해제 인정 전이다. 해제 인정 전 화기 시작 보류", "비대상")
        else:
            st_ = ("mute", "격리 비대상", "화기 허가서는 격리 목록을 받지 않는다 (문서 자동화 점검과 같은 기준)", "비대상")
        verdict = ("격리 비대상", "화기 허가서 — 격리 목록 대신 동시작업 · 가스 측정 · 화재감시자를 본다")
    elif not chk["has_pid"]:
        st_ = ("mute", "계통도 없음", f"{ptw['zone']} 에는 배관 계통도가 없어 대조할 수 없다 — 사업장 패키지 site.json 의 piping 에 넣는다", "판단 불가")
        verdict = ("대조 불가", "배관 계통도가 없는 구역")
    elif no_list:
        st_ = ("warn", "목록 미첨부", "격리 목록이 첨부되지 않았다 — 작업 전에 첨부해야 한다 (LIST)", "불인정")
        verdict = ("작업 시작 차단", "격리 목록이 첨부되지 않아 계통도와 대조할 수 없습니다. 목록을 첨부해야 작업 전 게이트가 열립니다.")
    elif miss:
        st_ = ("crit", f"누락 {len(miss)}건",
               f"계통도 {len(chk['lines'])}건 · 목록 {len(chk['lines']) - len(miss)}건 → 목록에 없는 연결 {len(miss)}건 · 작업 전 차단 (R1)", "불인정")
        verdict = ("작업 시작 차단", "계통도에는 있으나 격리 목록에 없는 배관이 있어 작업 전 게이트가 열리지 않습니다.")
    elif chk["extra"]:
        st_ = ("warn", f"계통도 확인 {len(chk['extra'])}건",
               f"목록에만 있는 배관 {len(chk['extra'])}건 — 계통도가 낡았거나 목록이 틀렸다. 확인 전까지 해제하지 않는다", "불인정")
        verdict = ("작업 시작 차단", "목록에만 있는 배관이 있습니다. 계통도와 목록 중 어느 쪽이 맞는지 확인하기 전까지 게이트가 열리지 않습니다.")
    elif not all_ok:
        n = sum(waiting.values())
        bits = ["대조는 일치"] + ([f"맹판 설치 대기 {len(blind_wait)}건 (R2)"] if blind_wait else []) + \
               [f"측정 {len(mrows) - len(meas_bad)}/{len(mrows)}지점 (R4)"] + \
               ([f"퍼지 {fmt(purge_min)}분 < {need}분 (R4)"] if not purge_ok else [])
        st_ = ("note", f"맹판 대기 {len(blind_wait)}" if blind_wait else ("퍼지 진행 중" if pg["state"] == "run" else
               ("측정 대기" if meas_bad else "퍼지 미달")), " · ".join(bits), "불인정 (가능 유지)")
        verdict = ("작업 시작 대기", f"목록은 계통도와 일치합니다. 단계 입력 {n}건이 남아 해제 조건이 아직 충족되지 않았습니다.")
    else:
        st_ = ("ok", "대조 일치", "계통도와 목록 일치 · 맹판 전부 설치 · 전 지점 측정 기준 이하 · 퍼지 기준 충족", "인정")
        verdict = ("작업 시작 가능", "해제 조건 네 개가 모두 충족됐습니다.")

    ph, active = phase(ptw, now)
    return {"ptw": ptw, "check": chk, "rows": rows, "no_list": no_list, "miss": miss, "pend": pend,
            "meas": mrows, "purge_min": purge_min, "purge_need": need, "lel_max": lel_max, "steps": st,
            "kind": st_[0], "tag": st_[1], "bar": st_[2], "clear": st_[3],
            "open": _is_open(ptw, now),
            # 화면 개편 (10/6) — 아래는 새 값
            "target": target, "gate": gate, "conds": conds, "all_ok": all_ok, "waiting": waiting,
            "blind_targets": [ln["line_id"] for ln in blind_targets], "blind_wait": [ln["line_id"] for ln in blind_wait],
            "purge": pg, "valid_min": valid_min, "verdict": verdict, "phase": ph, "active": active,
            "simops": partners, "records": recs, "now": now}


HIST_LABEL = {"blind": "맹판 설치", "blind_undo": "맹판 정정", "gas": "가스 측정", "purge_start": "퍼지 시작",
              "purge_end": "퍼지 종료", "purge": "퍼지 시간"}


def history(v: dict) -> list[dict]:
    """이력 줄 — 최근 순. 같은 대상의 이전 값은 '이전'으로, 시계보다 뒤 기록은 '시계 뒤'로 표시만 하고 지우지 않는다."""
    now, recs = v["now"], v["records"]
    lel_max, valid_min = v["lel_max"], v["valid_min"]
    latest: dict[tuple, int] = {}
    for i, r in enumerate(recs):
        if r["future"]:
            continue
        key = ("blind", r["line_id"]) if r["kind"] in ("blind", "blind_undo") else \
              ("gas", r["line_id"]) if r["kind"] == "gas" else ("purge", None)
        latest[key] = i
    out = []
    run_at = None
    for i, r in enumerate(recs):
        k = r["kind"]
        key = ("blind", r["line_id"]) if k in ("blind", "blind_undo") else ("gas", r["line_id"]) if k == "gas" else ("purge", None)
        text, kind = "", "mute"
        if k == "blind":
            text, kind = "설치 완료", "ok"
        elif k == "blind_undo":
            text, kind = "미설치로 정정" + (f" — {r.get('note')}" if r.get("note") else ""), "warn"
        elif k == "gas":
            val = _num(r["value"])
            if is_gas_fail(r["value"]):
                text, kind = "측정 실패", "warn"
            elif _bad_num(r["value"]):
                text, kind = f"값 오류 ({r['value']})", "warn"
            else:
                text = f"LEL {val:g}%" if val is not None else str(r["value"])
                kind = "crit" if val is not None and val > lel_max else "ok"
        elif k == "purge_start":
            text, kind = "퍼지 시작", "info"
            run_at = r["ts"] if not r["future"] else run_at
        elif k == "purge_end":
            text = f"{_mins(run_at, r['ts']):g}분" if run_at and not r["future"] else "퍼지 종료"
            kind = "info"
            run_at = None
        elif k == "purge":
            val = _num(r["value"])
            text, kind = (f"기록 오류 ({r['value']})", "warn") if _bad_num(r["value"]) else ((f"{val:g}분" if val is not None else str(r["value"])), "info")
        state = "future" if r["future"] else ("cur" if latest.get(key) == i else "old")
        valid = None
        if k == "gas" and state == "cur" and r["ts"] and not is_gas_fail(r["value"]):     # 측정 실패 기록에는 유효 · 만료를 붙이지 않는다
            valid = "유효" if _mins(r["ts"], now) <= valid_min else "만료"
        out.append({"t": r["ts"].strftime("%H:%M") if r["ts"] else "", "day": r["ts"].strftime("%m-%d") if r["ts"] else "",
                    "kind": k, "label": HIST_LABEL.get(k, k),
                    "text": text, "tone": kind, "line_id": r["line_id"] or "", "by": r["by"], "src": r["src"],
                    "state": state, "valid": valid, "group": key[0]})
    out.reverse()          # 최근 순 — 시각 없는 기재값(처음 상태)이 맨 아래
    return out


def with_steps(ptw: dict, rows: list[dict] | None) -> tuple[dict, list[dict] | None, dict]:
    """
    문서 자동화 작업허가서 점검이 읽을 값 — 허가서 원본에 관제 격리 화면의 현재 상태(단계 입력 포함)를 얹은 사본.
    원본 파일은 고치지 않는다. 측정은 지점마다 마지막 값(유효시간이 지났으면 expired 표시), 퍼지는 지금까지의 분.
    """
    import copy
    from .common import system_now
    try:
        before = system_now() < datetime.fromisoformat(ptw["start"])
    except (KeyError, ValueError):
        before = False
    if before:
        # 10/8 — 작업일이 아직 안 온 허가서(예: 시나리오 날짜 10/12 허가서를 그 전에 점검)는 허가서에 적힌 그대로 본다.
        # 예전에는 '지금보다 뒤의 기록은 아직 없다'는 규칙 때문에 허가서에 적힌 가스 측정까지 빠져 '가스 측정 누락'으로 나왔다.
        return copy.deepcopy(ptw), copy.deepcopy(rows), {"steps": 0, "expired": [], "purge_state": "", "before_start": True}
    v = view(ptw, with_simops=False)
    p, rs = copy.deepcopy(ptw), copy.deepcopy(rows)
    by_line = {ln["line_id"]: ln for ln in v["check"]["lines"]}
    for r in rs or []:
        ln = by_line.get(r.get("line_id"))
        if ln is None:
            continue
        if ln["blind"] == "done":
            r["맹판설치"] = "O"
            if not r.get("격리방법"):
                r["격리방법"] = "맹판"
        elif ln.get("blind_undone"):
            r["맹판설치"] = ""
    keep = [g for g in ptw.get("gas_tests") or [] if not g.get("line_id")]      # 지점 없는 측정(화기 위치 등)은 그대로
    p["gas_tests"] = keep + [{"time": m["time"], "point": m["point"], "line_id": m["line_id"], "lel_pct": m["lel"],
                              **({} if m["valid"] else {"expired": True})}
                             for m in v["meas"] if m["measured"] and not m.get("bad") and not m.get("fail")]
    if v["purge_min"] is not None:
        p["purge"] = {**(ptw.get("purge") or {}), "minutes": v["purge_min"]}
    info = {"steps": len(v["steps"]), "expired": [m["line_id"] for m in v["meas"] if m["measured"] and not m["valid"]],
            "purge_state": v["purge"]["state"]}
    return p, rs, info


def _is_open(ptw: dict, now: datetime | None = None) -> bool:
    from .common import system_now
    now = now or system_now()
    try:
        return datetime.fromisoformat(ptw["start"]) <= now <= datetime.fromisoformat(ptw["end"])
    except (KeyError, ValueError):
        return False
