/*
 * 트리거형 안전관제 — 화면 시안(자료 › 안전관제_대시보드.html)의 그리기 함수 그대로에,
 * 시안에 박혀 있던 예시 값 대신 /api(관제 · 관제 엔진 · 문서 자동화)의 값을 넣는다.
 * 경보는 화면 오른쪽 위 팝업으로 뜬다.
 */
(function () {
  'use strict';

  /* ---------- 도우미 (시안 그대로) ---------- */
  var LV = {'최고 경보': 'crit', '경보': 'warn', '주의': 'note', '정상': 'ok', '무음': 'mute'};
  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }

  /* ---------- 상태 표현 체계 (10/6 확정) ----------
     위험 단계 다섯 개만 단계 색을 쓴다 — 최고 경보(채운 빨강) · 경보(주황빨강 + 실선) · 주의(앰버) · 정상(초록) · 무음 기록(회색 점선, 계산된 단계는 글자로만).
     단계가 아닌 것 — 자동 조정(청록) · 정보(슬레이트 파랑) · 문서 연계(무채색 + 문서 아이콘) · 승인 대기(무채색 테두리 + 시계).
     작업 전 차단 = 경보 주황 + 자물쇠(이벤트 로그 칩 · 팝업 같게), 사고 = 빨강 + 구급 아이콘. 색만으로 구분하지 않고 아이콘 · 글자를 늘 같이 쓴다. */
  var ICO = {
    crit: '<path d="M8 16v-4a4 4 0 0 1 8 0v4"/><path d="M3 12h1"/><path d="M12 3v1"/><path d="M20 12h1"/><path d="M5.6 5.6l.7.7"/><path d="M18.4 5.6l-.7.7"/><rect x="6" y="16" width="12" height="4" rx="1"/>',
    warn: '<path d="M12 9v4"/><path d="M10.4 3.6L2.3 17.1a1.9 1.9 0 0 0 1.6 2.9h16.2a1.9 1.9 0 0 0 1.6-2.9L13.6 3.6a1.9 1.9 0 0 0-3.2 0z"/><path d="M12 16h.01"/>',
    note: '<circle cx="12" cy="12" r="9"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
    ok: '<circle cx="12" cy="12" r="9"/><path d="M9 12l2 2 4-4"/>',
    silent: '<path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"/><path d="M16.7 16.7A8.7 8.7 0 0 1 12 18c-3.6 0-6.6-2-9-6 1.3-2.1 2.7-3.7 4.3-4.7m2.9-1.1A9 9 0 0 1 12 6c3.6 0 6.6 2 9 6-.7 1.1-1.4 2.1-2.1 2.9"/><path d="M3 3l18 18"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 8h.01"/><path d="M11 12h1v4h1"/>',
    adj: '<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>',
    doc: '<path d="M14 3v4a1 1 0 0 0 1 1h4"/><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z"/><path d="M9 13h6"/><path d="M9 17h6"/>',
    wait: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
    gate: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/><path d="M12 15v2"/>',
    acc: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/><path d="M12 10.5v6"/><path d="M9 13.5h6"/>',
    leak: '<path d="M7.5 10.5c-2 .3-3.5 1.9-3.5 3.9 0 2.2 1.8 4 4 4h9a3.5 3.5 0 0 0 .5-7 5 5 0 0 0-9.6-1.5"/><path d="M9 21h.01M13 21h.01M17 21h.01"/>',
    stack: '<path d="M12 4L4 8l8 4 8-4-8-4"/><path d="M4 12l8 4 8-4"/><path d="M4 16l8 4 8-4"/>',
    flame: '<path d="M12 12c2-3 0-7-1-8 0 3-1.8 4.7-3 6-1.2 1.3-2 3.2-2 5a6 6 0 1 0 12 0c0-1.5-1.1-3.9-2-5-1.8 3-2.8 3-4 2z"/>',
    user: '<circle cx="12" cy="7" r="4"/><path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2"/>',
    axis: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/>'
  };
  function ico(k, cls) { return '<svg class="ico' + (cls ? ' ' + cls : '') + '" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' + (ICO[k] || '') + '</svg>'; }
  var LVI = {crit: 'crit', warn: 'warn', note: 'note', ok: 'ok'};
  // 단계 칩 — 최고 경보는 채운 칩(lv4), 경보는 연한 칩 + 실선(lv3), 주의(lv2), 정상(lv1). quiet = 판정표처럼 글자색만
  function lv(level, alerted, quiet) {
    if (alerted === false && level && level !== '정상') return '<span class="lv silent">' + ico('silent') + '무음 · ' + esc(level) + '</span>';
    if (!level || level === '무음') return '<span class="lv silent">' + ico('silent') + '무음 기록</span>';
    var k = LV[level] || 'mute';
    var n = {crit: ' lv4', warn: ' lv3', note: ' lv2', ok: ' lv1'}[k] || '';
    return '<span class="lv ' + k + n + (quiet ? ' q' : '') + '">' + (LVI[k] ? ico(LVI[k]) : '') + esc(level) + '</span>';
  }
  function z(id) { return '<span class="z">' + esc(id || '-') + '</span>'; }
  function chip(text, k) { return '<span class="lv ' + (k || 'mute') + '">' + esc(text) + '</span>'; }
  // 아이콘이 붙는 칩 — gate(작업 전 차단) · acc(사고) · adj(자동 조정) · wait(승인 대기) · info · doc
  function tag(text, k) {
    var cls = {gate: 'warn gate', acc: 'crit lv4 acc', adj: 'adj', wait: 'wait', info: 'info', doc: 'docl'}[k] || k;
    return '<span class="lv ' + cls + '">' + ico(k) + esc(text) + '</span>';
  }
  // 작업허가서 대조 결과 — 누락(crit) · 목록 미첨부(warn)는 작업 전 차단 대상(주황 + 자물쇠), 맹판 · 측정 · 퍼지 대기(note)는 사람 처리 대기
  function ptwTag(kind, text) {
    if (kind === 'crit' || kind === 'warn') return tag(text, 'gate');
    if (kind === 'note') return tag(text, 'wait');
    return chip(text, kind === 'ok' ? 'ok' : 'mute');
  }
  function kindTag(e) {
    if (e.kind === 'gate') return tag('작업 전 차단', 'gate');
    if (e.kind === 'accident') return tag('사고', 'acc');
    if (e.kind === 'info') return tag(e.type === '작업중지_지시' ? '작업중지 지시' : e.type === '입력_취소' ? '입력 취소' : '참고', 'info');
    return lv(e.level, e.alerted);
  }
  function opt(v, label, sel) { return '<option value="' + esc(v) + '"' + (sel ? ' selected' : '') + '>' + esc(label) + '</option>'; }
  function mins(hhmm) { var p = String(hhmm || '0:0').split(':'); return (+p[0]) * 60 + (+p[1]); }
  function hhmm(v) { v = Math.round(v); var h = Math.floor(v / 60), m = v % 60; return (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m; }
  function download(url, label) { return url ? '<a class="btn sm" href="' + esc(url) + '" download>' + esc(label) + '</a>' : ''; }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }

  function api(url, body) {
    var o = body === undefined ? {} : (body instanceof FormData ? {method: 'POST', body: body}
      : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    return fetch(url, o).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) throw new Error(d.error || ('요청 실패 (' + r.status + ')'));
        return d;
      });
    });
  }
  var flashT = null;
  function flash(msg, err) {
    var f = $('flash'); f.textContent = msg; f.className = 'flash' + (err ? ' err' : ''); f.hidden = false;
    clearTimeout(flashT); flashT = setTimeout(function () { f.hidden = true; }, err ? 7000 : 4500);
  }
  function fail(e) { flash(e.message || String(e), true); }
  function busy(btn, p) {
    if (!btn) return p;
    var t = btn.textContent; btn.disabled = true; btn.textContent = t + ' …';
    return p.finally(function () { btn.disabled = false; btn.textContent = t; });
  }

  /* ---------- 카메라 자리 그림 (시안 camSVG — 영상이 없을 때) ---------- */
  function camSVG(o) {
    var s = '<svg viewBox="0 0 640 330" role="img" aria-label="' + esc(o.aria || '카메라 화면') + '">';
    s += '<rect width="640" height="330" fill="var(--cam-bg)"/><polygon points="0,150 640,120 640,330 0,330" fill="var(--cam-floor)"/>';
    s += '<g stroke="var(--cam-line)" stroke-width="1"><line x1="0" y1="200" x2="640" y2="172"/><line x1="0" y1="260" x2="640" y2="232"/><line x1="120" y1="145" x2="60" y2="330"/><line x1="300" y1="137" x2="300" y2="330"/><line x1="480" y1="129" x2="540" y2="330"/></g>';
    if (o.pipes) { s += '<rect x="0" y="62" width="640" height="16" fill="#6f7a86"/><rect x="0" y="92" width="640" height="12" fill="#5f6b78"/><rect x="0" y="116" width="400" height="6" fill="#7b8691"/>'; }
    if (o.equip) { s += '<rect x="470" y="20" width="150" height="120" rx="6" fill="#4a3a36" stroke="#8a5a50"/><text x="545" y="84" font-size="13" fill="#e6c9c2" text-anchor="middle" font-family="IBM Plex Sans KR,sans-serif">' + esc(o.equip) + '</text>'; }
    var on = o.active;
    var fill = on ? 'rgba(198,40,40,.18)' : 'rgba(160,170,180,.10)', stroke = on ? '#e5584a' : '#8b939d', tc = on ? '#ff8a80' : '#c9d1da';
    if (o.polys && o.polys.length) {
      o.polys.forEach(function (p) {
        var pts = p.points.map(function (q) { return (q[0] * 640).toFixed(0) + ',' + (q[1] * 330).toFixed(0); }).join(' ');
        var c = zcol(p.type), info = zinfo(p.type), lit = !info && (on || p.type === 'hazard');   // hazard 만 상시 — 나머지는 모드가 켜져야 진하게
        s += '<polygon points="' + pts + '" fill="' + c + '" fill-opacity="' + (lit ? 0.16 : 0.05) + '" stroke="' + c + '" stroke-opacity="' + (lit || info ? 1 : 0.6) + '" stroke-width="1" stroke-dasharray="' + (info ? '2 4' : '7 5') + '"/>';
        s += '<text x="' + (p.points[0][0] * 640 + 8).toFixed(0) + '" y="' + (p.points[0][1] * 330 + 18).toFixed(0) + '" font-size="12" font-weight="700" fill="' + c + '" font-family="IBM Plex Mono,monospace">' + esc(p.label) + (lit || info ? '' : ' · 무음 기록') + '</text>';
      });
    } else if (o.poly) {
      s += '<polygon points="150,150 460,132 520,300 110,318" fill="' + fill + '" stroke="' + stroke + '" stroke-width="1" stroke-dasharray="7 5"/>';
      s += '<text x="160" y="168" font-size="12" font-weight="700" fill="' + tc + '" font-family="IBM Plex Mono,monospace">' + esc(o.poly) + (on ? '' : ' · 무음 기록') + '</text>';
    }
    var pos = [[258, 186], [338, 178], [196, 210], [392, 196]];
    for (var i = 0; i < Math.min(o.persons || 0, 4); i++) {
      var x = pos[i][0], y = pos[i][1];
      s += '<ellipse cx="' + x + '" cy="' + y + '" rx="10" ry="11" fill="#b9c2cc"/><rect x="' + (x - 14) + '" y="' + (y + 12) + '" width="28" height="62" rx="8" fill="#8d97a3"/>';
      s += '<rect x="' + (x - 26) + '" y="' + (y - 14) + '" width="52" height="98" fill="none" stroke="#6cc3c8" stroke-width="2"/><circle cx="' + x + '" cy="' + (y + 84) + '" r="4" fill="#6cc3c8"/>';
    }
    if (o.spark) {
      s += '<circle cx="428" cy="238" r="16" fill="#ffb74d" opacity=".45"/><circle cx="428" cy="238" r="7" fill="#fff3c4"/>';
      s += '<g stroke="#ffcc66" stroke-width="2" stroke-linecap="round"><line x1="436" y1="232" x2="456" y2="220"/><line x1="438" y1="240" x2="462" y2="238"/><line x1="434" y1="246" x2="452" y2="260"/></g>';
      s += '<rect x="404" y="206" width="64" height="62" fill="none" stroke="#ff5a4a" stroke-width="2.4"/><rect x="404" y="192" width="92" height="14" fill="#ff5a4a"/><text x="408" y="203" font-size="10" fill="#fff" font-family="IBM Plex Mono,monospace">점화원 (신호)</text>';
    }
    if (o.note) { s += '<text x="320" y="316" font-size="12" fill="#8b939d" text-anchor="middle" font-family="IBM Plex Sans KR,sans-serif">' + esc(o.note) + '</text>'; }
    else if (!o.persons && !o.spark && !o.poly && !(o.polys && o.polys.length)) { s += '<text x="320" y="240" font-size="13" fill="#8b939d" text-anchor="middle" font-family="IBM Plex Sans KR,sans-serif">검출 없음</text>'; }
    return s + '</svg>';
  }

  /* ---------- 상태 ---------- */
  var META = null, STATUS = null, LIVE = null;
  var curScreen = 'live', curZone = null, curCam = 0, zonePickedAt = 0;
  var zonesOpen = false;

  /* ---------- 머리글 · 메뉴 숫자 · 경보 팝업 ---------- */
  function badge(id, n) { var b = $(id); if (!b) return; b.textContent = n; b.hidden = !n; }
  function renderStatus(s) {
    var d = s.now.slice(0, 10), t = s.now.slice(11, 19);
    // 머리줄 한 줄: LIVE · 시각 · 규칙셋 · 켜진 모드 · 영상 (+ 경보 칩)
    var lp = $('livepill');
    lp.className = 'livepill ' + (s.sid ? (s.running ? 'live' : 'pause') : 'idle');
    lp.innerHTML = s.sid ? (s.running ? '<i></i>LIVE' : '⏸ 멈춤') : '○ 시작 전';
    lp.setAttribute('data-go', 'live');
    $('clock').innerHTML = esc(d) + ' <b>' + esc(t) + '</b>';
    var chips = '<span class="chip rs">현재 규칙셋 v' + s.ruleset.version + '</span>' +
      '<span class="chip mode" data-go="live">켜진 모드 ' + s.modes_on + ' · ' + s.zones_on + '개 구역</span>' +
      '<span class="chip vid' + (s.video ? ' on' : '') + '" title="' + esc(s.scene ? '영상 장면 ' + s.scene : '영상 장면이 붙지 않았다') + '">' + (s.video ? '<i></i>영상 재생 중' : '영상 없음 · 신호 판정') + '</span>';
    var gates = s.incidents.filter(function (i) { return i.kind === 'gate'; }).length;
    var accs = s.incidents.filter(function (i) { return i.kind === 'accident'; }).length;
    if (accs) chips += '<span class="chip alarm-chip crit" data-reopen="1" title="누르면 알림 창을 다시 연다">' + ico('acc') + '사고 ' + accs + '</span>';
    if (gates && !s.alarms.length) chips += '<span class="chip alarm-chip warn" data-reopen="1" title="누르면 알림 창을 다시 연다">' + ico('gate') + '작업 전 차단 ' + gates + '</span>';
    if (s.alarms.length) {
      var w = s.alarms[0], wk = LV[w.level] || 'note';
      chips += '<span class="chip alarm-chip ' + wk + '" data-reopen="1" title="누르면 경보 창을 다시 연다">' + ico(wk) + esc(w.zone) + ' ' + esc(w.level) + (s.alarms.length > 1 ? ' 외 ' + (s.alarms.length - 1) : '') + '</span>';
    }
    $('topchips').innerHTML = chips;
    ['live', 'iso', 'feedback', 'home', 'docs', 'voice'].forEach(function (k) { badge('n-' + k, s.badges[k] || 0); });
    // 메뉴 숫자 — 중요할 때만 색: 실시간 관제는 지금 가장 높은 경보 단계 색, 격리 목록 대조는 작업 전 차단(주황). 나머지는 흐린 회색
    var top = s.alarms.length ? (LV[s.alarms[0].level] || '') : '';
    $('n-live').className = 'cnt' + (top ? ' hot ' + top : '');
    $('n-iso').className = 'cnt' + ((s.badges.iso || 0) ? ' hot warn' : '');
    $('fb-seg').querySelectorAll('button').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-fbmode') === s.feedback_mode); });
    $('ft-rs').textContent = '사업장 패키지 · 규칙셋 v' + s.ruleset.version + (s.ruleset.ids.length ? ' (' + s.ruleset.ids.join(' ') + ')' : '');
    popups(s);
  }

  var popSeen = {}, popClosed = {}, popSid = undefined;
  function popups(s) {
    // 실시간 관제에서는 오른쪽 아래에 띄운다 — 오른쪽 위 3축 신호판 · 현재 판정을 가리지 않게. 다른 화면은 그대로 오른쪽 위
    $('popups').classList.toggle('dock-b', curScreen === 'live');
    if (s.sid !== popSid) { popSeen = {}; popClosed = {}; popSid = s.sid; $('popups').innerHTML = ''; }
    var box = $('popups'), live = {};
    s.alarms.forEach(function (a) { live[a.key] = a; });
    s.incidents.forEach(function (i) { live[i.key] = i; });
    // 사라진 경보(단계가 내려감)는 팝업도 닫는다. 게이트 · 사고는 사람이 닫을 때까지 둔다
    box.querySelectorAll('.popup[data-key]').forEach(function (el) {
      if (!live[el.getAttribute('data-key')]) el.remove();
    });
    var fresh = null;
    s.alarms.concat(s.incidents).forEach(function (a) {
      if (popClosed[a.key] || box.querySelector('.popup[data-key="' + CSS.escape(a.key) + '"]')) return;
      var el = document.createElement('div');
      el.setAttribute('data-key', a.key);
      el.setAttribute('role', 'alert');
      if (a.level) {                                   // 구역 경보
        var k = LV[a.level] || 'note';
        el.className = 'popup' + (k === 'crit' ? '' : ' ' + k);
        var head = a.title || (a.reason || '').split(' · ')[0];      // 짧은 줄 이름이 있으면 그것 (STEP 03-3 보완 — 긴 이름이 잘려 원인이 틀리게 읽히지 않게)
        el.innerHTML = '<div class="hd"><span class="pill">' + ico(k) + esc(a.level) + '</span><span class="t">' + esc(a.since) + '부터 · ' + (a.rule ? esc(a.rule) : '판정표 ' + esc(a.row || '-') + '번 줄') + '</span><button class="x" type="button" data-close="1" aria-label="닫기">×</button></div>' +
          '<b class="w">' + z(a.zone) + ' ' + esc(a.name) + ' — ' + esc(head) + '</b>' +
          '<em>대응: ' + esc(a.response || '-') + (a.adj.length ? ' · 강화 중 ' + esc(a.adj.join(', ')) : '') + '</em>' +
          '<div class="btnrow"><button class="btn sm" type="button" data-pop-zone="' + esc(a.zone) + '">구역 보기</button>' +
          (k !== 'note' ? '<button class="btn ' + (k === 'crit' ? 'primary' : 'stop') + ' sm" type="button" data-stop="' + esc(a.zone) + '">작업중지 지시</button><button class="btn doc sm" type="button" data-pop-co="1">시정지시서 초안</button>' : '') + '</div>';
        if (k === 'note') setTimeout(function () { if (el.parentNode) { popClosed[a.key] = 1; el.remove(); } }, 12000);
      } else {                                         // 작업 전 게이트 · 사고
        el.className = 'popup' + (a.kind === 'gate' ? ' gate' : ' acc');
        if (a.kind === 'gate') setTimeout(function () { if (el.parentNode) { popClosed[a.key] = 1; el.remove(); } }, 12000);   // 게이트는 12초 뒤 접는다 (머리글 칩 · 이벤트 로그에 남는다)
        el.innerHTML = '<div class="hd"><span class="pill">' + (a.kind === 'gate' ? ico('gate') + '작업 전 차단' : ico('acc') + '사고') + '</span><span class="t">' + esc(a.t) + ' · ' + esc(a.id) + '</span><button class="x" type="button" data-close="1" aria-label="닫기">×</button></div>' +
          '<b class="w">' + z(a.zone) + ' ' + esc(a.name) + '</b><em>' + esc(a.reason) + '</em>' +
          '<div class="btnrow">' + (a.kind === 'gate'
            ? '<button class="btn sm" type="button" data-go="iso">격리 목록 대조로 →</button>'
            : '<button class="btn doc sm" type="button" data-go="docs" data-tab="accident" data-acc="' + esc(a.id) + '">산업재해조사표로 →</button>') +
          '<button class="btn sm" type="button" data-pop-zone="' + esc(a.zone) + '">구역 보기</button></div>';
      }
      box.appendChild(el);
      if (!popSeen[a.key]) { popSeen[a.key] = 1; if (a.level && LV[a.level] !== 'note') fresh = a.zone; }
    });
    // 한 번에 두 개까지만 — 오래된 것은 접는다 (머리글 칩을 누르면 다시 연다). 경보가 게이트보다 먼저 남는다
    var shown = Array.prototype.slice.call(box.querySelectorAll('.popup'));
    shown.sort(function (x, y) { return (y.classList.contains('gate') ? 0 : 1) - (x.classList.contains('gate') ? 0 : 1); });
    shown.slice(2).forEach(function (el) { popClosed[el.getAttribute('data-key')] = 1; el.remove(); });
    // 새 경보가 뜨면 사람이 방금 구역을 고른 게 아니면 그 구역으로 따라간다
    if (fresh && curScreen === 'live' && Date.now() - zonePickedAt > 20000 && fresh !== curZone) { curZone = fresh; curCam = 0; if (LIVE) renderLive(); }
  }
  $('popups').addEventListener('click', function (e) {
    var p = e.target.closest('.popup'); if (!p) return;
    var key = p.getAttribute('data-key');
    if (e.target.closest('[data-close]')) { popClosed[key] = 1; p.remove(); return; }
    var zb = e.target.closest('[data-pop-zone]');
    if (zb) { curZone = zb.getAttribute('data-pop-zone'); curCam = 0; zonePickedAt = Date.now(); show('live'); return; }
    var st = e.target.closest('[data-stop]');
    if (st) { busy(st, api('/api/live/stop-order', {zone: st.getAttribute('data-stop')})).then(function (d) { flash(d.msg); tick(); }).catch(fail); return; }
    if (e.target.closest('[data-pop-co]')) { goCorrectiveFromLive(); return; }
    if (e.target.closest('[data-go]')) { popClosed[key] = 1; p.remove(); }
  });

  function tickStatus() {
    return api('/api/status').then(function (s) {
      STATUS = s; renderStatus(s); if (curScreen === 'feedback' && FB.d) updLeft();
      // 등록 칸 날짜 — 관제 시계가 처음 들어오면 그 날로 맞춘다 (손대기 전에만)
      if (!ISO.dated && !$('reg-title').value.trim() && !$('reg-csv').value.trim()) { regReset($('reg-zone').value); ISO.dated = true; }
    }).catch(function () {});
  }

  /* ---------- 1. 실시간 관제 ---------- */
  var ORDER = {'최고 경보': 3, '경보': 2, '주의': 1, '정상': 0};
  function zoneOf(id) { return LIVE ? LIVE.zones.filter(function (x) { return x.id === id; })[0] : null; }
  function zk(x) { return x.alerting ? (LV[x.level] || 'ok') : 'ok'; }
  function renderZones() {
    $('zstrip').innerHTML = LIVE.zones.map(function (x) {
      var k = zk(x), silent = !x.alerting && x.computed !== '정상';
      var t = x.id + ' ' + x.name + ' · ' + (x.alerting ? x.level : (silent ? '무음 · ' + x.computed : '정상')) + (x.modes.length ? ' · ' + x.modes.join(', ') : '');
      // 색만으로 구분하지 않는다 — 경보 구역은 단계 아이콘 + 단계 글자, 무음 계산은 점선 + 눈 아이콘
      var mark = k !== 'ok' ? ico(k) : silent ? ico('silent') : '<i></i>';
      var lvTxt = k !== 'ok' ? '<b class="zl">' + esc(x.level) + '</b>' : '';
      return '<button type="button" class="zchip ' + (k !== 'ok' ? k : silent ? 'silent' : '') + (x.id === curZone ? ' on' : '') + '" data-zone="' + x.id + '" title="' + esc(t) + '">' + mark + x.id + ' ' + esc(x.name) + lvTxt + '</button>';
    }).join('');
    var cnt = {};
    LIVE.events.forEach(function (e) { if (!e.alerted && (e.kind === 'stage' || e.kind === 'check')) cnt[e.zone] = (cnt[e.zone] || 0) + 1; });
    $('zones').innerHTML = LIVE.zones.map(function (x) {
      var k = zk(x);
      var l = x.alerting ? lv(x.level) : (x.computed !== '정상' ? lv(x.computed, false) : lv('정상'));
      return '<button type="button" class="ztile ' + (k !== 'ok' ? k : '') + (x.id === curZone ? ' on' : '') + '" data-zone="' + x.id + '">' +
        '<span class="zt">' + z(x.id) + l + '</span><span class="zn">' + esc(x.name) + '</span>' +
        '<span class="zm">' + (x.modes.length ? esc(x.modes.join(' · ')) : '평상시') + '</span>' +
        '<span class="zp">사람 ' + x.people + ' · 카메라 ' + x.cams.length + (cnt[x.id] ? ' · 무음 ' + cnt[x.id] : '') + '</span>' +
        ((x.faults || []).length ? '<span class="zf" title="' + esc(faultTitle(x.faults)) + '">' + ico('info') + '센서 이상 · 측정 실패 ' + x.faults.length + '</span>' : '') + '</button>';
    }).join('');
  }
  function renderCam(x) {
    var active = x.modes.length > 0;
    var cam = x.cams[curCam];
    $('cam-title').textContent = x.cams.length ? cam + ' · ' + x.id + ' ' + x.name : x.id + ' ' + x.name;
    $('cam-sub').textContent = x.cams.length ? (active ? '모드 켜짐 · 폴리곤 판정 중' : '평상시 · 기본 규칙 + 무음 기록') + (LIVE.video ? ' · 영상 탐지 중' : '') : '';
    var box = $('cam');
    if (!x.cams.length) {
      box.innerHTML = '<div class="empty" style="color:#8b939d;padding:60px 18px">이 구역에는 카메라가 없다. 신호(CSV · 버튼)로만 판정한다.</div>';
      $('camlist').innerHTML = '';
      return;
    }
    var hud = '<div class="hud"><span>' + esc(cam) + ' · ' + x.id + '</span><span class="rec">' + (LIVE.sid && LIVE.running ? '<span class="pulse">●</span> REC ' : '') + LIVE.now.slice(11, 19) + '</span></div>';
    var hasFrame = LIVE.frames.indexOf(cam) >= 0;
    if (hasFrame) hud = '<div class="hud bottom"><span></span><span class="rec">' + (LIVE.sid && LIVE.running ? '<span class="pulse">●</span> REC ' : '') + LIVE.now.slice(11, 19) + '</span></div>';   // 영상에는 엔진이 쓴 글자가 위에 있다
    if (hasFrame) {
      var img = box.querySelector('img[data-cam="' + cam + '"]');
      // 영상이 도는 동안은 스트림(/api/live/stream — 끊김 없이 받는다) 하나를 열어 두고 손대지 않는다.
      // 영상이 끝나면 마지막 프레임 한 장(/api/live/frame)으로 바꾼다.
      var mode = LIVE.video ? 'stream' : 'still';
      var url = mode === 'stream' ? '/api/live/stream/' + encodeURIComponent(cam) + '?s=' + encodeURIComponent((LIVE.sid || '') + '|' + ((LIVE.scene || {}).name || ''))
        : '/api/live/frame/' + encodeURIComponent(cam) + '?t=' + Date.now();
      if (!img) { box.innerHTML = '<img data-cam="' + esc(cam) + '" data-mode="' + mode + '" alt="' + esc(cam) + ' 영상" src="' + url + '">' + hud; box.removeAttribute('data-prev'); }
      else {
        if (mode === 'stream') {
          if (img.getAttribute('data-mode') !== 'stream' || img.getAttribute('src') !== url) { img.setAttribute('data-mode', 'stream'); img.src = url; }
        } else if (img.getAttribute('data-mode') === 'stream') {
          img.setAttribute('data-mode', 'still');            // 스트림이 닫히면 마지막 프레임이 남는다 — 한 장만 다시 받아 둔다
          var pre = new Image(); pre.onload = function () { img.src = pre.src; }; pre.src = url;
        }
        var h = box.querySelector('.hud'); if (h) h.outerHTML = hud;
      }
    } else if (LIVE.scene && LIVE.scene.video && LIVE.scene.camera === cam) {
      camPreview(box, x, active, hud.replace(/<span>[^<]*<\/span>/, '<span></span>'));   // 영상 첫 프레임에도 글자가 있다 — 오른쪽 시각만
    } else {
      box.removeAttribute('data-prev');
      box.innerHTML = camSVG({polys: x.polys, poly: x.id + ' 구역', active: active, persons: x.people, spark: x.ignition,
        equip: curCam === 0 ? x.equip : null, pipes: x.piping, aria: x.id + ' 카메라 화면',
        note: LIVE.video ? '' : '영상이 연결되지 않았다 — 폴리곤만 표시 · 판정은 신호(CSV · 버튼)로'}) + hud;
    }
    $('camlist').innerHTML = x.cams.map(function (c, i) { return '<button type="button" data-cam="' + i + '" class="' + (i === curCam ? 'on' : '') + '">' + esc(c) + '</button>'; }).join('');
  }
  /* 영상 장면이 붙었는데 아직 재생 전 — 그 영상의 첫 프레임에 구역을 겹쳐 보여주고, 언제 도는지 알려준다 */
  var PCOL = {hazard: '#e5584a', hazard_repair: '#ff6b5e', work: '#6cc3c8', restricted: '#e0a13a'};
  function zcol(t) { var c = (META && META.zone_types || []).filter(function (y) { return y.key === t; })[0]; return c ? c.color : (PCOL[t] || '#9aa4af'); }
  function zinfo(t) { return !PCOL[t]; }        // 관리자가 더한 종류 — 판정이 아니라 표시 · 기록용
  function camPreview(box, x, active, hud) {
    var sc = LIVE.scene;
    var key = sc.video + '|' + JSON.stringify(x.polys) + '|' + active;
    // 같은 장면을 다시 틀면 key 가 같아도 칸 안은 지난 영상의 마지막 프레임으로 바뀌어 있다 — 미리 보기가 실제로 있는지도 본다 (10/7)
    if (box.getAttribute('data-prev') !== key || !box.querySelector('#cam-wait')) {
      var svg = '<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">' + x.polys.map(function (p) {
        var c = zcol(p.type), info = zinfo(p.type), lit = !info && (active || p.type === 'hazard');
        return '<polygon points="' + p.points.map(function (q) { return (q[0] * 100).toFixed(2) + ',' + (q[1] * 100).toFixed(2); }).join(' ') +
          '" fill="' + c + '" fill-opacity="' + (lit ? 0.14 : 0.05) + '" stroke="' + c + '" stroke-opacity="' + (lit || info ? 1 : 0.6) + '" stroke-width="1" stroke-dasharray="' + (info ? '2 4' : '6 4') + '" vector-effect="non-scaling-stroke"/>';
      }).join('') + '</svg>';
      var labels = x.polys.map(function (p) {
        return '<span class="plab" style="left:' + (p.points[0][0] * 100).toFixed(1) + '%;top:' + (p.points[0][1] * 100).toFixed(1) + '%;color:' + zcol(p.type) + '">' + esc(p.label) + '</span>';
      }).join('');
      box.innerHTML = '<div class="prev"><img alt="' + esc(sc.name) + ' 첫 프레임" src="/api/scene/frame?video=' + encodeURIComponent(sc.video) + '&schedule=' + encodeURIComponent(LIVE.meta.schedule || '') + '">' + svg + labels +
        '<div class="wait" id="cam-wait"></div></div>' + hud;
      box.setAttribute('data-prev', key);
    } else {
      var h = box.querySelector('.hud'); if (h) h.outerHTML = hud;
    }
    var cw = $('cam-wait'); if (cw) cw.innerHTML = sceneWait(true);
  }
  /* 영상 장면이 언제 도는지 — 한 줄. 영상은 ▶ 시작과 함께 지금 시각부터 돈다 (10/8) */
  function sceneWait(onCam) {
    var sc = LIVE.scene; if (!sc) return '';
    var btn = '<button class="btn sm" type="button" data-scene-now="1">' + (sc.started ? '⏭ 다시 재생' : '⏭ 지금 재생') + '</button>';
    if (LIVE.video) return '';
    if (sc.started) return '<span>영상 장면 <b>' + esc(sc.name) + '</b> 재생이 끝났다 — 지금은 신호로만 판정한다</span>' + btn;
    if (!LIVE.sid) return '<span>시작 전 미리 보기 — <b>▶ 시작</b>을 누르면 지금 시각부터 이 영상이 돈다</span>' + btn;
    if (!LIVE.running) return '<span>' + (onCam ? '영상 대기' : '영상 장면 <b>' + esc(sc.name) + '</b> 대기') + ' — 멈춤 상태다. ▶ 계속을 누르면 돈다</span>' + btn;
    return '<span>영상 장면 <b>' + esc(sc.name) + '</b> 곧 시작</span>';
  }
  function fmtSec(v) { v = Math.max(0, Math.round(v || 0)); return Math.floor(v / 60) + ':' + ('0' + v % 60).slice(-2); }
  function renderRun() {
    if (typeof renderVideos === 'function' && !$('lv-panel').hidden) renderVideos();    // '재생 중 · 이 세션' 표시
    var st, cls;
    if (!LIVE.sid) { st = '○ 시작 전 — 시계가 서 있다'; cls = 'idle'; }
    else if (!LIVE.running) { st = '⏸ 멈춤'; cls = 'pause'; }
    else if (LIVE.video) { st = '<i></i>영상 재생 중 ' + (LIVE.video_pos ? fmtSec(LIVE.video_pos[0]) + ' / ' + fmtSec(LIVE.video_pos[1]) : ''); cls = 'live'; }
    else { st = '<i></i>관제 중'; cls = 'live'; }
    $('lv-run').className = 'runpill ' + cls;
    $('lv-run').innerHTML = st + ' <span class="clk">현재 시각 <b>' + esc(LIVE.now.slice(11, 19)) + '</b></span>';
    var line = $('lv-scn'), w = LIVE.scene ? sceneWait(false) : '';
    var sel = $('lv-scene').value, ses = (LIVE.meta && LIVE.meta.scene) || '';
    if (!w && sel && sel !== ses) {
      w = '<span>고른 영상 ‘<b>' + esc(sel) + '</b>’ — 아직 이 세션에 붙지 않았다. 새 세션을 시작하거나 바로 재생한다</span><button class="btn sm" type="button" data-scene-now="form">⏭ 고른 영상 바로 재생</button>';
    }
    if (LIVE.video && LIVE.scene) w = '<span><i class="dot-live"></i>영상 장면 <b>' + esc(LIVE.scene.name) + '</b> 재생 중 · ' + esc(LIVE.scene.camera || '') + ' — 사람 · 불꽃을 프레임마다 탐지해 판정에 넣는다</span>';
    line.hidden = !w;
    if (line.getAttribute('data-w') !== w) { line.innerHTML = w; line.setAttribute('data-w', w); }
  }
  function focusCam(camId) {
    if (!LIVE || !camId) return;
    LIVE.zones.forEach(function (x) { var i = x.cams.indexOf(camId); if (i >= 0) { curZone = x.id; curCam = i; zonePickedAt = Date.now(); } });
  }
  function sceneNow(btn, body) {
    if (!body.scene) { flash('영상을 먼저 고른다 — 시연 설정의 영상 목록', true); return Promise.resolve(); }
    return busy(btn, api('/api/live/scene-now', body)).then(function (d) {
      flash(d.msg); popSid = undefined;
      return api('/api/live').then(function (l) { LIVE = l; if (l.scene) focusCam(l.scene.camera); renderLive(); });
    }).catch(fail);
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-scene-now]'); if (!b) return;
    var m = LIVE && LIVE.meta || {};
    var body = b.getAttribute('data-scene-now') === 'form' || !LIVE.scene ? liveForm()
      : {schedule: m.schedule, ruleset: m.ruleset, scene: m.scene};
    sceneNow(b, body);
  });
  /* 3축 신호판 — 축 이름은 무채색 + 아이콘(A). 그 축에 실제로 상황이 생겼을 때(tone danger)만 아이콘 칸에 그 축의 색이 든다(B).
     단계 이름은 축에 붙이지 않는다 — 축은 확인 · 가능 · 해제 · 있음 · 없음, 단계는 아래 '현재 판정' 한 곳에만. */
  var AXK = {'발생': ['leak', 'x1'], '축적': ['stack', 'x2'], '점화원': ['flame', 'x3']};
  function axState(a) { return a.state === '●' ? '있음' : a.state === '○' ? '없음' : a.state === '-' ? '—' : a.state; }
  function splitT(s) { var m = /^(\d{1,2}:\d{2}(?::\d{2})?)\s+(.*)$/.exec(String(s || '')); return m ? {t: m[1], x: m[2]} : {t: '', x: String(s || '')}; }
  var judgeOpen = false;
  function renderAxes(x) {
    var active = x.modes.length > 0;
    $('ax-title').textContent = '3축 신호판 · ' + x.id;
    $('ax-sub').textContent = active ? '켜진 모드: ' + x.modes.join(' · ') : '모드 꺼짐 — 경보 없이 무음 기록';
    if (!x.table) {
      $('axes').innerHTML = '<p class="empty">' + esc(x.id) + '에는 판정표가 걸려 있지 않다 — 구역 규칙 · 모드 규칙(영상)과 무음 기록만 돈다.</p>';
      $('judge').innerHTML = ''; $('jt-toggle').parentNode.hidden = true;
      if (x.alerting && x.level !== '정상') {          // 구역 규칙(위험구역 진입)이 울리는 중
        var kk = LV[x.level] || 'warn';
        $('verdict').className = 'verdict ' + kk;
        $('verdict').innerHTML = '<span class="vi">' + ico(kk) + '</span><div class="vb"><span class="vl">현재 판정</span><b class="vh">' + esc(x.level) + '</b>' +
          '<span class="vr">' + esc(x.rule || x.violation) + '</span><small>' + esc((x.since ? x.since + '부터 · ' : '') + x.reason + (x.response ? ' · 대응: ' + x.response : '')) + '</small></div>';
      } else { $('verdict').className = 'verdict'; $('verdict').innerHTML = ''; }
      renderPerson(x);
      return;
    }
    $('jt-toggle').parentNode.hidden = false;
    var rows = x.axes.map(function (a, i) {
      var key = AXK[a.name] || ['axis', 'x' + ((i % 3) + 1)];
      var st = a.tone === 'danger' ? 'on' : a.tone === 'warn' ? 'half' : a.tone === 'ok' ? 'clr' : 'off';
      var ev = a.why.length ? splitT(a.why[0]) : {t: '', x: a.why_not[0] || ''};
      var more = a.why.slice(1).map(function (w) { return splitT(w).x; }).join(' · ');
      return '<div class="axr ' + st + ' ' + key[1] + '"><span class="axi">' + ico(key[0]) + '</span><span class="axn">' + esc(a.name) + '</span>' +
        '<span class="axs">' + esc(axState(a)) + '</span><span class="axe" title="' + esc(a.why.concat(a.why.length ? [] : a.why_not.slice(0, 1)).join(' · ')) + '"><b>' + esc(ev.x || '—') + '</b>' + (more ? '<small>' + esc(more) + '</small>' : '') + '</span>' +
        '<span class="axt mono">' + esc(ev.t || '—') + '</span></div>';
    });
    $('axes').innerHTML = rows.join('<div class="axar" aria-hidden="true"></div>') + '<div class="axar to" aria-hidden="true"></div>';
    // 현재 판정 — 단계 색은 여기 한 곳에만
    var silent = !x.alerting && x.computed !== '정상';
    var hitRow = x.judge.filter(function (r) { return r.hit; })[0];
    var lvl = x.alerting ? x.level : x.computed, k = silent ? 'silent' : (LV[lvl] || 'ok');
    var dflt = x.judge[x.judge.length - 1] || {};
    var rowTxt = x.rule && x.alerting ? x.rule : hitRow ? hitRow.n + '번 줄 · ' + (x.title || hitRow.label) : (lvl === '정상' || !x.row ? '걸린 줄 없음' + (dflt.n ? ' (' + dflt.n + '번 그 외)' : '') : x.row + '번 줄');
    var head = silent ? '무음 기록 <span class="vk">계산상 ' + esc(x.computed) + '</span>' : esc(lvl || '정상');
    var sub = silent ? '모드가 꺼져 있어 경보를 울리지 않는다 — 기록만 남긴다'
      : (lvl === '정상' ? (active ? '3축 기준으로 경보 조건이 아니다' : '모드 꺼짐 — 계산돼도 무음 기록으로만 남는다')
        : (x.since ? x.since + '부터' : '') + (x.response ? ' · 대응: ' + x.response : ''));
    $('verdict').className = 'verdict ' + k;
    $('verdict').innerHTML = '<span class="vi">' + ico(k === 'silent' ? 'silent' : k) + '</span><div class="vb"><span class="vl">현재 판정</span><b class="vh">' + head + '</b>' +
      '<span class="vr">' + esc(rowTxt) + '</span><small>' + esc(sub) + '</small>' + causeHtml(x) + '</div>';
    renderPerson(x);
    // 전체 판정표 (접기) — 걸린 줄만 단계 칩, 나머지는 글자색만
    $('jt-toggle').textContent = '전체 판정표 ' + (judgeOpen ? '접기 ▾' : '보기 ▸');
    $('jt-toggle').setAttribute('aria-expanded', judgeOpen ? 'true' : 'false');
    $('jt-note').textContent = '위에서부터 처음 맞는 줄에서 멈춘다';
    $('judge').hidden = !judgeOpen;
    $('judge').innerHTML = x.judge.map(function (r) {
      var hit = r.hit, rk = LV[r.level] || 'ok';
      return '<div class="row' + (hit ? ' hit ' + (silent ? 'silent' : rk) : '') + '"><span class="n">' + (r.n || '') + '</span><span>' + esc(r.label) + '</span>' + lv(r.level, undefined, !hit) + '</div>';
    }).join('') + (x.alerting ? '' : '<p class="note" style="margin-top:6px">모드가 꺼져 있어 경보를 울리지 않는다. 판정은 무음 기록으로만 남는다' + (silent ? ' (점선이 계산된 줄)' : '') + '.</p>');
  }
  /* 세부 원인 (STEP 03-3 보완) — 판정 칸 안에 실제 원인 · 지점 · 측정값. 단계 · 경보 출력은 바꾸지 않는다.
     발생 축이 '해제'인데 원인 줄로 경보가 났으면 두 판단이 다르다는 것을 적는다 (발생 축 = 작업 시작 조건 K05, 최종 판정 = 판정표) */
  function causeHtml(x) {
    var cs = x.causes;
    if (!cs || !cs.length || x.computed === '정상') return '';
    var lines = cs.map(function (c) { return '<span class="vrel"><span class="lv crit">' + esc(c.label) + '</span> ' + esc(c.detail) + '</span>'; }).join('');
    var occ = (x.axes || []).filter(function (a) { return a.name === '발생'; })[0];
    if (occ && occ.state === '해제') {
      lines += '<span class="vrel"><span class="lv wait">발생 축 해제와 다름</span> 발생 축 \'해제\'는 작업 시작 조건(K05) 판단이다 — 최종 판정은 위 원인으로 ' + esc(x.computed) + '</span>';
    }
    return lines;
  }
  /* 사람 축 — 다른 축과 떨어진 보조 칸. 단계에는 영향 없이 대응만 바꾼다 */
  /* 센서 이상 · 측정 실패 (STEP 02-10 A-3 · B-3) — 판정 단계와 따로 보인다. 위험 수치로 바꾸지 않고, 직전 유효값과 그 시각을 나란히 적는다 */
  function faultTitle(fs) { return fs.map(function (f) { return f.label + (f.target ? ' ' + f.target : '') + ' ' + f.fault + ' (' + f.since + '~)'; }).join(' · '); }
  function renderFaults(x) {
    var box = $('faults');
    if (!box) { box = document.createElement('div'); box.id = 'faults'; box.className = 'faultbox'; $('verdict').parentNode.insertBefore(box, $('verdict').nextSibling); }
    var fs = x.faults || [];
    box.hidden = !fs.length;
    box.innerHTML = fs.length ? '<b class="fh">' + ico('info') + '센서 이상 · 측정 실패 ' + fs.length + '건</b>' + fs.map(function (f) {
      var lvTxt = f.last_valid ? '직전 유효값 ' + num(f.last_valid.value) + '% (' + f.last_valid.t + ')' : '직전 유효값 없음';
      var use = f.last_valid_used ? '판정은 직전 유효값 기준 — 위험값으로 바꾸지 않음 · 이상 이후 값이 아님'
        : (f.last_valid_over ? '실패 전 값이 기준 초과 — 위험 미해제 · 재측정 전까지 해제 불인정'
          : '이 지점의 이전 값은 현재값으로 쓰지 않음 — 재측정 전까지 해제 불인정');
      return '<div class="fr"><span class="lv wait">' + esc(f.fault) + '</span><span class="fw"><b>' + esc(f.label + (f.target ? ' ' + f.target : '')) + '</b> ' +
        esc(f.since) + '부터 · ' + num(f.minutes) + '분째' + (f.count > 1 ? ' · ' + f.count + '회' : '') + ' · 마지막 입력 <span class="mono">' + esc(f.raw) + '</span> (' + esc(f.t) + ')<br><small>' +
        esc(lvTxt) + ' · ' + esc(use) + '</small></span></div>';
    }).join('') : '';
    // 판정 신뢰 제한 (STEP 02-10 보완 B) — 단계 글자는 그대로 두고, 그 계산이 지금 센서값에 기댄 것이 아님을 판정 칸 안에 적는다
    var vb = $('verdict').querySelector('.vb');
    if (vb && x.reliability) {
      var r = x.reliability;
      // 신뢰가 제한된 '정상'은 초록으로 보이지 않게 — 단계 글자는 그대로 (가스 카드의 '초록은 해제 조건과 같은 뜻'과 같은 원칙)
      if ($('verdict').classList.contains('ok')) { $('verdict').classList.remove('ok'); $('verdict').classList.add('rel'); }
      vb.insertAdjacentHTML('beforeend', '<span class="vrel"><span class="lv wait">' + (r.state === 'none' ? '판정 근거 없음' : '판정 신뢰 제한') + '</span> ' +
        esc(r.text) + ' · ' + esc(r.since) + '부터 ' + num(r.minutes) + '분째</span>');
    }
  }
  function renderPerson(x) {
    renderFaults(x);
    var on = LIVE.video ? x.people > 0 : !!x.present;
    var ppl = LIVE.video ? '사람 ' + x.people + '명 감지 (영상)' : (x.present ? '허가 작업 중 — 사람이 있다고 본다' : '영상 없음 · 허가 작업 없음');
    // 보호구 (10/7) — 영상이 돌고 보호구 모델이 붙었을 때만. 안전모 · 안전조끼마다 사람 수 − 착용 = 미착용.
    // 너무 작은 사람은 따로 센다(미착용에 안 넣는다)
    var list = LIVE.video ? x.ppe : null, ppe = '', bad = false;
    if (list && x.people) {
      ppe = list.map(function (h) {
        bad = bad || h.off > 0;
        return '<span class="ppe"><span class="lv ' + (h.off ? 'crit' : 'ok') + '">' + esc(h.label) + ' 미착용 ' + h.off + '명</span>' +
          '<span class="pc">착용 ' + h.on + (h.skip ? ' · 판단 보류 ' + h.skip : '') + '</span></span>';
      }).join('');
    } else if (LIVE.video && x.ppe === null && x.people) {
      ppe = '<span class="ppe"><span class="pc">보호구 — 모델이 안 붙어 있다 (detect.json ppe)</span></span>';
    }
    $('person').className = 'person' + (on ? ' on' : '') + (bad ? ' nohat' : '');
    $('person').innerHTML = '<span class="axi">' + ico('user') + '</span><div class="pb"><b>' + esc(ppl) + '</b>' + ppe +
      '<small>단계에는 영향 없음 · 대응만 바뀐다' + (x.response && x.alerting ? ' — ' + esc(x.response) : '') + '</small></div>' +
      '<span class="pn mono">' + x.people + '</span>';
  }
  $('jt-toggle').addEventListener('click', function () { judgeOpen = !judgeOpen; if (LIVE) renderAxes(zoneOf(curZone)); });
  function renderZoneDetail() {
    var x = zoneOf(curZone); if (!x) return;
    renderCam(x);
    renderAxes(x);
    var today = LIVE.events.filter(function (e) { return e.zone === x.id; });
    $('zlog-title').textContent = '최근 기록 · ' + x.id + ' ' + today.length + '건 · ' + LIVE.log_src;
    $('zlog').innerHTML = today.length ? today.slice(0, 14).map(function (e) {
      return '<div><span class="t">' + e.time + '</span><span title="' + esc(e.type) + '">' + esc(e.title || e.type) + ' · ' + esc(e.mode) + (e.adj ? ' · ' + tag('강화 ' + e.adj, 'adj') : '') + '</span>' + kindTag(e) + '</div>';
    }).join('') : '<p class="empty">오늘 기록 없음</p>';
    if (x.ptws.length) {
      // 격리 목록 누락 · 미첨부는 작업 전 차단 대상 — 경보 주황 + 자물쇠 (빨강은 최고 경보 · 사고에만)
      $('zptw').innerHTML = '<div class="ph"><h2>작업허가서 · 격리 상태</h2><button class="go" type="button" data-go="iso" data-ptw="' + esc(x.ptws[0].id) + '">격리 목록 대조로 →</button></div><div class="stack">' +
        x.ptws.map(function (p) {
          return '<div class="hcard' + (p.kind === 'crit' ? ' gatec' : '') + '"><div class="hd"><b class="mono">' + esc(p.id) + '</b>' + ptwTag(p.kind, p.tag) + '</div><p>' + esc(p.work) + '</p><p>' + esc(p.type) + ' · ' + esc(p.when) + ' · 발생 축 해제: <b>' + esc(p.clear) + '</b></p></div>';
        }).join('') + '</div>';
    } else { $('zptw').innerHTML = '<div class="ph"><h2>작업허가서 · 격리 상태</h2></div><p class="empty">이 구역에 걸린 허가서가 없다.</p>'; }
  }
  /* 다음 처리 — 판정 바로 아래. 숫자는 이 세션 · 전 구역 기준(고른 구역 기준이 아니다) */
  function renderNext() {
    var c = LIVE.counts;
    function row(icon, label, n, sub, btn) {
      return '<div class="nxr' + (n ? '' : ' zero') + (icon === 'gate' ? ' g' : '') + '"><span class="nxi">' + ico(icon) + '</span><div class="nxb"><b>' + label + ' <span class="mono">' + n + '</span>건</b><small>' + sub + '</small></div>' + btn + '</div>';
    }
    $('lv-next').innerHTML =
      row('doc', '시정지시서 초안', c.alerts, '경보 이상 기록에서 만든다 · 발행은 사람이', '<button class="btn sm doc" type="button" id="go-co">안전 문서로 →</button>') +
      row('doc', '수시 위험성평가 제안', c.adhoc, '위험도 12 이상 또는 중대성 4등급 1건이면 열린다', '<button class="btn sm doc" type="button" data-go="docs" data-tab="ra">위험성평가로 →</button>') +
      (c.gates ? row('gate', '작업 전 차단', c.gates, '격리 목록 누락 등으로 작업 시작을 막은 기록 (R1)', '<button class="btn sm doc" type="button" data-go="docs" data-tab="ptw">작업허가서 점검 →</button>') : '');
  }
  function renderCtl() {
    var m = LIVE.meta;
    $('lv-play').textContent = LIVE.running ? '⏸ 멈춤' : (LIVE.sid ? '▶ 계속' : '▶ 시작');
    $('lv-status').innerHTML = (LIVE.sid ? '세션 <b>' + esc(LIVE.sid) + '</b> · ' : '미리 보기 · ') + esc(m.schedule_title) + ' · 규칙 ' + esc(m.rules_label) +
      (LIVE.scene ? ' · 영상 장면 ' + esc(LIVE.scene.name) : ' · 영상 장면 없음') + (LIVE.video_note ? ' · ' + esc(LIVE.video_note) : '');
    renderSigpadState();
    var nh = LIVE.notes.length ? LIVE.notes.map(function (n) { return '<div><span class="t">' + n.t + '</span>' + esc(n.msg) + '</div>'; }).join('') : '<div>엔진 메모 없음 — 신호가 무엇을 바꿨는지 여기에 남는다</div>';
    if ($('lv-notes').getAttribute('data-h') !== nh) { $('lv-notes').innerHTML = nh; $('lv-notes').setAttribute('data-h', nh); }
    $('lv-notes-n').textContent = LIVE.notes.length ? '최근 ' + LIVE.notes.length + '줄 · 마지막 ' + LIVE.notes[0].t : '신호가 무엇을 바꿨는지';
  }
  /* 접는 칸 (엔진 메모) — 연 상태는 이 브라우저에 기억 */
  function drawer(id, open) {
    var sec = $(id), b = sec.querySelector('.dr-b'), h = sec.querySelector('.dr-h');
    if (open === undefined) open = b.hidden;
    b.hidden = !open; h.setAttribute('aria-expanded', open ? 'true' : 'false');
    h.querySelector('.chev').textContent = open ? '▾' : '▸';
    store('dr:' + id, open ? '1' : '0');
  }
  ['dr-notes'].forEach(function (id) {
    $(id).querySelector('.dr-h').addEventListener('click', function () { drawer(id); });
    if (store('dr:' + id) === '1') drawer(id, true);
  });
  var wasVideo = false;
  function renderLive() {
    if (!curZone || !zoneOf(curZone)) curZone = (META && META.focus_zone) || LIVE.zones[0].id;
    if (LIVE.video && !wasVideo && LIVE.scene) focusCam(LIVE.scene.camera);    // 영상이 막 돌기 시작 — 그 카메라 화면으로
    wasVideo = !!LIVE.video;
    renderCtl(); renderRun(); renderZones(); renderZoneDetail(); renderNext(); renderDetFp();
  }
  /* 실시간 탐지 오탐 (10/8) — 지금 영상에서 잡힌 탐지 하나를 골라 판정에서 뺀다. control/detfp.py
     사람 = 영상 끝까지 · 보호구 미착용 = 그 사람의 그 보호구만 판단 보류 · 물체(불꽃) = 같은 자리를 정해진 시간 동안 */
  function renderDetFp() {
    var a = LIVE.det_fp || [], el = $('cam-fp-list');
    $('cam-fp').disabled = !LIVE.video;
    var h = a.length ? '<span class="d">오탐 처리 중</span>' + a.map(function (r) {
      return '<span class="lv note">' + (r.seen_at ? '<span class="t" title="탐지된 시각">' + esc(r.seen_at.slice(11, 19)) + '</span> ' : '') + esc(r.label) + ' · ' + esc((r.action_label || '').split(' - ')[0]) + ' · ' + (r.left_s !== null && r.left_s !== undefined ? fmtSec(r.left_s) + ' 남음' : '영상 끝까지') +
        ' <button type="button" data-dfp="' + esc(r.dfp_id) + '">해제</button></span>';
    }).join('') : '';
    if (el.getAttribute('data-h') !== h) { el.innerHTML = h; el.setAttribute('data-h', h); }
    el.hidden = !a.length;
  }
  /* 등록 창의 '저장될 이미지 로그' 미리 보기 (10/8 오후) — 창을 연 순간 고정한 그림(/api/live/snapshot)을 그대로 보인다.
     저장하면 이 그림들이 control/records/dataset/ 에 남는다. key = 'now' 또는 탐지 ref */
  function logPreview(snapId, key, crop, caption) {
    var u = function (k) { return '/api/live/snapshot/' + encodeURIComponent(snapId) + '/img?key=' + encodeURIComponent(key) + '&kind=' + k; };
    return '<div class="logpv" id="logpv"><div class="logpv-h"><b>저장될 이미지 로그</b> <span class="note">' + esc(caption) + '</span></div><div class="logpv-g">' +
      '<figure class="big"><img src="' + u('view') + '" alt="관제 화면"><figcaption>관제 화면</figcaption></figure><div class="logpv-s">' +
      (crop ? '<figure><img src="' + u('crop') + '" alt="박스 둘레" onerror="this.parentNode.hidden=true"><figcaption>박스 둘레</figcaption></figure>' : '') +
      '<figure><img src="' + u('raw') + '" alt="원본" onerror="this.parentNode.hidden=true"><figcaption>원본 (학습용)</figcaption></figure></div></div></div>';
  }
  $('cam-fp').addEventListener('click', function () {
    if (!LIVE || !LIVE.video) { flash('영상 탐지가 돌 때만 고를 수 있다', true); return; }
    // 창을 여는 순간의 목록을 그대로 들고 있다가 보낸다 — 저장하는 사이 사람이 화면 밖으로 나가도 저장된다 (10/8 오후)
    // 목록에는 지금 잡힌 것 + 최근 30초 안에 잡혔다 사라진 것(몇 초 전)이 들어 있다. 번호는 영상 위 꺽쇠 이름표와 같다
    var snap = (LIVE.dets || []).slice();
    function optText(d) { return d.label + (d.now ? '' : ' · ' + d.ago + '초 전 사라짐') + (d.seen_at ? ' · ' + d.seen_at.slice(11, 19) : ''); }
    function byRef(r) { return snap.filter(function (x) { return x.ref === r; })[0] || snap[0]; }
    var cam = LIVE.scene && LIVE.scene.camera;
    // 판정 처리 방식은 탐지 종류마다 다르다 (10/8 오후) — 첫 번째 '기록만'이 기본값. 경보 중이면 판정을 바꾸는 쪽에 확인을 받는다
    // 창을 여는 순간 그 화면을 서버에 고정한다 (10/8 오후) — 창 맨 위 그림 = 이미지 로그로 남을 그림. 저장을 누른 순간이 아니다
    api('/api/live/snapshot', {purpose: 'fp'}).catch(function () { return {}; }).then(function (al) {
      if (al.dets && al.dets.length) snap = al.dets;
      function fpPv(d) { return logPreview(al.snap_id, d.ref, true, (d.seen_at ? '탐지 ' + d.seen_at.slice(11, 19) + ' · ' : '') + d.label + ' — 저장하면 이대로 남는다. 위 관제 화면의 P번호를 보고 고른다'); }
      if (!snap.length) { flash('지금 · 최근 30초 안에 잡힌 탐지가 없다', true); return; }
      var fields = [{k: 'ref', label: '잘못 잡힌 탐지 — 위 그림의 P번호와 같다', options: snap.map(function (d) { return {v: d.ref, t: optText(d)}; })},
                    {k: 'action', label: '판정은 어떻게 할까', options: META.fp_actions[snap[0].kind]},
                    {k: 'cat', label: '오탐 사유', options: [{v: '', t: '고른다'}].concat(META.fp_reasons)},
                    {k: 'reason', label: '기타 사유', area: true, req: true, ph: '무엇을 잘못 잡았는지 적는다', show: {k: 'cat', v: '기타'}}];
      // 경보 중 확인 칸은 늘 둔다 — 창을 연 뒤에 경보가 올라가도(영상은 계속 돈다) 여기서 확인하고 저장할 수 있게
      fields.push({k: 'confirm', label: '경보 중 확인 — ' + (al && al.alarm ? (al.zone + ' 이(가) 지금 ' + al.alarm) : '구역이 경보 · 최고 경보일 때 판정을 바꾸려면 고른다'),
        options: [{v: '', t: al && al.alarm ? '판정을 바꾸는 처리를 골랐으면 여기서 확인한다' : '지금은 경보 아님 — 필요 없다'}, {v: 'yes', t: '확인 — 경보 중인 판정을 바꾼다 (기록에 남는다)'}]});
      fields.push({k: 'by', label: '표시자', req: true});
      ask({title: '탐지 오탐 — 지금 영상',
        html: al.snap_id ? fpPv(snap[0]) : '',
        img: al.snap_id ? '' : (cam ? '/api/live/frame/' + encodeURIComponent(cam) + '?t=' + Date.now() : ''),
        imgAlt: '지금 영상 — 사람 위 P번호를 보고 고른다',
        note: '잘못 잡힌 탐지를 고르고 판정을 어떻게 할지 정한다. 기본은 기록만(판정은 그대로) — 진짜 위험을 놓치지 않게. 표시자 · 사유 · 처리 방식이 남고 탐지 신뢰도 화면 · 히트맵 · 통계에 모인다.',
        fields: fields}, function (v) {
        if (!v.cat) return Promise.reject(new Error('오탐 사유를 고른다'));
        if (al && al.alarm && v.action !== 'record' && !v.confirm) return Promise.reject(new Error(al.zone + ' 이(가) 지금 ' + al.alarm + ' 이다 — 판정을 바꾸려면 경보 중 확인을 고른다'));
        var d = byRef(v.ref);
        return api('/api/live/det-fp', {ref: v.ref, xyxy: d ? d.xyxy : null, target: d || null, by: v.by, cat: v.cat, reason: v.reason,
                                        action: v.action, confirm: v.confirm === 'yes', snap_id: al.snap_id || ''})
          .then(function (r) { flash(r.msg); loadLive(); })
          .catch(function (e) {                // 저장 사이 경보가 올라갔다 — 확인 칸으로 안내한다
            var c = $('askf-confirm'); if (c && /경보/.test(e.message)) { c.focus(); c.closest('.field').classList.add('need'); }
            throw e;
          });
      });
      // 탐지를 바꾸면 그 종류의 처리 방식으로 바꾼다
      $('askf-ref').addEventListener('change', function () {
        var pv = $('logpv'); if (pv && al.snap_id) pv.outerHTML = fpPv(byRef(this.value));     // 고른 탐지의 그림으로
        $('askf-action').innerHTML = META.fp_actions[byRef(this.value).kind].map(function (x, i) { return opt(x.v, x.t, i === 0); }).join('');
      });
    });
  });
  $('cam-fp-list').addEventListener('click', function (e) {
    var b = e.target.closest('[data-dfp]'); if (!b) return;
    var id = b.getAttribute('data-dfp');
    ask({title: '오탐 처리 해제 — ' + id, note: '다음 탐지부터 다시 판정한다.',
      fields: [{k: 'mode', label: '해제 방식', options: [{v: 'end', t: '오탐 처리 끝 — 기록은 남긴다'}, {v: 'undo', t: '잘못 고름 — 기록도 취소'}]},
               {k: 'by', label: '해제한 사람', req: true}]}, function (v) {
      return api('/api/live/det-fp/clear', {dfp_id: id, by: v.by, undo: v.mode === 'undo'}).then(function (r) { flash(r.msg); loadLive(); });
    });
  });
  function loadLive() { return api('/api/live').then(function (d) { LIVE = d; renderLive(); }).catch(fail); }

  $('z-toggle').addEventListener('click', function () {
    zonesOpen = !zonesOpen;
    $('zones').hidden = !zonesOpen; $('zstrip').hidden = zonesOpen;
    this.textContent = zonesOpen ? '간단히 보기' : '구역 전체 보기';
    this.setAttribute('aria-expanded', zonesOpen ? 'true' : 'false');
  });
  $('lv-more').addEventListener('click', function () {
    var p = $('lv-panel'); p.hidden = !p.hidden; this.setAttribute('aria-expanded', p.hidden ? 'false' : 'true');
  });
  function liveForm() {
    return {schedule: $('lv-sched').value, ruleset: $('lv-rs').value, scene: $('lv-scene').value};
  }
  $('lv-new').addEventListener('click', function () {
    busy(this, api('/api/live/session', liveForm())).then(function (d) { flash(d.msg); popSid = undefined; tick(); }).catch(fail);
  });
  $('lv-play').addEventListener('click', function () {
    busy(this, api('/api/live/play', liveForm())).then(function (d) { flash(d.msg); tick(); }).catch(fail);
  });
  /* 3축 신호 버튼 (10/8) — 영상 목록 위. 누르면 그 신호가 지금 시각으로 엔진에 들어가고 3축 신호판이 바뀐다.
     버튼은 패키지 buttons.json 에서 group(작업 허가 · 발생 · 축적 · 점화원 · 사고)이 있는 것. 세션이 돌 때만 누를 수 있다.
     구역이 비어 있는 버튼은 지금 고른 구역(3축 신호판의 구역)으로, 구역이 적힌 버튼(Z8 배관 신호)은 늘 그 구역으로 들어간다 */
  function renderSigpad() {
    var bs = META.buttons || [], groups = [];
    bs.forEach(function (b) { if (groups.indexOf(b.group) < 0) groups.push(b.group); });
    $('sigpad').hidden = !bs.length;
    $('sigpad').innerHTML = '<div class="sp-h"><b>3축 신호 · <span id="sp-zone"></span></b><span class="note" id="sp-note"></span></div>' +
      groups.map(function (g) {
        return '<div class="sp-g"><span class="sp-lb">' + esc(g) + '</span>' + bs.filter(function (b) { return b.group === g; }).map(function (b) {
          return '<button class="btn sm" type="button" data-press="' + esc(b.key) + '"' + (b.zone ? ' title="늘 ' + esc(b.zone) + ' 로 들어간다"' : '') + '>' +
            (b.zone ? '<span class="sp-z">' + esc(b.zone) + '</span>' : '') + esc(b.label) + '</button>';
        }).join('') + '</div>';
      }).join('');
  }
  function renderSigpadState() {
    var on = !!(LIVE && LIVE.sid);
    $('sigpad').querySelectorAll('[data-press]').forEach(function (b) { b.disabled = !on; });
    var zt = $('sp-zone'); if (zt) zt.textContent = curZone ? curZone + ' ' + ((zoneOf(curZone) || {}).name || '') : '';
    var n = $('sp-note'); if (n) n.textContent = on ? '누르면 지금 시각으로 이 구역에 들어간다 (구역은 위 구역 줄에서 고른다)' : '세션을 시작하면 누를 수 있다';
  }
  $('sigpad').addEventListener('click', function (e) {
    var b = e.target.closest('[data-press]'); if (!b) return;
    busy(b, api('/api/live/press', {key: b.getAttribute('data-press'), zone: curZone})).then(function (d) { flash(d.msg); tick(); }).catch(fail);
  });
  $('lv-sched').addEventListener('change', fillScenes);
  function fillScenes() {
    var sc = META.schedules.filter(function (x) { return x.key === $('lv-sched').value; })[0];
    $('lv-scene').innerHTML = opt('', '영상 없음 — 신호로만 판정') + (sc ? sc.scenes.map(function (x) { return opt(x.name, x.name + ' · ' + (x.camera || '') + (x.own ? ' · 그린 구역' : '')); }).join('') : '');
    if (typeof sceneHint === 'function') sceneHint();
    if (typeof renderVideos === 'function') renderVideos();
  }
  $('lv-send').addEventListener('click', function () {
    busy(this, api('/api/live/handoff', {})).then(function (d) { return followSpace(d.space).then(function () { flash(d.msg); show('docs', {tab: 'handoff', hid: d.handoff_id}); }); }).catch(fail);
  });
  function goCorrectiveFromLive() {
    api('/api/live/corrective', {}).then(function (d) { return followSpace(d.space).then(function () { show('docs', {tab: 'corrective', ev: d.event_id}); }); }).catch(fail);
  }
  document.addEventListener('click', function (e) { if (e.target.closest('#go-co')) goCorrectiveFromLive(); });

  /* ---------- 2. 격리 목록 대조 (10/6 개편) ----------
     입력 창구 + 작업 전 게이트. 왼쪽 = 고른 허가서의 판정 · 계통도 ↔ 목록 대조 · 등록, 오른쪽 = 해제 조건 · 단계 입력 · 최근 이력 · 다음 연결.
     단계 입력은 추가만 된다 — 화면은 마지막 기록을 현재값으로 보이고, 이전 값은 서랍(전체 입력 이력)에 남긴다.
     상태 색은 10/6 표현 체계 그대로: 작업 전 차단 = 경보 주황 + 자물쇠, 사람 처리 대기 = 앰버, 충족 = 초록, 정보(진행 · 유효) = 슬레이트 파랑. */
  ICO.xc = '<circle cx="12" cy="12" r="9"/><path d="M15 9l-6 6"/><path d="M9 9l6 6"/>';
  ICO.blind = '<path d="M2 12h7"/><path d="M15 12h7"/><rect x="9" y="4" width="6" height="16" rx="1.5"/>';
  ICO.bars = '<path d="M6 20v-6"/><path d="M12 20V8"/><path d="M18 20V11"/><path d="M3 20h18"/>';
  ICO.screen = '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8"/><path d="M12 16v4"/>';
  ICO.list = '<path d="M9 6h12"/><path d="M9 12h12"/><path d="M9 18h12"/><path d="M4 6h.01"/><path d="M4 12h.01"/><path d="M4 18h.01"/>';
  ICO.dash = '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>';

  var ISO = {list: [], kpi: null, cur: null, detail: null, open: null, sheet: null, sheetArg: null, histF: 'all', ptwF: 'active', back: null};
  var VCLS = {'작업 시작 차단': 'gate', '작업 시작 대기': 'wait', '작업 시작 가능': 'ok', '격리 비대상': 'mute', '대조 불가': 'mute'};
  function num(v) { return v == null ? '—' : (Math.round(v * 10) / 10).toString(); }

  // 배관 줄 하나의 대조 상태 — 표 · 그림 · 서랍이 같이 쓴다
  function lineState(l, p) {
    if (p.no_list) return {k: 'mute', t: '미정', b: '목록 없음'};
    if (!l.in_list) return {k: 'miss', t: '누락', b: l.blind === 'done' ? '설치 (목록 없음)' : '없음'};
    if (l.blind === 'done') return {k: 'ok', t: '일치', b: '설치'};
    if (l.blind === 'valve') return {k: 'wait', t: '밸브만', b: '밸브만'};
    return {k: 'wait', t: '맹판 대기', b: '대기'};
  }
  function lineChip(st) {
    if (st.k === 'ok') return '<span class="lv ok">' + ico('ok') + esc(st.t) + '</span>';
    if (st.k === 'miss') return '<span class="lv warn lv3">' + ico('note') + esc(st.t) + '</span>';
    if (st.k === 'wait') return '<span class="lv note">' + ico('wait') + esc(st.t) + '</span>';
    return '<span class="lv silent">' + esc(st.t) + '</span>';
  }

  function isoDiagram(p, big) {
    var L = p.lines, n = Math.max(L.length, 1), rowH = 72, top = 48, W = 500, H = top + n * rowH + 36;
    var meas = {}; (p.meas || []).forEach(function (m) { meas[m.line_id] = m; });
    var F = ' font-family="IBM Plex Sans KR,sans-serif"', M = ' font-family="IBM Plex Mono,monospace"';
    var COL = {ok: 'var(--ok)', miss: 'var(--warn-line)', wait: 'var(--note-line)', mute: 'var(--mute-line)'};
    var BG = {ok: 'var(--ok-bg)', miss: 'var(--warn-bg)', wait: 'var(--note-bg)', mute: 'var(--panel-2)'};
    var TX = {ok: 'var(--ok)', miss: 'var(--warn)', wait: 'var(--note)', mute: 'var(--ink-3)'};
    var s = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + esc(p.equipment) + ' 배관 계통도와 격리 목록 대조"' + (big ? ' class="big"' : '') + '>';
    // 공급 측 · 설비
    s += '<text x="22" y="24" font-size="11.5" font-weight="600" fill="var(--ink-3)"' + F + '>공급 측</text>';
    s += '<line x1="30" y1="34" x2="30" y2="' + (top + n * rowH - 16) + '" stroke="var(--line)" stroke-width="2"/>';
    var vx = 410, vy = top - 14, vh = n * rowH - 6;
    s += '<rect x="' + vx + '" y="' + vy + '" width="84" height="' + vh + '" rx="22" fill="var(--panel-2)" stroke="var(--ink-3)" stroke-width="1.5"/>';
    var eq = String(p.equipment || '').split(' ('), ey = vy + vh / 2 - (eq.length > 1 ? 8 : 0);
    s += '<text x="' + (vx + 42) + '" y="' + ey + '" font-size="14" font-weight="700" fill="var(--ink)" text-anchor="middle"' + F + '>' + esc(eq[0]) + '</text>';
    if (eq.length > 1) s += '<text x="' + (vx + 42) + '" y="' + (ey + 18) + '" font-size="11" fill="var(--ink-2)" text-anchor="middle"' + F + '>(' + esc(eq.slice(1).join(' (')) + '</text>';
    L.forEach(function (l, i) {
      var st = lineState(l, p), k = st.k, c = COL[k], y = top + i * rowH + 18, dash = (k === 'miss' || k === 'mute' || l.blind === 'valve') ? ' stroke-dasharray="8 6"' : '';
      // 배관 — 설비까지
      s += '<circle cx="30" cy="' + y + '" r="4" fill="var(--ink-3)"/>';
      s += '<line x1="30" y1="' + y + '" x2="' + vx + '" y2="' + y + '" stroke="' + c + '" stroke-width="5" stroke-linecap="round"' + dash + '/>';
      s += '<path d="M' + (vx - 12) + ',' + (y - 6) + ' L' + vx + ',' + y + ' L' + (vx - 12) + ',' + (y + 6) + '" fill="none" stroke="' + c + '" stroke-width="2.5"/>';
      // 배관 이름표
      var tw = 14 + String(l.line_id).length * 8.2;
      s += '<rect x="44" y="' + (y - 33) + '" width="' + tw + '" height="20" rx="5" fill="' + BG[k] + '" stroke="' + c + '"/>';
      s += '<text x="' + (44 + tw / 2) + '" y="' + (y - 19) + '" font-size="12.5" font-weight="700" fill="' + TX[k] + '" text-anchor="middle"' + M + '>' + esc(l.line_id) + '</text>';
      s += '<text x="' + (52 + tw) + '" y="' + (y - 19) + '" font-size="12" fill="var(--ink-2)"' + F + '>' + esc(l.name) + (l.hazard ? ' · 가연물' : '') + '</text>';
      // 차단밸브 (◇◇)
      s += '<path d="M90,' + (y - 9) + ' L102,' + y + ' L90,' + (y + 9) + ' z" fill="var(--panel)" stroke="var(--ink-2)" stroke-width="1.6"/><path d="M114,' + (y - 9) + ' L102,' + y + ' L114,' + (y + 9) + ' z" fill="var(--panel)" stroke="var(--ink-2)" stroke-width="1.6"/>';
      // 맹판 자리
      var bx = 170, lab = '', lc = TX[k];
      if (k === 'miss') {
        s += '<circle cx="' + bx + '" cy="' + y + '" r="11" fill="var(--warn-line)"/><text x="' + bx + '" y="' + (y + 4.5) + '" font-size="14" font-weight="700" fill="#fff" text-anchor="middle"' + F + '>!</text>';
        s += '<rect x="' + (bx + 18) + '" y="' + (y - 11) + '" width="76" height="22" rx="11" fill="var(--panel)" stroke="var(--warn-line)" stroke-width="1.5"/><text x="' + (bx + 56) + '" y="' + (y + 4) + '" font-size="11.5" font-weight="700" fill="var(--warn)" text-anchor="middle"' + F + '>목록 누락</text>';
        lab = l.blind === 'done' ? '맹판 O · 목록 없음' : '밸브만 · 목록 없음';
      } else if (l.blind === 'done') {
        s += '<rect x="' + (bx - 5) + '" y="' + (y - 16) + '" width="10" height="32" rx="2" fill="var(--ok)"/>';
        lab = '맹판 설치' + (l.by_step ? ' (단계 입력)' : '');
      } else if (k === 'wait') {
        s += '<rect x="' + (bx - 6) + '" y="' + (y - 16) + '" width="12" height="32" rx="2" fill="var(--panel)" stroke="var(--note-line)" stroke-width="2"' + (l.blind === 'valve' ? ' stroke-dasharray="4 3"' : '') + '/>';
        lab = l.blind === 'valve' ? '밸브만 잠김 — 해제 아님' : '맹판 설치 대기';
      } else { lab = '목록 없음 — 판단 불가'; }
      if (lab) s += '<text x="' + (bx - 10) + '" y="' + (y + 30) + '" font-size="11.5" font-weight="600" fill="' + lc + '"' + F + '>' + esc(lab) + '</text>';
      // 가스 측정 지점
      var m = meas[l.line_id];
      if (m) {
        var gx = 312, gk = m.ok ? 'ok' : (m.over && m.valid ? 'over' : 'none');
        var gf = gk === 'ok' ? 'var(--ok)' : gk === 'over' ? 'var(--warn-line)' : 'var(--panel)';
        s += '<circle cx="' + gx + '" cy="' + y + '" r="8" fill="' + gf + '" stroke="' + (gk === 'none' ? 'var(--ink-3)' : gf) + '" stroke-width="2"/>';
        var gt = !m.measured ? '측정 없음' : (m.value + (!m.valid ? ' · 만료' : m.over ? ' · 기준 초과' : ''));
        s += '<text x="' + (gx - 30) + '" y="' + (y + 30) + '" font-size="11.5" font-weight="600" fill="' + (gk === 'over' ? 'var(--warn)' : gk === 'ok' ? 'var(--ok)' : 'var(--ink-3)') + '"' + F + '>' + esc(gt) + '</text>';
      }
    });
    s += '<text x="22" y="' + (H - 10) + '" font-size="11" fill="var(--ink-3)"' + F + '>◇◇ 차단밸브 · ▮ 맹판 · ● 가스 측정 지점 · 점선 = 맹판 없이 이어진 구간</text>';
    return s + '</svg>';
  }
  function isoTable(p) {
    var rows = p.lines.map(function (l) {
      var st = lineState(l, p);
      return '<tr class="' + (st.k === 'miss' ? 'miss' : '') + '"><td><b class="mono">' + esc(l.line_id) + '</b><small>' + esc(l.name) + '</small></td>' +
        '<td>있음</td><td>' + (p.no_list ? '—' : l.in_list ? '있음' : '<b class="x">없음</b>') + '</td><td>' + lineChip(st) + '</td></tr>';
    }).join('') + p.extra.map(function (x) {
      return '<tr class="miss"><td><b class="mono">' + esc(x.split(' ')[0]) + '</b><small>' + esc(x.split(' ').slice(1).join(' ')) + '</small></td><td><b class="x">없음</b></td><td>있음</td><td><span class="lv warn">' + ico('note') + '계통도 확인</span></td></tr>';
    }).join('');
    return '<table class="t iso-t"><thead><tr><th>라인</th><th>계통도</th><th>격리 목록</th><th>상태</th></tr></thead><tbody>' + rows + '</tbody></table>' +
      (!p.target ? '<p class="note" style="margin-top:8px">화기 허가서 — 격리 비대상. 이 구역 배관의 격리 상태는 정비 허가서에서 본다.</p>'
        : p.no_list ? '<p class="note" style="margin-top:8px">격리 목록이 첨부되지 않아 배관마다 대조할 수 없다.</p>' : '');
  }

  function loadIso(pick) {
    return api('/api/iso').then(function (d) {
      ISO.list = d.ptws; ISO.kpi = d.kpi;
      if (pick) ISO.cur = pick;
      renderIsoKpis(); renderIsoPicks();
      if (ISO.sheet === 'ptws') renderSheet();
    }).catch(fail);
  }
  function renderIsoKpis() {
    var k = ISO.kpi, wb = k.wait_by;
    function card(ic, cls, label, n, small) {
      return '<div class="kpi iso-kpi ' + cls + '"><span class="ki">' + ico(ic) + '</span><div><span>' + esc(label) + '</span><b>' + n + '<small class="u">건</small></b><small>' + esc(small) + '</small></div></div>';
    }
    $('iso-kpis').innerHTML =
      card('doc', 'info', '활성 작업허가서', k.active, '진행 중 ' + k.run + ' · 오늘 예정 ' + k.plan + (k.zones.length ? ' · ' + k.zones.join(' ') : '')) +
      card('gate', k.gate ? 'gate' : '', '작업 시작 차단', k.gate, '목록 누락 · 미첨부 · 계통도 외 배관 (R1)') +
      card('note', k.notclear ? 'wait' : 'ok', '발생 측 해제 불인정', k.notclear, k.gate ? '해제 조건 미충족 · 차단 ' + k.gate + '건 포함' : '해제 조건 네 개 중 미충족') +
      card('wait', k.wait ? 'wait' : 'ok', '단계 입력 대기', k.wait, '맹판 ' + wb.blind + ' · 가스 측정 ' + wb.gas + ' · 퍼지 ' + wb.purge);
  }
  function pickDot(p) {
    if (p.gate) return '<span class="pd gate">' + ico('gate') + '</span>';
    if (!p.target) return '<span class="pd mute">' + ico('info') + '</span>';
    if (p.clear === '인정') return '<span class="pd ok">' + ico('ok') + '</span>';
    return '<span class="pd wait">' + ico('wait') + '</span>';
  }
  function renderIsoPicks() {
    var act = ISO.list.filter(function (p) { return p.active; });
    var show_ = act.length ? act : ISO.list.slice(0, 3);
    if (!ISO.list.some(function (p) { return p.id === ISO.cur; })) {
      var pref = show_.filter(function (p) { return p.gate; })[0] || show_.filter(function (p) { return p.target; })[0] || show_[0] || ISO.list[0];
      ISO.cur = pref ? pref.id : null;
    }
    if (ISO.cur && !show_.some(function (p) { return p.id === ISO.cur; })) show_ = show_.concat(ISO.list.filter(function (p) { return p.id === ISO.cur; }));
    $('iso-picks').innerHTML = show_.map(function (p) {
      var on = p.id === ISO.cur;
      return '<button type="button" class="iso-pk' + (on ? ' on' : '') + (p.new ? ' new' : '') + '" role="radio" aria-checked="' + on + '" data-isopick="' + esc(p.id) + '" title="' + esc(p.work + ' · ' + p.verdict) + '"><i class="rd"></i><span class="mono">' + esc(p.id) + '</span>' + pickDot(p) + '</button>';
    }).join('') || '<span class="note">등록된 허가서가 없다 — 아래에서 등록한다.</span>';
    if (ISO.cur) loadIsoDetail(); else ['iso-state', 'iso-diagram', 'iso-list', 'iso-conds', 'iso-cards', 'iso-recent', 'iso-next'].forEach(function (i) { $(i).innerHTML = ''; });
  }
  function loadIsoDetail() {
    return api('/api/iso/' + encodeURIComponent(ISO.cur)).then(function (p) { ISO.detail = p; renderIsoDetail(p); if (ISO.sheet && ISO.sheet !== 'ptws') renderSheet(); }).catch(fail);
  }

  function renderIsoState(p) {
    var v = p.verdict, cls = VCLS[v.title] || 'mute', hotSim = p.simops.filter(function (x) { return x.target ? x.clear !== '인정' : true; });
    if (!p.target && hotSim.length) cls = 'wait';
    var icon = {gate: 'gate', wait: 'wait', ok: 'ok', mute: 'info'}[cls];
    var tagTxt = p.gate ? p.tag : (cls === 'wait' && p.target ? '단계 대기 ' + (p.waiting.blind + p.waiting.gas + p.waiting.purge) + '건' : (!p.target && hotSim.length ? '동시작업 주의' : ''));
    var lines = [];
    if (p.miss_ids.length && !p.no_list) lines.push('<p class="iso-miss">누락 배관 : ' + esc(p.miss_ids.join(', ')) + '</p>');
    if (p.extra.length) lines.push('<p class="iso-miss">목록에만 있는 배관 : ' + esc(p.extra.join(', ')) + '</p>');
    if (p.target && !p.gate && !p.all_ok) {
      var w = [];
      if (p.waiting.blind) w.push('맹판 ' + p.blind_wait.join(' · '));
      if (p.waiting.gas) w.push('가스 측정 ' + p.waiting.gas + '지점');
      if (p.waiting.purge) w.push('퍼지 ' + num(p.purge.minutes) + '/' + p.purge.need + '분');
      lines.push('<p>남은 단계 : ' + esc(w.join(' · ')) + '</p>');
    }
    p.simops.forEach(function (x) {
      if (p.target) lines.push('<p class="iso-sim">' + ico('flame') + '동시작업 : ' + esc(x.id) + ' ' + esc(x.type) + ' (' + esc(x.when) + ') — ' + (p.all_ok ? '해제 인정 상태' : '이 허가서 해제 인정 전 화기 금지') + '</p>');
      else lines.push('<p class="iso-sim">' + ico('flame') + '동시작업 : ' + esc(x.id) + ' ' + esc(x.type) + ' (' + esc(x.when) + ') 격리 ' + esc(x.clear === '인정' ? '해제 인정' : '해제 인정 전') + (x.clear === '인정' ? '' : ' — 화기 시작 보류') + '</p>');
    });
    var btns = '';
    if (p.gate) btns += '<button class="btn dark sm" type="button" id="iso-redo">목록 ' + (p.no_list ? '첨부' : '보완') + ' — 다시 등록</button>';
    if (!p.target && p.simops.length) btns += '<button class="btn sm" type="button" data-isopick="' + esc(p.simops[0].id) + '">' + esc(p.simops[0].id) + ' 격리 보기</button>';
    var when = (p.ptw.start || '').replace('T', ' ') + ' ~ ' + (p.ptw.end || '').slice(11, 16);
    $('iso-state').innerHTML = '<div class="iso-verdict ' + cls + '">' +
      '<span class="vi">' + ico(icon) + '</span>' +
      '<div class="vb"><div class="vh">' + esc(v.title) + (tagTxt ? '<span class="vt">' + esc(tagTxt) + '</span>' : '') + '</div><p>' + esc(v.desc) + '</p>' + lines.join('') + (btns ? '<div class="btnrow" style="margin-top:8px">' + btns + '</div>' : '') + '</div>' +
      '<dl class="iso-meta"><dt>작업</dt><dd>' + esc(p.ptw.work) + '</dd><dt>구역</dt><dd>' + z(p.ptw.zone) + ' ' + esc(p.zname) + '</dd><dt>작업 종류</dt><dd>' + esc(p.ptw.type) + (p.ptw.work_type && p.ptw.work_type !== p.ptw.type ? ' · ' + esc(p.ptw.work_type) : '') + '</dd>' +
      '<dt>일정</dt><dd class="mono">' + esc(when) + ' <span class="lv ' + (p.phase === '진행 중' ? 'info' : 'mute') + '">' + esc(p.phase) + '</span></dd></dl></div>' +
      ((p.form || p.doc) ? '<div class="hcard soft" style="margin-top:8px">' + ptwFormHtml(p) + '</div>' : '');
  }
  function renderIsoConds(p) {
    if (!p.target) {
      $('iso-conds-sub').textContent = '격리 비대상';
      $('iso-conds').innerHTML = '<p class="note" style="margin-bottom:10px">화기 허가서는 격리 해제 조건을 따지지 않는다 (격리 비대상). 대신 같은 시간 · 인접 구역 정비 허가의 격리가 해제 인정됐는지 본다.</p>' +
        (p.simops.length ? '<ul class="iso-conds">' + p.simops.map(function (x) {
          var ok = x.clear === '인정';
          return '<li class="ic sim ' + (ok ? 'ok' : 'fail') + '"><span class="n">' + ico('flame') + '</span><div class="b"><b>동시작업 ' + esc(x.id) + ' (' + esc(x.type) + ')</b><small>' + esc(x.work) + ' · ' + esc(x.when) + '</small></div><span class="lv ' + (ok ? 'ok' : 'warn') + '">' + (ok ? '격리 해제 인정' : '격리 해제 인정 전') + '</span></li>';
        }).join('') + '</ul>' : '<p class="empty">겹치는 정비 허가가 없다.</p>');
      return;
    }
    $('iso-conds-sub').textContent = p.now + ' 기준';
    var ST = {fail: ['warn', 'xc', '실패'], run: ['info', 'wait', '진행 중'], ok: ['ok', 'ok', '충족'], na: ['mute', 'dash', '해당 없음']};
    var res = p.all_ok ? ['ok', 'ok', '발생 측 해제 인정', '작업 전 게이트 열림 · 작업 시작 가능'] : ['gate', 'gate', '발생 측 해제 불인정', '작업 전 게이트 유지 · 조건 충족 전 작업 시작 불가'];
    $('iso-conds').innerHTML = '<ol class="iso-conds">' + p.conds.map(function (c) {
      var t = ST[c.state] || ST.na;
      return '<li class="ic ' + c.state + '"><span class="n">' + c.no + '</span><span class="si ' + t[0] + '">' + ico(t[1]) + '</span>' +
        '<div class="b"><b>' + esc(c.label) + ' <span class="rule">' + esc(c.rule) + '</span></b><small>' + esc(c.desc) + '</small></div>' +
        '<span class="lv ' + t[0] + '">' + t[2] + '</span><span class="v">' + esc(c.value) + '</span></li>';
    }).join('') + '</ol>' +
      '<div class="iso-result ' + res[0] + '"><span class="vi">' + ico(res[1]) + '</span><div><b>현재 결과 : ' + res[2] + '</b><small>' + res[3] + '</small></div></div>';
  }
  function lastOf(p, group) { return p.history.filter(function (h) { return h.group === group && h.state === 'cur' && h.t; })[0]; }
  function metaLine(h, fallback) { return h ? [h.t, h.by, h.src].filter(Boolean).map(esc).join(' · ') : esc(fallback || '입력 없음'); }
  function renderIsoCards(p) {
    var eng = $('iso-eng-note');
    eng.textContent = p.engine ? '실시간 세션이 돌고 있어 같은 입력이 엔진 신호로도 들어간다. 기록에 이름이 남는다.' : '실시간 세션이 돌지 않아 기록만 남는다 (엔진에는 안 들어감). 기록에 이름이 남는다.';
    if (!p.target) { $('iso-cards').innerHTML = '<p class="empty wide">화기 허가서는 맹판 · 퍼지 단계 입력을 받지 않는다. 배관 격리 입력은 같은 구역의 정비 허가서에서 한다.</p>'; return; }
    var bt = p.blind_targets.length, bw = p.blind_wait.length;
    var blindH = p.history.filter(function (h) { return h.group === 'blind' && h.state === 'cur'; }).filter(function (h) { return h.t; })[0];
    var blind = '<div class="ic-card' + (ISO.open === 'blind' ? ' open' : '') + '"><div class="ic-h">' + ico('blind') + '<b>맹판 설치 완료</b><span class="rule">R2</span></div>' +
      '<div class="ic-v">' + (bw ? '<span class="lv note">' + ico('wait') + '미설치 ' + bw + '</span>' : '<span class="lv ok">' + ico('ok') + '전부 설치</span>') + '<span class="big">' + (bt - bw) + '<small> / ' + bt + ' 설치</small></span></div>' +
      '<p class="ic-m">' + (bw ? '대기 <b class="mono">' + esc(p.blind_wait.join(' · ')) + '</b><br>' : '') + '마지막 변경 ' + metaLine(blindH, '없음 — 격리 목록 기재값') + '</p>' +
      '<div class="ic-b"><button class="btn dark sm" type="button" data-iso-open="blind" aria-expanded="' + (ISO.open === 'blind') + '">입력</button><button class="btn sm" type="button" data-iso-hist="blind">이력</button></div></div>';
    var fBlind = '<div class="ic-f" data-for="blind"><div class="ic-fh"><b>맹판 설치 입력</b><span class="note">배관마다 넣는다 · 잘못 넣은 완료는 정정 기록으로 되돌린다</span></div>' + p.lines.filter(function (l) { return l.target; }).map(function (l) {
        var done = l.blind === 'done';
        return '<div class="ic-row"><span><b class="mono">' + esc(l.line_id) + '</b> <small>' + esc(l.name) + (l.in_list ? '' : ' · 목록에 없음') + '</small></span>' +
          (done ? '<span class="lv ok">설치</span><button class="btn sm" type="button" data-blind-undo="' + esc(l.line_id) + '" title="잘못 넣은 완료를 지우지 않고 정정 기록을 덧붙인다">설치 취소(정정)</button>'
            : '<span class="lv note">' + (l.blind === 'valve' ? '밸브만' : '대기') + '</span><button class="btn dark sm" type="button" data-blind="' + esc(l.line_id) + '">설치 완료</button>') + '</div>';
      }).join('') + '</div>';

    var ms = p.meas, okN = ms.filter(function (m) { return m.ok; }).length;
    var valid = ms.filter(function (m) { return m.valid && m.lel != null; });
    var worst = valid.length ? valid.reduce(function (a, b) { return b.lel > a.lel ? b : a; }) : null;
    var latest = ms.filter(function (m) { return m.measured; }).sort(function (a, b) { return a.time < b.time ? 1 : -1; })[0];
    var vchip = '';
    if (latest && latest.fail) vchip = '<span class="lv wait">' + ico('wait') + '측정 실패 — 재측정 필요</span>';
    else if (latest) vchip = latest.valid ? '<span class="lv info">' + ico('wait') + '유효 · ' + latest.remain + '분 남음</span>' : '<span class="lv wait">' + ico('wait') + '만료 — 판정에서 측정 없음</span>';
    // 대표 수치 (STEP 02-8) — 값 오류 지점이 있으면 숫자 대신 '값 오류', 초록은 모든 지점이 기준 이하 · 유효할 때만 (해제 조건 ④와 같은 뜻)
    var badPts = ms.filter(function (m) { return m.bad; });
    var failPts = ms.filter(function (m) { return m.fail; });          // 측정 실패 지점 (STEP 02-10 B-3) — 기준 초과값으로 보이지 않게 숫자 대신 글자
    var gasBig = badPts.length ? '<span class="big bad">값 오류</span>' : failPts.length ? '<span class="big bad">측정 실패</span>'
      : worst ? '<span class="big ' + (worst.lel > p.lel_max ? 'bad' : (okN === ms.length ? 'good' : 'none')) + '">' + num(worst.lel) + '%</span>' : '<span class="big none">—</span>';
    var gas = '<div class="ic-card' + (ISO.open === 'gas' ? ' open' : '') + '"><div class="ic-h">' + ico('bars') + '<b>가스 측정 LEL</b><span class="rule">R4</span></div>' +
      '<div class="ic-v">' + gasBig + '<small class="ref">기준 ≤ ' + p.lel_max + '%</small></div>' +
      '<p class="ic-m">' + (latest ? esc(latest.time) + ' 측정' + (latest.by ? ' · ' + esc(latest.by) : '') + ' · ' + esc(latest.src) + ' ' + vchip : '측정 없음') +
      '<br>지점 ' + okN + '/' + ms.length + ' 기준 이하' + (badPts.length ? ' · 값 오류 <b class="mono">' + esc(badPts.map(function (m) { return m.line_id; }).join(' · ')) + '</b>' : '') + (failPts.length ? ' · 측정 실패 <b class="mono">' + esc(failPts.map(function (m) { return m.line_id; }).join(' · ')) + '</b>' : '') + (ms.filter(function (m) { return !m.measured; }).length ? ' · 미측정 <b class="mono">' + esc(ms.filter(function (m) { return !m.measured; }).map(function (m) { return m.line_id; }).join(' · ')) + '</b>' : '') + '</p>' +
      '<div class="ic-b"><button class="btn dark sm" type="button" data-iso-open="gas" aria-expanded="' + (ISO.open === 'gas') + '">새 측정값</button><button class="btn sm" type="button" data-iso-hist="gas">이력</button></div></div>';
    var fGas = '<div class="ic-f" data-for="gas"><div class="ic-fh"><b>가스 측정값 입력</b><span class="note">새 값은 이전 값을 지우지 않고 추가된다 · 유효시간 ' + p.valid_min + '분이 지나면 판정에서 측정 없음</span></div><div class="form iso-mini"><div class="field"><label for="iso-pt">측정 지점</label><select id="iso-pt">' + ms.map(function (m) { return opt(m.line_id, m.point); }).join('') + '</select></div>' +
        '<div class="field"><label for="iso-lel">LEL %</label><input id="iso-lel" type="number" min="0" step="0.1" inputmode="decimal"></div><button class="btn dark sm" type="button" id="iso-gas">측정값 입력</button><button class="btn sm" type="button" id="iso-gas-fail" title="측정하지 못했을 때 — 이 지점의 이전 값은 현재값으로 쓰지 않는다 (기준 초과로 보지도 않음)">측정 실패 기록</button></div></div>';

    var pg = p.purge, run = pg.state === 'run', pct = pg.minutes == null ? 0 : Math.min(100, pg.minutes / pg.need * 100);
    var pchip = pg.ok ? '<span class="lv ok">' + ico('ok') + '충족</span>' : run ? '<span class="lv info">' + ico('wait') + '진행 중</span>' : pg.minutes == null ? '<span class="lv silent">미실시</span>' : '<span class="lv note">' + ico('wait') + '미달</span>';
    var purge = '<div class="ic-card' + (ISO.open === 'purge' ? ' open' : '') + '"><div class="ic-h">' + ico('wait') + '<b>퍼지 시간</b><span class="rule">R4</span></div>' +
      '<div class="ic-v"><span class="big">' + num(pg.minutes) + '<small> / ' + pg.need + '분</small></span>' + pchip + '</div>' +
      '<div class="ic-bar" role="img" aria-label="퍼지 ' + num(pg.minutes) + '분 / 기준 ' + pg.need + '분"><i style="width:' + pct + '%"></i></div>' +
      '<p class="ic-m">' + (run ? '시작 ' + esc(pg.start) + (pg.by ? ' · ' + esc(pg.by) : '') + ' · 지금 ' + esc(p.now) + ' 기준 계산' : pg.minutes != null ? [pg.t ? pg.t + ' 기록' : '', pg.by, pg.src + (pg.t ? '' : ' 기재값')].filter(Boolean).map(esc).join(' · ') : '퍼지 기록 없음') + '</p>' +
      '<div class="ic-b"><button class="btn dark sm" type="button" data-iso-open="purge" aria-expanded="' + (ISO.open === 'purge') + '">입력</button><button class="btn sm" type="button" data-iso-hist="purge">이력</button></div></div>';
    var fPurge = '<div class="ic-f" data-for="purge"><div class="ic-fh"><b>퍼지 입력</b><span class="note">시작 · 종료를 그때그때 넣으면 경과 시간이 저절로 계산된다</span></div><div class="btnrow">' + (run ? '<button class="btn dark sm" type="button" data-purge="purge_end">퍼지 종료</button>' : '<button class="btn dark sm" type="button" data-purge="purge_start">퍼지 시작</button>') + '</div>' +
        '<div class="form iso-mini" style="margin-top:8px"><div class="field"><label for="iso-purge">끝난 퍼지를 분으로 기록</label><input id="iso-purge" type="number" min="0" step="1" inputmode="numeric" placeholder="분"></div><button class="btn sm" type="button" id="iso-purge-go"' + (run ? ' disabled' : '') + '>기록</button></div></div>';
    $('iso-cards').innerHTML = blind + gas + purge + ({blind: fBlind, gas: fGas, purge: fPurge}[ISO.open] || '');
  }
  function histRow(h) {
    var cls = h.state === 'old' ? ' old' : h.state === 'future' ? ' future' : '';
    var badge = h.state === 'old' ? '<span class="lv mute">이전</span>' : h.state === 'future' ? '<span class="lv silent">시계 뒤 · 반영 안 됨</span>' : '';
    if (h.valid) badge += h.valid === '유효' ? '<span class="lv info">유효</span>' : '<span class="lv wait">만료</span>';
    var tone = {ok: 'ok', crit: 'warn', warn: 'warn', info: 'info'}[h.tone] || 'mute';
    return '<li class="ih-r' + cls + '"><span class="ih-t mono">' + esc(h.t || '기재') + '</span><span class="ih-d ' + tone + '"></span>' +
      '<div class="ih-b"><b>' + esc(h.label) + (h.line_id ? ' <span class="mono">' + esc(h.line_id) + '</span>' : '') + ' <span class="ih-v ' + tone + '">' + esc(h.text) + '</span></b><small>' + esc(h.by || '—') + ' · ' + esc(h.src) + '</small></div>' + (badge ? '<span class="ih-tags">' + badge + '</span>' : '') + '</li>';
  }
  function renderIsoRecent(p) {
    var rows = p.history.filter(function (h) { return h.state !== 'future'; }).slice(0, 4);
    $('iso-recent').innerHTML = rows.length ? '<ul class="iso-hist">' + rows.map(histRow).join('') + '</ul>' : '<p class="empty">입력 기록이 아직 없다.</p>';
  }
  function renderIsoNext(p) {
    $('iso-next').innerHTML =
      '<button class="nxc" type="button" data-iso-live="' + esc(p.ptw.zone) + '">' + ico('screen') + '<span><b>실시간 관제로 보기</b><small>' + esc(p.ptw.zone) + ' 영상 · 3축 판정</small></span></button>' +
      '<button class="nxc" type="button" data-go="docs" data-tab="ptw" data-ptw="' + esc(p.ptw.ptw_id) + '">' + ico('doc') + '<span><b>작업허가서 점검으로</b><small>같은 데이터로 자동 점검</small></span></button>' +
      '<button class="nxc" type="button" data-go="log" data-q="' + esc(p.ptw.zone) + '">' + ico('list') + '<span><b>이벤트 로그 보기</b><small>' + esc(p.ptw.zone) + ' 구역 관제 기록</small></span></button>';
  }
  function renderIsoDetail(p) {
    renderIsoState(p);
    $('iso-dg-title').textContent = '배관 계통도 ↔ 격리 목록 대조 — ' + p.equipment;
    $('iso-diagram').innerHTML = p.has_pid ? isoDiagram(p) : '<p class="empty">' + esc(p.ptw.zone) + '에는 배관 계통도가 없다 — 사업장 패키지 site.json 의 piping 에 넣는다.</p>';
    $('iso-list').innerHTML = p.has_pid ? isoTable(p) : '';
    renderIsoConds(p); renderIsoCards(p); renderIsoRecent(p); renderIsoNext(p);
  }

  /* 오른쪽 서랍 — 전체 입력 이력 · 전체 허가서 목록 · 세부 기준 · 계통도 크게 보기 */
  function openSheet(mode, arg) {
    ISO.back = ISO.sheet ? ISO.back : document.activeElement;
    ISO.sheet = mode; ISO.sheetArg = arg || null;
    if (mode === 'hist') ISO.histF = arg || 'all';
    $('iso-sheet').classList.toggle('wide', mode === 'dg');
    $('iso-sheet').hidden = false; $('iso-sheet-back').hidden = false;
    renderSheet();
    $('iso-sheet-x').focus();
  }
  function closeSheet() {
    if (!ISO.sheet) return;
    ISO.sheet = null; $('iso-sheet').hidden = true; $('iso-sheet-back').hidden = true;
    if (ISO.back && ISO.back.focus && document.body.contains(ISO.back)) ISO.back.focus();
    ISO.back = null;
  }
  function renderSheet() {
    var p = ISO.detail, h = $('iso-sheet-h'), b = $('iso-sheet-b');
    if (ISO.sheet === 'hist' && p) {
      h.textContent = '단계 입력 이력 — ' + p.ptw.ptw_id;
      var F = {all: '전체', blind: '맹판', gas: '가스 측정', purge: '퍼지'};
      var rows = p.history.filter(function (x) { return ISO.histF === 'all' || x.group === ISO.histF; });
      var pg = p.purge;
      b.innerHTML = '<div class="sh-now"><b>현재 상태 <span class="sub mono">' + esc(p.now) + ' 기준</span></b>' +
        (p.target ? '<p>맹판 ' + (p.blind_targets.length - p.blind_wait.length) + '/' + p.blind_targets.length + ' 설치' + (p.blind_wait.length ? ' · 대기 ' + esc(p.blind_wait.join(', ')) : '') + '</p>' +
        '<p>가스 측정 ' + p.meas.map(function (m) { return esc(m.line_id) + ' ' + (m.measured ? esc(m.value) + (m.valid ? '' : ' 만료') : '미측정'); }).join(' · ') + '</p>' +
        '<p>퍼지 ' + num(pg.minutes) + ' / ' + pg.need + '분' + (pg.state === 'run' ? ' · 진행 중 (' + esc(pg.start) + ' 시작, 시스템 계산)' : '') + '</p>' : '<p>격리 비대상 — 단계 입력을 받지 않는다</p>') + '</div>' +
        '<div class="seg" role="group" aria-label="이력 거르기" id="sh-f">' + Object.keys(F).map(function (k) { return '<button type="button" data-hf="' + k + '"' + (ISO.histF === k ? ' class="on"' : '') + '>' + F[k] + '</button>'; }).join('') + '</div>' +
        (rows.length ? '<ul class="iso-hist full">' + rows.map(histRow).join('') + '</ul>' : '<p class="empty">기록 없음</p>') +
        '<p class="note" style="margin-top:10px">기록은 추가만 된다. 같은 대상의 이전 값은 지우지 않고 ‘이전’으로 남긴다. ‘기재’는 허가서 · 격리 목록에 처음부터 적혀 있던 값이다. 관제 시계보다 뒤 기록은 현재 상태에 넣지 않는다.</p>';
    } else if (ISO.sheet === 'ptws') {
      h.textContent = '작업허가서 전체';
      var PF = {active: '활성', bad: '차단 · 대기', all: '전체'};
      var list = ISO.list.filter(function (x) { return ISO.ptwF === 'all' || (ISO.ptwF === 'active' ? x.active : (x.gate || (x.target && x.clear !== '인정'))); });
      b.innerHTML = '<div class="seg" role="group" aria-label="허가서 거르기" id="sh-pf">' + Object.keys(PF).map(function (k) { return '<button type="button" data-pf="' + k + '"' + (ISO.ptwF === k ? ' class="on"' : '') + '>' + PF[k] + '</button>'; }).join('') + '</div>' +
        '<div class="picks" style="margin-top:10px">' + (list.map(function (x) {
          return '<button type="button" class="pick' + (x.id === ISO.cur ? ' on' : '') + '" data-isopick="' + esc(x.id) + '"><span class="top2">' + z(x.zone) + ptwTag(x.gate ? 'crit' : x.target ? (x.clear === '인정' ? 'ok' : 'note') : 'mute', x.verdict) + '</span><b>' + esc(x.work) + '</b><span class="s mono">' + esc(x.id) + ' · ' + esc(x.type) + ' · ' + esc((x.start || '').slice(5, 16).replace('T', ' ')) + '~' + esc((x.end || '').slice(11, 16)) + ' · ' + esc(x.phase) + (x.new ? ' · 방금 등록' : '') + '</span></button>';
        }).join('') || '<p class="empty">조건에 맞는 허가서가 없다.</p>') + '</div>';
    } else if (ISO.sheet === 'basis' && p) {
      h.textContent = '해제 조건 세부 기준';
      var bs = p.basis;
      b.innerHTML = '<table class="t"><thead><tr><th>조건</th><th>기준</th><th>어디서 읽나</th></tr></thead><tbody>' +
        '<tr><td>① 목록 일치 <span class="rule">R1</span></td><td>계통도 배관 전부가 목록에 · 목록에만 있는 배관 없음</td><td>사업장 패키지 site.json › piping</td></tr>' +
        '<tr><td>② 맹판 설치 <span class="rule">R2</span></td><td>목록의 배관 + 목록에 없는 가연물 배관 모두 맹판. 밸브만 잠근 것은 해제 아님</td><td>격리 목록 CSV · 단계 입력</td></tr>' +
        '<tr><td>③ 퍼지 <span class="rule">R4</span></td><td class="mono">' + bs.purge_need + '분 이상</td><td>문서 자동화 rulesets.json › isolation.purge.min_minutes</td></tr>' +
        '<tr><td>④ LEL <span class="rule">R4</span></td><td class="mono">가연물 배관 모든 지점 ≤ ' + bs.lel_max + '%</td><td>문서 자동화 rulesets.json › isolation.purge.lel_max</td></tr>' +
        '<tr><td>측정 유효시간</td><td class="mono">' + bs.valid_min + '분' + (bs.invalidated_by.length ? ' · 무효 사건 ' + esc(bs.invalidated_by.join(', ')) : '') + '</td><td>사업장 패키지 rules.json › vars.gas_valid_min (엔진과 같은 값)</td></tr>' +
        '</tbody></table><p class="note" style="margin-top:10px">' + (bs.rules_label ? '실시간 세션 규칙: ' + esc(bs.rules_label) + '. ' : '') + '이 화면은 개정 후 기준(R1 · R2 · R4)으로 판정한다. 실시간 세션이 개정 전 규칙으로 돌면 엔진 판정과 다를 수 있다 — 3축 신호판은 그 세션의 규칙을 따른다.</p>';
    } else if (ISO.sheet === 'dg' && p) {
      h.textContent = '배관 계통도 — ' + p.equipment;
      b.innerHTML = '<div class="svgwrap">' + isoDiagram(p, true) + '</div><div class="tbl" style="margin-top:12px">' + isoTable(p) + '</div>';
    }
  }

  function isoStep(kind, line, value, btn, note) {
    var by = $('iso-by').value.trim();
    if (!by) { flash('입력자 이름을 적는다 — 단계 입력 기록에 남는다', true); $('iso-by').focus(); return; }
    store('iso-by', by);
    return busy(btn, api('/api/iso/step', {ptw_id: ISO.cur, kind: kind, line_id: line, value: value, by: by, note: note || ''}))
      .then(function (d) { flash(d.msg); loadIso(); tickStatus(); }).catch(fail);
  }
  $('iso-cards').addEventListener('click', function (e) {
    var o = e.target.closest('[data-iso-open]');
    if (o) { var k = o.getAttribute('data-iso-open'); ISO.open = ISO.open === k ? null : k; renderIsoCards(ISO.detail); var f = $('iso-cards').querySelector('.ic-f select, .ic-f input, .ic-f button'); if (f && ISO.open) f.focus(); return; }
    var hb = e.target.closest('[data-iso-hist]'); if (hb) { openSheet('hist', hb.getAttribute('data-iso-hist')); return; }
    var b = e.target.closest('[data-blind]'); if (b) { isoStep('blind', b.getAttribute('data-blind'), null, b); return; }
    var u = e.target.closest('[data-blind-undo]');
    if (u) {
      var line = u.getAttribute('data-blind-undo'), by = $('iso-by').value.trim();
      if (!by) { flash('입력자 이름을 적는다 — 단계 입력 기록에 남는다', true); $('iso-by').focus(); return; }
      ask({title: '맹판 설치 취소(정정) — ' + line, note: '설치 완료 기록을 지우지 않고, 미설치로 되돌리는 정정 기록을 덧붙인다. 해제 조건 ②가 다시 실패로 바뀐다. 입력자 ' + by + '와 사유가 남는다.',
        fields: [{k: 'note', label: '정정 사유 (필수)', req: true, area: true}]}, function (v) { return isoStep('blind_undo', line, null, null, v.note); });
      return;
    }
    if (e.target.closest('#iso-gas-fail')) { isoStep('gas', $('iso-pt').value, '측정불가', e.target.closest('#iso-gas-fail')); return; }
    if (e.target.closest('#iso-gas')) { isoStep('gas', $('iso-pt').value, $('iso-lel').value, e.target.closest('#iso-gas')); return; }
    var pb = e.target.closest('[data-purge]'); if (pb) { isoStep(pb.getAttribute('data-purge'), null, null, pb); return; }
    if (e.target.closest('#iso-purge-go')) { isoStep('purge', null, $('iso-purge').value, e.target.closest('#iso-purge-go')); return; }
  });
  $('iso-cards').addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    if (e.target.id === 'iso-lel') $('iso-gas').click(); else if (e.target.id === 'iso-purge') $('iso-purge-go').click();
  });
  document.querySelector('.screen[data-screen="iso"]').addEventListener('click', function (e) {
    var pk = e.target.closest('[data-isopick]'); if (pk) { ISO.cur = pk.getAttribute('data-isopick'); ISO.open = null; renderIsoPicks(); return; }
    var lz = e.target.closest('[data-iso-live]'); if (lz) { curZone = lz.getAttribute('data-iso-live'); curCam = 0; zonePickedAt = Date.now(); show('live'); return; }
    if (e.target.closest('#iso-redo') && ISO.detail) { openReg(ISO.detail.ptw.zone, ISO.detail.ptw.work, ISO.detail.ptw); return; }
    if (e.target.closest('#iso-pr-open')) {
      var open = $('iso-pr').hidden; $('iso-pr').hidden = !open;
      var b = $('iso-pr-open'); b.setAttribute('aria-expanded', open ? 'true' : 'false'); b.textContent = open ? '운영 원칙 접기 ↑' : '운영 원칙 보기 →';
    }
  });
  $('iso-picks').addEventListener('keydown', function (e) {        // 라디오 묶음 — 화살표로 옮긴다
    if (['ArrowRight', 'ArrowLeft', 'ArrowDown', 'ArrowUp'].indexOf(e.key) < 0) return;
    var bs = Array.prototype.slice.call(this.querySelectorAll('[data-isopick]')), i = bs.indexOf(document.activeElement); if (i < 0) return;
    e.preventDefault(); var nx = bs[(i + (e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : bs.length - 1)) % bs.length];
    ISO.cur = nx.getAttribute('data-isopick'); renderIsoPicks(); var f = $('iso-picks').querySelector('[data-isopick="' + CSS.escape(ISO.cur) + '"]'); if (f) f.focus();
  });
  $('iso-all').addEventListener('click', function () { openSheet('ptws'); });
  $('iso-hist-all').addEventListener('click', function () { openSheet('hist', 'all'); });
  $('iso-hist-more').addEventListener('click', function () { openSheet('hist', 'all'); });
  $('iso-basis').addEventListener('click', function () { openSheet('basis'); });
  $('iso-dg-big').addEventListener('click', function () { if (ISO.detail && ISO.detail.has_pid) openSheet('dg'); });
  $('iso-sheet-x').addEventListener('click', closeSheet);
  $('iso-sheet-back').addEventListener('click', closeSheet);
  $('iso-sheet-b').addEventListener('click', function (e) {
    var f = e.target.closest('[data-hf]'); if (f) { ISO.histF = f.getAttribute('data-hf'); renderSheet(); return; }
    var pf = e.target.closest('[data-pf]'); if (pf) { ISO.ptwF = pf.getAttribute('data-pf'); renderSheet(); return; }
    var pk = e.target.closest('[data-isopick]'); if (pk) { ISO.cur = pk.getAttribute('data-isopick'); ISO.open = null; closeSheet(); renderIsoPicks(); }
  });

  /* 작업허가서 등록 — 화면 아래 접는 칸 (대조와 등록은 서버에서) */
  function regZoneNote() {
    var zz = META.zones.filter(function (x) { return x.id === $('reg-zone').value; })[0];
    $('reg-pid').textContent = zz && zz.piping ? '이 구역 계통도: ' + zz.equip + '에 물린 배관 ' + zz.lines.length + '건 (' + zz.lines.join(' · ') + ')' : '이 구역에는 배관 계통도가 없다.';
  }
  var REG_DOCX = null;   // 작업허가서 파일에서 읽은 것 (10/13) — 등록할 때 허가 번호 · 퍼지 · 가스 측정 · 화재감시자 · 서명을 같이 넘긴다
  function regRead() {
    return {zone: $('reg-zone').value, work_type: $('reg-mode').value, start: $('reg-start').value, end: $('reg-end').value,
      work: $('reg-title').value.trim(), supervisor: $('reg-sup').value.trim(), workers: $('reg-n').value ? +$('reg-n').value : null,
      csv: $('reg-csv').value, no_list: $('reg-nolist').checked,
      ptw_id: REG_DOCX ? REG_DOCX.ptw_id : null, extra: REG_DOCX ? REG_DOCX.extra : null, docx_token: REG_DOCX ? REG_DOCX.token : null};
  }
  function regDocxShow(d) {
    $('reg-docx').innerHTML = '<div class="reg-read"><p class="note"><b>' + esc(d.filename) + '</b> — ' +
      (d.ptw_id ? '허가 번호 <b class="mono">' + esc(d.ptw_id) + '</b> 로 등록된다' : '허가 번호가 없어 새 번호로 등록된다') + ' · 허가서 유형 ' + esc(d.ptw_type) + '</p>' +
      '<dl>' + d.read.map(function (x) { return '<div><dt>' + esc(x.k) + '</dt><dd>' + esc(x.v) + '</dd></div>'; }).join('') + '</dl>' +
      (d.warnings.length ? '<div class="bar warn"><span><b>확인 필요 ' + d.warnings.length + '건</b> — 허가서를 보완하거나 아래 칸에서 고친 뒤 등록한다</span></div><ul class="reg-warn">' +
        d.warnings.map(function (w) { return '<li>' + esc(w) + '</li>'; }).join('') + '</ul>'
        : '<div class="bar ok"><span>빈칸 · 누락 없음</span></div>') + '</div>';
  }
  function regPreview() {
    var r = regRead(), err = $('reg-err');
    if (!r.work) { err.textContent = '작업 내용을 적는다.'; err.hidden = false; $('reg-title').focus(); return Promise.resolve(null); }
    return api('/api/iso/check', {zone: r.zone, csv: r.csv, no_list: r.no_list}).then(function (c) {
      err.hidden = true;
      if (c.no_list) { $('reg-preview').innerHTML = '<div class="bar warn"><span>목록 없이 등록된다 — 정비 허가서면 작업 전 게이트에서 막힌다 (화기 허가서는 격리 비대상)</span></div>'; return r; }
      var miss = c.lines.filter(function (l) { return !l.in_list; });
      $('reg-preview').innerHTML = '<div class="tbl"><table class="t"><thead><tr><th>line_id</th><th>배관</th><th>대조</th></tr></thead><tbody>' +
        c.lines.map(function (l) { return '<tr class="' + (l.in_list ? '' : 'hit') + '"><td class="t">' + esc(l.line_id) + '</td><td>' + esc(l.name) + '</td><td>' + (l.in_list ? (l.blind === 'done' ? '<span class="lv ok">목록에 있음 · 맹판 O</span>' : '<span class="lv note">목록에 있음 · 맹판 대기</span>') : '<span class="lv warn lv3">목록에 없음</span>') + '</td></tr>'; }).join('') +
        c.extra.map(function (x) { return '<tr class="gate"><td class="t" colspan="2">' + esc(x) + '</td><td><span class="lv warn">계통도에 없음 — 확인 필요</span></td></tr>'; }).join('') +
        '</tbody></table></div><div class="bar ' + (miss.length ? 'warn' : 'ok') + '"><span>계통도 ' + c.lines.length + '건 · 목록에 없는 연결 ' + miss.length + '건' + (c.extra.length ? ' · 계통도에 없는 줄 ' + c.extra.length + '건' : '') + '</span></div>';
      return r;
    }).catch(function (e) { err.textContent = e.message; err.hidden = false; $('reg-preview').innerHTML = ''; return null; });
  }
  function setReg(open) {
    $('reg').hidden = !open;
    var t = $('reg-toggle'); t.setAttribute('aria-expanded', open ? 'true' : 'false'); t.textContent = open ? '접기 ↑' : '펼치기 ↓';
    store('iso-reg-open', open ? '1' : '0');
  }
  function showPaste(on) { $('reg-csv-f').hidden = !on; $('reg-paste').setAttribute('aria-expanded', on ? 'true' : 'false'); $('reg-paste').textContent = on ? '붙여넣기 닫기' : '붙여넣기'; }
  function regReset(zone, work) {
    var zs = zone || (META.zones.filter(function (x) { return x.id === curZone && x.piping; })[0] || {}).id || META.focus_zone;
    $('reg-zone').value = zs; regZoneNote();
    var day = (STATUS ? STATUS.now : new Date().toISOString()).slice(0, 10);
    $('reg-start').value = day + 'T13:00'; $('reg-end').value = day + 'T17:00';
    $('reg-title').value = work || ''; $('reg-csv').value = ''; $('reg-file').value = ''; $('reg-nolist').checked = false;
    $('reg-sup').value = ''; $('reg-n').value = '';
    $('reg-preview').innerHTML = ''; $('reg-err').hidden = true; showPaste(false);
    REG_DOCX = null; $('reg-docx').innerHTML = ''; $('reg-docx-file').value = '';
  }
  // 목록 보완 — 다시 등록: 고른 허가서의 값으로 채워 연다 (새 번호로 등록된다)
  function openReg(zone, work, ptw) {
    regReset(zone, work);
    if (ptw) {
      if (ptw.start) $('reg-start').value = ptw.start.slice(0, 16);
      if (ptw.end) $('reg-end').value = ptw.end.slice(0, 16);
      if (ptw.supervisor) $('reg-sup').value = ptw.supervisor;
      if (ptw.workers) $('reg-n').value = ptw.workers;
      if (ptw.work_type && META.work_types.indexOf(ptw.work_type) >= 0) $('reg-mode').value = ptw.work_type;
      $('reg-preview').innerHTML = '<p class="note">' + esc(ptw.ptw_id) + '의 값으로 채웠다. 격리 목록을 보완해 등록하면 새 번호로 등록된다.</p>';
    }
    setReg(true);
    $('reg-panel').scrollIntoView({behavior: 'smooth', block: 'start'});
    $('reg-title').focus({preventScroll: true});
  }
  $('reg-toggle').addEventListener('click', function () { setReg($('reg').hidden); });
  $('reg-paste').addEventListener('click', function () { showPaste($('reg-csv-f').hidden); if (!$('reg-csv-f').hidden) $('reg-csv').focus(); });
  $('reg-zone').addEventListener('change', function () { regZoneNote(); if ($('reg-preview').querySelector('table')) regPreview(); });
  $('reg-sample').addEventListener('click', function () {
    api('/api/iso-sample?zone=' + encodeURIComponent($('reg-zone').value)).then(function (d) {
      if (!d.csv) { $('reg-err').textContent = '이 구역에는 예시가 없다 (배관 계통도 없음).'; $('reg-err').hidden = false; return; }
      $('reg-csv').value = d.csv; $('reg-nolist').checked = false; showPaste(true);
      if (!$('reg-title').value.trim()) $('reg-title').value = d.work;
      if (!$('reg-sup').value) $('reg-sup').value = d.supervisor;
      if (!$('reg-n').value) $('reg-n').value = d.workers;
      regPreview();
    }).catch(fail);
  });
  $('reg-file').addEventListener('change', function () {
    var f = this.files && this.files[0]; if (!f) return;
    var fd = new FormData(); fd.append('file', f);
    api('/api/docs/upload-csv', fd).then(function (d) { $('reg-csv').value = d.text; $('reg-nolist').checked = false; showPaste(true); regPreview(); })
      .catch(function (e) { $('reg-err').textContent = e.message; $('reg-err').hidden = false; });
  });
  $('reg-docx-file').addEventListener('change', function () {
    var f = this.files && this.files[0]; if (!f) return;
    var fd = new FormData(); fd.append('file', f);
    $('reg-err').hidden = true;
    api('/api/iso/ptw-docx', fd).then(function (d) {
      var x = d.fields;
      if (x.zone && META.zones.some(function (z) { return z.id === x.zone; })) { $('reg-zone').value = x.zone; regZoneNote(); }
      if (x.work_type && META.work_types.indexOf(x.work_type) >= 0) $('reg-mode').value = x.work_type;
      if (x.start) $('reg-start').value = x.start;
      if (x.end) $('reg-end').value = x.end;
      $('reg-title').value = x.work || ''; $('reg-sup').value = x.supervisor || ''; $('reg-n').value = x.workers || '';
      $('reg-csv').value = d.csv; $('reg-nolist').checked = d.no_list; $('reg-file').value = ''; showPaste(!!d.csv);
      REG_DOCX = {ptw_id: d.ptw_id, extra: d.extra, token: d.token};
      regDocxShow(d);
      if (x.work) regPreview();
      flash('작업허가서 파일을 읽었다 — 확인 필요 ' + d.warnings.length + '건');
    }).catch(function (e) { $('reg-err').textContent = e.message; $('reg-err').hidden = false; });
  });
  $('reg-check').addEventListener('click', regPreview);
  $('reg-save').addEventListener('click', function () {
    var btn = this;
    regPreview().then(function (r) {
      if (!r) return;
      return busy(btn, api('/api/iso/register', r)).then(function (d) {
        regReset(r.zone);
        $('reg-toast').textContent = d.msg; $('reg-toast').hidden = false;
        loadIso(d.ptw_id); tickStatus();
        document.querySelector('.screen[data-screen="iso"]').scrollIntoView({behavior: 'smooth', block: 'start'});
      });
    }).catch(function (e) { $('reg-err').textContent = e.message; $('reg-err').hidden = false; });
  });

  /* ---------- 3. 이벤트 로그 (10/6 배치) ----------
     거르기는 서버(control/eventlog.py)가 한다 — '보이는 경보 이상 넘기기'가 같은 조건으로 넘겨야 화면과 넘긴 목록이 같다.
     조건을 바꾸면 '적용'(또는 검색창에서 Enter)을 눌러야 목록에 반영된다. 정렬 · 더 보기 · 고르기는 바로 바뀐다(목록이 달라지지 않는다).
     묶음(cat) — crit · warn · note(감지 단계) · gate(작업 전 차단) · acc(사고) · silent(무음 기록) · info(참고). */
  var MULTI = ['kinds', 'levels', 'types', 'rulesets', 'flags'];
  var FACET_T = {kinds: '종류', levels: '단계', types: '위반 유형', rulesets: '규칙셋', flags: '표시'};
  var KIND_SEL = {'': [], detect: ['stage', 'check'], gate: ['gate'], accident: ['accident'], info: ['info']};
  var GRADE_T = {note: '주의 이상', warn: '경보 이상', crit: '최고 경보', silent: '무음 기록만'};
  var CAT_ICO = {crit: 'crit', warn: 'warn', note: 'note', gate: 'gate', acc: 'acc', silent: 'silent', info: 'info'};
  var PAGE = 50;
  function defF() { return {q: '', mode: '전체', zone: '전체', period: '14', grade: '', cat: '', kinds: [], levels: [], types: [], rulesets: [], flags: [], src: ''}; }
  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  var applied = defF(), draft = defF(), selEv = null, LOG = null, logShown = PAGE, logSort = 'new', clipOpen = false;
  function normF(f) { var o = clone(f); o.q = String(o.q || '').trim().replace(/\s+/g, ' '); MULTI.forEach(function (k) { o[k] = (o[k] || []).slice().sort(); }); return o; }
  function same(a, b) { return JSON.stringify(normF(a)) === JSON.stringify(normF(b)); }
  function periodText(p) { return {today: '오늘', '7': '최근 7일', '14': '최근 14일', '90': '최근 90일', all: '전체 기간'}[p]; }
  function kindSel(f) { var k = (f.kinds || []).slice().sort().join(','); return Object.keys(KIND_SEL).filter(function (x) { return KIND_SEL[x].slice().sort().join(',') === k; })[0] || ''; }
  function rxq(t) { return t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  function hl(text, toks) {               // 찾은 낱말 표시 — 글자는 먼저 이스케이프하고, 태그 안은 건드리지 않는다
    var out = esc(text);
    (toks || []).forEach(function (t) { if (t) out = out.replace(new RegExp('(' + rxq(esc(t)) + ')(?![^<]*>)', 'gi'), '<mark class="hl">$1</mark>'); });
    return out;
  }
  function facetLabel(k, v) { var x = ((LOG && LOG.facets[k]) || []).filter(function (y) { return y.v === v; })[0]; return x ? x.label : v; }
  function catLabel(v) { var x = ((LOG && LOG.cats) || []).filter(function (y) { return y.v === v; })[0]; return x ? x.label : v; }
  function appliedText() {
    var parts = [];
    if (normF(applied).q) parts.push('검색 “' + normF(applied).q + '”');
    parts.push(periodText(applied.period));
    if (applied.zone !== '전체') parts.push('구역 ' + applied.zone);
    if (applied.mode !== '전체') parts.push('모드 ' + applied.mode);
    if (applied.grade) parts.push('등급 ' + GRADE_T[applied.grade]);
    if (applied.kinds.length) parts.push('종류 ' + $('f-kind').querySelector('option[value="' + kindSel(applied) + '"]').textContent);
    if (applied.cat) parts.push(catLabel(applied.cat) + '만');
    ['types', 'rulesets', 'flags'].forEach(function (k) { if (applied[k].length) parts.push(FACET_T[k] + ' ' + applied[k].map(function (v) { return facetLabel(k, v); }).join('·')); });
    if (applied.src) parts.push('출처 ' + facetLabel('sources', applied.src));
    return '적용 중: ' + parts.join(' · ');
  }
  function renderChips() {
    if (!LOG) return;
    ['types', 'rulesets', 'flags'].forEach(function (k) {
      $('f-' + k).innerHTML = (LOG.facets[k] || []).map(function (x) {
        var on = draft[k].indexOf(x.v) >= 0;
        return '<button type="button" class="fchip' + (on ? ' on' : '') + '" aria-pressed="' + on + '" data-fk="' + k + '" data-fv="' + esc(x.v) + '">' + esc(x.label) + ' <small>' + x.n + '</small></button>';
      }).join('') || '<span class="note">기록 없음</span>';
    });
    var src = LOG.facets.sources || [];
    $('f-src').innerHTML = opt('', '전체') + src.map(function (x) { return opt(x.v, x.label + ' (' + x.n + ')', x.v === draft.src); }).join('');
    $('f-src').value = draft.src;
    // 건수 칩 — 묶음을 고르기 전 기준 건수. 누르면 그 묶음만(다시 누르면 해제) — 적용을 눌러야 반영
    $('f-cats').innerHTML = (LOG.cats || []).map(function (x) {
      var on = draft.cat === x.v;
      return '<button type="button" class="lg-cat c-' + x.v + (on ? ' on' : '') + '" aria-pressed="' + on + '" data-cat="' + x.v + '">' + ico(CAT_ICO[x.v]) + esc(x.label) + ' <b class="mono">' + x.n + '</b></button>';
    }).join('') || '<span class="note">해당 기록 없음</span>';
    var nd = ['types', 'rulesets', 'flags'].reduce(function (n, k) { return n + draft[k].length; }, 0);
    $('f-more-n').textContent = nd ? '· 상세 조건 ' + nd + '개' : '';
  }
  function updatePending() { $('f-pending').hidden = same(applied, draft); }
  function syncInputs() {
    $('f-q').value = draft.q; $('f-zone').value = draft.zone; $('f-period').value = draft.period;
    $('f-grade').value = draft.grade; $('f-kind').value = kindSel(draft);
    if ($('f-mode').options.length) $('f-mode').value = draft.mode;
  }
  function loadLog(o) {
    if (o && o.q) { draft = defF(); draft.q = o.q; draft.period = 'all'; applied = clone(draft); syncInputs(); }  // 다른 화면에서 ID 로 찾아 들어올 때
    if (o && o.f) { draft = Object.assign(defF(), o.f); applied = clone(draft); syncInputs(); }      // 통계 화면에서 구역 · 기간 · 등급으로 거른 채 들어올 때
    return api('/api/log', Object.assign({}, applied, {sort: logSort})).then(function (d) {
      LOG = d; logShown = PAGE;
      $('f-mode').innerHTML = ['전체'].concat(d.modes).map(function (m) { return opt(m, m, m === draft.mode); }).join('');
      $('f-mode').value = draft.mode;
      if (o && o.q && d.rows.length) selEv = d.rows[0].id;
      renderChips(); renderLog();
    }).catch(fail);
  }
  function applyLog() { draft.q = normF(draft).q; applied = clone(draft); loadLog(); }
  // 종류 표시 — 작업 전 차단 · 사고는 단계 칩이 이미 같은 말이라 붙이지 않는다
  function badge(e) { return e.kind === 'gate' || e.kind === 'accident' ? '' : '<span class="ev-badge">' + esc(e.badge) + '</span>'; }
  function evRow(e, toks) {
    var flags = (e.adj ? tag('강화 중', 'adj') : '') + (e.fp ? '<span class="lv mute">오탐 표시됨</span>' : '');
    return '<div class="ev-row c-' + e.cat + (e.id === selEv ? ' sel' : '') + (e.cat === 'silent' ? ' shadow' : '') + '" data-ev="' + esc(e.id) + '" tabindex="0" role="button" aria-label="' + esc(e.id + ' ' + e.title) + '">' +
      '<span class="ev-ico">' + ico(CAT_ICO[e.cat]) + '</span>' +
      '<span class="ev-t mono">' + hl(e.date.slice(5), toks) + '<b>' + hl(e.ts.slice(11, 19), toks) + '</b></span>' +
      '<span class="ev-lv">' + kindTag(e) + '</span>' +
      '<span class="ev-main"><span class="ev-h"><span class="z" title="' + esc(e.zname || '') + '">' + hl(e.zone || '-', toks) + '</span><b>' + hl(e.title, toks) + '</b>' + badge(e) + '</span><small>' + hl(e.sub, toks) + '</small>' +
        (e.hit && e.hit.length ? '<span class="hitnote">' + esc(e.hit.join(' · ')) + '에서 일치</span>' : '') + '</span>' +
      '<span class="ev-rule"><small>' + hl(e.rs, toks) + '</small><small>' + hl(e.rule, toks) + '</small></span>' +
      '<span class="ev-flag">' + flags + '<small>' + esc(e.src_t) + (e.run_kind && e.run_kind !== '운영' ? ' · ' + esc(e.run_kind) : '') + '</small></span>' +
      '<span class="ev-go" aria-hidden="true">›</span></div>';
  }
  function renderLog() {
    var rows = LOG.rows, toks = LOG.tokens || [];
    $('log-count').textContent = '총 ' + LOG.total + '건 · 현재 필터 ' + LOG.n + '건';
    $('f-applied').textContent = appliedText();
    updatePending();
    if (!rows.some(function (e) { return e.id === selEv; })) selEv = rows.length ? rows[0].id : null;
    var idx = rows.findIndex(function (e) { return e.id === selEv; });
    if (idx >= logShown) logShown = Math.ceil((idx + 1) / PAGE) * PAGE;
    var extra = LOG.extra ? '<div class="extra-note note"><span>' + periodText(applied.period) + ' 밖에도 맞는 기록이 ' + LOG.extra + '건 더 있다.</span><button class="go" type="button" id="f-all-period">전체 기간으로 보기 →</button></div>' : '';
    var more = rows.length > logShown ? '<button class="btn ev-more" type="button" id="ev-more">더 보기 (' + Math.min(PAGE, rows.length - logShown) + '건 · 남은 ' + (rows.length - logShown) + '건)</button>' : '';
    $('log-table').innerHTML = (rows.length ? rows.slice(0, logShown).map(function (e) { return evRow(e, toks); }).join('') + more
      : '<p class="empty">조건에 맞는 이벤트가 없다.</p>') + extra;
    renderLogDetail();
  }
  /* 줄을 고르면 목록은 그대로 두고(스크롤 · 위치 유지) 고른 표시와 오른쪽 상세만 바꾼다 */
  function selectEv(id) {
    if (selEv !== id) clipOpen = false;
    selEv = id;
    document.querySelectorAll('#log-table .ev-row[data-ev]').forEach(function (r) { r.classList.toggle('sel', r.getAttribute('data-ev') === id); });
    renderLogDetail();
  }
  function stepEv(d) {
    if (!LOG || !LOG.rows.length) return;
    var i = LOG.rows.findIndex(function (e) { return e.id === selEv; }), j = Math.max(0, Math.min(LOG.rows.length - 1, i + d));
    if (j === i) return;
    if (j >= logShown) { logShown += PAGE; selEv = LOG.rows[j].id; clipOpen = false; renderLog(); }
    else selectEv(LOG.rows[j].id);
    var el = document.querySelector('#log-table .ev-row[data-ev="' + CSS.escape(LOG.rows[j].id) + '"]');
    if (el) { el.scrollIntoView({block: 'nearest'}); el.focus({preventScroll: true}); }
  }
  function axTone(t) { return t === 'danger' ? 'on' : t === 'warn' ? 'half' : t === 'ok' ? 'clr' : 'off'; }
  /* 탐지 신뢰도 칸 (10/8) — 근거 탐지의 모델 점수와 기준. 기준보다 0.1 이내로 높으면 '기준 근처'(오탐 의심) */
  function confCell(c) {
    if (!c || !c.rows.length) return '<span class="note">' + esc((c && c.note) || '-') + '</span>';
    return '<span class="cf-list">' + c.rows.map(function (r) {
      var near = r.min !== null && r.v < r.min + 0.1;
      return '<span class="cf' + (r.main ? ' cf-main' : '') + (near ? ' near' : '') + '" title="' + esc(r.what) + '">' + esc(r.label) + ' <b class="mono">' + r.v.toFixed(2) + '</b>' +
        (r.min !== null ? ' <small>기준 ' + r.min + (near ? ' · 기준 근처' : '') + '</small>' : ' <small>색 검출</small>') + '</span>';
    }).join('') + '</span>' + (c.det ? '<small class="note" style="display:block;margin-top:2px">이 기록은 ' + esc(c.det) + ' 탐지에 기댄다</small>' : '');
  }
  function renderLogDetail() {
    var i = LOG ? LOG.rows.findIndex(function (e) { return e.id === selEv; }) : -1;
    $('ld-prev').disabled = i <= 0; $('ld-next').disabled = !LOG || i < 0 || i >= LOG.rows.length - 1;
    if (!selEv) { $('log-detail').innerHTML = '<p class="empty">이벤트를 고르면 여기에 뜬다.</p>'; return; }
    var toks = (LOG && LOG.tokens) || [], want = selEv;
    api('/api/event/' + encodeURIComponent(selEv)).then(function (e) {
      if (want !== selEv) return;            // 그새 다른 줄을 골랐다
      var detect = e.kind === 'stage' || e.kind === 'check';
      var frameUrl = '/api/event/' + encodeURIComponent(e.id) + '/frame';
      var frame = e.has_frame ? '<img alt="' + esc(e.id) + ' 대표 프레임 — 관제 엔진이 분석 결과를 그려 넣은 화면" src="' + frameUrl + '"><a class="ld-zoom" href="' + frameUrl + '" target="_blank" rel="noopener" title="크게 보기" aria-label="대표 프레임 크게 보기">⤢</a>'
        : camSVG({poly: e.zone + ' 구역', active: e.cat !== 'silent', persons: 0, aria: e.id + ' 대표 프레임',
            note: detect ? '프레임 없음 — 영상이 없던 기록(신호 판정)이거나 무음 기록' : '프레임 없음 — 영상이 아니라 입력 · 신호로 남은 기록'});
      var axes = e.axes.length ? '<span class="ld-axes">' + e.axes.map(function (a) {
        var k = AXK[a.name] || ['axis', 'x1'];
        return '<span class="ld-ax ' + axTone(a.tone) + ' ' + k[1] + '">' + ico(k[0]) + esc(a.name) + ' <b>' + esc(axState(a)) + '</b></span>';
      }).join('') + '</span>' : '';
      var why = axes + '<span class="ld-why">' + hl(e.reason || (e.axes.length ? '' : '축 기록 없음 — 예시 기록이거나 영상 규칙 기록'), toks) + '</span>';
      var resp = (e.response ? hl(e.response, toks) + ' <span class="note">(판정표 권장 대응)</span>' : '<span class="note">-</span>') +
        (e.stop ? '<br>' + tag('작업중지 지시함 ' + e.stop.t, 'info') : '');
      var rows = [['판정 근거', why], ['걸린 규칙', hl(e.rule, toks)], ['대응', resp], ['규칙셋', hl(e.rs, toks) + (e.ruleset && e.ruleset !== e.rs ? ' <span class="note">' + hl(e.ruleset, toks) + '</span>' : '')],
        ['강화 중', e.adj ? hl(e.adj, toks) + ' ' + tag('강화 중', 'adj') + ' <button class="go" type="button" data-go="feedback">조정 보기 →</button>' : '<span class="note">아님 — 기본 강도</span>'],
        ['출처', hl(e.src_t + (e.src && e.src !== '샘플' ? ' (' + e.src + ')' : ''), toks)],
        ['구분', esc(e.run_kind || '미기록') + ' <span class="note">데이터 공간 · ' + esc(e.space_label || '') + '</span>'],
        ['영상 위치', e.video_t != null ? esc(e.video_t + '초') + (e.track_id != null ? ' <span class="note">추적 #' + esc(e.track_id) + '</span>' : '') : '<span class="note">해당 없음 — 영상이 아닌 입력</span>'],
        ['증빙 파일', (e.frame_file ? '<span class="mono note">' + esc(e.frame_file) + '</span>' : '<span class="note">프레임 없음</span>') + (e.clip_file ? '<br><span class="mono note">' + esc(e.clip_file) + '</span>' : '')],
        ['탐지 신뢰도', confCell(e.conf)],
        ['오탐 표시', e.fp ? hl((e.fp_by || '예') + (e.fp_cat ? ' · ' + e.fp_cat : '') + (e.fp_note ? ' — ' + e.fp_note : ''), toks) : '<span class="note">없음</span>'],
        ['이벤트 ID', '<span class="mono">' + hl(e.id, toks) + '</span>']];
      var clip = e.has_clip ? '<div class="ld-clip"><span class="k">' + ico('doc') + '클립</span><span class="note">' + esc(e.clip_window) + '</span></div>' +
          (clipOpen ? '<div class="frame" style="margin-top:6px"><video controls autoplay preload="metadata" src="/api/event/' + encodeURIComponent(e.id) + '/clip"></video></div>' : '')
        : '<div class="ld-clip"><span class="k">' + ico('doc') + '클립</span><span class="note">' + (e.clip_path ? '파일이 없다 — ' + esc(e.clip_path) : '클립 없음') + '</span></div>';
      $('log-detail').innerHTML =
        '<div class="ld-frame"><span class="k">대표 프레임</span><div class="frame">' + frame + '</div></div>' +
        '<div class="ld-head c-' + e.cat + '"><span class="ld-hl">' + kindTag(e) + badge(e) + '</span>' +
          '<span class="ld-meta">' + z(e.zone) + ' ' + esc(e.zname) + ' · <span class="mono">' + esc(e.ts_full) + '</span></span>' +
          '<b class="ld-title">' + hl(e.title, toks) + '</b><small>' + hl(e.sub, toks) + '</small></div>' +
        '<table class="t ld-kv"><tbody>' + rows.map(function (r) { return '<tr><td class="d">' + r[0] + '</td><td>' + r[1] + '</td></tr>'; }).join('') + '</tbody></table>' +
        clip +
        '<div class="ld-act">' +
          (detect ? '<button class="btn" type="button" id="ld-fp">' + (e.fp ? '오탐 취소' : '오탐 표시') + '</button>' : '') +
          (e.has_clip ? '<button class="btn" type="button" id="ld-clip">' + (clipOpen ? '클립 닫기' : '▶ 클립 보기') + '</button>' : '') +
          '<button class="btn dark" type="button" id="ld-send">문서로 넘기기</button></div>' +
        '<p class="note" style="margin-top:6px">' + (!e.alerted && detect ? '모드가 꺼진 구간의 검출이라 경보 없이 남았다. 통계와 사고 경과에 쓰인다. ' : '') +
          '오탐 표시는 별도 기록으로 저장되며, 원본 관제 기록은 수정되지 않는다. 문서로 넘기면 안전 문서 › 관제 인계에서 시정지시서 등을 만든다.</p>';
      $('log-detail').setAttribute('data-fp', e.fp ? '1' : '');
    }).catch(fail);
  }
  $('log-detail').addEventListener('click', function (e) {
    if (e.target.closest('#ld-clip')) { clipOpen = !clipOpen; renderLogDetail(); return; }
    if (e.target.closest('#ld-send')) { busy(e.target, api('/api/log/handoff', {event_ids: [selEv], source: '이벤트 로그 · 한 건'})).then(function (d) { flash(d.handoff_id + ' — 넘김 · 관제 인계에서 문서를 만든다'); show('docs', {tab: 'handoff', hid: d.handoff_id}); }).catch(fail); return; }
    if (e.target.closest('#ld-fp')) {
      var undo = !!$('log-detail').getAttribute('data-fp');
      // 오탐 사유는 고정 목록에서 고른다 — 기타면 사유를 직접 적는다 (10/8). 히트맵 · 통계의 오탐 · 미탐에 사유별로 모인다
      var fields = undo ? [{k: 'by', label: '취소한 사람', req: true}]
        : [{k: 'by', label: '표시자', req: true},
           {k: 'cat', label: '오탐 사유', options: [{v: '', t: '고른다'}].concat(META.fp_reasons)},
           {k: 'reason', label: '기타 사유', area: true, req: true, ph: '무엇을 잘못 잡았는지 적는다', show: {k: 'cat', v: '기타'}}];
      ask({title: undo ? '오탐 취소 — ' + selEv : '오탐 표시 — ' + selEv, note: '표시자와 시각이 남는다. 위험성평가 집계 · 통계에서 ' + (undo ? '다시 들어간다.' : '빠지고, 오탐 · 미탐 통계에 사유별로 모인다.'),
        fields: fields}, function (v) {
        if (!undo && !v.cat) return Promise.reject(new Error('오탐 사유를 고른다'));
        return api('/api/log/fp', {event_id: selEv, by: v.by, cat: v.cat, reason: v.reason, undo: undo}).then(function (d) { flash(d.msg); loadLog(); if (curScreen === 'quality') loadQuality(); });
      });
    }
  });
  $('ld-prev').addEventListener('click', function () { stepEv(-1); });
  $('ld-next').addEventListener('click', function () { stepEv(1); });
  // ↑ ↓ — 이벤트 로그 화면에서 입력칸 밖일 때 이전 · 다음 기록
  document.addEventListener('keydown', function (e) {
    if (curScreen !== 'log' || (e.key !== 'ArrowUp' && e.key !== 'ArrowDown')) return;
    if (e.target.closest && e.target.closest('input, select, textarea, video, .modal, [role="dialog"]')) return;
    e.preventDefault(); stepEv(e.key === 'ArrowUp' ? -1 : 1);
  });
  $('log-send').addEventListener('click', function () {
    if (!same(applied, draft)) flash('바꾼 조건은 아직 적용 전이다 — 지금 목록에 보이는 조건(적용 중)으로 넘긴다');
    busy(this, api('/api/log/handoff', {filter: applied})).then(function (d) { flash(d.handoff_id + ' — 넘김'); show('docs', {tab: 'handoff', hid: d.handoff_id}); }).catch(fail);
  });
  $('log-table').addEventListener('click', function (e) {
    if (e.target.closest('#f-all-period')) { draft.period = 'all'; applied.period = 'all'; syncInputs(); loadLog(); return; }
    if (e.target.closest('#ev-more')) { logShown += PAGE; renderLog(); return; }
  });
  $('f-sort').addEventListener('change', function () { logSort = this.value; loadLog(); });
  $('f-q').addEventListener('input', function () { draft.q = this.value; updatePending(); });
  $('f-q').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); applyLog(); } });
  $('f-mode').addEventListener('change', function () { draft.mode = this.value; updatePending(); });
  $('f-zone').addEventListener('change', function () { draft.zone = this.value; updatePending(); });
  $('f-period').addEventListener('change', function () { draft.period = this.value; updatePending(); });
  $('f-grade').addEventListener('change', function () { draft.grade = this.value; updatePending(); });
  $('f-kind').addEventListener('change', function () { draft.kinds = KIND_SEL[this.value].slice(); updatePending(); });
  $('f-src').addEventListener('change', function () { draft.src = this.value; renderChips(); updatePending(); });
  document.querySelector('[data-screen="log"]').addEventListener('click', function (e) {
    var cat = e.target.closest('.lg-cat[data-cat]');
    if (cat) { var v = cat.getAttribute('data-cat'); draft.cat = draft.cat === v ? '' : v; renderChips(); updatePending(); return; }
    var c = e.target.closest('.fchip[data-fk]'); if (!c) return;
    var k = c.getAttribute('data-fk'), fv = c.getAttribute('data-fv'), i = draft[k].indexOf(fv);
    if (i >= 0) draft[k].splice(i, 1); else draft[k].push(fv);
    renderChips(); updatePending();
  });
  $('f-more').addEventListener('click', function () {
    var open = $('f-detail').hidden; $('f-detail').hidden = !open;
    this.setAttribute('aria-expanded', open ? 'true' : 'false'); this.textContent = open ? '상세 필터 ▴' : '상세 필터 ▾';
  });
  $('lg-pr-open').addEventListener('click', function () {
    var open = $('lg-pr').hidden; $('lg-pr').hidden = !open;
    this.setAttribute('aria-expanded', open ? 'true' : 'false'); this.textContent = open ? '운영 원칙 접기 ↑' : '이벤트 로그 운영 원칙 보기 →';
  });
  $('f-apply').addEventListener('click', applyLog);
  $('f-reset').addEventListener('click', function () {
    draft = defF(); applied = defF(); syncInputs(); loadLog();
  });

  /* ---------- 4. 재생 비교 ----------
     규칙셋 이름은 v 번호(기본 규칙 v1 · 개정 규칙 v2), 기대 결과 대조는 개정 규칙 기준.
     시스템 판정 = 둥근 칩(lv · 작업 전 차단 tag), 현장 결과 = 테두리만 있는 네모 태그(res). */
  var RP = {list: [], cur: null, d: null, cursor: null, timer: null, speed: 10, lastAt: null, at: null, send: null, more: false};
  function resTag(kind) {
    if (kind === 'acc') return '<span class="res acc"><b>결과</b>사고 발생</span>';
    if (kind === 'prevented' || kind === 'none') return '<span class="res safe"><b>결과</b>사고 없음</span>';
    return '';
  }
  function judgeChip(c) {
    if (!c || !c.kind) return '<span class="d">-</span>';
    if (c.kind === 'gate') return tag('작업 전 차단', 'gate');
    return lv(c.level);
  }
  function loadReplay(force) {
    return api('/api/replay' + (force ? '?force=1' : '')).then(function (d) {
      RP.list = d.scenarios;
      if (!RP.list.some(function (s) { return s.key === RP.cur; })) RP.cur = RP.list.length ? RP.list[0].key : null;
      renderScPicks();
      if (RP.cur) return loadSc();
    }).catch(fail);
  }
  function renderScPicks() {
    $('sc-picks').innerHTML = RP.list.map(function (s) {
      var good = s.ok === s.n;
      return '<button type="button" class="pick' + (s.key === RP.cur ? ' on' : '') + '" data-sc="' + esc(s.key) + '"><span class="top2"><b>' + esc(s.title) + '</b>' +
        '<span class="rp-n ' + (good ? 'ok' : 'bad') + '" title="개정 규칙 기준 기대 결과 일치">' + s.ok + ' / ' + s.n + ' ' + ico(good ? 'ok' : 'warn') + '</span></span>' +
        '<span class="top2"><span class="s">' + esc(s.summary || (s.zone + ' ' + s.zname)) + '</span>' + (s.example ? '<span class="lv mute" title="예시데이터_삭제가능 — 지워도 되는 예시 시나리오">예시</span>' : '') + '</span></button>';
    }).join('') || '<p class="empty">사업장 패키지에 시나리오가 없다.</p>';
  }
  function loadSc() {
    stopPlay();
    return api('/api/replay/' + encodeURIComponent(RP.cur)).then(function (d) {
      RP.d = d; RP.cursor = d.times.length ? mins(d.times[d.times.length - 1]) : 0; RP.at = null; RP.lastAt = null;
      if (!RP.send || !d.variants.some(function (v) { return v.name === RP.send; })) RP.send = d.variants.length ? d.variants[d.variants.length - 1].name : null;
      renderScStatic(); renderSc(); fetchAt();
    }).catch(fail);
  }
  function scLetter(d) { return String(d.title || '').split('·')[0].trim(); }
  // 커서와 상관없는 것 — 시나리오 정보 · 기대 결과 · 규칙셋 비교 카드 · 넘길 규칙셋
  function renderScStatic() {
    var d = RP.d;
    $('sc-info').innerHTML = '<table class="t rp-kv"><tbody>' +
      '<tr><td class="d">구역</td><td>' + z(d.zone) + ' ' + esc(d.zname) + ' · ' + esc(d.table) + ' 판정표</td></tr>' +
      '<tr><td class="d">목적</td><td>' + esc(d.purpose || '-') + '</td></tr>' +
      '<tr><td class="d">입력 문서</td><td>' + esc(d.docs.join(' / ')) + '</td></tr>' +
      '<tr><td class="d">기대 핵심</td><td>' + esc(d.key_expect || '-') + '</td></tr></tbody></table>';
    $('sc-more').innerHTML = '<p class="note"><b>근거</b> ' + esc(d.basis || '-') + '</p>' +
      d.variants.map(function (v) { return '<p class="note"><b>' + esc(v.label) + '</b> 개정안 ' + esc(v.changes.join(' ') || '없음') + ' · 기록 폴더 control/records/replay/' + esc(d.key) + '/' + esc(v.name.replace(/ /g, '')) + '</p>'; }).join('') +
      (d.example ? '<p class="note">예시 시나리오 — 예시데이터_삭제가능 폴더째 지워도 된다.</p>' : '');
    $('sc-more').hidden = !RP.more;
    var good = d.ok === d.n;
    $('sc-score').innerHTML = '<b class="' + (good ? 'ok' : 'bad') + '">' + d.ok + ' / ' + d.n + (good ? ' 일치' : ' 불일치') + '</b>';
    $('sc-expect-basis').textContent = d.expect_label + ' 기준 — 기대 결과는 개정된 규칙으로 대조한다';
    $('sc-expect').innerHTML = d.expect.length ? d.expect.map(function (x) {
      return '<div class="' + (x.ok ? '' : 'bad') + '"><b class="mk ' + (x.ok ? 'y' : 'x') + '">' + (x.ok ? '✓' : '✗') + '</b><span>' + esc(x.msg) + '</span></div>';
    }).join('') : '<p class="empty">이 시나리오에는 기대 결과가 없다.</p>';
    $('sc-title').textContent = '규칙셋 비교 · 시나리오 ' + scLetter(d);
    $('sc-sub').textContent = d.title;
    $('sc-cards').innerHTML = d.variants.map(function (v) {
      var top = v.top ? lv(v.top.level) + ' <span class="d">' + esc(v.top.t) + (v.top.row ? ' · ' + v.top.row + '줄' : '') + '</span>' : lv('정상');
      return '<div class="vcard rp-vcard"><div class="rp-vh">' + ico('doc') + '<b>' + esc(v.label) + '</b><span class="d">개정안 ' + esc(v.changes.join(' ') || '없음') + '</span></div>' +
        '<table class="t rp-kv"><tbody>' +
        '<tr><td class="d">작업 전 차단</td><td>' + (v.gate ? tag('작업 전 차단', 'gate') + ' <span class="d">' + esc(v.gate.t) + '</span>' : '<span class="d">없음</span>') + '</td></tr>' +
        '<tr><td class="d">최고 판정</td><td>' + top + '</td></tr>' +
        '<tr><td class="d">현장 결과</td><td>' + resTag(v.result.kind) + (v.result.t ? ' <span class="d">' + esc(v.result.t) + (v.result.kind === 'prevented' ? ' · 사전 중지 가정' : '') + '</span>' : '') + '</td></tr>' +
        '<tr><td class="d">결과 요약</td><td>' + esc(v.text) + '</td></tr></tbody></table></div>';
    }).join('');
    $('sc-send-pick').innerHTML = d.variants.map(function (v) {
      return '<label class="rp-radio' + (v.name === RP.send ? ' on' : '') + '"><input type="radio" name="sc-send" value="' + esc(v.name) + '"' + (v.name === RP.send ? ' checked' : '') + '> ' + esc(v.label) + '</label>';
    }).join('');
    // 플레이어 눈금 — 판정이 바뀐 시각만 이름을 단다
    var t0 = d.times.length ? mins(d.times[0]) : 0, t1 = d.times.length ? mins(d.times[d.times.length - 1]) : 1, n = 0;
    // 이름표 — 판정이 바뀐 시각에만. 처음 · 끝은 늘 달고, 나머지는 두 줄 중 자리가 나는 줄에(너무 가까우면 생략 — 점에 마우스를 올리면 보인다)
    var xs = d.rows.map(function (r) { return t1 > t0 ? (mins(r.t) - t0) / (t1 - t0) * 100 : 0; });
    var place = {}, used = {hi: [], lo: []}, last = d.rows.length - 1;
    function fits(row, x) { return used[row].every(function (u) { return Math.abs(u - x) >= 20; }); }
    function put(i) { var row = fits('hi', xs[i]) ? 'hi' : fits('lo', xs[i]) ? 'lo' : null; if (row) { used[row].push(xs[i]); place[i] = row; } }
    if (d.rows.length) { put(0); if (last > 0) put(last); }
    d.rows.forEach(function (r, i) { if (i > 0 && i < last && r.notes.length) put(i); });
    $('sc-marks').innerHTML = d.rows.map(function (r, i) {
      var row = place[i], x = xs[i];
      var lab = row ? '<span class="lb' + (row === 'lo' ? ' lo' : '') + '"><b>' + esc(r.t) + '</b>' + esc(r.label || '') + '</span>' : '';
      return '<span class="mk' + (row ? ' key' : '') + '" style="left:' + x.toFixed(2) + '%" title="' + esc(r.t + ' ' + r.what) + '"><i></i>' + lab + '</span>';
    }).join('');
  }
  function renderSc() {
    var d = RP.d; if (!d) return;
    var t0 = d.times.length ? mins(d.times[0]) : 0, t1 = d.times.length ? mins(d.times[d.times.length - 1]) : 1;
    $('sc-end').innerHTML = '<b>' + esc(hhmm(RP.cursor)) + '</b> / ' + esc(d.times[d.times.length - 1] || '');
    $('sc-track').style.width = (t1 > t0 ? (RP.cursor - t0) / (t1 - t0) * 100 : 100) + '%';
    var curT = hhmm(RP.cursor), lastPast = null;
    d.rows.forEach(function (r) { if (r.t <= curT) lastPast = r.t; });
    var head = '<th>시각</th><th>입력 / 사건</th><th>입력 출처</th>' + d.variants.map(function (v) { return '<th>' + esc(v.label) + '</th>'; }).join('') + '<th>비고</th>';
    $('sc-table').innerHTML = '<table class="t rp-table" style="min-width:' + (480 + d.variants.length * 110) + 'px"><thead><tr>' + head + '</tr></thead><tbody>' +
      d.rows.map(function (r) {
        var cells = r.cells.map(function (c) {
          return '<td><span class="rp-cell">' + judgeChip(c) + resTag(c.result) + '</span></td>';
        }).join('');
        var cls = r.t === lastPast ? 'sel' : '';
        return '<tr class="' + cls + '"' + (r.t > curT ? ' style="opacity:.35"' : '') + '><td class="t">' + r.t + '</td><td>' + esc(r.what) + '</td><td class="rp-src">' + esc(r.source) + '</td>' + cells +
          '<td class="rp-note">' + r.notes.map(function (x) { return '<span>' + esc(x) + '</span>'; }).join('') + '</td></tr>';
      }).join('') + '</tbody></table>';
    var at = {};
    if (RP.at) RP.at.states.forEach(function (s) { at[s.name] = s; });
    $('sc-now').innerHTML = '<div class="rp-nc"><span class="k">' + ico('wait') + '시나리오 시각</span><b class="mono">' + esc(curT) + '</b></div>' +
      d.variants.map(function (v) {
        var s = at[v.name];
        if (!s) return '<div class="rp-nc"><span class="k">' + esc(v.label) + '</span><span class="d">—</span></div>';
        return '<div class="rp-nc"><span class="k">' + esc(v.label) + '</span><span class="rp-cell">' + lv(s.level) + (s.row && s.level !== '정상' ? '<span class="d">' + s.row + '줄</span>' : '') + '</span>' +
          (s.gate ? '<span class="rp-cell">' + tag('작업 전 차단', 'gate') + '<span class="d">' + esc(s.gate.t) + '</span></span>' : '') +
          (s.result ? '<span class="rp-cell">' + resTag(s.result.kind) + '</span>' : '') + '</div>';
      }).join('');
    $('sc-play').textContent = RP.timer ? '⏸ 멈춤' : '▶ 재생';
  }
  function fetchAt() {
    var t = hhmm(RP.cursor);
    if (t === RP.lastAt) return;
    RP.lastAt = t;
    api('/api/replay/' + encodeURIComponent(RP.cur) + '/at?t=' + t).then(function (d) { if (d.t === hhmm(RP.cursor) || !RP.timer) { RP.at = d; renderSc(); } }).catch(function () {});
  }
  function stopPlay() { if (RP.timer) { clearInterval(RP.timer); RP.timer = null; } }
  $('sc-play').addEventListener('click', function () {
    if (!RP.d || !RP.d.times.length) return;
    if (RP.timer) { stopPlay(); renderSc(); return; }
    var t0 = mins(RP.d.times[0]), t1 = mins(RP.d.times[RP.d.times.length - 1]);
    if (RP.cursor >= t1) RP.cursor = t0;
    RP.timer = setInterval(function () {
      RP.cursor = Math.min(t1, RP.cursor + RP.speed * 0.25 / 60 * 6);   // 1× = 시연 시각 1분을 10초에 (60× = 1초에 6분)
      if (RP.cursor >= t1) stopPlay();
      renderSc(); fetchAt();
    }, 250);
    renderSc(); fetchAt();
  });
  $('sc-speed').addEventListener('click', function (e) {
    var b = e.target.closest('button'); if (!b) return;
    RP.speed = +b.getAttribute('data-v');
    this.querySelectorAll('button').forEach(function (x) { x.classList.toggle('on', x === b); });
  });
  $('sc-trackbar').addEventListener('click', function (e) {
    if (!RP.d || !RP.d.times.length) return;
    var r = this.querySelector('.track').getBoundingClientRect(), f = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    var t0 = mins(RP.d.times[0]), t1 = mins(RP.d.times[RP.d.times.length - 1]);
    RP.cursor = t0 + f * (t1 - t0); renderSc(); fetchAt();
  });
  $('sc-all').addEventListener('click', function () { busy(this, loadReplay(true)).then(function () { flash('전체 다시 돌렸다 — control/records/replay/'); }); });
  $('sc-import').addEventListener('click', function () { $('sc-zip').click(); });
  $('sc-zip').addEventListener('change', function () {
    var fs = this.files; if (!fs || !fs.length) return;
    var fd = new FormData();
    for (var i = 0; i < fs.length; i++) fd.append('files', fs[i]);
    busy($('sc-import'), api('/api/replay/import', fd)).then(function (d) { flash(d.msg); RP.cur = d.key; return loadReplay(); }).catch(fail).finally(function () { $('sc-zip').value = ''; });
  });
  $('sc-more-open').addEventListener('click', function () {
    RP.more = !RP.more; $('sc-more').hidden = !RP.more;
    this.setAttribute('aria-expanded', RP.more ? 'true' : 'false'); this.textContent = RP.more ? '시나리오 상세 접기 ↑' : '시나리오 상세 보기 →';
  });
  $('rp-pr-open').addEventListener('click', function () {
    var open = $('rp-pr').hidden; $('rp-pr').hidden = !open;
    this.setAttribute('aria-expanded', open ? 'true' : 'false'); this.textContent = open ? '운영 원칙 접기 ↑' : '운영 원칙 보기 →';
  });
  $('sc-send-pick').addEventListener('change', function (e) {
    if (e.target.name !== 'sc-send') return;
    RP.send = e.target.value;
    this.querySelectorAll('.rp-radio').forEach(function (l) { l.classList.toggle('on', l.querySelector('input').checked); });
  });
  $('sc-send').addEventListener('click', function () {
    if (!RP.cur || !RP.send) { flash('넘길 규칙셋을 고른다', true); return; }
    busy(this, api('/api/replay/' + encodeURIComponent(RP.cur) + '/handoff', {variant: RP.send})).then(function (d) {
      flash(d.handoff_id + ' — ' + d.mark); show('docs', {tab: 'handoff', hid: d.handoff_id});
    }).catch(fail);
  });

  /* ---------- 5. 피드백 · 조정 로그 ----------
     짧은 루프(자동 · 기한부 · 감시 강도 강화만) | 긴 루프(사람 확정 · 규칙 변경 다섯 단계) | 조정 로그(상태가 바뀔 때마다 한 줄).
     판단은 control/feedback.py · 위험성평가(docgen) — 여기는 모양만. */
  var FB = {d: null, rc: null, review: false, open: {}, logAll: false, lf: null};
  // 피드백 화면의 처리 상태 — 위험 단계 색(빨강 · 주황 · 앰버)은 쓰지 않는다. 자동 조정 = 청록, 사람 처리 대기 = 무채색 테두리, 반려 · 승격 = 진한 무채색
  var LOG_K = {applied: 'adj', scheduled: 'wait', pending: 'wait', approved: 'ok', expired: 'mute', reverted: 'mute', rejected: 'mute',
    promoted: 'ink', toggle: 'mute', signed: 'wait', confirmed: 'ok', reflected: 'ok', ra_rejected: 'ink', rule_rejected: 'ink', restored: 'mute'};
  var PH_K = {none: 'mute', draft: 'wait', worker: 'wait', rejected: 'ink', ra_rejected: 'ink', rejected_final: 'ink', confirmed: 'info', live: 'ok'};
  var ST_K = {done: 'ok', now: 'info', wait: 'mute', rej: 'ink'};
  function ymd(d) { return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); }
  function fbDefLF(now) {
    var t = new Date(now.slice(0, 10) + 'T00:00:00');
    return {from: ymd(new Date(t.getTime() - 13 * 86400000)), to: now.slice(0, 10), zone: '', loop: '', state: '', actor: '', q: ''};
  }
  function syncLF() { var f = FB.lf; $('fbl-from').value = f.from; $('fbl-to').value = f.to; $('fbl-zone').value = f.zone; $('fbl-loop').value = f.loop; $('fbl-state').value = f.state; $('fbl-actor').value = f.actor; $('fbl-q').value = f.q; }
  function loadFb() {
    return api('/api/feedback').then(function (d) {
      FB.d = d;
      if (!FB.lf) { FB.lf = fbDefLF(d.now); }
      renderFb();
    }).catch(fail);
  }
  function fbKpi(label, n, sub, cls, tail) {
    return '<div class="kpi' + (cls ? ' ' + cls : '') + '"><div class="kb"><span>' + esc(label) + '</span><b>' + n + '<small>건</small></b><small>' + sub + '</small></div>' + (tail || '') + '</div>';
  }
  function renderFb() {
    var d = FB.d, k = d.kpis, t = k.trend;
    $('fb-banner').textContent = '자동 조정은 감시 강도만 강화 방향으로 ' + d.expire_h + '시간 기한부로 올린다. 규칙 자체 변경은 긴 루프(위험성평가 확정)에서만 반영된다.';
    var mx = Math.max.apply(null, t.vals.concat([1]));
    var spark = '<div class="spark" role="img" aria-label="최근 14일 날짜별 조정 건수">' + t.vals.map(function (v, i) {
      return '<i' + (v ? '' : ' class="z"') + ' style="height:' + (v ? Math.max(14, v / mx * 100) : 6).toFixed(0) + '%" title="' + t.days[i] + ' · ' + v + '건"></i>'; }).join('') + '</div>';
    var delta = t.delta === 0 ? '전주와 같음 (' + t.this_week + '건)' : '전주 대비 <span class="' + (t.delta > 0 ? 'up' : 'dn') + '">' + (t.delta > 0 ? '+' : '') + t.delta + '건' +
      (t.pct != null ? ' (' + (t.delta > 0 ? '▲' : '▼') + Math.abs(t.pct) + '%)' : '') + '</span>';
    var waitN = k.pending + k.long_wait;
    $('fb-kpis').innerHTML =
      fbKpi('활성 자동 조정', k.active, '짧은 루프 · ' + d.expire_h + '시간 안에 만료' + (k.active_zones.length ? ' · ' + esc(k.active_zones.join(' · ')) : '')) +
      fbKpi('승인 대기', waitN, '짧은 루프(승인형) ' + k.pending + ' · 긴 루프 ' + k.long_wait + (k.long_wait ? ' (' + esc(k.long_wait_ids.join(' ')) + ')' : ''), waitN ? 'waitk' : '') +
      fbKpi('최근 14일 조정', k.n14, delta, '', spark) +
      '<div class="kpi"><div class="kb"><span>현재 운영 규칙셋</span><b class="txt">v' + esc(k.version) + '</b><small>' + (k.last_ts ? '최근 반영 ' + esc(k.last_ts) : '개정 없음 — 기본 규칙') +
        (k.ids.length ? ' · ' + esc(k.ids.join(' · ')) : '') + '</small></div><button class="btn sm" type="button" id="fb-rs-hist">변경 이력 보기</button></div>';
    // 짧은 루프
    $('fb-mode-badge').textContent = k.mode === 'auto' ? '자동' : '승인형';
    $('fb-mode-badge').className = 'lv ' + (k.mode === 'auto' ? 'adj' : 'wait');
    $('fb-mode-sub').textContent = d.expire_h + '시간 · 감시 강도 강화만 (규칙 자체 변경 없음)' + (k.mode === 'auto' ? '' : ' · 승인형 — 사람이 승인해야 적용');
    renderFbOpen();
    $('fb-crit-short').innerHTML = d.criteria_short.map(critLi).join('');
    var bmx = Math.max.apply(null, d.zone_counts.map(function (x) { return x.n; }).concat([d.promote.count]));
    $('fb-bars').innerHTML = d.zone_counts.length ? d.zone_counts.map(function (x) {
      return '<div class="hb" title="' + esc(x.zone + ' ' + x.name) + '"><span>' + esc(x.zone) + ' ' + esc(x.name) + '</span><div class="tr"><i class="' + (x.n >= d.promote.count ? 'k' : x.n >= d.promote.count - 1 ? 'k2' : 'p') + '" style="width:' + (x.n / bmx * 100).toFixed(0) + '%"></i></div><b>' + x.n + '</b></div>';
    }).join('') : '<p class="empty">최근 14일 조정 없음</p>';
    $('fb-bars-note').textContent = '진한 막대 = 같은 구역 ' + d.promote.within_days + '일 안에 ' + d.promote.count + '회 — 긴 루프로 승격하는 기준';
    $('fb-rules').innerHTML = [
      '<b>감시 강도만 강화 방향으로</b> 올린다 — 알림 단계 상향(구역당 최대 +' + d.max_up + ') · 꺼진 구역 규칙 임시 활성화 · 관리자 알림. 규칙 내용은 바꾸지 않는다.',
      '최대 <b>' + d.expire_h + '시간</b> 적용 후 자동 만료 — 연장하지 않는다.',
      '<b>만료되거나 사람이 되돌릴 때만</b> 원래 값으로 (되돌리기는 사유 필수).',
      '강화 기간에 잡힌 기록은 <b>기준선에서 뺀다</b> — 자기강화 폭주 방지.',
      '같은 구역 ' + d.promote.within_days + '일 안에 ' + d.promote.count + '회면 <b>긴 루프로 승격</b>한다.'
    ].map(function (x) { return '<li>' + x + '</li>'; }).join('');
    // 긴 루프
    var wait = d.rcs.filter(function (r) { return r.phase === 'worker' || r.phase === 'draft'; });
    if (!d.rcs.some(function (r) { return r.id === FB.rc; })) FB.rc = ((wait[0] || d.rcs[0]) || {}).id;
    $('rc-picks').innerHTML = d.rcs.map(function (r) {
      var dot = {worker: 'now', draft: 'now', confirmed: 'done', live: 'done', rejected: 'rej', ra_rejected: 'rej', rejected_final: 'rej'}[r.phase] || '';
      return '<button type="button" class="rc-chip' + (r.id === FB.rc ? ' on' : '') + '" data-rc="' + esc(r.id) + '" aria-pressed="' + (r.id === FB.rc) + '" title="' + esc(r.text) + '"><i class="' + dot + '"></i><b>' + esc(r.id) + '</b>' + esc(r.phase_text) + '</button>';
    }).join('') || '<p class="empty">규칙셋 변경안이 없다 — 사업장 패키지 rules.json › rule_changes</p>';
    renderRc();
    $('fb-prop-h').textContent = '긴 루프로 올라온 제안 ' + d.proposals.length + '건';
    $('fb-prop').innerHTML = d.proposals.length ? d.proposals.map(function (x) {
      return '<div class="pr">' + chip(x.kind, x.kind === '급감' ? 'mute' : x.kind === '승격' || x.kind === '위험도' ? 'ink' : 'wait') +
        '<div class="tx"><p>' + z(x.zone) + ' ' + esc(x.zname) + ' — ' + esc(x.text) + '</p>' + (x.ref ? '<small class="mono">' + esc(x.ref) + '</small>' : '') + '</div>' +
        '<span class="t">' + esc(x.ts.slice(5)) + '</span>' + (x.go ? '<button class="go" type="button" data-go="docs" data-tab="ra">위험성평가로 →</button>' : '<span class="note">점검 알림</span>') + '</div>';
    }).join('') : '<p class="empty">긴 루프로 올릴 제안이 없다.</p>';
    $('fb-crit-long').innerHTML = d.criteria_long.map(critLi).join('');
    renderFbLog();
    updLeft();
  }
  /* 짧은 루프 카드 — '적용 중'과 '승인 대기'를 두 묶음으로 나눈다 */
  function renderFbOpen() {
    var d = FB.d, live = d.open.filter(function (a) { return a.state !== 'pending'; }), pend = d.open.filter(function (a) { return a.state === 'pending'; });
    if (!d.open.length) { $('fb-open').innerHTML = '<p class="empty">걸려 있는 자동 조정이 없다. 이탈 조건에 걸리면 여기에 뜬다.</p>'; return; }
    function grp(cls, icon, title, sub, list, empty) {
      return '<div class="fb-grp ' + cls + '"><div class="fb-gh">' + ico(icon) + '<b>' + title + ' <span class="mono">' + list.length + '</span></b><span class="sub">' + sub + '</span></div>' +
        (list.length ? list.map(adjCard).join('') : '<p class="empty sm">' + empty + '</p>') + '</div>';
    }
    $('fb-open').innerHTML = grp('g-live', 'adj', '적용 중', '지금 감시를 강화하고 있다 · 만료되면 원래 값으로', live, '적용 중인 조정이 없다') +
      grp('g-wait', 'wait', '승인 대기', '사람이 승인해야 적용된다', pend, '승인을 기다리는 조정이 없다');
  }
  function critLi(c) { return '<li><b>' + esc(c[0]) + '</b><span>' + esc(c[1]) + '</span><em>' + esc(c[2]) + '</em></li>'; }
  function adjCard(a) {
    var pend = a.state === 'pending', open = !!FB.open[a.adj_id], id = esc(a.adj_id);
    var target = [a.zone_rule ? '구역 규칙 임시 활성화(무음 → 경보)' : '', a.notify ? '알림 대상에 관리자 추가' : ''].filter(Boolean).join(' · ');
    var btns = pend
      ? '<button class="btn sm dark" type="button" data-adj="approve" data-id="' + id + '">승인</button><button class="btn sm" type="button" data-adj="reject" data-id="' + id + '">거부</button>'
      : '<button class="btn sm" type="button" data-adj="revert" data-id="' + id + '">↶ 되돌리기</button><button class="btn sm" type="button" data-adj="promote" data-id="' + id + '">개정 제안으로 승격</button>';
    btns += '<button class="btn sm" type="button" data-adj-more="' + id + '" aria-expanded="' + open + '">' + (open ? '접기' : '상세 보기') + '</button>';
    var more = open ? '<div class="more">' +
      '<p><b>근거 이벤트</b> ' + (a.evidence.length ? '<span class="evlinks">' + a.evidence.map(function (x) { return '<button class="go" type="button" data-go="log" data-q="' + esc(x) + '">' + esc(x) + '</button>'; }).join('') + '</span>' : '—') + '</p>' +
      '<p><b>처리 이력</b></p><ol class="hist">' + a.history.map(function (h) { return '<li><span class="mono">' + esc(h.ts) + '</span> · ' + esc(h.state) + ' · ' + esc(h.actor) + (h.note ? ' · ' + esc(h.note) : '') + '</li>'; }).join('') + '</ol>' +
      '<p class="note mono">' + id + ' · ' + (a.feedback_mode === 'approval' ? '승인형' : '자동') + ' 방식으로 생성 · ' + esc(a.mode) + ' · ' + esc(a.violation_type) + (a.sample ? ' · 예시 데이터' : '') + '</p></div>' : '';
    return '<div class="acard' + (pend ? ' pending' : '') + (a.severe ? ' severe' : '') + '">' +
      '<div class="hd"><b>' + z(a.zone) + ' ' + esc(a.zname) + '</b><span class="btnrow" style="gap:6px">' + (a.severe ? chip('중대성 4', 'ink') : '') + (pend ? tag(a.state_label, 'wait') : a.state_key === 'applied' ? tag(a.state_label, 'adj') : chip(a.state_label, 'mute')) + '</span></div>' +
      '<dl><dt>조정 대상</dt><dd>감시 강도' + (target ? ' — ' + esc(target) : '') + '</dd>' +
      '<dt>알림 단계</dt><dd><span class="lvchg" title="1 = 현장 · 2 = 현장 + 관리자">' + chip('단계 ' + a.level_before, 'mute') + '→' + chip('단계 ' + a.level_after, 'adj') + '</span></dd>' +
      (pend ? '<dt>시작</dt><dd>승인하면 그때부터 ' + FB.d.expire_h + '시간</dd>'
            : '<dt>시작</dt><dd class="mono">' + esc(a.start) + '</dd><dt>만료 예정</dt><dd><span class="mono">' + esc(a.expires_at.replace('T', ' ')) + '</span><span class="left" data-exp="' + esc(a.expires_at) + '"></span></dd>') +
      '<dt>조정 사유</dt><dd>' + esc(a.reason) + '</dd></dl>' +
      '<div class="btnrow">' + btns + '</div>' + more + '</div>';
  }
  function updLeft() {
    var now = new Date((STATUS && STATUS.now) || (FB.d && FB.d.now));
    document.querySelectorAll('#fb-open [data-exp]').forEach(function (el) {
      var ms = new Date(el.getAttribute('data-exp')) - now;
      if (ms <= 0) { el.textContent = '(만료 — 정리 전)'; el.classList.add('soon'); return; }
      var s = Math.floor(ms / 1000), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
      el.textContent = '(남은 시간 ' + h + ':' + ('0' + m).slice(-2) + ':' + ('0' + x).slice(-2) + ')';
      el.classList.toggle('soon', ms < 6 * 3600 * 1000);
    });
  }
  function curRc() { return FB.d.rcs.filter(function (x) { return x.id === FB.rc; })[0]; }
  function renderRc() {
    var r = curRc();
    if (!r) { $('rc-steps').innerHTML = ''; $('rc-detail').innerHTML = '<p class="empty">변경안을 고른다.</p>'; return; }
    $('rc-steps').innerHTML = r.steps.map(function (s, i) {
      return '<li class="' + s.state + '"><span class="n">' + (s.state === 'done' ? '✓' : s.state === 'rej' ? '✕' : i + 1) + '</span><div class="tx"><div class="t1"><b>' + esc(s.name) + '</b>' + chip(s.label, ST_K[s.state]) + '</div><small>' + esc(s.sub) + '</small></div></li>';
    }).join('');
    var ev = r.evidence.length ? r.evidence.length + '건 <span class="evlinks">' + r.evidence.map(function (x) { return '<button class="go" type="button" data-go="log" data-q="' + esc(x) + '">' + esc(x) + '</button>'; }).join('') + '</span>' : '—';
    if (r.accidents.length) ev += ' · 사고 ' + esc(r.accidents.join(', '));
    var chg = function (k, cls) { return r.change.map(function (c) { return '<span class="p">' + esc(c.path) + '</span><code class="' + cls + '">' + esc(c[k]) + '</code>'; }).join(''); };
    var rejTitle = r.can_reject ? '' : r.phase === 'none' || r.phase === 'draft' ? '관리자 서명 뒤 · 근로자 확인 전에만 반려한다' : r.phase === 'confirmed' || r.phase === 'live' ? '확정된 변경은 새 위험성평가로만 되돌린다' : '이미 반려됐다';
    var dl = '<dl><dt>변경안</dt><dd><b class="mono">' + esc(r.id) + '</b> ' + esc(r.text) + '</dd>' +
      '<dt>구역</dt><dd>' + (r.zones.length ? r.zones.map(function (x) { return z(x.id) + ' ' + esc(x.name); }).join(' · ') : '—') + '</dd>' +
      '<dt>위험성평가</dt><dd>' + (r.ra_id ? '<span class="mono">' + esc(r.ra_id) + '</span> · ' + esc(r.ra_kind) + ' · ' + esc(r.ra_state) : r.phase === 'draft' ? '초안 (서명 전)' : '— 연결 전') + '</dd>' +
      '<dt>변경 전</dt><dd class="chg">' + chg('before', 'b') + '</dd><dt>변경 후</dt><dd class="chg">' + chg('after', 'a') + '</dd>' +
      '<dt>제안자</dt><dd>' + esc(r.proposer || '—') + '</dd><dt>생성 일시</dt><dd class="mono">' + esc(r.created || '—') + '</dd>' +
      '<dt>제안 사유</dt><dd>' + esc(r.reason || (r.phase === 'none' ? '위험성평가 감소대책에 ' + r.id + ' 가 연결되면 채워진다' : '—')) + '</dd>' +
      '<dt>첨부 근거</dt><dd>' + ev + '</dd></dl>';
    var review = FB.review ? '<div class="rc-review"><div class="diff">' + r.diff.map(function (x) { return '<div class="' + x[0] + '">' + esc(x[1]) + '</div>'; }).join('') + '</div>' +
      (r.rows.length ? r.rows.map(function (x) { return '<div class="hcard soft"><div class="hd"><b>' + z(x.zone) + ' ' + esc(x.mode || '') + ' · ' + esc(x.violation_type || '') + '</b>' + chip('위험도 ' + x.score + ' · ' + (x.grade || ''), 'ink') + '</div><p>' + esc(x.hazard) + '</p>' + (x.cause ? '<p>' + esc(x.cause) + '</p>' : '') + '<p class="mono">' + esc(x.measures.join(' / ')) + '</p></div>'; }).join('') : '<p class="note">연결된 평가표 행이 아직 없다.</p>') + '</div>' : '';
    $('rc-detail').innerHTML = '<div class="bh"><b>현재 선택된 변경안</b>' + chip(r.phase_text, PH_K[r.phase]) + '</div>' + dl +
      (r.rejection ? '<div class="bar ink rej"><span>반려 · ' + esc(r.rejection.name) + (r.rejection.role ? ' (' + esc(r.rejection.role) + ')' : '') + ' · ' + esc(r.rejection.ts) + '</span><span>' + esc(r.rejection.note) + '</span></div>' : '') +
      (r.demo_on ? '<p class="note" style="margin-top:6px">지금 관제 세션에 시연용으로 켜져 있다 — 확정 전이다.</p>' : '') +
      '<div class="btnrow" style="margin-top:10px">' +
        '<button class="btn sm' + (FB.review ? ' dark' : '') + '" type="button" id="rc-review" aria-pressed="' + FB.review + '">검토</button>' +
        (r.can_restore ? '<button class="btn sm" type="button" data-rc-act="restore">반려 취소</button>'
                       : '<button class="btn sm" type="button" data-rc-act="reject"' + (r.can_reject ? '' : ' disabled title="' + esc(rejTitle) + '"') + '>반려</button>') +
        '<button class="btn sm doc" type="button" data-go="docs" data-tab="ra">위험성평가로 →</button>' +
        (r.phase === 'worker' || r.phase === 'rejected' ? '<button class="go" type="button" data-go="voice">근로자 확인 →</button>' : '') +
      '</div>' + review;
  }
  $('rc-detail').addEventListener('click', function (e) {
    if (e.target.closest('#rc-review')) { FB.review = !FB.review; renderRc(); return; }
    var b = e.target.closest('[data-rc-act]'); if (!b || b.disabled) return;
    var act = b.getAttribute('data-rc-act'), r = curRc();
    ask({title: (act === 'reject' ? '변경안 반려 — ' : '반려 취소 — ') + r.id,
      note: act === 'reject' ? '이 변경안만 규칙셋에 올리지 않는다. ' + r.ra_id + ' 은 그대로 근로자 확인을 기다리고, 확정할 때 ' + r.id + ' 만 빠진다. 처리자 · 사유가 위험성평가 기록과 조정 로그에 남는다.'
                             : r.id + ' 를 다시 ' + r.ra_id + ' 근로자 확인 대상으로 되돌린다.',
      fields: [{k: 'actor', label: '처리자', req: true}, {k: 'role', label: '역할', options: ['관리자', '안전관리자', '근로자 대표']},
               {k: 'note', label: act === 'reject' ? '반려 사유 (필수)' : '사유', area: true, req: act === 'reject'}]}, function (v) {
      return api('/api/feedback/rule', {action: act, rule_id: r.id, actor: v.actor, role: v.role, note: v.note}).then(function (d) { flash(d.msg); loadFb(); tickStatus(); });
    });
  });
  // 조정 로그 — 화면에서 바로 거른다 (작은 표 · 서버에 다시 묻지 않는다)
  function fbLogRows() {
    var f = FB.lf, toks = String(f.q || '').toLowerCase().split(/\s+/).filter(Boolean);
    return FB.d.log.filter(function (r) {
      var day = r.ts.slice(0, 10);
      if (f.from && day < f.from) return false;
      if (f.to && day > f.to) return false;
      if (f.zone && r.zone.split(' · ').indexOf(f.zone) < 0) return false;
      if (f.loop && r.loop !== f.loop) return false;
      if (f.state && r.label !== f.state) return false;
      if (f.actor && r.actor !== f.actor) return false;
      if (toks.length) {
        var hay = [r.id, r.text, r.note, r.actor, r.zone, r.zname, r.kind, r.label].join(' ').toLowerCase();
        if (!toks.every(function (t) { return hay.indexOf(t) >= 0; })) return false;
      }
      return true;
    });
  }
  function uniq(xs) { var o = []; xs.forEach(function (x) { if (x && o.indexOf(x) < 0) o.push(x); }); return o; }
  function renderFbLog() {
    var d = FB.d, f = FB.lf;
    $('fbl-zone').innerHTML = opt('', '전체') + d.zones.map(function (x) { return opt(x.id, x.id + ' ' + x.name); }).join('');
    $('fbl-state').innerHTML = opt('', '전체') + uniq(d.log.map(function (r) { return r.label; })).map(function (x) { return opt(x, x); }).join('');
    $('fbl-actor').innerHTML = opt('', '전체') + uniq(d.log.map(function (r) { return r.actor; })).sort().map(function (x) { return opt(x, x); }).join('');
    syncLF();
    var rows = fbLogRows(), shown = FB.logAll ? rows : rows.slice(0, 12), toks = String(f.q || '').split(/\s+/).filter(Boolean);
    $('fb-log').innerHTML = shown.length ? shown.map(function (r) {
      var lk = r.kind === '승격' ? 'ink' : r.loop === 'short' ? 'adj' : 'mute';
      return '<tr class="' + r.loop + (r.kind === '승격' ? ' promo' : '') + '"><td class="t lb">' + esc(r.ts.slice(5)) + '</td><td>' + chip(r.kind, lk) + '</td><td class="id">' + hl(r.id, toks) + '</td>' +
        '<td>' + hl(r.text, toks) + (r.sample ? ' <span class="lv mute">예시</span>' : '') + '</td><td>' + (r.zone ? r.zone.split(' · ').map(function (x) { return z(x); }).join(' ') : '—') + '</td>' +
        '<td>' + chip(r.label, LOG_K[r.state] || 'mute') + '</td><td class="t">' + esc(r.expires || '—') + '</td><td>' + hl(r.actor || '—', toks) + '</td><td class="note2">' + hl(r.note || '', toks) + '</td></tr>';
    }).join('') : '<tr><td colspan="9" class="d">조건에 맞는 기록이 없다</td></tr>';
    $('fbl-count').textContent = rows.length + '건' + (rows.length !== d.log.length ? ' · 전체 ' + d.log.length + '건 중' : '') + (!FB.logAll && rows.length > 12 ? ' · 앞의 12건만 보인다' : '');
    $('fbl-more').hidden = rows.length <= 12;
    $('fbl-more').textContent = FB.logAll ? '접기 ↑' : '전체 보기 →';
  }
  [['fbl-from', 'from'], ['fbl-to', 'to'], ['fbl-zone', 'zone'], ['fbl-loop', 'loop'], ['fbl-state', 'state'], ['fbl-actor', 'actor']].forEach(function (x) {
    $(x[0]).addEventListener('change', function () { FB.lf[x[1]] = this.value; renderFbLog(); });
  });
  $('fbl-q').addEventListener('input', function () { FB.lf.q = this.value; renderFbLog(); });
  $('fbl-reset').addEventListener('click', function () { FB.lf = fbDefLF(FB.d.now); renderFbLog(); });
  $('fbl-more').addEventListener('click', function () { FB.logAll = !FB.logAll; renderFbLog(); });
  $('fbl-csv').addEventListener('click', function () {
    var rows = fbLogRows();
    if (!rows.length) { flash('내보낼 줄이 없다', true); return; }
    var q = function (v) { v = String(v == null ? '' : v); return /[",\r\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    var lines = [['시각', '구분', 'ID', '내용', '구역', '결과', '만료', '처리자', '사유·비고']].concat(rows.map(function (r) { return [r.ts, r.kind, r.id, r.text, r.zone, r.label, r.expires, r.actor, r.note]; }));
    var blob = new Blob(['﻿' + lines.map(function (l) { return l.map(q).join(','); }).join('\r\n')], {type: 'text/csv;charset=utf-8'});
    var url = URL.createObjectURL(blob), a = document.createElement('a');
    a.href = url; a.download = '조정로그_' + (FB.lf.from || '처음') + '_' + (FB.lf.to || '끝') + '.csv';
    document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(url); a.remove(); }, 0);
    flash('조정 로그 ' + rows.length + '줄을 내보냈다 — 지금 거른 조건 그대로');
  });
  document.querySelector('[data-screen="feedback"]').addEventListener('click', function (e) {
    if (e.target.closest('#fb-rs-hist')) {
      FB.lf = fbDefLF(FB.d.now); FB.lf.from = ''; FB.lf.loop = 'long'; FB.logAll = true; renderFbLog();
      $('fbl').scrollIntoView({behavior: 'smooth', block: 'start'}); return;
    }
    if (e.target.closest('#fb-pr-open')) {
      var open = $('fb-pr').hidden; $('fb-pr').hidden = !open;
      var b = $('fb-pr-open'); b.setAttribute('aria-expanded', open ? 'true' : 'false'); b.textContent = open ? '운영 원칙 접기 ↑' : '운영 원칙 자세히 보기 →';
      return;
    }
    var m = e.target.closest('[data-adj-more]');
    if (m) { var id = m.getAttribute('data-adj-more'); FB.open[id] = !FB.open[id]; renderFbOpen(); updLeft(); }
  });
  $('fb-open').addEventListener('click', function (e) {
    var b = e.target.closest('[data-adj]'); if (!b) return;
    var act = b.getAttribute('data-adj'), id = b.getAttribute('data-id');
    var need = act === 'revert' || act === 'reject';
    var T = {revert: '되돌리기', approve: '승인', reject: '거부', promote: '개정 제안으로 승격'};
    ask({title: T[act] + ' — ' + id, note: '처리자' + (need ? '와 사유' : '') + '가 조정 로그에 남는다.',
      fields: [{k: 'actor', label: '처리자', req: true}, {k: 'note', label: '사유' + (need ? ' (필수)' : ''), area: true, req: need}]}, function (v) {
      return api('/api/feedback/act', {action: act, adj_id: id, actor: v.actor, note: v.note}).then(function (d) { flash(d.msg); loadFb(); tickStatus(); });
    });
  });
  $('fb-eval').addEventListener('click', function () { busy(this, api('/api/feedback/eval', {})).then(function (d) { flash(d.msg); loadFb(); }).catch(fail); });
  $('fb-seg').addEventListener('click', function (e) {
    var b = e.target.closest('button'); if (!b) return;
    e.stopPropagation();
    var mode = b.getAttribute('data-fbmode');
    if (STATUS && STATUS.feedback_mode === mode) return;
    ask({title: '피드백 방식 → ' + (mode === 'auto' ? '자동' : '승인형'), note: '자동은 이탈 조건에 걸리면 바로 적용하고, 승인형은 사람이 승인해야 적용한다. 바꾼 사람과 사유가 조정 로그에 남는다.',
      fields: [{k: 'actor', label: '처리자', req: true}, {k: 'note', label: '사유 (필수)', area: true, req: true}]}, function (v) {
      return api('/api/feedback/mode', {mode: mode, actor: v.actor, note: v.note}).then(function (d) { flash(d.msg); tickStatus(); if (curScreen === 'feedback') loadFb(); });
    });
  }, true);

  /* ---------- 6. 히트맵 · 통계 (10/6 배치) ----------
     필터(기간 · 출처 · 구역)는 '적용'을 눌러야 반영된다(이벤트 로그와 같다). 카드 안 기준(전체 · 경보 이상 · 무음 기록)은 보는 방식이라 바로 바뀐다.
     비교는 직전 같은 기간 — 그 기간에 기록이 없으면 숫자를 만들지 않는다. 구역 · 부서 단위만, 개인을 평가하지 않는다. */
  var SF = {draft: {period: '14', src: '', zone: ''}, applied: {period: '14', src: '', zone: ''}, zb: 'all', hb: 'all', d: null, allZones: false};
  var SF_PERIOD = {today: '오늘', '7': '최근 7일', '14': '최근 14일', '90': '최근 90일'};
  function sfPending() { $('sf-pending').hidden = JSON.stringify(SF.draft) === JSON.stringify(SF.applied); }
  function deltaTxt(x, unit) {
    unit = unit || '건';
    if (x.diff === null) return '<span class="st-d none">직전 기간 기록 없음</span>';
    var arrow = x.diff > 0 ? '▲' : x.diff < 0 ? '▼' : '→';
    return '<span class="st-d">직전 대비 <b>' + (x.diff > 0 ? '+' : '') + x.diff + unit + '</b>' + (x.pct !== null ? ' (' + arrow + ' ' + Math.abs(x.pct) + '%)' : '') + '</span>';
  }
  function loadStats() {
    var a = SF.applied;
    return api('/api/stats?period=' + a.period + '&src=' + encodeURIComponent(a.src) + '&zone=' + encodeURIComponent(a.zone) + '&zbasis=' + SF.zb + '&hbasis=' + SF.hb).then(function (d) {
      SF.d = d;
      // 필터 칸 — 출처 · 구역 목록을 채운다(고른 값은 그대로)
      var srcSel = $('sf-src'), zSel = $('sf-zone');
      srcSel.innerHTML = opt('', '전체') + d.sources.map(function (x) { return opt(x.v, x.label); }).join(''); srcSel.value = SF.draft.src;
      if (META && zSel.options.length <= 1) zSel.innerHTML = opt('', '전체') + META.zones.map(function (x) { return opt(x.id, x.id + ' ' + x.name); }).join('');
      zSel.value = SF.draft.zone; $('sf-period').value = SF.draft.period;
      $('st-upd').innerHTML = '데이터 기준 <span class="mono">' + esc(d.updated.replace('T', ' ')) + '</span>';
      $('st-range').textContent = SF_PERIOD[a.period] + ' · ' + d.period.start.replace('T', ' ') + ' ~ ' + d.period.end.replace('T', ' ') +
        (a.src ? ' · 출처 ' + (a.src === 'sample' ? '예시 데이터' : '실시간 세션') : '') + (a.zone ? ' · 구역 ' + a.zone : '') +
        ' · 비교: 직전 같은 기간 (' + d.period.prev_start.slice(0, 10) + ' ~)' + (d.period.has_prev ? '' : ' — 기록 없음');
      sfPending();
      renderStats();
    }).catch(fail);
  }
  function renderStats() {
    var d = SF.d, k = d.kpis;
    function kpi(icon, label, x, sub, cls) {
      return '<div class="kpi st-kpi' + (cls ? ' ' + cls : '') + '"><span class="st-ki">' + ico(icon) + '</span><span class="st-kt"><span>' + label + '</span><span class="st-num"><b>' + x.cur + '</b>' + deltaTxt(x) + '</span><small>' + sub + '</small></span></div>';
    }
    $('st-kpis').innerHTML = kpi('doc', '전체 위반', k.total, '오탐 제외 · ' + SF_PERIOD[SF.applied.period]) +
      kpi('warn', '경보 이상', k.alert, '경보 · 최고 경보로 울린 것') +
      kpi('silent', '무음 기록', k.shadow, '모드가 꺼진 구간의 검출') +
      kpi('info', '오탐 표시 (이벤트 로그)', k.fp, '숫자에서 뺀 기록 · 실시간 탐지 오탐은 아래 오탐 · 미탐 표');
    // 위험 집중 구역 — 많은 구역부터(순위는 매기지 않는다)
    var rows = d.zones, show = SF.allZones ? rows : rows.slice(0, 5);
    $('st-zones').innerHTML = rows.length ? '<table class="t st-zt"><thead><tr><th>구역</th><th class="num">건수</th><th class="num">직전 대비</th></tr></thead><tbody>' +
      show.map(function (r) {
        var dd = r.diff === null ? '<span class="d">-</span>' : (r.diff > 0 ? '↑ +' + r.diff : r.diff < 0 ? '↓ ' + r.diff : '→ ±0');
        return '<tr class="click" data-st-zone="' + esc(r.zone) + '" tabindex="0" title="' + esc(r.zone) + ' 이벤트 로그 열기"><td>' + z(r.zone) + ' ' + esc(r.name) + '</td><td class="num"><b>' + r.n + '</b>건</td><td class="num">' + dd + '</td></tr>';
      }).join('') + '</tbody></table>' + (rows.length > 5 ? '<button class="go" type="button" id="st-zall" style="margin-top:8px">' + (SF.allZones ? '접기 ↑' : '전체 ' + rows.length + '개 구역 보기 →') + '</button>' : '')
      : '<p class="empty">고른 기간 · 기준에 기록이 없다.</p>';
    // 구역 × 시간 — 0~23시
    var h = d.heat, hrs = []; for (var i = 0; i < 24; i++) hrs.push(i);
    $('heat-head').innerHTML = '<tr><th class="rh">구역</th>' + hrs.map(function (x) { return '<th>' + (x % 2 ? '' : (x < 10 ? '0' : '') + x) + '</th>'; }).join('') + '</tr>';
    var mx = Math.max.apply(null, h.rows.map(function (r) { return Math.max.apply(null, r.vals); }).concat([1]));
    $('heat').innerHTML = h.rows.length ? h.rows.map(function (r) {
      return '<tr><th class="rh">' + esc(r.zone) + ' <span class="d">' + esc(r.name) + '</span></th>' + r.vals.map(function (v, hh) {
        var lvl = v === 0 ? 0 : Math.min(4, Math.ceil(v / mx * 4));
        return '<td class="h' + lvl + '" data-st-zone="' + esc(r.zone) + '" title="' + esc(r.zone + ' ' + r.name + ' · ' + (hh < 10 ? '0' : '') + hh + '시 · ' + v + '건') + '">' + (v ? v : '') + '</td>';
      }).join('') + '</tr>';
    }).join('') : '<tr><td class="h0" colspan="25">고른 기간 · 기준에 기록이 없다</td></tr>';
    $('heat-note').textContent = SF_PERIOD[SF.applied.period] + ' · 시간대별 ' + {all: '위반', alert: '경보 이상', shadow: '무음 기록'}[SF.hb] + ' ' + h.n + '건 (오탐 제외)';
    // 작업 모드 효과
    var m = d.modes;
    var mxr = Math.max.apply(null, m.rows.map(function (r) { return Math.max(r.on.rate || 0, r.off.rate || 0); }).concat([0.0001]));
    function rateCell(x, cls) {
      if (x.rate === null) return '<td><span class="d">관찰 시간 없음</span></td>';
      return '<td><span class="st-rate"><b class="mono">' + x.rate.toFixed(2) + '</b>/h<span class="st-bar"><i class="' + cls + '" style="width:' + (x.rate / mxr * 100).toFixed(0) + '%"></i></span></span><small class="d">' + x.n + '건 / ' + x.h + '시간</small></td>';
    }
    $('st-modes').innerHTML = m.rows.length ? '<table class="t st-mt"><thead><tr><th>구역</th><th>비교한 위반</th><th><i class="st-sw off"></i>평상시</th><th><i class="st-sw on"></i>모드가 켜졌을 때</th><th class="num">증가율</th></tr></thead><tbody>' +
      m.rows.map(function (r) {
        return '<tr><td>' + z(r.zone) + ' ' + esc(r.name) + '<small class="d" style="display:block">' + esc(r.modes) + '</small></td><td class="d">' + esc(r.types.replace(/_/g, ' ')) + '</td>' +
          rateCell(r.off, 'off') + rateCell(r.on, 'on') +
          '<td class="num">' + (r.few ? '<span class="lv mute" title="어느 한쪽 관찰 시간이 1시간 미만">표본 적음</span>' : r.inc === null ? '<span class="d">-</span>' : '<b class="mono">' + (r.inc > 0 ? '+' : '') + r.inc + '%</b>') + '</td></tr>';
      }).join('') + '</tbody></table>'
      : '<p class="empty">비교할 수 있는 기록이 없다 — 모드가 켜져 있던 시간과, 평상시에도 기록되는 위반 유형이 둘 다 있어야 한다.</p>';
    $('st-modes-note').innerHTML = (m.excluded.length ? '비교에서 뺀 유형(모드가 켜져야 잡히는 유형): ' + esc(m.excluded.map(function (x) { return x.replace(/_/g, ' '); }).join(' · ')) + '. ' : '') +
      (m.sample ? '예시 모드 구간을 같이 쓰고 있다(예시데이터_삭제가능/관제/sample_modes.json).' : '');
    // PPE (10/8) — 보호구(안전모 · 안전조끼)마다 한 칸. 실시간 관제 영상의 보호구 탐지와 같은 목록이다.
    // 모델이 붙고 영상이 돈 시간이 있으면 착용률(사람이 보인 시간 중 착용한 시간), 아니면 미착용 기록 건수
    $('st-ppe').innerHTML = d.ppe.length ? d.ppe.map(function (p) {
      var cnt = '미착용 기록 <b class="mono">' + p.n + '건</b>' + (p.diff === null ? ' · 직전 기간 기록 없음' : ' · 직전 대비 ' + (p.diff > 0 ? '+' : '') + p.diff + '건');
      if (p.rate !== null) {
        var deg = (p.rate / 100 * 360).toFixed(1);
        return '<div class="st-ppe-item"><div class="st-ppe-top"><div class="st-donut" style="--p:' + deg + 'deg" role="img" aria-label="' + esc(p.label) + ' 착용률 ' + p.rate + '%"><b class="mono">' + p.rate + '%</b></div>' +
          '<div><span class="note">' + esc(p.label) + ' 착용률</span><b class="st-big mono">' + p.rate + '%</b><small class="d">영상에 사람이 보인 ' + p.seen_min + '분 중 착용한 시간 · ' + cnt + '</small></div></div>' +
          '<div class="hbars" style="margin-top:10px">' + p.rate_by_dep.map(function (x) { return '<div class="hb"><span>' + esc(x.dep) + '</span><div class="tr"><i style="width:' + x.rate + '%"></i></div><b>' + x.rate + '%</b></div>'; }).join('') + '</div></div>';
      }
      var mh = Math.max.apply(null, p.by_dep.map(function (x) { return x.n; }).concat([1]));
      var why = !p.has_model ? '<b>' + esc(p.label) + ' 모델 미연결 — 착용률 대신 미착용 기록 건수</b>detect.json 의 ppe 를 켜고(enabled) 가중치를 넣으면 착용률로 바뀐다.'
        : '<b>고른 기간에 영상이 돈 시간이 없다 — 착용률 대신 미착용 기록 건수</b>실시간 관제에서 영상을 돌리면 영상이 끝날 때 착용률이 들어온다.';
      return '<div class="st-ppe-item"><div class="st-ppe-top"><span class="st-ki">' + ico('user') + '</span><div><span class="note">' + esc(p.label) + ' 미착용 기록</span><b class="st-big mono">' + p.n + '건</b>' +
        (p.diff === null ? '<small class="d">직전 기간 기록 없음</small>' : '<small class="d">직전 대비 ' + (p.diff > 0 ? '+' : '') + p.diff + '건</small>') + '</div></div>' +
        '<div class="st-notice">' + ico('info') + '<span>' + why + '</span></div>' +
        (p.by_dep.length ? '<div class="hbars" style="margin-top:10px">' + p.by_dep.map(function (x) { return '<div class="hb"><span>' + esc(x.dep) + '</span><div class="tr"><i style="width:' + (x.n / mh * 100).toFixed(0) + '%"></i></div><b>' + x.n + '건</b></div>'; }).join('') + '</div>'
          : '<p class="empty">고른 기간에 ' + esc(p.label) + ' 미착용 기록 없음</p>') + '</div>';
    }).join('') : '<p class="empty">보호구 탐지 설정이 없다 (detect.json ppe.items)</p>';
    renderQualStats(d.quality);
  }
  function statsToLog(zone) {
    var per = SF.applied.period === 'today' ? 'today' : SF.applied.period;
    var f = {period: per, zone: zone || '전체'};
    if (SF.applied.src) f.src = SF.applied.src;
    show('log', {f: f});
  }
  ['period', 'src', 'zone'].forEach(function (k) { $('sf-' + k).addEventListener('change', function () { SF.draft[k] = this.value; sfPending(); }); });
  $('sf-apply').addEventListener('click', function () { SF.applied = JSON.parse(JSON.stringify(SF.draft)); busy(this, loadStats()); });
  $('sf-reset').addEventListener('click', function () { SF.draft = {period: '14', src: '', zone: ''}; SF.applied = JSON.parse(JSON.stringify(SF.draft)); loadStats(); });
  $('st-zb').addEventListener('click', function (e) { var b = e.target.closest('button'); if (!b) return; SF.zb = b.getAttribute('data-v'); loadStats(); });
  $('st-hb').addEventListener('click', function (e) { var b = e.target.closest('button'); if (!b) return; SF.hb = b.getAttribute('data-v'); loadStats(); });
  $('st-pr-open').addEventListener('click', function () {
    var open = $('st-pr').hidden; $('st-pr').hidden = !open;
    this.setAttribute('aria-expanded', open ? 'true' : 'false'); this.textContent = open ? '상세 안내 접기 ↑' : '상세 안내 보기 →';
  });
  $('st-ppe-go').addEventListener('click', function () { show('log', {q: '미착용'}); });
  document.querySelector('[data-screen="stats"]').addEventListener('click', function (e) {
    var hb = e.target.closest('.help[aria-controls]');
    if (hb) { var box = $(hb.getAttribute('aria-controls')), open = box.hidden; box.hidden = !open; hb.setAttribute('aria-expanded', open ? 'true' : 'false'); hb.classList.toggle('on', open); return; }
    if (e.target.closest('#st-zall')) { SF.allZones = !SF.allZones; renderStats(); return; }
    var zr = e.target.closest('[data-st-zone]'); if (zr) statsToLog(zr.getAttribute('data-st-zone'));
  });
  document.querySelector('[data-screen="stats"]').addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return; var zr = e.target.closest('tr[data-st-zone]'); if (zr) statsToLog(zr.getAttribute('data-st-zone'));
  });

  /* ---------- 7. 홈 ---------- */
  var RA_KIND = {'확정': 'ok', '서명 대기': 'note', '수시평가 필요': 'crit', '정기평가 반영 대기': 'mute'};
  function loadHome() {
    return api('/api/home').then(function (d) {
      $('home-todo').innerHTML = d.cards.map(function (c, i) {
        var k = c.num ? (i === 0 ? ' crit' : i === 1 ? ' warn' : '') : '';
        return '<div class="tc' + k + '"><div class="hd"><b>' + esc(c.title) + '</b><span class="n">' + c.num + '</span></div><ul>' + c.lines.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' +
          '<button class="go" type="button" data-go="' + c.go + '"' + (c.tab ? ' data-tab="' + c.tab + '"' : '') + ' style="align-self:flex-start">' + ({docs: '안전 문서로 →', duty: '의무 이행 관리로 →', voice: '안전소통으로 →'}[c.go] || '열기 →') + '</button></div>';
      }).join('');
      $('home-board').innerHTML = d.zones.length ? d.zones.map(function (r) {
        return '<tr class="' + (r.score >= 12 ? 'hit' : '') + '"><td>' + z(r.zone) + ' ' + esc(r.zname) + '</td><td>' + esc(r.mode) + '</td><td class="num">' + (r.score >= 12 ? '<b>' + r.score + '</b>' : r.score) + ' <span class="d">' + esc(r.grade) + '</span></td><td>' + chip(r.ra, RA_KIND[r.ra] || 'mute') + '</td><td>' + (r.co ? '미조치 ' + r.co : '—') + '</td><td>' + (r.ptw && r.ptw !== '-' ? esc(r.ptw) : '—') + '</td><td>' + (r.voice || '—') + '</td></tr>';
      }).join('') : '<tr><td colspan="7" class="d">관제 기록이 아직 없다</td></tr>';
      var ev = d.evidence;
      $('home-period').textContent = ev.period + ' · 중처법 이행 증빙';
      $('home-kpis').innerHTML =
        '<div class="kpi"><span>이벤트</span><b>' + ev.events + '</b><small>경보 ' + ev.alerts + ' · 무음 ' + ev.silent + '</small></div>' +
        '<div class="kpi"><span>저장된 클립</span><b>' + ev.clips + '</b><small>전후 클립 · 대표 프레임</small></div>' +
        '<div class="kpi"><span>작업 전 게이트</span><b>' + ev.gates + '</b><small>목록 누락 · 미첨부</small></div>' +
        '<div class="kpi"><span>확정 문서</span><b>' + (ev.confirmed + ev.correctives) + '</b><small>평가 ' + ev.confirmed + ' · 지시서 ' + ev.correctives + '</small></div>';
      $('home-note').textContent = '기록된 날 ' + ev.recorded + '/' + ev.days + (ev.gaps.length ? ' · 끊긴 날 ' + ev.gaps.join(', ') + ' — 카메라 · 시스템 점검 대상' : ' · 끊긴 날 없음') +
        (d.handoff ? ' · 관제 인계 ' + d.handoff.n + '회, 마지막 ' + d.handoff.id + ' (' + d.handoff.source + ', 감지 ' + d.handoff.events + '건)' : '');
    }).catch(fail);
  }

  /* ---------- 8. 의무 이행 관리 ---------- */
  var DUTY = null;
  function dutyBody() { return {industry: $('dt-ind').value, workers: $('dt-n').value, cat: $('dt-cat').value, hazardous: META.profile.hazardous}; }
  function loadDuty() {
    return api('/api/duty', dutyBody()).then(function (d) {
      DUTY = d;
      var s = d.summary;
      $('dt-summary').textContent = '기준일 ' + d.today + ' · 기한 경과 ' + s.overdue + ' · 1일 이내 ' + s.urgent + ' · 7일 이내 ' + s.soon + ' · 30일 이내 ' + s.upcoming + ' · 여유 ' + s.ok;
      $('dt-rows').innerHTML = d.items.length ? d.items.map(function (it) {
        return '<tr class="' + (it.kind === 'crit' ? 'hit' : '') + '" title="' + esc(it.why) + '"><td>' + chip(it.status, it.kind) + '</td><td>' + esc(it.name) + (it.ref ? ' <span class="d mono">' + esc(it.ref) + '</span>' : '') + '</td><td class="nw">' + esc(it.category) + '</td><td>' + esc(it.basis) + '</td><td class="t">' + esc(it.due) + '</td><td>' + esc(it.retention) + '</td></tr>';
      }).join('') : '<tr><td colspan="6" class="d">해당 의무 없음</td></tr>';
      var cur = $('dt-item').value;
      $('dt-item').innerHTML = d.items.map(function (it) { return opt(it.key, it.name + (it.ref ? ' · ' + it.ref : '') + ' (기한 ' + it.due + ')', it.key === cur); }).join('');
      if (!$('dt-day').value) $('dt-day').value = d.today;
      $('dt-done').innerHTML = d.done.length ? d.done.map(function (r) {
        return '<tr><td class="t">' + esc(r['이행일']) + '</td><td>' + esc(r['의무']) + (r['대상'] && r['대상'] !== '-' ? ' <span class="d mono">' + esc(r['대상']) + '</span>' : '') + '</td><td>' + esc([r['담당자'], r['부서']].filter(function (x) { return x && x !== '-'; }).join(' · ') || '—') + '</td><td>' + esc(r['출처']) + '</td><td class="t">' + esc(r['서류 보존']) + '</td></tr>';
      }).join('') : '<tr><td colspan="5" class="d">이행 기록 없음</td></tr>';
    }).catch(fail);
  }
  ['dt-ind', 'dt-cat'].forEach(function (id) { $(id).addEventListener('change', loadDuty); });
  $('dt-n').addEventListener('change', loadDuty);
  $('dt-day').addEventListener('blur', function () {
    var v = this.value.trim(); if (!v) return;
    api('/api/norm-day?value=' + encodeURIComponent(v) + (DUTY ? '&today=' + DUTY.today : '')).then(function (d) { $('dt-day').value = d.day; }).catch(fail);
  });
  $('dt-go').addEventListener('click', function () {
    busy(this, api('/api/duty/done', {key: $('dt-item').value, staff: $('dt-who').value, day: $('dt-day').value, note: $('dt-note').value, today: DUTY && DUTY.today}))
      .then(function (d) { flash(d.msg); $('dt-note').value = ''; loadDuty(); tickStatus(); }).catch(fail);
  });

  /* ---------- 9. 안전 문서 ---------- */
  function pickTab(group, tab) {
    var bar = document.querySelector('.subtabs[data-group="' + group + '"]'); if (!bar) return;
    bar.querySelectorAll('button').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-tab') === tab); });
    document.querySelectorAll('[data-pane^="' + group + ':"]').forEach(function (p) { p.hidden = p.getAttribute('data-pane') !== group + ':' + tab; });
    if (group === 'docs') loadDocTab(tab);
    if (group === 'accdoc') renderAccDocs();       // 두 탭이 같은 내용을 쓴다 — 탭을 바꿀 때 다시 그린다 (10/13)
    if (group === 'arc') { if (tab === 'acc') loadAccStats(); else loadArchive(); }
  }
  var DOCS = {tab: 'ra', ev: null, ptw: null, acc: null, hid: null, ra: null, raPick: {}};
  function loadDocTab(tab, o) {
    DOCS.tab = tab; o = o || {};
    if (tab === 'ra') return loadRa();
    if (tab === 'corrective') return loadCo(o.ev);
    if (tab === 'ptw') return loadPtwDoc(o.ptw);
    if (tab === 'accident') return loadAcc(o.acc);
    if (tab === 'handoff') return loadHo(o.hid);
  }

  /* 위험성평가 */
  function loadRa() {
    return api('/api/docs/ra').then(function (d) { DOCS.ra = d; renderRa(); }).catch(fail);
  }
  function renderRa() {
    var d = DOCS.ra, has = d.drafts.length > 0;
    $('ra-steps').innerHTML = '<span class="done">① 이벤트 집계 · 위험도 계산</span>→<span class="' + (has ? 'done' : 'now') + '">② 자동 초안 생성</span>→<span class="' + (has ? 'now' : '') + '">③ 관리자 서명 → 근로자 확인 요청</span>';
    $('ra-calc').innerHTML = d.rows.length ? '<table class="t" style="min-width:640px"><thead><tr><th></th><th>구역</th><th>모드</th><th>위반 유형</th><th>건수</th><th>가능성</th><th>중대성</th><th>위험도</th></tr></thead><tbody>' +
      d.rows.map(function (r) {
        return '<tr class="' + (r.adhoc.length ? 'hit' : '') + '" title="' + esc(r.l_label + (r.adhoc.length ? ' · ' + r.adhoc.join(', ') : '')) + '"><td class="pick"><input type="checkbox" data-ra-pick="' + r.i + '"' + (DOCS.raPick[r.i] ? ' checked' : '') + ' aria-label="이 행으로 초안"></td><td>' + z(r.zone) + '</td><td>' + esc(r.mode) + '</td><td>' + esc(r.type) + '</td><td class="num">' + r.count + '</td><td class="num">' + r.likelihood + (/하한/.test(r.l_label) ? ' <span class="d">(하한)</span>' : '') + '</td><td class="num">' + r.severity + '</td><td class="num">' + (r.score >= 12 ? '<b>' + r.score + '</b>' : r.score) + '</td></tr>';
      }).join('') + '</tbody></table>' : '<p class="empty">최근 90일 관제 기록이 없다.</p>';
    $('ra-bar').innerHTML = d.adhoc.length ? '<div class="bar crit"><span>위험도 12 이상 또는 중대성 4 1건 → 수시평가 제안 ' + d.adhoc.length + '건</span><span>위험성평가 지침 제15조제2항</span></div>'
      : '<div class="bar ok"><span>수시평가 제안 없음 — 정기평가로 반영</span></div>';
    if (!has) {
      $('ra-sheet').innerHTML = '<div class="ph"><h2>초안</h2><span class="sub">문장 칸은 직접 고칠 수 있다</span></div><p class="empty">자동 초안 생성을 누르면 여기에 평가표 초안이 뜬다. 숫자 칸은 코드가 채우고, 문장 칸은 관제 기록으로 조립한다(외부 AI 없음).</p>';
      return;
    }
    var today = (STATUS ? STATUS.now : '').slice(0, 10);
    var kind = d.adhoc.length ? '수시' : '정기';
    var sheets = d.drafts.map(function (x) {
      function ed(k, v) { return '<dd class="llm" contenteditable="true" data-ed="' + k + '" data-i="' + x.i + '">' + esc(v) + '</dd>'; }
      return '<div class="docsheet"><div class="dh"><b>' + z(x.zone) + ' ' + esc(x.zname) + ' · ' + esc(x.mode) + '</b><span class="mono sub">' + esc(x.type) + ' · 위험도 ' + x.score + ' ' + esc(x.grade) + '</span></div><dl>' +
        '<dt>평가 구분 · 일자</dt><dd class="code"><span data-kind-view>' + kind + '</span> · ' + esc(today) + '</dd>' +
        '<dt>근거</dt><dd class="code">' + esc(x.event_ids.slice(0, 6).join(' · ') + (x.event_ids.length > 6 ? ' 외 ' + (x.event_ids.length - 6) + '건' : '')) + (x.accident_ids.length ? ' · 사고 ' + esc(x.accident_ids.join(', ')) : '') + '</dd>' +
        '<dt>가능성 × 중대성</dt><dd class="code">' + x.likelihood + ' × ' + x.severity + ' = <b>' + x.score + '</b> (' + esc(x.grade) + ')</dd>' +
        '<dt>단위작업</dt>' + ed('unit_work', x.unit_work) +
        '<dt>유해위험요인</dt>' + ed('hazard', x.hazard) +
        '<dt>발생 원인</dt>' + ed('cause', x.cause) +
        '<dt>현재 안전조치</dt>' + ed('current_measures', x.current_measures) +
        '<dt>감소대책</dt>' + ed('measures', x.measures) +
        '<dt>법적 근거</dt>' + ed('legal_refs', x.legal_refs) +
        '<dt>개선 후 위험도</dt><dd class="d">비워 둔다 — 적용 후 14일 실측</dd>' +
        (x.check ? '<dt>확인 필요</dt><dd class="d">' + esc(x.check) + '</dd>' : '') +
        '<dt>확인</dt><dd class="human">관리자 ☐ · 근로자 대표 ☐</dd></dl></div>';
    }).join('');
    $('ra-sheet').innerHTML = '<div class="ph"><h2>초안 — ' + d.drafts.length + '행</h2><span class="sub">문장 칸(노란 칸)은 눌러서 직접 고친다. 감소대책은 한 줄에 하나, [공학적]·[관리적]·[보호구]로 시작. 규칙 변경과 같으면 [관리적·R1]처럼 적는다</span></div>' + sheets +
      '<div class="btnrow" style="margin-top:10px">' +
      '<span class="field" style="flex-direction:row;align-items:center;gap:8px"><span class="lb">평가 구분</span><span class="seg" id="ra-kind"><button type="button"' + (kind === '수시' ? ' class="on"' : '') + ' data-v="수시">수시</button><button type="button"' + (kind === '정기' ? ' class="on"' : '') + ' data-v="정기">정기</button></span></span>' +
      '<span class="field" style="flex-direction:row;align-items:center;gap:8px"><label for="ra-sign">서명</label><select id="ra-sign">' + META.staff.map(function (p) { return opt(p.name, p.label); }).join('') + '</select></span>' +
      '<button class="btn dark" type="button" id="ra-go">관리자 서명 → 근로자 확인 요청</button>' + download(d.file, '엑셀로 내려받기') + '</div>';
  }
  $('ra-calc').addEventListener('change', function (e) { var c = e.target.closest('[data-ra-pick]'); if (c) DOCS.raPick[c.getAttribute('data-ra-pick')] = c.checked; });
  $('ra-draft').addEventListener('click', function () {
    var pick = Object.keys(DOCS.raPick).filter(function (k) { return DOCS.raPick[k]; }).map(Number);
    busy(this, api('/api/docs/ra/draft', {rows: pick})).then(function (d) { DOCS.ra.drafts = d.drafts; DOCS.ra.file = d.file; renderRa(); flash('초안 ' + d.drafts.length + '행 — 문장 칸을 확인하고 서명한다'); }).catch(fail);
  });
  $('ra-sheet').addEventListener('click', function (e) {
    var kb = e.target.closest('#ra-kind button');
    if (kb) { $('ra-kind').querySelectorAll('button').forEach(function (b) { b.classList.toggle('on', b === kb); }); document.querySelectorAll('[data-kind-view]').forEach(function (s) { s.textContent = kb.getAttribute('data-v'); }); return; }
    if (!e.target.closest('#ra-go')) return;
    var edits = {};
    document.querySelectorAll('#ra-sheet [data-ed]').forEach(function (dd) {
      var i = dd.getAttribute('data-i'); edits[i] = edits[i] || {i: +i}; edits[i][dd.getAttribute('data-ed')] = dd.innerText.trim();
    });
    var k = $('ra-kind').querySelector('button.on');
    busy(e.target, api('/api/docs/ra/sign', {edits: Object.keys(edits).map(function (i) { return edits[i]; }), kind: k ? k.getAttribute('data-v') : '수시', manager: $('ra-sign').value}))
      .then(function (d) { flash(d.msg); loadRa(); tickStatus(); }).catch(fail);
  });

  /* 시정지시서 */
  function loadCo(ev) {
    return api('/api/docs/co').then(function (d) {
      var want = ev || DOCS.ev || d.default;
      if (!d.events.some(function (x) { return x.id === want; })) want = d.default;
      DOCS.ev = want;
      $('co-ev').innerHTML = d.events.map(function (e) {
        return opt(e.id, (e.replay ? '[재생 비교 검증본] ' : '') + e.id + ' · ' + e.ts + ' · ' + e.zone + ' · ' + e.level + ' · ' + e.type + (e.frame ? ' · 프레임' : '') + (e.handoff ? ' · 관제 인계' : '') + (e.issued ? ' · 발행 ' + e.issued : ''), e.id === want);
      }).join('') || opt('', '경보 이상 이벤트가 없다');
      return want ? showCoEvent(want) : null;
    }).catch(fail);
  }
  function showCoEvent(id) {
    DOCS.ev = id;
    return api('/api/docs/co/' + encodeURIComponent(id)).then(function (e) {
      $('co-frame').innerHTML = e.frame ? '<img alt="' + esc(id) + ' CCTV 프레임" src="/api/docs/co/' + encodeURIComponent(id) + '/frame">'
        : camSVG({poly: e.zone + ' 구역', active: true, aria: id + ' 대표 프레임', note: '프레임 없음 — 영상이 없던 기록'});
      $('co-info').innerHTML = '<table class="t"><tbody>' +
        '<tr><td class="d">일시</td><td class="t">' + esc(e.ts) + '</td></tr><tr><td class="d">구역 · 모드</td><td>' + z(e.zone) + ' ' + esc(e.zname) + ' · ' + esc(e.mode) + '</td></tr>' +
        '<tr><td class="d">판정</td><td>' + lv(e.level) + ' ' + esc(e.type) + (e.row ? ' · ' + e.row + '번 줄' : '') + '</td></tr>' +
        '<tr><td class="d">규칙</td><td>' + esc(e.adj ? '강화 중 ' + e.adj : '기본') + '</td></tr>' +
        (e.handoff ? '<tr><td class="d">관제 인계</td><td class="t">' + esc(e.handoff) + '</td></tr>' : '') +
        (e.replay ? '<tr><td class="d">표시</td><td>' + tag('재생 비교 검증본', 'doc') + ' <span class="note">' + esc(e.replay) + '</span></td></tr>' : '') + '</tbody></table>';
      $('co-sheet').innerHTML = '<div class="ph"><h2>시정지시서 초안</h2>' + (e.issued ? '<span class="lv ok">발행 ' + esc(e.issued.doc_no) + '</span>' : '<span class="lv note">아직 없음</span>') + '</div>' +
        '<p class="note">' + (e.replay ? '재생 비교 검증본이다 — 만든 문서에 검증본 표시가 찍히고, 의무 이행 관리(조치 기한) · 기록(보존)에는 올라가지 않는다. ' : '') + (e.issued ? '이미 발행한 지시서가 있다 (조치 기한 ' + esc(e.issued.deadline) + '). 다시 만들면 같은 번호의 새 판이 기록된다.' : '장면 설명 · 위험 요인 · 시정 요구 문장만 관제 기록으로 조립하고, 조치 기한과 근거 기록은 코드가 채운다. 만들면 발행 기록이 남고 의무 이행 관리에 조치 기한이 올라간다.') + '</p>' +
        '<div class="btnrow" style="margin-top:10px"><button class="btn dark" type="button" id="co-go">시정지시서 초안 생성</button>' + download(e.issued && e.issued.file, '워드로 내려받기') + '</div>';
      DOCS.co = null;
      if (e.order) renderCoSheet(e.order);           // 만들어 둔 초안이 있으면 바로 고칠 수 있게 연다 (10/8)
    }).catch(fail);
  }
  $('co-ev').addEventListener('change', function () { showCoEvent(this.value); });
  /* 시정지시서 초안 — 문장 칸(노란 칸) · 조치 기한 · 법적 근거 · 수신자는 눌러서 고친다 (10/8). 문서번호 · 중대성 · 근거 기록은 코드 값 그대로 */
  function coEd(k, v) { return '<dd class="llm" contenteditable="true" data-co-ed="' + k + '">' + esc(v) + '</dd>'; }
  function renderCoSheet(o) {
    DOCS.co = o;
    var hz = o.hazards.map(function (h) { return h.rank + '. ' + h.hazard + (h.reason ? ' — ' + h.reason : ''); }).join('\n');
    var ac = o.actions.map(function (a) { return '[' + a.category + '] ' + a.text; }).join('\n');
    var rows = [['발행일 · 구역', 'code', esc(o.issued) + ' · ' + z(o.zone) + ' ' + esc(o.zname)],
      ['판정', 'code', lv(o.level) + ' ' + esc(o.type) + ' · 모드 ' + esc(o.mode) + ' · ' + esc(o.rule_state)],
      ['근거', 'code', esc(o.event_id) + ' · ' + esc(o.clip || '클립 없음') + ' · 같은 위반 최근 14일 ' + o.same_recent + '건'],
      ['중대성', 'code', o.severity + '등급 (' + esc(o.severity_label) + ')']];
    var html = rows.map(function (r) { return '<dt>' + r[0] + '</dt><dd class="' + r[1] + '">' + r[2] + '</dd>'; }).join('') +
      '<dt>현장 상황</dt>' + coEd('scene', o.scene) +
      '<dt>위험 기인물</dt>' + coEd('hazards', hz) +
      '<dt>위반 사항</dt>' + coEd('violation', o.violation) +
      '<dt>시정 요구</dt>' + coEd('actions', ac) +
      '<dt>조치 기한</dt><dd class="human" contenteditable="true" data-co-ed="deadline">' + esc(o.deadline) + '</dd>' +
      '<dt>법적 근거</dt><dd class="human" contenteditable="true" data-co-ed="legal_refs">' + esc(o.legal_refs.join('\n')) + '</dd>' +
      '<dt>확인 필요</dt>' + coEd('uncertain', o.uncertain || '') +
      (o.warnings.length ? '<dt>시스템 경고</dt><dd class="d">' + o.warnings.map(esc).join('<br>') + '</dd>' : '') +
      '<dt>수신</dt><dd class="human" contenteditable="true" data-co-ed="recipient">' + esc(o.recipient || '') + '</dd>';
    if (o.replay) html = '<dt>표시</dt><dd class="code">' + tag('재생 비교 검증본', 'doc') + ' ' + esc(o.replay) + '</dd>' + html;
    $('co-sheet').innerHTML = '<div class="ph"><h2>시정지시서 초안</h2>' + (o.replay ? tag('재생 비교 검증본', 'doc') : '<span class="lv note">' + (o.edited ? '고친 판' : '초안') + '</span>') +
      '<span class="sub">✎ 표시 칸(노란 칸 · 초록 칸)은 눌러서 바로 고친다. 위험 기인물은 한 줄에 하나(1. 기인물 — 이유), 시정 요구는 한 줄에 하나([공학적] · [관리적] · [보호구] 로 시작), 법적 근거도 한 줄에 하나. 조치 기한을 날짜(2026-10-15 …)로 시작하면 의무 이행 관리 기한도 바뀐다</span></div>' +
      '<div class="docsheet"><div class="dh"><b>시정지시서</b><span class="mono" style="font-size:12px;color:var(--ink-2)">' + esc(o.doc_no) + (o.edited ? ' · 고침 ' + esc(String(o.edited.at || '').slice(0, 16).replace('T', ' ')) + (o.edited.by ? ' ' + esc(o.edited.by) : '') : '') + '</span></div><dl>' + html + '</dl></div>' +
      '<div class="btnrow" style="margin-top:10px">' +
      '<span class="field" style="flex-direction:row;align-items:center;gap:8px"><label for="co-editor">고친 사람</label>' +
        ((META.staff || []).length ? '<select id="co-editor">' + META.staff.map(function (p) { return opt(p.name, p.label); }).join('') + '</select>'
          : '<input id="co-editor" type="text" placeholder="이름 · 직책" style="width:140px">') + '</span>' +
      '<button class="btn dark" type="button" id="co-save">고친 내용 저장 · 워드 다시 만들기</button>' + download(o.file, '워드로 내려받기') + '<button class="btn sm" type="button" id="co-go">자동 초안 다시 만들기</button></div>' +
      '<p class="note" style="margin-top:6px">' + (o.replay ? '검증본 — 발행 · 조치 대상이 아니라 보존 기한을 두지 않는다' : '보존: 조치 이행일부터 5년 (중대재해처벌법 시행령 제13조). ‘자동 초안 다시 만들기’는 고친 문장을 덮어쓴다') + '</p>';
  }
  $('co-sheet').addEventListener('click', function (e) {
    if (e.target.closest('#co-save')) {
      if (!DOCS.co) return;
      var body = {doc_no: DOCS.co.doc_no, editor: ($('co-editor') || {}).value || ''};
      document.querySelectorAll('#co-sheet [data-co-ed]').forEach(function (dd) { body[dd.getAttribute('data-co-ed')] = dd.innerText.trim(); });
      busy(e.target, api('/api/docs/co/edit', body)).then(function (o) { renderCoSheet(o); flash(o.doc_no + ' — 고친 내용으로 워드를 다시 만들었다'); tickStatus(); }).catch(fail);
      return;
    }
    if (!e.target.closest('#co-go')) return;
    var again = DOCS.co && DOCS.co.edited;
    var go = function () {
      return busy(e.target, api('/api/docs/co', {event_id: DOCS.ev})).then(function (o) {
        renderCoSheet(o);
        flash(o.doc_no + (o.replay ? ' — 재생 비교 검증본' : ' — 초안 · 발행 기록')); tickStatus();
      }).catch(fail);
    };
    if (again) ask({title: '자동 초안 다시 만들기', note: '고친 문장이 새 자동 초안으로 덮어써진다. 계속할까?', fields: []}, go);
    else go();
  });

  /* 작업허가서 점검 */
  function loadPtwDoc(pid) {
    return api('/api/docs/ptw').then(function (d) {
      var want = pid || DOCS.ptw || (d.ptws[0] || {}).id;
      if (!d.ptws.some(function (p) { return p.id === want; })) want = (d.ptws[0] || {}).id;
      DOCS.ptw = want;
      $('ptw-sel').innerHTML = d.ptws.map(function (p) { return opt(p.id, p.id + ' · ' + p.type + ' · ' + p.zone + ' · ' + p.work, p.id === want); }).join('') || opt('', '등록된 허가서가 없다');
      $('ptw-find').innerHTML = '<p class="empty">점검을 누르면 격리 목록 · 밸브 단독 격리 · 퍼지 · 측정 · 동시작업을 코드로 판정하고, 지적 문장만 미리 써 둔 문장 · 템플릿으로 채운다.</p>'; $('ptw-cnt').innerHTML = '';
      return want ? showPtwDoc(want) : null;
    }).catch(fail);
  }
  /* 공통 양식(안전작업허가서) 작성본 요약 · 원본 워드 (10/8) — 문서 자동화 · 격리 목록 대조가 같이 쓴다 */
  function ptwFormHtml(d) {
    var f = d.form; if (!f && !d.doc) return '';
    var h = '';
    if (f) {
      h += '<p>공통 양식 · ' + esc(f.category) + (f.supplementary.length ? ' · 보충 ' + esc(f.supplementary.join(', ')) : '') + ' · 안전조치 해당 ' + f.need + '건' +
        (f.not_done.length ? ' — <b class="x">미실시 ' + f.not_done.length + '건: ' + esc(f.not_done.join(', ')) + '</b>' : ' — 모두 실시') + '</p>';
      if (f.unsigned.length) h += '<p class="note">서명 빈칸: ' + esc(f.unsigned.join(', ')) + '</p>';
    }
    if (d.doc) h += '<div class="btnrow" style="margin-top:6px">' + download(d.doc, '허가서 원본 (공통 양식) 내려받기') + '</div>';
    return h;
  }
  function showPtwDoc(pid) {
    DOCS.ptw = pid;
    return api('/api/docs/ptw/' + encodeURIComponent(pid)).then(function (d) {
      var p = d.ptw;
      var stp = d.steps || {};
      $('ptw-info').innerHTML = '<div class="hcard soft"><div class="hd"><b class="mono">' + esc(p.ptw_id) + '</b>' + chip(p.type, 'info') + '</div><p>' + z(p.zone) + ' ' + esc(d.zname) + ' · ' + esc(p.work) + '</p><p>' + esc((p.start || '').replace('T', ' ')) + ' ~ ' + esc((p.end || '').slice(11)) + ' · 인원 ' + esc(p.workers || '-') + ' · 작업책임자 ' + esc(p.supervisor || '(비어 있음)') + ' · 퍼지 ' + esc(d.purge == null ? '-' : d.purge) + '분' + (stp.purge_state === 'run' ? ' (진행 중)' : '') + '</p>' + (p.registered_at ? '<p class="note">관제 격리 목록 대조에서 등록 · ' + esc(p.registered_at.replace('T', ' ')) + '</p>' : '') + ptwFormHtml(d) +
        '<p class="note">관제 격리 목록 대조와 같은 데이터 — ' + (stp.steps ? '단계 입력 ' + stp.steps + '건(맹판 · 측정 · 퍼지)이 반영된 값' : '단계 입력 없음 · 허가서 원본 값') + (stp.expired && stp.expired.length ? ' · 측정 만료 ' + esc(stp.expired.join(', ')) : '') + '</p></div>';
      $('ptw-list').innerHTML = d.iso ? '<div class="tbl"><table class="t"><thead><tr><th>line_id</th><th>배관</th><th>격리방법</th><th>맹판</th></tr></thead><tbody>' +
        d.iso.map(function (l) { var b = String(l['맹판설치'] || '').trim().toUpperCase(); return '<tr><td class="t">' + esc(l.line_id) + '</td><td>' + esc(l['배관'] || '') + '</td><td>' + esc(l['격리방법'] || '-') + '</td><td class="c ' + (b === 'O' ? 'y' : 'x') + '">' + (b === 'O' ? 'O' : '대기') + '</td></tr>'; }).join('') + '</tbody></table></div>'
        : '<p class="empty">첨부된 격리 목록 없음</p>';
    }).catch(fail);
  }
  $('ptw-sel').addEventListener('change', function () { showPtwDoc(this.value); $('ptw-find').innerHTML = ''; $('ptw-cnt').innerHTML = ''; });
  $('ptw-run').addEventListener('click', function () {
    busy(this, api('/api/docs/ptw/' + encodeURIComponent(DOCS.ptw), {})).then(function (r) {
      var crit = function (c) { return ['R1', 'R2', 'LIST', 'SIMOPS'].indexOf(c) >= 0; };
      $('ptw-cnt').innerHTML = chip(r.findings.length ? r.findings.length + '건' : '없음', r.findings.length ? 'crit' : 'ok');
      $('ptw-find').innerHTML = '<div class="bar ' + (r.findings.length ? 'crit' : 'ok') + '" style="margin-top:0"><span>' + esc(r.result) + '</span><span>판정은 코드 · 문장은 ' + esc(r.text_source) + '</span></div><p class="note">' + esc(r.summary) + '</p>' +
        (r.findings.length ? r.findings.map(function (f) {
          return '<div class="hcard' + (crit(f.code) ? ' crit' : '') + '"><div class="hd"><b>' + esc(f.code) + ' · ' + esc(f.title) + '</b></div><p>' + esc(f.detail) + '</p><p>' + esc(f.note) + '</p><p class="note">' + esc(f.legal_refs.join(' · ')) + '</p></div>';
        }).join('') : '<p class="empty">찾은 항목 없음 — 허가 발급 가능</p>') +
        '<div class="tbl"><table class="t"><thead><tr><th>배관</th><th>이름</th><th>유체</th><th>격리 목록</th><th>맹판</th><th>측정</th></tr></thead><tbody>' +
        r.pid.map(function (l) { return '<tr class="' + (l.listed ? '' : 'hit') + '"><td class="t">' + esc(l.line_id) + '</td><td>' + esc(l.name) + '</td><td>' + esc(l.fluid) + '</td><td>' + (l.listed ? '있음' : '<b class="x">없음</b>') + '</td><td>' + esc(l.blind || '-') + '</td><td>' + esc(l.gas || '-') + '</td></tr>'; }).join('') + '</tbody></table></div>' +
        '<div class="btnrow">' + download(r.file, '점검 결과 워드로 내려받기') + '</div>';
    }).catch(fail);
  });

  function accTimeline(tl) {
    return '<table class="t"><tbody>' + tl.map(function (t) { return '<tr class="' + t.kind + '"><td class="t">' + esc(t.t) + '</td><td class="t">' + esc(t.src) + '</td><td>' + esc(t.what) + '</td></tr>'; }).join('') + '</tbody></table>';
  }
  /* 산업재해조사표 · 사고조사보고서 (10/13) — 사고 한 건 = 기록 한 줄(accident_case.py).
     재해 정보는 두 문서 공통 · 진행 상태(감지됨 → 내부 보고서 → 조사표 → 근로자대표 확인 → 제출) · 원본 양식에 채운 두 문서 */
  var ACC = {list: null, d: null, c: null, stage: '', dirty: false};
  var ACC_CATS = ['관리적', '설비적', '인적', '물질·환경적', '기타'];
  function ddayTxt(n) {
    if (n < 0) return '<span class="dday crit">기한 ' + (-n) + '일 지남</span>';
    return '<span class="dday ' + (n <= 3 ? 'crit' : n <= 7 ? 'warn' : '') + '">D-' + n + '</span>';
  }
  function loadAcc(aid) {
    return api('/api/docs/acc').then(function (d) {
      ACC.list = d;
      renderAccSteps();
      var want = fillAccSel(aid || DOCS.acc || d.default);
      if (!want) { emptyAcc(); return null; }
      return showAcc(want);
    }).catch(fail);
  }
  function renderAccSteps() {
    var d = ACC.list;
    var chips = d.stages.map(function (s) {
      var cls = s.key === 'detected' && s.n ? 'hot' : s.key === 'submitted' ? 'done' : s.key === 'closed' ? 'closed' : '';
      return '<button type="button" class="' + cls + (ACC.stage === s.key ? ' on' : '') + '" data-acc-stage="' + s.key + '" title="누르면 아래 사고 목록이 이 단계로 걸러진다">' + esc(s.label) + '<b>' + s.n + '</b></button>';
    }).join('');
    var soon = d.soon.filter(function (r) { return r.dday <= 7; });
    var soonTxt = soon.length ? (soon[0].dday < 0 ? '' : '기한 임박 ') + ddayTxt(soon[0].dday) + ' ' + esc(soon[0].id) + (soon.length > 1 ? ' 외 ' + (soon.length - 1) + '건' : '') : '';
    $('acc-steps').innerHTML = '<span class="lbl">진행 상태</span>' + chips + (soonTxt ? '<span class="soon">' + soonTxt + '</span>' : '');
  }
  function fillAccSel(want) {
    var rows = ACC.list.accidents.filter(function (a) { return !ACC.stage || a.status === ACC.stage; });
    if (!rows.some(function (a) { return a.id === want; })) want = rows.length ? rows[rows.length - 1].id : null;
    $('acc-sel').innerHTML = rows.slice().reverse().map(function (a) {
      return opt(a.id, a.id + ' · ' + a.date + ' ' + a.time + ' · ' + (a.zone || '') + ' ' + a.summary + ' (' + a.status_label + ')', a.id === want);
    }).join('') || opt('', ACC.stage ? '이 단계의 사고가 없다' : '사고 기록이 없다 — 관제에서 사고가 넘어오면 여기에 뜬다');
    return want;
  }
  function emptyAcc() {
    ACC.d = null; ACC.c = null; DOCS.acc = null;
    $('acc-due').innerHTML = ''; $('acc-tl').innerHTML = '<p class="empty">사고를 고르면 사고 전 관제 기록이 보인다.</p>';
    $('acc-flow').innerHTML = ''; $('acc-form').innerHTML = $('acc-report').innerHTML = '<p class="empty">고른 사고가 없다.</p>';
    $('acc-files').innerHTML = ''; $('acc-files-sub').textContent = '';
  }
  function showAcc(aid) {
    DOCS.acc = aid;
    return api('/api/docs/acc/' + encodeURIComponent(aid)).then(renderAcc).catch(fail);
  }
  function renderAcc(d) {
    ACC.d = d; ACC.c = JSON.parse(JSON.stringify(d.case)); ACC.dirty = false;
    var open = d.status !== 'submitted' && d.status !== 'closed';
    $('acc-due').innerHTML = '발생일부터 1개월 이내 제출 · 기한 <b>' + esc(d.due) + '</b>' + (open && d.target !== false ? ' ' + ddayTxt(d.dday) : '');
    $('acc-tl').innerHTML = d.timeline.length ? accTimeline(d.timeline) : '<p class="empty">사고 전 관제 기록이 없다.</p>';
    // 재해 정보 입력 (두 문서 공통)
    var c = ACC.c, o = d.options;
    $('acf-acc_type').innerHTML = opt('', '고른다') + o.types.map(function (t) { return opt(t, t, t === c.acc_type); }).join('');
    $('acf-employ').innerHTML = opt('', '고른다') + o.employ.map(function (t) { return opt(t, t, t === c.employ); }).join('');
    $('acf-shift').innerHTML = opt('', '고른다') + o.shift.map(function (t) { return opt(t, t, t === c.shift); }).join('');
    ['dept', 'injury', 'body_part', 'duty', 'tenure'].forEach(function (k) { $('acf-' + k).value = c[k] || ''; });
    $('acf-lost_days').value = c.lost_days === '' || c.lost_days == null ? '' : c.lost_days;
    $('acf-fatal').value = c.fatal ? '1' : '';
    $('acf-causes').innerHTML = o.causes.map(function (k) {
      var on = (c.causes || []).indexOf(k) >= 0;
      return '<label class="' + (on ? 'on' : '') + '"><input type="checkbox" value="' + esc(k) + '"' + (on ? ' checked' : '') + '>' + esc(k) + '</label>';
    }).join('');
    renderAccFlow(); renderAccDocs(); renderAccFiles();
  }
  function renderAccFlow() {
    var d = ACC.d, st = d.status, idx = -1;
    d.stages.forEach(function (s, i) { if (s.key === st) idx = i; });
    var chips = d.stages.map(function (s, i) {
      return '<span class="' + (st === 'closed' ? '' : i < idx ? 'done' : i === idx ? 'now' : '') + '">' + esc(s.label) + '</span>';
    }).join('<em>›</em>');
    var btns = '', note = '';
    if (st === 'closed') {
      chips = '<span class="closed">보고 대상 아님' + (ACC.c.status_reason ? ' — ' + esc(ACC.c.status_reason) : '') + '</span>';
      btns = '<button class="btn sm" type="button" data-acc-act="reopen">다시 열기</button>';
    } else if (st !== 'submitted') {
      var next = d.stages[idx + 1];
      var lock = st === 'detected' && d.target !== true;
      btns = '<button class="btn sm dark" type="button" data-acc-act="next"' + (lock ? ' disabled' : '') + '>다음 단계로 — ' + esc(next.label) + '</button>' +
        '<button class="btn sm" type="button" data-acc-act="close">보고 대상 아님으로 닫기</button>';
      if (st === 'detected') note = d.target === false ? '휴업 3일 미만 — 조사표 대상이 아니다. ‘보고 대상 아님으로 닫기’로 닫는다'
        : d.target === null ? '다음 단계로 넘기기는 재해 정보(휴업 예상일수 · 사망 여부)를 넣고 저장한 뒤에 열린다' : '조사표 대상 (사망 또는 휴업 3일 이상)';
      if (st === 'rep_check') note = '근로자대표(없으면 재해자)의 확인을 받고 넘긴다 — 시행규칙 제73조제3항';
    }
    $('acc-flow').innerHTML = '<div class="ac-flow">' + chips + '</div><div class="ac-flowbar"><span class="note">' + esc(note) + '</span><span class="btnrow">' + btns + '</span></div>';
    var has = !!d.files.form;
    ['form', 'report'].forEach(function (k) {
      var el = $('acc-st-' + k);
      el.className = 'st ' + (ACC.dirty ? 'w' : has ? 'ok' : 'w');
      el.textContent = ACC.dirty ? '고치는 중' : has ? '작성됨' : '초안 전';
    });
  }
  function accEdit(k, ph) {
    return '<dd class="edit" contenteditable="true" data-k="' + k + '" data-ph="' + esc(ph) + '">' + esc(ACC.c[k] || '') + '</dd>';
  }
  function accMeasureLines() {
    var ms = ACC.c.measures || [];
    return ms.length ? ms.map(function (m) { return '[' + esc(m.cat) + '] ' + esc(m.text) + (m.owner || m.due ? ' (' + esc([m.owner, m.due && m.due + '까지'].filter(Boolean).join(' · ')) + ')' : ''); }).join('<br>')
      : '<span class="d">사고조사보고서 탭의 재발방지 대책 표에서 넣는다</span>';
  }
  function renderAccDocs() {
    if (!ACC.d) return;
    var d = ACC.d, c = ACC.c, a = d.acc;
    var wd = '일월화수목금토'.charAt(new Date(a.date + 'T00:00').getDay());
    var when = esc(a.date + ' (' + wd + ') ' + (a.time || '')) + ' · ' + esc(d.place);
    var share = '<span class="share">공통</span>';
    var hand = '<dd class="blank">출력 후 손으로 작성 (개인 정보)</dd>';
    $('acc-form').innerHTML = '<div class="docsheet"><div class="dh"><b>산업재해조사표</b><span class="mono" style="font-size:12px;color:var(--ink-2)">' + esc(a.id) + '</span></div><dl>' +
      '<dt>발생 일시 · 장소' + share + '</dt><dd class="code">' + when + '</dd>' +
      '<dt>성명 · 주민번호 · 주소 · 연락처</dt>' + hand +
      '<dt>고용 · 근무 형태</dt><dd class="human">' + esc([c.employ, c.shift].filter(Boolean).join(' · ') || '—') + '</dd>' +
      '<dt>같은 종류 업무 근속기간' + share + '</dt><dd class="human">' + esc(c.tenure || '—') + '</dd>' +
      '<dt>상해 종류 · 부위</dt><dd class="human">' + esc([c.injury, c.body_part].filter(Boolean).join(' · ') || '—') + '</dd>' +
      '<dt>휴업 · 사망</dt><dd class="human">' + (c.lost_days === '' || c.lost_days == null ? '—' : '휴업 ' + esc(c.lost_days) + '일') + (c.fatal ? ' · 사망' : '') + '</dd>' +
      '<dt>재해관련 작업유형' + share + '</dt><dd class="human">' + esc(c.duty || '—') + '</dd>' +
      '<dt>재해발생 당시 상황' + share + '</dt>' + accEdit('narrative', '비워 두고 저장하면 관제 기록으로 초안을 만든다') +
      '<dt>재해발생 원인' + share + '</dt>' + accEdit('cause_text', '조사자가 쓴다 — 초안은 원인을 단정하지 않는다') +
      '<dt>재발방지 계획' + share + '</dt><dd class="human">' + accMeasureLines() + '</dd></dl></div>' +
      '<p class="note" style="margin-top:8px">Ⅰ. 사업장 정보는 사업장 정보 파일(site_profile.json)에서 채운다. 제출은 발생일부터 1개월 이내, 근로자대표의 확인을 받는다 (산업안전보건법 시행규칙 제73조).</p>';
    var photos = d.photos.map(function (p) {
      return '<figure><img alt="' + esc(p.caption) + '" src="/api/docs/acc/' + encodeURIComponent(a.id) + '/photo/' + p.i + '"><figcaption>사진 ' + (p.i + 1) + ' — ' + esc(p.caption) + '</figcaption></figure>';
    });
    while (photos.length < 2) photos.push('<figure><div class="noimg">관제 프레임이 없다 — 출력 후 사진을 붙인다</div><figcaption>사진 ' + (photos.length + 1) + '</figcaption></figure>');
    var ms = c.measures || [];
    var used = {}; ms.forEach(function (m) { if (m.lib_id) used[m.lib_id] = 1; });
    var prev = $('acc-report').querySelector('.ms-cand'), candOpen = prev ? prev.open : !ms.length;   // 후보를 고르는 동안 접히지 않게
    $('acc-report').innerHTML =
      '<div class="sec">1. 사고 개요 · 인적사항</div><div class="docsheet"><dl>' +
      '<dt>사고 일시 · 장소' + share + '</dt><dd class="code">' + when + '</dd>' +
      '<dt>부서 · 사고 종류' + share + '</dt><dd class="human">' + esc([c.dept, c.acc_type].filter(Boolean).join(' · ') || '—') + '</dd>' +
      '<dt>소속 · 직급 · 성명</dt>' + hand +
      '<dt>임무 · 근무기간' + share + '</dt><dd class="human">' + esc([c.duty, c.tenure && '해당 업무 ' + c.tenure].filter(Boolean).join(' · ') || '—') + '</dd></dl></div>' +
      '<div class="sec">2. 사고 내용 및 경위 <span class="note">육하원칙 · 사실만</span><span class="share">조사표 ‘재해발생 당시 상황’과 같은 문장</span></div>' +
      '<div class="docsheet"><dl><dt>경위</dt>' + accEdit('narrative', '비워 두고 저장하면 관제 기록으로 초안을 만든다') + '</dl></div>' +
      '<div class="ph4">' + photos.join('') + '</div>' +
      '<div class="sec">3. 원인분석 · 시정조치</div><div class="docsheet"><dl>' +
      '<dt>원인분석' + share + '</dt>' + accEdit('cause_text', '조사자가 쓴다 — 초안은 원인을 단정하지 않는다') +
      '<dt>시정(단기) 조치</dt>' + accEdit('short_action', '바로 한 조치 (예: 작업 중지 · 임시 휴게소 설치)') + '</dl></div>' +
      '<div class="sec">4. 재발방지 대책 <span class="share">조사표 Ⅳ 재발방지 계획으로 같이 들어감</span></div>' +
      '<div class="tbl"><table class="t ms-t"><thead><tr><th style="width:120px">구분</th><th>대책</th><th style="width:110px">담당</th><th style="width:135px">기한</th><th style="width:40px">이행</th><th style="width:36px"></th></tr></thead><tbody>' +
      (ms.length ? ms.map(function (m, i) {
        return '<tr><td><select data-ms="' + i + '" data-f="cat">' + ACC_CATS.map(function (k) { return opt(k, k, k === m.cat); }).join('') + '</select></td>' +
          '<td class="txt"><input data-ms="' + i + '" data-f="text" value="' + esc(m.text) + '"' + (m.legal ? ' title="' + esc(m.legal) + '"' : '') + '></td>' +
          '<td><input data-ms="' + i + '" data-f="owner" value="' + esc(m.owner || '') + '" placeholder="부서"></td>' +
          '<td><input type="date" data-ms="' + i + '" data-f="due" value="' + esc(m.due || '') + '"></td>' +
          '<td style="text-align:center"><input type="checkbox" data-ms="' + i + '" data-f="done"' + (m.done ? ' checked' : '') + ' aria-label="이행"></td>' +
          '<td><button class="btn sm" type="button" data-ms-del="' + i + '" aria-label="빼기">×</button></td></tr>';
      }).join('') : '<tr><td colspan="6" class="d">아래 후보에서 고르거나 직접 추가한다</td></tr>') +
      '</tbody></table></div>' +
      '<div class="btnrow" style="margin-top:8px"><button class="btn sm" type="button" data-ms-add>+ 직접 추가</button></div>' +
      '<details class="ms-cand"' + (candOpen ? ' open' : '') + '><summary>대책 후보 ' + d.candidates.length + '개 — 사고 종류 · 원인 분류로 추림, 법령 근거 표시 (prevention_library.json)</summary>' +
      (d.candidates.length ? '<ul>' + d.candidates.map(function (k, i) {
        return '<li>' + chip(k.cat, 'mute') + '<span>' + esc(k.text) + (k.legal ? '<small>' + (k.basis === '법정' ? '법정 · ' : '권고 · ') + esc(k.legal) + '</small>' : '<small>권고</small>') +
          (k.note ? '<small>' + esc(k.note) + '</small>' : '') + '</span><button class="btn sm" type="button" data-cand="' + i + '"' + (used[k.lib_id] ? ' disabled' : '') + '>' + (used[k.lib_id] ? '추가됨' : '추가') + '</button></li>';
      }).join('') + '</ul>' : '<p class="note" style="margin-top:6px">사고 종류를 고르고 저장하면 후보가 보인다.</p>') +
      '<p class="note" style="margin-top:6px">원인 분류를 바꾸고 저장하면 후보가 다시 추려진다. 후보 문장은 원인 분석에 맞게 고쳐 쓴다.</p></details>';
  }
  function renderAccFiles() {
    var d = ACC.d, f = d.files, a = d.acc;
    $('acc-files-sub').textContent = f.form ? a.id + ' · v' + f.ver + ' — 마지막으로 저장한 판' : '';
    $('acc-files').innerHTML = !f.form ? '<p class="empty">아직 만든 문서가 없다 — 재해 정보를 넣고 ‘저장하고 두 문서 초안 만들기’를 누른다.</p>' :
      '<div class="dl"><ul>' +
      '<li>' + ico('doc') + '<span><b>산업재해조사표</b> <span class="d">별지 제30호서식 (2025.10.1 개정) 원본 양식에 채움</span></span><span class="mono d">' + esc(f.form_name) + '</span><a class="btn sm" href="' + esc(f.form) + '" download>이것만 받기</a></li>' +
      '<li>' + ico('doc') + '<span><b>사고조사보고서</b> <span class="d">내부 양식 · 사진 ' + d.photos.length + '장 포함</span></span><span class="mono d">' + esc(f.report_name) + '</span><a class="btn sm" href="' + esc(f.report) + '" download>이것만 받기</a></li></ul>' +
      '<div class="big"><a class="btn dark" href="/api/docs/acc/' + encodeURIComponent(a.id) + '/zip" download>두 문서 한번에 받기 (.zip)</a>' +
      '<span class="note" style="text-align:center">산업재해_' + esc(a.id) + '_v' + esc(f.ver) + '.zip · 워드 2개</span></div></div>';
  }
  function accDirty() { if (!ACC.dirty) { ACC.dirty = true; renderAccFlow(); } }
  function accBody() {
    var b = {};
    ['dept', 'acc_type', 'injury', 'body_part', 'employ', 'shift', 'duty', 'tenure', 'lost_days'].forEach(function (k) { b[k] = $('acf-' + k).value.trim(); });
    b.fatal = $('acf-fatal').value === '1';
    b.causes = [].map.call($('acf-causes').querySelectorAll('input:checked'), function (x) { return x.value; });
    b.narrative = ACC.c.narrative || ''; b.cause_text = ACC.c.cause_text || ''; b.short_action = ACC.c.short_action || '';
    b.measures = ACC.c.measures || [];
    return b;
  }
  function accSave() {
    if (!ACC.d) return flash('고른 사고가 없다', true);
    var aid = ACC.d.acc.id;
    busy(this, api('/api/docs/acc/' + encodeURIComponent(aid) + '/save', accBody())).then(function (d) {
      renderAcc(d); flash('저장 — v' + d.files.ver + ' 두 문서를 새로 만들었다');
      return api('/api/docs/acc').then(function (l) { ACC.list = l; renderAccSteps(); fillAccSel(aid); });
    }).catch(fail);
  }
  function accStage(action, reason) {
    var aid = ACC.d.acc.id;
    return api('/api/docs/acc/' + encodeURIComponent(aid) + '/stage', {action: action, reason: reason || ''}).then(function (d) {
      renderAcc(d); flash('진행 상태 — ' + d.status_label);
      return api('/api/docs/acc').then(function (l) { ACC.list = l; renderAccSteps(); fillAccSel(aid); });
    });
  }
  $('acc-sel').addEventListener('change', function () {
    if (ACC.dirty && !window.confirm('저장하지 않은 내용이 있다. 다른 사고로 넘어갈까?')) { this.value = DOCS.acc; return; }
    showAcc(this.value);
  });
  $('acc-save').addEventListener('click', accSave);
  $('acc-save2').addEventListener('click', accSave);
  $('acc-steps').addEventListener('click', function (e) {
    var b = e.target.closest('[data-acc-stage]'); if (!b) return;
    var k = b.getAttribute('data-acc-stage');
    ACC.stage = ACC.stage === k ? '' : k;
    renderAccSteps();
    var want = fillAccSel(DOCS.acc);
    if (!want) emptyAcc(); else if (want !== (ACC.d && ACC.d.acc.id)) showAcc(want);
  });
  $('acc-flow').addEventListener('click', function (e) {
    var b = e.target.closest('[data-acc-act]'); if (!b || !ACC.d) return;
    if (ACC.dirty) return flash('먼저 ‘저장’을 누른다 — 저장하지 않은 내용이 있다', true);
    var act = b.getAttribute('data-acc-act');
    if (act === 'close') {
      ask({title: '보고 대상 아님으로 닫기', note: ACC.d.acc.id + ' — 오탐지이거나 휴업 3일 미만이면 산업재해조사표 대상이 아니다. 사유는 기록에 남는다.',
        fields: [{k: 'reason', label: '사유', req: true, ph: '예: 오탐지, 휴업 3일 미만'}]}, function (v) { return accStage('close', v.reason); });
      return;
    }
    busy(b, accStage(act)).catch(fail);
  });
  // 재해 정보 입력 — 고치면 '고치는 중'
  document.querySelector('[data-pane="docs:accident"] .fm').addEventListener('input', function (e) {
    var cb = e.target.closest('#acf-causes input'); if (cb) cb.parentElement.classList.toggle('on', cb.checked);
    if (ACC.d) accDirty();
  });
  // 문서 고치기 — 두 탭이 같은 내용을 쓴다 (ACC.c)
  ['acc-form', 'acc-report'].forEach(function (id) {
    $(id).addEventListener('input', function (e) {
      var k = e.target.getAttribute('data-k');
      if (k) { ACC.c[k] = e.target.innerText.replace(/\n$/, ''); accDirty(); return; }
      var i = e.target.getAttribute('data-ms');
      if (i !== null) {
        var f = e.target.getAttribute('data-f');
        ACC.c.measures[+i][f] = f === 'done' ? e.target.checked : e.target.value;
        accDirty();
      }
    });
    $(id).addEventListener('change', function (e) {
      if (e.target.getAttribute('data-ms') !== null) { var f = e.target.getAttribute('data-f'); ACC.c.measures[+e.target.getAttribute('data-ms')][f] = f === 'done' ? e.target.checked : e.target.value; accDirty(); }
    });
    $(id).addEventListener('click', function (e) {
      var del = e.target.closest('[data-ms-del]'), add = e.target.closest('[data-ms-add]'), cand = e.target.closest('[data-cand]');
      if (!del && !add && !cand) return;
      ACC.c.measures = ACC.c.measures || [];
      if (del) ACC.c.measures.splice(+del.getAttribute('data-ms-del'), 1);
      if (add) ACC.c.measures.push({cat: '관리적', text: '', owner: '', due: '', done: false});
      if (cand) {
        var k = ACC.d.candidates[+cand.getAttribute('data-cand')];
        ACC.c.measures.push({cat: k.cat, text: k.text, owner: '', due: '', done: false, lib_id: k.lib_id, legal: k.legal});
      }
      accDirty(); renderAccDocs();
      if (add) { var ins = $('acc-report').querySelectorAll('td.txt input'); if (ins.length) ins[ins.length - 1].focus(); }
    });
  });

  /* 관제 인계 */
  function loadHo(hid) {
    return api('/api/docs/handoff').then(function (d) {
      var want = hid || DOCS.hid || (d.handoffs[0] || {}).id;
      if (!d.handoffs.some(function (h) { return h.id === want; })) want = (d.handoffs[0] || {}).id;
      DOCS.hid = want;
      $('ho-sel').innerHTML = d.handoffs.map(function (h) {
        return opt(h.id, (h.replay ? '[재생 비교 검증본] ' : '') + h.id + ' · ' + h.source + ' · 감지 ' + h.n + '건' + (h.gates ? ' · 게이트 ' + h.gates : '') + (h.accidents ? ' · 사고 ' + h.accidents : ''), h.id === want);
      }).join('') || opt('', '넘어온 감지 내역이 아직 없다');
      $('ho-sub').textContent = d.handoffs.length + '회';
      if (want) return showHo(want);
      $('ho-info').textContent = '관제 화면에서 ‘문서 자동화로 넘기기’를 누르면 여기에 쌓인다. 관제 화면이 없을 때는 아래 ‘관제 엔진 결과 파일로 넘기기’로 엔진 결과를 바로 넣어 볼 수 있다.';
      $('ho-table').innerHTML = ''; $('ho-cand').innerHTML = '<p class="empty">인계 기록이 없다.</p>';
    }).catch(fail);
  }
  function showHo(hid) {
    DOCS.hid = hid;
    return api('/api/docs/handoff/' + encodeURIComponent(hid)).then(function (h) {
      $('ho-info').innerHTML = (h.replay ? tag('재생 비교 검증본', 'doc') + ' ' + esc(h.replay) + ' — 위험성평가 집계 · 의무 이행 · 기록(보존)에 들어가지 않는다<br>' : '') + esc(h.id + ' · ' + h.source + ' · 받은 시각 ' + h.ts + ' · 감지 ' + h.received + '건 받음 · 이미 받은 내역 ' + h.duplicates + '건 건너뜀 · 게이트 ' + h.gates.length + ' · 사고 ' + h.accidents.length + (h.warnings.length ? ' · ⚠ ' + h.warnings.join(' · ') : ''));
      $('ho-table').innerHTML = h.events.length ? '<table class="t" style="min-width:640px"><thead><tr><th>시각</th><th>번호</th><th>구역</th><th>모드</th><th>위반</th><th>판정</th><th>판정 근거</th></tr></thead><tbody>' +
        h.events.map(function (x) { return '<tr class="' + (x.alerted ? '' : 'shadow') + '"><td class="t">' + esc(x.t) + '</td><td class="t">' + esc(x.id) + '</td><td>' + z(x.zone) + '</td><td>' + esc(x.mode) + '</td><td>' + esc(x.type) + (x.frame ? ' <span class="rule">프레임</span>' : '') + '</td><td>' + lv(x.level, x.alerted) + '</td><td>' + esc(x.why) + '</td></tr>'; }).join('') + '</tbody></table>'
        : '<p class="empty">감지 기록이 없다 (게이트 · 사고만 넘어왔거나 이미 받은 내역).</p>';
      var nNew = h.corrective.filter(function (x) { return !x.issued; }).length;
      var c = '<div class="hcard' + (nNew ? ' crit' : '') + '"><div class="hd"><b>시정지시서 — 경보 이상 ' + h.corrective.length + '건</b>' + chip(nNew ? '미발행 ' + nNew : '해당 없음', nNew ? 'note' : 'ok') + '</div>' +
        (h.corrective.length ? '<div class="stack" style="gap:4px">' + h.corrective.map(function (x) { return '<label class="note" style="display:flex;gap:8px;align-items:center;color:var(--ink)"><input type="checkbox" data-ho-pick="' + esc(x.id) + '"' + (x.issued ? '' : ' checked') + '> ' + esc(x.t) + ' ' + esc(x.id) + ' · ' + esc(x.zone) + ' · ' + esc(x.type) + ' · ' + esc(x.level) + (x.frame ? ' · 프레임' : '') + (x.issued ? ' · 발행됨 ' + esc(x.issued) : '') + '</label>' +
          (x.issued ? '<button class="go" type="button" data-go="docs" data-tab="corrective" data-ev="' + esc(x.id) + '" style="margin-left:24px">✎ 고치기 →</button>' : ''); }).join('') + '</div>' +
          '<div class="btnrow"><button class="btn dark sm" type="button" id="ho-make">선택한 이벤트로 시정지시서 초안 만들기</button></div><div id="ho-made"></div>' : '') + '</div>';
      c += '<div class="hcard' + (h.adhoc.length ? ' crit' : ' soft') + '"><div class="hd"><b>수시 위험성평가 제안 ' + h.adhoc.length + '건</b><button class="go" type="button" data-go="docs" data-tab="ra">위험성평가로 →</button></div>' +
        (h.adhoc.length ? h.adhoc.map(function (a) { return '<p>' + z(a.zone) + ' ' + esc(a.mode) + ' · ' + esc(a.violation_type) + ' — 위험도 ' + a.score + ' ' + esc(a.grade) + ' · ' + esc(a.reasons.join(', ')) + '</p>'; }).join('') : '<p>기준(위험도 12 · 중대성 4)에 걸린 행 없음</p>') + '</div>';
      if (h.gates.length) c += '<div class="hcard"><div class="hd"><b>작업허가서 점검 — 작업 전 게이트 ' + h.gates.length + '건</b><button class="go" type="button" data-go="docs" data-tab="ptw">작업허가서 점검으로 →</button></div>' + h.gates.map(function (g) { return '<p>' + esc(g.t) + ' ' + z(g.zone) + ' ' + esc(g.type || '') + ' — ' + esc(g.reason) + '</p>'; }).join('') + '</div>';
      if (h.accidents.length) c += '<div class="hcard crit"><div class="hd"><b>산업재해조사표 — 사고 ' + h.accidents.length + '건</b><button class="go" type="button" data-go="docs" data-tab="accident">산업재해조사표로 →</button></div>' + h.accidents.map(function (a) { return '<p>' + esc(a.t) + ' ' + z(a.zone) + ' ' + esc(a.type || '') + ' — ' + esc(a.reason) + '</p>'; }).join('') + '<p class="note">사망 · 휴업 3일 이상이면 조사표 대상이다. 재해자 수 · 휴업일수는 사람이 넣는다.</p></div>';
      $('ho-cand').innerHTML = c;
    }).catch(fail);
  }
  $('ho-sel').addEventListener('change', function () { showHo(this.value); });
  $('ho-cand').addEventListener('click', function (e) {
    if (!e.target.closest('#ho-make')) return;
    var ids = []; document.querySelectorAll('[data-ho-pick]').forEach(function (c) { if (c.checked) ids.push(c.getAttribute('data-ho-pick')); });
    busy(e.target, api('/api/docs/handoff/' + encodeURIComponent(DOCS.hid) + '/make', {event_ids: ids})).then(function (d) {
      var ver = d.made.some(function (m) { return m.replay; });
      flash('시정지시서 초안 ' + d.made.length + '건 — ' + (ver ? '재생 비교 검증본 (의무 이행 · 기록에 올라가지 않는다)' : '발행 기록이 남고 의무 이행 관리에 조치 기한이 올라간다'));
      return showHo(DOCS.hid).then(function () {
        $('ho-made').innerHTML = '<div class="stack" style="gap:4px;margin-top:8px">' + d.made.map(function (m) { return '<div class="btnrow"><span class="mono">' + esc(m.doc_no) + '</span><span class="note">← ' + esc(m.event_id) + ' · 중대성 ' + m.severity + ' · 기한 ' + esc(m.deadline) + '</span>' + download(m.file, '워드') +
          '<button class="btn sm" type="button" data-go="docs" data-tab="corrective" data-ev="' + esc(m.event_id) + '">✎ 고치기</button></div>'; }).join('') + '</div>';
        tickStatus();
      });
    }).catch(fail);
  });
  $('ho-up').addEventListener('click', function () {
    var f = $('ho-file').files && $('ho-file').files[0];
    if (!f) { flash('관제 엔진 결과 파일(events.jsonl 또는 events_for_docgen.json)을 고른다', true); return; }
    var fd = new FormData(); fd.append('file', f); fd.append('base_dir', $('ho-base').value); fd.append('source', $('ho-src').value);
    busy(this, api('/api/docs/handoff/upload', fd)).then(function (d) { flash(d.msg); $('ho-file').value = ''; loadHo(d.handoff_id); }).catch(fail);
  });

  /* ---------- 10. 안전소통 ---------- */
  var VC = {sel: null, kind: null, state: null};
  var VS_K = {'접수': 'warn', '조치 중': 'info', '완료': 'ok'};
  function loadVoice() {
    return api('/api/voice').then(function (d) {
      var s = d.summary;
      $('vc-kpis').innerHTML = '<div class="kpi"><span>접수</span><b>' + s.total + '</b><small>최근 30일 ' + s.recent + '건</small></div>' +
        '<div class="kpi' + (s.open ? ' warn' : '') + '"><span>미조치</span><b>' + s.open + '</b><small>완료되지 않은 제보</small></div>' +
        '<div class="kpi"><span>조치 중</span><b>' + s.doing + '</b></div><div class="kpi"><span>완료</span><b>' + s.done + '</b><small>조치율 ' + s.rate + '%</small></div>';
      var cur = $('vc-ra').value;
      $('vc-ra').innerHTML = d.pending.map(function (r) { return opt(r.id, r.id + ' · ' + r.kind + ' · 관리자 서명 ' + r.manager + ' · ' + r.n + '행', r.id === cur); }).join('') || opt('', '근로자 확인 대기 평가가 없다');
      showVcRa();
      $('vc-list').innerHTML = d.reports.length ? '<table class="t" style="min-width:560px"><thead><tr><th>접수</th><th>구분</th><th>구역</th><th>내용</th><th>상태</th></tr></thead><tbody>' +
        d.reports.map(function (r) { return '<tr class="click' + (r.id === VC.sel ? ' sel' : '') + '" data-vc="' + esc(r.id) + '" title="' + esc((r.action ? '조치: ' + r.action : '') + (r.by ? ' · ' + r.by : '')) + '"><td class="t">' + esc(r.ts.slice(5, 10)) + '</td><td>' + esc(r.kind) + '</td><td>' + z(r.zone) + '</td><td>' + esc(r.text) + '</td><td>' + chip(r.state === '접수' ? '미조치' : r.state, VS_K[r.state]) + '</td></tr>'; }).join('') + '</tbody></table>'
        : '<p class="empty">제보가 없다.</p>';
      $('vc-upd').hidden = !VC.sel;
    }).catch(fail);
  }
  function showVcRa() {
    var id = $('vc-ra').value;
    if (!id) { $('vc-ra-rows').innerHTML = ''; return; }
    api('/api/voice/ra/' + encodeURIComponent(id)).then(function (r) {
      $('vc-ra-rows').innerHTML = (r.rule_rejected && r.rule_rejected.length ? '<div class="bar crit" style="margin:0 0 8px"><span>반려된 규칙 변경 ' + esc(r.rule_rejected.join(', ')) + ' — 확정해도 규칙셋에 올리지 않는다</span><span>관제 › 피드백 · 조정 로그</span></div>' : '') + '<table class="t"><thead><tr><th>유해위험요인</th><th>위험도</th><th>감소대책</th></tr></thead><tbody>' +
        r.rows.map(function (x) { return '<tr><td>' + z(x.zone) + ' ' + esc(x.hazard || x.mode) + '</td><td class="num">' + x.score + '</td><td style="white-space:pre-line">' + esc(x.measures) + '</td></tr>'; }).join('') + '</tbody></table>';
    }).catch(fail);
  }
  $('vc-ra').addEventListener('change', showVcRa);
  $('vc-ok').addEventListener('click', function () {
    busy(this, api('/api/voice/confirm', {ra_id: $('vc-ra').value, name: $('vc-by').value, note: $('vc-why').value})).then(function (d) { flash(d.msg); $('vc-why').value = ''; loadVoice(); tickStatus(); }).catch(fail);
  });
  $('vc-no').addEventListener('click', function () {
    busy(this, api('/api/voice/reject', {ra_id: $('vc-ra').value, name: $('vc-by').value, reason: $('vc-why').value})).then(function (d) { flash(d.msg); $('vc-why').value = ''; loadVoice(); tickStatus(); }).catch(fail);
  });
  $('vc-list').addEventListener('click', function (e) {
    var tr = e.target.closest('[data-vc]'); if (!tr) return;
    VC.sel = tr.getAttribute('data-vc');
    $('vc-upd-id').textContent = VC.sel + ' 상태';
    $('vc-list').querySelectorAll('tr[data-vc]').forEach(function (r) { r.classList.toggle('sel', r === tr); });
    $('vc-upd').hidden = false;
  });
  $('vc-state').addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) VC.state = b.getAttribute('data-v'); });
  $('vc-kind').addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) VC.kind = b.getAttribute('data-v'); });
  $('vc-upd-go').addEventListener('click', function () {
    busy(this, api('/api/voice/update', {id: VC.sel, state: VC.state, action: $('vc-act').value, by: $('vc-who').value})).then(function (d) { flash(d.msg); $('vc-act').value = ''; loadVoice(); tickStatus(); }).catch(fail);
  });
  $('vc-send').addEventListener('click', function () {
    busy(this, api('/api/voice/report', {kind: VC.kind, zone: $('vc-zone').value, text: $('vc-body').value, reporter: $('vc-rep').value})).then(function (d) { flash(d.msg); $('vc-body').value = ''; $('vc-rep').value = ''; loadVoice(); tickStatus(); }).catch(fail);
  });

  /* ---------- 11. 기록 ---------- */
  function loadArchive() {
    return api('/api/archive').then(function (d) {
      function stK(s) { return /확정|완료|이행/.test(s) ? 'ok' : /반려|대기|초안|보완/.test(s) ? 'note' : 'mute'; }
      $('ar-docs').innerHTML = d.docs.length ? d.docs.map(function (r) {
        return '<tr><td>' + esc(r['종류']) + '</td><td class="t">' + esc(r['번호']) + '</td><td class="t">' + esc(r['날짜']) + '</td><td>' + chip(r['상태'], stK(r['상태'])) + '</td><td>' + esc(r['근거 기록']) + '</td><td class="t" title="' + esc(r['보존 근거']) + '">' + esc(r['보존 기한']) + '</td><td>' + (r.url ? '<a class="go" href="' + esc(r.url) + '" download>내려받기</a>' : '—') + '</td></tr>';
      }).join('') : '<tr><td colspan="7" class="d">문서가 없다</td></tr>';
      $('ar-eff').innerHTML = d.effects.length ? d.effects.map(function (r) {
        var done = !/측정 중/.test(r['개선 후 (실측)']);
        return '<tr><td class="t">' + esc(r['평가 번호']) + '</td><td>' + z(r['구역']) + ' ' + esc(r['작업 모드']) + '</td><td>' + esc(r['위반 유형']) + '</td><td class="num">' + esc(r['개선 전 위험도']) + '</td><td>' + chip(r['개선 후 (실측)'], done ? 'ok' : 'mute') + '</td></tr>';
      }).join('') : '<tr><td colspan="5" class="d">확정된 평가가 아직 없다</td></tr>';
      $('ar-rules').innerHTML = d.rulesets.slice().reverse().map(function (r) {
        return '<tr><td class="t">v' + esc(r['버전']) + '</td><td class="t">' + esc(r['시각']) + '</td><td style="white-space:pre-line">' + esc(r['반영한 변경']) + '</td><td class="t">' + esc(r['근거 평가']) + (r['확정자'] && r['확정자'] !== '-' ? ' · ' + esc(r['확정자']) : '') + '</td></tr>';
      }).join('');
      $('ar-rev').innerHTML = d.revisions.length ? d.revisions.map(function (r) {
        return '<tr><td class="t">' + esc(r['시각']) + '</td><td class="t">' + esc(r['평가 번호']) + '</td><td>' + chip(r['상태'], r['상태'] === '확정' ? 'ok' : r['상태'] === '반려' ? 'warn' : 'note') + '</td><td>' + esc(r['서명·처리']) + (r['비고'] ? ' · ' + esc(r['비고']) : '') + '</td></tr>';
      }).join('') : '<tr><td colspan="4" class="d">기록 없음</td></tr>';
    }).catch(fail);
  }

  /* ---------- 11-2. 기록 › 산업재해 기록 (10/13) — 계산은 accident_case.py accident_stats() ---------- */
  var ACS_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6'];   // 순서 고정 — 색은 순위가 아니라 항목을 따른다
  function loadAccStats() {
    var q = 'months=' + $('acs-months').value + '&zone=' + encodeURIComponent($('acs-zone').value) + '&scope=' + $('acs-scope').value;
    return api('/api/accident-stats?' + q).then(renderAccStats).catch(fail);
  }
  function donut(items, center, sub, colors) {
    var total = items.reduce(function (s, x) { return s + x.n; }, 0);
    if (!total) return '<p class="empty">고른 기간 · 조건에 기록이 없다.</p>';
    var r = 54, sw = 22, c = 2 * Math.PI * r, off = 0, arcs = '';
    var col = function (x, i) { return x.other ? '#8b939d' : (colors || ACS_COLORS)[i % (colors || ACS_COLORS).length]; };
    items.forEach(function (x, i) {
      var len = x.n / total * c, seg = Math.max(len - (items.length > 1 ? 2 : 0), 0.5);
      arcs += '<circle class="seg" r="' + r + '" cx="70" cy="70" fill="none" stroke="' + col(x, i) + '" stroke-width="' + sw + '" stroke-dasharray="' + seg.toFixed(2) + ' ' + (c - seg).toFixed(2) + '" stroke-dashoffset="' + (-off).toFixed(2) + '"><title>' + esc(x.name) + ' ' + x.n + '건</title></circle>';
      off += len;
    });
    return '<div class="dn"><svg viewBox="0 0 140 140" class="dn-svg" role="img" aria-label="' + esc(sub) + '"><g transform="rotate(-90 70 70)"><circle r="' + r + '" cx="70" cy="70" fill="none" stroke="var(--panel-2)" stroke-width="' + sw + '"/>' + arcs + '</g>' +
      '<text x="70" y="68" class="dn-n">' + esc(center) + '</text><text x="70" y="86" class="dn-t">' + esc(sub) + '</text></svg>' +
      '<ul class="dn-leg">' + items.map(function (x, i) {
        return '<li><i style="background:' + col(x, i) + '"></i><span class="nm" title="' + esc(x.name) + '">' + esc(x.name) + '</span><span class="v">' + x.n + '</span><span class="p">' + Math.round(x.n / total * 100) + '%</span></li>';
      }).join('') + '</ul></div>';
  }
  function renderAccStats(d) {
    var k = d.kpis, m = d.period.months;
    var zSel = $('acs-zone'), zv = zSel.value;
    zSel.innerHTML = opt('', '전체') + d.zones.map(function (z) { return opt(z, z + ' ' + d.zone_names[z], z === zv); }).join('');
    var rk = Object.keys(d.run_kinds || {}).map(function (k) { return k + ' ' + d.run_kinds[k] + '건'; }).join(' · ');
    $('acs-upd').innerHTML = '데이터 기준 <span class="mono">' + esc(d.updated.replace('T', ' ')) + '</span>' +
      '<br><span class="note">데이터 공간 ' + esc(d.data_space || '') + (rk ? ' · 사고 기록 구분: ' + esc(rk) + ' — 시험 · 시연 기록은 실제 산업재해가 아니다' : '') + '</span>';
    function kpi(icon, label, num, extra, sub) {
      return '<div class="kpi st-kpi"><span class="st-ki">' + ico(icon) + '</span><span class="st-kt"><span>' + label + '</span><span class="st-num"><b>' + num + '</b>' +
        (extra ? '<span class="d">' + extra + '</span>' : '') + '</span><small>' + sub + '</small></span></div>';
    }
    $('acs-kpis').innerHTML = kpi('acc', '전체 사고', k.total, '직전 ' + m + '개월 ' + k.prev + '건', '관제 기록 + 사람 입력 · 최근 ' + m + '개월') +
      kpi('doc', '조사표 대상', k.target, '', '사망 또는 휴업 3일 이상') +
      kpi('doc', '조사표 제출 완료', k.submitted, '/ ' + k.target + '건', '진행 중인 건은 안전 문서 › 산업재해조사표') +
      kpi('ok', '재발방지 대책 이행률', k.rate == null ? '—' : k.rate + '%', k.measures ? k.done + ' / ' + k.measures + '개' : '', '기한 지난 미이행 ' + k.late + '개');
    // 월별 사고 추이 — 막대 하나 = 조사표 대상(아래) + 그 외(위)
    var mx = Math.max.apply(null, d.monthly.map(function (x) { return x.target + x.other; }).concat([1]));
    var cols = 'grid-template-columns:repeat(' + d.monthly.length + ',minmax(0,1fr))';
    $('acs-range').textContent = '발생일 기준 · ' + d.period.label;
    $('acs-month').innerHTML = '<div class="ac-month" style="' + cols + '">' + d.monthly.map(function (x) {
      var n = x.target + x.other;
      return '<div class="ac-col" title="' + esc(x.month) + ' · 조사표 대상 ' + x.target + ' · 그 외 ' + x.other + '"><span class="n">' + (n || '') + '</span><span class="ac-stack" style="height:' + (n / mx * 85).toFixed(0) + '%">' +
        (x.target ? '<i class="tg" style="flex:' + x.target + '"></i>' : '') + (x.other ? '<i class="ot" style="flex:' + x.other + '"></i>' : '') + '</span></div>';
    }).join('') + '</div><div class="ac-mlab" style="' + cols + '">' + d.monthly.map(function (x, i) {
      return '<span' + (i === d.monthly.length - 1 ? ' class="cur"' : '') + '>' + esc(x.label) + '</span>';
    }).join('') + '</div>';
    $('acs-zones').innerHTML = donut(d.by_zone, k.total, '건');
    $('acs-types').innerHTML = donut(d.by_type, k.total, '건');
    var nc = d.by_cause.reduce(function (s, x) { return s + x.n; }, 0);
    $('acs-cause-sub').textContent = '원인 분석이 끝난 ' + d.cause_cases + '건';
    $('acs-causes').innerHTML = donut(d.by_cause, nc, '원인 항목');
    $('acs-m-sub').textContent = '대책 ' + k.measures + '개';
    $('acs-measures').innerHTML = donut(d.measure_parts.filter(function (x) { return x.n; }).map(function (x) { return x; }),
      k.rate == null ? '—' : k.rate + '%', '이행 완료', d.measure_parts.filter(function (x) { return x.n; }).map(function (x) {
        return {'이행 완료': 'var(--ok)', '진행 중': 'var(--a)', '기한 지남': 'var(--crit)'}[x.name];
      }));
    $('acs-late-sub').textContent = d.late.length + '개 · 오래된 순';
    $('acs-late').innerHTML = d.late.length ? '<table class="t"><thead><tr><th>사고</th><th>분류</th><th>대책</th><th>담당</th><th class="num">기한</th></tr></thead><tbody>' +
      d.late.map(function (x) {
        return '<tr class="click" data-go="docs" data-tab="accident" data-acc="' + esc(x.acc) + '" title="산업재해조사표에서 열기"><td class="t">' + esc(x.acc) + '</td><td>' + chip(x.cat, 'mute') + '</td><td>' + esc(x.text) + '</td><td>' + esc(x.owner || '—') + '</td><td class="num"><span class="dday crit">+' + x.over + '일</span></td></tr>';
      }).join('') + '</tbody></table>' : '<p class="empty">기한 지난 미이행 대책이 없다.</p>';
  }
  $('acs-apply').addEventListener('click', function () { busy(this, loadAccStats()); });
  $('acs-reset').addEventListener('click', function () { $('acs-months').value = '12'; $('acs-zone').value = ''; $('acs-scope').value = 'all'; busy(this, loadAccStats()); });

  /* ---------- 확인 창 (이름 · 사유) ---------- */
  var askCb = null;
  /* ---------- 탐지 신뢰도 (10/8) — 판정 기준표 · 안전 영향 · 미탐 기록 · 성능 평가 · 변경 이력 ----------
     미탐 등록 창은 실시간 관제(카메라 칸) · 이벤트 로그(목록 위) · 이 화면에서 같이 쓴다 */
  var QS = {d: null, edit: false};
  function nowText() { var t = (LIVE && LIVE.sid ? LIVE.now : (STATUS && STATUS.now)) || new Date().toISOString(); return t.slice(0, 19).replace('T', ' '); }
  function missedForm(pre) {
    pre = pre || {};
    // 영상이 도는 중이면 창을 여는 순간 화면을 고정한다 (10/8 오후) — 일어난 시각을 그대로 두면 이 그림이 이미지 로그로 남는다
    if (pre.snap === undefined && LIVE && LIVE.sid && LIVE.video) {
      api('/api/live/snapshot', {purpose: 'miss'}).catch(function () { return {}; }).then(function (sn) {
        missedForm(Object.assign({}, pre, {snap: sn.snap_id ? sn : null, ts: pre.ts || (sn.made_at ? sn.made_at.replace('T', ' ') : undefined)}));
      });
      return;
    }
    var sn = pre.snap || null;
    // 처리 방식 (10/8 오후) — 세션이 돌고 일어난 시각이 지금(2분 안)이면 '지금 판정에 반영', 지난 일이면 '증거 저장', 세션이 없으면 '기록만'
    var live = !!(LIVE && LIVE.sid), ts = pre.ts || nowText();
    var gap = Math.abs(new Date(nowText().replace(' ', 'T')) - new Date(ts.replace(' ', 'T'))) / 1000;
    var defAct = !live ? 'record' : gap <= 120 ? 'now' : 'evidence';
    var acts = (META.miss_actions || []).filter(function (x) { return live || x.v === 'record'; });
    ask({title: '미탐 등록 — 시스템이 놓친 것',
      html: sn && sn.has_frame ? logPreview(sn.snap_id, 'now', false, (sn.made_at ? sn.made_at.slice(11, 19) + ' (창을 연 순간)' : '') + ' — 일어난 시각을 그대로 두면 이대로 남는다. 시각을 바꾸면 그 시각에 가장 가까운 원본으로 남는다')
        : '<p class="note logpv-none">영상이 돌지 않아 이미지 로그가 남지 않는다 — 실시간 관제에서 영상이 도는 중에 등록하면 그 순간 그림이 남는다.</p>',
      note: '영상에 있었는데 시스템이 잡지 못한 것을 남기고, 어떻게 처리할지 고른다. 지금 판정에 반영하면 불꽃은 점화원 신호가, 사람 · 보호구는 위반 기록(경보)이 들어간다. 원본 관제 기록은 고치지 않는다.' + (pre.scene ? ' 영상 장면 ‘' + pre.scene + '’' + (pre.video_t != null ? ' ' + fmtSec(pre.video_t) : '') + ' 에 묶인다.' : '') + (live ? '' : ' 세션이 돌지 않아 기록만 할 수 있다.'),
      fields: [{k: 'det', label: '놓친 탐지', options: META.dets.map(function (d) { return {v: d.key, t: d.label}; }), value: pre.det || 'person'},
               {k: 'zone', label: '구역', options: META.zones.map(function (x) { return {v: x.id, t: x.id + ' ' + x.name}; }), value: pre.zone || META.focus_zone},
               {k: 'ts', label: '일어난 시각', req: true, value: ts, ph: '2026-10-08 14:05:30'},
               {k: 'action', label: '처리', options: acts, value: defAct},
               {k: 'note', label: '무엇을 놓쳤나', area: true, ph: '예: 위험구역 오른쪽 끝에 서 있던 작업자를 못 잡음 · 역광'},
               {k: 'by', label: '등록자', req: true}]}, function (v) {
      return api('/api/missed', {det: v.det, zone: v.zone, ts: v.ts, note: v.note, by: v.by, action: v.action, snap_id: sn ? sn.snap_id : '', sid: pre.sid || '', scene: pre.scene || '', video_t: pre.video_t})
        .then(function (d) { flash(d.msg); if (curScreen === 'quality') loadQuality(); if (curScreen === 'stats') loadStats(); if (curScreen === 'live') loadLive(); });
    });
  }
  $('cam-miss').addEventListener('click', function () {
    missedForm({zone: curZone, sid: LIVE && LIVE.sid, scene: LIVE && LIVE.video && LIVE.scene ? LIVE.scene.name : '',
                video_t: LIVE && LIVE.video && LIVE.video_pos ? LIVE.video_pos[0] : null});
  });
  $('log-miss').addEventListener('click', function () {
    var zf = applied && applied.zone && applied.zone !== '전체' ? applied.zone : '';
    missedForm({zone: zf || META.focus_zone});
  });
  $('qm-add').addEventListener('click', function () { missedForm({}); });
  function loadQuality() { return api('/api/quality').then(function (d) { QS.d = d; renderQuality(); }).catch(fail); }
  function fmtV(c) {
    if (c.value === null || c.value === undefined) return '<span class="note">설정 없음</span>';
    return '<b class="mono">' + esc(String(c.value)) + '</b>' + (c.unit ? ' <small class="d">' + esc(c.unit) + '</small>' : '');
  }
  function renderQuality() {
    var d = QS.d;
    $('qc-edit').hidden = QS.edit; $('qc-save').hidden = !QS.edit; $('qc-cancel').hidden = !QS.edit;
    var last = '';
    $('qc-table').innerHTML = '<table class="t qc"><thead><tr><th>탐지</th><th>항목</th><th>지금 값</th><th>뜻</th><th>이 값을 고른 이유</th></tr></thead><tbody>' +
      d.criteria.map(function (c) {
        var head = c.det_t !== last; last = c.det_t;
        var val = QS.edit && c.edit ? '<input class="qc-in mono" type="number" data-qk="' + esc(c.key) + '" value="' + esc(String(c.value === null ? '' : c.value)) + '" min="' + c.min + '" max="' + c.max + '" step="' + c.step + '" aria-label="' + esc(c.label) + '">' +
            '<small class="d" style="display:block">' + c.min + ' ~ ' + c.max + '</small>'
          : fmtV(c) + (QS.edit && !c.edit ? '<small class="d" style="display:block">화면에서 못 고침</small>' : '');
        return '<tr' + (head ? ' class="qc-g"' : '') + '><td>' + (head ? '<b>' + esc(c.det_t) + '</b>' : '') + '</td><td>' + esc(c.label) + '</td><td class="qc-v">' + val + '</td>' +
          '<td class="d">' + esc(c.means) + '</td><td class="d">' + esc(c.why) + '</td></tr>';
      }).join('') + '</tbody></table>';
    $('qi-table').innerHTML = '<table class="t qi"><thead><tr><th>탐지</th><th>놓치면 (미탐)</th><th>잘못 울리면 (오탐)</th><th>먼저 줄일 쪽</th><th>그래서 이렇게 잡았다</th></tr></thead><tbody>' +
      d.impact.map(function (x) {
        return '<tr><td><b>' + esc(x.det_t) + '</b></td><td>' + esc(x.miss) + '</td><td>' + esc(x.false) + '</td>' +
          '<td><span class="lv ' + (x.prefer === '미탐 줄이기' ? 'crit' : 'warn') + '">' + esc(x.prefer) + '</span></td><td class="d">' + esc(x.how) + '</td></tr>';
      }).join('') + '</tbody></table>';
    var sg = d.suggest || [];          // 기준 조정 제안 (10/8 오후) — 미탐 · 탐지 오탐이 쌓이면
    $('qs-suggest').hidden = !sg.length;
    $('qs-suggest').innerHTML = sg.length ? '<b>판정 기준 조정 제안</b> <span class="note">판정 기준표에서 사람이 사유를 적고 바꾼다</span>' + sg.map(function (x) {
      return '<div class="qs-row"><span class="lv ' + (x.kind === 'missed' ? 'crit' : 'warn') + '">' + (x.kind === 'missed' ? '미탐' : '오탐') + ' ' + x.n + '</span> ' + esc(x.text) + '</div>';
    }).join('') : '';
    var fps = d.det_fp || [];
    $('qf-n').textContent = fps.length + '건';
    $('qf-list').innerHTML = fps.length ? '<div class="qm-rows">' + fps.map(function (r) {
      return '<div class="qm-row qm-img"><span class="mono qm-t" title="탐지된 시각">' + esc((r.seen_at || r.ts).replace('T', ' ').slice(5, 19)) + '</span>' + thumbs(r.images) +
        '<span><b>' + esc(r.target) + '</b> · ' + esc(r.zone + ' ' + (r.zname || '')) + ' · ' + esc(r.cat) +
        (r.scene ? ' · <span class="note">' + esc(r.scene) + (r.seen_t != null ? ' ' + fmtSec(r.seen_t) : '') + '</span>' : '') +
        '<small class="d" style="display:block">고른 시각 ' + esc(r.ts.replace('T', ' ').slice(5, 19)) + ' · 판정: ' + esc(r.action_label || r.scope) + (r.confirmed_alarm ? ' · ' + esc(r.confirmed_alarm) + ' 중 확인' : '') + (r.note ? ' · ' + esc(r.note) : '') + '</small></span>' +
        '<span class="note">' + esc(r.by) + '</span><button class="btn sm" type="button" data-qf-undo="' + esc(r.dfp_id) + '">취소</button></div>';
    }).join('') + '</div>' : '<p class="empty">탐지 오탐 기록이 없다 — 실시간 관제 카메라 칸의 탐지 오탐으로 고르면 여기 남는다.</p>';
    $('qm-n').textContent = d.missed.length + '건';
    $('qm-list').innerHTML = d.missed.length ? '<div class="qm-rows">' + d.missed.map(function (m) {
      return '<div class="qm-row qm-img"><span class="mono qm-t">' + esc(m.ts.replace('T', ' ').slice(5, 19)) + '</span>' + thumbs(m.images) +
        '<span><b>' + esc(m.det_t) + '</b> · ' + esc(m.zone + ' ' + m.zname) + (m.scene ? ' · <span class="note">' + esc(m.scene) + (m.video_t != null ? ' ' + fmtSec(m.video_t) : '') + '</span>' : '') +
        (m.note ? '<small class="d" style="display:block">' + esc(m.note) + '</small>' : '') +
        '<small class="d" style="display:block">처리: ' + esc(m.action_label || '기록만') + (m.result ? ' — ' + esc(m.result) : '') +
          (m.clip_path ? ' · 클립 ' + esc(m.clip_path.split('/').pop()) : '') + (m.frame_path && !m.clip_path ? ' · 프레임 ' + esc(m.frame_path.split('/').pop()) : '') +
          (m.error ? ' · <b style="color:var(--crit)">처리 실패: ' + esc(m.error) + '</b>' : '') + '</small></span>' +
        '<span class="note">' + esc(m.by) + '</span><button class="btn sm" type="button" data-qm-undo="' + esc(m.miss_id) + '">취소</button></div>';
    }).join('') + '</div>' : '<p class="empty">등록된 미탐이 없다 — 영상에서 놓친 것이 보이면 실시간 관제의 카메라 칸 · 이벤트 로그 · 여기서 등록한다.</p>';
    function pct(v) { return v === null || v === undefined ? '-' : (v * 100).toFixed(1) + '%'; }
    $('qe-list').innerHTML = (d.reports.length ? d.reports.map(function (r) {
      return '<div class="qe-r"><div class="qe-h"><b>' + esc(r.label) + '</b> <span class="note">' + esc(r.video) + ' · ' + esc(r.camera || '') + ' · 정답 ' + esc(r.truth) + ' · ' + esc(r.created.replace('T', ' ').slice(0, 16)) + '</span></div>' +
        '<table class="t qe"><thead><tr><th>항목</th><th class="num">정밀도</th><th class="num">재현율</th><th class="num">오탐률</th><th class="num">미탐률</th><th>그 밖</th></tr></thead><tbody>' +
        r.items.filter(function (x) { return x.samples; }).map(function (x) {
          return '<tr><td>' + esc(x.label) + '</td><td class="num mono">' + pct(x.precision) + '</td><td class="num mono">' + pct(x.recall) + '</td><td class="num mono">' + (x.kind === 'binary' ? pct(x.fp_rate) : '-') + '</td><td class="num mono">' + pct(x.miss_rate) + '</td>' +
            '<td class="d">' + (x.kind === 'count' ? '평균 오차 ' + x.mae + '명' : (x.spans ? '구간 ' + x.spans_hit + '/' + x.spans + ' · 첫 탐지 ' + (x.delay_avg === null ? '-' : x.delay_avg + '초') : '')) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }).join('') : '<p class="empty">아직 평가 결과가 없다.</p>') +
      '<div class="st-notice" style="margin-top:10px">' + ico('info') + '<span><b>정답을 적고 채점한다</b>' +
      '① 양식 만들기 — <code>cd monitor_engine</code> 뒤 <code>python evaluate.py steel_pickling V_영상점검 --scene 장면이름 --template 정답/장면이름.csv</code><br>' +
      '② 엑셀로 구간마다 사람 수 · 안전모 · 조끼 미착용 수 · 불꽃(1/0) · 위험구역 안 사람(1/0)을 적는다 (모르는 칸은 비운다)<br>' +
      '③ 채점 — <code>python evaluate.py steel_pickling V_영상점검 --scene 장면이름 --truth 정답/장면이름.csv</code> · 기준을 바꿔 비교하려면 <code>--set person.conf=0.3 --label "기준 0.3"</code></span></div>';
    $('qh-list').innerHTML = d.history.length ? '<table class="t"><thead><tr><th>시각</th><th>항목</th><th>바꾸기 전 → 후</th><th>변경자</th><th>이유</th></tr></thead><tbody>' +
      d.history.map(function (h) {
        return '<tr><td class="mono">' + esc(h.ts.replace('T', ' ').slice(0, 16)) + '</td><td>' + esc(h.label) + '</td><td class="mono">' + esc(String(h.old)) + ' → <b>' + esc(String(h.new)) + '</b></td><td>' + esc(h.by) + '</td><td class="d">' + esc(h.reason) + '</td></tr>';
      }).join('') + '</tbody></table>' : '<p class="empty">아직 바꾼 기준이 없다 — 위 판정 기준표의 ‘기준 고치기’로 바꾸면 여기에 남는다.</p>';
  }
  $('qc-edit').addEventListener('click', function () { QS.edit = true; renderQuality(); });
  $('qc-cancel').addEventListener('click', function () { QS.edit = false; renderQuality(); });
  $('qc-save').addEventListener('click', function () {
    var ch = {}, n = 0;
    $('qc-table').querySelectorAll('[data-qk]').forEach(function (el) {
      var c = QS.d.criteria.filter(function (x) { return x.key === el.getAttribute('data-qk'); })[0];
      if (el.value !== '' && String(c.value) !== el.value && +el.value !== c.value) { ch[c.key] = el.value; n++; }
    });
    if (!n) { flash('바뀐 값이 없다'); QS.edit = false; renderQuality(); return; }
    ask({title: '판정 기준 바꾸기 — ' + n + '개', note: '사업장 패키지 detect.json 에 저장하고 변경 이력에 남긴다. 새 세션(영상 다시 재생)부터 적용된다. 바꾼 뒤에는 같은 정답으로 다시 채점해 개선됐는지 확인한다.',
      fields: [{k: 'by', label: '변경자', req: true}, {k: 'reason', label: '바꾸는 이유', area: true, req: true, ph: '예: 역광 영상에서 사람 미탐 3건 — 기준을 낮춘다'}]}, function (v) {
      return api('/api/quality/criteria', {changes: ch, by: v.by, reason: v.reason}).then(function (d) { flash(d.msg); QS.edit = false; return loadQuality(); });
    });
  });
  $('qf-list').addEventListener('click', function (e) {
    var b = e.target.closest('[data-qf-undo]'); if (!b) return;
    var id = b.getAttribute('data-qf-undo');
    ask({title: '탐지 오탐 기록 취소 — ' + id, note: '잘못 고른 것으로 한다(취소한 기록은 남는다). 실시간 관제에서 아직 빼고 있으면 그것도 멈춘다.', fields: [{k: 'by', label: '취소한 사람', req: true}]}, function (v) {
      return api('/api/det-fp/undo', {dfp_id: id, by: v.by}).then(function (r) { flash(r.msg); return loadQuality(); });
    });
  });
  $('qm-list').addEventListener('click', function (e) {
    var b = e.target.closest('[data-qm-undo]'); if (!b) return;
    var id = b.getAttribute('data-qm-undo');
    ask({title: '미탐 등록 취소 — ' + id, note: '등록을 없던 것으로 한다(취소한 기록은 남는다).', fields: [{k: 'by', label: '취소한 사람', req: true}]}, function (v) {
      return api('/api/missed/undo', {miss_id: id, by: v.by}).then(function (d) { flash(d.msg); return loadQuality(); });
    });
  });
  /* 오탐 · 미탐 이미지 로그 썸네일 (10/8) — 누르면 원본 · 관제 화면을 새 창으로 */
  function thumbs(im) {
    if (!im) return '<span class="qthumbs"></span>';
    var u = function (p) { return '/api/' + p; };
    var main = im.crop || im.view || im.raw;
    return '<span class="qthumbs"><a href="' + esc(u(im.view || main)) + '" target="_blank" rel="noopener" title="관제 화면 크게 보기"><img class="qthumb" loading="lazy" alt="" src="' + esc(u(main)) + '"></a>' +
      (im.raw ? '<a class="d" href="' + esc(u(im.raw)) + '" target="_blank" rel="noopener" title="표시 없는 원본 — 학습용">원본</a>' : '') + '</span>';
  }
  /* 히트맵 · 통계의 오탐 · 미탐 칸 */
  function renderQualStats(q) {
    if (!q) return;
    function cf(v) { return v === null ? '<span class="d">-</span>' : '<span class="mono">' + v.toFixed(2) + '</span>'; }
    $('st-qual').innerHTML = '<table class="t st-mt"><thead><tr><th>탐지</th><th class="num">탐지 기록</th><th class="num">오탐 표시</th><th class="num">오탐률</th><th class="num">미탐 등록</th><th class="num" title="실시간 관제에서 탐지 하나를 오탐으로 고른 수 — 이벤트 기록 전 단계라 오탐률에는 안 넣는다">탐지 오탐</th><th class="num" title="근거 탐지의 모델 점수 평균">평균 신뢰도 정상 / 오탐</th></tr></thead><tbody>' +
      q.rows.map(function (r) {
        return '<tr><td>' + esc(r.label) + '</td><td class="num mono">' + r.n + '</td><td class="num mono">' + r.fp + '</td>' +
          '<td class="num">' + (r.fp_rate === null ? '<span class="d">-</span>' : '<b class="mono">' + r.fp_rate + '%</b>') + '</td>' +
          '<td class="num mono">' + r.missed + (r.missed_prev ? ' <small class="d">직전 ' + r.missed_prev + '</small>' : '') + '</td>' +
          '<td class="num mono">' + (r.det_fp || 0) + '</td>' +
          '<td class="num">' + cf(r.conf_ok) + ' / ' + cf(r.conf_fp) + '</td></tr>';
      }).join('') + '</tbody></table>';
    var mx = Math.max.apply(null, q.reasons.map(function (x) { return x.n; }).concat([1]));
    $('st-qual-why').innerHTML = '<div class="ph" style="margin:0 0 6px"><h2 style="font-size:13px">오탐 사유</h2><span class="sub">이벤트 로그 · 실시간 탐지 오탐에서 고른 사유</span></div>' +
      (q.reasons.length ? '<div class="hbars">' + q.reasons.map(function (x) { return '<div class="hb"><span>' + esc(x.reason) + '</span><div class="tr"><i style="width:' + (x.n / mx * 100).toFixed(0) + '%"></i></div><b>' + x.n + '건</b></div>'; }).join('') + '</div>'
        : '<p class="empty">고른 기간에 오탐 표시가 없다</p>');
  }

  /* 입력 창 — fields: [{k, label, req, area, secret, ph, value, options: ['값' 또는 {v, t}], show: {k: '다른 칸', v: '그 값'}}]
     show 가 있으면 그 칸이 그 값일 때만 보이고, 숨은 칸은 필수 검사를 하지 않는다 (10/8 — 오탐 사유 '기타') */
  function ask(o, cb) {
    $('ask-h').textContent = o.title; $('ask-note').textContent = o.note || '';
    // o.img — 창 위에 그림 한 장 (10/8 — 탐지 오탐: 창을 연 순간의 영상 프레임. 번호를 보고 고른다)
    // o.html — 창 위에 넣을 묶음 (10/8 — 등록 창의 '저장될 이미지 로그' 미리 보기)
    $('ask-fields').innerHTML = (o.html || '') + (o.img ? '<img class="ask-img" alt="' + esc(o.imgAlt || '') + '" src="' + esc(o.img) + '">' : '') + o.fields.map(function (f) {
      var v = f.k === 'actor' || f.k === 'by' ? (store('actor') || '') : (f.value || '');
      var ctl = f.options ? '<select id="askf-' + f.k + '" data-k="' + f.k + '">' + f.options.map(function (x) {
          var xv = typeof x === 'object' ? x.v : x, xt = typeof x === 'object' ? x.t : x;
          return opt(xv, xt, xv === f.value);
        }).join('') + '</select>'
        : f.area ? '<textarea id="askf-' + f.k + '" data-k="' + f.k + '"' + (f.req ? ' data-req="1"' : '') + (f.ph ? ' placeholder="' + esc(f.ph) + '"' : '') + '>' + esc(v) + '</textarea>'
        : '<input id="askf-' + f.k + '" data-k="' + f.k + '"' + (f.secret ? ' type="password" autocomplete="off"' : '') + (f.ph ? ' placeholder="' + esc(f.ph) + '"' : '') + (f.req ? ' data-req="1"' : '') + ' value="' + esc(v) + '">';
      return '<div class="field"' + (f.show ? ' data-show-k="' + f.show.k + '" data-show-v="' + esc(f.show.v) + '"' : '') + '><label for="askf-' + f.k + '">' + esc(f.label) + '</label>' + ctl + '</div>';
    }).join('');
    askShow();
    $('ask-err').hidden = true; askCb = cb; $('ask').hidden = false;
    var first = $('ask-fields').querySelector('input,textarea,select'); if (first) first.focus();
  }
  function askShow() {
    $('ask-fields').querySelectorAll('[data-show-k]').forEach(function (w) {
      var src = $('askf-' + w.getAttribute('data-show-k'));
      w.hidden = !src || src.value !== w.getAttribute('data-show-v');
    });
  }
  $('ask-fields').addEventListener('change', askShow);
  function closeAsk() { $('ask').hidden = true; askCb = null; }
  $('ask-close').addEventListener('click', closeAsk);
  $('ask-cancel').addEventListener('click', closeAsk);
  $('ask').addEventListener('click', function (e) { if (e.target === this) closeAsk(); });
  $('ask-ok').addEventListener('click', function () {
    var v = {}, miss = null;
    $('ask-fields').querySelectorAll('[data-k]').forEach(function (el) {
      var hid = el.closest('.field').hidden;
      v[el.getAttribute('data-k')] = hid ? '' : el.value.trim();
      if (!hid && el.getAttribute('data-req') && !el.value.trim() && !miss) miss = el;
    });
    if (miss) { $('ask-err').textContent = '필수 칸을 채운다.'; $('ask-err').hidden = false; miss.focus(); return; }
    if (v.actor || v.by) store('actor', v.actor || v.by);
    var btn = this;
    busy(btn, askCb(v)).then(closeAsk).catch(function (e) { $('ask-err').textContent = e.message; $('ask-err').hidden = false; });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (!$('ask').hidden) closeAsk(); else if (ISO.sheet) closeSheet();
    else if (!$('scn').hidden && !SC.draw && !SC.dirty) closeScene();   // 그리던 것이 있으면 Esc 로 닫지 않는다
  });

  /* ---------- 화면 전환 (시안 그대로) ---------- */
  var screens = document.querySelectorAll('.screen'), links = document.querySelectorAll('.nav a[data-go]');
  var LOADERS = {live: loadLive, iso: function (o) { return loadIso(o && o.ptw); }, log: function (o) { return loadLog(o); }, replay: function () { return loadReplay(); },
    feedback: loadFb, stats: loadStats, quality: loadQuality, home: loadHome, duty: loadDuty, voice: loadVoice,
    archive: function () { var on = document.querySelector('.subtabs[data-group="arc"] button.on'); return on && on.getAttribute('data-tab') === 'acc' ? loadAccStats() : loadArchive(); },
    docs: function (o) { var t = (o && o.tab) || DOCS.tab; pickTabOnly('docs', t); return loadDocTab(t, o || {}); }};
  function pickTabOnly(group, tab) {
    var bar = document.querySelector('.subtabs[data-group="' + group + '"]'); if (!bar) return;
    bar.querySelectorAll('button').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-tab') === tab); });
    document.querySelectorAll('[data-pane^="' + group + ':"]').forEach(function (p) { p.hidden = p.getAttribute('data-pane') !== group + ':' + tab; });
  }
  /* ---------- 데이터 공간 (10/14) — 조회 공간과 새 세션 저장 공간을 따로 고른다 ---------- */
  var DS = null;
  function dsLabel(k) { var s = DS && DS.spaces.filter(function (x) { return x.key === k; })[0]; return s ? s.label : k; }
  function dsInfo(k) { return DS && DS.spaces.filter(function (x) { return x.key === k; })[0]; }
  function renderDS() {
    var b = $('dsbar'); if (!b || !DS) return;
    var v = DS.view, w = DS.write, ses = DS.session;
    var vOpts = DS.spaces.map(function (s) { return '<option value="' + esc(s.key) + '"' + (s.key === v ? ' selected' : '') + (s.connected ? '' : ' disabled') + '>' + esc(s.label + (s.connected ? '' : ' — 폴더 연결 안 됨')) + '</option>'; }).join('');
    var wOpts = DS.spaces.map(function (s) { var ok = s.accept_new_sessions; return '<option value="' + esc(s.key) + '"' + (s.key === w ? ' selected' : '') + (ok ? '' : ' disabled') + '>' + esc(s.label + (ok ? '' : ' — 새 기록 받지 않음')) + '</option>'; }).join('');
    var kOpts = DS.run_kinds.map(function (k) { return '<option' + (k === DS.write_run_kind ? ' selected' : '') + '>' + esc(k) + '</option>'; }).join('');
    var miss = DS.spaces.filter(function (s) { return !s.connected; });
    b.innerHTML = '<span class="ds-k">조회</span><select id="ds-view" aria-label="조회할 데이터 공간">' + vOpts + '</select>' +
      '<span class="ds-k">새 세션 저장</span><select id="ds-write" aria-label="새 세션을 저장할 데이터 공간">' + wOpts + '</select>' +
      '<select id="ds-kind" aria-label="시험 · 운영 · 시연 구분">' + kOpts + '</select>' +
      '<span class="ds-path mono" title="새 세션 저장 경로">' + esc((dsInfo(w) || {}).root || '') + '</span>' +
      (ses ? '<span class="ds-ses">지금 세션 <b class="mono">' + esc(ses.sid) + '</b> → ' + esc(ses.label) + ' · ' + esc(ses.run_kind) + '</span>' : '') +
      (miss.length ? '<span class="ds-miss">' + miss.map(function (s) { return esc(s.label) + ' 폴더가 연결되지 않음'; }).join(' · ') + '</span>' : '') +
      (DS.note ? '<span class="ds-miss">' + esc(DS.note) + '</span>' : '');
    b.classList.toggle('not-user', v !== 'user');
    var ban = $('ds-banner');
    if (ban) { ban.hidden = v === 'user'; ban.textContent = v === 'user' ? '' : '‘' + dsLabel(v) + '’ 조회 중 — 목록 · 통계 · 문서는 이 공간의 기록만 셉니다. 시연 · 시험 기록이며 실제 운영 · 산업재해 집계가 아닙니다. 새 세션은 ‘' + dsLabel(w) + '’에 저장됩니다.'; }
    var dest = $('lv-dest');
    if (dest) dest.innerHTML = '새 세션 저장 대상 — <b>' + esc(dsLabel(w)) + '</b> · ' + esc(DS.write_run_kind) + ' <span class="mono note">' + esc(((dsInfo(w) || {}).root || '') + '\\control\\records\\live') + '</span>' +
      (ses && ses.space !== w ? '<br><span class="note">지금 세션은 끝날 때까지 ‘' + esc(ses.label) + '’에 기록한다</span>' : '');
  }
  function loadDS() { return api('/api/dataspace').then(function (d) { DS = d; renderDS(); return d; }); }
  function followSpace(key) {
    // 실시간 관제에서 넘긴 기록은 세션의 공간에 있다 — 조회 공간이 다르면 그 공간으로 옮겨서 연다 (저장 공간은 그대로)
    if (!key || !DS || DS.view === key) return Promise.resolve();
    return api('/api/dataspace/view', {key: key}).then(function (d) { DS = d; renderDS(); flash('조회 공간을 ‘' + dsLabel(key) + '’로 옮겼다 — 세션 기록이 있는 곳'); });
  }
  document.addEventListener('change', function (e) {
    if (e.target.id === 'ds-view') {
      api('/api/dataspace/view', {key: e.target.value}).then(function (d) { DS = d; renderDS(); flash(d.msg); show(curScreen); }).catch(function (x) { fail(x); loadDS(); });
    } else if (e.target.id === 'ds-write' || e.target.id === 'ds-kind') {
      api('/api/dataspace/write', {key: $('ds-write').value, run_kind: $('ds-kind').value}).then(function (d) { DS = d; renderDS(); flash(d.msg); }).catch(function (x) { fail(x); loadDS(); });
    }
  });
  setInterval(function () { loadDS().catch(function () {}); }, 5000);

  function show(id, o) {
    var target = document.querySelector('.screen[data-screen="' + id + '"]'); if (!target) return;
    if (id !== 'replay') stopPlay();
    curScreen = id;
    $('popups').classList.toggle('dock-b', id === 'live');
    screens.forEach(function (s) { s.hidden = (s !== target); });
    links.forEach(function (a) { a.classList.toggle('on', a.getAttribute('data-go') === id); });
    $('title').textContent = target.getAttribute('data-title');
    $('crumb').textContent = target.getAttribute('data-crumb');
    try { history.replaceState(null, '', '#' + id); } catch (e) { /* 미리 보기 등 */ }
    window.scrollTo(0, 0);
    if (LOADERS[id]) LOADERS[id](o || {});
  }
  document.addEventListener('click', function (e) {
    if (e.target.closest('#popups')) return;
    var go = e.target.closest('[data-go]');
    if (go) { e.preventDefault(); show(go.getAttribute('data-go'), {tab: go.getAttribute('data-tab'), ev: go.getAttribute('data-ev'), ptw: go.getAttribute('data-ptw'), acc: go.getAttribute('data-acc'), q: go.getAttribute('data-q')}); return; }
    if (e.target.closest('[data-reopen]')) { popClosed = {}; if (STATUS) popups(STATUS); return; }
    var zt = e.target.closest('[data-zone]'); if (zt) { curZone = zt.getAttribute('data-zone'); curCam = 0; zonePickedAt = Date.now(); if (LIVE) { renderZones(); renderZoneDetail(); } return; }
    var cb = e.target.closest('[data-cam]'); if (cb && cb.tagName === 'BUTTON') { curCam = +cb.getAttribute('data-cam'); renderZoneDetail(); return; }
    var pk = e.target.closest('[data-ptw]'); if (pk && pk.classList.contains('pick')) { ISO.cur = pk.getAttribute('data-ptw'); renderIsoPicks(); return; }
    var sc = e.target.closest('[data-sc]'); if (sc) { RP.cur = sc.getAttribute('data-sc'); renderScPicks(); loadSc(); return; }
    var rc = e.target.closest('[data-rc]'); if (rc) { if (FB.rc !== rc.getAttribute('data-rc')) FB.review = false; FB.rc = rc.getAttribute('data-rc'); renderFb(); return; }
    var ev = e.target.closest('tr[data-ev], .ev-row[data-ev]'); if (ev) { selectEv(ev.getAttribute('data-ev')); return; }
    var st = e.target.closest('.subtabs button'); if (st) { pickTab(st.parentElement.getAttribute('data-group'), st.getAttribute('data-tab')); return; }
    var sb = e.target.closest('.seg button');
    if (sb && !sb.closest('#fb-seg')) { sb.parentElement.querySelectorAll('button').forEach(function (x) { x.classList.remove('on'); }); sb.classList.add('on'); }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    var ev = e.target.closest && e.target.closest('tr[data-ev], .ev-row[data-ev]'); if (ev) { selectEv(ev.getAttribute('data-ev')); }
  });
  document.querySelectorAll('.nav a').forEach(function (a) {
    a.setAttribute('tabindex', '0'); a.setAttribute('role', 'button');
    a.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); a.click(); } });
  });
  /* ---------- 영상 장면 — 영상 올리기 · 첫 프레임 위에 구역 그리기 ----------
   * 영상을 올리면 첫 프레임이 뜨고, 그 위에 구역(폴리곤)을 찍어 장면으로 저장한다.
   * 구역 종류(위험구역 · 작업 구역 · 출입 제한)가 규칙(rules.json)과 불꽃 탐지에 그대로 걸린다.
   * 저장하면 그 스케줄의 scenario.json scenes 에 들어가고, 새 세션 시작부터 그 장면의 구역으로 판정한다. */
  var SC = {opt: null, polys: [], sel: -1, draw: null, drag: null, img: null, iw: 0, ih: 0, video: '', orig: '', hover: null, dirty: false};

  function scType(k) { return (SC.opt ? SC.opt.types : []).filter(function (t) { return t.key === k; })[0] || {label: k, color: '#9aa4af', prefix: 'P'}; }
  function scCam(id) { return (SC.opt ? SC.opt.cameras : []).filter(function (c) { return c.id === id; })[0]; }
  function scSelScene() {
    var sc = META && META.schedules.filter(function (x) { return x.key === $('lv-sched').value; })[0];
    return sc ? sc.scenes.filter(function (x) { return x.name === $('lv-scene').value; })[0] : null;
  }
  function sceneHint() {
    var x = scSelScene();
    $('sc-up').disabled = !$('lv-sched').value;
    $('sc-hint').textContent = !$('lv-sched').value ? '영상은 시나리오마다 따로 둔다 — 시나리오를 먼저 고른다'
      : !x ? '영상 없이 신호로만 판정한다. 줄을 눌러 영상을 고르거나, 줄의 ▶ 로 바로 세션을 시작한다'
      : '고른 영상 ‘' + x.name + '’ — 세션을 시작하면 지금 시각부터 이 영상이 돈다. ' +
        (x.own ? '구역: 이 장면에 그린 구역' : '구역: 아직 없음(화면 전체) — 구역 고치기로 그린다');
  }
  $('lv-scene').addEventListener('change', function () {
    sceneHint(); renderVideos(); if (LIVE) renderRun();
  });

  /* 영상 목록 — 영상(파일)마다 한 줄, 최근 올린 순. 같은 영상을 쓰는 장면이 여럿이면 그 아래 줄로 단다(예전에 따로 늘어난 것).
     줄을 누르면 고르고(▶ 시작 · 새 세션 시작이 이 영상으로), 줄 버튼으로 바로 세션 시작 · 구역 고치기 · 삭제 */
  function curSched() { return META && META.schedules.filter(function (x) { return x.key === $('lv-sched').value; })[0]; }
  function renderVideos() {
    if (!META) return;
    var box = $('vlist'), sc = curSched();
    var sel = $('lv-scene').value, m = (LIVE && LIVE.meta) || {};
    var live = sc && m.schedule === sc.key ? m.scene : null;
    var h;
    if (!sc) h = '<div class="vl-empty note">시나리오를 고르면 그 시나리오의 영상이 여기 나온다</div>';
    else {
      var vs = sc.videos || [];
      var tag = function (name) {
        return name !== live ? '' : (LIVE.video ? '<span class="lv ok">재생 중</span>' : '<span class="lv info">이 세션</span>');
      };
      var btns = function (x, one, g) {
        return '<span class="vbtns"><button class="btn dark sm" type="button" data-vplay="' + esc(x.name) + '" title="이 영상으로 새 세션을 처음부터 시작하고 바로 튼다">▶ 세션 시작</button>' +
          '<button class="btn sm" type="button" data-vedit="' + esc(x.name) + '"' + (g.exists ? '' : ' disabled') + '>구역 고치기</button>' +
          (one ? '<button class="btn sm" type="button" data-vdel="' + esc(g.video) + '">삭제</button>'
               : '<button class="btn sm" type="button" data-vrm="' + esc(x.name) + '" title="이 장면만 뺀다 — 영상은 남는다">빼기</button>') + '</span>';
      };
      var thumb = function (g) {
        return '<span class="vthumb">' + (g.exists ? '<img loading="lazy" alt="" src="/api/scene/frame?schedule=' + encodeURIComponent(sc.key) + '&video=' + encodeURIComponent(g.video) + '">' : '<i>파일 없음</i>') + '</span>';
      };
      var meta = function (x) { return esc(x.camera || '-') + ' · ' + (x.own ? '그린 구역 ' + x.n + '개' : '구역 없음'); };
      h = '<div class="vrow none' + (!sel ? ' on' : '') + '" data-vsel="" tabindex="0" aria-pressed="' + !sel + '"><span class="vthumb blank">—</span>' +
        '<span class="vtx"><b>영상 없이</b><small>신호로만 판정</small></span></div>';
      h += vs.map(function (g) {
        var file = esc(g.file) + (g.uploaded ? ' · ' + esc(g.uploaded) + ' 올림' : '');
        if (g.scenes.length === 1) {
          var x = g.scenes[0], on = x.name === sel;
          return '<div class="vrow' + (on ? ' on' : '') + '" data-vsel="' + esc(x.name) + '" tabindex="0" aria-pressed="' + on + '">' + thumb(g) +
            '<span class="vtx"><b>' + esc(x.name) + tag(x.name) + '</b><small>' + meta(x) + ' · ' + file + '</small></span>' + btns(x, true, g) + '</div>';
        }
        return '<div class="vgroup"><div class="vrow vhead">' + thumb(g) +
          '<span class="vtx"><b>' + esc(g.file) + '</b><small>같은 영상을 쓰는 장면 ' + g.scenes.length + '개' + (g.uploaded ? ' · ' + esc(g.uploaded) + ' 올림' : '') + ' — 하나만 남기고 빼도 된다</small></span>' +
          '<span class="vbtns"><button class="btn sm" type="button" data-vdel="' + esc(g.video) + '">영상 삭제</button></span></div>' +
          g.scenes.map(function (x) {
            var on = x.name === sel;
            return '<div class="vrow vsub' + (on ? ' on' : '') + '" data-vsel="' + esc(x.name) + '" tabindex="0" aria-pressed="' + on + '"><span class="vtx"><b>' + esc(x.name) + tag(x.name) + '</b><small>' + meta(x) + '</small></span>' + btns(x, false, g) + '</div>';
          }).join('') + '</div>';
      }).join('');
      if (!vs.length) h += '<div class="vl-empty note">이 시나리오에 올린 영상이 없다 — + 영상 올리기</div>';
      var picked = sel ? '고른 영상: ' + sel : '영상 없이';
      $('vl-n').textContent = (vs.length ? vs.length + '개 · 최근 올린 순' : '없음') + ($('vlist').hidden ? ' · ' + picked : '');
    }
    if (box.getAttribute('data-h') !== h) { box.innerHTML = h; box.setAttribute('data-h', h); }
  }
  /* 영상 목록 접기 · 펴기 — 연 상태는 이 브라우저에 기억. 접으면 머리줄에 고른 영상이 보인다 */
  function vlFold(open) {
    $('vlist').hidden = !open;
    $('vl-tog').setAttribute('aria-expanded', open ? 'true' : 'false');
    $('vl-tog').querySelector('.chev').textContent = open ? '▾' : '▸';
    store('vl-open', open ? '1' : '0');
    renderVideos();
  }
  $('vl-tog').addEventListener('click', function () { vlFold($('vlist').hidden); });
  if (store('vl-open') === '0') { $('vlist').hidden = true; $('vl-tog').setAttribute('aria-expanded', 'false'); $('vl-tog').querySelector('.chev').textContent = '▸'; }
  function pickScene(name) {
    $('lv-scene').value = name; if ($('lv-scene').value !== name) $('lv-scene').value = '';
    sceneHint(); renderVideos(); if (LIVE) renderRun();
  }
  $('vlist').addEventListener('click', function (e) {
    var b = e.target.closest('[data-vplay],[data-vedit],[data-vdel],[data-vrm]');
    if (b) {
      if (b.hasAttribute('data-vplay')) {
        pickScene(b.getAttribute('data-vplay'));
        sceneNow(b, Object.assign(liveForm(), {fresh: true}));
      } else if (b.hasAttribute('data-vedit')) {
        pickScene(b.getAttribute('data-vedit')); openScene(true);
      } else if (b.hasAttribute('data-vrm')) {
        var name = b.getAttribute('data-vrm');
        ask({title: '장면 빼기', note: '‘' + name + '’ 을 목록에서 뺀다. 같은 영상을 쓰는 다른 장면과 영상 파일은 남는다.', fields: []}, function () {
          return api('/api/scene/remove', {schedule: $('lv-sched').value, name: name}).then(function (d) { flash(d.msg); return scRefresh($('lv-scene').value === name ? '' : null); });
        });
      } else {
        var video = b.getAttribute('data-vdel'), g = (curSched().videos || []).filter(function (x) { return x.video === video; })[0] || {scenes: []};
        var sched = $('lv-sched').value, names = g.scenes.map(function (x) { return x.name; });
        var KEEP = '남긴다 — 영상 · 장면만 지운다';
        api('/api/scene/video/records?schedule=' + encodeURIComponent(sched) + '&video=' + encodeURIComponent(video)).then(function (r) {
          var has = r.sessions > 0;
          ask({title: '영상 삭제 — ' + (g.file || video),
            note: '이 영상을 쓰는 장면 ' + names.length + '개(' + names.join(', ') + ')를 목록에서 빼고, 다른 시나리오에서 쓰지 않으면 영상 파일도 지운다. ' +
              (has ? '이 영상으로 돌린 세션이 ' + r.sessions + '개(관제 기록 ' + r.events + '건) 있다 — 같이 지우면 이벤트 로그 · 통계에서 빠지고, 문서 자동화로 넘어간 사본도 빠진다(이미 문서에 쓰인 것은 남긴다). 되돌릴 수 없다.'
                   : '이 영상으로 돌린 관제 기록은 없다.'),
            fields: has ? [{k: 'rec', label: '관제 기록', options: [KEEP, '같이 지운다 — 세션 ' + r.sessions + '개 · 기록 ' + r.events + '건']}] : []}, function (v) {
            return api('/api/scene/video/remove', {schedule: sched, video: video, records: !!(v.rec && v.rec !== KEEP)}).then(function (d) {
              flash(d.msg); popSid = undefined;
              if (d.sids && d.sids.length) { tick(); if (curScreen === 'log' && typeof loadLog === 'function') loadLog(); }
              return scRefresh(names.indexOf($('lv-scene').value) >= 0 ? '' : null);
            });
          });
        }).catch(fail);
      }
      return;
    }
    var r = e.target.closest('[data-vsel]'); if (r) pickScene(r.getAttribute('data-vsel'));
  });
  $('vlist').addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    var r = e.target.closest('[data-vsel]'); if (!r || e.target !== r) return;
    e.preventDefault(); pickScene(r.getAttribute('data-vsel'));
  });

  function scErr(msg) { $('scn-err').textContent = msg || ''; $('scn-err').hidden = !msg; }
  function scNextName(type) {
    var pre = scType(type).prefix || 'P', n = 1;
    var used = SC.polys.map(function (p) { return p.name; });
    while (used.indexOf(pre + n) >= 0) n++;
    return pre + n;
  }

  function openScene(edit) {
    var sched = $('lv-sched').value;
    if (!sched) { flash('시나리오를 먼저 고른다 — 영상 장면은 시나리오마다 따로 둔다', true); return; }
    scErr('');
    api('/api/scene/options?schedule=' + encodeURIComponent(sched)).then(function (o) {
      SC.opt = o; SC.polys = []; SC.sel = -1; SC.draw = null; SC.drag = null; SC.img = null; SC.video = ''; SC.orig = ''; SC.dirty = false;
      var cam0 = o.cameras.filter(function (c) { return c.zone === o.zone; })[0] || o.cameras[0];
      scRenderCams(cam0 ? cam0.id : '');
      $('scn-file').value = ''; $('scn-vinfo').textContent = '';
      $('scn-cm').hidden = true; $('scn-cam-add').setAttribute('aria-expanded', 'false');
      $('scn-tm').hidden = true; $('scn-tm-open').setAttribute('aria-expanded', 'false');
      scRenderTypes();
      var x = edit ? o.scenes.filter(function (s) { return s.name === $('lv-scene').value; })[0] : null;
      if (edit && !x) { flash('고른 장면을 찾지 못했다', true); return; }
      if (x) {
        scUseScene(x);
        scLoadFrame(x.video);
      } else {
        $('scn-h').textContent = '영상 올리기 · 구역 설정';
        $('scn-file-lb').textContent = '영상 파일 (mp4)';
        $('scn-name').value = '';
        $('scn-lead').textContent = '시나리오 ‘' + o.title + '’에 영상을 더한다. 영상을 고르면 첫 프레임이 뜨고, 그 위에 구역을 찍는다. 이미 올린 영상이면 그 장면을 불러와 고친다(목록이 늘지 않는다). 영상은 세션을 시작하면 지금 시각부터 돈다.';
        $('scn-del').hidden = true;
        $('scn-draw').hidden = true;
      }
      scFillSrc(); scList(); scHelp(); scSaveState();
      $('scn').hidden = false;
      (x ? $('scn-name') : $('scn-file')).focus();
    }).catch(fail);
  }
  /* 있는 장면을 고치는 상태로 — 구역 고치기, 또는 같은 영상을 다시 올렸을 때 */
  function scUseScene(x) {
    SC.orig = x.name; SC.video = x.video;
    $('scn-h').textContent = '장면 구역 고치기 — ' + x.name;
    $('scn-file-lb').textContent = '영상 바꾸기 (선택) — 지금: ' + (x.video || '').split('/').pop();
    $('scn-name').value = x.name;
    if (x.camera) $('scn-cam').value = x.camera;
    SC.polys = (x.polygons || []).map(function (p) { return {name: p.name, type: p.type, zone: p.zone, label: p.label || '', points: p.points.map(function (q) { return [q[0], q[1]]; })}; });
    SC.sel = -1; SC.draw = null;
    $('scn-lead').textContent = x.own
      ? '이 장면에 그린 구역이다. 점을 끌어 옮기거나 구역을 더하고 지운 뒤 저장한다. 같은 영상이면 이름을 그대로 두고 저장해 덮어쓴다.'
      : '이 장면에는 아직 구역이 없다(화면 전체로 판정) — 구역을 그려 저장하면 이 장면의 구역이 된다.';
    $('scn-del').hidden = false;
    scFillSrc();
  }
  function scRenderCams(pick) {
    var o = SC.opt, keep = pick || $('scn-cam').value;
    $('scn-cam').innerHTML = o.cameras.map(function (c) { return opt(c.id, c.id + ' · ' + (c.zone || '') + (c.label ? ' · ' + c.label : '')); }).join('');
    if (keep && scCam(keep)) $('scn-cam').value = keep;
  }
  function scRenderTypes() {
    var o = SC.opt;
    $('scn-types').innerHTML = o.types.map(function (t) {
      return '<button class="btn sm tbtn" type="button" data-add="' + esc(t.key) + '" title="' + esc(t.desc || '') + '"><span class="sw" style="background:' + esc(t.color) + '"></span>' + esc(t.label) + '</button>';
    }).join('');
    $('scn-tm-list').innerHTML = o.types.map(function (t) {
      return '<div class="tm-row"><span class="sw" style="background:' + esc(t.color) + '"></span><b>' + esc(t.label) + '</b><span class="mono">' + esc(t.key) + '</span>' +
        (t.builtin ? '<span class="lv info">판정에 쓰임 · 고정</span>' : '<span class="lv mute">표시 · 기록용</span>') +
        '<span class="note">' + (t.used ? '구역 ' + t.used + '개에서 씀' : '아직 안 씀') + '</span>' +
        (t.builtin ? '' : '<span class="btnrow"><button class="btn sm" type="button" data-tm-edit="' + esc(t.key) + '">고치기</button><button class="btn sm" type="button" data-tm-del="' + esc(t.key) + '"' + (t.used ? ' disabled title="이 종류를 쓰는 구역이 있다 — 그 구역의 종류를 바꾼 뒤 지운다"' : '') + '>지우기</button></span>') + '</div>';
    }).join('');
  }
  /* 종류 · 카메라를 더하거나 지운 뒤 — 그리던 구역은 그대로 두고 고를 거리만 다시 받는다 */
  function scReloadOpt(pickCam) {
    return api('/api/scene/options?schedule=' + encodeURIComponent($('lv-sched').value)).then(function (o) {
      SC.opt.types = o.types; SC.opt.cameras = o.cameras;
      scRenderTypes(); scRenderCams(pickCam); scFillSrc(); scList(); scPaint();
      return api('/api/meta').then(function (m) { META.zone_types = m.zone_types; META.schedules = m.schedules; });
    });
  }
  function tmReset() {
    $('tm-label').value = ''; $('tm-desc').value = ''; $('tm-key').value = ''; $('tm-key').disabled = false;
    $('tm-color').value = '#8fd17a'; $('tm-save').textContent = '종류 더하기'; $('tm-save').removeAttribute('data-key'); $('tm-new').hidden = true;
  }
  $('scn-tm-open').addEventListener('click', function () {
    var p = $('scn-tm'); p.hidden = !p.hidden; this.setAttribute('aria-expanded', p.hidden ? 'false' : 'true');
    if (!p.hidden) { tmReset(); $('tm-label').focus(); }
  });
  $('tm-new').addEventListener('click', tmReset);
  $('tm-save').addEventListener('click', function () {
    var key = this.getAttribute('data-key') || $('tm-key').value.trim();
    var body = {label: $('tm-label').value.trim(), color: $('tm-color').value, desc: $('tm-desc').value.trim(), key: key};
    busy(this, api('/api/scene/type', body)).then(function (d) { flash(d.msg); tmReset(); return scReloadOpt(); }).catch(function (e) { scErr(e.message); });
  });
  $('scn-tm-list').addEventListener('click', function (e) {
    var b = e.target.closest('[data-tm-edit],[data-tm-del]'); if (!b) return;
    var k = b.getAttribute('data-tm-edit') || b.getAttribute('data-tm-del'), t = scType(k);
    if (b.hasAttribute('data-tm-edit')) {
      $('tm-label').value = t.label; $('tm-color').value = t.color; $('tm-desc').value = t.desc || ''; $('tm-key').value = k; $('tm-key').disabled = true;
      $('tm-save').textContent = '고친 내용 저장'; $('tm-save').setAttribute('data-key', k); $('tm-new').hidden = false; $('tm-label').focus();
      return;
    }
    busy(b, api('/api/scene/type/remove', {key: k})).then(function (d) { flash(d.msg); return scReloadOpt(); }).catch(function (e) { scErr(e.message); });
  });
  $('scn-cam-add').addEventListener('click', function () {
    var p = $('scn-cm'); p.hidden = !p.hidden; this.setAttribute('aria-expanded', p.hidden ? 'false' : 'true');
    if (p.hidden) return;
    var zs = (SC.opt.zones || []);
    $('cm-zone').innerHTML = zs.map(function (x) { return opt(x.id, x.id + ' ' + x.name); }).join('');
    var c = scCam($('scn-cam').value), z = (c && c.zone) || SC.opt.zone || (zs[0] && zs[0].id);
    $('cm-zone').value = z;
    var n = 1; while (scCam('CAM-' + z + '-' + ('0' + n).slice(-2))) n++;
    $('cm-id').value = 'CAM-' + z + '-' + ('0' + n).slice(-2); $('cm-label').value = '';
    $('cm-id').focus(); $('cm-id').select();
  });
  $('cm-zone').addEventListener('change', function () {
    var z = this.value, n = 1; if (!/^CAM-/.test($('cm-id').value)) return;
    while (scCam('CAM-' + z + '-' + ('0' + n).slice(-2))) n++;
    $('cm-id').value = 'CAM-' + z + '-' + ('0' + n).slice(-2);
  });
  $('cm-save').addEventListener('click', function () {
    busy(this, api('/api/scene/camera', {camera_id: $('cm-id').value.trim(), zone: $('cm-zone').value, label: $('cm-label').value.trim()}))
      .then(function (d) { flash(d.msg); $('scn-cm').hidden = true; $('scn-cam-add').setAttribute('aria-expanded', 'false'); SC.dirty = true; return scReloadOpt(d.camera_id).then(scSaveState); })
      .catch(function (e) { scErr(e.message); });
  });
  $('cm-del').addEventListener('click', function () {
    var id = $('scn-cam').value; if (!id) return;
    busy(this, api('/api/scene/camera/remove', {camera_id: id})).then(function (d) { flash(d.msg); return scReloadOpt(''); }).catch(function (e) { scErr(e.message); });
  });
  function closeScene() { $('scn').hidden = true; SC.draw = null; SC.drag = null; $('sc-up').focus(); }
  $('sc-up').addEventListener('click', function () { openScene(false); });
  $('scn-close').addEventListener('click', closeScene);
  $('scn-cancel').addEventListener('click', closeScene);

  function scFillSrc() {
    var o = SC.opt, h = opt('', '다른 구역 불러오기 …');
    o.scenes.forEach(function (s) { if (s.own && s.name !== SC.orig) h += opt('scene:' + s.name, '장면 ‘' + s.name + '’ 구역 (' + s.polygons.length + '개)'); });
    $('scn-src').innerHTML = h;
  }
  $('scn-load').addEventListener('click', function () {
    var v = $('scn-src').value; if (!v) return;
    var src = v.indexOf('cam:') === 0 ? (scCam(v.slice(4)) || {}).polygons
      : (SC.opt.scenes.filter(function (s) { return 'scene:' + s.name === v; })[0] || {}).polygons;
    SC.polys = (src || []).map(function (p) { return {name: p.name, type: p.type, zone: p.zone, label: p.label || '', points: p.points.map(function (q) { return [q[0], q[1]]; })}; });
    SC.sel = SC.polys.length ? 0 : -1; SC.draw = null; SC.dirty = true;
    scList(); scPaint(); scHelp(); scSaveState();
    flash('구역 ' + SC.polys.length + '개를 불러왔다 — 영상에 맞게 점을 끌어 옮긴다');
  });

  /* 영상 올리기 → 첫 프레임 */
  $('scn-file').addEventListener('change', function () {
    var f = this.files && this.files[0]; if (!f) return;
    var fd = new FormData(); fd.append('schedule', $('lv-sched').value); fd.append('file', f);
    scErr(''); $('scn-vinfo').textContent = '올리는 중 … ' + f.name + ' (' + (f.size / 1048576).toFixed(1) + 'MB)';
    $('scn-save').disabled = true;
    api('/api/scene/upload', fd).then(function (d) {
      SC.video = d.video;
      var ex = !SC.orig && d.same && d.scenes.length ? SC.opt.scenes.filter(function (s) { return s.name === d.scenes[0].name; })[0] : null;
      if (ex) {
        scUseScene(ex);
        flash('이미 올린 영상이다 (' + d.file + ') — 장면 ‘' + ex.name + '’ 을 불러왔다. 저장하면 이 장면을 고친다 — 목록이 늘지 않는다' +
          (d.scenes.length > 1 ? ' · 같은 영상을 쓰는 장면이 ' + d.scenes.length + '개 있다' : ''));
      } else {
        if (!$('scn-name').value.trim()) $('scn-name').value = f.name.replace(/\.[^.]+$/, '');
        flash(d.same ? '이미 있는 영상 파일을 쓴다 — ' + d.file : d.msg);
      }
      scLoadFrame(d.video);
    }).catch(function (e) { $('scn-vinfo').textContent = ''; scErr(e.message); scSaveState(); });
  });
  function scLoadFrame(video) {
    var q = '?schedule=' + encodeURIComponent($('lv-sched').value) + '&video=' + encodeURIComponent(video);
    api('/api/scene/info' + q).then(function (info) {
      SC.iw = info.w; SC.ih = info.h;
      $('scn-vinfo').textContent = '영상: ' + video.split('/').pop() + ' · ' + info.w + '×' + info.h + (info.fps ? ' · ' + info.fps + 'fps' : '') + (info.seconds ? ' · ' + info.seconds + '초' : '') +
        ' — 첫 프레임 위에 그린다. 좌표는 화면 비율로 저장돼 해상도가 달라도 같다.';
      var im = new Image();
      im.onload = function () { SC.img = im; $('scn-draw').hidden = false; scSize(); scList(); scHelp(); scSaveState(); };
      im.onerror = function () { scErr('첫 프레임을 불러오지 못했다'); };
      im.src = '/api/scene/frame' + q + '&t=' + Date.now();
    }).catch(function (e) { scErr(e.message); });
  }

  /* 캔버스 크기 · 그리기 */
  var cv = $('scn-cv');
  function scSize() {
    if (!SC.img) return;
    var w = $('scn-stage').clientWidth || 800, h = Math.round(w * SC.img.naturalHeight / SC.img.naturalWidth);
    var r = window.devicePixelRatio || 1;
    cv.width = Math.round(w * r); cv.height = Math.round(h * r); cv.style.height = h + 'px';
    scPaint();
  }
  window.addEventListener('resize', function () { if (!$('scn').hidden) scSize(); });
  function hexA(hex, a) {
    var n = parseInt(hex.slice(1), 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
  }
  function scPaint() {
    if (!SC.img) return;
    var c = cv.getContext('2d'), W = cv.width, H = cv.height, r = window.devicePixelRatio || 1;
    c.clearRect(0, 0, W, H);
    c.drawImage(SC.img, 0, 0, W, H);
    SC.polys.forEach(function (p, i) {
      var col = scType(p.type).color, on = i === SC.sel, pts = p.points;
      if (SC.draw && SC.draw.i === i) return;
      if (pts.length < 2) return;
      c.beginPath(); pts.forEach(function (q, k) { c[k ? 'lineTo' : 'moveTo'](q[0] * W, q[1] * H); }); c.closePath();
      c.fillStyle = hexA(col, on ? 0.30 : 0.16); c.fill();
      c.lineWidth = (on ? 3 : 2) * r; c.strokeStyle = col; c.setLineDash(on ? [] : [7 * r, 5 * r]); c.stroke(); c.setLineDash([]);
      var x0 = Math.min.apply(null, pts.map(function (q) { return q[0]; })) * W, y0 = Math.min.apply(null, pts.map(function (q) { return q[1]; })) * H;
      var tag = p.name + ' · ' + scType(p.type).label;
      c.font = '700 ' + (12 * r) + 'px "IBM Plex Sans KR","Malgun Gothic",sans-serif';
      var tw = c.measureText(tag).width + 10 * r;
      c.fillStyle = col; c.fillRect(x0, Math.max(0, y0 - 18 * r), tw, 18 * r);
      c.fillStyle = '#fff'; c.fillText(tag, x0 + 5 * r, Math.max(0, y0 - 18 * r) + 13 * r);
      if (on) pts.forEach(function (q) { c.fillStyle = '#fff'; c.strokeStyle = col; c.lineWidth = 2 * r; c.fillRect(q[0] * W - 5 * r, q[1] * H - 5 * r, 10 * r, 10 * r); c.strokeRect(q[0] * W - 5 * r, q[1] * H - 5 * r, 10 * r, 10 * r); });
    });
    if (SC.draw) {                                   // 찍는 중인 구역
      var p = SC.polys[SC.draw.i], col = scType(p.type).color, pts = SC.draw.pts;
      c.lineWidth = 2.5 * r; c.strokeStyle = col; c.fillStyle = hexA(col, 0.18);
      if (pts.length) {
        c.beginPath(); pts.forEach(function (q, k) { c[k ? 'lineTo' : 'moveTo'](q[0] * W, q[1] * H); });
        if (SC.hover) c.lineTo(SC.hover[0] * W, SC.hover[1] * H);
        if (pts.length > 2) { c.closePath(); c.fill(); }
        c.stroke();
      }
      pts.forEach(function (q, k) {
        c.beginPath(); c.arc(q[0] * W, q[1] * H, (k === 0 && pts.length > 2 ? 8 : 5) * r, 0, Math.PI * 2);
        c.fillStyle = k === 0 ? col : '#fff'; c.fill(); c.lineWidth = 2 * r; c.strokeStyle = col; c.stroke();
      });
    }
  }
  function scPt(e) {
    var b = cv.getBoundingClientRect();
    return [Math.min(1, Math.max(0, (e.clientX - b.left) / b.width)), Math.min(1, Math.max(0, (e.clientY - b.top) / b.height))];
  }
  function scNear(a, b, px) {
    var bb = cv.getBoundingClientRect();
    return Math.abs((a[0] - b[0]) * bb.width) <= px && Math.abs((a[1] - b[1]) * bb.height) <= px;
  }
  function scInside(pt, pts) {
    var x = pt[0], y = pt[1], ins = false;
    for (var i = 0, j = pts.length - 1; i < pts.length; j = i++) {
      var xi = pts[i][0], yi = pts[i][1], xj = pts[j][0], yj = pts[j][1];
      if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) ins = !ins;
    }
    return ins;
  }

  /* 찍기 · 끌기 */
  function scStartDraw(i) {
    SC.draw = {i: i, pts: [], old: SC.polys[i].points};
    SC.sel = i; SC.hover = null;
    scList(); scPaint(); scHelp();
  }
  function scFinishDraw() {
    if (!SC.draw) return;
    if (SC.draw.pts.length < 3) { scErr('점이 3개 이상이어야 한다 — 꼭짓점을 더 찍는다'); return; }
    SC.polys[SC.draw.i].points = SC.draw.pts;
    SC.draw = null; SC.dirty = true; scErr('');
    scList(); scPaint(); scHelp(); scSaveState();
  }
  function scCancelDraw() {
    if (!SC.draw) return;
    var i = SC.draw.i;
    if (SC.draw.old && SC.draw.old.length >= 3) SC.polys[i].points = SC.draw.old;
    else { SC.polys.splice(i, 1); SC.sel = -1; }
    SC.draw = null;
    scList(); scPaint(); scHelp(); scSaveState();
  }
  cv.addEventListener('pointerdown', function (e) {
    if (!SC.img) return;
    var pt = scPt(e);
    if (SC.draw) {
      var d = SC.draw;
      if (d.pts.length > 2 && scNear(pt, d.pts[0], 12)) { scFinishDraw(); return; }
      d.pts.push(pt); scPaint(); scHelp(); return;
    }
    var order = SC.sel >= 0 ? [SC.sel].concat(SC.polys.map(function (_, i) { return i; }).filter(function (i) { return i !== SC.sel; })) : SC.polys.map(function (_, i) { return i; });
    for (var a = 0; a < order.length; a++) {             // 꼭짓점 — 고른 구역부터
      var pi = order[a], pts = SC.polys[pi].points;
      for (var v = 0; v < pts.length; v++) {
        if (scNear(pt, pts[v], 10)) {
          SC.drag = {pi: pi, vi: v}; SC.sel = pi;
          cv.setPointerCapture(e.pointerId); scList(); scPaint(); e.preventDefault(); return;
        }
      }
    }
    for (var k = SC.polys.length - 1; k >= 0; k--) {    // 구역 안 — 고르기
      if (SC.polys[k].points.length > 2 && scInside(pt, SC.polys[k].points)) { SC.sel = k; scList(); scPaint(); return; }
    }
    SC.sel = -1; scList(); scPaint();
  });
  cv.addEventListener('pointermove', function (e) {
    if (SC.drag) {
      SC.polys[SC.drag.pi].points[SC.drag.vi] = scPt(e); SC.dirty = true; scPaint(); return;
    }
    if (SC.draw) { SC.hover = scPt(e); scPaint(); }
  });
  function scEndDrag() { if (SC.drag) { SC.drag = null; scList(); scSaveState(); } }
  cv.addEventListener('pointerup', scEndDrag);
  cv.addEventListener('pointercancel', scEndDrag);
  cv.addEventListener('pointerleave', function () { if (SC.draw) { SC.hover = null; scPaint(); } });
  cv.addEventListener('contextmenu', function (e) { if (SC.draw) { e.preventDefault(); SC.draw.pts.pop(); scPaint(); scHelp(); } });
  document.addEventListener('keydown', function (e) {
    if ($('scn').hidden || !SC.draw) return;
    var tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
    if (e.key === 'Enter') { e.preventDefault(); scFinishDraw(); }
    else if (e.key === 'Escape') { e.preventDefault(); scCancelDraw(); }
    else if (e.key === 'Backspace') { e.preventDefault(); SC.draw.pts.pop(); scPaint(); scHelp(); }
  });

  function scHelp() {
    var h = $('scn-help');
    $('scn-stage').classList.toggle('idle', !SC.draw);
    if (!SC.img) { h.innerHTML = ''; return; }
    if (SC.draw) {
      var p = SC.polys[SC.draw.i], n = SC.draw.pts.length;
      h.innerHTML = '<span><b>' + esc(p.name) + ' · ' + esc(scType(p.type).label) + '</b> — 꼭짓점을 차례로 누른다 (' + n + '개). 첫 점을 다시 누르거나 Enter 로 닫는다</span>' +
        '<button class="btn sm" type="button" data-h="done"' + (n < 3 ? ' disabled' : '') + '>완료</button>' +
        '<button class="btn sm" type="button" data-h="undo"' + (n ? '' : ' disabled') + '>점 하나 지우기</button>' +
        '<button class="btn sm" type="button" data-h="cancel">취소</button>';
    } else {
      h.innerHTML = SC.polys.length ? '<span>구역을 누르면 고르고, 흰 네모(꼭짓점)를 끌면 옮긴다. 새 구역은 위 ‘구역 추가’ 버튼</span>'
        : '<span>위 ‘구역 추가’에서 종류를 고른 뒤, 첫 프레임 위에 꼭짓점을 차례로 누른다</span>';
    }
  }
  $('scn-help').addEventListener('click', function (e) {
    var b = e.target.closest('[data-h]'); if (!b) return;
    var k = b.getAttribute('data-h');
    if (k === 'done') scFinishDraw(); else if (k === 'cancel') scCancelDraw();
    else if (k === 'undo' && SC.draw) { SC.draw.pts.pop(); scPaint(); scHelp(); }
  });
  $('scn-types').addEventListener('click', function (e) {
    var b = e.target.closest('[data-add]'); if (!b || !SC.img) return;
    if (SC.draw) scCancelDraw();
    var t = b.getAttribute('data-add'), cam = scCam($('scn-cam').value);
    SC.polys.push({name: scNextName(t), type: t, zone: (cam && cam.zone) || SC.opt.zone || (SC.opt.zones[0] || {}).id, label: scType(t).label, points: []});
    scStartDraw(SC.polys.length - 1);
  });

  /* 구역 목록 */
  function scList() {
    var o = SC.opt, el = $('scn-list');
    if (!o) return;
    if (!SC.polys.length) { el.innerHTML = '<div class="empty">아직 구역이 없다 — 그리지 않아도 저장 · 재생된다(화면 전체로 판정). 위험구역(상시 또는 작업 중)을 그리면 영상 불꽃이 점화원으로 잡힌다.</div>'; return; }
    el.innerHTML = SC.polys.map(function (p, i) {
      var t = scType(p.type), drawing = SC.draw && SC.draw.i === i;
      return '<div class="scn-item' + (i === SC.sel ? ' on' : '') + (p.points.length < 3 && !drawing ? ' bad' : '') + '" data-i="' + i + '">' +
        '<div class="r"><span class="sw" style="background:' + esc(t.color) + '"></span>' +
        '<input class="nm" data-f="name" value="' + esc(p.name) + '" aria-label="구역 이름 (영문 · 숫자)" maxlength="20">' +
        '<select data-f="type" aria-label="구역 종류">' + o.types.map(function (x) { return opt(x.key, x.label, x.key === p.type); }).join('') + '</select></div>' +
        '<div class="r"><select data-f="zone" aria-label="구역">' + o.zones.map(function (z) { return opt(z.id, z.id + ' ' + z.name, z.id === p.zone); }).join('') + '</select></div>' +
        '<div class="r"><input class="lbl" data-f="label" value="' + esc(p.label) + '" placeholder="설명 (경보 문장에 쓰인다)" aria-label="구역 설명"></div>' +
        '<div class="r"><span class="meta">' + (drawing ? '찍는 중 …' : '점 ' + p.points.length + '개') + ' · ' + esc(t.desc) + '</span></div>' +
        '<div class="r"><button class="btn sm" type="button" data-a="redraw">다시 찍기</button><button class="btn sm" type="button" data-a="del">지우기</button></div>' +
        '</div>';
    }).join('');
  }
  $('scn-list').addEventListener('input', function (e) {
    var it = e.target.closest('.scn-item'), f = e.target.getAttribute('data-f'); if (!it || !f) return;
    var p = SC.polys[+it.getAttribute('data-i')];
    if (f === 'name') p.name = e.target.value.trim();
    else if (f === 'label') p.label = e.target.value;
    SC.dirty = true; scPaint(); scSaveState();
  });
  $('scn-list').addEventListener('change', function (e) {
    var it = e.target.closest('.scn-item'), f = e.target.getAttribute('data-f'); if (!it || !f) return;
    var p = SC.polys[+it.getAttribute('data-i')];
    if (f === 'type') {
      var old = scType(p.type);
      if (!p.label || p.label === old.label) p.label = scType(e.target.value).label;
      p.type = e.target.value; scList();
    } else if (f === 'zone') p.zone = e.target.value;
    SC.dirty = true; scPaint(); scHelp(); scSaveState();
  });
  $('scn-list').addEventListener('click', function (e) {
    var it = e.target.closest('.scn-item'); if (!it) return;
    var i = +it.getAttribute('data-i'), b = e.target.closest('[data-a]');
    if (!b) { if (SC.sel !== i && !SC.draw) { SC.sel = i; scPaint(); it.parentNode.querySelectorAll('.scn-item').forEach(function (n) { n.classList.toggle('on', n === it); }); } return; }
    if (SC.draw) scCancelDraw();
    if (b.getAttribute('data-a') === 'del') {
      SC.polys.splice(i, 1); SC.sel = -1; SC.dirty = true;
      scList(); scPaint(); scHelp(); scSaveState();
    } else scStartDraw(i);
  });

  /* 저장 */
  function scProblem() {
    if (!SC.video) return '영상을 올린다';
    if (!SC.img) return '첫 프레임을 불러오는 중이다';
    if (SC.draw) return '찍는 중인 구역을 먼저 닫는다 (완료 또는 Enter)';
    var names = {};
    for (var i = 0; i < SC.polys.length; i++) {
      var p = SC.polys[i];
      if (p.points.length < 3) return p.name + ': 점이 3개 이상이어야 한다';
      if (!/^[A-Za-z0-9_.-]{1,20}$/.test(p.name)) return (i + 1) + '번 구역: 이름은 영문 · 숫자로 (영상 위에 적힌다 — 예: E1, W1)';
      if (names[p.name]) return '구역 이름 ‘' + p.name + '’ 가 두 번 나온다';
      names[p.name] = 1;
    }
    return '';
  }
  // 구역은 없어도 저장 · 재생된다 (10/8) — 빠진 것만 알려 준다
  function scZoneNote() {
    if (!SC.polys.length) return '구역 없이도 돈다 — 화면 전체를 카메라 구역으로 보고 사람 · 보호구 · 불꽃만 본다';
    if (!SC.polys.some(function (p) { return p.type === 'hazard' || p.type === 'hazard_repair'; })) return '위험구역(상시 · 작업 중)이 없다 — 저장 · 재생은 되지만 불꽃이 점화원으로 확정되지 않는다(점화원 수동 입력은 된다)';
    return '';
  }
  function scSaveState() {
    var why = scProblem();
    $('scn-save').disabled = $('scn-save-play').disabled = !!why;
    $('scn-save').title = why;
    $('scn-save-play').title = why || scZoneNote() || '저장하고 이 장면으로 관제 화면에서 바로 영상을 튼다';
    if (!why) $('scn-save').title = scZoneNote();
  }
  function scSave(btn, play) {
    var why = scProblem(); if (why) { scErr(why); return; }
    var body = {schedule: $('lv-sched').value, orig: SC.orig, name: $('scn-name').value.trim(),
      camera: $('scn-cam').value, video: SC.video, polygons: SC.polys};
    scErr('');
    busy(btn, api('/api/scene/save', body)).then(function (d) {
      flash(d.msg); SC.dirty = false; closeScene();
      return scRefresh(d.name).then(function () {
        if (!play) return;
        $('lv-panel').hidden = false; $('lv-more').setAttribute('aria-expanded', 'true');
        window.scrollTo({top: 0, behavior: 'smooth'});
        return sceneNow(null, Object.assign(liveForm(), {fresh: true}));
      });
    }).catch(function (e) { scErr(e.message); });
  }
  $('scn-save').addEventListener('click', function () { scSave(this, false); });
  $('scn-save-play').addEventListener('click', function () { scSave(this, true); });
  $('scn-del').addEventListener('click', function () {
    var name = SC.orig; if (!name) return;
    ask({title: '장면 빼기', note: '‘' + name + '’ 을 영상 장면 목록에서 뺀다. 영상 파일은 지우지 않는다(사업장 패키지 videos/ 에 남는다).', fields: []}, function () {
      return api('/api/scene/remove', {schedule: $('lv-sched').value, name: name}).then(function (d) { flash(d.msg); closeScene(); scRefresh(''); });
    });
  });
  function scRefresh(pick) {
    return api('/api/meta').then(function (m) {
      META.schedules = m.schedules; META.zone_types = m.zone_types || META.zone_types; META.cameras = m.cameras || META.cameras;
      var keep = pick != null ? pick : $('lv-scene').value;
      fillScenes(); $('lv-scene').value = keep; if ($('lv-scene').value !== keep) $('lv-scene').value = '';
      sceneHint(); renderVideos();
    }).catch(fail);
  }

  /* ---------- 시작 ---------- */
  function fillMeta() {
    $('brand-sub').textContent = (META.site_name || META.package) + ' · 구역 ' + META.zones[0].id + '~' + META.zones[META.zones.length - 1].id;
    $('ft-pkg').textContent = META.package + (META.sample ? ' · 예시 데이터 켜짐' : '');
    $('ft-in').textContent = '3축 신호 버튼 · 카메라 ' + META.cams_total + '대';
    var zOpts = META.zones.map(function (x) { return opt(x.id, x.id + ' ' + x.name); }).join('');
    $('f-zone').innerHTML = opt('전체', '전체') + zOpts;
    $('vc-zone').innerHTML = zOpts;
    $('reg-zone').innerHTML = META.zones.map(function (x) { return opt(x.id, x.id + ' ' + x.name + (x.piping ? '' : ' (계통도 없음)')); }).join('');
    $('reg-mode').innerHTML = META.work_types.map(function (w) { return opt(w, w); }).join('');
    $('lv-sched').innerHTML = opt('', '시나리오 없음') + META.schedules.map(function (s) { return opt(s.key, s.title, s.key === META.live.schedule); }).join('');
    $('lv-rs').innerHTML = META.rulesets.map(function (r) { return opt(r.key, r.label, r.key === META.live.ruleset); }).join('');
    fillScenes(); $('lv-scene').value = META.live.scene || ''; renderVideos(); renderSigpad();
    $('dt-ind').innerHTML = META.industries.map(function (x) { return opt(x, x, x === META.profile.industry); }).join('');
    $('dt-n').value = META.profile.workers;
    $('dt-cat').innerHTML = opt('전체', '전체') + META.duty_cats.map(function (c) { return opt(c, c); }).join('');
    $('dt-who').innerHTML = META.staff.map(function (p) { return opt(p.id, p.label); }).join('');
    VC.kind = META.voice.kinds[0]; VC.state = META.voice.states[1] || META.voice.states[0];
    $('vc-kind').innerHTML = META.voice.kinds.map(function (k, i) { return '<button type="button" data-v="' + esc(k) + '"' + (i === 0 ? ' class="on"' : '') + '>' + esc(k) + '</button>'; }).join('');
    $('vc-state').innerHTML = META.voice.states.map(function (k) { return '<button type="button" data-v="' + esc(k) + '"' + (k === VC.state ? ' class="on"' : '') + '>' + esc(k) + '</button>'; }).join('');
    $('iso-by').value = store('iso-by') || '';
    curZone = META.focus_zone;
    regReset(); setReg(store('iso-reg-open') !== '0');      // 등록 칸은 처음엔 펼쳐 둔다 (접어 두면 다음에도 접힌 채)
  }
  function tick() {
    tickStatus();
    if (curScreen === 'live') return api('/api/live').then(function (d) { LIVE = d; renderLive(); }).catch(function () {});
  }
  loadDS().catch(function () {});
  api('/api/meta').then(function (m) {
    META = m; fillMeta();
    var start = (location.hash || '').replace('#', '');
    show(start && document.querySelector('.screen[data-screen="' + start + '"]') ? start : 'live');
    tickStatus();
    setInterval(function () { if (!document.hidden) tickStatus(); }, 2000);
    // 실시간 관제 — 영상이 도는 동안은 0.5초마다 받아 영상 위 사람 · 안전모 수와 맞춘다 (10/8). 영상이 없으면 1초마다
    var liveBusy = false, liveLast = 0;
    setInterval(function () {
      if (document.hidden || curScreen !== 'live' || liveBusy) return;
      var gap = LIVE && LIVE.video ? 500 : 1000;
      if (Date.now() - liveLast < gap - 50) return;
      liveBusy = true; liveLast = Date.now();
      api('/api/live').then(function (d) { LIVE = d; renderLive(); }).catch(function () {}).then(function () { liveBusy = false; });
    }, 250);
  }).catch(function (e) {
    document.querySelector('.main').insertAdjacentHTML('afterbegin', '<div class="bar crit"><span>' + esc(e.message) + '</span></div>');
  });
})();
