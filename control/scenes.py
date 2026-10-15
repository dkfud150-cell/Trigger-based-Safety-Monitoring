"""
영상 장면 — 화면에서 영상을 올리고, 첫 프레임 위에 구역(폴리곤)을 그려 장면으로 등록한다.

  영상     사업장 패키지 videos/ 에 저장한다 (scenario.json 의 video 경로가 가리키는 곳과 같다)
  장면     그 시나리오의 scenario.json scenes 에 한 줄 — 이름 · 시작 시각 · 카메라 · 영상 · 구역(polygons)
  구역     장면에 적힌 polygons 만 쓴다. 카메라 기본 구역(cameras/*.json)은 쓰지 않는다 (10/8) —
           장면에 구역이 없으면 화면 전체로 판정한다. 좌표는 화면 비율(0~1)이라 해상도가 달라도 같다.

판정은 폴리곤 이름이 아니라 종류(type)로 걸린다 — rules.json 의 checks 가 'work' · 'restricted' 를,
불꽃 탐지(detect.json flame.polygons)가 'hazard' · 'hazard_repair' 를 본다. 그래서 종류와 구역만 맞으면
새로 그린 구역에도 같은 규칙 · 판정표가 그대로 걸린다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from .common import live_sessions, package, package_changed, read_jsonl, zone_name, zones

VIDEO_EXT = {".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm"}

# 구역 종류 — 화면에 보이는 이름 · 설명 · 색. 판정이 보는 종류는 monitor_engine 의 zones.py / rules.json 과 같다.
# 이 네 개는 판정에 쓰여 고정이고, 그 밖의 종류(통로 · 설비 위치 …)는 관리자가 화면에서 더한다 → 패키지 zone_types.json
TYPES = {
    "hazard": {"label": "위험구역 (상시)", "prefix": "E", "color": "#e5584a",
               "desc": "설비 때문에 늘 위험한 곳. 불꽃이 여기서 잡히면 점화원 축이 켜진다"},
    "hazard_repair": {"label": "위험구역 (작업 중)", "prefix": "ER", "color": "#ff6b5e",
                      "desc": "그 작업 때문에 한시적으로 위험한 곳. 불꽃도 본다 · 모드가 켜질 때 진하게 보인다"},
    "work": {"label": "작업 구역", "prefix": "W", "color": "#6cc3c8",
             "desc": "작업 인원 · 2인 1조 · 화재감시자를 세는 곳"},
    "restricted": {"label": "출입 제한", "prefix": "X", "color": "#e0a13a",
                   "desc": "모드가 켜지면 사람이 들어올 때 경보"},
}
HAZARD_TYPES = ("hazard", "hazard_repair")
TYPE_FILE = "zone_types.json"
_type_lock = threading.Lock()


# ====================================================================== 구역 종류 — 기본 넷 + 관리자가 더한 것
def all_types() -> dict[str, dict]:
    """key → {label, prefix, color, desc, builtin}. 기본 넷이 먼저, 관리자가 더한 것이 뒤."""
    out = {k: {**v, "builtin": True} for k, v in TYPES.items()}
    for t in package().zone_types:
        if t.get("key") and t["key"] not in out:
            out[t["key"]] = {"label": t.get("label") or t["key"], "prefix": t.get("prefix") or "P",
                             "color": t.get("color") or "#9aa4af", "desc": t.get("desc") or "", "builtin": False}
    return out


def type_usage() -> dict[str, list[str]]:
    """종류마다 어디서 쓰는지 — '시나리오/장면.구역' · 'cameras/카메라.구역'."""
    pkg = package()
    use: dict[str, list[str]] = {}
    for c in pkg.cameras.values():
        for q in c.get("polygons", []):
            use.setdefault(q.get("type", "work"), []).append(f"카메라 {c['camera_id']}.{q.get('name')}")
    for k in pkg.scenario_keys():
        for x in pkg.scenario(k).scenes():
            for q in x.get("polygons") or []:
                use.setdefault(q.get("type"), []).append(f"장면 ‘{x.get('name')}’.{q.get('name')}")
    return use


def _type_file() -> tuple[Path, dict]:
    p = package().root / TYPE_FILE
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {
        "_설명": "영상 장면 편집기 '구역 추가'에 나오는 종류 가운데 관리자가 더한 것. 기본 네 종류(hazard · hazard_repair · "
                 "work · restricted)는 판정에 쓰여서 여기 적지 않는다. 여기 종류는 화면 표시와 사람 위치 기록에 쓰이고, "
                 "판정에 쓰려면 rules.json 모드 checks 의 polygons 에 key 를 적는다.", "types": []}
    data.setdefault("types", [])
    return p, data


def _write_json(p: Path, data: dict):
    text = json.dumps(data, ensure_ascii=False, indent=2)
    json.loads(text)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    tmp.replace(p)
    package_changed()


def save_type(body: dict) -> dict:
    """구역 종류 더하기 · 고치기 (관리자). key 를 비우면 영문으로 하나 만든다."""
    label = str(body.get("label") or "").strip()
    color = str(body.get("color") or "").strip().lower()
    desc = str(body.get("desc") or "").strip()
    key = str(body.get("key") or "").strip().lower()
    prefix = str(body.get("prefix") or "").strip().upper()
    if not label or len(label) > 30:
        raise ValueError("종류 이름을 30자 안으로 적는다 — 예: 통로 (작업자 이동)")
    if not re.fullmatch(r"#[0-9a-f]{6}", color):
        raise ValueError("색은 #RRGGBB 로 고른다")
    if len(desc) > 120:
        raise ValueError("설명은 120자 안으로")
    with _type_lock:
        p, data = _type_file()
        types = data["types"]
        have = all_types()
        cur = next((t for t in types if t.get("key") == key), None) if key else None
        if key and key in TYPES:
            raise ValueError(f"‘{key}’ 는 판정에 쓰는 기본 종류라 바꿀 수 없다")
        if cur is None:
            if any((t.get("label") or "") == label for t in types) or any(v["label"] == label for v in TYPES.values()):
                raise ValueError(f"같은 이름의 종류가 이미 있다 — ‘{label}’")
            if key:
                if not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", key):
                    raise ValueError("영문 키는 영문 소문자로 시작하는 영문 · 숫자 · _ (예: passage) — 비우면 저절로 만든다")
            else:
                n = 1
                while f"type{n}" in have:
                    n += 1
                key = f"type{n}"
            if not prefix:
                prefix = "".join(ch for ch in key.upper() if ch.isalpha())[:2] or "P"
            if not re.fullmatch(r"[A-Z]{1,3}", prefix):
                raise ValueError("구역 이름 앞글자는 영문 대문자 1~3자 (예: P → P1, P2)")
            types.append({"key": key, "label": label, "prefix": prefix, "color": color, "desc": desc})
            verb = "더했다"
        else:
            cur.update(label=label, color=color, desc=desc, **({"prefix": prefix} if prefix else {}))
            verb = "고쳤다"
        _write_json(p, data)
    return {"key": key, "msg": f"구역 종류 ‘{label}’ 를 {verb} ({key}) — 화면 표시 · 사람 위치 기록용. "
                               f"판정에 쓰려면 rules.json 의 polygons 에 ‘{key}’ 를 적는다"}


def remove_type(body: dict) -> dict:
    key = str(body.get("key") or "").strip()
    if key in TYPES:
        raise ValueError("판정에 쓰는 기본 종류는 지울 수 없다")
    used = type_usage().get(key, [])
    if used:
        raise ValueError(f"이 종류를 쓰는 구역이 {len(used)}개 있다 — {', '.join(used[:4])}" + (" …" if len(used) > 4 else "")
                         + ". 그 구역의 종류를 바꾸거나 지운 뒤 다시 한다")
    with _type_lock:
        p, data = _type_file()
        left = [t for t in data["types"] if t.get("key") != key]
        if len(left) == len(data["types"]):
            raise ValueError(f"없는 종류 ‘{key}’")
        data["types"] = left
        _write_json(p, data)
    return {"msg": f"구역 종류 ‘{key}’ 를 지웠다"}


# ====================================================================== 카메라 — 장면 편집기에서 한 대 더하기
def save_camera(body: dict) -> dict:
    """새 카메라 → cameras/<id>.json. 기본 구역 없이 만든다 — 장면마다 그린 구역으로 판정한다."""
    pkg = package()
    cid = str(body.get("camera_id") or "").strip()
    zone = body.get("zone") or ""
    label = str(body.get("label") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,39}", cid):
        raise ValueError("카메라 ID 는 영문 · 숫자 · - · _ 로 (예: CAM-Z8-02) — 파일 이름이 된다")
    if cid in pkg.cameras or (pkg.root / "cameras" / f"{cid}.json").exists():
        raise ValueError(f"이미 있는 카메라 ‘{cid}’")
    if zone not in zones():
        raise ValueError("카메라가 보는 구역을 고른다")
    if len(label) > 60:
        raise ValueError("설명은 60자 안으로")
    d = pkg.root / "cameras"
    d.mkdir(exist_ok=True)
    _write_json(d / f"{cid}.json", {
        "_설명": f"영상 장면 편집기에서 만든 카메라 ({datetime.now():%Y-%m-%d %H:%M}). 기본 구역이 없다 — 이 카메라를 쓰는 장면마다 "
                 "화면에서 그린 구역으로 판정한다. 기본 구역이 필요하면 calibrate.py 로 polygons 를 찍는다.",
        "camera_id": cid, "zone": zone, "label": label, "polygons": [], "floor_calib": None})
    return {"camera_id": cid, "msg": f"카메라 ‘{cid}’ 를 더했다 — {zone} {zone_name(zone)}" + (f" · {label}" if label else "")}


def remove_camera(body: dict) -> dict:
    """카메라 파일 지우기 — 어느 장면도 쓰지 않고 기본 구역도 없는 카메라만."""
    pkg = package()
    cid = str(body.get("camera_id") or "").strip()
    cam = pkg.cameras.get(cid)
    if not cam:
        raise ValueError(f"없는 카메라 ‘{cid}’")
    if cam.get("polygons"):
        raise ValueError(f"‘{cid}’ 에는 기본 구역이 {len(cam['polygons'])}개 있다 — 화면에서는 지우지 않는다 (cameras/{cid}.json)")
    used = [f"{k}/{x.get('name')}" for k in pkg.scenario_keys() for x in pkg.scenario(k).scenes() if x.get("camera") == cid]
    if used:
        raise ValueError(f"이 카메라를 쓰는 장면이 있다 — {', '.join(used[:4])}. 장면의 카메라를 바꾸거나 뺀 뒤 다시 한다")
    Path(cam["_path"]).unlink()
    package_changed()
    return {"msg": f"카메라 ‘{cid}’ 를 지웠다"}


# ====================================================================== 경로
def _scenario(schedule: str):
    if not schedule:
        raise ValueError("신호 스케줄을 먼저 고른다 — 영상 장면은 스케줄(시나리오)마다 따로 둔다")
    return package().scenario(schedule)


def videos_dir() -> Path:
    return package().root / "videos"


def resolve_video(video: str, schedule: str | None = None) -> Path:
    """장면의 video 경로 → 실제 파일. 패키지 폴더 밖은 열지 않는다."""
    pkg = package()
    if not video:
        raise ValueError("영상이 없다")
    if Path(video).suffix.lower() not in VIDEO_EXT:
        raise ValueError(f"영상 파일이 아니다 — {video}")
    bases = ([_scenario(schedule).dir] if schedule else []) + [pkg.root]
    for b in bases:
        p = (b / video).resolve()
        if p.exists() and (pkg.root.resolve() in p.parents):
            return p
    raise ValueError(f"영상 파일이 없다 — {video}")


def _rel(p: Path) -> str:
    return p.resolve().relative_to(package().root.resolve()).as_posix()


def _safe_name(filename: str) -> str:
    stem, ext = os.path.splitext(Path(filename or "").name)
    ext = ext.lower()
    if ext not in VIDEO_EXT:
        raise ValueError(f"영상 파일만 올린다 ({', '.join(sorted(VIDEO_EXT))}) — 받은 것: {ext or '확장자 없음'}")
    # OpenCV 가 윈도우 한글 경로를 못 여는 경우가 있어 파일 이름은 영문 · 숫자로만 둔다
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._-")[:60]
    return (stem or f"scene_{datetime.now():%Y%m%d_%H%M%S}") + ext


# ====================================================================== 영상 읽기
_lock = threading.Lock()
_frame_cache: dict[tuple[str, float], tuple[bytes, dict]] = {}


def _open(path: Path):
    """cv2.VideoCapture — 한글 경로에서 못 열면 영문 임시 파일로 복사해서 연다(돌고 있는 영상과 겹치지 않게 이름을 따로)."""
    import cv2
    cap = cv2.VideoCapture(str(path))
    if cap.isOpened():
        return cap, None
    fd, tmp = tempfile.mkstemp(suffix=path.suffix.lower() or ".mp4", prefix="sm_scene_")
    os.close(fd)
    shutil.copyfile(path, tmp)
    cap = cv2.VideoCapture(tmp)
    return cap, Path(tmp)


def first_frame(path: Path) -> tuple[bytes, dict]:
    """첫 프레임 JPEG 와 영상 정보(가로 · 세로 · fps · 길이). 못 읽으면 ValueError."""
    import cv2
    key = (str(path), path.stat().st_mtime)
    with _lock:
        if key in _frame_cache:
            return _frame_cache[key]
    cap, tmp = _open(path)
    try:
        if not cap.isOpened():
            raise ValueError(f"영상을 열지 못했다 — {path.name}. mp4(H.264)로 바꿔서 올린다")
        ok, frame = cap.read()
        if not ok or frame is None:
            raise ValueError(f"영상에서 프레임을 읽지 못했다 — {path.name}. mp4(H.264)로 바꿔서 올린다")
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        h, w = frame.shape[:2]
        ok, enc = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not ok:
            raise ValueError("첫 프레임을 그림으로 바꾸지 못했다")
        info = {"w": int(w), "h": int(h), "fps": round(float(fps), 2),
                "seconds": round(n / fps, 1) if fps > 0 and n > 0 else None}
    finally:
        cap.release()
        if tmp:
            tmp.unlink(missing_ok=True)
    out = (enc.tobytes(), info)
    with _lock:
        if len(_frame_cache) > 40:
            _frame_cache.clear()
        _frame_cache[key] = out
    return out


def _digest(p: Path) -> str:
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _same_video(d: Path, tmp: Path) -> Path | None:
    """videos/ 에 내용이 똑같은 영상이 이미 있으면 그 파일 — 이름이 달라도(scene_날짜.mp4 등) 같은 영상으로 본다."""
    size, dig = tmp.stat().st_size, None
    for f in sorted(d.iterdir()):
        if f == tmp or not f.is_file() or f.suffix.lower() not in VIDEO_EXT or f.stat().st_size != size:
            continue
        dig = dig or _digest(tmp)
        if _digest(f) == dig:
            return f
    return None


def save_upload(schedule: str, filename: str, fileobj) -> dict:
    """
    올린 영상을 videos/ 에 저장하고 첫 프레임을 확인한다.
    내용이 같은 영상이 이미 있으면 새로 저장하지 않고 있던 파일을 쓴다(same=True) — 그 영상을 쓰는 장면도 같이 돌려준다.
    이름만 같고 내용이 다르면 뒤에 -2, -3 …
    """
    _scenario(schedule)                              # 스케줄이 있는지 먼저
    name = _safe_name(filename)
    d = videos_dir()
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=Path(name).suffix, prefix="sm_up_", dir=d)
    os.close(fd)
    tmp = Path(tmp)
    same = False
    try:
        with open(tmp, "wb") as f:
            shutil.copyfileobj(fileobj, f)
        if tmp.stat().st_size == 0:
            raise ValueError("빈 파일이다")
        dest = _same_video(d, tmp)
        if dest is not None:
            same = True                              # 같은 영상을 또 올렸다 — 있던 것을 쓴다
        else:
            _, info = first_frame(tmp)               # 못 읽는 영상이면 여기서 멈춘다 — 저장하지 않는다
            stem, ext = os.path.splitext(name)
            dest, i = d / name, 2
            while dest.exists():
                dest, i = d / f"{stem}-{i}{ext}", i + 1
            tmp.replace(dest)
            os.chmod(dest, 0o644)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    _, info = first_frame(dest)
    rel = _rel(dest)
    _, data = _read(schedule)
    used = [x for x in data.get("scenes", []) if _video_key(x.get("video"), schedule) == rel]
    return {"video": rel, "file": dest.name, "same": same,
            "scenes": [{"name": x.get("name"), "camera": x.get("camera")} for x in used], **info}


def _video_key(video: str | None, schedule: str | None = None) -> str:
    """장면의 video 값 → 패키지 기준 경로 (같은 파일인지 비교용). 파일이 없으면 적힌 값 그대로."""
    try:
        return _rel(resolve_video(video or "", schedule))
    except ValueError:
        return video or ""


def video_list(schedule: str) -> list[dict]:
    """
    시연 설정의 영상 목록 — 영상(파일)마다 한 줄로 묶고, 그 영상을 쓰는 장면을 단다.
    최근에 올린 영상이 위에 온다(파일 시각). 파일이 없는 영상은 맨 아래.
    """
    sc = package().scenario(schedule)
    groups: dict[str, dict] = {}
    for x in sc.scenes():
        key = _video_key(x.get("video"), schedule)
        g = groups.get(key)
        if g is None:
            try:
                path = resolve_video(x.get("video") or "", schedule)
                mtime, ok = path.stat().st_mtime, True
            except ValueError:
                mtime, ok = 0.0, False
            g = groups[key] = {"video": x.get("video") or "", "file": Path(key).name, "exists": ok, "mtime": mtime, "scenes": []}
        g["scenes"].append({"name": x.get("name"), "camera": x.get("camera"), "own": bool(x.get("polygons")),
                            "n": len(x.get("polygons") or [])})
    out = sorted(groups.values(), key=lambda g: (not g["exists"], -g["mtime"], g["file"]))
    for g in out:
        g["uploaded"] = datetime.fromtimestamp(g["mtime"]).strftime("%m-%d %H:%M") if g["exists"] else ""
    return out


# ====================================================================== 장면 읽기 · 쓰기
def _read(schedule: str) -> tuple[Path, dict]:
    sc = _scenario(schedule)
    p = sc.dir / "scenario.json"
    return p, json.loads(p.read_text(encoding="utf-8"))


def _write(p: Path, data: dict):
    """scenario.json 쓰기 — 사람이 읽는 파일이라 구역 좌표(points)는 한 줄로 둔다."""
    import copy
    d = copy.deepcopy(data)
    pts = []
    for sc in d.get("scenes", []):
        for poly in sc.get("polygons", []) or []:
            pts.append(json.dumps(poly.get("points", [])))
            poly["points"] = f"__PTS_{len(pts) - 1}__"
    text = json.dumps(d, ensure_ascii=False, indent=2)
    for i, t in enumerate(pts):
        text = text.replace(f'"__PTS_{i}__"', t)
    json.loads(text)                                   # 망가진 파일을 쓰지 않는다
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    tmp.replace(p)
    package_changed()


def _cam_polys(cam: dict) -> list[dict]:
    return [{"name": p.get("name"), "type": p.get("type"), "zone": p.get("zone") or cam.get("zone"),
             "label": p.get("label"), "points": p.get("points")}
            for p in cam.get("polygons", []) if p.get("space", "image") == "image"]


def options(schedule: str) -> dict:
    """구역 그리기 창이 쓰는 값 — 카메라(기본 구역) · 구역 목록 · 종류 · 이 스케줄의 장면."""
    pkg = package()
    sc = _scenario(schedule)
    cams = [{"id": c["camera_id"], "zone": c.get("zone"), "label": c.get("label") or "", "polygons": []}   # 카메라 기본 구역은 쓰지 않는다 (10/8)
            for c in pkg.cameras.values()]
    scenes = []
    for x in sc.scenes():
        own = bool(x.get("polygons"))
        scenes.append({"name": x.get("name"), "camera": x.get("camera"), "video": x.get("video"),
                       "own": own, "polygons": x["polygons"] if own else []})
    use = type_usage()
    return {"schedule": schedule, "title": sc.title, "zone": sc.zone,
            "cameras": cams, "scenes": scenes,
            "zones": [{"id": z, "name": zone_name(z)} for z in zones()],
            "types": [{"key": k, "used": len(use.get(k, [])), **v} for k, v in all_types().items()]}


def _clean_polys(polys: list, zs: set[str], cam_zone: str | None) -> list[dict]:
    """
    화면에서 그린 구역을 검사한다. 구역은 없어도 된다 (10/8) — 없으면(카메라 기본 구역은 쓰지 않는다)
    화면 전체를 카메라 구역으로 본다(사람 · 보호구 · 불꽃은 보고, 위험구역 · 작업 구역 규칙은 걸리지 않는다).
    """
    out, names = [], set()
    kinds = all_types()
    for i, p in enumerate(polys, 1):
        name = str(p.get("name") or "").strip()
        label = str(p.get("label") or "").strip()
        t = p.get("type")
        zone = p.get("zone") or cam_zone
        pts = p.get("points") or []
        who = f"{i}번 구역" + (f" ({name})" if name else "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,20}", name):
            raise ValueError(f"{who}: 이름은 영문 · 숫자 20자 이내 (영상 위에 적힌다 — 예: E1, W1)")
        if name in names:
            raise ValueError(f"구역 이름 ‘{name}’ 가 두 번 나온다")
        names.add(name)
        if t not in kinds:
            raise ValueError(f"{who}: 종류를 고른다" + (f" — ‘{t}’ 는 지워진 종류다" if t else ""))
        if zone not in zs:
            raise ValueError(f"{who}: 없는 구역 ‘{zone}’")
        if len(pts) < 3:
            raise ValueError(f"{who}: 점이 3개 이상이어야 한다")
        try:
            pts = [[round(min(1.0, max(0.0, float(x))), 4), round(min(1.0, max(0.0, float(y))), 4)] for x, y in pts]
        except (TypeError, ValueError):
            raise ValueError(f"{who}: 점 좌표가 잘못됐다") from None
        out.append({"name": name, "type": t, "zone": zone, "label": label or f"{name} {kinds[t]['label']}",
                    "space": "image", "points": pts})
    return out


def zone_note(polys: list[dict], cam: dict) -> str:
    """구역이 비었거나 위험구역이 없을 때 알려 줄 말 — 막지는 않는다 (10/8)."""
    if not polys:
        return "구역을 지정하지 않았다 — 화면 전체를 카메라 구역으로 보고 사람 · 보호구 · 불꽃만 본다(위험구역 · 작업 구역 규칙은 걸리지 않는다)"
    if not any(p.get("type") in HAZARD_TYPES for p in polys):
        return "위험구역(상시 · 작업 중)이 없다 — 불꽃은 점화원으로 확정되지 않는다(점화원 수동 입력은 된다)"
    return ""


def save_scene(body: dict) -> dict:
    """장면 저장 — 같은 이름(또는 고치기 전 이름 orig)이 있으면 바꾸고, 없으면 덧붙인다."""
    schedule = body.get("schedule") or ""
    p, data = _read(schedule)
    pkg = package()
    name = str(body.get("name") or "").strip()
    orig = str(body.get("orig") or "").strip()
    # 장면에는 시각을 적지 않는다 (10/8) — 영상은 실시간 관제의 ▶ 시작과 함께 지금 시각으로 돈다
    cam_id = body.get("camera") or ""
    video = str(body.get("video") or "").strip()
    if not name:
        raise ValueError("장면 이름을 적는다")
    if cam_id not in pkg.cameras:
        raise ValueError(f"없는 카메라 ‘{cam_id}’")
    resolve_video(video, schedule)
    cam = pkg.cameras[cam_id]
    polys = _clean_polys(body.get("polygons") or [], set(zones()), cam.get("zone"))
    scenes = data.setdefault("scenes", [])
    vkey = _video_key(video, schedule)
    clash = next((x for x in scenes if x.get("name") == name), None)
    if clash is not None and name != orig and _video_key(clash.get("video"), schedule) != vkey:
        raise ValueError(f"같은 이름의 장면이 이미 있다 — ‘{name}’ (다른 영상). 같은 영상이면 같은 이름으로 덮어쓴다")
    # 같은 이름 + 같은 영상이면 그 장면을 덮어쓴다. 고치던 장면(orig)의 이름을 바꿔 그쪽에 합치면 고치던 줄은 뺀다
    idx = next((i for i, x in enumerate(scenes) if x.get("name") == name), None)
    if idx is None and orig:
        idx = next((i for i, x in enumerate(scenes) if x.get("name") == orig), None)
    old = scenes[idx] if idx is not None else {}
    entry = {"name": name, "camera": cam_id, "video": video,
             "polygons": polys, "_구역": f"화면에서 그린 구역 ({datetime.now():%Y-%m-%d %H:%M})"}
    if idx is None:
        scenes.append(entry)
        verb = "등록"
    else:
        keep = {k: v for k, v in old.items() if k not in entry and k != "at" and not (k == "_설명" and old.get("video") != video)}
        scenes[idx] = {**entry, **keep}
        verb = "덮어씀" if old.get("name") != orig else "고침"
        if orig and orig != name:
            data["scenes"] = scenes = [x for x in scenes if x.get("name") != orig]
    _write(p, data)
    note = zone_note(polys, cam)
    return {"name": name, "msg": f"장면 ‘{name}’ {verb} — {cam_id} · 구역 {len(polys)}개. "
                                 "영상 목록의 ▶ 로 바로 틀 수 있다" + (f" · {note}" if note else "")}


def remove_scene(body: dict) -> dict:
    """장면을 목록에서 뺀다. 영상 파일은 지우지 않는다(videos/ 에 남는다)."""
    schedule = body.get("schedule") or ""
    name = str(body.get("name") or "").strip()
    p, data = _read(schedule)
    scenes = data.get("scenes", [])
    left = [x for x in scenes if x.get("name") != name]
    if len(left) == len(scenes):
        raise ValueError(f"없는 장면 ‘{name}’")
    data["scenes"] = left
    _write(p, data)
    return {"msg": f"장면 ‘{name}’ 을 목록에서 뺐다 — 영상 파일은 videos/ 에 그대로 있다"}


def _scene_names(schedule: str, key: str) -> list[str]:
    _, data = _read(schedule)
    return [x.get("name") for x in data.get("scenes", []) if _video_key(x.get("video"), schedule) == key]


def _sessions_for(schedule: str, names: list[str]) -> list[Path]:
    """그 장면(들)으로 돌린 실시간 세션 폴더 — session.json 첫 줄의 schedule · scene 으로 찾는다."""
    out = []
    for d in live_sessions():
        rows = read_jsonl(d / "session.json")
        m = rows[0] if rows else {}
        if m.get("schedule") == schedule and m.get("scene") and m.get("scene") in names:
            out.append(d)
    return out


def video_records(schedule: str, video: str) -> dict:
    """영상을 지우기 전에 — 이 영상으로 돌린 세션 수 · 관제 기록 수 (삭제 확인 창에 보인다)."""
    key = _video_key(video, schedule)
    names = _scene_names(schedule, key)
    ss = _sessions_for(schedule, names)
    return {"sessions": len(ss), "events": sum(len(read_jsonl(d / "events.jsonl")) for d in ss),
            "sids": [d.name for d in ss], "names": names}


def _remove_records(dirs: list[Path]) -> str:
    """
    세션 폴더(events · frames · clips · modes · session.json)를 지우고, 그 세션에서 문서 자동화로 넘어간 사본
    (monitor_events.jsonl 줄 · 복사한 프레임 · 인계 기록 줄)도 뺀다. 이미 문서(시정지시서 · 조사표 · 평가 …)에 쓰인 이벤트는 남긴다.
    """
    if not dirs:
        return ""
    from safety_docs.config import MONITOR_EVENTS, RECORD_DIR, ROOT, doc_file
    tags = tuple(f"({d.name})" for d in dirs)
    n_ev = sum(len(read_jsonl(d / "events.jsonl")) for d in dirs)
    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)
    # 문서에 쓰인 이벤트 번호 — 인계 사본 두 파일 밖의 기록에 번호가 나오면 쓰인 것으로 본다
    used_text = ""
    for f in RECORD_DIR.rglob("*"):
        if f.is_file() and f.suffix in (".jsonl", ".json") and f.name not in ("monitor_events.jsonl", "handoffs.jsonl"):
            try:
                used_text += f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                pass
    rows = read_jsonl(MONITOR_EVENTS)
    keep, drop, kept_used = [], 0, 0
    for r in rows:
        if str(r.get("source") or "").endswith(tags):
            eid = str(r.get("event_id") or "")
            if eid and f'"{eid}"' in used_text:
                kept_used += 1
                keep.append(r)
                continue
            fp = r.get("frame_path")
            if fp:
                doc_file(fp).unlink(missing_ok=True)
            drop += 1
            continue
        keep.append(r)
    if drop:
        _rewrite_jsonl(MONITOR_EVENTS, keep)
    hlog = RECORD_DIR / "handoffs.jsonl"
    heads = read_jsonl(hlog)
    left = [h for h in heads if not (str(h.get("source") or "").endswith(tags) and not (set(h.get("event_ids") or []) & {str(r.get("event_id")) for r in keep}))]
    if len(left) != len(heads):
        _rewrite_jsonl(hlog, left)
    msg = f" · 관제 기록도 지웠다 — 세션 {len(dirs)}개 · 기록 {n_ev}건" + (f" · 문서 자동화로 넘어간 사본 {drop}건" if drop else "")
    if kept_used:
        msg += f" (이미 문서에 쓰인 {kept_used}건은 문서 자동화에 남겼다)"
    return msg


def _rewrite_jsonl(p: Path, rows: list[dict]):
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    tmp.replace(p)


def remove_video(body: dict, busy: str | None = None) -> dict:
    """
    영상 하나를 목록에서 지운다 — 이 스케줄에서 그 영상을 쓰는 장면을 모두 빼고,
    다른 스케줄(시나리오)의 장면도 쓰지 않으면 영상 파일까지 지운다. busy = 지금 재생 중인 영상(지우지 않는다).
    records=true 면 그 영상으로 돌린 세션의 관제 기록도 지운다(기본은 남긴다 — 관제 기록은 추가 전용).
    """
    schedule = body.get("schedule") or ""
    video = str(body.get("video") or "").strip()
    if not video:
        raise ValueError("지울 영상을 고른다")
    key = _video_key(video, schedule)
    if busy and key == busy:
        raise ValueError("지금 재생 중인 영상이다 — 세션을 멈추거나 다른 장면으로 새 세션을 시작한 뒤 지운다")
    p, data = _read(schedule)
    scenes = data.get("scenes", [])
    gone = [x.get("name") for x in scenes if _video_key(x.get("video"), schedule) == key]
    rec_dirs = _sessions_for(schedule, gone) if body.get("records") else []
    if gone:
        data["scenes"] = [x for x in scenes if _video_key(x.get("video"), schedule) != key]
        _write(p, data)
    pkg = package()
    others = [f"{k} ‘{x.get('name')}’" for k in pkg.scenario_keys() for x in pkg.scenario(k).scenes()
              if _video_key(x.get("video"), k) == key]
    msg = f"영상 {Path(key).name} — 장면 {len(gone)}개를 뺐다" + (f" ({', '.join(gone)})" if gone else "")
    try:
        path = resolve_video(video, schedule)
    except ValueError:
        path = None
    if others:
        msg += f". 다른 스케줄의 장면({', '.join(others[:3])}{' …' if len(others) > 3 else ''})이 쓰고 있어 파일은 남겼다"
    elif path is not None and path.parent.resolve() == videos_dir().resolve():
        path.unlink()
        package_changed()
        msg += " · 영상 파일도 지웠다"
    elif path is not None:
        msg += f". 파일은 videos/ 밖({_rel(path)})이라 지우지 않았다"
    msg += _remove_records(rec_dirs)
    return {"msg": msg, "removed": gone, "sids": [d.name for d in rec_dirs]}
