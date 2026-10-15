"""
영상 규칙 — 모드가 켜져 있을 때 영상으로 보는 규칙 (모드의 checks).

종류 (checks[].type):
  no_entry    : polygons 안에 사람이 있다                     — 배관 랙 하부 진입
  min_persons : polygons 안 인원이 min 보다 적다 (0명은 제외) — 2인 1조, 화재감시자
  max_persons : polygons 안 인원이 max 보다 많다              — 인원 상한
  no_ppe      : polygons(없으면 그 구역 전부) 안에 보호구(item: helmet · vest)를 안 갖춘 사람이 있다 — 보호구 모델이 붙었을 때만 (10/7)
  no_helmet   : no_ppe 의 item=helmet 과 같다
공통: when (조건어 — 맞을 때만 본다), dwell_s (그만큼 이어져야 위반), level, violation,
      shadow_when_off (모드가 꺼져 있어도 무음 기록으로 남긴다)
새 종류가 필요하면 CHECK_TYPES 에 함수 하나를 더한다.
"""
from __future__ import annotations

from .conditions import Ctx, count_people, evaluate


def _types(ck: dict) -> set[str]:
    p = ck.get("polygons", ["work"])
    return set(p if isinstance(p, list) else [p])


def _no_entry(ck, zone, eng):
    out = []
    want = _types(ck)
    for p in eng.persons:
        polys = [q for q in p.polys if q.type in want and q.zone == zone]
        if polys:
            key = p.track_id if p.track_id is not None else "-"
            out.append((key, f"{polys[0].label} 안에 사람" + (f" #{p.track_id}" if p.track_id is not None else ""), p.track_id))
    return out


def _min_persons(ck, zone, eng):
    n = count_people(eng.store, zone, sorted(_types(ck)))
    if 0 < n < ck["min"]:
        return [("zone", f"{zone} {'/'.join(sorted(_types(ck)))} {n}명 < {ck['min']}명", None)]
    return []


def _max_persons(ck, zone, eng):
    n = count_people(eng.store, zone, sorted(_types(ck)))
    if n > ck["max"]:
        return [("zone", f"{zone} {'/'.join(sorted(_types(ck)))} {n}명 > {ck['max']}명", None)]
    return []


def _no_ppe(ck, zone, eng):
    out = []
    item = ck.get("item", "helmet")
    name = eng.ppe_items.get(item, item)
    want = set(ck["polygons"]) if ck.get("polygons") else None
    for p in eng.persons:
        if p.ppe.get(item) is not False:
            continue
        polys = [q for q in p.polys if q.zone == zone and (want is None or q.type in want)]
        if polys:
            key = p.track_id if p.track_id is not None else "-"
            out.append((key, f"{name} 미착용" + (f" #{p.track_id}" if p.track_id is not None else "") + f" — {polys[0].label}", p.track_id))
    return out


def _no_helmet(ck, zone, eng):
    return _no_ppe({**ck, "item": "helmet"}, zone, eng)


def _fallen(ck, zone, eng):
    """쓰러짐이 확정된 사람 (fall.py, 10/13). 폴리곤 밖이면 그 카메라 구역의 사람으로 본다."""
    out = []
    cam = eng.zones.camera_zone if eng.zones else None
    for p in eng.persons:
        if not p.fallen:
            continue
        if any(q.zone == zone for q in p.polys) or (not p.polys and cam == zone):
            key = p.track_id if p.track_id is not None else p.key
            out.append((key, "작업자 쓰러짐" + (f" #{p.track_id}" if p.track_id is not None else "")
                        + " — 누운 채 움직임 없음", p.track_id))
    return out


CHECK_TYPES = {"no_entry": _no_entry, "min_persons": _min_persons, "max_persons": _max_persons, "no_helmet": _no_helmet,
               "no_ppe": _no_ppe, "fallen": _fallen}


def check_hits(ck: dict, zone: str, eng) -> list[tuple]:
    if "when" in ck and not evaluate(ck["when"], Ctx(eng, zone, eng.now)).ok:
        return []
    return CHECK_TYPES[ck["type"]](ck, zone, eng)
