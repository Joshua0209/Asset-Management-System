/* k6-charts.js — minimal interactive area/line charts in authentic k6-dashboard style.
   Dark (#0d0d0d) panels, k6 series palette, uPlot-like crosshair + live legend,
   optional dual y-axis, dashed threshold lines and pinned annotation callouts.
   API:  renderK6Chart(containerEl, config)  */
(function () {
  'use strict';

  const K6 = {
    text: '#9197ad',
    dim: '#6f7691',
    bright: '#e6e9f4',
    grid: 'rgba(255,255,255,0.055)',
    axis: 'rgba(255,255,255,0.16)',
  };
  // k6 dashboard series palette (Material variants, brightened for projection on navy)
  const PALETTE = {
    teal:   { line: '#2ec5b6', fill: 'rgba(46,197,182,0.15)' },   // throughput / rate
    blue:   { line: '#5e8def', fill: 'rgba(94,141,239,0.16)' },  // latency / duration
    purple: { line: '#c45ce0', fill: 'rgba(196,92,224,0.15)' },  // failed
    indigo: { line: '#6b79da', fill: 'rgba(107,121,218,0.22)' },   // VUs / load
    sky:    { line: '#29b6f6', fill: 'rgba(41,182,246,0.15)' },   // error rate (k6 light-blue)
    amber:  { line: '#e6a93c', fill: 'rgba(230,169,60,0.15)' },   // active VUs
  };

  const NS = 'http://www.w3.org/2000/svg';
  const el = (n, a) => { const e = document.createElementNS(NS, n); for (const k in (a || {})) e.setAttribute(k, a[k]); return e; };
  const niceMax = (v) => {
    if (v <= 0) return 1;
    const pow = Math.pow(10, Math.floor(Math.log10(v)));
    const n = v / pow;
    const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
    return step * pow;
  };

  function renderK6Chart(container, cfg) {
    container.innerHTML = '';
    container.style.position = 'relative';
    const W = cfg.width, H = cfg.height;
    const hasRight = cfg.series.some(s => s.axis === 'right');
    const hasPct = cfg.series.some(s => s.axis === 'pct');
    const PCT_OFF = hasRight ? 92 : 16; // how far out the pct ticks sit
    const m = { top: cfg.leftTitle || cfg.rightTitle ? 60 : 26, right: 30 + (hasRight ? 74 : 0) + (hasPct ? 84 : 0), bottom: cfg.xTitle ? 78 : 60, left: 92 };
    const plotW = W - m.left - m.right;
    const plotH = H - m.top - m.bottom;
    const n = cfg.x.length;

    // y-domains
    const domains = {};
    ['left', 'right', 'pct'].forEach(ax => {
      const ss = cfg.series.filter(s => (s.axis || 'left') === ax);
      if (!ss.length) return;
      let max = 0;
      ss.forEach(s => s.data.forEach(v => { if (v != null && v > max) max = v; }));
      (cfg.thresholds || []).forEach(t => { if ((t.axis || 'left') === ax) max = Math.max(max, t.value); });
      domains[ax] = { max: cfg[ax + 'Max'] || niceMax(max * 1.08) };
    });

    const xAt = i => m.left + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
    const yAt = (v, ax) => m.top + plotH - (v / domains[ax || 'left'].max) * plotH;

    const svg = el('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}` });
    svg.style.display = 'block';
    svg.style.overflow = 'visible';

    // ---- horizontal gridlines + left axis ticks ----
    const TICKS = 4;
    for (let t = 0; t <= TICKS; t++) {
      const y = m.top + (t / TICKS) * plotH;
      svg.appendChild(el('line', { x1: m.left, y1: y, x2: m.left + plotW, y2: y, stroke: K6.grid, 'stroke-width': 1 }));
      const lv = domains.left.max * (1 - t / TICKS);
      const lab = el('text', { x: m.left - 14, y: y + 7, 'text-anchor': 'end', fill: K6.dim, 'font-size': 22 });
      lab.textContent = cfg.leftFmt ? cfg.leftFmt(lv) : String(Math.round(lv));
      svg.appendChild(lab);
      if (hasRight) {
        const rv = domains.right.max * (1 - t / TICKS);
        const rl = el('text', { x: m.left + plotW + 16, y: y + 7, 'text-anchor': 'start', fill: K6.dim, 'font-size': 22 });
        rl.textContent = cfg.rightFmt ? cfg.rightFmt(rv) : String(Math.round(rv));
        svg.appendChild(rl);
      }
      if (hasPct) {
        const pv = domains.pct.max * (1 - t / TICKS);
        const pl = el('text', { x: m.left + plotW + PCT_OFF, y: y + 7, 'text-anchor': 'start', fill: cfg.pctTickColor || K6.dim, 'font-size': 22 });
        pl.textContent = cfg.pctFmt ? cfg.pctFmt(pv) : String(Math.round(pv));
        svg.appendChild(pl);
      }
    }
    // axis titles — colored to match their series, placed clear above the top tick (k6 style)
    if (cfg.leftTitle) {
      const lt = el('text', { x: m.left, y: m.top - 26, 'text-anchor': 'start', fill: cfg.leftTitleColor || K6.text, 'font-size': 21, 'font-weight': 500 });
      lt.textContent = cfg.leftTitle; svg.appendChild(lt);
    }
    if (hasRight && cfg.rightTitle) {
      const rt = el('text', { x: m.left + plotW, y: m.top - 26, 'text-anchor': 'end', fill: cfg.rightTitleColor || K6.text, 'font-size': 21, 'font-weight': 500 });
      rt.textContent = cfg.rightTitle; svg.appendChild(rt);
    }
    if (hasPct && cfg.pctTitle) {
      const pt = el('text', { x: m.left + plotW + PCT_OFF + 70, y: m.top - 26, 'text-anchor': 'end', fill: cfg.pctTitleColor || K6.text, 'font-size': 21, 'font-weight': 500 });
      pt.textContent = cfg.pctTitle; svg.appendChild(pt);
    }

    // ---- vertical gridlines + x labels ----
    const xEvery = Math.max(1, Math.round(n / (cfg.xTicks || 10)));
    for (let i = 0; i < n; i++) {
      if (i % xEvery !== 0 && i !== n - 1) continue;
      const x = xAt(i);
      svg.appendChild(el('line', { x1: x, y1: m.top, x2: x, y2: m.top + plotH, stroke: K6.grid, 'stroke-width': 1 }));
      const lab = el('text', { x: x, y: m.top + plotH + 32, 'text-anchor': 'middle', fill: K6.dim, 'font-size': 22 });
      lab.textContent = cfg.xFmt ? cfg.xFmt(cfg.x[i], i) : cfg.x[i];
      svg.appendChild(lab);
    }
    if (cfg.xTitle) {
      const xt = el('text', { x: m.left + plotW / 2, y: m.top + plotH + 66, 'text-anchor': 'middle', fill: K6.text, 'font-size': 21, 'font-weight': 500 });
      xt.textContent = cfg.xTitle; svg.appendChild(xt);
    }

    // ---- threshold lines ----
    (cfg.thresholds || []).forEach(t => {
      const y = yAt(t.value, t.axis);
      svg.appendChild(el('line', { x1: m.left, y1: y, x2: m.left + plotW, y2: y, stroke: t.color || '#e2574c', 'stroke-width': 2, 'stroke-dasharray': '8 6', opacity: 0.85 }));
      const onLeft = t.labelSide === 'left';
      const lab = el('text', { x: onLeft ? m.left + 8 : m.left + plotW - 6, y: y - 10, 'text-anchor': onLeft ? 'start' : 'end', fill: t.color || '#e2574c', 'font-size': 20, 'font-weight': 600 });
      lab.textContent = t.label; svg.appendChild(lab);
    });

    // ---- series (areas first, then lines) ----
    const resolved = cfg.series.map(s => {
      const pal = PALETTE[s.color] || { line: s.color, fill: 'rgba(255,255,255,0.1)' };
      return Object.assign({}, s, { _line: s.lineColor || pal.line, _fill: s.fillColor || pal.fill, _ax: s.axis || 'left' });
    });
    resolved.forEach(s => {
      if (s.kind !== 'area') return;
      let d = '';
      s.data.forEach((v, i) => { if (v == null) return; d += (d ? 'L' : 'M') + xAt(i) + ' ' + yAt(v, s._ax) + ' '; });
      const base = m.top + plotH;
      const area = d + `L${xAt(n - 1)} ${base} L${xAt(0)} ${base} Z`;
      svg.appendChild(el('path', { d: area, fill: s._fill, stroke: 'none' }));
      svg.appendChild(el('path', { d, fill: 'none', stroke: s._line, 'stroke-width': s.width || 2.5, 'stroke-linejoin': 'round', opacity: 0.9 }));
    });
    resolved.forEach(s => {
      if (s.kind === 'area') return;
      let d = '';
      s.data.forEach((v, i) => { if (v == null) return; d += (d ? 'L' : 'M') + xAt(i) + ' ' + yAt(v, s._ax) + ' '; });
      svg.appendChild(el('path', { d, fill: 'none', stroke: s._line, 'stroke-width': s.width || 3, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
    });

    // ---- pinned annotation callouts ----
    (cfg.annotations || []).forEach(a => {
      const s = resolved[a.s];
      const x = xAt(a.i), y = yAt(s.data[a.i], s._ax);
      // marker ring on the point
      svg.appendChild(el('circle', { cx: x, cy: y, r: 7, fill: '#1b2030', stroke: s._line, 'stroke-width': 3 }));
      svg.appendChild(el('circle', { cx: x, cy: y, r: 13, fill: 'none', stroke: s._line, 'stroke-width': 1.5, opacity: 0.45 }));
      const note = document.createElement('div');
      note.className = 'k6c-annot';
      note.style.cssText = `position:absolute;pointer-events:none;border:1px solid ${s._line};
        background:rgba(27,32,48,0.97);color:${K6.bright};padding:10px 13px;border-radius:6px;
        font:500 22px/1.3 system-ui,-apple-system,Segoe UI,sans-serif;white-space:nowrap;
        box-shadow:0 8px 24px rgba(0,0,0,0.5);z-index:4;`;
      note.innerHTML = a.html;
      container.appendChild(note);
      // position after attach (need offsetWidth)
      requestAnimationFrame(() => {
        const dir = a.dir || 'up';
        let nx = x - note.offsetWidth / 2, ny;
        if (dir === 'up') ny = y - note.offsetHeight - 22;
        else if (dir === 'down') ny = y + 22;
        else if (dir === 'left') { nx = x - note.offsetWidth - 22; ny = y - note.offsetHeight / 2; }
        else { nx = x + 22; ny = y - note.offsetHeight / 2; }
        nx = Math.max(4, Math.min(nx, W - note.offsetWidth - 4));
        ny = Math.max(4, Math.min(ny, H - note.offsetHeight - 4));
        note.style.left = nx + 'px'; note.style.top = ny + 'px';
        // connector
        const cn = el('line', { x1: x, y1: y, x2: nx + note.offsetWidth / 2, y2: dir === 'down' ? ny : ny + note.offsetHeight, stroke: s._line, 'stroke-width': 1.5, 'stroke-dasharray': '3 3', opacity: 0.6 });
        svg.insertBefore(cn, svg.firstChild.nextSibling);
      });
    });

    container.appendChild(svg);

    // ---- crosshair + tooltip overlay ----
    const cursor = el('line', { x1: 0, y1: m.top, x2: 0, y2: m.top + plotH, stroke: '#90a4ae', 'stroke-width': 1, 'stroke-dasharray': '4 4', opacity: 0 });
    svg.appendChild(cursor);
    const dots = resolved.map(s => { const c = el('circle', { r: 6, fill: s._line, stroke: '#1b2030', 'stroke-width': 2, opacity: 0 }); svg.appendChild(c); return c; });

    const tip = document.createElement('div');
    tip.style.cssText = `position:absolute;pointer-events:none;opacity:0;transition:opacity .08s;z-index:6;
      background:rgba(20,25,38,0.30);backdrop-filter:blur(9px);-webkit-backdrop-filter:blur(9px);
      border:1px solid rgba(255,255,255,0.18);border-radius:6px;
      padding:9px 12px;font:400 19px/1.4 system-ui,-apple-system,Segoe UI,sans-serif;color:${K6.text};
      text-shadow:0 1px 3px rgba(0,0,0,0.7);
      box-shadow:0 8px 22px rgba(0,0,0,0.4);white-space:nowrap;`;
    container.appendChild(tip);

    const hit = el('rect', { x: m.left, y: m.top, width: plotW, height: plotH, fill: 'transparent', style: 'cursor:crosshair' });
    svg.appendChild(hit);

    const rectFor = () => svg.getBoundingClientRect();
    function show(i) {
      const x = xAt(i);
      cursor.setAttribute('x1', x); cursor.setAttribute('x2', x); cursor.setAttribute('opacity', 1);
      let rows = `<div style="color:${K6.bright};font-weight:600;margin-bottom:6px">${cfg.xLabel ? cfg.xLabel(cfg.x[i], i) : cfg.x[i]}</div>`;
      resolved.forEach((s, si) => {
        const v = s.data[i];
        if (v == null) { dots[si].setAttribute('opacity', 0); return; }
        dots[si].setAttribute('cx', x); dots[si].setAttribute('cy', yAt(v, s._ax)); dots[si].setAttribute('opacity', 1);
        rows += `<div style="display:flex;align-items:center;gap:9px">
          <span style="width:13px;height:13px;border-radius:3px;background:${s._line}"></span>
          <span style="flex:1">${s.name}</span>
          <span style="color:${K6.bright};font-weight:600;margin-left:18px">${s.fmt ? s.fmt(v) : v}</span></div>`;
      });
      tip.innerHTML = rows; tip.style.opacity = 1;
      const r = rectFor();
      const sx = r.width / W, sy = r.height / H;
      let tx = x * sx + 16, ty = m.top * sy + 8;
      if (tx + tip.offsetWidth > r.width) tx = x * sx - tip.offsetWidth - 16;
      tip.style.left = tx + 'px'; tip.style.top = ty + 'px';
    }
    function hide() { cursor.setAttribute('opacity', 0); dots.forEach(d => d.setAttribute('opacity', 0)); tip.style.opacity = 0; }
    hit.addEventListener('mousemove', e => {
      const r = rectFor();
      const px = (e.clientX - r.left) / (r.width / W);
      let i = Math.round(((px - m.left) / plotW) * (n - 1));
      i = Math.max(0, Math.min(n - 1, i));
      show(i);
    });
    hit.addEventListener('mouseleave', hide);
  }

  window.renderK6Chart = renderK6Chart;
  window.K6_PALETTE = PALETTE;
})();
