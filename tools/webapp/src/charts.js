// Hand-rolled SVG charts. No charting library: the shapes here are simple, and a
// dependency would cost more bytes than the ~200 lines it would replace.
// Colour comes from CSS custom properties so the page themes in one place.

const NS = 'http://www.w3.org/2000/svg';

function el(name, attrs = {}, text) {
  const node = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text != null) node.textContent = text;
  return node;
}

function frame(width, height, cls = '') {
  const svg = el('svg', {
    viewBox: `0 0 ${width} ${height}`,
    preserveAspectRatio: 'xMidYMid meet',
    class: `chart ${cls}`.trim(),
    role: 'img',
  });
  return svg;
}

/**
 * Rating over time, with a peak marker and a goal line.
 * points: [{t: epochSeconds, r: rating}], already sorted.
 */
export function ratingChart(points, { goal, peak, width = 720, height = 260 } = {}) {
  const pad = { l: 44, r: 12, t: 14, b: 26 };
  const svg = frame(width, height, 'chart-rating');
  if (!points.length) return svg;

  const xs = points.map((p) => p.t);
  const ys = points.map((p) => p.r);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y0 = Math.min(...ys, goal ?? Infinity) - 40;
  const y1 = Math.max(...ys, goal ?? -Infinity) + 40;

  const sx = (t) => pad.l + ((t - x0) / (x1 - x0 || 1)) * (width - pad.l - pad.r);
  const sy = (r) => height - pad.b - ((r - y0) / (y1 - y0 || 1)) * (height - pad.t - pad.b);

  // Horizontal gridlines every 200 rating points.
  for (let r = Math.ceil(y0 / 200) * 200; r <= y1; r += 200) {
    svg.append(el('line', { x1: pad.l, x2: width - pad.r, y1: sy(r), y2: sy(r), class: 'grid' }));
    svg.append(el('text', { x: pad.l - 8, y: sy(r) + 4, class: 'tick', 'text-anchor': 'end' }, r));
  }

  if (goal) {
    svg.append(el('line', { x1: pad.l, x2: width - pad.r, y1: sy(goal), y2: sy(goal), class: 'goal-line' }));
    svg.append(el('text', { x: width - pad.r, y: sy(goal) - 6, class: 'goal-label', 'text-anchor': 'end' }, `goal ${goal}`));
  }

  const d = points.map((p, i) => `${i ? 'L' : 'M'}${sx(p.t).toFixed(1)},${sy(p.r).toFixed(1)}`).join('');
  svg.append(el('path', { d, class: 'series' }));

  if (peak) {
    svg.append(el('circle', { cx: sx(peak.t), cy: sy(peak.r), r: 4, class: 'peak-dot' }));
    svg.append(el('text', {
      x: sx(peak.t), y: sy(peak.r) - 10, class: 'peak-label',
      'text-anchor': sx(peak.t) > width * 0.7 ? 'end' : 'middle',
    }, `peak ${peak.r}`));
  }

  const last = points[points.length - 1];
  svg.append(el('circle', { cx: sx(last.t), cy: sy(last.r), r: 4, class: 'last-dot' }));

  const year = (t) => new Date(t * 1000).getFullYear();
  for (let y = year(x0); y <= year(x1); y++) {
    const t = new Date(`${y}-01-01T00:00:00Z`).getTime() / 1000;
    if (t < x0 || t > x1) continue;
    svg.append(el('text', { x: sx(t), y: height - 8, class: 'tick', 'text-anchor': 'middle' }, y));
  }
  return svg;
}

/**
 * Horizontal bars with a value label. Used for the think-time and phase breakdowns,
 * where the story is the comparison between a handful of rates.
 * bars: [{label, value, note, highlight}]
 */
export function barChart(bars, { unit = '%', width = 560, rowH = 34 } = {}) {
  // Right padding has to hold both the percentage and the "56 / 1173" denominator,
  // which is the part that makes a rate believable.
  const pad = { l: 96, r: 150, t: 6, b: 6 };
  const height = pad.t + pad.b + bars.length * rowH;
  const svg = frame(width, height, 'chart-bars');
  const max = Math.max(...bars.map((b) => b.value), 1);
  const track = width - pad.l - pad.r;

  bars.forEach((b, i) => {
    const y = pad.t + i * rowH;
    const mid = y + rowH / 2;
    svg.append(el('text', { x: pad.l - 10, y: mid + 4, class: 'bar-label', 'text-anchor': 'end' }, b.label));
    svg.append(el('rect', { x: pad.l, y: y + 7, width: track, height: rowH - 16, rx: 3, class: 'bar-track' }));
    svg.append(el('rect', {
      x: pad.l, y: y + 7, width: Math.max(2, (b.value / max) * track), height: rowH - 16, rx: 3,
      class: `bar-fill${b.highlight ? ' is-high' : ''}`,
    }));
    svg.append(el('text', { x: pad.l + track + 10, y: mid + 4, class: 'bar-value' }, `${b.value}${unit}`));
    if (b.note) svg.append(el('text', { x: pad.l + track + 62, y: mid + 4, class: 'bar-note' }, b.note));
  });
  return svg;
}

/**
 * One stacked bar showing how a whole divides. Used for move classification,
 * where the shape of the whole matters more than any single slice.
 * parts: [{label, value, cls}]
 */
export function stackedBar(parts, { width = 720, height = 58 } = {}) {
  const svg = frame(width, height, 'chart-stack');
  const total = parts.reduce((s, p) => s + p.value, 0) || 1;
  let x = 0;
  parts.forEach((p) => {
    const w = (p.value / total) * width;
    svg.append(el('rect', { x, y: 0, width: Math.max(0, w - 1), height: 26, class: `slice ${p.cls || ''}` }));
    if (w > 42) {
      svg.append(el('text', { x: x + w / 2, y: 45, class: 'slice-label', 'text-anchor': 'middle' }, p.label));
      svg.append(el('text', { x: x + w / 2, y: 56, class: 'slice-pct', 'text-anchor': 'middle' },
        `${((p.value / total) * 100).toFixed(1)}%`));
    }
    x += w;
  });
  return svg;
}

/** Distribution histogram: how much clock was left when a game was lost. */
export function histogram(values, { bins = 10, width = 460, height = 180, xLabel = '' } = {}) {
  const pad = { l: 34, r: 10, t: 10, b: 34 };
  const svg = frame(width, height, 'chart-hist');
  const counts = new Array(bins).fill(0);
  for (const v of values) counts[Math.min(bins - 1, Math.max(0, Math.floor(v * bins)))]++;
  const max = Math.max(...counts, 1);
  const bw = (width - pad.l - pad.r) / bins;

  counts.forEach((c, i) => {
    const h = (c / max) * (height - pad.t - pad.b);
    svg.append(el('rect', {
      x: pad.l + i * bw + 1, y: height - pad.b - h, width: bw - 2, height: h, rx: 2,
      class: 'hist-bar',
    }));
    if (c) svg.append(el('text', {
      x: pad.l + i * bw + bw / 2, y: height - pad.b - h - 4, class: 'tick', 'text-anchor': 'middle',
    }, c));
  });

  for (const f of [0, 0.25, 0.5, 0.75, 1]) {
    svg.append(el('text', {
      x: pad.l + f * (width - pad.l - pad.r), y: height - 16, class: 'tick', 'text-anchor': 'middle',
    }, `${Math.round(f * 100)}%`));
  }
  if (xLabel) svg.append(el('text', { x: width / 2, y: height - 3, class: 'axis-label', 'text-anchor': 'middle' }, xLabel));
  return svg;
}

/** Sparkline for a small trend, e.g. blunders per game by month. */
export function sparkColumns(series, { width = 720, height = 150, unit = '' } = {}) {
  const pad = { l: 34, r: 10, t: 12, b: 30 };
  const svg = frame(width, height, 'chart-cols');
  if (!series.length) return svg;
  const max = Math.max(...series.map((s) => s.value), 1);
  const bw = (width - pad.l - pad.r) / series.length;

  series.forEach((s, i) => {
    const h = (s.value / max) * (height - pad.t - pad.b);
    svg.append(el('rect', {
      x: pad.l + i * bw + 1.5, y: height - pad.b - h, width: Math.max(2, bw - 3), height: h, rx: 2,
      class: 'col-bar',
    }));
    svg.append(el('title', {}, `${s.label}: ${s.value}${unit} (${s.n} games)`));
    if (series.length <= 18 || i % 2 === 0) {
      svg.append(el('text', {
        x: pad.l + i * bw + bw / 2, y: height - 14, class: 'tick tick-rot', 'text-anchor': 'end',
        transform: `rotate(-45 ${pad.l + i * bw + bw / 2} ${height - 14})`,
      }, s.label));
    }
  });
  svg.append(el('text', { x: pad.l - 8, y: pad.t + 6, class: 'tick', 'text-anchor': 'end' }, max.toFixed(1)));
  return svg;
}
