"""
히트맵 · 통계 — 구역 · 부서 단위 통계다. 개인을 평가하지 않는다.
무음 기록도 세어서, 모드가 꺼진 구간에 무엇이 일어났는지 같이 본다.

  view()        히트맵 · 통계 화면(/api/stats) — 필터 · 직전 기간 비교 · 위험 집중 구역 · 구역 × 시간 · 작업 모드 효과 · PPE
  mode_intervals() · session_spans()  실시간 세션이 남긴 모드 켜짐 구간 · 관제가 돈 구간 (modes.jsonl · events.jsonl)
                부서 · 협력사로 묶는 대응표는 사업장 패키지 dashboard.json 의 departments.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from .common import detections, live_sessions, read_jsonl, zone_name, zones


def mode_intervals(now: datetime) -> list[tuple[str, str, datetime, datetime]]:
    """실시간 세션들이 남긴 모드 켜짐 구간 (구역, 모드, 시작, 끝)."""
    out = []
    for d in live_sessions():
        open_: dict[tuple, datetime] = {}
        last = None
        for r in read_jsonl(d / "modes.jsonl"):
            t = datetime.fromisoformat(r["ts"])
            last = t
            k = (r["zone"], r["mode"])
            if r["on"]:
                open_[k] = t
            elif k in open_:
                out.append((k[0], k[1], open_.pop(k), t))
        ev_last = max((datetime.fromisoformat(e["ts"]) for e in read_jsonl(d / "events.jsonl")), default=last)
        end = max(x for x in (last, ev_last) if x) if (last or ev_last) else None
        for k, t0 in open_.items():
            if end and end > t0:
                out.append((k[0], k[1], t0, end))
    return out


def session_spans() -> list[tuple[datetime, datetime]]:
    """세션마다 관제가 실제로 돈 구간 (시작 ~ 마지막 기록)."""
    out = []
    for d in live_sessions():
        meta = read_jsonl(d / "session.json")
        if not meta:
            continue
        t0 = datetime.fromisoformat(meta[0]["start"])
        ts = [datetime.fromisoformat(r["ts"]) for r in read_jsonl(d / "modes.jsonl")] + \
             [datetime.fromisoformat(e["ts"]) for e in read_jsonl(d / "events.jsonl")]
        if ts and max(ts) > t0:
            out.append((t0, max(ts)))
    return out


def ppe_items() -> list[dict]:
    """
    보호구 목록 (10/8) — detect.json ppe.items (안전모 · 안전조끼). has_model = 보호구 탐지가 켜져 있고 그 보호구의 가중치 파일이 있다.
    실시간 관제의 3축 신호판 아래 사람 칸(안전모 · 안전조끼 미착용 n명)과 같은 목록이다.
    """
    from .common import package
    from safety_monitor.package import ROOT as ENGINE_ROOT
    cfg = package().detect.get("ppe", {})
    out = []
    for key, it in (cfg.get("items") or {}).items():
        if key.startswith("_") or not isinstance(it, dict):
            continue
        w = Path(it.get("weights") or cfg.get("weights", "models/helmet.pt"))
        out.append({"key": key, "label": it.get("label", key),
                    "has_model": bool(cfg.get("enabled")) and (w if w.is_absolute() else ENGINE_ROOT / w).exists()})
    return out


def ppe_seconds(a: datetime, b: datetime) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    """
    기간(a, b] 에 시작한 실시간 세션에서 영상이 센 사람-초(구역별)와 보호구별 미착용 사람-초(보호구 → 구역).
    세션 파일(session.json)에 누적값이 한 줄씩 쌓이므로 마지막 줄이 그 세션의 합계다. 예전 세션은 안전모만 있다(no_helmet_seconds).
    """
    ps: dict[str, float] = {}
    off: dict[str, dict[str, float]] = {}
    for d in live_sessions():
        rows = read_jsonl(d / "session.json")
        start = next((r.get("start") for r in rows if r.get("start")), None)
        try:
            t0 = datetime.fromisoformat(start) if start else None
        except ValueError:
            t0 = None
        if t0 is None or not (a < t0 <= b):
            continue
        snaps = [m for m in rows if "person_seconds" in m]
        if not snaps:
            continue
        m = snaps[-1]
        for z, sec in (m.get("person_seconds") or {}).items():
            ps[z] = ps.get(z, 0.0) + sec
        items = m.get("ppe_off_seconds") or {"helmet": m.get("no_helmet_seconds") or {}}
        for k, zs in items.items():
            for z, sec in zs.items():
                off.setdefault(k, {})[z] = off.get(k, {}).get(z, 0.0) + sec
    return ps, off


# ---------------------------------------------------------------------- 10/6 화면 — 필터(기간 · 출처 · 구역) + 직전 같은 기간 비교
# 히트맵 · 통계 화면(web/api_control.py /api/stats)이 부른다.
# 원칙 — 오탐 표시는 뺀다 · 무음 기록도 센다 · 구역 · 부서 단위로만 묶는다(개인을 평가하지 않는다).
PERIOD_DAYS = {"today": 0, "7": 7, "14": 14, "90": 90}
BASIS = ("all", "alert", "shadow")


def _span(now: datetime, period: str) -> tuple[datetime, datetime, datetime]:
    """(이번 기간 시작, 끝, 직전 같은 길이 기간 시작). 오늘 = 그날 0시부터."""
    d = PERIOD_DAYS.get(str(period), 14)
    if d == 0:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now, start - timedelta(days=1)
    return now - timedelta(days=d), now, now - timedelta(days=2 * d)


def _keep(e: dict, src: str, zone: str) -> bool:
    if zone and zone != "전체" and e.get("zone") != zone:
        return False
    is_sample = e.get("_src", "샘플") == "샘플"
    return not ((src == "sample" and not is_sample) or (src == "live" and is_sample))


def _basis_ok(e: dict, basis: str) -> bool:
    if basis == "alert":
        return bool(e.get("alerted")) and e.get("level") in ("경보", "최고 경보")
    if basis == "shadow":
        return not e.get("alerted")
    return True


def _delta(cur: int, prev: int, has_prev: bool) -> dict:
    if not has_prev:
        return {"cur": cur, "prev": None, "diff": None, "pct": None}
    return {"cur": cur, "prev": prev, "diff": cur - prev, "pct": round((cur - prev) / prev * 100) if prev else None}


def sample_modes() -> dict:
    """예시 모드 켜짐 구간 (예시데이터_삭제가능/관제/sample_modes.json) — 예시를 끄거나 지우면 안 읽는다."""
    import json
    from safety_docs.config import use_sample_data
    from .common import sample_root
    p = sample_root() / "관제" / "sample_modes.json"
    if not use_sample_data() or not p.exists():
        return {"observed": [], "intervals": []}
    d = json.loads(p.read_text(encoding="utf-8"))
    iv = [(x["zone"], x["mode"], datetime.fromisoformat(x["start"]), datetime.fromisoformat(x["end"])) for x in d.get("intervals", [])]
    ob = [(datetime.fromisoformat(x["start"]), datetime.fromisoformat(x["end"])) for x in d.get("observed", [])]
    return {"observed": ob, "intervals": iv}


def _clip_hours(spans, a: datetime, b: datetime) -> float:
    return sum(max(0.0, (min(y, b) - max(x, a)).total_seconds()) for x, y in spans) / 3600


def view(events: list[dict], now: datetime, period: str = "14", src: str = "", zone: str = "",
         zbasis: str = "all", hbasis: str = "all") -> dict:
    """
    한 화면에 필요한 숫자 전부.
      kpis    전체 위반(오탐 제외) · 경보 이상 · 무음 기록 · 오탐 표시 — 직전 같은 기간 대비(그 기간에 기록이 없으면 비교 안 함)
      zones   위험 집중 구역 — 고른 기준(전체 · 경보 이상 · 무음 기록)의 건수가 많은 구역부터, 직전 기간 대비
      heat    구역 × 시간(0~23시) — 고른 기준
      modes   작업 모드 효과 — 평상시에도 무음으로 기록되는 위반 유형만, 시간당 위반(평상시 vs 모드가 켜졌을 때)
      ppe     보호구(안전모 · 안전조끼)마다 — 미착용 기록 건수(부서 · 협력사별, 직전 대비)와, 모델이 붙고 영상이 돈 시간이 있으면 착용률
    """
    from .common import dashboard, package
    a, b, pa = _span(now, period)
    det = [e for e in detections(events) if _keep(e, src, zone)]
    cur_all = [e for e in det if a < e["_ts"] <= b]
    prev_all = [e for e in det if pa < e["_ts"] <= a]
    cur = [e for e in cur_all if not e.get("false_positive")]
    prev = [e for e in prev_all if not e.get("false_positive")]
    has_prev = bool(prev_all)

    def n(evs, f=lambda e: True):
        return sum(1 for e in evs if f(e))
    kpis = {"total": _delta(len(cur), len(prev), has_prev),
            "alert": _delta(n(cur, lambda e: _basis_ok(e, "alert")), n(prev, lambda e: _basis_ok(e, "alert")), has_prev),
            "shadow": _delta(n(cur, lambda e: _basis_ok(e, "shadow")), n(prev, lambda e: _basis_ok(e, "shadow")), has_prev),
            "fp": _delta(n(cur_all, lambda e: e.get("false_positive")), n(prev_all, lambda e: e.get("false_positive")), has_prev)}

    # 위험 집중 구역
    zb = zbasis if zbasis in BASIS else "all"
    zc: dict[str, list[int]] = {}
    for e in cur:
        if _basis_ok(e, zb):
            zc.setdefault(e["zone"], [0, 0])[0] += 1
    for e in prev:
        if _basis_ok(e, zb) and e["zone"] in zc:
            zc[e["zone"]][1] += 1
    zrows = sorted(({"zone": z, "name": zone_name(z), "n": c, "prev": p if has_prev else None,
                     "diff": (c - p) if has_prev else None} for z, (c, p) in zc.items()), key=lambda r: (-r["n"], r["zone"]))

    # 구역 × 시간
    hb = hbasis if hbasis in BASIS else "all"
    grid: dict[str, list[int]] = {}
    for e in cur:
        if _basis_ok(e, hb):
            grid.setdefault(e["zone"], [0] * 24)[e["_ts"].hour] += 1
    hrows = [{"zone": z, "name": zone_name(z), "vals": grid[z]} for z in zones() if z in grid]

    # 작업 모드 효과 — 평상시에도 기록되는 유형(무음 기록이 있는 유형)만 같은 기준으로 비교
    comparable = {e.get("violation_type") for e in detections(events) if not e.get("alerted")}
    sm = sample_modes()
    ivs = [x for x in mode_intervals(now) + sm["intervals"]]
    observed = session_spans() + sm["observed"]
    mrows, excluded = [], sorted({e.get("violation_type") for e in cur if e.get("violation_type") not in comparable})
    for z in zones():
        if zone and zone != "전체" and z != zone:
            continue
        z_on = [(m, x, y) for zz, m, x, y in ivs if zz == z and m != "평상시"]
        if not z_on:
            continue
        on_h = _clip_hours([(x, y) for _, x, y in z_on], a, b)
        off_h = max(_clip_hours(observed, a, b) - on_h, 0.0)
        ze = [e for e in cur if e["zone"] == z and e.get("violation_type") in comparable]
        on_n = sum(1 for e in ze if (e.get("mode") or "평상시") != "평상시")
        off_n = len(ze) - on_n
        if not (on_h or off_h) or not (on_n or off_n):
            continue
        r_on = on_n / on_h if on_h else None
        r_off = off_n / off_h if off_h else None
        few = on_h < 1 or off_h < 1
        inc = None if few or not r_off or r_on is None else round((r_on - r_off) / r_off * 100)
        mrows.append({"zone": z, "name": zone_name(z), "modes": " · ".join(dict.fromkeys(m for m, _, _ in z_on)),
                      "types": " · ".join(sorted({e.get("violation_type") for e in ze})),
                      "on": {"n": on_n, "h": round(on_h, 1), "rate": r_on}, "off": {"n": off_n, "h": round(off_h, 1), "rate": r_off},
                      "inc": inc, "few": few})
    # PPE (10/8) — 보호구마다. 미착용 기록(실시간 관제의 구역 규칙 안전모 · 안전조끼 미착용)과 영상이 센 착용률
    deps = {k: v for k, v in dashboard().get("departments", {}).items() if not k.startswith("_")}

    def dep(z):
        return deps.get(z, f"{z} {zone_name(z)}")
    ps, offs = ppe_seconds(a, b)
    ppe = []
    for it in ppe_items():
        lab = it["label"]
        hit = [e for e in cur if lab in (e.get("violation_type") or "")]
        hit_prev = [e for e in prev if lab in (e.get("violation_type") or "")]
        by_dep: dict[str, int] = {}
        for e in hit:
            by_dep[dep(e["zone"])] = by_dep.get(dep(e["zone"]), 0) + 1
        dps: dict[str, float] = {}
        doff: dict[str, float] = {}
        for z, sec in ps.items():
            if zone and zone != "전체" and z != zone:
                continue
            dps[dep(z)] = dps.get(dep(z), 0.0) + sec
            doff[dep(z)] = doff.get(dep(z), 0.0) + offs.get(it["key"], {}).get(z, 0.0)
        rates = {d: max(0.0, 1 - doff.get(d, 0.0) / sec) for d, sec in dps.items() if sec > 0}
        tot = sum(dps.values())
        ppe.append({"key": it["key"], "label": lab, "has_model": it["has_model"], "n": len(hit),
                    "diff": (len(hit) - len(hit_prev)) if has_prev else None,
                    "by_dep": [{"dep": d, "n": c} for d, c in sorted(by_dep.items(), key=lambda x: -x[1])],
                    "rate": round((1 - sum(doff.values()) / tot) * 100, 1) if it["has_model"] and tot > 0 else None,
                    "seen_min": round(tot / 60, 1),
                    "rate_by_dep": [{"dep": d, "rate": round(r * 100, 1)} for d, r in sorted(rates.items())] if it["has_model"] else []})
    return {"period": {"start": a.isoformat(timespec="minutes"), "end": b.isoformat(timespec="minutes"),
                       "prev_start": pa.isoformat(timespec="minutes"), "has_prev": has_prev},
            "kpis": kpis, "zones": zrows, "zbasis": zb,
            "heat": {"rows": hrows, "n": sum(sum(r["vals"]) for r in hrows), "basis": hb},
            "modes": {"rows": mrows, "excluded": [x for x in excluded if x], "sample": bool(sm["intervals"])},
            "ppe": ppe}
