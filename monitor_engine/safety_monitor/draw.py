"""
영상 위 최소 표시 — 폴리곤 · 사람(접지점) · 검출 박스 · 윗줄 상태.
증거 클립과 --show 창에 쓴다. 관제 화면(대시보드)은 이 폴더의 일이 아니다.
OpenCV 는 한글을 못 그려서 윗줄은 영문 약어로 쓴다.
"""
from __future__ import annotations

import cv2
import numpy as np

from .detector import person_no
from .judge import RANK
from .modes import active_poly_types
from .zones import HAZARD_TYPES, label_tag

try:                                    # 사람 꺽쇠(코너) 표시 — roboflow/supervision 의 BoxCornerAnnotator. 없으면 같은 모양을 직접 그린다
    import supervision as sv
except ImportError:  # pragma: no cover
    sv = None

OK_BGR, BAD_BGR, HOLD_BGR = (70, 160, 70), (40, 40, 220), (0, 150, 230)   # 보호구 착용 초록 · 미착용 빨강 · 판단 보류 주황


def _corner_len(xyxy) -> int:
    x1, y1, x2, y2 = xyxy
    return int(max(6, min(18, 0.22 * min(x2 - x1, y2 - y1))))


def person_corners(vis: np.ndarray, boxes: list, cols: list) -> np.ndarray:
    """사람 박스를 네 귀퉁이 꺽쇠로만 그린다 — 이름표 없음. 어두운 테두리를 먼저 깔아 밝은 배경에서도 보이게."""
    if not boxes:
        return vis
    if sv is not None:
        det = sv.Detections(xyxy=np.array(boxes, dtype=float), class_id=np.arange(len(boxes)))
        n = int(np.median([_corner_len(b) for b in boxes]))
        dark = sv.BoxCornerAnnotator(color=sv.Color(20, 20, 20), thickness=4, corner_length=n + 1)
        pal = sv.ColorPalette([sv.Color(int(c[2]), int(c[1]), int(c[0])) for c in cols])
        top = sv.BoxCornerAnnotator(color=pal, thickness=2, corner_length=n, color_lookup=sv.ColorLookup.INDEX)
        return top.annotate(dark.annotate(vis, det), det)
    for b, col in zip(boxes, cols):
        x1, y1, x2, y2 = (int(v) for v in b)
        n = _corner_len(b)
        for c, t in (((20, 20, 20), 4), (col, 2)):
            for (px, py, dx, dy) in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
                cv2.line(vis, (px, py), (px + dx * n, py), c, t, cv2.LINE_AA)
                cv2.line(vis, (px, py), (px, py + dy * n), c, t, cv2.LINE_AA)
    return vis

LEVEL_EN = {"정상": "NORMAL", "주의": "CAUTION", "경보": "ALARM", "최고 경보": "CRITICAL"}
LEVEL_BGR = {"정상": (60, 150, 60), "주의": (30, 170, 200), "경보": (20, 125, 230), "최고 경보": (40, 40, 210)}


def draw(frame: np.ndarray, eng, zones, camera_zone: str | None) -> np.ndarray:
    vis = frame.copy()
    present = {p.type for p in zones.polys}
    on = {z: active_poly_types(eng.rules, ms, present) for z, ms in eng.modes.items()}
    zones.draw(vis, {p.name: p.type in on.get(p.zone, {"hazard"}) for p in zones.polys})
    # 사람 = 네 귀퉁이 꺽쇠만(이름표 없음, 10/7). 색: 위험구역 안 = 빨강, 작업 · 출입 제한 구역 안 = 주황, 그 밖 = 흰색.
    # 아래 점 = 판정에 쓰는 발 위치. 보호구(안전모 · 안전조끼)는 꺽쇠 안쪽 위에 작은 이름표 — 착용 초록 · 미착용 빨강.
    boxes, cols = [], []
    for p in eng.persons:
        types = {q.type for q in p.polys}
        cols.append((40, 40, 230) if types & set(HAZARD_TYPES) else (0, 150, 255) if types & {"work", "restricted"} else (245, 245, 245))
        boxes.append(p.xyxy)
    vis = person_corners(vis, boxes, cols)
    for p, col in zip(eng.persons, cols):
        x1, y1, x2, y2 = (int(v) for v in p.xyxy)
        cv2.circle(vis, ((x1 + x2) // 2, y2), 4, (20, 20, 20), -1)
        cv2.circle(vis, ((x1 + x2) // 2, y2), 3, col, -1)
        # 번호 + 신뢰도 (10/8) — 꺽쇠 바깥 왼쪽 위에 'P1 0.44'. 번호는 탐지 오탐 목록과 같다
        no = person_no(p)
        label_tag(vis, (f"{no} " if no else "") + f"{p.conf:.2f}", (x1, max(0, y1 - 15)), (60, 60, 60))
        y = y1 + 3
        if p.fallen:                                   # 쓰러짐 확정 (10/13) — 빨간 이름표를 맨 위에
            _, y = label_tag(vis, "FALLEN", (x1 + 3, y), BAD_BGR)
            y += 1
        for k, v in p.ppe.items():
            if v is None and (y2 - y1) < 40:          # 너무 작은 사람은 표시도 하지 않는다
                continue
            name = k.upper()
            txt, col = (name, OK_BGR) if v else (f"{name} ?", HOLD_BGR) if v is None else (f"NO {name}", BAD_BGR)
            if p.ppe_conf.get(k) is not None:               # 판정 근거가 된 보호구 모델 점수 (10/8)
                txt += f" {p.ppe_conf[k]:.2f}"
            _, y = label_tag(vis, txt, (x1 + 3, y), col)
            y += 1
    for name, dets in eng.objects.items():
        for d in dets:
            x1, y1, x2, y2 = (int(v) for v in d.xyxy)
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 90, 255), 2)
            label_tag(vis, f"{name.upper()} {d.conf:.2f}", (x1, max(0, y1 - 15)), (0, 90, 255))
    # 오른쪽 위 — 사람 수와 보호구 미착용 수
    n = len(eng.persons)
    txt = f"PERSON {n}"
    off_any = 0
    for k in getattr(eng, "ppe_items", {}):
        off = sum(1 for p in eng.persons if p.ppe.get(k) is False)
        off_any += off
        txt += f"  NO {k.upper()} {off}"
    (tw, _), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.36, 1)
    label_tag(vis, txt, (vis.shape[1] - tw - 12, 28), BAD_BGR if off_any else (60, 60, 60))
    zone = camera_zone or (zones.zones()[0] if zones.zones() else "")
    level, ls, table = eng.zone_level(zone)
    txt = f"{eng.now:%H:%M:%S}  {zone}  {LEVEL_EN[level]}" + (f" row {ls.row}" if ls and level != "정상" else "")
    area = eng.area_alert(zone) if hasattr(eng, "area_alert") else None      # 구역 규칙(위험구역 진입) 경보가 더 높으면 그걸 쓴다
    if area and RANK[area["level"]] > RANK[level]:
        level = area["level"]
        txt = f"{eng.now:%H:%M:%S}  {zone}  {LEVEL_EN[level]}  HAZARD-ENTRY"
    if any(p.fallen for p in eng.persons):             # 쓰러짐 (10/13) — 다른 경보가 더 높아도 늘 붙인다
        level = "최고 경보"
        txt += "  WORKER-DOWN"
    txt += f"  modes {len([m for m, s in eng.modes.get(zone, []) if s is not None])}"
    if any(g.blocked for g in eng.gates.get(zone, [])):
        txt += "  GATE-BLOCKED"
    cv2.rectangle(vis, (0, 0), (vis.shape[1], 22), LEVEL_BGR[level], -1)
    cv2.putText(vis, txt, (8, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (255, 255, 255), 1, cv2.LINE_AA)
    if RANK[level] >= 2:
        cv2.rectangle(vis, (0, 0), (vis.shape[1] - 1, vis.shape[0] - 1), LEVEL_BGR[level], 6)
    return vis
