"""
탐지 — 사람 · 불꽃 · 안전모.

  PersonDetector : 공개 YOLO(COCO person) + ByteTrack 추적. 추가 학습 없음.
  PPEChecker     : 사람마다 몸을 잘라 키운 뒤 보호구 모델을 돌린다 → 안전모 · 안전조끼 착용 / 미착용 (10/7)
  FlameDetector  : backend = color (학습 없이 색 · 밝기 · 움직임) / yolo (불꽃 클래스 가중치) / off
                   color 는 사람 박스 · 작업복 같은 색 면을 빼고 본다 (노랑 · 주황 작업복 오탐 방지)
  Persistence    : N프레임 연속이어야 불꽃으로 확정 (오탐 억제)

가스 · 압력 · 배기 · 맹판 설치는 영상으로 보지 않는다 — CSV 와 버튼으로 들어온다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np


@dataclass
class Det:
    xyxy: tuple[float, float, float, float]
    conf: float
    cls: str
    track_id: int | None = None
    polys: list = field(default_factory=list)   # zones.Zones.locate 결과
    ppe: dict = field(default_factory=dict)      # 사람만 — {보호구: True 착용 · False 미착용 · None 안 봄(너무 작음)}
    ppe_conf: dict = field(default_factory=dict) # 사람만 — {보호구: 판정 근거가 된 보호구 모델 점수 (착용이면 착용 점수, 맨머리면 맨머리 점수, 안 보였으면 없음)} (10/8)
    key: int | None = None                       # 사람만 — 보호구 판정을 이어 붙이는 번호 (추적 번호, 없으면 앞 프레임 가까운 사람의 번호)
    no: int | None = None                        # 사람만 — 화면에 보이는 사람 번호 P1 · P2 … (영상마다 처음 본 순서, 10/8)
    fallen: bool = False                         # 사람만 — 쓰러짐 확정 (fall.py, 10/13)


def person_no(p: Det) -> str:
    """
    화면 · 탐지 오탐 목록에 쓰는 사람 번호 (10/8). 영상마다 처음 본 순서로 P1 · P2 · P3 …
    추적 번호(#42)나 큰 임시 번호 대신 짧은 번호로 — 영상 위 이름표와 오탐 목록이 같은 번호라 누가 누군지 바로 맞춰 본다.
    """
    if p.no is not None:
        return f"P{p.no}"
    if p.track_id is not None:
        return f"#{p.track_id}"
    return ""


# ---------------------------------------------------------------------- 사람
class PersonDetector:
    def __init__(self, cfg: dict, model_dir: Path | None = None):
        from ultralytics import YOLO   # 여기서 불러야 replay.py 가 ultralytics 없이도 돈다

        self.cfg = cfg
        self.model = None
        errors = []
        for w in (cfg.get("weights"), cfg.get("fallback_weights")):
            if not w:
                continue
            p = Path(w)
            if model_dir and not p.is_absolute() and (model_dir / p).exists():
                p = model_dir / p
            try:
                self.model = YOLO(str(p))
                self.weights = str(p)
                break
            except Exception as e:  # noqa: BLE001 — 가중치 이름이 버전마다 달라서 다음 후보로 넘어간다
                errors.append(f"{w}: {e}")
        if self.model is None:
            raise RuntimeError("사람 탐지 모델을 불러오지 못했습니다\n" + "\n".join(errors))
        self.use_track = True

    def _make_tracker(self):
        """ByteTrack 을 직접 만든다 — model.track() 은 두 번 잇달아 맞춘 사람만 돌려줘서, 탐지가 느릴 때 걷는 사람이 화면에서 빠졌다 (10/7)."""
        from ultralytics.trackers.byte_tracker import BYTETracker
        from ultralytics.utils.checks import check_yaml
        try:
            from ultralytics.utils import YAML
            args = YAML.load(check_yaml(self.cfg.get("tracker", "bytetrack.yaml")))
        except ImportError:                                   # 예전 ultralytics
            from ultralytics.utils import yaml_load
            args = yaml_load(check_yaml(self.cfg.get("tracker", "bytetrack.yaml")))
        from types import SimpleNamespace
        args = SimpleNamespace(**args)
        try:
            return BYTETracker(args=args, frame_rate=30)
        except TypeError:
            return BYTETracker(args)

    def __call__(self, frame: np.ndarray) -> list[Det]:
        """
        사람을 찾고 추적 번호를 붙인다. 찾은 사람은 전부 돌려준다 — 추적기가 아직 확정하지 못한 사람(빨리 걷는 사람 등)은
        추적 번호 없이(None) 나온다. 예전 model.track() 은 그런 사람을 빼서, 탐지가 초당 1~2번일 때 걷는 사람 꺽쇠가 사라졌다.
        """
        kw = dict(classes=[0], conf=self.cfg.get("conf", 0.35), imgsz=self.cfg.get("imgsz", 640),
                  verbose=False, device=self.cfg.get("device"))
        res = self.model.predict(frame, **kw)[0]
        b = res.boxes
        if b is None:
            return []
        xyxy, conf = b.xyxy.tolist(), b.conf.tolist()
        ids: list[int | None] = [None] * len(xyxy)
        if self.use_track:
            try:
                if getattr(self, "tracker", None) is None:
                    self.tracker = self._make_tracker()
                for row in self.tracker.update(b.cpu().numpy(), frame):
                    k = int(row[7])                              # [x1, y1, x2, y2, 추적 번호, 점수, 클래스, 탐지 번호]
                    if 0 <= k < len(ids):
                        ids[k] = int(row[4])
            except Exception as e:  # noqa: BLE001 — lap 미설치 등. 추적 없이 프레임 단위로
                print(f"[안내] 추적을 끄고 프레임 단위로 판정합니다: {e}")
                self.use_track = False
        out = [Det(tuple(x), float(c), "person", i) for x, c, i in zip(xyxy, conf, ids)]
        self._keys(out)
        return out

    def _keys(self, dets: list[Det]):
        """
        보호구 판정을 이어 붙일 번호(key). 추적 번호가 있으면 그것, 없으면 앞 프레임에서 가장 가까운 사람(발 위치가 키의 0.8 안)의 번호,
        그것도 없으면 새 번호. 화면 · 기록에 보이는 추적 번호(track_id)는 그대로 둔다.
        """
        prev = getattr(self, "_prev", [])
        used = set()
        for d in dets:
            if d.track_id is not None:
                d.key = d.track_id
                used.add(d.key)
        for d in dets:
            if d.key is not None:
                continue
            x1, y1, x2, y2 = d.xyxy
            cx, cy, h = (x1 + x2) / 2, y2, y2 - y1
            best = None
            for k, (px, py, ph) in prev:
                dist = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
                if k not in used and dist < 0.8 * max(h, ph) and (best is None or dist < best[1]):
                    best = (k, dist)
            if best:
                d.key = best[0]
            else:
                self._next = getattr(self, "_next", 1_000_000) + 1      # 추적 번호와 겹치지 않는 큰 번호
                d.key = self._next
            used.add(d.key)
        nos = self.__dict__.setdefault("_nos", {})          # key -> 화면 번호 (이 영상에서 처음 본 순서)
        for d in dets:
            d.no = nos.setdefault(d.key, len(nos) + 1)
        self._prev = [(d.key, (d.xyxy[0] + d.xyxy[2]) / 2, d.xyxy[3], d.xyxy[3] - d.xyxy[1]) for d in dets]
        self._prev = [(k, (x, y, h)) for k, x, y, h in self._prev]


# ---------------------------------------------------------------------- 불꽃
class FlameDetector:
    def __init__(self, cfg: dict, roi_mask_fn=None, root: Path | None = None):
        """
        roi_mask_fn(scale) → uint8 마스크(작업 해상도). color 방식에서 roi='hazard' 일 때 hazard 폴리곤 근처만 본다.
        root: 가중치 상대 경로의 기준 폴더 (monitor/).
        """
        self.cfg = cfg
        self.backend = cfg.get("backend", "color")
        self.roi_mask_fn = roi_mask_fn
        self.prev = None
        self._roi = None
        self.model = None
        self.last_mask = None      # color 방식의 마지막 불티 후보 마스크 (조정할 때 들여다보는 용)
        self.last_scale = 1.0
        self.last: list[Det] = []  # 마지막 결과 — 똑같은 프레임이 다시 오면 그대로 돌려준다
        if self.backend == "yolo":
            from ultralytics import YOLO
            y = cfg["yolo"]
            p = Path(y["weights"])
            if root and not p.is_absolute():
                p = root / p
            if not p.exists():
                raise FileNotFoundError(f"불꽃 가중치가 없습니다: {p}  (detect.json 의 flame.backend 를 'color' 로 두면 학습 없이 돈다)")
            self.model = YOLO(str(p))
            names = {i: n.lower() for i, n in self.model.names.items()}
            want = {c.lower() for c in y.get("classes", [])}
            self.class_ids = [i for i, n in names.items() if n in want] or None
            print(f"[불꽃] {p.name} 클래스: {[names[i] for i in (self.class_ids or names)]}")

    def __call__(self, frame: np.ndarray, persons: list[Det] | None = None) -> list[Det]:
        """persons: 같은 프레임의 사람 탐지 결과. color 방식은 사람 박스 안을 불티 후보에서 뺀다(작업복 · 안전모)."""
        if self.backend == "off":
            return []
        if self.backend == "yolo":
            y = self.cfg["yolo"]
            r = self.model.predict(frame, conf=y.get("conf", 0.3), imgsz=y.get("imgsz", 640),
                                   classes=self.class_ids, verbose=False)[0]
            if r.boxes is None:
                return []
            return [Det(tuple(b), float(c), "flame") for b, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist())]
        return self._color(frame, persons or [])

    def _color(self, frame: np.ndarray, persons: list[Det]) -> list[Det]:
        """
        그라인더 불티 = 작고 밝고 따뜻한 색(또는 흰빛)이면서 프레임마다 자리가 바뀌는 점들.
        정지된 조명 · 반사는 '움직임' 조건에서 빠진다. 첫 프레임은 비교 대상이 없어서 항상 0.

        노랑 · 주황 작업복과 안전모도 밝고 따뜻한 색이라, 사람이 움직이면 옷 가장자리가 불티 후보로 잡힌다.
        그래서 후보를 고른 뒤 아래를 뺀다 (값은 detect.json flame.color).
          skip_person      사람 박스 안 (사람 탐지가 있을 때)
          solid_*          채도 높은 따뜻한 색 '면'(작업복 · 안전모 · 주황 설비) — 불티는 가늘고 작아 면이 되지 않는다.
                           단 하얗게 타는 심지(hot_*)가 섞인 면은 불길로 보고 남긴다
          white_near_warm  흰빛은 따뜻한 색 바로 옆일 때만 — 흰 안전모 · 장갑 · 반사띠 · 조명을 빼고 불티 심지만 남긴다
          cluster_blobs    한 무리 안에 점이 이만큼 — 여기저기 흩어진 한두 점을 모아 불티로 치지 않는다
          max_motion_ratio 화면 대부분이 한꺼번에 바뀌면(장면 전환 · 섬광 · 카메라 흔들림) 그 프레임은 건너뛴다
          skip_repeat      앞 프레임과 똑같은 프레임(생성 영상에 흔하다)은 앞 결과를 그대로 쓴다
        """
        c = self.cfg["color"]
        H, W = frame.shape[:2]
        ww = int(c.get("work_width", 640))
        s = min(1.0, ww / W)
        small = cv2.resize(frame, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA) if s < 1 else frame
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        if self.prev is None or self.prev.shape != gray.shape:
            self.prev = gray
            self.last = []
            return []
        diff = cv2.absdiff(gray, self.prev)
        if c.get("skip_repeat", True) and float(diff.mean()) < 0.5:
            return list(self.last)
        self.prev = gray
        moving = (diff >= c["motion_min"]).astype(np.uint8) * 255
        mr = c.get("max_motion_ratio")
        if mr and np.count_nonzero(moving) > mr * moving.size:
            self.last_mask, self.last_scale, self.last = np.zeros_like(moving), s, []
            return []

        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        h, sat, val = cv2.split(hsv)
        warm_hue = (h <= c["hue_max"]) | (h >= c["hue_wrap_min"])
        warm = warm_hue & (sat >= c["s_min"]) & (val >= c["v_min"])
        if c.get("s_max"):                      # 10/8 — 형광 주황 작업복(채도 190~220)은 빼고 불티(채도 120~150)는 남긴다
            warm &= sat <= c["s_max"]
        white = (val >= c["white_v_min"]) & (sat <= c["white_s_max"])
        wn = int(c.get("white_near_warm", 0))
        if wn > 0:
            white &= cv2.dilate(warm.astype(np.uint8), _disk(2 * wn + 1)) > 0
        color = (warm | white).astype(np.uint8) * 255

        moving = cv2.dilate(moving, np.ones((3, 3), np.uint8))
        cand = cv2.bitwise_and(color, moving)

        if c.get("roi", "frame") == "hazard" and self.roi_mask_fn is not None:
            if self._roi is None or self._roi.shape != cand.shape:
                self._roi = self.roi_mask_fn(s)
            if self._roi is not None:
                cand = cv2.bitwise_and(cand, self._roi)

        if persons and c.get("skip_person", True):
            pad = float(c.get("person_pad", 0.08))
            ph, pw = cand.shape
            for p in persons:
                x0, y0, x1, y1 = p.xyxy
                dx, dy = (x1 - x0) * pad, (y1 - y0) * pad
                cand[max(0, int((y0 - dy) * s)):min(ph, int((y1 + dy) * s) + 1),
                     max(0, int((x0 - dx) * s)):min(pw, int((x1 + dx) * s) + 1)] = 0

        k = int(c.get("solid_px", 0))
        if k >= 3 and np.any(cand):
            sup = self._solid(warm_hue, sat, val, c, k)
            # 10/8 — 면 빼기는 사람 둘레에서만 한다(solid_near_person). 작업복 · 안전모는 사람에게 붙어 있다.
            # 화면 전체에 걸면 그라인더 불티 다발(촘촘한 주황 부채꼴)까지 '면'으로 보고 지워서, 불티는 못 잡고 폭발만 잡혔다.
            if persons and c.get("solid_near_person", True):
                near = np.zeros_like(sup)
                pad = float(c.get("solid_person_pad", 0.25))
                ph, pw = near.shape
                for p in persons:
                    x0, y0, x1, y1 = p.xyxy
                    dx, dy = (x1 - x0) * pad, (y1 - y0) * pad
                    near[max(0, int((y0 - dy) * s)):min(ph, int((y1 + dy) * s) + 1),
                         max(0, int((x0 - dx) * s)):min(pw, int((x1 + dx) * s) + 1)] = 255
                sup = cv2.bitwise_and(sup, near)
            cand = cv2.bitwise_and(cand, cv2.bitwise_not(sup))

        self.last_mask, self.last_scale = cand, s
        self.last = self._blobs(cand, c, s)
        return self.last

    def _solid(self, warm_hue, sat, val, c, k) -> np.ndarray:
        """채도 높은 따뜻한 색 면(작업복 · 안전모 · 주황 설비)을 칠한 마스크. 하얗게 타는 심지가 섞인 면(불길)은 뺀다."""
        surf = (warm_hue & (sat >= c.get("solid_s_min", 110)) & (val >= c.get("solid_v_min", 100))).astype(np.uint8) * 255
        surf = cv2.morphologyEx(surf, cv2.MORPH_OPEN, _disk(k))
        n, lab, st, _ = cv2.connectedComponentsWithStats(surf, connectivity=8)
        if n <= 1:
            return surf
        hot = (val >= c.get("hot_v_min", 250)) & (sat <= c.get("hot_s_max", 130))
        cnt = np.bincount(lab[hot].ravel(), minlength=n)
        fire = cnt / np.maximum(st[:, cv2.CC_STAT_AREA], 1) >= c.get("hot_ratio", 0.1)
        fire[0] = True
        sup = np.where(fire[lab], 0, 255).astype(np.uint8)
        pad = int(c.get("solid_pad", 5))
        return cv2.dilate(sup, _disk(2 * pad + 1)) if pad > 0 else sup

    @staticmethod
    def _blobs(cand: np.ndarray, c: dict, s: float) -> list[Det]:
        n, lab, stats, _ = cv2.connectedComponentsWithStats(cand, connectivity=8)
        big = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= c["min_blob_px"]]
        keep = np.isin(lab, big).astype(np.uint8) * 255 if big else np.zeros_like(cand)
        total = int(np.count_nonzero(keep))
        if len(big) < c.get("min_blobs", 3) or total < c["min_total_ratio"] * cand.size:
            return []
        # 흩어진 불티를 한 덩어리로 묶는다
        k = int(c.get("cluster_px", 25))
        grp = cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        n2, lab2, st2, _ = cv2.connectedComponentsWithStats(grp, connectivity=8)
        per = np.zeros(n2, int)                      # 무리마다 점이 몇 개인가
        for i in big:
            x, y = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
            ys, xs = np.nonzero(lab[y:y + stats[i, cv2.CC_STAT_HEIGHT], x:x + stats[i, cv2.CC_STAT_WIDTH]] == i)
            per[lab2[y + ys[0], x + xs[0]]] += 1
        need = int(c.get("cluster_blobs", 1))
        out = []
        for i in range(1, n2):
            x, y, w, hh, _a = st2[i]
            px = int(np.count_nonzero(keep[y:y + hh, x:x + w]))
            if px < c["min_blob_px"] * c.get("min_blobs", 3) or per[i] < need:
                continue
            conf = min(1.0, px / (0.002 * cand.size) + 0.3)
            out.append(Det((x / s, y / s, (x + w) / s, (y + hh) / s), conf, "flame"))
        return out


def _disk(k: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


def run_objects(dets: dict, frame: np.ndarray, persons: list[Det]) -> dict[str, list[Det]]:
    """물체 탐지를 돌린다. 불꽃 탐지에는 사람 박스를 넘겨 작업복 · 안전모를 불티로 잡지 않게 한다."""
    return {n: (d(frame, persons=persons) if isinstance(d, FlameDetector) else d(frame)) for n, d in dets.items()}


class Persistence:
    """
    최근 window 프레임 안에 on_frames 번 검출이면 켜고, off_frames 프레임 연속 미검출이면 끈다.
    window 를 주지 않으면(= on_frames) 예전처럼 'N프레임 연속'. 10/8 — 그라인더 불티는 깜빡이며 튀어서
    연속 5프레임이 잘 안 채워졌다. 불꽃은 패키지 detect.json persistence.window_frames 로 '최근 몇 번 중 몇 번'을 쓴다.
    """

    def __init__(self, on_frames: int = 5, off_frames: int = 15, window_frames: int | None = None):
        self.on_n, self.off_n = on_frames, off_frames
        self.win = max(on_frames, int(window_frames or on_frames))
        self.recent: list[bool] = []
        self.hit = 0
        self.miss = 0
        self.on = False
        self.max_streak = 0

    def update(self, detected: bool) -> bool:
        self.recent = (self.recent + [bool(detected)])[-self.win:]
        if detected:
            self.hit += 1
            self.miss = 0
            self.max_streak = max(self.max_streak, self.hit)
            if sum(self.recent) >= self.on_n:
                self.on = True
        else:
            self.miss += 1
            self.hit = 0
            if self.miss >= self.off_n:
                self.on = False
        return self.on


# ---------------------------------------------------------------------- 그 밖의 물체 (패키지가 정한다)
class YoloObjectDetector:
    """
    detect.json 의 extra 에 적은 가중치로 물체를 찾는다 (사다리 · 보호구 · 적치물 …).
    결과는 이름(name)으로 엔진에 들어가고, 규칙에서 {"detect": 이름} 으로 쓴다.
    """

    def __init__(self, spec: dict, root: Path | None = None):
        from ultralytics import YOLO
        p = Path(spec["weights"])
        if root and not p.is_absolute():
            p = root / p
        if not p.exists():
            raise FileNotFoundError(f"[{spec['name']}] 가중치가 없습니다: {p}")
        self.spec = spec
        self.model = YOLO(str(p))
        names = {i: n.lower() for i, n in self.model.names.items()}
        want = {c.lower() for c in spec.get("classes", [])}
        self.class_ids = [i for i, n in names.items() if n in want] or None

    def __call__(self, frame: np.ndarray) -> list[Det]:
        r = self.model.predict(frame, conf=self.spec.get("conf", 0.4), imgsz=self.spec.get("imgsz", 640),
                               classes=self.class_ids, verbose=False)[0]
        if r.boxes is None:
            return []
        return [Det(tuple(b), float(c), self.spec["name"]) for b, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist())]


# ---------------------------------------------------------------------- 보호구 — 안전모 · 안전조끼 (10/7)
class PPEChecker:
    """
    사람 박스마다 몸 전체를 (조금 넓혀) 잘라 키운 뒤 보호구 모델을 한 번 돌린다 — 안전모와 안전조끼를 같이 본다.
    화면 전체에 한 번 돌리면 멀리 있는 사람의 작은 머리 · 조끼를 놓쳐서(시험 영상에서 4명 중 2명), 사람마다 따로 본다.

      items      보호구 목록 — {키: {label, classes, region}}. region: head = 잘라낸 그림 위쪽(head_ratio)에서만,
                 body = 몸통(위 15% ~ 아래 85%)에서만 인정. classes 는 모델의 클래스 이름 (여러 모델 이름을 같이 적어 둔다)
      착용 / 미착용  그 영역에 그 보호구가 conf 이상으로 잡혔다 / 안 잡혔다 — 사람 수 − 착용 = 미착용
      안 봄      사람 박스가 min_person_px 보다 작다 — 판단하지 않는다(미착용으로 세지 않는다)
    추적 번호가 있는 사람은 최근 window_s 초의 판정을 모아 정한다 (10/7 오후 — 예전 '한 번 보이면 2초 착용'은 모델이 맨머리를
    안전모로 한 번 잘못 본 것만으로 2초 동안 착용이 돼서, 맨머리 사람이 '안전모 미착용 0명'으로 나왔다).
      머리 쪽(no_classes 가 있는 것)  안전모로 본 횟수가 맨머리로 본 횟수보다 많으면 착용, 적으면 미착용 — 다수결.
                                     머리가 아예 안 보였으면 '판단 보류' (absent_as_off: true 면 예전처럼 미착용으로 센다)
      몸통                           그 사이 한 번이라도 보였으면 착용 (조끼는 뒤돌면 안 보이니까)
      아무것도 안 보였으면            confirm_n 번 넘게 쌓인 뒤 미착용 · 그 전에는 '판단 보류'(None)
    color(보호구마다, 선택): 몸통에 형광 주황 · 연두 같은 고시인성 색이 min_ratio 이상이면 모델이 못 잡아도 착용으로 본다 (10/7 —
      공장 영상에서 모델이 주황 조끼를 'NO-Safety Vest' 로 잘못 본 경우가 41% 였다. 색을 같이 보면 4% 로 준다).
    결과는 p.ppe = {키: True/False/None}.
    """

    def __init__(self, cfg: dict, root: Path | None = None):
        from ultralytics import YOLO
        self.cfg = cfg
        # 보호구마다 다른 모델을 쓸 수 있다 — items.<키>.weights 가 있으면 그 모델, 없으면 ppe.weights (10/7: 안전모는 SHWD 로 학습한 전용 모델)
        self.models: dict[str, dict] = {}            # 가중치 경로 → {model, cls_of, neg_of}
        self.items: dict[str, dict] = {}
        for key, it in cfg.get("items", {}).items():
            if key.startswith("_"):
                continue
            p = Path(it.get("weights") or cfg.get("weights", "models/helmet.pt"))
            if root and not p.is_absolute():
                p = root / p
            if not p.exists():
                raise FileNotFoundError(f"보호구 가중치가 없습니다: {p} ({key})")
            m = self.models.get(str(p))
            if m is None:
                m = self.models[str(p)] = {"model": YOLO(str(p)), "cls_of": {}, "neg_of": {}, "name": p.name}
            names = {i: str(n).lower() for i, n in m["model"].names.items()}
            want = {c.lower() for c in it.get("classes", [])}
            nowant = {c.lower() for c in it.get("no_classes", [])}       # 반대 증거 (예: NO-Hardhat · head = 맨머리)
            ids = [i for i, n in names.items() if n in want]
            no_ids = [i for i, n in names.items() if n in nowant]
            if not ids:
                raise ValueError(f"[{key}] 보호구 클래스를 모델 {p.name} 에서 못 찾았다 — 모델 클래스: {list(names.values())}. detect.json ppe.items.{key}.classes 를 맞춘다")
            self.items[key] = {"ids": ids, "no_ids": no_ids, "region": it.get("region", "body"), "color": it.get("color"),
                               "bright": it.get("bright")}
            m["cls_of"].update({i: key for i in ids})
            m["neg_of"].update({i: key for i in no_ids})
        if not self.items:
            raise ValueError("detect.json ppe.items 에 보호구가 없다")
        self.models = {k: m for k, m in self.models.items() if m["cls_of"]}
        self.weights = " + ".join(m["name"] for m in self.models.values())
        self.hist: dict[tuple[str, int], list] = {}    # (보호구, 추적 번호) → [(영상 시각, +1 착용 · -1 반대 증거 · 0 안 보임)]
        self.cache: dict[int, tuple[float, dict]] = {}  # 추적 번호 → (마지막으로 본 영상 시각, 판정) — 매번 다 보지 않는다
        self.cache_conf: dict[int, dict] = {}           # 추적 번호 → 마지막 판정의 모델 점수 (10/8 — 이벤트 기록 · 화면의 신뢰도)

    def __call__(self, frame: np.ndarray, persons: list[Det], t: float = 0.0) -> None:
        c = self.cfg
        H, W = frame.shape[:2]
        # 속도 (10/7) — 보호구 모델은 사람 수만큼 도는데 사람이 많으면 한 번에 1초 가까이 걸려, 영상 위 꺽쇠가 사람을 못 따라갔다.
        # 같은 사람(추적 번호)은 recheck_s 초마다 한 번만, 한 번에 max_per_round 명까지만 다시 보고, 그 사이에는 마지막 판정을 쓴다.
        # 다시 볼 사람과 박스가 겹치는 옆 사람도 같이 본다 — 옆 사람 안전모를 내 것으로 세지 않게(아래 2번)
        every, cap = c.get("recheck_s", 1.0), int(c.get("max_per_round", 6))
        due = [p for p in persons if p.key is None or t - self.cache.get(p.key, (-1e9, {}))[0] >= every]
        due.sort(key=lambda p: self.cache.get(p.key, (-1e9, {}))[0] if p.key is not None else -2e9)
        pick = due[:cap]
        for q in list(pick):
            for p in persons:
                if p not in pick and _overlap(p.xyxy, q.xyxy):
                    pick.append(p)
        for p in persons:
            if p not in pick:
                p.ppe = dict(self.cache[p.key][1]) if p.key in self.cache else {k: None for k in self.items}
                p.ppe_conf = dict(self.cache_conf.get(p.key, {}))
        crops, who = [], []
        for p in pick:
            x1, y1, x2, y2 = p.xyxy
            w, h = x2 - x1, y2 - y1
            p.ppe = {k: None for k in self.items}
            p.ppe_conf = {}
            if h < c.get("min_person_px", 40):
                continue
            cx1, cx2 = max(0, int(x1 - 0.2 * w)), min(W, int(x2 + 0.2 * w))
            cy1, cy2 = max(0, int(y1 - 0.1 * h)), min(H, int(y2 + 0.05 * h))
            if cx2 - cx1 < 4 or cy2 - cy1 < 4:
                continue
            crops.append(frame[cy1:cy2, cx1:cx2])
            who.append((p, cx1, cy1))
        if not crops:
            return
        runs = [(m, m["model"].predict(crops, conf=min(0.25, c.get("conf", 0.35)), imgsz=c.get("imgsz", 320),
                                       classes=list(m["cls_of"]) + list(m["neg_of"]), verbose=False, device=c.get("device")))
                for m in self.models.values()]
        conf, head, win = c.get("conf", 0.35), c.get("head_ratio", 0.35), c.get("window_s", 2.5)
        need = max(1, int(c.get("confirm_n", 3)))
        absent_off = bool(c.get("absent_as_off", False))
        # 1) 잘라낸 그림에서 찾은 보호구를 원래 화면 좌표로 돌리고, 그 사람 자기 몸 위치에 있는 것만 후보로 둔다.
        #    잘라낼 때 옆으로 넓혀서, 바로 옆 사람의 안전모가 같이 들어온다 (10/7 PPE.mp4 — 맨머리 2명이 옆 사람 안전모로 '착용'이 됐다)
        #      head  보호구 가운데가 그 사람 박스 가로 안 · 세로로 박스 위 15% 위 ~ 위에서 head_ratio(0.35) 사이
        #      body  보호구 가운데가 그 사람 박스 가로 안 · 세로로 위 15% ~ 위 80% 사이
        #    머리 쪽은 '착용'(Hardhat)과 '맨머리'(NO-Hardhat) 후보 가운데 그 사람 머리 기준점에 가장 가까운 하나로 정한다 —
        #    사람 박스가 뒤에 선 사람까지 덮어도 남의 안전모가 내 맨머리를 이기지 못하게
        cand = []                                          # (사람 번호, 보호구, 점수, 화면 좌표 박스, 기준점까지 거리, 착용 증거인가)
        for m, res in runs:
            for i, ((p, ox, oy), r) in enumerate(zip(who, res)):
                if r.boxes is None:
                    continue
                x1, y1, x2, y2 = p.xyxy
                w, h = x2 - x1, y2 - y1
                for k, sc, b in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist()):
                    pos = int(k) in m["cls_of"]
                    key = m["cls_of"].get(int(k)) or m["neg_of"].get(int(k))
                    if key is None:
                        continue
                    fb = (b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy)
                    mx, my = (fb[0] + fb[2]) / 2, (fb[1] + fb[3]) / 2
                    if not (x1 <= mx <= x2):
                        continue
                    if self.items[key]["region"] == "head":
                        if not (y1 - 0.15 * h <= my <= y1 + head * h):
                            continue
                        ax, ay = (x1 + x2) / 2, y1 + 0.08 * h       # 머리 기준점
                    else:
                        if not (y1 + 0.15 * h <= my <= y1 + 0.8 * h):
                            continue
                        ax, ay = (x1 + x2) / 2, y1 + 0.4 * h        # 몸통 기준점
                    cand.append((i, key, sc, fb, ((mx - ax) ** 2 + (my - ay) ** 2) ** 0.5 / max(h, 1), pos))
        # 2) 같은 보호구가 두 사람 후보에 다 들어 있으면 기준점이 더 가까운 사람 것으로만 둔다.
        #    작은 안전모는 잘라낸 그림마다 박스가 몇 px 씩 어긋나서, 겹침 대신 가운데끼리의 거리로 같은 것인지 본다
        keep = [a for a in cand if not any(b[0] != a[0] and b[1] == a[1] and b[4] < a[4] and _same_obj(a[3], b[3]) for b in cand)]
        bests = [{k: 0.0 for k in self.items} for _ in who]
        near: dict[tuple[int, str], tuple] = {}            # 머리 쪽 — 기준점에 가장 가까운 후보
        for a in keep:
            i, key, sc, _, d, pos = a
            if self.items[key]["region"] == "head":
                if sc >= conf and ((i, key) not in near or d < near[(i, key)][4]):
                    near[(i, key)] = a
            elif pos:
                bests[i][key] = max(bests[i][key], sc)
        neg = [{k: False for k in self.items} for _ in who]
        for (i, key), a in near.items():
            pos, br = a[5], self.items[key]["bright"]
            # 안전모로 봤어도 그 박스 윗부분이 어두우면(머리카락) 맨머리로 본다 — 안전모는 흰 · 노랑 · 주황 · 파랑처럼 밝거나 색이 있다 (10/7)
            if pos and br is not None and bright_ratio(frame, a[3], br) < br.get("min_ratio", 0.4):
                pos = False
            bests[i][key] = a[2] if pos else 0.0              # 가장 가까운 게 맨머리면 착용 아님
            neg[i][key] = not pos
        for i, ((p, _, _), best, ng) in enumerate(zip(who, bests, neg)):
            for key, it in self.items.items():
                on = best[key] >= conf or (it["color"] is not None and hivis_ratio(frame, p.xyxy, it["color"]) >= it["color"].get("min_ratio", 0.10))
                raw = 1 if on else (-1 if ng[key] else 0)
                # 이 프레임 판정의 근거 점수 — 착용이면 착용 점수(색으로만 착용이면 없음), 맨머리면 맨머리 점수, 안 보였으면 없음 (10/8)
                sc = best[key] if on and best[key] > 0 else (near[(i, key)][2] if ng[key] and (i, key) in near else None)
                if sc is not None:
                    p.ppe_conf[key] = round(float(sc), 2)
                if p.key is None:
                    p.ppe[key] = on
                    continue
                h = self.hist.setdefault((key, p.key), [])
                h.append((t, raw))
                while h and (t - h[0][0] > win or len(h) > c.get("window_n", 5)):
                    h.pop(0)
                pos, nev = sum(1 for _, v in h if v > 0), sum(1 for _, v in h if v < 0)
                if it["no_ids"]:                          # 머리 — 다수결. 머리가 아예 안 보였으면(고개 숙임 · 뒤돌아섬) 판단 보류
                    if pos > nev:
                        dec = True
                    elif nev > pos:
                        dec = False
                    else:
                        dec = False if (absent_off and not pos and len(h) >= need) else None
                else:                                     # 몸통 — 한 번이라도 보였으면
                    dec = True if pos else (False if len(h) >= need else None)
                p.ppe[key] = dec
            if p.key is not None:
                self.cache[p.key] = (t, dict(p.ppe))
                self.cache_conf[p.key] = dict(p.ppe_conf)


def _overlap(a, b) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def _same_obj(a, b) -> bool:
    """두 박스가 같은 물건인가 — 가운데 거리가 박스 크기의 절반 안이면 같다고 본다."""
    d = ((a[0] + a[2] - b[0] - b[2]) ** 2 + (a[1] + a[3] - b[1] - b[3]) ** 2) ** 0.5 / 2
    size = max(a[2] - a[0], a[3] - a[1], b[2] - b[0], b[3] - b[1])
    return d <= 0.5 * size


def bright_ratio(frame: np.ndarray, xyxy, spec: dict) -> float:
    """안전모 박스 윗절반에서 밝거나(흰 · 노랑) 색이 있는(주황 · 빨강 · 파랑) 점의 비율 — 머리카락은 어둡고 색이 없다."""
    x1, y1, x2, y2 = (int(v) for v in xyxy)
    t = frame[max(0, y1):max(0, y1 + max(1, (y2 - y1) // 2)), max(0, x1):max(0, x2)]
    if t.size == 0:
        return 0.0
    hsv = cv2.cvtColor(t, cv2.COLOR_BGR2HSV)
    S, V = hsv[..., 1], hsv[..., 2]
    return float(((V >= spec.get("v_min", 150)) | ((S >= spec.get("s_min", 100)) & (V >= spec.get("sv_min", 110)))).mean())


def hivis_ratio(frame: np.ndarray, xyxy, spec: dict) -> float:
    """
    사람 박스 몸통(위 20%~60%, 좌우 15% 안쪽)에서 고시인성 색 점의 비율.
    spec.hsv = [[H 최소, H 최대], ...] (OpenCV 색상 0~180), s_min · v_min — 기본은 형광 주황(3~22) · 노랑 연두(25~45).
    """
    x1, y1, x2, y2 = xyxy
    w, h = x2 - x1, y2 - y1
    t = frame[max(0, int(y1 + 0.2 * h)):max(0, int(y1 + 0.6 * h)), max(0, int(x1 + 0.15 * w)):max(0, int(x2 - 0.15 * w))]
    if t.size == 0:
        return 0.0
    hsv = cv2.cvtColor(t, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    sv = (S >= spec.get("s_min", 120)) & (V >= spec.get("v_min", 120))
    hue = np.zeros_like(sv)
    for lo, hi in spec.get("hsv", [[3, 22], [25, 45]]):
        hue |= (H >= lo) & (H <= hi)
    return float((sv & hue).mean())
