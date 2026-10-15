"""
엔진 — 패키지를 읽어서 돈다. 특정 공정 · 시나리오를 모른다.

    ① 트리거      apply(신호)             신호 사전대로 사실 저장소에 넣는다
    ② 상황 인식    modes.evaluate_modes    규칙의 when → 지금 켜진 모드
    ③ 작업 전 게이트 gates.run_gates        문서가 들어오면 대조
    ④ 감지 · 판정  update_video + 판정표    영상 사실(검출 · 인원) + 판정표 rows
    ⑤ 기록 · 알림  EventLog                무음 기록 · 중복 억제 · 전후 클립

영상 없이도 돈다(run_scenario.py) — tick(시각)으로 시간만 흘려도 만료 같은 조건이 판정된다.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from . import modes as M
from .checks import check_hits
from .conditions import Ctx, evaluate
from .detector import Det, Persistence
from .events import EventLog
from .facts import FactStore, apply_signal
from .fall import FallJudge
from .gates import GateResult, run_gates
from .judge import LEVELS, RANK, LevelState, eval_table, response
from .modes import expand_zones
from .signals import Signal


class Engine:
    def __init__(self, pkg, rules: dict, start: datetime, *, log: EventLog, scenario_dir: Path | None = None,
                 zones=None, detect_cfg: dict | None = None):
        self.pkg = pkg
        self.site = pkg.site
        self.signals = pkg.signals
        self.rules = rules
        self.now = start
        self.log = log
        self.scenario_dir = scenario_dir
        self.zones = zones                     # zones.Zones (영상일 때만)
        self.video_on = False
        self.video_t: float | None = None
        self.store = FactStore()
        self.levels: dict[tuple[str, str], LevelState] = {}
        self.mode_since: dict[tuple[str, str], datetime] = {}
        self.modes: dict[str, list] = {}
        self.gates: dict[str, list[GateResult]] = {}
        self.persons: list[Det] = []
        self.objects: dict[str, list[Det]] = {}
        self.ppe_items: dict[str, str] = {}         # 보호구 모델이 보는 것 {키: 이름} — 비어 있으면 모델 없음 (10/7)
        self.ppe: dict[str, dict] = {}              # 구역 → {보호구: {on: 착용, off: 미착용, skip: 작아서 안 봄}}
        self._dwell: dict[tuple, datetime] = {}
        # 구역 규칙(rules.json area_checks — 모드와 상관없이 영상으로 보는 규칙)이 지금 울리고 있는 것.
        # {구역: {위반: {level, violation, reason, response, since, last}}} — 사람이 잠깐 안 잡혀도 AREA_HOLD_S 동안은 유지한다
        self.area_alerts: dict[str, dict[str, dict]] = {}
        self._accidents: dict[tuple, datetime] = {}    # 영상이 확정한 사고 (구역, 위반) → 마지막 기록 시각 (10/13)
        dc = detect_cfg or pkg.detect
        pc = dc.get("persistence", {})
        self._pers_cfg = (pc.get("on_frames", 5), pc.get("off_frames", 15), pc.get("window_frames"))
        self.persistence: dict[tuple[str, str], Persistence] = {}
        self.fall = FallJudge(dc.get("fall"))      # 쓰러짐 (10/13)
        self.detect_polys = {"flame": dc.get("flame", {}).get("polygons", ["hazard"])}
        for x in dc.get("extra", []):
            self.detect_polys[x["name"]] = x.get("polygons", ["hazard", "work"])
        self.tables = {n: t for n, t in rules.get("judgments", {}).items() if not n.startswith("_")}
        self.table_zones = {n: expand_zones(t.get("zones", ["*"]), self.site) for n, t in self.tables.items()}

    def ctx(self, zone: str, **kw) -> Ctx:
        return Ctx(self, zone, self.now, **kw)

    # ================================================================== ① 트리거
    def apply(self, sig: Signal) -> list[str]:
        if sig.ts > self.now:
            self.now = sig.ts
        notes, docs = apply_signal(sig, self.signals, self.site, self.store, self.scenario_dir)
        spec = self.signals.get(sig.signal, {})
        # 측정 신호의 reset(방출 기록 지우기)은 측정값이 실제로 저장됐을 때만 본다 — '측정불가' · nan 처럼 버려진 입력이
        # 예전 적합값으로 해제 조건을 맞춰 확인된 방출을 지우지 않게 (STEP 02-8, signals.json gas_test._reset "측정 뒤")
        is_measure = any(a.get("do") == "measure" for a in (spec["do"] if isinstance(spec.get("do"), list) else [spec]))
        if "reset" in spec and sig.zone and (not is_measure or sig.extra.get("measure")):
            rs = spec["reset"]
            if evaluate(rs.get("if", True), self.ctx(sig.zone)).ok:
                n = 0
                for e in self.store.events:
                    if e.fact in rs.get("events", []) and e.zone == sig.zone and e.cleared_at is None and e.ts <= sig.ts:
                        e.cleared_at = sig.ts
                        n += 1
                if n:
                    notes.append(f"이전 {'/'.join(rs.get('events', []))} 기록 {n}건 해제")
        # 센서 이상 · 측정 실패와 그 복구를 관제 기록(kind=info, 참고)으로 남긴다 — 경보가 아니라 상태 기록 (STEP 02-10 A-3 · B-3)
        flt, rec = sig.extra.get("fault"), sig.extra.get("recovered")
        if (flt or rec) and sig.zone:
            what = f"{sig.label}" + (f" {sig.target}" if sig.target else "")
            self.log.emit(kind="info", ts=sig.ts, zone=sig.zone, mode=M.label_mode(self.modes.get(sig.zone, [])),
                          violation_type=f"{flt}" if flt else f"{rec} 복구", level=None, alerted=False,
                          reason=(f"{what} {flt} 기록 — 입력 {sig.value!r} · 판정에서 측정값으로 쓰지 않음" if flt
                                  else f"{what} {rec} 복구 — 유효 측정 {sig.value}"),
                          video_t=self.video_t,
                          extra={"measure_fault": {"fact": next((a.get('fact') for a in (spec['do'] if isinstance(spec.get('do'), list) else [spec])), None),
                                                   "target": sig.target, "state": "fault" if flt else "recovered",
                                                   "kind": flt or rec, "raw": None if sig.value is None else str(sig.value),
                                                   "ts": sig.ts.isoformat()}})
        self._refresh_modes()
        for d in docs:
            for g in run_gates(d, sig.zone, self, self.now):
                self.gates.setdefault(sig.zone, []).append(g)
                notes.append(g.message)
                if g.blocked:
                    gd = next(x for x in self.rules.get("gates", []) if x["id"] == g.gate_id)
                    self.log.emit(kind="gate", ts=sig.ts, zone=sig.zone, mode=M.label_mode(self.modes.get(sig.zone, [])),
                                  violation_type=gd.get("violation", g.gate_id), level="작업 전 차단", alerted=True,
                                  reason="; ".join(g.problems), response=gd.get("response", ""), video_t=self.video_t,
                                  extra={"gate_id": g.gate_id})
        self.evaluate()
        if any(a.get("do") == "accident" for a in (spec["do"] if isinstance(spec.get("do"), list) else [spec])):
            notes += self._accident(sig)
        return notes

    def tick(self, now: datetime):
        """시간만 흐른다 (측정 만료 · 체류 시간 같은 조건이 여기서 판정된다)."""
        if now > self.now:
            self.now = now
        self.evaluate()

    def _accident(self, sig: Signal) -> list[str]:
        z = sig.zone
        for (zone, tname), ls in self.levels.items():
            if zone != z:
                continue
            thr = self.tables[tname].get("accident_prevented_at", "최고 경보")
            if RANK[ls.level] >= RANK[thr]:
                msg = (f"{ls.raised_at:%H:%M} {ls.level}({tname})로 작업이 멈춘 상태 — "
                       f"이 사고는 일어나지 않는다고 본다 (가정)")
                self.log.emit(kind="info", ts=sig.ts, zone=z, mode=None, violation_type="사고_예방", level=None,
                              alerted=False, reason=msg, video_t=self.video_t)
                return [msg]
        self.log.emit(kind="accident", ts=sig.ts, zone=z, mode=None, violation_type=sig.label or sig.signal,
                      level=None, alerted=False, reason=sig.note or "사고 발생", video_t=self.video_t)
        return ["사고 발생 — 기록"]

    # ================================================================== ② 모드
    def _refresh_modes(self):
        self.modes = M.evaluate_modes(self, self.now)

    # ================================================================== ④ 영상
    def update_video(self, now: datetime, video_t: float, persons: list[Det], objects: dict[str, list[Det]]):
        if self.zones is None:                     # 10/14 — 영상이 이미 끝나 구역이 없다 (늦게 끝난 탐지) — 판정하지 않는다
            return
        self.now, self.video_t, self.video_on = now, video_t, True
        self.persons, self.objects = persons, objects
        self.fall.mark(persons)                    # 쓰러짐 박스 안에 있는 사람에게 p.fallen (10/13 — 판단은 fall.look 이 따로)
        Z = self.zones
        people: dict[str, list[set[str]]] = {}
        ppe: dict[str, dict] = {}
        for p in persons:
            p.polys = Z.locate(Z.ground_point(p.xyxy))
            if getattr(p, "no_zone", False):       # 관제자가 '구역 판정만 빼기'로 고른 사람 (10/8, control/detfp.py) - 사람 수에만 든다
                p.polys = []
            by_zone: dict[str, set[str]] = {}
            for q in p.polys:
                by_zone.setdefault(q.zone, set()).add(q.type)
            # 10/8 — 어느 폴리곤에도 안 든 사람은 그 카메라 구역의 사람으로 센다(종류 없음).
            # 예전에는 폴리곤 밖 사람이 대시보드 사람 수 · 보호구 수에서 빠져, 영상 위 PERSON 수와 달랐다.
            # 종류가 없어서 폴리곤 규칙(작업 구역 인원 · 위험구역 진입 …)에는 걸리지 않는다.
            if not by_zone and Z.camera_zone:
                by_zone[Z.camera_zone] = set()
            for z, types in by_zone.items():
                people.setdefault(z, []).append(types)
                for k, v in p.ppe.items():
                    h = ppe.setdefault(z, {}).setdefault(k, {"on": 0, "off": 0, "skip": 0})
                    h["on" if v else "skip" if v is None else "off"] += 1
        self.store.people = people
        self.ppe = ppe
        for name, dets in objects.items():
            want = set(self.detect_polys.get(name, ["hazard"]))
            if getattr(Z, "implicit", False):
                want.add("frame")           # 구역을 지정하지 않은 화면 — 화면 전체에서 검출을 확정한다 (10/8)
            hit = set()
            for d in dets:
                d.polys = Z.locate(Z.center(d.xyxy))
                hit |= {q.zone for q in d.polys if q.type in want}
            for z in {q.zone for q in Z.polys if q.type in want}:
                g = self.persistence.setdefault((name, z), Persistence(*self._pers_cfg))
                on = g.update(z in hit)
                rec = self.store.detections.setdefault((name, z), {"on": False, "since": None, "last": None})
                if on and not rec["on"]:
                    rec["since"] = now
                if on:
                    rec["last"] = now
                rec["on"] = on
        self._refresh_modes()
        self._run_checks()
        self.evaluate()

    def _run_checks(self):
        now = self.now
        hit_keys = set()
        for zone in (self.zones.zones() if self.zones else []):
            active = self.modes.get(zone, [])
            names = {n for n, _ in active}
            for mname, m in M.mode_items(self.rules):
                if zone not in expand_zones(m.get("zones"), self.site):
                    continue
                is_on = mname in names
                for ck in m.get("checks", []):
                    if not is_on and not ck.get("shadow_when_off"):
                        continue
                    for key, detail, tid in check_hits(ck, zone, self):
                        dk = (zone, mname, ck["violation"], key)
                        hit_keys.add(dk)
                        first = self._dwell.setdefault(dk, now)
                        if (now - first).total_seconds() < ck.get("dwell_s", 0):
                            continue
                        det = self._check_det(ck)
                        self.log.emit(kind="check", ts=now, zone=zone, mode=mname if is_on else M.label_mode(active),
                                      violation_type=ck["violation"], level=ck.get("level", "주의"), alerted=is_on,
                                      reason=detail + ("" if is_on else f" · '{mname}' 모드가 꺼져 있어 무음 기록"),
                                      response=ck.get("response", ""), track_id=tid,
                                      dedup=(zone, ck["violation"], key), video_t=self.video_t,
                                      extra={"rule_mode": mname, "det": det,
                                             "conf": self._evidence(zone, tid, det if det != "person" else None)})
        self._run_area_checks(hit_keys)
        for k in [k for k in self._dwell if k not in hit_keys]:
            self._dwell.pop(k)

    AREA_HOLD_S = 3.0

    def _run_area_checks(self, hit_keys: set):
        """
        구역 규칙 (rules.json 의 area_checks) — 작업 모드와 상관없이 영상으로 본다 (10/6).
          alert: always   늘 경보 (위험구역 상시 진입)
                 mode_on  그 구역에 작업 모드가 켜졌을 때만 경보, 꺼져 있으면 무음 기록 (위험구역 작업 중 진입)
        dwell_s 만큼 이어져야 위반이다. 울리는 동안은 area_alerts 에 남아 구역 단계 · 팝업에 쓰인다.
        """
        now = self.now
        for zone in (self.zones.zones() if self.zones else []):
            active = self.modes.get(zone, [])
            mode_on = any(since is not None for _, since in active)
            for ck in self.rules.get("area_checks", []):
                if not isinstance(ck, dict) or "type" not in ck or zone not in expand_zones(ck.get("zones", ["*"]), self.site):
                    continue
                alert = ck.get("alert", "always") == "always" or mode_on
                for key, detail, tid in check_hits(ck, zone, self):
                    dk = (zone, "_area", ck["violation"], key)
                    hit_keys.add(dk)
                    first = self._dwell.setdefault(dk, now)
                    if (now - first).total_seconds() < ck.get("dwell_s", 0):
                        continue
                    det = self._check_det(ck)
                    ev = self.log.emit(kind="check", ts=now, zone=zone, mode=M.label_mode(active),
                                  violation_type=ck["violation"], level=ck.get("level", "경보"), alerted=alert,
                                  reason=detail + ("" if alert else " · 작업 모드가 꺼져 있어 무음 기록"),
                                  response=ck.get("response", ""), track_id=tid,
                                  dedup=(zone, ck["violation"], key), video_t=self.video_t,
                                  extra={"rule_mode": "구역 규칙", "rule_label": ck.get("label", ck["violation"]), "det": det,
                                         "conf": self._evidence(zone, tid, det if det != "person" else None)})
                    if alert:
                        cur = self.area_alerts.setdefault(zone, {}).get(ck["violation"])
                        if cur is None or (now - cur["last"]).total_seconds() > self.AREA_HOLD_S:
                            cur = {"since": now}
                        cur.update(level=ck.get("level", "경보"), violation=ck["violation"], reason=detail,
                                   label=ck.get("label", ck["violation"]), response=ck.get("response", ""), last=now,
                                   override=bool(ck.get("override")))   # 10/13 — 같은 단계면 판정표보다 앞에 보인다 (쓰러짐)
                        self.area_alerts[zone][ck["violation"]] = cur
                    if ck.get("accident"):
                        self._detected_accident(zone, ck, detail, tid, ev)
        for zone, d in list(self.area_alerts.items()):
            for v in [v for v, a in d.items() if (now - a["last"]).total_seconds() > self.AREA_HOLD_S]:
                d.pop(v)
            if not d:
                self.area_alerts.pop(zone)

    ACCIDENT_GAP_S = 600

    def _detected_accident(self, zone: str, ck: dict, detail: str, tid, src_ev: dict | None = None):
        """
        영상이 확정한 사고(쓰러짐 · 끼임 — area_checks 에 "accident": true) → 사고 기록 (10/13).
        문서 자동화로 넘기면 '산업재해조사표' 안내가 된다(handoff.py). 신호로 들어온 사고(_accident)와 달리
        이미 최고 경보였어도 '예방됨'으로 보지 않는다 — 사람이 실제로 쓰러진 것을 봤기 때문이다.
        같은 구역 · 같은 사고는 ACCIDENT_GAP_S 초에 한 번만 남긴다 (추적 번호가 바뀌어도 한 건).
        """
        k = (zone, ck["violation"])
        last = self._accidents.get(k)
        if last is not None and (self.now - last).total_seconds() < self.ACCIDENT_GAP_S:
            return
        self._accidents[k] = self.now
        # 10/14 A-06 — 이 사고를 확정한 영상 기록(같은 순간 check)의 번호 · 프레임 · 클립을 그대로 묶는다.
        # 그 기록이 없으면(중복 억제로 안 남은 경우) 프레임 없이 둔다 — 다른 사건의 사진으로 대신하지 않는다
        link = {}
        if src_ev:
            link = {"source_event_id": src_ev.get("event_id"), "frame_path": src_ev.get("frame_path"),
                    "clip_path": src_ev.get("clip_path")}
        self.log.emit(kind="accident", ts=self.now, zone=zone, mode=None, violation_type=ck.get("label", ck["violation"]),
                      level=None, alerted=False, reason=f"영상 감지 — {detail}", track_id=tid, video_t=self.video_t,
                      extra={"rule_mode": "구역 규칙", "source": "영상", **link})

    def area_alert(self, zone: str) -> dict | None:
        """그 구역에서 지금 울리는 구역 규칙 중 가장 높은 것 (없으면 None)."""
        best = None
        for a in self.area_alerts.get(zone, {}).values():
            if (self.now - a["last"]).total_seconds() <= self.AREA_HOLD_S and (best is None or RANK[a["level"]] > RANK[best["level"]]):
                best = a
        return best

    # ================================================================== 탐지 신뢰도 (10/8)
    def _evidence(self, zone: str, track_id=None, item: str | None = None) -> dict:
        """
        이벤트 근거가 된 탐지의 신뢰도(모델 점수) — {"person": 0.82, "flame": 0.41, "helmet": 0.67}.
        추적 번호가 있으면 그 사람, 없으면 그 구역에서 가장 높은 값. 영상이 없으면(신호 판정) 빈 dict.
        """
        if not self.video_on:
            return {}
        cz = self.zones.camera_zone if self.zones else None
        ppl = [p for p in self.persons if any(q.zone == zone for q in p.polys) or (not p.polys and cz == zone)]
        if track_id is not None:
            ppl = [p for p in ppl if p.track_id == track_id] or ppl
        out = {}
        if ppl:
            out["person"] = round(max(p.conf for p in ppl), 2)
            if item:
                cs = [p.ppe_conf[item] for p in ppl if p.ppe_conf.get(item) is not None]
                if cs:
                    out[item] = round(max(cs), 2)
        fl = [d.conf for d in self.objects.get("flame", []) if any(q.zone == zone for q in d.polys)]
        if fl:
            out["flame"] = round(max(fl), 2)
        return out

    @staticmethod
    def _check_det(ck: dict) -> str:
        """영상 규칙 하나가 어떤 탐지에 기대나 — 보호구 규칙이면 그 보호구, 나머지는 사람."""
        if ck.get("type") == "no_helmet":
            return "helmet"
        if ck.get("type") == "no_ppe":
            return ck.get("item", "helmet")
        return "person"

    # ================================================================== ④ 판정표
    def evaluate(self):
        self._refresh_modes()
        for tname, table in self.tables.items():
            for z in self.table_zones[tname]:
                ls = self.levels.setdefault((z, tname), LevelState())
                res = eval_table(tname, table, self.ctx(z, raised_at=ls.raised_at))
                self._update_level(z, tname, table, ls, res)

    def _update_level(self, zone: str, tname: str, table: dict, ls: LevelState, res):
        ls.result = res
        cur, new = RANK[ls.level], RANK[res.level]
        if new > cur or (new == cur and new > 0 and res.violation != ls.violation):
            ls.level, ls.row, ls.violation = res.level, res.row, res.violation
            ls.raised_at, ls.lower_since = self.now, None
            ls.history.append((self.now, res.level, res.row))
            active = self.modes.get(zone, [])
            alerted = M.alerting(self.rules, active, tname)
            c = self.ctx(zone, axes=res.axes)
            present = evaluate(table["presence"], c).ok if "presence" in table else bool(self.store.people.get(zone))
            # 점화원을 영상 불꽃 검출이 켰으면 그 탐지에 기댄 기록이다 (10/8). 신호(버튼 · 센서)로만 켜졌으면 탐지 없음
            flame_on = bool(self.store.detections.get(("flame", zone), {}).get("on"))
            self.log.emit(kind="stage", ts=self.now, zone=zone, mode=M.label_mode(active), violation_type=res.violation,
                          level=res.level, alerted=alerted, reason=res.reason, row=res.row,
                          response=response(table, res.level, present),
                          axes={a.name: a.state for a in res.axes.values()}, video_t=self.video_t,
                          extra={"table": tname, "det": "flame" if flame_on else None, "conf": self._evidence(zone),
                                 # 세부 원인 — 판정 줄에 "causes" 가 있을 때만 (STEP 03-3 보완). 사건 시각의 기록을 그대로 남긴다
                                 **({"causes": res.causes} if res.causes is not None else {}),
                                 **({"title": res.title} if res.title else {})})
        elif new < cur:
            lw = table.get("lower", {})
            ls.lower_since = ls.lower_since or self.now
            hold = timedelta(minutes=float(lw.get("hold_min", 5)))
            ok = evaluate(lw.get("when", True), self.ctx(zone, axes=res.axes, raised_at=ls.raised_at)).ok
            if ok and self.now - ls.lower_since >= hold:
                ls.level = LEVELS[cur - 1]
                if RANK[res.level] == cur - 1:
                    ls.row, ls.violation = res.row, res.violation
                ls.lower_since = self.now
                ls.history.append((self.now, ls.level, ls.row))
        else:
            ls.lower_since = None

    # ================================================================== 화면 · 요약용
    def zone_level(self, zone: str) -> tuple[str, LevelState | None, str | None]:
        """그 구역의 판정표들 중 가장 높은 단계."""
        best, bl, bt = "정상", None, None
        for (z, t), ls in self.levels.items():
            if z == zone and (bl is None or RANK[ls.level] > RANK[best]):
                best, bl, bt = ls.level, ls, t
        return best, bl, bt

    def snapshot(self, zone: str) -> dict:
        active = self.modes.get(zone) or [(M.default_mode(self.rules), None)]
        tables = [(t, self.levels[(zone, t)]) for t in self.tables if (zone, t) in self.levels]
        return {"zone": zone, "now": self.now, "modes": active, "view": M.merged_view(self.rules, active),
                "tables": tables, "gates": self.gates.get(zone, []), "people": self.store.people.get(zone, []),
                "persistence": {n: g for (n, z), g in self.persistence.items() if z == zone}}
