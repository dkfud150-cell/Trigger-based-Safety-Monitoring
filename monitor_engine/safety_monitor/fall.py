"""
쓰러짐 — 사람 박스가 옆으로 길게 누운 채 거의 안 움직이면 쓰러짐으로 본다 (10/13).

사람 추적(yolo26n)과 따로 돈다. 쓰러짐은 몸 전체가 박스에 들어와야 보여서 더 큰 모델(weights, 기본 yolo26m)을 쓰는데,
그 모델을 프레임마다 돌리면 사람 박스가 느려진다. 그래서 every_s 초에 한 번만 본다.

  look(frame, t) : 큰 모델로 사람을 찾아 '누움'(가로/세로 >= ratio) 박스를 따라간다.
                   지난번 자리에서 몸 높이의 still 비율보다 덜 움직였으면 정지 — 누움 + 정지가 hold_s 초 이어지면 쓰러짐
  mark(persons)  : 추적 중인 사람 중 박스 가운데가 쓰러짐 박스 안에 있으면 p.fallen = True

설정은 detect.json 의 "fall". 시연 영상(z8_blind_B_injured)에서 누운 사람 1.5~1.6, 난간 뒤에서 숙인 사람 1.0~1.25 라 ratio 1.4.
"""
from __future__ import annotations

from pathlib import Path


class FallJudge:
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        self.weights = cfg.get("weights", "yolo26m.pt")
        self.imgsz = cfg.get("imgsz", 960)
        self.conf = cfg.get("conf", 0.35)
        self.every_s = cfg.get("every_s", 1.0)
        self.ratio = cfg.get("ratio", 1.4)
        self.still = cfg.get("still", 0.3)
        self.hold_s = cfg.get("hold_s", 3.0)
        self.model = None
        self.last_t = None
        self.lying = []     # 누운 박스들 [{"box": (x1, y1, x2, y2), "secs": 누운 채 멈춰 있던 시간}]
        self.fallen = []    # 쓰러짐이 확정된 박스들

    def due(self, t: float) -> bool:
        return self.last_t is None or t - self.last_t >= self.every_s or t < self.last_t

    def look(self, frame, t: float):
        if self.model is None:
            from ultralytics import YOLO
            from .package import MODEL_DIR
            p = MODEL_DIR / self.weights
            self.model = YOLO(str(p if p.exists() else self.weights))   # models/ 에 없으면 자동으로 받는다
        dt = 0.0 if self.last_t is None else min(2 * self.every_s, max(0.0, t - self.last_t))
        self.last_t = t
        res = self.model.predict(frame, classes=[0], imgsz=self.imgsz, conf=self.conf, verbose=False)[0]

        new = []
        for x1, y1, x2, y2 in res.boxes.xyxy.tolist():
            w, h = x2 - x1, max(1.0, y2 - y1)
            if w / h < self.ratio:
                continue                                  # 누워 있지 않다
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            secs = 0.0
            for old in self.lying:                        # 지난번에도 이 자리에 누워 있었나
                ox1, oy1, ox2, oy2 = old["box"]
                if abs(cx - (ox1 + ox2) / 2) + abs(cy - (oy1 + oy2) / 2) < h * self.still:
                    secs = old["secs"] + dt
                    break
            new.append({"box": (x1, y1, x2, y2), "secs": secs})
        self.lying = new
        self.fallen = [d["box"] for d in new if d["secs"] >= self.hold_s]

    def mark(self, persons):
        fallen = self.fallen                              # 다른 스레드가 바꿔도 이번 판정은 같은 목록으로
        for p in persons:
            x1, y1, x2, y2 = p.xyxy
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            p.fallen = any(a <= cx <= c and b <= cy <= d for a, b, c, d in fallen)
