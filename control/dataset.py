"""
오탐 · 미탐 이미지 로그 (10/8) - 나중에 탐지 모델을 다시 학습할 때 쓸 자료

관제자가 실시간 관제에서 탐지 오탐을 고르거나 미탐을 등록하면, 그 시각의 영상 프레임을 같이 남긴다.
처리 방식(기록만 · 판정 반영 · 증거 저장)과 상관없이 영상이 돌고 있으면 늘 남긴다.

  control/records/dataset/fp/      탐지 오탐 - <번호>_raw.jpg   표시 없는 원본 프레임 (학습용)
                                               <번호>_view.jpg  관제 화면 그대로 (박스 · 이름표 - 사람이 볼 때)
                                               <번호>_crop.jpg  고른 박스 둘레를 잘라 낸 것
                                               <번호>.json      박스(원본 좌표 · 0~1 비율) · 탐지 종류 · 신뢰도 · 사유 · 처리
  control/records/dataset/missed/  미탐     - <번호>_raw.jpg · <번호>_view.jpg · <번호>.json
                                               놓친 물체의 박스는 없다 - 라벨링 도구에서 그려 넣는다 (json 의 needs_box)

어느 프레임을 남기나 (10/8 오후 고침) - '저장을 누른 순간'이 아니라 '오탐 · 미탐이 난 순간'
  창을 여는 순간 그 화면을 고정해 둔다(Pins). 창 맨 위 그림이 그 고정본이고, 저장하면 그 그림이 그대로 남는다.
    탐지 오탐  고른 탐지가 마지막으로 잡힌 시각(seen_t)의 원본 · 관제 화면 - 창을 여는 순간 탐지마다 고정
    미탐      '일어난 시각'이 창을 연 시각 그대로면 고정본, 고쳤으면 그 시각에 가장 가까운 원본(최근 RAW_KEEP_S 초)
  창을 오래 열어 두거나 사유를 길게 적어도 바뀌지 않는다. 버퍼에도 없는 옛 시각이면 json 의 gap_s 에 차이를 적는다.
"""
from __future__ import annotations

import json
import re
import threading
from collections import deque
from pathlib import Path

from .common import RECORD_DIR

DATASET_DIR = RECORD_DIR / "dataset"
RAW_KEEP_S = 60.0          # 원본 프레임을 들고 있는 시간 (초)
CROP_PAD = 0.25            # 잘라 낼 때 박스 둘레 여유 (박스 크기 비율)


class RawFrames:
    """탐지에 들어간 원본 프레임(표시 없음)을 최근 RAW_KEEP_S 초만 JPEG 로 들고 있는다."""

    def __init__(self):
        self.buf: deque = deque()
        self._lock = threading.Lock()      # 탐지 스레드가 넣고 화면 요청이 읽는다

    def clear(self):
        with self._lock:
            self.buf.clear()

    def push(self, t: float, frame):
        import cv2
        ok, enc = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            return
        with self._lock:
            self.buf.append((t, enc.tobytes(), frame.shape[1], frame.shape[0]))
            while self.buf and self.buf[0][0] < t - RAW_KEEP_S:
                self.buf.popleft()

    def near(self, t: float | None):
        """t 에 가장 가까운 프레임 (t, jpeg, w, h). t 가 없으면 마지막 것."""
        with self._lock:
            if not self.buf:
                return None
            if t is None:
                return self.buf[-1]
            return min(self.buf, key=lambda x: abs(x[0] - t))


class Pins:
    """
    창을 여는 순간의 프레임 고정본. pin(frames) 로 번호를 받고, 저장할 때 그 번호로 꺼낸다.
    frames = {열쇠: (원본 (t, jpeg, w, h) 또는 None, 관제 화면 jpeg 또는 None)} - 열쇠는 'now' 와 탐지 ref
    최근 KEEP 개 · TTL_S 초까지만 들고 있는다.
    """
    KEEP, TTL_S = 8, 900

    def __init__(self):
        self.items: dict[str, dict] = {}
        self._n = 0
        self._lock = threading.Lock()

    def pin(self, frames: dict, made_at: str = "", boxes: dict | None = None, times: dict | None = None) -> str:
        import time
        with self._lock:
            self._n += 1
            sid = f"S{int(time.time())}-{self._n}"
            self.items[sid] = {"wall": time.time(), "made_at": made_at, "frames": frames,
                               "boxes": boxes or {}, "times": times or {}}
            now = time.time()
            keep = sorted(((k, v) for k, v in self.items.items() if now - v["wall"] <= self.TTL_S),
                          key=lambda kv: kv[1]["wall"])[-self.KEEP:]
            self.items = dict(keep)
            return sid

    def get(self, sid: str | None, key: str = "now"):
        with self._lock:
            it = self.items.get(sid or "")
            if not it:
                return None
            return it["frames"].get(key) or it["frames"].get("now")

    def made_at(self, sid: str | None) -> str:
        with self._lock:
            return (self.items.get(sid or "") or {}).get("made_at", "")

    def view(self, sid: str | None) -> bytes | None:
        f = self.get(sid, "now")
        return f[1] if f else None

    def image(self, sid: str | None, key: str, kind: str) -> bytes | None:
        """창에 미리 보여 줄 그림 - 저장하면 남을 그대로. kind = view(관제 화면) · raw(원본) · crop(박스 둘레)."""
        f = self.get(sid, key or "now")
        if not f:
            return None
        raw, view = f
        if kind == "view":
            return view or (raw[1] if raw else None)
        if kind == "raw":
            return raw[1] if raw else None
        if kind == "crop":
            with self._lock:
                box = ((self.items.get(sid or "") or {}).get("boxes") or {}).get(key)
            return _crop(raw[1], box) if raw and box else None
        return None

    def time_of(self, sid: str | None, key: str) -> str:
        with self._lock:
            it = self.items.get(sid or "") or {}
            return (it.get("times") or {}).get(key) or it.get("made_at", "")


def _write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)          # cv2.imwrite 는 윈도 한글 경로에서 실패해 바이트로 쓴다


def _crop(jpeg: bytes, box, pad: float = CROP_PAD) -> bytes | None:
    import cv2
    import numpy as np
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    x1, y1 = max(0, int(x1 - bw * pad)), max(0, int(y1 - bh * pad))
    x2, y2 = min(w, int(x2 + bw * pad)), min(h, int(y2 + bh * pad))
    if x2 <= x1 or y2 <= y1:
        return None
    ok, enc = cv2.imencode(".jpg", img[y1:y2, x1:x2], [cv2.IMWRITE_JPEG_QUALITY, 92])
    return enc.tobytes() if ok else None


def save(kind: str, rid: str, *, raw, view: bytes | None, t_event: float | None, meta: dict,
         box=None) -> dict:
    """
    한 건을 남긴다. kind = 'fp' | 'missed'. raw = RawFrames.near() 결과(없으면 None), view = 관제 화면 JPEG.
    돌려주는 것 = 기록에 덧붙일 {"images": {...}} (경로는 control/records 기준).
    """
    d = DATASET_DIR / kind
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", rid)
    out: dict = {}
    label = {"id": rid, "kind": kind, **meta}
    if raw is not None:
        t, jpeg, w, h = raw
        _write(d / f"{safe}_raw.jpg", jpeg)
        out["raw"] = f"dataset/{kind}/{safe}_raw.jpg"
        label.update(image=f"{safe}_raw.jpg", width=w, height=h, frame_t=round(t, 2),
                     gap_s=None if t_event is None else round(abs(t - t_event), 2))
        if box:
            x1, y1, x2, y2 = (float(v) for v in box)
            label["box"] = [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)]
            label["box_norm"] = [round((x1 + x2) / 2 / w, 5), round((y1 + y2) / 2 / h, 5),
                                 round((x2 - x1) / w, 5), round((y2 - y1) / h, 5)]     # YOLO 모양 (중심 x, 중심 y, 너비, 높이)
            c = _crop(jpeg, box)
            if c:
                _write(d / f"{safe}_crop.jpg", c)
                out["crop"] = f"dataset/{kind}/{safe}_crop.jpg"
    if view:
        _write(d / f"{safe}_view.jpg", view)
        out["view"] = f"dataset/{kind}/{safe}_view.jpg"
    if kind == "missed":
        label["needs_box"] = True       # 놓친 물체 자리는 사람이 라벨링 도구에서 그린다
    (d / f"{safe}.json").parent.mkdir(parents=True, exist_ok=True)
    (d / f"{safe}.json").write_text(json.dumps({**label, "files": out}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"images": out} if out else {}


def image_path(rel: str) -> Path | None:
    """화면이 부르는 이미지 경로(dataset/fp/xxx.jpg)를 실제 파일로 - dataset 폴더 밖은 열지 않는다."""
    m = re.fullmatch(r"dataset/(fp|missed)/([A-Za-z0-9_.-]+\.jpg)", rel or "")
    if not m:
        return None
    p = DATASET_DIR / m.group(1) / m.group(2)
    return p if p.exists() else None
