// The Games tab: your own library. Best games first — a page that only ever shows
// you your mistakes is a page you stop opening.
//
// Rendering is lichess-pgn-viewer, the same widget lichess embeds, shipped as a
// package so nothing is fetched at runtime.

import LichessPgnViewer from '@lichess-org/pgn-viewer';

const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function mountViewer(host, pgn, orientation) {
  host.innerHTML = '';
  LichessPgnViewer(host, {
    pgn,
    orientation,
    showPlayers: 'auto',
    showMoves: 'right',
    showClocks: false,
    scrollToMove: true,
    keyboardToMove: true,
    drawArrows: true,
    menu: { getPgn: { enabled: true }, analysisBoard: { enabled: false } },
  });
}

/** Lazily mount a viewer the first time its panel is opened; they are not cheap. */
function lazyViewer(detailsEl, host, pgn, orientation) {
  let mounted = false;
  detailsEl.addEventListener('toggle', () => {
    if (detailsEl.open && !mounted) {
      mounted = true;
      mountViewer(host, pgn, orientation);
    }
  });
}

export function renderGames(root, data) {
  root.innerHTML = '';

  // ------------------------------------------------------------------ best games
  const best = document.createElement('section');
  best.className = 'games-section';
  best.innerHTML = `<h3>Your best games</h3>
    <p class="sub">From the depth-12 scan of all ${data.meta.total_games} games in the archive.</p>`;
  data.best_games.forEach((g, i) => {
    const d = document.createElement('details');
    d.className = 'game-card';
    d.open = i === 0;
    d.innerHTML = `<summary>
        <strong>${esc(g.title)}</strong>
        <span class="game-meta">${esc(g.date)} · vs ${esc(g.opponent)} · ${esc(g.time_class)}</span>
      </summary>
      <p class="game-note">${esc(g.note)}</p>
      <div class="viewer-host"></div>
      <a class="game-link" href="${esc(g.url)}" target="_blank" rel="noopener">open on chess.com</a>`;
    const host = d.querySelector('.viewer-host');
    best.append(d);
    if (i === 0) mountViewer(host, g.pgn, g.color);
    else lazyViewer(d, host, g.pgn, g.color);
  });
  root.append(best);

  // ----------------------------------------------------------- imported studies
  if (data.studies?.length) {
    const studies = document.createElement('section');
    studies.className = 'games-section';
    studies.innerHTML = `<h3>Imported studies</h3>
      <p class="sub">Exported from Lichess on ${data.meta.built} and embedded here, so they work
      with no connection. ${data.studies.length} studies, all free and public.</p>`;
    const groups = [...new Set(data.studies.map((s) => s.group))];
    groups.forEach((group) => {
      const h = document.createElement('h4');
      h.className = 'study-group';
      h.textContent = group;
      studies.append(h);
      data.studies.filter((s) => s.group === group).forEach((s) => {
        const d = document.createElement('details');
        d.className = 'game-card';
        d.innerHTML = `<summary><strong>${esc(s.label)}</strong>
            <span class="game-meta">${s.chapters} chapters</span></summary>
          <div class="viewer-host"></div>
          <a class="game-link" href="${esc(s.source_url)}" target="_blank" rel="noopener">open on lichess</a>`;
        lazyViewer(d, d.querySelector('.viewer-host'), s.pgn, 'white');
        studies.append(d);
      });
    });
    root.append(studies);
  }

  // ------------------------------------------------------------- the games table
  const table = document.createElement('section');
  table.className = 'games-section';
  table.innerHTML = `<h3>Every reviewed game</h3>
    <p class="sub">${data.games.length} rapid games since 2025, at depth 16. Click a column to sort;
    the worst games by accuracy are where the ritual says to start.</p>`;

  const wrap = document.createElement('div');
  wrap.className = 'table-scroll';
  const t = document.createElement('table');
  t.className = 'data-table sortable';
  const cols = [
    { k: 'date', label: 'Date' },
    { k: 'color', label: 'Colour' },
    { k: 'opponent', label: 'Opponent' },
    { k: 'accuracy', label: 'Accuracy', num: true },
    { k: 'acpl', label: 'ACPL', num: true },
    { k: 'blunders', label: 'Blunders', num: true },
    { k: 'moves', label: 'Moves', num: true },
    { k: 'result', label: 'Result' },
  ];
  let sortKey = 'accuracy';
  let sortAsc = true;

  function draw() {
    const rows = [...data.games].sort((a, b) => {
      const x = a[sortKey], y = b[sortKey];
      const cmp = typeof x === 'number' ? x - y : String(x).localeCompare(String(y));
      return sortAsc ? cmp : -cmp;
    });
    t.innerHTML = `
      <thead><tr>${cols.map((c) => `
        <th class="${c.num ? 'num' : ''} ${c.k === sortKey ? 'sorted' : ''}" data-k="${c.k}">
          ${c.label}${c.k === sortKey ? (sortAsc ? ' ▲' : ' ▼') : ''}</th>`).join('')}
        <th></th></tr></thead>
      <tbody>${rows.map((g) => `
        <tr class="${g.accuracy < 55 ? 'row-bad' : ''}">
          <td>${esc(g.date)}</td>
          <td>${esc(g.color)}</td>
          <td>${esc(g.opponent)}</td>
          <td class="num">${g.accuracy.toFixed(1)}</td>
          <td class="num">${g.acpl}</td>
          <td class="num ${g.blunders >= 4 ? 'flag' : ''}">${g.blunders}</td>
          <td class="num">${g.moves}</td>
          <td>${esc(g.result)}</td>
          <td><a href="${esc(g.url)}" target="_blank" rel="noopener">open</a></td>
        </tr>`).join('')}</tbody>`;
    t.querySelectorAll('th[data-k]').forEach((th) => {
      th.onclick = () => {
        const k = th.dataset.k;
        if (k === sortKey) sortAsc = !sortAsc;
        else { sortKey = k; sortAsc = k === 'accuracy' || k === 'date'; }
        draw();
      };
    });
  }
  draw();
  wrap.append(t);
  table.append(wrap);
  root.append(table);

  // -------------------------------------------------------------- worst blunders
  const worst = document.createElement('section');
  worst.className = 'games-section';
  worst.innerHTML = `<h3>The 15 worst single moves</h3>
    <p class="sub">The ritual says to set these up on a board and find the move before reading the
    answer. The Train tab does exactly that — these are listed here for the record.</p>
    <ol class="worst-list">${data.worst_moves.map((w) => `
      <li>
        <span class="worst-date">${esc(w.date)}</span>
        <span class="worst-move">move ${w.move_no} as ${esc(w.color)}: played
          <strong class="bad">${esc(w.played)}</strong>, best <strong class="good">${esc(w.best)}</strong></span>
        <span class="worst-swing">${(w.eval_before / 100).toFixed(1)} → ${(w.eval_after / 100).toFixed(1)}</span>
        <span class="worst-meta">${esc(w.phase)}, thought ${w.think_seconds.toFixed(1)}s</span>
        <a href="${esc(w.url)}" target="_blank" rel="noopener">game</a>
      </li>`).join('')}</ol>`;
  root.append(worst);
}
