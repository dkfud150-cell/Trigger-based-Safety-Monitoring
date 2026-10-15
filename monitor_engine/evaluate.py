"""
정답 대비 성능 평가 — 시험 영상 하나를 엔진으로 돌려, 사람이 적은 정답(CSV)과 비교한다 (10/8).

  python evaluate.py steel_pickling V_영상점검 --scene PPE탐지 --template 정답/PPE탐지.csv   정답 칸이 빈 양식부터 만든다
  python evaluate.py steel_pickling V_영상점검 --scene PPE탐지 --truth 정답/PPE탐지.csv       채점
  python evaluate.py steel_pickling --video 파일.mp4 --camera CAM-Z10-01 --truth 정답.csv
  옵션  --set person.conf=0.3   판정 기준을 바꿔 돌린다(여러 번 줄 수 있다) — 같은 정답으로 바꾸기 전 · 후를 비교할 때
        --label 이름            결과 이름 (예: '개선 전' · '밝기 확인 켬')
        --stride 2              몇 프레임마다 탐지할지 (기본 detect.json run.stride)
        --tol 2                 불꽃 · 위험구역의 구간 경계 앞뒤 몇 초는 채점하지 않는다 (기본 2초)

정답 CSV — 한 줄 = 영상의 한 구간
  start,end,zone,people,no_helmet,no_vest,flame,hazard_entry,note
  0:00,0:05,Z10,3,1,0,0,0,세 명 · 한 명 안전모 없음
    start · end      영상 안의 시각 (초 또는 분:초)
    zone             구역 (비우면 카메라 구역)
    people           그 구역에 보이는 사람 수
    no_helmet        안전모를 안 쓴 사람 수     no_vest  안전조끼를 안 입은 사람 수
    flame            불꽃(불티)이 보이면 1, 아니면 0
    hazard_entry     위험구역(상시 · 작업 중) 안에 사람이 있으면 1, 아니면 0
  칸을 비우면 그 항목은 그 구간에서 채점하지 않는다. note 는 조명 · 거리 · 각도 같은 조건을 적어 두는 칸이다.

채점 — 탐지한 프레임마다 시스템이 낸 값을 그 시각의 정답과 비교한다
  사람 · 미착용 수     맞춤 = min(정답, 시스템) · 오탐 = 시스템이 더 센 만큼 · 미탐 = 덜 센 만큼
  불꽃 · 위험구역 진입  있음/없음 — 맞춤 · 오탐 · 미탐 · 맞는 없음. 불꽃은 확정(persistence) 기준이라 몇 초 늦게 켜지고 늦게 꺼진다 —
                       그래서 값이 바뀌는 구간 경계 ±tol 초는 채점하지 않고, 지연은 '첫 탐지까지'로 따로 잰다
  정밀도 = 맞춤 / (맞춤 + 오탐)   재현율 = 맞춤 / (맞춤 + 미탐)   오탐률 = 오탐 / (오탐 + 맞는 없음)   미탐률 = 미탐 / (맞춤 + 미탐)
결과  outputs/eval/<영상>_<시각>/report.md · samples.csv · summary.json — summary 는 대시보드 '탐지 신뢰도' 화면의 성능 평가에 뜬다
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from safety_monitor.package import OUTPUT_DIR, ROOT, PackageError, load_package, resolve_changes

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

COLS = ["start", "end", "zone", "people", "no_helmet", "no_vest", "flame", "hazard_entry", "note"]
ITEMS = [  # (키, 이름, 종류)
    ("people", "사람 수", "count"),
    ("no_helmet", "안전모 미착용 수", "count"),
    ("no_vest", "안전조끼 미착용 수", "count"),
    ("flame", "불꽃 (점화원 확정)", "binary"),
    ("hazard_entry", "위험구역 안 사람", "binary"),
]


# ---------------------------------------------------------------------- 정답 읽기
def parse_t(s: str) -> float:
    s = str(s).strip()
    if ":" in s:
        m, sec = s.rsplit(":", 1)
        return int(m) * 60 + float(sec)
    return float(s)


def parse_v(s: str, kind: str):
    s = str(s or "").strip()
    if not s:
        return None
    if kind == "binary":
        if s.upper() in ("1", "O", "Y", "YES", "예", "있음", "TRUE"):
            return 1
        if s.upper() in ("0", "X", "N", "NO", "아니오", "없음", "FALSE"):
            return 0
        raise ValueError(f"있음/없음 칸은 1 또는 0 — '{s}'")
    return int(float(s))


def load_truth(path: Path, cam_zone: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for i, r in enumerate(csv.DictReader(f), start=2):
            if not (r.get("start") or "").strip() or r["start"].strip().startswith("#"):
                continue
            try:
                row = {"start": parse_t(r["start"]), "end": parse_t(r["end"]), "zone": (r.get("zone") or "").strip() or cam_zone,
                       "note": (r.get("note") or "").strip()}
                for k, _, kind in ITEMS:
                    row[k] = parse_v(r.get(k), kind)
            except (ValueError, KeyError) as e:
                raise PackageError(f"정답 CSV {path.name} {i}번째 줄: {e}") from None
            if row["end"] <= row["start"]:
                raise PackageError(f"정답 CSV {path.name} {i}번째 줄: end 가 start 보다 커야 한다")
            rows.append(row)
    if not rows:
        raise PackageError(f"정답 CSV 에 구간이 없다 — {path}")
    # 값이 바뀌는 경계 표시 — 있음/없음 항목에서 앞 · 뒤와 값이 다르면 그 경계 ±tol 은 채점하지 않는다.
    # 이웃 구간이 없는 '있음' 구간(앞뒤를 안 적은 경우)도 바깥은 '없음'으로 보고 경계로 친다 (영상 맨 앞 0초는 빼고)
    for z in {r["zone"] for r in rows}:
        zr = sorted((r for r in rows if r["zone"] == z), key=lambda r: r["start"])
        for i, r in enumerate(zr):
            prev = zr[i - 1] if i > 0 and abs(zr[i - 1]["end"] - r["start"]) < 1e-6 else None
            nxt = zr[i + 1] if i + 1 < len(zr) and abs(zr[i + 1]["start"] - r["end"]) < 1e-6 else None
            for k, _, kind in ITEMS:
                if kind != "binary" or r[k] is None:
                    continue
                if (prev is not None and prev[k] is not None and prev[k] != r[k]) or (prev is None and r[k] == 1 and r["start"] > 0):
                    r.setdefault("_edge_start", set()).add(k)
                if (nxt is not None and nxt[k] is not None and nxt[k] != r[k]) or (nxt is None and r[k] == 1):
                    r.setdefault("_edge_end", set()).add(k)
    return rows


# ---------------------------------------------------------------------- 시스템 값 (탐지한 프레임마다)
def system_values(eng, zone: str) -> dict:
    from safety_monitor.zones import HAZARD_TYPES
    ppe = eng.ppe.get(zone, {})
    in_hz = any(q.zone == zone and q.type in HAZARD_TYPES for p in eng.persons for q in p.polys)
    return {"people": len(eng.store.people.get(zone, [])),
            "no_helmet": ppe.get("helmet", {}).get("off", 0) if "helmet" in eng.ppe_items else None,
            "no_vest": ppe.get("vest", {}).get("off", 0) if "vest" in eng.ppe_items else None,
            "flame": 1 if eng.store.detections.get(("flame", zone), {}).get("on") else 0,
            "hazard_entry": 1 if in_hz else 0}


# ---------------------------------------------------------------------- 채점
def _ratio(a, b):
    return round(a / b, 3) if b else None


def score(samples: list[dict], truth: list[dict], tol: float) -> list[dict]:
    """samples = [{t, zone → {항목: 시스템 값}}] · truth = load_truth() 결과 → 항목마다 결과 한 줄."""
    out = []
    for key, label, kind in ITEMS:
        tp = fp = fn = tn = n = 0
        err = 0.0
        spans = hit = 0
        delays = []
        skipped = 0
        for r in truth:
            if r[key] is None:
                continue
            g = r[key]
            first = None
            for s in samples:
                t = s["t"]
                if not (r["start"] <= t < r["end"] + (tol if kind == "binary" and g == 1 else 0)):
                    continue
                p = s["v"].get(r["zone"], {}).get(key)
                if p is None:
                    continue
                if kind == "binary" and g == 1 and p == 1 and first is None:
                    first = t
                if t >= r["end"]:            # 끝 뒤 tol 은 '첫 탐지'를 찾을 때만 본다
                    continue
                if kind == "binary" and ((key in r.get("_edge_start", ()) and t < r["start"] + tol)
                                         or (key in r.get("_edge_end", ()) and t > r["end"] - tol)):
                    skipped += 1
                    continue
                n += 1
                if kind == "count":
                    tp += min(g, p)
                    fp += max(0, p - g)
                    fn += max(0, g - p)
                    err += abs(p - g)
                else:
                    tp += int(g == 1 and p == 1)
                    fp += int(g == 0 and p == 1)
                    fn += int(g == 1 and p == 0)
                    tn += int(g == 0 and p == 0)
            if kind == "binary" and g == 1:
                spans += 1
                if first is not None:
                    hit += 1
                    delays.append(max(0.0, first - r["start"]))
        row = {"key": key, "label": label, "kind": kind, "samples": n, "tp": tp, "fp": fp, "fn": fn,
               "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn), "miss_rate": _ratio(fn, tp + fn)}
        if kind == "count":
            row["mae"] = round(err / n, 2) if n else None
        else:
            row.update(tn=tn, fp_rate=_ratio(fp, fp + tn), skipped=skipped, spans=spans, spans_hit=hit,
                       delay_avg=round(sum(delays) / len(delays), 1) if delays else None)
        out.append(row)
    return out


# ---------------------------------------------------------------------- 실행
def _set(cfg: dict, assign: str) -> tuple[str, object]:
    if "=" not in assign:
        raise PackageError(f"--set 은 경로=값 — '{assign}'")
    path, raw = assign.split("=", 1)
    keys = path.strip().split(".")
    d = cfg
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    old = d.get(keys[-1])
    try:
        v = int(raw) if isinstance(old, int) and not isinstance(old, bool) else float(raw)
    except ValueError:
        v = raw
    d[keys[-1]] = v
    return path.strip(), v


def resolve(pkg, args):
    sc = pkg.scenario(args.scenario) if args.scenario else None
    scene, cam_id, video = None, args.camera, args.video
    if args.scene:
        if not sc:
            raise PackageError("--scene 은 시나리오와 같이 준다")
        scene = next((s for s in sc.scenes() if s.get("name") == args.scene), None)
        if scene is None:
            raise PackageError(f"장면이 없습니다: {args.scene} (있는 것: {', '.join(s.get('name', '') for s in sc.scenes())})")
        cam_id = cam_id or scene.get("camera")
        video = video or scene.get("video")
    if not video:
        raise PackageError("--video 또는 --scene 이 필요하다")
    cands = [Path(video)] + ([sc.dir / video] if sc else []) + [pkg.root / video, ROOT / video]
    vpath = next((c for c in cands if c.exists()), None)
    if vpath is None:
        raise PackageError(f"영상 파일이 없습니다: {video}")
    cam = pkg.scene_camera({**scene, "camera": cam_id}) if scene and cam_id == scene.get("camera") else {**pkg.camera(cam_id), "polygons": []}
    return sc, scene, cam, vpath


def write_template(path: Path, vpath: Path, zone: str, span: float):
    import cv2
    cap = cv2.VideoCapture(str(vpath))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
    cap.release()
    if dur <= 0:
        raise PackageError(f"영상 길이를 읽지 못했다 — {vpath}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        t = 0.0
        while t < dur - 1e-6:
            e = min(dur, t + span)
            w.writerow([f"{int(t // 60)}:{t % 60:04.1f}", f"{int(e // 60)}:{e % 60:04.1f}", zone, "", "", "", "", "", ""])
            t = e
    print(f"정답 양식을 만들었다 — {path} ({dur:.1f}초 · {span:g}초 구간). 칸을 채우고 --truth 로 채점한다 (모르는 칸은 비운다)")


def report_md(summary: dict, rows: list[dict]) -> str:
    def pct(v):
        return "-" if v is None else f"{v * 100:.1f}%"
    lines = [f"# 정답 대비 성능 평가 — {summary['video']}", "",
             f"- 결과 이름: {summary['label']}", f"- 장면 · 카메라: {summary.get('scene') or '-'} · {summary['camera']}",
             f"- 정답: {summary['truth']} (구간 {summary['truth_rows']}개)", f"- 탐지한 프레임: {summary['samples']}개 · stride {summary['stride']} · 경계 제외 ±{summary['tol']}초",
             f"- 바꾼 판정 기준: {', '.join(f'{k}={v}' for k, v in summary['settings'].items()) or '없음 (패키지 기본)'}",
             f"- 만든 시각: {summary['created']}", "",
             "| 항목 | 채점 프레임 | 맞춤 | 오탐 | 미탐 | 정밀도 | 재현율 | 오탐률 | 미탐률 | 그 밖 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        etc = f"평균 오차 {r['mae']}명" if r["kind"] == "count" and r.get("mae") is not None else \
            (f"구간 {r['spans_hit']}/{r['spans']} 잡음 · 첫 탐지까지 평균 {r['delay_avg']}초" if r["kind"] == "binary" and r.get("spans") else "")
        lines.append(f"| {r['label']} | {r['samples']} | {r['tp']} | {r['fp']} | {r['fn']} | {pct(r['precision'])} | {pct(r['recall'])} | "
                     f"{pct(r.get('fp_rate')) if r['kind'] == 'binary' else '-'} | {pct(r['miss_rate'])} | {etc} |")
    lines += ["", "채점 방법은 monitor_engine/evaluate.py 맨 위 설명. 사람 · 미착용 수는 사람 단위(맞춤 = 정답과 시스템 중 작은 쪽), "
              "불꽃 · 위험구역은 프레임 단위(있음/없음)다. 정답을 비운 칸은 채점하지 않는다."]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="정답 대비 성능 평가 — 정밀도 · 재현율 · 오탐률 · 미탐률")
    ap.add_argument("package")
    ap.add_argument("scenario", nargs="?")
    ap.add_argument("--scene")
    ap.add_argument("--video")
    ap.add_argument("--camera")
    ap.add_argument("--truth", help="정답 CSV")
    ap.add_argument("--template", help="정답 양식(빈 칸)을 이 경로에 만든다")
    ap.add_argument("--span", type=float, default=5.0, help="양식 구간 길이 (초)")
    ap.add_argument("--set", action="append", default=[], help="판정 기준 바꾸기 — 예: person.conf=0.3")
    ap.add_argument("--label", default="")
    ap.add_argument("--changes", default="none", help="규칙셋 (none · all · R1,R3 …) — 탐지 채점에는 거의 영향 없다")
    ap.add_argument("--stride", type=int)
    ap.add_argument("--tol", type=float, default=2.0)
    args = ap.parse_args()

    pkg = load_package(args.package)
    sc, scene, cam, vpath = resolve(pkg, args)
    cam_zone = cam.get("zone") or ""
    if args.template:
        write_template(Path(args.template), vpath, cam_zone, args.span)
        return
    if not args.truth:
        ap.error("--truth 정답.csv 또는 --template 양식.csv 를 준다")
    truth_path = Path(args.truth)
    truth = load_truth(truth_path, cam_zone)

    dcfg = copy.deepcopy(pkg.detect)
    settings = dict(_set(dcfg, a) for a in args.set)
    ids, rlabel = resolve_changes(args.changes, pkg, sc)
    rules = pkg.rules(ids)
    rules["_label"] = rlabel
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = OUTPUT_DIR / "eval" / f"{vpath.stem}_{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    zones_needed = sorted({r["zone"] for r in truth})
    samples = []

    def on_sample(t, eng):
        samples.append({"t": round(t, 3), "v": {z: system_values(eng, z) for z in zones_needed}})

    from safety_monitor.video import run_video
    print(f"영상 {vpath.name} · 카메라 {cam.get('camera_id')} · 정답 {truth_path.name} ({len(truth)}구간)"
          + (f" · 바꾼 기준 {settings}" if settings else ""))
    run_video(pkg, rules, vpath, cam, out / "run", scenario=None, show=False, save=False, stride=args.stride,
              realtime=False, on_sample=on_sample, detect_cfg=dcfg)
    rows = score(samples, truth, args.tol)

    with open(out / "samples.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "zone"] + [f"시스템_{k}" for k, _, _ in ITEMS])
        for s in samples:
            for z, v in s["v"].items():
                w.writerow([s["t"], z] + [v.get(k) for k, _, _ in ITEMS])
    summary = {"label": args.label or (", ".join(f"{k}={v}" for k, v in settings.items()) or "패키지 기본"),
               "video": vpath.name, "scene": scene.get("name") if scene else "", "camera": cam.get("camera_id"),
               "truth": truth_path.name, "truth_rows": len(truth), "samples": len(samples),
               "stride": args.stride or dcfg.get("run", {}).get("stride", 1), "tol": args.tol, "settings": settings,
               "created": datetime.now().isoformat(timespec="seconds"), "items": rows}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md = report_md(summary, rows)
    (out / "report.md").write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"저장: {out}")


if __name__ == "__main__":
    try:
        main()
    except PackageError as e:
        sys.exit(f"[오류] {e}")
