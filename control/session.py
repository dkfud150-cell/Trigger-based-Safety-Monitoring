"""
실시간 관제 세션 — 엔진 하나를 실제 시각에 맞춰 돌린다.

  시계        실제 시각(지금)으로 흐른다 (10/8 — 시작 시각 입력 · 배속을 뺐다). 날짜는 문서 자동화와 같은 날(demo_day).
  신호        ① 화면의 3축 신호 버튼(패키지 buttons.json — PLC · PTW · 센서 대신) ② 작업허가서 등록 · 격리 단계 입력(격리 목록 대조 화면)
              — 전부 같은 Signal 로 엔진에 들어간다. 시나리오 타임라인(timeline.csv)은 재생 비교에서만 쓴다
              (영상이 1분 남짓이라 타임라인의 시각과 맞출 수 없다)
  영상        장면(scenario.json scenes)을 고르면 ▶ 시작과 함께 영상 탐지를 붙인다 (사람 · 불꽃 → 폴리곤 → 판정)
              장면에 그린 구역(polygons — 화면의 '영상 올리기 · 구역 설정')만 쓴다 (카메라 기본 구역은 쓰지 않는다)
  기록        control/records/live/<세션>/events.jsonl (추가 전용) · clips/ · frames/ · modes.jsonl
  피드백      새 기록이 생길 때마다 이탈 조건을 보고 자동 조정을 건다(feedback.py). 조정 중인 구역의 기록에는 adj_id 가 붙는다
  자동 인계   기록할 때마다 문서 자동화로 넘긴다(집계 · 증빙 누적용) — docgen handoff.receive(auto=True)

프로그램 하나에 세션 하나다(관제실 화면). 화면은 1초마다 snapshot 을 읽어 그린다.
"""
from __future__ import annotations

import threading
import time
import traceback
from collections import deque
from datetime import datetime
from pathlib import Path

from safety_monitor.engine import Engine
from safety_monitor.events import ClipRecorder, EventLog
from safety_monitor.judge import RANK, response
from safety_monitor.modes import alerting, label_mode
from safety_monitor.signals import Signal

import dataspace

from .common import LIVE_DIR, append_jsonl, clock_text, dashboard, demo_day, live_sessions, load_config, package, read_jsonl
from .dataset import Pins, RawFrames
from .detfp import DetFalsePositives, RecentTargets, current_targets


RULESETS = {"docgen": "문서 자동화 확정분", "none": "기본 규칙 (v1)", "all": "개정안 전부"}


def resolve_ruleset(ruleset: str, pkg, sc=None) -> tuple[list[str], str]:
    """
    세션 규칙셋.  docgen = 문서 자동화에서 위험성평가 확정으로 쌓인 개정안 (실제 운영과 같다)
                 none = 기본 규칙 · all = 개정안 전부 · 그 밖 = 시나리오 variants 이름 또는 'R1,R3'
    """
    from safety_monitor.package import docgen_confirmed_changes, resolve_changes
    if ruleset == "docgen":
        ids = [i for i in docgen_confirmed_changes() if i in pkg.change_ids()]
        return ids, f"문서 자동화 확정분 ({' '.join(ids) or '없음 — 기본 규칙'})"
    if ruleset in ("none", "", None):
        return [], "기본 규칙 (v1)"
    if ruleset == "all":
        return pkg.change_ids(), "개정안 전부"
    return resolve_changes(ruleset, pkg, sc)


def real_now() -> datetime:
    """실시간 관제의 '지금' — 실제 시각. 날짜는 문서 자동화와 같은 날(예시 데이터의 demo_today, 없으면 오늘)."""
    return datetime.combine(demo_day(), datetime.now().time())


# ====================================================================== 기록 — 조정 중이면 표시한다
class LiveEventLog(EventLog):
    """
    엔진의 EventLog 에 두 가지를 더한다.
      - 번호가 세션마다 처음부터 시작하지 않게 이어서 센다 (EV-10120915-017)
      - 자동 조정이 걸린 구역이면 adj_id 를 붙이고, '구역 규칙 임시 활성화'면 무음 기록을 경보로 올린다
    """

    def __init__(self, out_dir, rules, *, seq_start: int = 0, adjust=None, id_tag: str = "", stamp: dict | None = None, **kw):
        super().__init__(out_dir, rules, quiet=True, **kw)
        self._seq = seq_start
        self.adjust = adjust
        self.id_tag = id_tag                # 데이터 공간 태그 (10/14) — 사건 번호 EV-…-D001 처럼 공간끼리 겹치지 않게
        self.stamp = dict(stamp or {})      # 기록마다 붙이는 값 — 데이터 공간 · 시험/운영/시연 구분 · 세션 (10/14)

    def emit(self, **kw):
        zone, ts = kw.get("zone"), kw.get("ts")
        extra = dict(kw.get("extra") or {})
        if self.adjust and zone and kw.get("kind") in ("stage", "check"):
            adj_id, enable = self.adjust(zone, ts)
            if adj_id:
                extra["adj_id"] = adj_id
                if enable and not kw.get("alerted") and kw.get("level") and kw.get("level") != "정상":
                    kw["alerted"] = True
                    kw["reason"] = (kw.get("reason") or "") + f" · 강화 중 {adj_id} — 꺼져 있던 구역 규칙을 임시로 켰다"
        extra = {**self.stamp, **extra}
        kw["extra"] = extra
        ev = super().emit(**kw)
        if ev is not None and extra.get("adj_id"):
            ev["adj_id"] = extra["adj_id"]
        return ev


# ====================================================================== 영상
class VideoRunner(threading.Thread):
    """장면 영상 하나를 프레임마다 탐지해 엔진에 넣는다. 탐지 결과는 실제 시각으로 들어간다."""

    def __init__(self, session: "LiveSession", scene: dict, camera: dict, path: Path, start: datetime):
        super().__init__(daemon=True)
        self.s, self.scene, self.camera, self.path, self.start_ts = session, scene, camera, path, start
        self.stop_evt = threading.Event()
        self.error = None
        self.person_note = ""
        self.t, self.dur = 0.0, 0.0      # 영상 안의 지금 위치 · 길이 (초) — 화면의 진행 표시
        self.done, self.skipped = 0, 0   # 탐지한 횟수 · 화면에 못 그리고 건너뛴 프레임 (실제 속도를 지키려고)

    def run(self):
        import cv2
        from safety_monitor.detector import FlameDetector, PersonDetector, PPEChecker, YoloObjectDetector, run_objects
        from safety_monitor.draw import draw
        from safety_monitor.package import MODEL_DIR, ROOT as ENGINE_ROOT
        from safety_monitor.video_io import open_video, resize_max_width
        from safety_monitor.zones import Zones

        s = self.s
        dataspace.set_current(s.space)      # 이 스레드의 기록은 세션의 데이터 공간으로 (10/14)
        eng0 = s.eng            # 이 영상이 붙은 엔진 — 새 세션으로 바뀌면 끝정리에서 새 엔진을 건드리지 않는다
        try:
            pkg = package()
            dcfg = pkg.detect
            cap = open_video(self.path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            self.dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("영상에서 프레임을 읽지 못했습니다")
            frame = resize_max_width(frame, dcfg.get("run", {}).get("work_width", 960))
            H, W = frame.shape[:2]
            zones = Zones(self.camera, W, H)
            try:
                person_det = PersonDetector(dcfg["person"], MODEL_DIR)
            except Exception as ex:  # noqa: BLE001 — ultralytics 가 없거나 가중치가 없다
                person_det = None
                self.person_note = f"사람 탐지 없이 돈다 — {str(ex).splitlines()[0][:120]}"
            dets = {}
            if dcfg.get("flame", {}).get("backend", "color") != "off":
                dets["flame"] = FlameDetector(dcfg["flame"], root=ENGINE_ROOT,
                                              roi_mask_fn=lambda sc: zones.mask(tuple(dcfg["flame"].get("polygons", ["hazard"])),
                                                                                dilate_px=int(30 * sc), scale=sc))
            for x in dcfg.get("extra", []):
                try:
                    dets[x["name"]] = YoloObjectDetector(x, root=ENGINE_ROOT)
                except Exception as ex:  # noqa: BLE001
                    self.person_note += f" · {x['name']} 탐지 없음({str(ex)[:60]})"
            ppe = None                                      # 보호구 — 안전모 · 안전조끼 (10/7). 사람마다 몸을 잘라 본다
            if person_det and dcfg.get("ppe", {}).get("enabled"):
                try:
                    ppe = PPEChecker(dcfg["ppe"], root=ENGINE_ROOT)
                except Exception as ex:  # noqa: BLE001 — 가중치가 없으면 보호구 없이 돈다
                    self.person_note += f" · 보호구 탐지 없음({str(ex).splitlines()[0][:80]})"
            ev = dcfg["event"]
            clips = ClipRecorder(s.out_dir, fps, ev["clip_pre_s"], ev["clip_post_s"], ev["clip_max_width"])
            run_cfg = dcfg.get("run", {})
            show_fps = float(run_cfg.get("display_fps", 20))
            with s.lock:
                s.eng.zones = zones
                s.log.clips = clips
                s.eng.ppe_items = {k: dcfg["ppe"]["items"][k].get("label", k) for k in ppe.items} if ppe else {}
            cam_zone = self.camera.get("zone")

            # 화면과 탐지를 나눠 돌린다 (10/6).
            #   화면(이 스레드)  영상을 실제 속도(1×)로 읽어 초당 display_fps 장까지 그려 보낸다. 늦으면 프레임을 건너뛴다.
            #   탐지(따로 한 스레드)  가장 최근 프레임을 받아 사람 · 불꽃을 찾고 엔진에 넣는다. 끝나면 다음 최근 프레임.
            # 예전에는 프레임마다 탐지가 끝나야 다음 프레임으로 가서, 노트북에서는 영상이 몇 배 느리게 흐르고 사진처럼 넘어갔다.
            # 박스는 탐지가 끝난 프레임 기준이라 화면보다 한 박자(탐지 한 번 시간) 늦을 수 있다.
            box = {"frame": frame, "t": 0.0, "seq": 0}
            cond = threading.Condition()
            fin = threading.Event()

            def detect_loop():
                dataspace.set_current(s.space)
                seen, last_t = -1, None
                try:
                    while not fin.is_set():
                        with cond:
                            while box["seq"] == seen and not fin.is_set():
                                cond.wait(0.2)
                            if fin.is_set():
                                return
                            f, t, seen = box["frame"], box["t"], box["seq"]
                        persons = person_det(f) if person_det else []
                        if ppe:
                            ppe(f, persons, t)
                        objects = run_objects(dets, f, persons)
                        s.raw_frames.push(t, f)                    # 표시 없는 원본 - 오탐 · 미탐 이미지 로그 (dataset.py)
                        dt = 0.0 if last_t is None else max(0.0, t - last_t)
                        last_t = t
                        with s.lock:
                            if s.eng is not eng0:                  # 그새 새 세션이 시작됐다 — 이 영상은 손을 뗀다
                                fin.set()
                                return
                            if fin.is_set() or s.eng.zones is None:  # 10/14 — 영상이 끝나 구역을 비운 뒤 늦게 끝난 탐지는 버린다
                                return                               # (느린 PC 에서 탐지 한 번이 끝정리 대기 5초보다 길었다)
                            now = max(real_now(), s.eng.now)       # 실제 시각 — 뒤로 가지 않게
                            s._apply_due(now)
                            # 관제자가 오탐으로 고른 탐지는 판정 · 화면에서 뺀다 (10/8, detfp.py)
                            persons, objects = s.det_fp.apply(persons, objects)
                            s.eng.update_video(now, t, persons, objects)
                            s.det_recent.update(current_targets(s.eng, getattr(s.eng, "ppe_items", {})), now, t)
                            for z, ppl in s.eng.store.people.items():
                                s.person_seconds[z] = s.person_seconds.get(z, 0.0) + len(ppl) * dt
                            for z, d in s.eng.ppe.items():              # 보호구마다 미착용 사람-초 (히트맵 · 통계 PPE 착용률)
                                for item, v in d.items():
                                    off = v.get("off", 0)
                                    if off:
                                        sec = s.ppe_off_seconds.setdefault(item, {})
                                        sec[z] = sec.get(z, 0.0) + off * dt
                        self.done += 1
                        s._after_step()
                except Exception as ex:  # noqa: BLE001
                    self.error = f"탐지 오류: {ex}"
                    traceback.print_exc()
                    fin.set()

            def fall_loop():
                dataspace.set_current(s.space)
                """쓰러짐 (10/13) — 큰 모델(yolo26m)을 사람 탐지와 따로, every_s 초에 한 번 가장 최근 프레임에 돌린다.
                사람 탐지 스레드에서 같이 돌리면 사람 박스가 그만큼 느려진다. 실패하면 쓰러짐만 빼고 계속 돈다."""
                try:
                    while not fin.is_set():
                        with cond:
                            f, t = box["frame"], box["t"]
                        if self.done and eng0.fall.due(t):
                            eng0.fall.look(f, t)
                        else:
                            time.sleep(0.1)
                except Exception as ex:  # noqa: BLE001
                    self.person_note += f" · 쓰러짐 탐지 없음({str(ex).splitlines()[0][:80]})"
                    traceback.print_exc()

            det = threading.Thread(target=detect_loop, daemon=True)
            det.start()
            threading.Thread(target=fall_loop, daemon=True).start()
            i, shown, t0 = 0, 0, time.time()
            first = True
            while not self.stop_evt.is_set() and not fin.is_set():
                if not s.running:
                    time.sleep(0.1)
                    t0 = time.time() - i / fps
                    continue
                if first:
                    # 첫 탐지(모델 예열)가 끝날 때까지 첫 프레임에서 기다린다 — 영상 앞부분을 건너뛰지 않게
                    with cond:
                        box.update(frame=frame, t=0.0, seq=box["seq"] + 1)
                        cond.notify()
                    while self.done == 0 and not fin.is_set() and not self.stop_evt.is_set():
                        time.sleep(0.02)
                    first, t0 = False, time.time()
                else:
                    late = int((time.time() - t0) * fps) - i      # 실제 시각보다 몇 프레임 늦었나
                    ok = True
                    for _ in range(max(0, late - 1)):
                        ok = cap.grab()
                        if not ok:
                            break
                        i += 1
                        self.skipped += 1
                    ok, frame = cap.read() if ok else (False, None)
                    if not ok:
                        break
                    i += 1
                    frame = resize_max_width(frame, W)
                t = i / fps
                self.t = t
                with cond:                                     # 탐지 스레드에 가장 최근 프레임을 건넨다
                    box.update(frame=frame, t=t, seq=box["seq"] + 1)
                    cond.notify()
                with s.lock:
                    vis = draw(frame, s.eng, zones, cam_zone)
                clips.push(t, vis)
                s._set_frame(self.camera["camera_id"], vis)
                shown += 1
                # 다음 그릴 시각 — 원본 fps 와 display_fps 중 느린 쪽. 남는 프레임은 위에서 건너뛴다
                nxt = t0 + max((i + 1) / fps, shown / show_fps)
                wait = nxt - time.time()
                if wait > 0:
                    time.sleep(wait)
            fin.set()
            with cond:
                cond.notify_all()
            det.join(timeout=5)
            cap.release()
            clips.flush()
        except Exception as ex:  # noqa: BLE001
            self.error = f"영상 실행 오류: {ex}"
            traceback.print_exc()
        finally:
            with s.lock:
                e = s.eng if s.eng is eng0 else None     # 늦게 끝난 지난 영상이 새 세션의 엔진을 비우지 않게
                if e is not None:
                    e.video_on, e.video_t, e.persons, e.objects, e.zones = False, None, [], {}, None
                    e.store.people = {}
                    e.ppe, e.ppe_items = {}, {}
                    e.area_alerts = {}                       # 영상이 끝나면 구역 규칙(위험구역 진입) 경보도 내린다
                    for rec in e.store.detections.values():
                        rec["on"] = False
                    e.evaluate()
                if e is not None and s.log is not None:
                    s.log.clips = None
                if e is not None and s.sid:
                    s._save_counts()                         # 영상이 끝나면 바로 통계(PPE 착용률)에 보이게
                if s.sid and s.out_dir is not None and e is not None:   # 10/14 — 영상 실행 결과 (처리 프레임 · 건너뜀 · 오류)
                    try:
                        append_jsonl(s.out_dir / "session.json", {"sid": s.sid, "event": "video_end", "ts": real_now().isoformat(timespec="seconds"),
                                                                  "video_file": Path(self.path).name, "video_len_s": round(self.dur, 2),
                                                                  "reached_s": round(self.t, 2), "detect_runs": self.done,
                                                                  "frames_skipped": self.skipped, "error": self.error or "",
                                                                  "note": self.person_note})
                    except Exception:  # noqa: BLE001
                        pass
                if s.video is self:
                    s.video = None
                if e is not None:
                    s.note(f"영상 장면 '{self.scene.get('name')}' 끝 — 신호로만 판정한다 · 탐지 {self.done}번"
                           + (f" (영상 {self.dur:.0f}초 · 초당 약 {self.done / self.dur:.1f}번)" if self.dur else "")
                           + (f" · {self.error}" if self.error else ""))


# ====================================================================== 세션
class LiveSession:
    def __init__(self):
        self.lock = threading.RLock()
        self.eng: Engine | None = None
        self.log: LiveEventLog | None = None
        self.rules: dict | None = None
        self.out_dir: Path | None = None
        self.sid: str | None = None
        self.running = False
        self.speed = 1                      # 시계는 실제 시각 — 배속 없음 (화면 표시용으로만 남긴다)
        self.schedule: list[Signal] = []
        self.sched_i = 0
        self.scenario = None
        self.scene: dict | None = None
        self.scene_started = False
        self.video: VideoRunner | None = None
        self.frames: dict[str, bytes] = {}
        self.frame_no = 0                   # 프레임이 바뀔 때마다 1씩 — 영상 스트림(/api/live/stream)이 새 프레임만 보낸다
        self.person_seconds: dict[str, float] = {}
        self.ppe_off_seconds: dict[str, dict[str, float]] = {}    # 보호구(helmet · vest) → 구역 → 미착용 사람-초
        self.notes = deque(maxlen=40)
        self.det_fp = DetFalsePositives()   # 실시간 탐지 오탐 처리 (10/8)
        self.det_recent = RecentTargets()   # 최근 몇 초 안에 잡힌 탐지 - 탐지 오탐 창이 고르는 목록
        self.cam_zone = ""                  # 영상 카메라의 구역 - 영상이 끝난 뒤 오탐을 저장할 때도 쓴다
        self.raw_frames = RawFrames()       # 최근 60초 원본 프레임 - 오탐 · 미탐 이미지 로그 (10/8)
        self.pins = Pins()                  # 오탐 · 미탐 창을 연 순간의 프레임 고정본 - 저장하면 이 그림이 남는다
        self.meta: dict = {}
        self.space = dataspace.DEFAULT_KEY   # 이 세션이 기록하는 데이터 공간 (10/14) — 세션을 시작할 때 정하고 끝날 때까지 바꾸지 않는다
        self.run_kind = ""                   # 시험 · 운영 · 시연 (10/14)
        self._mode_open: dict[tuple[str, str], datetime] = {}
        self._fb_seen = 0
        self._handoff_i = 0
        self._handoff_wall = 0.0
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ 읽기
    def clock(self) -> datetime | None:
        with self.lock:
            return self.eng.now if self.eng is not None and self.sid else None

    def note(self, msg: str):
        t = self.eng.now if self.eng is not None else datetime.now()
        self.notes.appendleft((t, msg))

    def _set_frame(self, cam_id: str, vis):
        import cv2
        from safety_monitor.video_io import resize_max_width
        ok, enc = cv2.imencode(".jpg", resize_max_width(vis, 960), [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ok:
            self.frames[cam_id] = enc.tobytes()
            self.frame_no += 1

    # ------------------------------------------------------------------ 시작 · 멈춤
    def ensure(self):
        """화면이 처음 열릴 때 — 아직 시작 전이면 기록 없이 미리 보기 엔진을 만든다."""
        with self.lock:
            if self.eng is None:
                cfg = load_config()["live"]
                demo = dashboard().get("demo", {})
                sched = demo.get("schedule") or None
                if sched not in package().scenario_keys():
                    sched = None                    # 패키지에 없는 시나리오 — 스케줄 없이 버튼으로만
                self.reset(sched, cfg.get("ruleset", "docgen"), (demo.get("scene") or None) if sched else None, record=False)

    def reset(self, schedule: str | None, ruleset: str, scene: str | None = None, record: bool = True,
              space: str | None = None, run_kind: str | None = None) -> str:
        """
        새 세션 — 지금 시각부터. record=True 면 기록 폴더를 만들고 시계를 돌린다.
        데이터 공간(10/14): 새 세션은 화면에서 고른 '새 세션 저장' 공간(dataspace.write_key)에 기록하고, 끝날 때까지 그 공간을 쓴다.
        저장 공간 폴더가 연결되어 있지 않으면 기록을 시작하지 않는다(SpaceError) — 다른 공간에 대신 저장하지 않는다.
        """
        key = space or (dataspace.write_key() if record else self.space)
        kind = run_kind or (dataspace.write_run_kind() if record else self.run_kind)
        if record:
            dataspace.prepare_write(key)     # 연결 확인 — 실패하면 지금 세션은 그대로 둔 채 오류
        if self.sid:
            with dataspace.use(self.space):
                self.stop_video()
                self._flush()
        else:
            self.stop_video()
        with dataspace.use(key):
            self.space, self.run_kind = key, kind
            return self._reset(schedule, ruleset, scene, record)

    def _reset(self, schedule: str | None, ruleset: str, scene: str | None = None, record: bool = True) -> str:
        from . import feedback           # 앞 세션의 영상 멈춤 · 남은 인계는 reset() 이 앞 세션의 공간에서 끝냈다
        with self.lock:
            if self.eng is not None and self.sid:
                self._save_counts()
            pkg = package()
            self.running = False
            sc = pkg.scenario(schedule) if schedule else None
            ids, label = resolve_ruleset(ruleset, pkg, sc)
            rules = pkg.rules(ids)
            rules["_label"] = label
            t0 = real_now()                     # 시작 시각은 따로 받지 않는다 — 지금
            self.sid = None
            self.out_dir = None
            if record:
                n = len(live_sessions()) + 1
                tag = dataspace.id_tag(self.space)
                self.sid = f"LIVE-{datetime.now():%Y%m%d-%H%M%S}" + (f"-{tag}" if tag else "")
                self.out_dir = (LIVE_DIR / self.sid).real()      # 세션 폴더는 시작할 때의 공간으로 고정 (10/14)
                self.out_dir.mkdir(parents=True, exist_ok=True)
                seq = sum(len(read_jsonl(d / "events.jsonl")) for d in live_sessions())
            else:
                n, seq = 0, 0
            cooldown = pkg.detect.get("event", {}).get("cooldown_s", 30)
            sp = dataspace.info(self.space)
            stamp = {"data_space": self.space, "run_kind": self.run_kind} if record else {}
            self.log = LiveEventLog(self.out_dir, rules, seq_start=seq, cooldown_s=cooldown, adjust=feedback.lookup,
                                    id_tag=dataspace.id_tag(self.space), stamp=stamp)
            self.eng = Engine(pkg, rules, t0, log=self.log, scenario_dir=sc.dir if sc else None)
            self.rules, self.scenario = rules, sc
            self.scene = None                           # 영상은 ▶ 시작 뒤에 붙는다 — 세션을 만들기만 해서는 돌지 않는다
            self.scene_started = False
            self.schedule, self.sched_i = [], 0         # 시나리오 타임라인은 넣지 않는다 — 3축 신호 버튼 · 격리 목록 대조 입력으로만
            self.frames, self.person_seconds, self.ppe_off_seconds = {}, {}, {}
            self._mode_open, self._handoff_i, self._handoff_wall = {}, 0, 0.0
            self._fb_seen = 0
            self.notes.clear()
            self.det_fp.clear()
            self.det_recent.clear()
            self.raw_frames.clear()
            self.meta = {"schedule": schedule or "", "schedule_title": sc.title if sc else "스케줄 없음",
                         "ruleset": ruleset, "rules_label": label, "applied": list(ids), "start": t0,
                         "scene": scene or "", "n": n,
                         "data_space": self.space, "data_space_label": sp["label"], "data_space_root": sp["root"],
                         "run_kind": self.run_kind if record else ""}
            self._apply_due(t0)
            self.eng.tick(t0)
            self._track_modes()
            self.scene = next((x for x in sc.scenes() if x.get("name") == scene), None) if (sc and scene) else None
            if record:
                append_jsonl(self.out_dir / "session.json", {**self.meta, "sid": self.sid, "start": t0.isoformat(),
                                                              "package": pkg.root.name})
                self.note(f"세션 시작 — {self.meta['schedule_title']} · 규칙 {label} · 신호는 3축 신호 버튼으로 넣는다")
            return self.sid or ""

    def start(self):
        with self.lock:
            if not self.sid:
                m = self.meta
                self.reset(m.get("schedule") or None, m.get("ruleset", "docgen"), m.get("scene") or None)
            self.running = True

    def pause(self):
        with self.lock:
            self.running = False
            self._save_counts()
        self._flush()

    def _flush(self):
        """멈추거나 새 세션으로 넘어갈 때 — 남은 기록을 자동 인계로 마저 넘긴다."""
        try:
            self._auto_handoff(force=True)
        except Exception:  # noqa: BLE001 — 인계가 실패해도 관제는 멈추지 않는다
            traceback.print_exc()

    def _save_counts(self):
        """영상에서 센 사람 시간 · 보호구 미착용 시간을 세션 파일에 누적값으로 한 줄 남긴다 (히트맵 · 통계 PPE). 영상이 끝날 때 · 멈출 때 · 새 세션 때."""
        if self.out_dir and (self.person_seconds or self.ppe_off_seconds):
            append_jsonl(self.out_dir / "session.json", {"sid": self.sid, "ts": self.eng.now.isoformat(),
                                                          "person_seconds": dict(self.person_seconds),
                                                          "ppe_off_seconds": {k: dict(v) for k, v in self.ppe_off_seconds.items()},
                                                          "no_helmet_seconds": dict(self.ppe_off_seconds.get("helmet", {}))})

    def stop_video(self):
        v = self.video
        if v is not None:
            v.stop_evt.set()
            v.join(timeout=3)
        self.video = None

    # ------------------------------------------------------------------ 시계
    def _loop(self):
        while True:
            time.sleep(0.25)
            dataspace.set_current(self.space)    # 이 스레드는 지금 세션의 데이터 공간에 기록한다 (10/14)
            try:
                if not self.running or self.video is not None or self.eng is None:
                    continue
                with self.lock:
                    target = max(real_now(), self.eng.now)     # 실제 시각으로 — 멈췄다 계속하면 지금 시각으로 건너뛴다
                    self._apply_due(target)
                    if self.video is None:
                        self.eng.tick(target)
                self._after_step()
            except Exception:  # noqa: BLE001 — 시계가 죽으면 화면이 멈춘다. 적고 계속 간다
                traceback.print_exc()

    def _apply_due(self, target: datetime):
        """스케줄에서 target 시각까지의 신호를 넣는다(실시간 관제는 비어 있다). 세션이 돌기 시작하면 영상을 붙인다."""
        while self.sched_i < len(self.schedule) and self.schedule[self.sched_i].ts <= target:
            sig = self.schedule[self.sched_i]
            self.sched_i += 1
            self._apply(sig)
        if self.scene and not self.scene_started and self.sid and self.running:
            self.scene_started = True
            self._start_video(target)

    def _apply(self, sig: Signal) -> list[str]:
        notes = self.eng.apply(sig)
        for n in notes:
            self.note(f"{clock_text(sig.ts)} {sig.label or sig.signal}: {n}")
        if not notes:
            self.note(f"{clock_text(sig.ts)} {sig.short()} ({sig.source})")
        return notes

    def _start_video(self, at: datetime):
        pkg = package()
        sc = self.scene
        try:
            cam = pkg.scene_camera(sc)              # 장면에 그린 구역만 (없으면 화면 전체) — 카메라 기본 구역은 쓰지 않는다
        except Exception as ex:  # noqa: BLE001
            self.note(f"영상 장면을 붙이지 못했다 — {ex}")
            return
        video = sc.get("video") or ""
        cands = [Path(video), self.scenario.dir / video, pkg.root / video]
        path = next((c for c in cands if c.exists()), None)
        if path is None:
            self.note(f"영상 파일이 없다 — {video}. 신호로만 판정한다")
            return
        self.eng.now = at
        self.det_fp.clear()                     # 추적 번호는 영상마다 새로 매겨진다 - 지난 영상의 오탐 처리를 남기지 않는다
        self.det_recent.clear()
        self.raw_frames.clear()
        self.cam_zone = cam.get("zone") or ""
        self.video = VideoRunner(self, sc, cam, path, at)
        if self.sid and self.out_dir is not None:     # 10/14 — 어떤 영상 파일을 돌렸는지 세션 기록에 남긴다 (시연 로그 식별 정보)
            try:
                import hashlib
                h = hashlib.sha256(path.read_bytes()).hexdigest()
                append_jsonl(self.out_dir / "session.json", {"sid": self.sid, "event": "video_start", "ts": at.isoformat(timespec="seconds"),
                                                             "scene": sc.get("name"), "camera": cam.get("camera_id"),
                                                             "video_file": path.name, "video_path": str(path.resolve()),
                                                             "video_bytes": path.stat().st_size, "video_sha256": h,
                                                             "polygons": bool(sc.get("polygons"))})
            except Exception:  # noqa: BLE001 — 기록 실패로 영상을 막지 않는다
                pass
        self.video.start()
        self.note(f"{clock_text(at)} 영상 장면 '{sc.get('name')}' 시작 — {cam['camera_id']}"
                  + (" · 장면에 그린 구역" if sc.get("polygons") else " · 구역 없음(화면 전체)"))

    def play_scene_now(self) -> str:
        """세션에 붙은 영상 장면을 지금 튼다 (끝난 영상이면 처음부터 다시)."""
        with self.lock:
            if not self.sid:
                raise RuntimeError("세션을 시작해야 영상을 틀 수 있다 — 시연 제어에서 새 세션 시작")
            if self.video is not None:
                return f"영상 장면 '{self.scene.get('name')}' 재생 중 — {clock_text(self.video.start_ts)}부터"
            self._reload_scene()
            sc = self.scene
            if not sc:
                raise RuntimeError("이 세션에는 영상 장면이 없다 — 시연 제어에서 장면을 고르고 새 세션을 시작한다")
            self.running = True
            self.scene_started = True
            self._start_video(max(real_now(), self.eng.now))
            msg = f"영상 장면 '{sc.get('name')}' 재생 — {clock_text(self.eng.now)}부터" if self.video else \
                  (self.notes[0][1] if self.notes else "영상을 붙이지 못했다")
        self._after_step()
        return msg

    def _reload_scene(self):
        """영상 장면 편집기에서 고친 구역 · 영상을 다음 재생에 쓰도록 장면을 파일에서 다시 읽는다."""
        if self.scene and self.scenario is not None:
            try:
                fresh = package().scenario(self.scenario.key).scenes()
            except Exception:  # noqa: BLE001 — 시나리오가 사라졌으면 들고 있던 걸 쓴다
                return
            self.scene = next((x for x in fresh if x.get("name") == self.scene.get("name")), self.scene)

    def refresh_scene(self, schedule: str, name: str | None, orig: str | None = None):
        """장면을 저장 · 삭제했을 때 — 이 세션이 그 장면을 쓰고 있고 아직 재생 전이면 바로 바꿔 끼운다."""
        with self.lock:
            if self.video is not None or self.scenario is None or self.scenario.key != schedule or not self.scene:
                return
            cur = self.scene.get("name")
            if cur not in {name, orig}:
                return
            fresh = package().scenario(schedule).scenes()
            self.scene = next((x for x in fresh if x.get("name") == name), None) if name else None
            self.meta["scene"] = self.scene.get("name") if self.scene else ""
            self.note("영상 장면을 다시 읽었다 — " + (f"'{self.scene['name']}'" if self.scene else "장면이 빠졌다"))

    # ------------------------------------------------------------------ 신호 넣기 (3축 신호 버튼 · 입력창)
    def apply_signal(self, signal: str, zone: str | None = None, target: str | None = None,
                     value: str | None = None, source: str = "버튼", note: str = "",
                     ts: datetime | None = None) -> list[str]:
        with self.lock:
            if self.eng is None:
                self.ensure()
            if not self.sid:
                raise RuntimeError("세션을 시작해야 신호를 넣을 수 있다 — 시연 제어에서 ▶ 시작")
            sig = Signal(ts=ts or self.eng.now, signal=signal, zone=zone or None, target=target or None,
                         value=value or None, source=source, note=note)
            notes = self._apply(sig)
            self.eng.tick(self.eng.now)
        self._after_step()
        return notes

    def stop_order(self, zone: str) -> dict:
        """
        작업중지 지시 — 관제실이 지시한 시각을 관제 기록(kind=info)으로 남긴다.
        방송 설비와의 연동은 아직 없다. 사고 경과(산업재해조사표)에서 '경보 뒤 지시가 나갔는지'를 확인하는 근거가 된다.
        """
        with self.lock:
            if not self.sid:
                raise RuntimeError("세션이 돌지 않는다 — 지시를 남길 관제 기록이 없다")
            st = self.zone_state(zone)
            ev = self.log.emit(kind="info", ts=self.eng.now, zone=zone, mode=st.get("mode_label"),
                               violation_type="작업중지_지시", level=st.get("level"), alerted=True,
                               reason=f"관제실 작업중지 지시 — {st.get('level')} · {st.get('reason') or ''}"[:200],
                               response=st.get("response") or "")
            self.note(f"{self.eng.now:%H:%M} {zone} 작업중지 지시 기록")
        return ev

    def press(self, key: str, zone: str | None = None) -> list[str]:
        """3축 신호 버튼 — 버튼에 구역이 적혀 있으면 그 구역, 비어 있으면 화면에서 고른 구역(zone)으로 넣는다."""
        b = package().buttons.get(key)
        if not b:
            raise KeyError(key)
        z = b.get("zone") or zone
        if not z:
            raise ValueError("구역을 먼저 고른다 — 3축 신호판의 구역")
        return self.apply_signal(b["signal"], z, b.get("target"), b.get("value"), "버튼", b.get("label", ""))

    # ------------------------------------------------------------------ 한 걸음 뒤
    def _track_modes(self):
        """모드가 켜지고 꺼진 시각을 남긴다 — 히트맵 · 통계의 '모드가 켜졌을 때 vs 평상시'가 쓴다."""
        eng = self.eng
        now = eng.now
        cur = {(z, n) for z, act in eng.modes.items() for n, since in act if since is not None}
        for key in cur - set(self._mode_open):
            self._mode_open[key] = now
            if self.out_dir:
                append_jsonl(self.out_dir / "modes.jsonl", {"zone": key[0], "mode": key[1], "ts": now.isoformat(), "on": True})
        for key in set(self._mode_open) - cur:
            self._mode_open.pop(key)
            if self.out_dir:
                append_jsonl(self.out_dir / "modes.jsonl", {"zone": key[0], "mode": key[1], "ts": now.isoformat(), "on": False})

    def _after_step(self):
        from . import feedback
        with self.lock:
            if self.eng is None:
                return
            self._track_modes()
            rows = self.log.rows if self.log else []
            new = len(rows) > self._fb_seen
            self._fb_seen = len(rows)
            now = self.eng.now
        if new and self.sid:
            try:
                for a in feedback.evaluate(now=now):
                    self.note(f"{now:%H:%M} 자동 조정 {a['adj_id']} — {a['zone']} {feedback.reason_text(a)}")
            except Exception:  # noqa: BLE001
                traceback.print_exc()
        self._auto_handoff()

    def _auto_handoff(self, force: bool = False):
        cfg = load_config()["live"]
        if not self.sid or not cfg.get("auto_handoff", True):
            return
        if not force and time.time() - self._handoff_wall < cfg.get("auto_handoff_every_s", 10):
            return
        with self.lock:
            rows = self.log.rows[self._handoff_i:]
            ready = []
            for e in rows:                      # 프레임이 아직 안 써졌으면 다음 번에 넘긴다
                if e.get("frame_path") and not (self.out_dir / e["frame_path"]).exists() and not force:
                    break
                ready.append(e)
            if not ready:
                return
            self._handoff_i += len(ready)
            self._handoff_wall = time.time()
        from safety_docs.handoff import receive
        receive(ready, source=f"실시간 관제 · 자동 ({self.sid})", base_dir=self.out_dir, auto=True)

    def handoff(self, event_ids: list[str] | None = None, source: str = "실시간 관제") -> dict:
        """'문서 자동화로 넘기기' — 이 세션의 기록(또는 고른 것)을 넘긴다. 이미 넘긴 것은 인계 기록에 같이 보인다."""
        from safety_docs.handoff import receive
        with self.lock:
            if not self.sid:
                raise RuntimeError("시작한 세션이 없다 — 넘길 관제 기록이 없다")
            rows = [e for e in self.log.rows if not event_ids or e["event_id"] in event_ids]
        if not rows:
            raise RuntimeError("넘길 기록이 없다")
        self._auto_handoff(force=True)
        return receive(rows, source=f"{source} ({self.sid})", base_dir=self.out_dir)

    # ------------------------------------------------------------------ 화면용 요약
    def zone_state(self, zone: str) -> dict:
        """
        구역 하나의 지금 상태 — 단계 · 경보 여부 · 줄 · 이유 · 모드 · 축 · 사람.
        판정표(3축) 단계와 구역 규칙(영상 — 위험구역 진입, rules.json area_checks) 중 높은 쪽이 그 구역 단계다.
        """
        st = self._table_state(zone)
        a = self.eng.area_alert(zone) if self.eng is not None else None
        # override(쓰러짐, 10/13): 판정표가 같은 단계로 울리고 있어도 구역 규칙을 보인다 — 폭발 최고 경보 중에 사람이 쓰러진 것을 팝업으로 알린다
        if a and (not st["alerting"] or RANK[a["level"]] > RANK[st["level"]]
                  or (a.get("override") and RANK[a["level"]] >= RANK[st["level"]])):
            st = {**st, "alerting": True, "level": a["level"], "since": a["since"], "row": None,
                  "reason": a["reason"], "violation": a["violation"], "response": a["response"],
                  "computed": a["level"] if RANK[a["level"]] > RANK[st.get("computed") or "정상"] else st.get("computed"),
                  "rule": f"구역 규칙 (영상) · {a['label']}"}
        return st

    def _table_state(self, zone: str) -> dict:
        eng = self.eng
        active = eng.modes.get(zone) or []
        on_modes = [n for n, since in active if since is not None]
        best = None
        for (z, t), ls in eng.levels.items():
            if z != zone:
                continue
            al = alerting(eng.rules, active, t)
            key = (RANK[ls.level] if al else -1, RANK[ls.level])
            if best is None or key > best[0]:
                best = (key, t, ls, al)
        people = eng.store.people.get(zone, [])
        # 센서 이상 · 측정 실패 상태 (STEP 02-10 A-3 · B-3) — 판정과 별도로 화면 · API 에 보인다
        from safety_monitor.conditions import fault_states
        faults = [{"label": f["label"], "target": f["target"] or "", "fault": f["fault"], "raw": f["raw"],
                   "t": f["ts"].strftime("%H:%M:%S"), "ts": f["ts"].isoformat(), "since": f["since"].strftime("%H:%M:%S"),
                   "count": f["count"],
                   "last_valid": ({"value": f["last_valid"]["value"], "t": f["last_valid"]["ts"].strftime("%H:%M:%S"),
                                   "ts": f["last_valid"]["ts"].isoformat()} if f["last_valid"] else None),
                   "last_valid_used": f["last_valid_used"], "minutes": f["minutes"],
                   # 가스 측정 지점 실패: 실패 전 마지막 유효값이 해제 기준(lel_clear_max)을 넘었으면 '위험 미해제' 표시용 (보완)
                   "last_valid_over": bool(f["last_valid"] and f["fact"] == "gas"
                                           and f["last_valid"]["value"] > float(eng.rules.get("vars", {}).get("lel_clear_max", 5)))}
                  for f in fault_states(eng.ctx(zone))]
        # 판정 신뢰 상태 (STEP 02-10 보완 B) — 지점 없는 측정(LEL 센서)의 이상 중에는 계산이 직전 유효값에 기대고 있다.
        # 계산 결과(단계)는 바꾸지 않고, 그 계산의 근거가 지금 센서값이 아니라는 것만 따로 알린다. 기한 · 경보 등급은 정하지 않는다.
        lim = [f for f in faults if not f["target"]]
        reliability = None
        if lim:
            f0 = lim[0]
            reliability = {"state": "limited" if f0["last_valid"] else "none", "label": f0["label"], "fault": f0["fault"],
                           "since": f0["since"], "minutes": f0["minutes"], "last_valid": f0["last_valid"],
                           "text": (f"{f0['label']} {f0['fault']} — 판정은 직전 유효값 {f0['last_valid']['value']:g}% ({f0['last_valid']['t']}) 기준 · 지금 센서값 아님"
                                    if f0["last_valid"] else f"{f0['label']} {f0['fault']} — 유효한 측정값이 없어 이 측정에 기댄 판정 근거 없음")}
        # 보호구 — 모델이 돌 때만. [{key, label, on, off, skip}] (안전모 · 안전조끼 순)
        hel = [{"key": k, "label": lb, **eng.ppe.get(zone, {}).get(k, {"on": 0, "off": 0, "skip": 0})}
               for k, lb in eng.ppe_items.items()] if eng.ppe_items else None
        if best is None:
            return {"zone": zone, "level": "정상", "alerting": False, "modes": on_modes, "table": None, "ls": None,
                    "people": len(people), "ppe": hel, "computed": "정상", "faults": faults, "reliability": reliability}
        _, t, ls, al = best
        table = eng.tables[t]
        res = ls.result
        present = len(people) > 0 or (not eng.video_on and any(
            (f, zone) in eng.store.on for f in ("ptw", "hot_work_permit", "confined_permit")))
        return {"zone": zone, "table": t, "tdef": table, "ls": ls, "alerting": al,
                "level": ls.level if al else "정상", "computed": ls.level, "row": ls.row, "since": ls.raised_at,
                "reason": res.reason if res else "", "violation": ls.violation, "modes": on_modes,
                # 세부 원인 · 짧은 이름 (STEP 03-3 보완) — 지금 계산 줄의 것. 표시 단계(ls)와 계산 줄이 같을 때만 쓴다
                "causes": (res.causes if res and res.row == ls.row and res.violation == ls.violation else None),
                "title": (res.title if res and res.row == ls.row and res.violation == ls.violation else None),
                "axes": res.axes if res else {}, "people": len(people), "ppe": hel, "present": present,
                "response": response(table, ls.level, present) if al else "",
                "mode_label": label_mode(active), "faults": faults, "reliability": reliability}

    # ------------------------------------------------------------------ 실시간 탐지 오탐 (10/8)
    def zone_alarm(self, zone: str) -> str:
        """그 구역이 지금 경보 이상이면 그 단계, 아니면 "" - 판정을 끄는 처리 전에 확인을 받는 데 쓴다."""
        with self.lock:
            if not zone or self.eng is None or zone not in self.eng.site.get("zones", {}):
                return ""
            st = self.zone_state(zone)
            return st["level"] if st.get("alerting") and st.get("level") in ("경보", "최고 경보") else ""

    def _view_near(self, t: float | None) -> bytes | None:
        """관제 화면(표시 있는 프레임) - 클립 버퍼에서 t 에 가장 가까운 것, 없으면 지금 화면."""
        clips = self.log.clips if self.log else None
        if clips is not None and clips.buf and t is not None:
            for _ in range(3):                 # 화면 스레드가 같은 버퍼에 넣는 중이면 다시 읽는다
                try:
                    return min(list(clips.buf), key=lambda x: abs(x[0] - t))[1]
                except (RuntimeError, ValueError):
                    continue
        cam = ((self.video.camera or {}).get("camera_id") if self.video else None)
        return self.frames.get(cam) if cam else (next(iter(self.frames.values()), None) if self.frames else None)

    def pin_snapshot(self, purpose: str = "fp") -> dict:
        """
        탐지 오탐 · 미탐 창을 여는 순간 - 그 화면을 고정한다 (10/8 오후). 저장을 누른 순간이 아니라 이 순간의 그림이 남는다.
        탐지 오탐이면 목록의 탐지마다 '마지막으로 잡힌 시각'의 프레임도 같이 고정한다(방금 사라진 사람도 그 사람이 보이던 그림으로).
        """
        with self.lock:
            cam = ((self.video.camera or {}).get("camera_id") if self.video else None)
            cur_view = self.frames.get(cam) if cam else None
            frames = {"now": (self.raw_frames.near(None), cur_view)}
            boxes, times = {}, {}
            if purpose == "fp" and self.video is not None:
                for t in self.det_recent.list():
                    frames[t["ref"]] = (self.raw_frames.near(t.get("seen_t")),
                                        cur_view if t.get("now") else self._view_near(t.get("seen_t")))
                    boxes[t["ref"]], times[t["ref"]] = t.get("xyxy"), t.get("seen_at", "")
            made = self.eng.now.isoformat(timespec="seconds") if self.eng is not None else ""
            sid = self.pins.pin(frames, made, boxes, times)
            zone = ((self.video.camera or {}).get("zone") if self.video else "") or self.cam_zone
        return {"snap_id": sid, "made_at": made, "zone": zone, "alarm": self.zone_alarm(zone),
                "has_frame": bool(cur_view), "dets": self.det_recent.list() if self.video else []}

    def mark_det_fp(self, ref: str, xyxy, *, by: str, cat: str, note: str = "", target: dict | None = None,
                    action: str = "record", confirm: bool = False, snap_id: str = "") -> dict:
        """
        탐지 하나를 오탐으로 고른다. ref 는 snapshot 의 dets[].ref.
        최근 목록(RecentTargets)에서 찾고, 그새 빠졌으면 화면이 창을 열 때 본 줄(target)을 쓴다 -
        실시간 영상이라 저장하는 사이 사람이 사라져도 저장된다 (10/8 오후). 물체 박스는 화면이 본 박스(xyxy)로.
        action = 판정 처리 방식 (detfp.ACTIONS). 경보 중인 구역에서 판정을 바꾸려면 confirm 이 있어야 한다.
        """
        from . import detfp
        with self.lock:
            if not self.sid:
                raise ValueError("세션이 시작된 뒤에 고를 수 있다")
            # 창을 연 순간 화면이 본 줄(탐지 시각 · 박스)을 먼저 쓴다 - 서버 목록은 그 뒤에도 계속 시각이 바뀐다 (10/8 오후)
            t = detfp.from_client(target) or self.det_recent.get(ref)
            if t is None:
                raise ValueError("고른 탐지 정보를 읽지 못했다 - 탐지 오탐 창을 다시 열어 고른다")
            if action not in dict(detfp.ACTIONS[t["kind"]]):
                raise ValueError("판정 처리 방식을 고른다")
            if t["kind"] == "object" and xyxy:
                t = {**t, "xyxy": [float(v) for v in xyxy]}
            zone = ((self.video.camera or {}).get("zone") if self.video else "") or self.cam_zone
            alarm = self.zone_alarm(zone) if detfp.changes_judgment(action) else ""
            if alarm and not confirm:
                raise ValueError(f"{zone} 이(가) 지금 {alarm} 이다 - 판정을 끄려면 '경보 중 확인'을 고른다")
            vt = t.get("seen_t")
            if vt is None and self.video:
                vt = round(self.video.t, 1)
            row = detfp.record(t, by=by, cat=cat, note=note, zone=zone, ts=self.eng.now, action=action,
                               sid=self.sid or "", scene=(self.scene or {}).get("name", ""), video_t=vt,
                               confirmed_alarm=alarm)
            self.det_fp.add(t, row)
            try:                                   # 이미지 로그 - 원본 · 관제 화면 · 박스 둘레 (학습 자료, dataset.py)
                from . import dataset
                pinned = self.pins.get(snap_id, ref)              # 창을 연 순간 고정해 둔 그 탐지의 프레임
                raw, view = pinned if pinned else (self.raw_frames.near(vt), self._view_near(vt))
                img = dataset.save("fp", row["dfp_id"], raw=raw, view=view, t_event=vt,
                                   box=t.get("xyxy"),
                                   meta={k: row.get(k) for k in ("det", "kind", "target", "conf", "cat", "note", "action",
                                                                 "zone", "seen_at", "ts", "by", "sid", "scene")} | {"label": "false_positive"})
                if img:
                    detfp.add_update(row["dfp_id"], img)
                    row.update(img)
            except Exception as ex:  # noqa: BLE001 - 이미지가 안 남아도 오탐 기록은 남는다
                self.note(f"탐지 오탐 이미지 저장 실패 - {ex}")
            seen = (row.get("seen_at") or "")[11:19]
            self.note(f"{clock_text(self.eng.now)} 탐지 오탐 - {t['label']}" + (f" (탐지 {seen})" if seen else "")
                      + f" · {row['action_label']} · {cat} · {by}" + (f" · {alarm} 중 확인" if alarm else ""))
            return row

    # ------------------------------------------------------------------ 미탐 처리 (10/8 오후)
    MISS_SIGNAL = {"flame": "sparks"}          # 놓친 불꽃 -> 점화원 수동 입력 신호 (3축 버튼 '점화원 입력'과 같다)

    def _miss_check(self, det: str, zone: str) -> dict | None:
        """놓친 사람 · 보호구를 어느 영상 규칙의 위반으로 남길지 - rules.json area_checks 에서 그 탐지에 기대는 규칙."""
        from safety_monitor.engine import Engine
        cks = [c for c in self.rules.get("area_checks", []) if isinstance(c, dict) and "type" in c and Engine._check_det(c) == det]
        if not cks:
            return None
        mode_on = any(since is not None for _, since in self.eng.modes.get(zone, []))
        if det == "person":                    # 작업 모드가 켜져 있으면 '작업 중 진입' 규칙 먼저
            cks.sort(key=lambda c: 0 if (c.get("alert") == "mode_on") == mode_on else 1)
        return cks[0]

    def _miss_evidence(self, miss_id: str, ts: datetime) -> dict:
        """그 시각 영상 증거 - 버퍼에 남아 있으면 그 시각 앞뒤 클립 + 가장 가까운 프레임. 없으면 지금 프레임."""
        out = {}
        v = self.video
        clips = self.log.clips if self.log else None
        if v is None or clips is None or self.out_dir is None:
            return out
        t_ev = v.t - max(0.0, (self.eng.now - ts).total_seconds())
        if t_ev >= 0 and clips.buf and clips.buf[0][0] <= t_ev:
            clip, frame = clips.request(miss_id, t_ev)
            near = min(clips.buf, key=lambda x: abs(x[0] - t_ev))
            (self.out_dir / "frames").mkdir(parents=True, exist_ok=True)
            (self.out_dir / frame).write_bytes(near[1])
            out = {"clip_path": f"live/{self.sid}/{clip}", "frame_path": f"live/{self.sid}/{frame}", "video_t": round(t_ev, 1)}
        else:                                  # 버퍼보다 오래된 일 - 클립은 못 만든다. 지금 프레임만
            cam = (v.camera or {}).get("camera_id")
            b = self.frames.get(cam)
            if b:
                f = self.out_dir / "frames" / f"{miss_id}.jpg"
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(b)
                out = {"frame_path": f"live/{self.sid}/frames/{f.name}", "evidence_note": "그 시각 영상은 지나갔다 - 등록한 순간 프레임"}
        return out

    def handle_missed(self, row: dict, action: str, snap_id: str = "") -> dict:
        """
        등록한 미탐을 처리한다.
          now       지금 판정에 반영 - 불꽃은 점화원 신호, 사람 · 보호구는 그 규칙의 위반 기록(경보 단계)을 남긴다 + 증거
          evidence  그 시각 영상 증거(클립 · 프레임)만 붙인다
          record    기록만
        """
        out = {"action": action}
        ts = datetime.fromisoformat(row["ts"])
        if self.sid and self.video is not None:        # 이미지 로그는 처리 방식과 상관없이 영상이 돌면 늘 남긴다 (10/8)
            with self.lock:
                try:
                    from . import dataset
                    t_ev = self.video.t - max(0.0, (self.eng.now - ts).total_seconds())
                    # '일어난 시각'이 창을 연 시각 그대로면 그때 고정해 둔 그림, 고쳤으면 그 시각에 가장 가까운 원본 (10/8 오후)
                    made = self.pins.made_at(snap_id)
                    pinned = self.pins.get(snap_id) if made and abs((datetime.fromisoformat(made) - ts).total_seconds()) <= 2 else None
                    raw, view = pinned if pinned else (self.raw_frames.near(t_ev), self._view_near(t_ev))
                    if pinned and pinned[0] is not None:
                        t_ev = pinned[0][0]
                    out.update(dataset.save("missed", row["miss_id"], raw=raw, view=view,
                                            t_event=t_ev, meta={k: row.get(k) for k in ("det", "zone", "ts", "note", "by", "action", "sid", "scene")}
                                            | {"label": "missed"}))
                except Exception as ex:  # noqa: BLE001
                    self.note(f"미탐 이미지 저장 실패 - {ex}")
        if action == "record":
            return out
        if not self.sid:
            raise ValueError("세션이 돌 때만 판정 반영 · 증거 저장을 할 수 있다 - '기록만'으로 등록한다")
        with self.lock:
            out.update(self._miss_evidence(row["miss_id"], ts))
        if action != "now":
            return out
        det, zone = row["det"], row["zone"]
        why = f"관제자 미탐 등록 {row['miss_id']} · {row['by']}" + (f" — {row['note']}" if row.get("note") else "")
        if det in self.MISS_SIGNAL:
            notes = self.apply_signal(self.MISS_SIGNAL[det], zone, source="미탐 등록", note=why)
            out.update(signal=self.MISS_SIGNAL[det], result="점화원 신호 입력 - " + (" / ".join(notes) or "3축 판정에 반영"))
            return out
        with self.lock:
            ck = self._miss_check(det, zone)
            if ck is None:
                raise ValueError(f"'{det}' 를 위반으로 남길 영상 규칙이 없다 - '증거 저장'으로 등록한다")
            from safety_monitor.modes import label_mode
            ev = self.log.emit(kind="check", ts=self.eng.now, zone=zone, mode=label_mode(self.eng.modes.get(zone, [])),
                               violation_type=ck["violation"], level=ck.get("level", "경보"), alerted=True,
                               reason=why, response=ck.get("response", ""),
                               video_t=out.get("video_t", round(self.video.t, 2) if self.video else None),   # 영상이 돌면 이벤트 클립도 남는다
                               extra={"rule_mode": "미탐 등록 (수동)", "det": det, "manual": True, "miss_id": row["miss_id"]})
            self.note(f"{clock_text(self.eng.now)} 미탐 반영 - {zone} {ck['violation']} ({ck.get('level', '경보')}) · {why}")
        self._after_step()
        out.update(event_id=ev["event_id"] if ev else "", result=f"위반 기록 {ev['event_id'] if ev else ''} — {ck['violation']} · {ck.get('level', '경보')}")
        return out

    def clear_det_fp(self, dfp_id: str, *, by: str, undo_record: bool = False) -> bool:
        """오탐 처리를 끝낸다. undo_record=True 면 잘못 고른 것 - 기록도 취소한다."""
        from . import detfp
        with self.lock:
            hit = self.det_fp.remove(dfp_id)
            if undo_record:
                detfp.undo(dfp_id, by)
            self.note(f"{clock_text(self.eng.now)} 탐지 오탐 처리 해제 - {dfp_id}{' · 기록 취소' if undo_record else ''} · {by}")
            return hit

    def snapshot(self) -> dict:
        from . import feedback
        with self.lock:
            self.ensure()
            eng = self.eng
            zs = {z: self.zone_state(z) for z in eng.site.get("zones", {}) if not z.startswith("_")}
            nxt = self.schedule[self.sched_i] if self.sched_i < len(self.schedule) else None
            rows = list(self.log.rows) if self.log else []
            gates = {z: list(g) for z, g in eng.gates.items()}
            docs = {z: d for (f, z), d in eng.store.documents.items()}
            snap = {"sid": self.sid, "now": eng.now if self.sid else real_now(), "running": self.running, "speed": self.speed,
                    "meta": dict(self.meta), "zones": zs, "next": nxt, "rows": rows, "gates": gates, "docs": docs,
                    "video": bool(self.video), "video_note": self.video.person_note if self.video else "",
                    "video_pos": (self.video.t, self.video.dur) if self.video else None,
                    "scene_started": self.scene_started,
                    "scene": self.scene, "frames": dict(self.frames), "notes": list(self.notes),
                    "on": {k: v.ts for k, v in eng.store.on.items()}, "marks": {k: dict(v) for k, v in eng.store.marks.items()},
                    "measures": [(m.fact, m.zone, m.target, m.ts, m.value) for m in eng.store.measures],
                    "applied": list(self.rules.get("_applied", [])) if self.rules else [],
                    "dets": self.det_recent.list() if self.video else [],
                    "det_fp": self.det_fp.active()}
        snap["adjust"] = {z: feedback.zone_alert_level(z, snap["now"]) for z in zs}
        return snap


SESSION = LiveSession()


# ---------------------------------------------------------------------- 데이터 공간 (10/14)
# 세션의 기록 · 자동 인계 · 피드백 · 탐지 오탐 · 미탐 처리는 화면에서 무엇을 조회 중이든 세션의 데이터 공간으로 간다.
def _in_session_space(fn):
    import functools

    @functools.wraps(fn)
    def wrapped(self, *a, **kw):
        with dataspace.use(self.space):
            return fn(self, *a, **kw)
    return wrapped


for _name, _fn in list(vars(LiveSession).items()):
    if callable(_fn) and not _name.startswith("__") and _name not in ("reset", "_loop"):
        setattr(LiveSession, _name, _in_session_space(_fn))
