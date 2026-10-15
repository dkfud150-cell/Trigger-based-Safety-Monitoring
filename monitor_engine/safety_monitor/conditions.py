"""
조건어 평가기 — 패키지의 규칙(rules.json)에 적힌 조건을 현장 상태에 비춰 참/거짓을 낸다.

회사는 아래 조건어만 조합해서 규칙을 쓴다. 조건어는 특정 공정 · 시나리오를 모른다.
새 위험 유형이 와도 조건어를 조합해 판정표를 쓰면 되고, 엔진은 바뀌지 않는다.

  묶기     all · any · not · cond(이름 붙인 조건) · var(규칙 값)
  상태     fact(켜진 상태) · duration(켜져 있던 시간) · event(일어난 일) · document(입력된 문서)
  측정     measured(유효한 측정이 있나) · measure(최근 측정값 비교) · covers(모든 지점을 쟀나)
  대상     unmarked(표시 안 된 대상이 있나 — 맹판 미설치 배관 등)
  영상     detect(불꽃 등 검출 확정) · persons(폴리곤 안 인원) · video(영상이 도는 중인가)
  구역     zone_in · zone_attr(구역 속성)
  판정표   axis(같은 판정표 안의 축 상태)

값에 '@이름' 을 쓰면 rules.json 의 vars 값을 가리킨다.
어떤 조건이든 "label" 을 달면, 거짓일 때 화면 · 로그에 그 이름으로 이유가 남는다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# 조건어 → 같이 쓸 수 있는 키 (검사기 validate 가 쓴다)
PREDICATES: dict[str, set[str]] = {
    "all": set(), "any": set(), "not": set(), "cond": set(), "var": {"is"},
    "fact": {"zones", "for_min", "any_zone"},
    "event": {"attr", "within_min"},
    "measured": {"max_age_min", "max", "min", "invalidated_by", "after"},
    "exceeds": {"max", "max_age_min", "invalidated_by"},
    "measure": {"op", "value", "max_age_min"},
    "duration": {"op", "value"},
    "covers": set(), "unmarked": set(), "document": set(),
    "detect": {"hold_min"},
    "persons": {"op", "value"},
    "video": set(),
    "zone_in": set(),
    "zone_attr": {"in", "is"},
    "axis": {"is", "in"},
}
OPS = {">=": lambda a, b: a >= b, ">": lambda a, b: a > b, "<=": lambda a, b: a <= b,
       "<": lambda a, b: a < b, "==": lambda a, b: a == b, "!=": lambda a, b: a != b}


class ConditionError(ValueError):
    pass


@dataclass
class R:
    ok: bool
    ev: list[str] = field(default_factory=list)        # 참일 때 근거
    why_not: list[str] = field(default_factory=list)   # 거짓일 때 이유


class Ctx:
    """조건 하나를 평가할 때의 맥락 — 어느 구역, 몇 시, 영상이 도는지, 같은 판정표의 축 상태."""

    def __init__(self, eng, zone: str, now: datetime, axes: dict | None = None, raised_at: datetime | None = None):
        self.eng = eng
        self.store = eng.store
        self.rules = eng.rules
        self.site = eng.site
        self.zone = zone
        self.now = now
        self.axes = axes or {}
        self.raised_at = raised_at
        self._depth = 0

    @property
    def video(self) -> bool:
        return self.eng.video_on

    def var(self, name: str):
        vs = self.rules.get("vars", {})
        if name not in vs:
            raise ConditionError(f"vars 에 없는 값: @{name}")
        return vs[name]

    def val(self, v):
        if isinstance(v, str) and v.startswith("@"):
            return self.var(v[1:])
        return v

    def as_list(self, v) -> list:
        v = self.val(v)
        if v is None:
            return []
        return list(v) if isinstance(v, (list, tuple, set)) else [v]


# ---------------------------------------------------------------------- 평가
def evaluate(p, c: Ctx) -> R:
    if p is True or p is False:
        return R(bool(p))
    if not isinstance(p, dict):
        raise ConditionError(f"조건은 true/false 또는 {{조건어: ...}} 여야 합니다: {p!r}")
    keys = [k for k in p if k in PREDICATES]
    if len(keys) != 1:
        raise ConditionError(f"조건어가 정확히 하나여야 합니다: {sorted(k for k in p if not k.startswith('_'))}")
    r = HANDLERS[keys[0]](p, c)
    label = p.get("label")
    if not r.ok and label:
        r = R(False, [], [label + (f" — {'; '.join(r.why_not)}" if r.why_not else "")])
    return r


def _all(p, c):
    rs = [evaluate(x, c) for x in p["all"]]
    ok = all(r.ok for r in rs)
    return R(ok, [e for r in rs for e in r.ev] if ok else [], [w for r in rs if not r.ok for w in r.why_not])


def _any(p, c):
    rs = [evaluate(x, c) for x in p["any"]]
    ok = any(r.ok for r in rs)
    return R(ok, [e for r in rs if r.ok for e in r.ev], [] if ok else [w for r in rs for w in r.why_not])


def _not(p, c):
    r = evaluate(p["not"], c)
    return R(not r.ok, [], r.ev if r.ok else [])


def _cond(p, c):
    name = p["cond"]
    conds = c.rules.get("conditions", {})
    if name not in conds:
        raise ConditionError(f"conditions 에 없는 조건: {name}")
    c._depth += 1
    if c._depth > 20:
        raise ConditionError(f"조건이 자기 자신을 부릅니다: {name}")
    try:
        return evaluate(conds[name], c)
    finally:
        c._depth -= 1


def _var(p, c):
    v = c.var(p["var"])
    return R(v == p["is"]) if "is" in p else R(bool(v))


def _fact(p, c):
    name = p["fact"]
    if "zones" in p and c.zone not in c.as_list(p["zones"]):
        return R(False)
    zones = [z for (f, z) in c.store.on if f == name] if p.get("any_zone") else [c.zone]
    for z in zones:
        rec = c.store.on.get((name, z))
        if rec and rec.ts <= c.now:
            if "for_min" in p and (c.now - rec.ts) < timedelta(minutes=float(c.val(p["for_min"]))):
                continue
            return R(True, [f"{rec.ts:%H:%M} {rec.label}"])
    return R(False)


def _match_attrs(attrs: dict, want: dict, c: Ctx) -> bool:
    for k, v in want.items():
        allowed = c.as_list(v)
        if attrs.get(k) not in allowed:
            return False
    return True


def _event(p, c):
    name = p["event"]
    want = p.get("attr", {})
    hits = [e for e in c.store.events
            if e.fact == name and e.zone == c.zone and e.ts <= c.now
            and (e.cleared_at is None or e.cleared_at > c.now)
            and _match_attrs(e.attrs, want, c)]
    if "within_min" in p:
        lim = timedelta(minutes=float(c.val(p["within_min"])))
        hits = [e for e in hits if c.now - e.ts <= lim]
    if not hits:
        return R(False)
    e = max(hits, key=lambda x: x.ts)
    return R(True, [f"{e.ts:%H:%M} {e.label}" + (f" {e.target}" if e.target else "")])


def _latest_by_target(name: str, c: Ctx) -> dict:
    """
    측정 지점(target)마다 판정 시각까지 들어온 가장 늦은 측정 시각 (10/13 K05).
    순서는 신호가 들어온 순서가 아니라 측정 시각(ts)으로 정한다 — 나중에 거꾸로 적어 넣은 측정도 제 시각에 선다.
    지점 없는 측정(target 없음)은 넣지 않는다 — 처리 기준이 정해지지 않아 예전 동작 그대로 둔다.
    """
    out: dict = {}
    for m in c.store.measures:
        if m.fact == name and m.zone == c.zone and m.target is not None and m.ts <= c.now:
            if m.target not in out or m.ts > out[m.target]:
                out[m.target] = m.ts
    return out


def _valid_measures(name: str, c: Ctx, max_age=None, invalid=None, vmax=None, vmin=None, after_raise=False, reasons: dict | None = None):
    """reasons 를 주면 지점(target)마다 현재값이 빠진 이유를 짧게 적어 준다 — 전 지점 줄(covers)의 근거 문구용 (STEP 02-8). 판정에는 쓰지 않는다."""
    out, why = [], []
    reasons = {} if reasons is None else reasons
    inv = c.as_list(invalid) if invalid is not None else []
    latest = _latest_by_target(name, c)
    hi = float(c.val(vmax)) if vmax is not None else None
    lo = float(c.val(vmin)) if vmin is not None else None

    def out_of_range(v: float) -> bool:
        return not math.isfinite(v) or (hi is not None and v > hi) or (lo is not None and v < lo)    # 유한하지 않은 값(nan · ±inf)은 늘 기준 밖

    # 같은 지점 · 같은 시각에 기준 안 값과 기준 밖 값이 같이 있으면 기준 밖 값으로 본다 (10/13 K05 잔여 A)
    # — 실제로 잰 기준 초과값이 같은 시각의 적합값에 가려지지 않게. 입력 순서와 상관없다.
    tie_bad = {m.target for m in c.store.measures
               if m.fact == name and m.zone == c.zone and m.target is not None
               and m.ts == latest.get(m.target) and out_of_range(m.value) and not m.fault}
    # 같은 지점 · 같은 시각에 이상 · 실패 기록이 있으면 그 시각 값은 현재값으로 쓰지 않는다 — 실패를 기준 초과로 보지는 않는다 (STEP 02-10 B-3)
    tie_fault = {m.target: m.fault for m in c.store.measures
                 if m.fact == name and m.zone == c.zone and m.target is not None
                 and m.ts == latest.get(m.target) and m.fault}
    for m in c.store.measures:
        if m.fact != name or m.zone != c.zone or m.ts > c.now:
            continue
        # 같은 지점에 더 나중 측정이 있으면 이 값은 현재값이 아니다 — 최신값이 기준 초과 · 만료 · 무효여도
        # 옛 적합값으로 돌아가 해제를 인정하지 않는다 (10/13 K05).
        if m.target is not None and m.ts < latest[m.target]:
            continue
        if m.fault:                        # 이상 · 실패 기록 (STEP 02-10 A-3 · B-3) — 숫자로 쓰지 않는다. 지점이 있으면 이 지점의 현재값이 없다
            # 보완: 실패 전 마지막 유효값을 근거에 같이 적는다 — '측정값 없음'과 '위험 해소'를 구분 (판정은 그대로, 문구만)
            prev = _prev_valid(c, name, m) if m.target is not None else None
            tail = ""
            if prev is not None:
                over = hi is not None and prev.value > hi
                tail = f" · 실패 전 유효값 {prev.value:g}" + (f" > {c.val(vmax)} — 위험 미해제" if over else " — 현재값으로 쓰지 않음")
            why.append(f"{m.ts:%H:%M}" + (f" {m.target}" if m.target else "") + f" {m.fault} 기록 ({m.raw})" + tail)
            reasons[m.target] = m.fault + (f" (실패 전 {prev.value:g} > {c.val(vmax)} · 위험 미해제)" if prev is not None and hi is not None and prev.value > hi else "")
            continue
        if not math.isfinite(m.value):
            why.append(f"{m.ts:%H:%M} 측정값이 유한한 숫자가 아님")
            reasons[m.target] = "값 오류"
            continue
        if m.target in tie_fault:
            why.append(f"{m.ts:%H:%M} {m.target} 같은 시각 {tie_fault[m.target]} 기록 — 이 시각 값은 현재값으로 쓰지 않음")
            reasons[m.target] = f"같은 시각 {tie_fault[m.target]} 기록"
            continue
        if m.target in tie_bad and not out_of_range(m.value):
            why.append(f"{m.ts:%H:%M} {m.target} 같은 시각 측정이 상충 — 기준 밖 값으로 판정")
            reasons[m.target] = "같은 시각 측정 상충"
            continue
        if max_age is not None and c.now - m.ts > timedelta(minutes=float(c.val(max_age))):
            why.append(f"{m.ts:%H:%M} 측정 만료")
            reasons.setdefault(m.target, "측정 만료")
            continue
        killer = next((e for e in c.store.events if e.fact in inv and e.zone == c.zone and m.ts < e.ts <= c.now), None)
        if killer:
            why.append(f"{m.ts:%H:%M} 측정은 {killer.ts:%H:%M} {killer.label} 이전이라 무효")
            reasons.setdefault(m.target, f"{killer.label} 이전 측정이라 무효")
            continue
        if vmax is not None and m.value > float(c.val(vmax)):
            why.append(f"{m.ts:%H:%M} 측정 {m.value:g} > {c.val(vmax)}")
            reasons[m.target] = f"기준 초과 {m.value:g} > {c.val(vmax)}"
            continue
        if vmin is not None and m.value < float(c.val(vmin)):
            why.append(f"{m.ts:%H:%M} 측정 {m.value:g} < {c.val(vmin)}")
            reasons[m.target] = f"기준 미만 {m.value:g} < {c.val(vmin)}"
            continue
        if after_raise and (c.raised_at is None or m.ts <= c.raised_at):
            continue
        out.append(m)
    return out, why


def _prev_valid(c: Ctx, name: str, f):
    """이상 · 실패 기록 f 보다 앞선, 같은 측정 · 지점의 마지막 유효값 (STEP 02-10 보완) — 근거 문구용."""
    prev = None
    for m in c.store.measures:
        if (m.fact == name and m.zone == c.zone and m.target == f.target and m.ts <= f.ts and not m.fault
                and math.isfinite(m.value) and m is not f and (prev is None or m.ts >= prev.ts)):
            prev = m
    return prev


def invalid_latest(c: Ctx) -> list:
    """
    이 구역에서 측정(fact) · 지점(target)마다 판정 시각까지의 가장 늦은 기록이 이상 · 실패 기록인 것 (STEP 02-10 A-3 · B-3).
    LEL 센서처럼 지점이 없는 측정도 같은 측정끼리 묶어 본다. 같은 시각이면 이상 · 실패 기록을 앞세운다.
    판정에는 쓰지 않는다 — 화면 · API · 기록의 '센서 이상 · 측정 실패' 상태 표시용.
    """
    last: dict = {}
    for m in c.store.measures:
        if m.zone != c.zone or m.ts > c.now:
            continue
        k = (m.fact, m.target)
        if k not in last or m.ts > last[k].ts or (m.ts == last[k].ts and m.fault):
            last[k] = m
    return [m for m in last.values() if m.fault]


def fault_states(c: Ctx) -> list[dict]:
    """
    invalid_latest 를 화면 · API 에 넘길 모양으로 — 이상 · 실패가 언제 시작됐는지(이어진 이상 기록의 첫 시각),
    그 전의 마지막 유효값(값 · 시각)과 그 값이 지금 판정에 쓰이는지.
      지점 없는 측정(LEL 센서 등): 직전 유효값이 판정에 그대로 쓰인다 (A-3 — 위험값으로 바꾸지 않고, 내려가지도 않는다)
      지점 있는 측정(가스 측정 FG-01 등): 직전 유효값을 현재값으로 쓰지 않는다 (B-3 — 그 지점은 측정 없음)
    """
    out = []
    for f in invalid_latest(c):
        same = sorted((m for m in c.store.measures if m.fact == f.fact and m.zone == c.zone and m.target == f.target and m.ts <= c.now),
                      key=lambda m: (m.ts, bool(m.fault)))
        since, prev = f.ts, None
        for m in reversed(same):
            if m.fault:
                since = m.ts
            elif math.isfinite(m.value):
                prev = m
                break
        out.append({"fact": f.fact, "label": f.label, "target": f.target, "fault": f.fault, "raw": f.raw,
                    "ts": f.ts, "since": since, "count": sum(1 for m in same if m.fault and m.ts >= since),
                    "minutes": round((c.now - since).total_seconds() / 60, 1),          # 이상 · 실패가 이어진 시간 (보완 — 기한은 정하지 않음)
                    "last_valid": ({"value": prev.value, "ts": prev.ts} if prev else None),
                    "last_valid_used": prev is not None and f.target is None})
    return out


def _measured(p, c):
    ms, why = _valid_measures(p["measured"], c, p.get("max_age_min"), p.get("invalidated_by"),
                              p.get("max"), p.get("min"), p.get("after") == "raise")
    if not ms:
        return R(False, [], why[-1:] or ["측정 기록 없음"])
    m = max(ms, key=lambda x: x.ts)
    return R(True, [f"{m.ts:%H:%M} {m.label}" + (f" {m.target}" if m.target else "") + f" {m.value:g}"])


def _exceeds(p, c):
    """
    지금 유효한 측정 가운데 기준(max)을 넘는 값이 하나라도 있나 (STEP 03-3 P01 개정 V3-M).
    '지금 유효한 측정'은 해제 조건과 같은 기준(_valid_measures)으로 고른다 — 지점마다 최신값 · 유효시간 안 · 무효화 사건 전 ·
    측정 실패 · 값 오류 제외. 다른 지점의 적합값이 이 지점의 초과값을 가리지 않게 지점을 합치지 않고 하나씩 본다.
    """
    ms, _ = _valid_measures(p["exceeds"], c, p.get("max_age_min"), p.get("invalidated_by"))
    hi = float(c.val(p["max"]))
    over = [m for m in ms if m.value > hi]
    if not over:
        return R(False)
    m = max(over, key=lambda x: (x.value, x.ts))
    return R(True, [f"{m.ts:%H:%M} {m.label}" + (f" {m.target}" if m.target else "") + f" {m.value:g} > {c.val(p['max'])}"])


# ---------------------------------------------------------------------- 세부 원인 (STEP 03-3 보완)
CAUSE_LABELS = {
    "NO_RECORD": "측정 기록 없음", "EXPIRED": "측정 만료", "INVALIDATED": "측정 무효", "FAILED": "명시적 측정 실패",
    "VALUE_ERROR": "측정값 오류", "EXCEEDED": "기준 초과 측정", "R4_POINT": "R4 필수 지점 미충족",
}


def _change_ids(c: Ctx, var: str) -> list[str]:
    """그 vars 값을 바꾸는 개정안 중 지금 규칙셋에 적용된 것 (예: all_points_required → ['R4'])."""
    applied = set(c.rules.get("_applied") or [])
    out = []
    for cid, ch in (c.rules.get("rule_changes") or {}).items():
        if cid.startswith("_") or cid not in applied:
            continue
        keys = list((ch.get("set") or {}).keys()) + list((ch.get("add") or {}).keys())
        if f"vars.{var}" in keys:
            out.append(cid)
    return out


def _rule_text(c: Ctx, var: str, val) -> str:
    ids = _change_ids(c, var)
    return f"{var} = {val}" + (f" ({', '.join(ids)})" if ids else " (기본 규칙)")


def _record_state(name: str, c: Ctx, max_age, invalid) -> list[dict]:
    """
    판정 시각의 '현재 기록'마다 상태 — 지점 있는 측정은 지점마다 가장 늦은 시각의 기록, 지점 없는 측정은 그 시각까지의 기록 전부.
    현재 기록을 고르는 기준은 _valid_measures 와 같다(_latest_by_target 재사용). 판정에는 쓰지 않고 원인 설명에만 쓴다.
    """
    latest = _latest_by_target(name, c)
    inv = c.as_list(invalid) if invalid is not None else []
    out = []
    for m in c.store.measures:
        if m.fact != name or m.zone != c.zone or m.ts > c.now:
            continue
        if m.target is not None and m.ts < latest[m.target]:
            continue
        st = {"m": m, "state": "VALID", "event": None}
        if m.fault:
            st["state"] = "FAILED"
        elif not math.isfinite(m.value):
            st["state"] = "VALUE_ERROR"
        elif max_age is not None and c.now - m.ts > timedelta(minutes=float(c.val(max_age))):
            st["state"] = "EXPIRED"
        else:
            killer = next((e for e in c.store.events if e.fact in inv and e.zone == c.zone and m.ts < e.ts <= c.now), None)
            if killer:
                st["state"], st["event"] = "INVALIDATED", killer
        out.append(st)
    # 같은 지점 · 같은 시각에 실패 기록이 있으면 그 시각 값은 현재값이 아니다 (_valid_measures tie_fault 와 같은 처리)
    fail_t = {s["m"].target for s in out if s["state"] == "FAILED" and s["m"].target is not None}
    for s in out:
        if s["state"] == "VALID" and s["m"].target in fail_t:
            s["state"] = "FAILED"
    return out


def _cause(code: str, c: Ctx, rec=None, *, limit=None, rule="", detail="", **extra) -> dict:
    m = rec["m"] if rec else None
    d = {"code": code, "label": CAUSE_LABELS[code], "point": (m.target if m else extra.pop("point", None)),
         "value": (None if m is None or m.fault or not math.isfinite(m.value) else m.value),
         "raw": (m.raw if m is not None and (m.fault or not math.isfinite(m.value)) else None),
         "limit": limit, "unit": "%", "ts": (m.ts.isoformat(timespec="seconds") if m else None),
         "measure": (m.label if m else None), "rule": rule, "detail": detail, "source": "판정 시점 측정 기록"}
    d.update(extra)
    return d


def _state_cause(code: str, s: dict, c: Ctx, limit, max_age, invalid) -> dict:
    m = s["m"]
    where = f"{m.target} " if m.target else ""
    if code == "FAILED":
        return _cause("FAILED", c, s, limit=limit, rule="gas_valid (측정 실패 기록은 측정값으로 쓰지 않음)",
                      detail=f"{where}{m.ts:%H:%M} {m.fault or '측정 실패'} 기록 (입력 {m.raw})")
    if code == "VALUE_ERROR":
        return _cause("VALUE_ERROR", c, s, limit=limit, rule="gas_valid (유한한 숫자만 측정값)",
                      detail=f"{where}{m.ts:%H:%M} 측정값이 유한한 숫자가 아님")
    if code == "EXPIRED":
        mins = float(c.val(max_age))
        return _cause("EXPIRED", c, s, limit=limit, rule=_rule_text(c, "gas_valid_min", f"{mins:g}분"),
                      detail=f"{where}{m.ts:%H:%M} 측정 {m.value:g}% — 유효시간 {mins:g}분 지남", valid_min=mins)
    if code == "INVALIDATED":
        e = s["event"]
        return _cause("INVALIDATED", c, s, limit=limit, rule=_rule_text(c, "measure_invalidated_by", ", ".join(c.as_list(invalid))),
                      detail=f"{where}{m.ts:%H:%M} 측정 {m.value:g}% — {e.ts:%H:%M} {e.label} 이전 측정이라 무효",
                      event={"fact": e.fact, "label": e.label, "ts": e.ts.isoformat(timespec="seconds")})
    raise ValueError(code)


def measure_causes(spec: dict, c: Ctx) -> list[dict]:
    """
    측정 조건 줄(P01 4행)이 맞았을 때 그 판정 시각의 실제 기록으로 세부 원인을 만든다 (STEP 03-3 보완). 판정은 바꾸지 않는다.
    세 갈래를 판정식과 같은 함수로 다시 본다 — 참인 갈래의 원인만 낸다. 여러 원인이 함께 나올 수 있다.
      ① 유효한 측정 없음  _valid_measures(유효시간 · 무효화)  → 측정 기록 없음 / 만료 / 무효 / 명시적 실패 / 값 오류
      ② 기준 초과        _valid_measures 중 max 초과(_exceeds 와 같음) → 기준 초과 측정 (지점마다)
      ③ 전 지점 요구      points_when 이 참일 때 _valid_measures(max 포함, covers 와 같음)로 못 채운 지점 → R4 필수 지점 미충족
    spec: {"measure", "max", "max_age_min", "invalidated_by", "points_when", "points"} — rules.json 판정 줄의 "causes"
    """
    name, mx = spec["measure"], spec.get("max")
    age, inv = spec.get("max_age_min"), spec.get("invalidated_by")
    hi = float(c.val(mx)) if mx is not None else None
    lim = c.val(mx) if mx is not None else None
    states = _record_state(name, c, age, inv)
    valid, _ = _valid_measures(name, c, age, inv)
    out: list[dict] = []
    # ① 유효한 측정 없음
    if not valid:
        if not states:
            out.append(_cause("NO_RECORD", c, limit=lim, rule="gas_valid",
                              detail=f"판정 시각({c.now:%H:%M})까지 이 구역의 {spec.get('label', name)} 기록 없음", branch="유효 측정 없음"))
        for s in states:
            if s["state"] != "VALID":
                out.append({**_state_cause(s["state"], s, c, lim, age, inv), "branch": "유효 측정 없음"})
    # ② 기준 초과 — 지점을 합치지 않는다
    if hi is not None:
        for m in sorted((m for m in valid if m.value > hi), key=lambda x: (x.target or "", x.ts)):
            out.append(_cause("EXCEEDED", c, {"m": m}, limit=lim, rule=_rule_text(c, "lel_clear_max", f"{lim}%"),
                              detail=f"{m.target + ' ' if m.target else ''}{m.ts:%H:%M} 측정 {m.value:g}% > 기준 {lim}%", branch="기준 초과"))
    # ③ 전 지점 요구
    if spec.get("points") is not None and evaluate(spec.get("points_when", True), c).ok:
        need = points(spec["points"], c)
        ok_ms, _ = _valid_measures(name, c, age, inv, mx)
        got = {m.target for m in ok_ms if m.target}
        by_pt = {s["m"].target: s for s in states if s["m"].target is not None}
        for pt in need:
            if pt in got:
                continue
            s = by_pt.get(pt)
            if s is None:
                sub, why = "NO_RECORD", "미측정"
            elif s["state"] != "VALID":
                sub = s["state"]
                why = CAUSE_LABELS[sub] + " — " + _state_cause(sub, s, c, lim, age, inv)["detail"]
            elif hi is not None and s["m"].value > hi:
                sub, why = "EXCEEDED", f"기준 초과 {s['m'].value:g}% > {lim}%"
            else:
                sub, why = "CONFLICT", "같은 시각 측정 상충 — 기준 밖 값으로 판정"
            out.append(_cause("R4_POINT", c, s, limit=lim, rule=_rule_text(c, "all_points_required", "true"),
                              detail=f"필수 지점 {pt} — {why}", point=pt, sub_code=sub, sub_label=why,
                              required_points=need, branch="전 지점 요구"))
    return out


def _measure(p, c):
    ms, _ = _valid_measures(p["measure"], c, p.get("max_age_min"))
    if not ms:
        return R(False)
    m = max(ms, key=lambda x: x.ts)
    op = p.get("op", ">=")
    ok = OPS[op](m.value, float(c.val(p["value"])))
    return R(ok, [f"{m.ts:%H:%M} {m.label} {m.value:g}"] if ok else [])


def _duration(p, c):
    name = p["duration"]
    iv = c.store.intervals.get((name, c.zone), [])
    if not iv:
        return R(False, [], [f"{c.store.labels.get(name, name)} 기록 없음"])
    start, end = iv[-1]
    mins = ((end or c.now) - start).total_seconds() / 60
    op, val = p.get("op", ">="), float(c.val(p["value"]))
    ok = OPS[op](mins, val)
    return R(ok, [f"{c.store.labels.get(name, name)} {mins:.0f}분"] if ok else [], [] if ok else [f"{mins:.0f}분 (기준 {op} {val:g}분)"])


def points(spec, c: Ctx) -> list[str]:
    """대상 목록 — site.json 참조 목록이나 입력된 문서에서 뽑는다. 여러 개면 합친다."""
    specs = spec if isinstance(spec, list) else [spec]
    out: list[str] = []
    for s in specs:
        if "if" in s and not evaluate(s["if"], c).ok:
            continue
        if "ref" in s:
            items = c.site.get("references", {}).get(s["ref"], {}).get(c.zone, [])
            if s.get("where"):
                items = [i for i in items if i.get(s["where"])]
            out += [str(i[s.get("field", "id")]) for i in items]
        elif "document" in s:
            doc = c.store.documents.get((s["document"], c.zone))
            if doc:
                out += [r.get(s["field"], "") for r in doc["rows"] if r.get(s["field"])]
    return list(dict.fromkeys(out))


def _covers(p, c):
    s = p["covers"]
    need = points(s["points"], c)
    why_pt: dict = {}
    ms, _ = _valid_measures(s["measure"], c, s.get("max_age_min"), s.get("invalidated_by"), s.get("max"), reasons=why_pt)
    got = {m.target for m in ms if m.target}
    miss = [x for x in need if x not in got]
    # 빠진 지점마다 이유를 적는다 — 기준 초과 · 만료 · 값 오류를 '미측정'으로 뭉뚱그리지 않는다 (STEP 02-8, 판정은 그대로)
    return R(not miss, [f"{', '.join(need)} 측정"] if not miss else [],
             ["; ".join(f"{x} {why_pt.get(x, '미측정')}" for x in miss)] if miss else [])


def _unmarked(p, c):
    s = p["unmarked"]
    need = points(s["points"], c)
    marked = c.store.marks.get(s["mark"], {})
    left = [x for x in need if x not in marked]
    lab = c.store.labels.get(s["mark"], s["mark"])
    return R(bool(left), [f"{lab} 없음: {', '.join(left)}"] if left else [])


def _document(p, c):
    d = c.store.documents.get((p["document"], c.zone))
    return R(bool(d), [f"{d['ts']:%H:%M} {d['label']}"] if d else [])


def _detect(p, c):
    d = c.store.detections.get((p["detect"], c.zone))
    if not d:
        return R(False)
    if d["on"]:
        return R(True, [f"{d['since']:%H:%M:%S} 영상 {p['detect']}"])
    if "hold_min" in p and d.get("last") and c.now - d["last"] <= timedelta(minutes=float(c.val(p["hold_min"]))):
        return R(True, [f"{d['last']:%H:%M:%S} 영상 {p['detect']} (유지)"])
    return R(False)


def _persons(p, c):
    if not c.video:
        return R(False)
    n = count_people(c.store, c.zone, p["persons"])
    ok = OPS[p.get("op", ">=")](n, float(c.val(p.get("value", 1))))
    return R(ok, [f"사람 {n}명"] if ok else [])


def count_people(store, zone: str, types) -> int:
    """구역 안 사람 수. types = 'all' 또는 폴리곤 종류(들). 한 사람이 두 폴리곤에 걸쳐도 한 번만 센다."""
    people = store.people.get(zone, [])
    if types == "all":
        return len(people)
    want = set(types if isinstance(types, list) else [types])
    return sum(1 for s in people if s & want)


def _video(p, c):
    return R(c.video == bool(p["video"]))


def _zone_in(p, c):
    return R(c.zone in c.as_list(p["zone_in"]))


def _zone_attr(p, c):
    v = c.site.get("zones", {}).get(c.zone, {}).get(p["zone_attr"])
    if "is" in p:
        return R(v == c.val(p["is"]))
    ok = v in c.as_list(p.get("in", []))
    return R(ok, [], [] if ok else [f"{v or '-'} 미등록"])


def _axis(p, c):
    name = p["axis"]
    if name not in c.axes:
        raise ConditionError(f"축 '{name}' 은 이 판정표에서 아직 계산되지 않았습니다 (축 순서 확인)")
    a = c.axes[name]
    ok = a.state == p["is"] if "is" in p else a.state in p.get("in", [])
    return R(ok, ([f"{name} {a.state}" + (f"({', '.join(a.why)})" if a.why else "")] if ok else []))


HANDLERS = {
    "all": _all, "any": _any, "not": _not, "cond": _cond, "var": _var,
    "fact": _fact, "event": _event, "measured": _measured, "exceeds": _exceeds, "measure": _measure, "duration": _duration,
    "covers": _covers, "unmarked": _unmarked, "document": _document, "detect": _detect,
    "persons": _persons, "video": _video, "zone_in": _zone_in, "zone_attr": _zone_attr, "axis": _axis,
}
