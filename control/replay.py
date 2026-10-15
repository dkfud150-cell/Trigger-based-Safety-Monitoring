"""
재생 비교 — 시나리오는 시스템이 제대로 도는지 확인하는 도구다.

타임라인 CSV 를 규칙셋(variants)마다 엔진에 넣어 돌리고(monitor_engine runner.run_timeline),
결과를 시나리오에 적어 둔 기대 결과(expect)와 맞춰 본다. 규칙셋을 바꿨을 때 앞뒤를 나란히 본다.
기록은 control/records/replay/<시나리오>/<variant>/ 에 남지만 관제 기록(이벤트 로그 · 통계 · 피드백)에는 넣지 않는다.
결과를 문서 자동화로 넘기는 것은 사람이 고를 때만 한다. 넘긴 내역과 그것으로 만든 문서에는 '재생 비교 검증본' 표시가 붙고
위험성평가 집계 · 의무 이행 · 기록(보존)에는 들어가지 않는다 (docgen config.load_events · corrective.list_correctives).

화면 표기 (10/6)
- 규칙셋 이름은 'v' 번호로 통일한다 — 개정안이 없는 variant = '기본 규칙 v1', 개정안이 있는 variant = '개정 규칙 v2' (순서대로 v3 …).
  scenario.json 의 variant 이름(개정 전 · 개정 후)은 기록 폴더 이름으로만 쓴다.
- 기대 결과 대조는 개정 후(마지막 variant) 기준이다. 시나리오 목록의 'n / n' 도 같은 기준.
- 시스템 판정(둥근 칩)과 현장 결과(사고 발생 · 사고 없음 — 네모 태그)를 따로 낸다.
"""
from __future__ import annotations

import csv
import io
import json
import re
import shutil
import zipfile
from pathlib import Path

from safety_monitor.judge import RANK
from safety_monitor.runner import check_expect, run_timeline

from .common import REPLAY_DIR, package

_cache: dict[str, dict] = {}

# 입력 출처 — 타임라인 CSV 의 source 칸을 화면 말로. 불꽃(점화원)은 영상 탐지가 맡는다
SOURCE_LABEL = {"CSV": "CSV 스케줄", "버튼": "현장 버튼", "영상": "현장 영상", "자동": "자동 계산"}
FLAME_FACTS = {"ignition_manual"}
TIMELINE_COLS = ["time", "signal", "zone", "target", "value", "source", "note"]


def scenario_keys() -> list[str]:
    """재생 비교 대상 — 영상 점검용 스케줄(scenario.json 의 video_check)은 기대 결과가 없어 뺀다."""
    pkg = package()
    return [k for k in pkg.scenario_keys() if not pkg.scenario(k).data.get("video_check")]


def variant_label(i: int, changes: list[str]) -> str:
    return f"{'개정' if changes else '기본'} 규칙 v{i + 1}"


def run(key: str, force: bool = False) -> dict:
    pkg = package()
    sc = pkg.scenario(key)
    stamp = str(pkg.root.stat().st_mtime) + str((sc.dir / "scenario.json").stat().st_mtime) + key
    if not force and key in _cache and _cache[key]["stamp"] == stamp:
        return _cache[key]
    vs = sc.variants() or {"기본 규칙": {"changes": []}}
    out_root = REPLAY_DIR / key
    if out_root.exists():
        shutil.rmtree(out_root, ignore_errors=True)
    variants = {}
    for i, (name, v) in enumerate(vs.items()):
        r = run_timeline(pkg, sc, v.get("changes", []), name, out_root / name.replace(" ", ""))
        checks = check_expect(r, v.get("expect", []))
        variants[name] = {"run": r, "changes": v.get("changes", []), "checks": checks, "out_dir": out_root / name.replace(" ", ""),
                          "label": variant_label(i, v.get("changes", [])), "summary": summarize(r)}
    basis = list(variants)[-1]               # 기대 결과 대조 기준 = 개정 후(마지막 variant)
    res = {"key": key, "title": sc.title, "zone": sc.zone, "table": r["table"], "basis": sc.data.get("basis", ""),
           "purpose": sc.data.get("purpose", ""), "summary": sc.data.get("summary", ""), "example": bool(sc.data.get("example")),
           "docs": _docs(sc), "expect_basis": basis, "variants": variants, "stamp": stamp, "times": _times(variants)}
    _cache[key] = res
    return res


def run_all(force: bool = False) -> dict[str, dict]:
    return {k: run(k, force) for k in scenario_keys()}


def score(res: dict) -> tuple[int, int]:
    """기대 결과 일치 수 — 개정 후(마지막 variant) 기준."""
    checks = res["variants"][res["expect_basis"]]["checks"]
    return sum(1 for c, _ in checks if c), len(checks)


def _docs(sc) -> list[str]:
    """입력 문서 — 시나리오 폴더의 파일 (scenario.json · timeline.csv · 격리 목록 · 허가서 …)."""
    names = sorted(p.name for p in sc.dir.iterdir() if p.is_file() and not p.name.startswith("."))
    first = [n for n in ("scenario.json", sc.data.get("timeline", "timeline.csv")) if n in names]
    return first + [n for n in names if n not in first]


def summarize(r: dict) -> dict:
    """variant 하나 — 작업 전 차단 · 가장 높은 판정 · 현장 결과(사고 발생 · 사고 없음)."""
    rows = r["log"].rows
    gate = next((e for e in rows if e["kind"] == "gate"), None)
    acc = next((e for e in rows if e["kind"] == "accident"), None)
    prevented = next((e for e in rows if e["kind"] == "info" and e.get("violation_type") == "사고_예방"), None)
    best = None
    for t, st in sorted(r["states"].items()):
        if best is None or RANK[st["level"]] > RANK[best[1]["level"]]:
            best = (t, st)
    top = {"level": best[1]["level"], "t": best[0], "row": best[1]["row"]} if best and best[1]["level"] != "정상" else None
    if acc:
        result = {"kind": "acc", "t": acc["ts"][11:16], "text": "사고 발생", "why": acc.get("reason", "")}
    elif prevented:
        result = {"kind": "prevented", "t": prevented["ts"][11:16], "text": "사고 없음",
                  "why": prevented.get("reason", "")}
    else:
        result = {"kind": "none", "t": None, "text": "사고 없음", "why": "타임라인에 사고 신호가 없다"}
    parts = []
    if gate:
        parts.append(f"작업 시작 전 차단 ({gate['ts'][11:16]})")
    if top:
        parts.append(f"가장 높은 판정 {top['level']} ({top['t']})")
    if result["kind"] == "acc":
        parts.append(f"{result['t']} 사고 발생")
    elif result["kind"] == "prevented":
        parts.append(f"{result['t']} 사고 없음 — 그 전에 작업이 멈춘다고 본다 (가정)")
    return {"gate": {"t": gate["ts"][11:16], "reason": gate.get("reason", ""), "response": gate.get("response", "")} if gate else None,
            "top": top, "result": result, "text": " · ".join(parts) or "판정 변화 없음"}


def _times(variants: dict) -> list[str]:
    ts = set()
    for v in variants.values():
        for tr in v["run"]["trace"]:
            ts.add(f"{tr['t']:%H:%M}")
    return sorted(ts)


def source_label(sig, signals: dict) -> str:
    fact = (signals.get(sig.signal) or {}).get("fact")
    lab = SOURCE_LABEL.get(sig.source, sig.source)
    if sig.source == "영상" and fact in FLAME_FACTS:
        lab += " (불꽃 감지)"
    return lab


def merged_rows(res: dict) -> list[dict]:
    """
    시각마다 한 줄 — 입력 · 사건, 입력 출처, variant 마다 그 시각의 판정 칩과 현장 결과, 비고.
    cell = {kind: gate | 단계, level, row, result: acc | prevented | None, after_gate}
    after_gate = 그 variant 가 이미 작업 전 차단을 낸 뒤 — 엔진은 게이트를 무시하고 진행했다고 가정해 2차 방어를 본다.
    비고 = 작업 전 차단 사유 · 단계가 바뀐 이유(판정표 줄 이름) · 게이트 뒤 가정 · 현장 결과.
    """
    signals = package().signals
    names = list(res["variants"])
    short = {n: f"v{i + 1}" for i, n in enumerate(names)}
    gate_t = {n: (res["variants"][n]["summary"]["gate"] or {}).get("t") for n in names}
    by_t: dict[str, dict] = {}
    for n in names:
        table = res["variants"][n]["run"]["rules"].get("judgments", {}).get(res["table"], {})
        labels = [x.get("label", "") for x in table.get("rows", []) if x.get("label")]
        prev_lv = "정상"
        for tr in res["variants"][n]["run"]["trace"]:
            t = f"{tr['t']:%H:%M}"
            row = by_t.setdefault(t, {"t": t, "what": "", "label": "", "source": "", "cells": {}, "why": {}})
            if tr["signals"] and not row["what"]:
                # 초가 붙은 신호(09:15:30)는 그 분의 줄에 같이 들어가므로 시각을 앞에 적는다 (10/8)
                row["what"] = " + ".join((f"{s.ts:%H:%M:%S} " if s.ts.second else "") + (s.note or s.short()) for s in tr["signals"])
                row["label"] = tr["signals"][0].label or tr["signals"][0].signal      # 신호 사전 이름 (플레이어 눈금)
                row["source"] = " · ".join(dict.fromkeys(source_label(s, signals) for s in tr["signals"]))
            st = tr["state"]
            cell = {"kind": st["level"], "level": st["level"], "row": st["row"], "result": None,
                    "after_gate": bool(gate_t[n] and t > gate_t[n])}
            gates = [e for e in tr["events"] if e["kind"] == "gate"]
            if gates:
                cell["kind"] = "gate"
                row["why"][n] = f"작업 전 차단 — {_short(gates[0].get('reason', ''))}"
            elif st["level"] != prev_lv and st["level"] != "정상" and tr.get("reason"):
                row["why"][n] = _row_label(tr["reason"], labels)
            prev_lv = st["level"]
            if any(e["kind"] == "accident" for e in tr["events"]):
                cell["result"] = "acc"
            elif any(e["kind"] == "info" and e.get("violation_type") == "사고_예방" for e in tr["events"]):
                cell["result"] = "prevented"
            row["cells"][n] = cell
    rows = [by_t[t] for t in sorted(by_t)]
    # 변화가 없는 분은 앞 줄의 상태를 그대로 쓴다 (trace 는 바뀐 분만 남긴다)
    last: dict[str, dict] = {}
    noted_gate: set[str] = set()
    for r in rows:
        notes = []
        for n in names:
            if n in r["cells"]:
                last[n] = r["cells"][n]
            elif n in last:
                r["cells"][n] = {**last[n], "kind": last[n]["level"], "result": None,
                                 "after_gate": bool(gate_t[n] and r["t"] > gate_t[n])}
            c = r["cells"].get(n) or {}
            if n in r["why"]:
                notes.append(f"{short[n]} {r['why'][n]}")
            if c.get("after_gate") and n not in noted_gate:
                noted_gate.add(n)
                notes.append(f"{short[n]}는 이후 게이트를 무시하고 진행했다고 가정 (2차 방어 확인)")
            if c.get("result") == "acc":
                notes.append(f"{short[n]} 사고 발생")
            elif c.get("result") == "prevented":
                notes.append(f"{short[n]} 사고 없음 (사전 중지 가정)")
        r["notes"] = notes
    return rows


def _short(s: str, n: int = 60) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


def _row_label(reason: str, labels: list[str]) -> str:
    """판정 근거 문장 → 판정표 줄 이름 (근거는 '줄 이름 · 축 상태 …' 로 시작한다)."""
    hit = max((lb for lb in labels if reason.startswith(lb)), key=len, default="")
    return _short(hit or reason.split(" · ")[0], 30)


def expect_text(msg: str) -> str:
    """'08:05 게이트 isolation_cross_check 차단' → '08:05 작업 전 차단 (격리 목록 ↔ 배관 계통도)' — 게이트 id 대신 이름."""
    for g in package().rules_base.get("gates", []):
        msg = msg.replace(f"게이트 {g['id']} 차단", f"작업 전 차단 ({g.get('label', g['id'])})")
    return msg


def state_at(res: dict, name: str, t: str) -> dict:
    """player 커서 시각의 상태 — 그 시각까지의 마지막 상태."""
    st = res["variants"][name]["run"]["states"]
    keys = [k for k in sorted(st) if k <= t]
    return st[keys[-1]] if keys else {"level": "정상", "row": None, "axes": {}, "modes": []}


# ---------------------------------------------------------------------- 불러오기 (zip · json)
def _finish_import(pkg, dest: Path) -> str:
    """규격 검사 — 패키지를 다시 읽고 타임라인을 한 번 읽어 본다. 틀리면 풀어 둔 폴더를 지운다."""
    try:
        from safety_monitor.package import load_package
        p2 = load_package(pkg.root)
        sc = p2.scenario(dest.name)
        if not sc.timeline():
            raise ValueError("타임라인이 비었다")
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    from . import common
    common._stamp["t"] = 0                 # 패키지를 바로 다시 읽게
    return dest.name


def _dest(pkg, key: str) -> Path:
    key = key.strip().replace("/", "_").replace("\\", "_").replace("..", "_")
    if not key:
        raise ValueError("시나리오 이름(폴더 이름)이 비었다")
    dest = pkg.root / "scenarios" / key
    if dest.exists():
        raise ValueError(f"같은 이름의 시나리오가 이미 있다: {key}")
    return dest


def import_zip(path: str, filename: str = "") -> str:
    """zip — 시나리오 폴더째 (scenario.json · timeline.csv · 입력 문서). 사업장 패키지 scenarios/ 에 푼다."""
    pkg = package()
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        sj = [n for n in names if n.endswith("scenario.json")]
        if not sj:
            raise ValueError("zip 안에 scenario.json 이 없다")
        prefix = sj[0][: -len("scenario.json")]
        dest = _dest(pkg, Path(prefix.rstrip("/")).name or Path(filename or path).stem)
        for n in names:
            if not n.startswith(prefix) or ".." in n:
                continue
            out = dest / n[len(prefix):]
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(z.read(n))
    return _finish_import(pkg, dest)


def import_json(files: list[tuple[str, bytes]]) -> str:
    """
    json — scenario.json 하나, 또는 scenario.json + 같이 고른 파일(timeline.csv · 격리 목록 · 허가서).
      · timeline 이 행 목록이면 ([{"time": "08:00", "signal": "ptw_issued", ...}]) timeline.csv 로 풀어 쓴다
      · timeline 이 파일 이름이면 그 파일을 같이 골라야 한다
    폴더 이름 = scenario.json 의 key, 없으면 json 파일 이름 (scenario.json 이면 name 앞부분).
    """
    pkg = package()
    js = [(n, b) for n, b in files if n.lower().endswith(".json")]
    main = next(((n, b) for n, b in js if Path(n).name == "scenario.json"), None) or next(
        ((n, b) for n, b in js if b"\"variants\"" in b or b"\"timeline\"" in b), None)
    if not main:
        raise ValueError("시나리오 json 이 없다 — scenario.json(variants · timeline 이 있는 파일)을 고른다")
    try:
        data = json.loads(main[1].decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as ex:
        raise ValueError(f"{main[0]} — json 을 읽을 수 없다 ({ex})") from ex
    if not isinstance(data, dict) or not data.get("variants"):
        raise ValueError(f"{main[0]} — variants(비교할 규칙셋 · 기대 결과)가 없다")
    others = {Path(n).name: b for n, b in files if (n, b) is not main}
    stem = Path(main[0]).stem
    key = data.pop("key", None) or (stem if stem != "scenario" else re.sub(r"[\s·/\\]+", "_", data.get("name") or "").strip("_"))
    dest = _dest(pkg, key or "불러온_시나리오")
    tl = data.get("timeline", "timeline.csv")
    if isinstance(tl, list):
        if not tl:
            raise ValueError("timeline 행 목록이 비었다")
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=TIMELINE_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows({k: ("" if r.get(k) is None else r.get(k)) for k in TIMELINE_COLS} for r in tl)
        data["timeline"] = "timeline.csv"
        dest.mkdir(parents=True)
        (dest / "timeline.csv").write_text(buf.getvalue(), encoding="utf-8-sig")
    elif isinstance(tl, str):
        if tl not in others:
            raise ValueError(f"타임라인 파일 {tl} 을 json 과 같이 고른다 (또는 json 의 timeline 에 행 목록을 넣는다)")
        dest.mkdir(parents=True)
    else:
        raise ValueError("timeline 은 파일 이름 또는 행 목록이어야 한다")
    for n, b in others.items():
        (dest / n).write_bytes(b)
    (dest / "scenario.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return _finish_import(pkg, dest)


def handoff_mark(res: dict, name: str) -> dict:
    """문서 자동화로 넘길 때 붙이는 표시 — 넘긴 내역 · 그것으로 만든 문서에 '재생 비교 검증본'으로 남는다."""
    v = res["variants"][name]
    return {"scenario": res["key"], "title": res["title"], "variant": name, "label": v["label"],
            "changes": v["changes"], "text": f"재생 비교 검증본 · {res['title']} · {v['label']} · 운영 기록 아님"}
