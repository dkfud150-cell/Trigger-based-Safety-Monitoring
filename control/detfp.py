"""
실시간 객체 탐지 오탐 처리 (10/8)

이벤트 로그의 오탐 표시는 '이미 남은 기록'에 표시를 다는 것이다. 여기는 그보다 앞 단계 -
실시간 관제 영상에서 지금 잡히고 있는 탐지 하나(사람 · 보호구 미착용 · 불꽃 같은 물체)를 관제자가
"이건 잘못 잡은 것"이라고 고르면, 그 탐지를 판정에서 뺀다.

판정을 어떻게 할지는 고를 때 정한다 (10/8 오후, ACTIONS). 기본값은 '기록만 - 판정은 그대로'.
  사람          기록만 · 사람에서 빼기(사람이 아님) · 사람 수는 두고 구역 판정만 빼기(위치 오차)
  보호구 미착용  기록만 · 판단 보류로 · 착용으로 고치기
  물체(불꽃 등)  기록만 · 같은 자리를 1 · 5 · 10분 동안 빼기
                 - 자리 기준이라 진짜 불꽃이 같은 자리에 나도 그동안은 빠진다. 그래서 시간을 짧게 두고, 화면에서 바로 해제할 수 있다
  그 구역이 경보 · 최고 경보인데 판정을 바꾸는 쪽을 고르면 한 번 더 확인을 받는다 (기록에 그때 단계를 남긴다)

빠진 탐지는 영상 위에도 그리지 않는다(판정에 안 쓰는 것을 그려 두면 화면과 판정이 달라 보인다).
다른 탐지의 표시 모양은 그대로다.

고를 대상 (10/8 오후) - 지금 잡힌 것만이 아니라 최근 RECENT_S 초 안에 잡혔던 것까지 고른다.
  실시간 영상이라 창을 여는 사이 사람이 화면 밖으로 나가 "지금 화면에 없다"로 저장이 안 됐다.
  창을 열 때 본 목록을 화면이 그대로 들고 있다가 보내므로, 그새 사라져도 저장된다(다시 나타나면 그때부터 빠진다).
시각 - 기록에 '탐지된 시각(seen_at · 영상 위치)'과 '오탐으로 고른 시각(ts)'을 같이 남긴다.

기록  control/records/det_false_positives.jsonl (추가 전용 - 취소도 새 줄)
      히트맵 · 통계의 오탐 · 미탐 칸에 '탐지 오탐'으로, 오탐 사유는 이벤트 로그 오탐과 같은 고정 목록(quality.FP_REASONS)
"""
from __future__ import annotations

import time
from datetime import datetime

from .common import RECORD_DIR, append_jsonl, load_config, read_jsonl

DET_FP_LOG = RECORD_DIR / "det_false_positives.jsonl"
DEFAULTS = {"object_ttl_s": 300, "object_iou": 0.3, "recent_s": 30}



def _tag() -> str:
    """데이터 공간 태그 (10/14) — 공간끼리 번호가 겹치지 않게. 사용자 실행 데이터는 빈 값."""
    from dataspace import id_tag
    return id_tag()

def _cfg() -> dict:
    try:
        return {**DEFAULTS, **(load_config().get("det_fp") or {})}
    except Exception:  # noqa: BLE001 - 설정 파일이 깨져도 관제는 돈다
        return dict(DEFAULTS)


def _iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def _center_in(d, box, pad: float = 0.2) -> bool:
    w, h = box[2] - box[0], box[3] - box[1]
    cx, cy = (d[0] + d[2]) / 2, (d[1] + d[3]) / 2
    return box[0] - w * pad <= cx <= box[2] + w * pad and box[1] - h * pad <= cy <= box[3] + h * pad


def _pkey(p):
    """사람을 잇는 번호 - 추적 번호, 없으면 보호구 판정용 번호(key)."""
    return p.track_id if p.track_id is not None else p.key


def _where(box, width) -> str:
    """화면 어디쯤인가 - 목록에서 영상 속 사람을 찾기 쉽게."""
    if not width:
        return ""
    cx = (box[0] + box[2]) / 2 / width
    return "왼쪽" if cx < 1 / 3 else "가운데" if cx < 2 / 3 else "오른쪽"


# ============================================================
# 지금 화면의 탐지 목록 - 화면의 '탐지 오탐' 창이 고를 대상
# ============================================================
def current_targets(eng, ppe_labels: dict | None = None) -> list[dict]:
    """엔진이 지금 들고 있는 탐지(이미 오탐 처리된 것은 빠진 뒤)를 고를 수 있는 목록으로."""
    from safety_monitor.detector import person_no
    ppe_labels = ppe_labels or {}
    width = getattr(getattr(eng, "zones", None), "w", 0)
    out = []
    for p in getattr(eng, "persons", []) or []:
        k = _pkey(p)
        if k is None:
            continue
        box = [round(float(v), 1) for v in p.xyxy]
        no = person_no(p) or "사람"                                     # 영상 위 꺽쇠 이름표와 같은 번호 (P1 …)
        where = f" · {_where(box, width)}" if width else ""
        out.append({"ref": f"person:{k}", "kind": "person", "det": "person", "key": k, "no": no,
                    "label": f"{no} 사람{where} · 신뢰도 {p.conf:.2f}", "conf": round(float(p.conf), 2), "xyxy": box})
        for item, v in (p.ppe or {}).items():
            if v is False:                              # 미착용으로 잡힌 것만 - 경보를 만드는 쪽
                lab = ppe_labels.get(item, item)
                c = (p.ppe_conf or {}).get(item)
                out.append({"ref": f"ppe:{k}:{item}", "kind": "ppe", "det": item, "key": k, "item": item, "no": no,
                            "label": f"{no} {lab} 미착용{where}" + (f" · 신뢰도 {c:.2f}" if c is not None else ""),
                            "conf": c, "xyxy": box})
    for oname, dets in (getattr(eng, "objects", {}) or {}).items():
        for i, d in enumerate(dets):
            box = [round(float(v), 1) for v in d.xyxy]
            out.append({"ref": f"object:{oname}:{i}", "kind": "object", "det": oname, "name": oname,
                        "label": f"{'불꽃' if oname == 'flame' else oname}" + (f" · {_where(box, width)}" if width else "") + f" · 신뢰도 {d.conf:.2f}",
                        "conf": round(float(d.conf), 2), "xyxy": box})
    return out


def from_client(d: dict | None) -> dict | None:
    """
    화면이 창을 열 때 본 탐지(dets 한 줄)를 그대로 돌려보낸 것 - 서버의 최근 목록에서도 빠졌을 때 쓴다.
    판정에서 빼는 데 쓰는 칸(kind · key · item · name · xyxy)만 모양을 확인해 받는다.
    """
    if not isinstance(d, dict) or d.get("kind") not in ("person", "ppe", "object"):
        return None
    try:
        box = [float(v) for v in d.get("xyxy") or []]
    except (TypeError, ValueError):
        return None
    if len(box) != 4:
        return None
    t = {"ref": str(d.get("ref") or ""), "kind": d["kind"], "xyxy": box, "conf": d.get("conf"),
         "label": str(d.get("label") or "")[:80], "seen_at": str(d.get("seen_at") or "")[:19] or None,
         "seen_t": d.get("seen_t") if isinstance(d.get("seen_t"), (int, float)) else None}
    if d["kind"] in ("person", "ppe"):
        try:
            t["key"] = int(d.get("key"))
        except (TypeError, ValueError):
            return None
    if d["kind"] == "person":
        t["det"] = "person"
    elif d["kind"] == "ppe":
        t["item"] = t["det"] = str(d.get("item") or "")
        if not t["item"]:
            return None
    else:
        t["name"] = t["det"] = str(d.get("name") or "")
        if not t["name"]:
            return None
    return t


# ============================================================
# 최근에 잡혔던 탐지 - 창을 여는 사이 사라진 것도 고를 수 있게 (10/8 오후)
# ============================================================
class RecentTargets:
    def __init__(self):
        self.items: dict[str, dict] = {}

    def clear(self):
        self.items = {}

    def update(self, targets: list[dict], now: datetime, video_t: float | None):
        """탐지가 끝날 때마다 부른다. 같은 ref 는 마지막으로 잡힌 시각 · 박스로 덮는다."""
        wall = time.time()
        cur = set()
        for t in targets:
            cur.add(t["ref"])
            self.items[t["ref"]] = {**t, "seen_at": now.isoformat(timespec="seconds"),
                                    "seen_t": None if video_t is None else round(video_t, 1), "_wall": wall}
        for ref, t in self.items.items():
            t["_now"] = ref in cur
        keep = float(_cfg()["recent_s"])
        self.items = {r: t for r, t in self.items.items() if wall - t["_wall"] <= keep}
        # 물체는 프레임마다 번호가 바뀐다 - 지금 화면에 없는 물체 번호는 남기지 않는다(같은 불꽃이 여러 줄로 쌓이지 않게)
        self.items = {r: t for r, t in self.items.items() if t["kind"] != "object" or t["_now"]}

    def get(self, ref: str) -> dict | None:
        t = self.items.get(ref)
        return {k: v for k, v in t.items() if not k.startswith("_")} if t else None

    def list(self) -> list[dict]:
        """지금 잡힌 것 먼저, 그다음 방금 사라진 것(몇 초 전)."""
        wall = time.time()
        def order(t):                   # 지금 잡힌 것 먼저 -> 사람 번호(P1, P2 …) 순 -> 사람 · 보호구 · 물체
            no = str(t.get("no") or "")
            n = int(no[1:]) if no[:1] == "P" and no[1:].isdigit() else 9999
            return (not t["_now"], n, {"person": 0, "ppe": 1, "object": 2}.get(t["kind"], 3), t["ref"])
        rows = sorted(self.items.values(), key=order)
        return [{**{k: v for k, v in t.items() if not k.startswith("_")}, "now": t["_now"],
                 "ago": 0 if t["_now"] else int(wall - t["_wall"])} for t in rows]


# ============================================================
# 판정 처리 방식 (10/8 오후) - 오탐으로 고를 때 판정을 어떻게 할지 탐지 종류마다 고른다
#   기본값은 판정을 건드리지 않는 '기록만'. 진짜 위험을 놓치는 쪽(미탐)이 더 위험하기 때문이다
# ============================================================
ACTIONS = {
    "person": [("record", "기록만 - 판정은 그대로"),
               ("remove", "사람에서 빼기 - 사람이 아니다 (영상 끝까지)"),
               ("zone_only", "사람 수는 두고 구역 판정(진입 · 보호구)만 빼기 - 위치 · 경계 오차 (영상 끝까지)")],
    "ppe": [("record", "기록만 - 판정은 그대로"),
            ("hold", "판단 보류로 - 미착용으로 세지 않는다 (영상 끝까지)"),
            ("worn", "착용으로 고치기 - 착용으로 센다 (영상 끝까지)")],
    "object": [("record", "기록만 - 판정은 그대로"),
               ("mute_1", "같은 자리를 1분 동안 빼기"),
               ("mute_5", "같은 자리를 5분 동안 빼기"),
               ("mute_10", "같은 자리를 10분 동안 빼기")],
}


def action_label(kind: str, action: str) -> str:
    return dict(ACTIONS.get(kind, [])).get(action, action)


def changes_judgment(action: str) -> bool:
    return action != "record"


# ============================================================
# 세션마다 하나 - 켜져 있는 오탐 처리
# ============================================================
class DetFalsePositives:
    def __init__(self):
        self.rules: list[dict] = []

    def clear(self):
        self.rules = []

    def active(self) -> list[dict]:
        now = time.time()
        self.rules = [r for r in self.rules if r.get("until") is None or r["until"] > now]
        return [{k: v for k, v in r.items() if k != "until"} | {"left_s": None if r.get("until") is None else int(r["until"] - now)}
                for r in self.rules]

    def add(self, target: dict, row: dict) -> dict | None:
        """판정을 바꾸는 처리만 규칙으로 든다. '기록만'은 규칙이 없다."""
        action = row.get("action", "record")
        if not changes_judgment(action):
            return None
        cfg = _cfg()
        rule = {"dfp_id": row["dfp_id"], "kind": target["kind"], "det": target["det"], "label": target["label"],
                "key": target.get("key"), "item": target.get("item"), "name": target.get("name"),
                "xyxy": target.get("xyxy"), "until": None, "action": action, "action_label": row.get("action_label", ""),
                "seen_at": row.get("seen_at"), "seen_t": row.get("seen_t"), "ts": row["ts"]}
        if target["kind"] == "object":
            minutes = int(action.split("_")[1]) if action.startswith("mute_") else int(cfg["object_ttl_s"]) // 60
            rule["until"] = time.time() + minutes * 60
            rule["iou"] = float(cfg["object_iou"])
        self.rules.append(rule)
        return rule

    def remove(self, dfp_id: str) -> bool:
        n = len(self.rules)
        self.rules = [r for r in self.rules if r["dfp_id"] != dfp_id]
        return len(self.rules) != n

    def apply(self, persons: list, objects: dict) -> tuple[list, dict]:
        """탐지 결과에 오탐 처리(고른 판정 방식)를 적용한다. 엔진에 넣기 바로 앞에서 부른다."""
        if not self.rules:
            return persons, objects
        self.active()                                   # 시간이 지난 물체 처리는 여기서 떨어진다
        drop = {r["key"] for r in self.rules if r["kind"] == "person" and r["action"] == "remove"}
        nozone = {r["key"] for r in self.rules if r["kind"] == "person" and r["action"] == "zone_only"}
        ppe = {(r["key"], r["item"]): r["action"] for r in self.rules if r["kind"] == "ppe"}
        keep = []
        for p in persons:
            k = _pkey(p)
            if k is not None and k in drop:
                continue
            if k is not None and k in nozone:
                p.no_zone = True                        # 엔진이 구역(폴리곤) 판정을 하지 않는다 - 사람 수에는 든다
            for item in list((p.ppe or {}).keys()):
                act = ppe.get((k, item))
                if act and p.ppe.get(item) is False:
                    p.ppe[item] = True if act == "worn" else None     # 착용으로 고치기 · 판단 보류
                    (p.ppe_conf or {}).pop(item, None)
            keep.append(p)
        objs = {}
        orules = [r for r in self.rules if r["kind"] == "object"]
        for name, dets in objects.items():
            rs = [r for r in orules if r["name"] == name and r.get("xyxy")]
            objs[name] = [d for d in dets
                          if not any(_iou(d.xyxy, r["xyxy"]) >= r["iou"] or _center_in(d.xyxy, r["xyxy"]) for r in rs)]
        return keep, objs


# ============================================================
# 기록 (추가 전용)
# ============================================================
def record(target: dict, *, by: str, cat: str, note: str, zone: str, ts: datetime, action: str = "record",
           sid: str = "", scene: str = "", video_t: float | None = None, confirmed_alarm: str = "") -> dict:
    rows = read_jsonl(DET_FP_LOG)
    n = sum(1 for r in rows if not r.get("undo") and not r.get("update")) + 1
    row = {"dfp_id": f"DF-{ts:%m%d%H%M%S}-{_tag()}{n:03d}", "ts": ts.isoformat(timespec="seconds"), "zone": zone,
           "det": target["det"], "kind": target["kind"], "target": target["label"], "conf": target.get("conf"),
           "xyxy": target.get("xyxy"), "cat": cat, "note": note, "by": by,
           "action": action, "action_label": action_label(target["kind"], action),
           "scope": action_label(target["kind"], action),                        # 예전 기록과 같은 칸 이름
           "confirmed_alarm": confirmed_alarm,                                      # 경보 중 판정을 끈 경우 그때 단계
           "seen_at": target.get("seen_at") or ts.isoformat(timespec="seconds"),    # 탐지된 시각 (고른 시각은 ts)
           "seen_t": target.get("seen_t", video_t),                                  # 탐지된 영상 위치 (초)
           "sid": sid, "scene": scene, "video_t": video_t,
           "recorded_at": datetime.now().isoformat(timespec="seconds"), "undo": False}
    append_jsonl(DET_FP_LOG, row)
    return row


def undo(dfp_id: str, by: str) -> dict:
    return append_jsonl(DET_FP_LOG, {"dfp_id": dfp_id, "undo": True, "by": by,
                                     "recorded_at": datetime.now().isoformat(timespec="seconds")})


def add_update(dfp_id: str, data: dict) -> dict:
    """나중에 붙는 것(이미지 경로 등)을 같은 번호로 덧붙인다 - 원래 줄은 고치지 않는다."""
    return append_jsonl(DET_FP_LOG, {"dfp_id": dfp_id, "update": True, **data,
                                     "recorded_at": datetime.now().isoformat(timespec="seconds")})


def list_records() -> list[dict]:
    """취소되지 않은 탐지 오탐 기록 (최신순). update 줄은 같은 번호에 합친다."""
    out: dict[str, dict] = {}
    for r in read_jsonl(DET_FP_LOG):
        if r.get("update"):
            if r["dfp_id"] in out:
                out[r["dfp_id"]] = {**out[r["dfp_id"]], **{k: v for k, v in r.items() if k not in ("update", "recorded_at")}}
            continue
        if r.get("undo"):
            out.pop(r["dfp_id"], None)
        else:
            out[r["dfp_id"]] = r
    return sorted(out.values(), key=lambda r: r["ts"], reverse=True)
