"""
탐지 신뢰도 — 판정 기준 · 오탐 · 미탐 (10/8)

  판정 기준표   탐지마다 임계값 · 후처리 값과 '이 값을 고른 이유'. 일부는 화면에서 바꾼다(다음 세션부터 적용)
                바꾼 값은 사업장 패키지 detect.json 에 덮어쓰고, 누가 · 언제 · 무엇을 · 왜 바꿨는지 criteria_changes.jsonl 에 남는다
  안전 영향표   탐지마다 놓쳤을 때(미탐) · 잘못 울렸을 때(오탐) 무슨 일이 생기나, 그래서 어느 쪽을 줄이도록 잡았나
  오탐 사유     이벤트 로그의 오탐 표시는 고정 목록에서 사유를 고른다(기타는 직접 적는다)
  탐지 오탐     실시간 관제 영상에서 지금 잡힌 탐지를 오탐으로 고른 기록 - detfp.py (10/8). 사유 목록은 같다
  미탐 기록     시스템이 놓친 것을 관제자가 등록한다 — control/records/missed.jsonl (추가 전용, 취소도 새 줄)
                등록할 때 처리를 고른다 (10/8 오후): 지금 판정에 반영 · 증거 저장 · 기록만 (MISS_ACTIONS)
                처리 결과(이벤트 번호 · 클립 · 프레임)는 같은 미탐 번호로 update 줄을 덧붙인다
  조정 제안     같은 탐지의 미탐 · 탐지 오탐이 쌓이면 판정 기준을 고쳐 보라고 알린다 (SUGGEST) — 기준값은 사람이 바꾼다
  통계          히트맵 · 통계의 '오탐 · 미탐' 칸 — 탐지 유형별 오탐률 · 미탐 건수 · 신뢰도 평균 · 오탐 사유
  성능 평가     monitor_engine/evaluate.py 가 정답 CSV 와 비교한 결과(outputs/eval/*/summary.json)를 읽어 보인다

탐지 유형은 넷 — person(사람) · flame(불꽃 · 점화원) · helmet(안전모) · vest(안전조끼).
이벤트에는 엔진이 남긴 det(어느 탐지에 기댄 기록인가) · conf(근거 탐지의 모델 점수)가 있다. 10/8 이전 기록은 위반 이름으로 나눈다.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .common import RECORD_DIR, append_jsonl, package, package_changed, package_dir, read_jsonl, zone_name

DET = {"person": "사람", "flame": "불꽃 (점화원)", "helmet": "안전모", "vest": "안전조끼"}
FP_REASONS = ["조명 · 반사", "가림 · 겹침", "너무 작음 · 멀리", "비슷한 색 · 물체", "구역 경계 · 위치 오차", "모델 오인식", "기타"]
MISSED = RECORD_DIR / "missed.jsonl"
MISS_ACTIONS = [("now", "지금 판정에 반영 + 증거 저장 — 불꽃은 점화원 신호, 사람 · 보호구는 위반 기록(경보)"),
                ("evidence", "증거 저장 — 그 시각 영상 클립 · 프레임을 붙인다 (판정은 그대로)"),
                ("record", "기록만 — 통계에만 들어간다")]
SUGGEST = {"days": 7, "missed": 3, "det_fp": 5}      # 기준 조정 제안 — 최근 days 일에 미탐 · 탐지 오탐이 이만큼 쌓이면
CHANGES = RECORD_DIR / "criteria_changes.jsonl"


# ---------------------------------------------------------------------- 이벤트 → 탐지 유형

def _tag() -> str:
    """데이터 공간 태그 (10/14) — 공간끼리 번호가 겹치지 않게. 사용자 실행 데이터는 빈 값."""
    from dataspace import id_tag
    return id_tag()

def violation_dets() -> dict[str, str]:
    """위반 이름 → 탐지 유형. rules.json 의 영상 규칙(area_checks · 모드 checks)에서 만든다."""
    from safety_monitor.engine import Engine
    rules = package().rules_base
    out = {}
    cks = [c for c in rules.get("area_checks", []) if isinstance(c, dict) and "type" in c]
    for m in rules.get("modes", {}).values():
        if isinstance(m, dict):
            cks += [c for c in m.get("checks", []) if isinstance(c, dict) and "type" in c]
    for c in cks:
        out[c["violation"]] = Engine._check_det(c)
    return out


def det_of(e: dict, vmap: dict | None = None) -> str | None:
    """이 기록이 어느 탐지에 기댄 것인가. 신호(버튼 · 센서)로만 판정된 기록은 None."""
    if "det" in e:
        return e.get("det")
    vt = e.get("violation_type") or ""
    vmap = vmap if vmap is not None else violation_dets()
    if vt in vmap:
        return vmap[vt]
    if "안전모" in vt:
        return "helmet"
    if "조끼" in vt:
        return "vest"
    if "점화원" in vt or "화재감시자" in vt:
        return "flame" if "점화원" in vt else "person"
    if "진입" in vt or "인원" in vt or "2인" in vt:
        return "person"
    return None


def thresholds() -> dict[str, dict]:
    """탐지마다 지금 쓰는 신뢰도 기준 — 이벤트 상세 · 판정 기준표가 쓴다."""
    d = package().detect
    fl = d.get("flame", {})
    color = fl.get("backend", "color") == "color"
    return {"person": {"min": d.get("person", {}).get("conf"), "what": "사람 모델 점수"},
            "flame": {"min": None if color else fl.get("yolo", {}).get("conf"),
                      "what": "색 검출 점수 (불꽃 점 크기로 매긴 값 — 모델 점수 아님)" if color else "불꽃 모델 점수"},
            "helmet": {"min": d.get("ppe", {}).get("conf"), "what": "보호구 모델 점수"},
            "vest": {"min": d.get("ppe", {}).get("conf"), "what": "보호구 모델 점수"}}


def conf_rows(e: dict) -> dict:
    """이벤트 상세의 '탐지 신뢰도' 칸."""
    det = det_of(e)
    conf = e.get("conf")
    if conf is None:
        note = "기록 없음 — 신뢰도를 남기기 전(10/8 이전) 기록이거나 예시 데이터" if det else "영상 탐지가 아니라 신호 · 입력으로 판정한 기록"
        return {"det": DET.get(det, ""), "rows": [], "note": note}
    th = thresholds()
    order = [det] + [k for k in ("person", "flame", "helmet", "vest") if k != det]
    rows = [{"k": k, "label": DET[k], "v": conf[k], "min": th[k]["min"], "what": th[k]["what"], "main": k == det}
            for k in order if k in conf]
    note = "" if rows else ("영상에 근거 탐지가 잡히지 않은 순간의 기록 (신호로 켜진 축 · 유지 중 경보)" if det else "영상 탐지가 아니라 신호 · 입력으로 판정한 기록")
    return {"det": DET.get(det, ""), "rows": rows, "note": note}


# ---------------------------------------------------------------------- 판정 기준표 (3 · 4)
# key = detect.json 경로(점으로) 또는 rules:<위반 이름>.dwell_s · engine:area_hold (읽기 전용)
CRITERIA = [
    {"key": "person.conf", "det": "person", "label": "사람 검출 신뢰도", "edit": True, "min": 0.1, "max": 0.9, "step": 0.05,
     "means": "사람 모델 점수가 이 값 이상이어야 사람으로 본다",
     "why": "사람을 놓치면 위험구역 진입 · 2인 1조를 못 본다(미탐이 더 위험). 그래서 낮게 두고, 잘못 잡은 사람은 아래 머무름 시간이 한 번 더 거른다."},
    {"key": "rules:위험구역_진입.dwell_s", "det": "person", "label": "위험구역 진입 머무름", "unit": "초",
     "means": "발 위치가 위험구역(상시) 안에 이만큼 이어져야 진입으로 본다",
     "why": "발 위치가 경계에서 흔들리거나 스쳐 지나가는 사람으로 경보가 울리지 않게. 진입을 알리기에 늦지 않은 시간으로 잡았다. rules.json area_checks 에서 고친다."},
    {"key": "rules:작업중_위험구역_진입.dwell_s", "det": "person", "label": "작업 중 위험구역 진입 머무름", "unit": "초",
     "means": "위험구역(작업 중)에 이만큼 이어져야 진입 (작업 모드가 켜졌을 때만 경보)",
     "why": "위와 같다. rules.json area_checks 에서 고친다."},
    {"key": "engine:area_hold", "det": "person", "label": "구역 경보 유지", "unit": "초",
     "means": "사람이 잠깐 안 잡혀도 이 시간 동안은 구역 경보를 유지한다",
     "why": "가림 · 한두 프레임 미탐으로 경보가 꺼졌다 켜졌다 하지 않게. 엔진 코드(engine.py AREA_HOLD_S)에 있다."},
    {"key": "flame.backend", "det": "flame", "label": "불꽃 검출 방식", "text": True,
     "means": "color = 색 · 밝기 · 움직임으로 찾는다(학습 모델 아님) · yolo = 불꽃 모델",
     "why": "불꽃 학습 모델(models/fire.pt)이 아직 없어 색 검출을 쓴다. 10/8 조정 — AI 생성 시연 영상 세 개에서 그라인더 불티를 19.9~20.7초에 점화원으로 확정, 그 전 오탐 0 (패키지 detect.json 기록)."},
    {"key": "flame.color.v_min", "det": "flame", "label": "불꽃 후보 밝기", "edit": True, "min": 50, "max": 255, "step": 5, "int": True,
     "means": "이 밝기(V, 0~255) 이상인 점만 불꽃 후보",
     "why": "어두운 불티 끝까지 잡으려고 200 → 150 으로 낮췄다(10/8). 높이면 오탐(밝은 조명 · 반사)이 줄고 미탐이 는다."},
    {"key": "flame.color.s_max", "det": "flame", "label": "불꽃 후보 채도 상한", "edit": True, "min": 50, "max": 255, "step": 5, "int": True,
     "means": "채도가 이 값보다 높으면 불꽃에서 뺀다",
     "why": "형광 주황 작업복(채도 190~220)을 불티(120~150)와 나누려고 170 으로 잡았다(10/8)."},
    {"key": "flame.color.motion_min", "det": "flame", "label": "불꽃 후보 움직임", "edit": True, "min": 0, "max": 100, "step": 1, "int": True,
     "means": "앞 프레임과 이만큼 이상 달라진 점만 불꽃 후보 (가만히 있는 주황 물체를 뺀다)",
     "why": "움직임이 작은 불티까지 잡으려고 25 → 15 로 낮췄다(10/8)."},
    {"key": "flame.yolo.conf", "det": "flame", "label": "불꽃 모델 신뢰도", "edit": True, "min": 0.1, "max": 0.9, "step": 0.05,
     "means": "불꽃 모델(yolo)로 바꿨을 때의 점수 기준",
     "why": "지금은 색 검출이라 쓰이지 않는다. 불꽃 모델을 붙이면 이 값부터 정한다."},
    {"key": "persistence.on_frames", "det": "flame", "label": "불꽃 확정 — 잡힌 횟수", "edit": True, "min": 1, "max": 30, "step": 1, "int": True,
     "means": "최근 (아래 창) 번 탐지 중 이 횟수만큼 잡혀야 점화원으로 확정",
     "why": "불티는 깜빡여서 '5번 연속'이 잘 안 채워진다 — 8번 중 4번으로 바꿨다(10/8). 한두 프레임 반짝이는 반사는 여기서 걸러진다."},
    {"key": "persistence.window_frames", "det": "flame", "label": "불꽃 확정 — 보는 창", "edit": True, "min": 1, "max": 60, "step": 1, "int": True,
     "means": "확정을 판단할 때 보는 최근 탐지 횟수",
     "why": "위와 같다. 비우면 '연속 N번'으로 본다."},
    {"key": "persistence.off_frames", "det": "flame", "label": "불꽃 해제", "edit": True, "min": 1, "max": 120, "step": 1, "int": True,
     "means": "이 횟수만큼 연달아 안 잡혀야 점화원을 끈다",
     "why": "작업자 몸에 잠깐 가려져도 점화원이 꺼지지 않게 길게 둔다(미탐 쪽을 줄인다)."},
    {"key": "ppe.conf", "det": "helmet", "label": "보호구 검출 신뢰도 (안전모 · 조끼)", "edit": True, "min": 0.1, "max": 0.9, "step": 0.05,
     "means": "보호구 모델 점수가 이 값 이상이어야 착용 · 맨머리 근거로 쓴다",
     "why": "미착용 규칙은 주의 단계라 잦은 오경보가 더 해롭다(경보 피로). 그래서 한 번의 점수가 아니라 아래 다수결 · 확정 횟수와 같이 본다."},
    {"key": "ppe.confirm_n", "det": "helmet", "label": "미착용 확정 횟수", "edit": True, "min": 1, "max": 10, "step": 1, "int": True,
     "means": "보호구가 안 보인 판정이 이만큼 쌓여야 미착용 — 그 전에는 '판단 보류'",
     "why": "한 프레임 못 본 것(고개 숙임 · 뒤돌아섬)으로 미착용 경보가 나지 않게."},
    {"key": "ppe.min_person_px", "det": "helmet", "label": "보호구 판단 최소 사람 크기", "unit": "px", "edit": True, "min": 10, "max": 200, "step": 5, "int": True,
     "means": "사람 키가 이보다 작으면 보호구를 판단하지 않는다 (미착용으로 세지 않는다)",
     "why": "멀리 있는 작은 사람은 모델이 안전모 · 조끼를 못 봐 미착용 오탐이 난다."},
    {"key": "ppe.items.helmet.bright.min_ratio", "det": "helmet", "label": "안전모 밝기 확인", "edit": True, "min": 0, "max": 1, "step": 0.05,
     "means": "안전모로 본 박스 윗부분에 밝거나 색 있는 점이 이 비율 이상이어야 안전모 (어두우면 머리카락)",
     "why": "PPE.mp4(495건)에서 맨머리를 안전모로 본 것 60 → 0, 안전모를 맨머리로 본 것 0 → 4 (10/7). 검정 · 짙은 남색 안전모는 맨머리로 볼 수 있다."},
    {"key": "rules:안전모_미착용.dwell_s", "det": "helmet", "label": "안전모 미착용 머무름", "unit": "초",
     "means": "미착용이 이만큼 이어져야 기록한다",
     "why": "잠깐의 판정 흔들림으로 기록이 쌓이지 않게. rules.json area_checks 에서 고친다."},
    {"key": "ppe.items.vest.color.min_ratio", "det": "vest", "label": "조끼 색 확인", "edit": True, "min": 0, "max": 1, "step": 0.05,
     "means": "몸통에 형광 주황 · 연두가 이 비율 이상이면 모델이 못 잡아도 착용",
     "why": "PPE.mp4 에서 모델만으로는 조끼 미착용 오탐 41%, 색을 같이 보면 4% (10/7). 파랑 · 검정 조끼는 색으로 못 잡는다."},
    {"key": "rules:안전조끼_미착용.dwell_s", "det": "vest", "label": "안전조끼 미착용 머무름", "unit": "초",
     "means": "미착용이 이만큼 이어져야 기록한다",
     "why": "안전모와 같다. rules.json area_checks 에서 고친다."},
    {"key": "event.cooldown_s", "det": "", "label": "같은 위반 다시 기록", "unit": "초", "edit": True, "min": 0, "max": 600, "step": 5, "int": True,
     "means": "같은 구역 · 같은 위반 · 같은 사람은 이 시간 안에 다시 기록하지 않는다",
     "why": "같은 상황이 이어지는 동안 기록 · 팝업이 쏟아지지 않게(경보 피로). 경보 단계 자체는 계속 유지된다."},
]


def _get(d: dict, path: str):
    for k in path.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def _value(key: str):
    if key.startswith("rules:"):
        vt, field = key[6:].rsplit(".", 1)
        ck = next((c for c in package().rules_base.get("area_checks", []) if isinstance(c, dict) and c.get("violation") == vt), None)
        return ck.get(field) if ck else None
    if key == "engine:area_hold":
        from safety_monitor.engine import Engine
        return Engine.AREA_HOLD_S
    return _get(package().detect, key)


def criteria() -> list[dict]:
    """판정 기준표 — 지금 쓰는 값과 이유."""
    return [{**c, "det_t": DET.get(c["det"], "공통"), "value": _value(c["key"]), "edit": bool(c.get("edit"))} for c in CRITERIA]


def set_criteria(changes: dict, by: str, reason: str) -> dict:
    """
    판정 기준 바꾸기 — 사업장 패키지 detect.json 에 덮어쓴다(시스템 기본 monitor_engine/config/detect.json 은 그대로).
    새 세션 · 영상을 다시 틀 때부터 쓰인다. 바뀐 줄마다 criteria_changes.jsonl 에 한 줄.
    """
    if not by.strip():
        raise ValueError("변경자 이름이 필요하다")
    if not reason.strip():
        raise ValueError("바꾸는 이유를 적는다 — 판정 기준 변경 이력에 남는다")
    spec = {c["key"]: c for c in CRITERIA if c.get("edit")}
    p = package_dir() / "detect.json"
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    done = []
    for key, raw in changes.items():
        c = spec.get(key)
        if c is None:
            raise ValueError(f"화면에서 바꿀 수 없는 값 — {key}")
        try:
            v = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{c['label']}: 숫자를 넣는다") from None
        if not (c["min"] <= v <= c["max"]):
            raise ValueError(f"{c['label']}: {c['min']} ~ {c['max']} 사이로 넣는다")
        v = int(round(v)) if c.get("int") else round(v, 3)
        old = _value(key)
        if old == v:
            continue
        d = data
        parts = key.split(".")
        for k in parts[:-1]:
            d = d.setdefault(k, {})
        d[parts[-1]] = v
        done.append({"key": key, "label": c["label"], "old": old, "new": v})
    if not done:
        return {"changed": [], "msg": "바뀐 값이 없다"}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    package_changed()
    now = datetime.now().isoformat(timespec="seconds")
    for x in done:
        append_jsonl(CHANGES, {**x, "ts": now, "by": by.strip(), "reason": reason.strip()})
    return {"changed": done, "msg": " · ".join(f"{x['label']} {x['old']} → {x['new']}" for x in done)
            + " — 사업장 패키지 detect.json 에 저장했다. 새 세션(영상 다시 재생)부터 적용된다"}


def criteria_history(n: int = 50) -> list[dict]:
    return list(reversed(read_jsonl(CHANGES)))[:n]


# ---------------------------------------------------------------------- 오탐 · 미탐 안전 영향 (12)
IMPACT = [
    {"det": "person", "miss": "위험구역 안 작업자 · 2인 1조 미준수를 못 본다 — 끼임 · 폭발 노출 상태에서 경보가 없다",
     "false": "불필요한 퇴거 지시 · 경보. 잦으면 관제자가 경보를 무시하게 된다",
     "prefer": "미탐 줄이기", "how": "신뢰도 기준을 낮게 · 오탐은 머무름 시간으로 거르고 · 잠깐 가려져도 구역 경보 유지 (값은 위 판정 기준표)"},
    {"det": "flame", "miss": "점화원 + 축적(최고 경보)을 놓친다 — 폭발 직전 상태에서 작업중지가 안 나간다",
     "false": "화기 작업 모드가 잘못 켜지고 점화원 경보가 뜬다 — 작업이 불필요하게 멈춘다",
     "prefer": "미탐 줄이기", "how": "밝기 · 움직임 기준을 낮춰 어두운 불티까지 · 8번 중 4번으로 확정 · 해제는 15번 연속 안 잡혀야 · 놓치면 3축 신호의 점화원 입력(수동)이 폴백"},
    {"det": "helmet", "miss": "안전모를 안 쓴 사람을 못 잡는다 — 두부 보호 누락 (주의 단계 규칙)",
     "false": "쓴 사람을 미착용으로 잡는다 — 주의 경보가 쏟아지면 진짜 경보까지 무시된다(경보 피로)",
     "prefer": "오탐 줄이기", "how": "다수결 · 3번 쌓여야 미착용 · 밝기 확인 · 작은 사람은 판단 보류 · 머무름 3초"},
    {"det": "vest", "miss": "조끼를 안 입은 사람을 못 잡는다 — 차량 · 크레인 동선에서 잘 안 보인다 (주의 단계 규칙)",
     "false": "입은 사람을 미착용으로 잡는다 — 안전모와 같은 경보 피로",
     "prefer": "오탐 줄이기", "how": "한 번이라도 보이면 착용 · 형광색 확인 · 3번 쌓여야 미착용 · 머무름 3초"},
]


def impact() -> list[dict]:
    return [{**x, "det_t": DET[x["det"]]} for x in IMPACT]


# ---------------------------------------------------------------------- 미탐 기록 (5)
def add_missed(body: dict) -> dict:
    """놓친 것 등록 — 언제(그 일이 일어난 시각) · 어디서 · 무엇을 놓쳤나 · 누가. 원본 관제 기록은 건드리지 않는다."""
    det = body.get("det")
    if det not in DET:
        raise ValueError("놓친 탐지 종류를 고른다 (사람 · 불꽃 · 안전모 · 안전조끼)")
    zone = body.get("zone")
    if not zone:
        raise ValueError("구역을 고른다")
    by = str(body.get("by") or "").strip()
    if not by:
        raise ValueError("등록자 이름이 필요하다")
    ts = str(body.get("ts") or "").strip().replace(" ", "T")
    try:
        t = datetime.fromisoformat(ts)
    except ValueError:
        raise ValueError("시각은 2026-10-08 14:05:30 처럼 적는다") from None
    action = str(body.get("action") or "record")
    if action not in dict(MISS_ACTIONS):
        raise ValueError("처리 방식을 고른다")
    rows = read_jsonl(MISSED)
    n = sum(1 for r in rows if not r.get("undo") and not r.get("update")) + 1
    row = {"miss_id": f"MS-{t:%m%d%H%M}-{_tag()}{n:03d}", "ts": t.isoformat(timespec="seconds"), "zone": zone, "det": det,
           "note": str(body.get("note") or "").strip(), "by": by, "sid": body.get("sid") or "",
           "scene": body.get("scene") or "", "video_t": body.get("video_t"),
           "action": action, "action_label": dict(MISS_ACTIONS)[action].split(" — ")[0],
           "recorded_at": datetime.now().isoformat(timespec="seconds"), "undo": False}
    append_jsonl(MISSED, row)
    return row


def missed_result(miss_id: str, result: dict) -> dict:
    """처리 결과(이벤트 번호 · 클립 · 프레임 · 오류)를 덧붙인다 — 원래 줄은 고치지 않는다."""
    return append_jsonl(MISSED, {"miss_id": miss_id, "update": True, **result,
                                 "recorded_at": datetime.now().isoformat(timespec="seconds")})


def undo_missed(miss_id: str, by: str) -> dict:
    if not by.strip():
        raise ValueError("취소한 사람 이름이 필요하다")
    if miss_id not in {r["miss_id"] for r in list_missed()}:
        raise ValueError(f"없는 미탐 기록 — {miss_id}")
    return append_jsonl(MISSED, {"miss_id": miss_id, "undo": True, "by": by.strip(),
                                 "recorded_at": datetime.now().isoformat(timespec="seconds")})


def list_missed() -> list[dict]:
    """취소되지 않은 미탐 기록 (최신순)."""
    out: dict[str, dict] = {}
    for r in read_jsonl(MISSED):
        if r.get("update"):
            if r["miss_id"] in out:
                out[r["miss_id"]] = {**out[r["miss_id"]], **{k: v for k, v in r.items() if k not in ("update", "recorded_at")}}
        elif r.get("undo"):
            out.pop(r["miss_id"], None)
        else:
            out[r["miss_id"]] = r
    rows = sorted(out.values(), key=lambda r: r["ts"], reverse=True)
    return [{**r, "det_t": DET.get(r["det"], r["det"]), "zname": zone_name(r["zone"])} for r in rows]


def suggestions(now: datetime | None = None) -> list[dict]:
    """
    기준 조정 제안 — 최근 SUGGEST['days'] 일에 같은 탐지의 미탐이 쌓이면 '놓치지 않게', 탐지 오탐이 쌓이면 '덜 울리게'.
    제안만 한다. 판정 기준표에서 값을 바꾸는 것은 사람이 사유를 적고 한다.
    """
    from datetime import timedelta
    from .detfp import list_records as det_fp_records
    now = now or datetime.now()
    since = now - timedelta(days=SUGGEST["days"])
    out = []
    for k, label in DET.items():
        ms = [m for m in list_missed() if m["det"] == k and datetime.fromisoformat(m["ts"]) >= since]
        fp = [r for r in det_fp_records() if r["det"] == k and datetime.fromisoformat(r["ts"]) >= since]
        if len(ms) >= SUGGEST["missed"]:
            out.append({"det": k, "kind": "missed", "n": len(ms),
                        "text": f"{label} 미탐 {len(ms)}건 (최근 {SUGGEST['days']}일) — 놓치지 않게: 신뢰도 기준을 낮추거나 머무름 · 다수결 값을 줄여 본다"})
        if len(fp) >= SUGGEST["det_fp"]:
            out.append({"det": k, "kind": "det_fp", "n": len(fp),
                        "text": f"{label} 탐지 오탐 {len(fp)}건 (최근 {SUGGEST['days']}일) — 덜 울리게: 신뢰도 기준을 올리거나 머무름 값을 늘려 본다. 미탐 쪽 안전 영향을 같이 본다"})
    return out


# ---------------------------------------------------------------------- 통계 (7)
def _avg(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 2) if xs else None


def view(events: list[dict], a: datetime, b: datetime, pa: datetime, src: str = "", zone: str = "") -> dict:
    """
    히트맵 · 통계의 '오탐 · 미탐' 칸. 기간 (a, b] · 직전 같은 기간 (pa, a].
      탐지 기록   그 탐지에 기댄 감지 기록(무음 기록 포함, 오탐 표시도 포함해서 센다 — 오탐률의 분모)
      오탐률      오탐 표시 / 탐지 기록
      미탐        관제자가 등록한 미탐 기록 수
      신뢰도      근거 탐지 점수 평균 — 오탐 표시된 기록 vs 아닌 기록 (낮은 점수에서 오탐이 나는지 본다)
      탐지 오탐   실시간 관제에서 탐지 하나를 오탐으로 고른 수 (10/8 - 이벤트 기록이 되기 전 단계, 오탐률 분모에는 안 넣는다)
    """
    from .detfp import list_records as det_fp_records
    from .common import detections
    from .stats import _keep
    vmap = violation_dets()
    det_evs = [e for e in detections(events) if _keep(e, src, zone)]
    miss = [m for m in list_missed() if (not zone or zone == "전체" or m["zone"] == zone) and src != "sample"]
    dfp = [r for r in det_fp_records() if (not zone or zone == "전체" or r["zone"] == zone) and src != "sample"]

    def in_(t, x, y):
        return x < t <= y
    rows = []
    reasons: dict[str, int] = {}
    for k, label in DET.items():
        cur = [e for e in det_evs if in_(e["_ts"], a, b) and det_of(e, vmap) == k]
        prev = [e for e in det_evs if in_(e["_ts"], pa, a) and det_of(e, vmap) == k]
        fp = [e for e in cur if e.get("false_positive")]
        ms = [m for m in miss if m["det"] == k and in_(datetime.fromisoformat(m["ts"]), a, b)]
        ms_prev = [m for m in miss if m["det"] == k and in_(datetime.fromisoformat(m["ts"]), pa, a)]
        conf_fp = [e["conf"][k] for e in fp if isinstance(e.get("conf"), dict) and k in e["conf"]]
        conf_ok = [e["conf"][k] for e in cur if not e.get("false_positive") and isinstance(e.get("conf"), dict) and k in e["conf"]]
        dfp_cur = [r for r in dfp if r["det"] == k and in_(datetime.fromisoformat(r["ts"]), a, b)]
        for e in fp:
            r = e.get("fp_cat") or "사유 미분류"
            reasons[r] = reasons.get(r, 0) + 1
        for x in dfp_cur:
            r = x.get("cat") or "사유 미분류"
            reasons[r] = reasons.get(r, 0) + 1
        rows.append({"det": k, "label": label, "n": len(cur), "fp": len(fp),
                     "fp_rate": round(len(fp) / len(cur) * 100, 1) if cur else None,
                     "fp_prev": sum(1 for e in prev if e.get("false_positive")) if prev else None,
                     "missed": len(ms), "missed_prev": len(ms_prev), "det_fp": len(dfp_cur),
                     "conf_ok": _avg(conf_ok), "conf_fp": _avg(conf_fp), "conf_n": len(conf_ok) + len(conf_fp)})
    order = {r: i for i, r in enumerate(FP_REASONS + ["사유 미분류"])}
    return {"rows": rows, "reasons": [{"reason": r, "n": n} for r, n in sorted(reasons.items(), key=lambda x: (-x[1], order.get(x[0], 99)))],
            "missed_total": sum(r["missed"] for r in rows), "fp_total": sum(r["fp"] for r in rows),
            "det_fp_total": sum(r["det_fp"] for r in rows)}


# ---------------------------------------------------------------------- 성능 평가 결과 (8)
def eval_reports(n: int = 10) -> list[dict]:
    """monitor_engine/evaluate.py 가 남긴 정답 대비 성능 평가 (최신순)."""
    from safety_monitor.package import OUTPUT_DIR
    out = []
    for f in sorted((OUTPUT_DIR / "eval").glob("*/summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:n]:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({**d, "dir": str(f.parent.relative_to(OUTPUT_DIR.parent))})
    return out
