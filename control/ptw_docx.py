"""
작업허가서 파일 읽기 — '작업허가서_양식(공통).docx' 그대로 채운 워드 파일을 읽어 등록 창 칸을 채운다 (10/13)

작업허가서 등록 창(격리 목록 대조)에서 파일을 올리면
  read_ptw_docx()   양식의 표에서 값을 읽는다 — 허가 번호 · 허가 구분 · 보충 작업 · 부서 · 책임자 · 장소(구역) · 대상 설비 ·
                    작업 내용 · 작업 기간 · 인원 · 화재감시자 · 격리 목록 · 퍼지 · 가스 측정 · 안전조치 확인 · 서명
                    그리고 '확인 필요' — 빈칸 · 해당인데 실시 표시 없음 · 8시간 초과 · 정비인데 격리 목록 없음 같은 것
읽은 값으로 칸을 채울 뿐 등록은 사람이 '등록'을 눌러서 한다 — 등록하면 관제 엔진에 모드 신호가 들어가기 때문이다.

양식의 표 순서(0 기본 정보 · 1 안전조치 · 2 격리 목록 · 3 퍼지 · 4 가스 측정 · 5 서명)를 그대로 읽는다.
양식을 바꾸면 아래 표 번호 · 칸 이름도 같이 고친다.
"""
from __future__ import annotations

import io
import re
from datetime import datetime

from .common import load_config, zone_name, zones

BLANK = {"", "-", "(빈칸)", "빈칸", "해당 없음", "없음"}
LINE_ID = re.compile(r"\b([A-Z]{1,4}-\d{1,3})\b")


def _cells(row) -> list[str]:
    """한 줄의 칸 글자 — 가로로 합친 칸은 한 번만."""
    out, prev = [], None
    for c in row.cells:
        if c._tc is prev:
            continue
        prev = c._tc
        out.append(c.text.strip())
    return out


def _val(s: str) -> str:
    s = (s or "").strip()
    if re.fullmatch(r"[\s시분년월일:()인]*", s):       # 빈 양식의 '시    분' · '(인)' 같은 자리 글자
        return ""
    return "" if s in BLANK or s.startswith("해당 없음") else s


def _checked(text: str) -> list[str]:
    """'■ 일반위험작업  □ 화기작업' → ['일반위험작업'] (■ · ☑ · √ 표시가 붙은 것만)."""
    return [m.strip() for m in re.findall(r"[■☑√▣]\s*([^□■☑√▣(]+)", text or "") if m.strip()]


def _period(text: str, day: str | None):
    """'2026년 10월 12일 08:00부터 12:00까지' · '2026년 10월 12일 8시 0분부터 12시 0분까지' → (시작, 종료)."""
    t = text or ""
    m = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", t) or re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", day or "")
    times = re.findall(r"(\d{1,2})\s*(?::|시)\s*(\d{1,2})?", t.split("일", 1)[-1] if m else t)
    if not m or len(times) < 2:
        return None, None
    y, mo, d = (int(x) for x in m.groups())
    t0 = datetime(y, mo, d, int(times[0][0]), int(times[0][1] or 0))
    t1 = datetime(y, mo, d, int(times[1][0]), int(times[1][1] or 0))
    return t0, t1


def _zone(place: str, equip: str) -> str:
    """작업 장소에서 구역 — 'Z8 산 재생설비(배소로)' 처럼 번호가 있으면 그 번호, 없으면 구역 이름으로 찾는다."""
    m = re.search(r"\b(Z\d+)\b", place or "")
    if m and m.group(1) in zones():
        return m.group(1)
    for z in zones():
        n = zone_name(z)
        if n and n != z and (n in (place or "") or n in (equip or "")):
            return z
    return ""


def _work_type(ptw_type: str, extras: list[str], work: str) -> str:
    """
    등록 창의 '작업 종류(켜질 모드)' 짐작 — control/config.json work_types 중에서.
    화기작업이면 허가서 유형이 '화기'인 것, 보충 작업 · 작업 내용에 그 이름이 들어 있으면 그것, 아니면 유형이 같은 첫 번째.
    사람이 등록 창에서 바꿀 수 있다.
    """
    wts = {k: v for k, v in load_config()["work_types"].items() if not k.startswith("_")}
    same = [k for k, v in wts.items() if v.get("ptw_type") == ptw_type]
    for k in same:
        words = [w for w in re.split(r"\s+", k) if len(w) >= 2]
        if k in extras or any(w in (work or "") for w in words if w not in ("작업", "구역")):
            return k
    return same[0] if same else next(iter(wts), "")


def read_ptw_docx(data: bytes) -> dict:
    from docx import Document
    try:
        doc = Document(io.BytesIO(data))
    except Exception as ex:  # noqa: BLE001
        raise ValueError(f"워드 파일(.docx)을 열지 못했다: {ex}") from None
    t = doc.tables
    if len(t) < 6 or not _cells(t[0].rows[0]) or _cells(t[0].rows[0])[0] != "허가 번호":
        raise ValueError("작업허가서 양식(공통)이 아니다 — 첫 표가 '허가 번호'로 시작해야 한다")

    # 0. 기본 정보 — 왼쪽 이름 칸 → 값
    info = {}
    for r in t[0].rows:
        c = _cells(r)
        for i in range(0, len(c) - 1, 2):
            info[c[i]] = c[i + 1]
    ptw_id = _val(info.get("허가 번호", ""))
    kinds = _checked(info.get("허가 구분", ""))
    ptw_type = "화기" if any("화기" in k for k in kinds) else "정비"
    extras = [k for k in _checked(info.get("보충 작업", ""))]
    late = "사후" in info.get("허가 구분", "") or "긴급" in info.get("허가 구분", "")
    place, equip = info.get("작업 장소", ""), _val(info.get("대상 설비", ""))
    work = _val(info.get("작업 내용", ""))
    t0, t1 = _period(info.get("작업 기간", ""), info.get("허가 일자", ""))
    workers = re.search(r"\d+", info.get("작업 인원", "") or "")
    zone = _zone(place, equip)

    # 1. 안전조치 확인 — 묶음 · 번호 · 요구사항 · 해당 · 실시
    checklist, group = [], ""
    for r in t[1].rows[1:]:
        c = _cells(r)
        if len(c) == 1 or (c and not c[0].isdigit() and len(c) <= 2 and c[0] != "기타 특별사항"):
            group = c[0]
            continue
        if c and c[0].isdigit() and len(c) >= 4:
            applies = "해당" in _checked(c[2])
            checklist.append({"group": group, "no": c[0], "item": c[1], "applies": applies,
                              "done": "실시" in _checked(c[3]) if applies else None})
    special = ""
    for r in t[1].rows:
        c = _cells(r)
        if c and c[0] == "기타 특별사항" and len(c) > 1:
            special = _val(c[-1])

    # 2. 격리 목록
    rows = []
    for r in t[2].rows[1:]:
        c = _cells(r)
        if len(c) >= 6 and _val(c[0]):              # 합친 칸('해당 없음' 같은 안내 줄)은 건너뛴다
            rows.append({"line_id": c[0], "배관": c[1], "격리방법": c[2], "맹판설치": c[3], "벤트": c[4], "가스측정": c[5]})

    # 3. 퍼지
    pc = _cells(t[3].rows[0])
    medium = _val(pc[1]) if len(pc) > 1 else ""
    purge = None
    if medium:
        ptxt = pc[3] if len(pc) > 3 else ""
        mins = re.search(r"\((\d+)\s*분\)", ptxt)
        tt = re.findall(r"(\d{1,2}):(\d{2})", ptxt)
        minutes = int(mins.group(1)) if mins else ((int(tt[1][0]) * 60 + int(tt[1][1])) - (int(tt[0][0]) * 60 + int(tt[0][1])) if len(tt) >= 2 else None)
        purge = {"medium": medium, "minutes": minutes}

    # 4. 가스 측정
    gas = []
    for r in t[4].rows[1:]:
        c = _cells(r)
        if not c or not c[0]:
            continue
        lel = re.search(r"\d+(\.\d+)?", c[2] or "")
        o2 = re.search(r"\d+(\.\d+)?", c[1] or "")
        line = LINE_ID.search(c[0])
        gas.append({"time": c[4], "point": c[0], "line_id": line.group(1) if line else None,
                    "lel_pct": float(lel.group()) if lel else None, "o2_pct": float(o2.group()) if o2 else None,
                    "toxic": _val(c[3]), "by": _val(c[5])})

    # 5. 서명
    heads, signs = _cells(t[5].rows[0]), _cells(t[5].rows[1])
    sign = {h.split(" (")[0].split("(")[0].strip(): _val(re.sub(r"^\(인\)\s*", "", s)) for h, s in zip(heads, signs)}

    supervisor = _val(info.get("작업책임자", ""))
    fire_watch = _val(info.get("화재감시자", ""))

    # 확인 필요
    warn = []
    if not ptw_id:
        warn.append("허가 번호가 비었다 — 등록하면 새 번호를 붙인다")
    if not zone:
        warn.append(f"작업 장소에서 구역을 찾지 못했다 ({place or '빈칸'}) — 등록 창에서 고른다")
    if not work:
        warn.append("작업 내용이 비었다")
    if not t0:
        warn.append("작업 기간을 읽지 못했다 — 등록 창에서 넣는다")
    elif (t1 - t0).total_seconds() > 8 * 3600:
        warn.append("작업 기간이 8시간을 넘는다 — 허가 효력은 1일 8시간 이내 (KOSHA GUIDE P-94)")
    if not supervisor:
        warn.append("작업책임자가 비었다")
    if not workers:
        warn.append("작업 인원이 비었다")
    if ptw_type == "화기" and not fire_watch:
        warn.append("화기작업인데 화재감시자가 비었다 (안전보건규칙 제241조의2)")
    if ptw_type == "정비" and not rows:
        warn.append("일반위험작업인데 격리 목록이 비었다 — 배관 정비가 아니면 '목록 없이 등록'")
    if ptw_type == "정비" and rows and not purge:
        warn.append("격리 목록은 있는데 퍼지 기록이 없다")
    if not gas:
        warn.append("가스 측정 기록이 없다")
    for k in checklist:
        if k["applies"] and not k["done"]:
            warn.append(f"안전조치 '{k['item'].split('  —')[0]}' — 해당인데 실시 표시가 없다")
    for h, v in sign.items():
        if not v:
            warn.append(f"서명 '{h}'이 비었다")
    if late:
        warn.append("긴급 작업 · 사후 발급으로 적혀 있다")

    fields = {"zone": zone, "work_type": _work_type(ptw_type, extras, work),
              "start": t0.isoformat(timespec="minutes") if t0 else "", "end": t1.isoformat(timespec="minutes") if t1 else "",
              "work": work, "supervisor": supervisor, "workers": int(workers.group()) if workers else None}
    csv_text = ""
    if rows:
        cols = ["line_id", "배관", "격리방법", "맹판설치", "벤트", "가스측정"]
        csv_text = "\n".join([",".join(cols)] + [",".join(r[k].replace(",", " ") for k in cols) for r in rows])
    extra = {"purge": purge, "gas_tests": gas, "fire_watch": fire_watch or None, "permit_class": kinds,
             "extra_works": extras, "department": _val(info.get("작업 부서", "")), "equipment": equip,
             "tools": _val(info.get("사용 공구·장비", "")), "witness": _val(info.get("입회자", "")),
             "checklist": checklist, "special": special, "signatures": sign, "late_issue": late}
    read = [("허가 번호", ptw_id or "—"), ("허가 구분", " · ".join(kinds) or "—"),
            ("보충 작업", " · ".join(extras) or "없음"), ("작업 장소", place or "—"), ("대상 설비", equip or "—"),
            ("작업 부서", extra["department"] or "—"), ("화재감시자", fire_watch or "—"),
            ("격리 목록", f"{len(rows)}줄" if rows else "없음"),
            ("퍼지", f"{purge['medium']} {purge['minutes']}분" if purge and purge.get("minutes") is not None else (purge or {}).get("medium") or "없음"),
            ("가스 측정", f"{len(gas)}지점" if gas else "없음"),
            ("안전조치", f"해당 {sum(1 for k in checklist if k['applies'])}건 · 실시 {sum(1 for k in checklist if k['done'])}건")]
    return {"ptw_id": ptw_id, "ptw_type": ptw_type, "fields": fields, "csv": csv_text, "no_list": not rows,
            "extra": extra, "warnings": warn, "read": [{"k": k, "v": v} for k, v in read]}
