// Entry point. Data arrives as window.__CHESS_DATA__, injected by tools/build_page.py
// at build time; nothing is fetched while the page runs.

import '@lichess-org/chessground/assets/chessground.base.css';
import '@lichess-org/chessground/assets/chessground.brown.css';
import '@lichess-org/chessground/assets/chessground.cburnett.css';
// Imported by path: the package's exports map rewrites "./*" to "./dist/*.js",
// which would mangle a stylesheet request.
import '../node_modules/@lichess-org/pgn-viewer/dist/lichess-pgn-viewer.css';
import './style.css';

import { renderTrain } from './train.js';
import { renderStats } from './stats.js';
import { renderStudy } from './study.js';
import { renderGames } from './games.js';

const TABS = [
  { id: 'train', label: 'Train', render: renderTrain, note: 'drill the positions you lost' },
  { id: 'stats', label: 'Stats', render: renderStats, note: 'what the games actually say' },
  { id: 'study', label: 'Study', render: renderStudy, note: 'the plan and the resources' },
  { id: 'games', label: 'Games', render: renderGames, note: 'your library' },
];

function boot() {
  const data = window.__CHESS_DATA__;
  const app = document.getElementById('app');

  if (!data) {
    app.innerHTML = `<p class="fatal">No data was baked into this page.
      Rebuild it with <code>python tools/build_page.py</code>.</p>`;
    return;
  }

  document.getElementById('rating-now').textContent = data.stats.rating_now;
  document.getElementById('built-on').textContent = data.meta.built;

  const nav = document.getElementById('tabs');
  const panels = new Map();
  const rendered = new Set();

  TABS.forEach((tab) => {
    const btn = document.createElement('button');
    btn.className = 'tab';
    btn.id = `tab-${tab.id}`;
    btn.setAttribute('role', 'tab');
    btn.innerHTML = `<span class="tab-label">${tab.label}</span><span class="tab-note">${tab.note}</span>`;
    btn.onclick = () => select(tab.id);
    nav.append(btn);

    const panel = document.createElement('div');
    panel.className = 'panel';
    panel.id = `panel-${tab.id}`;
    panel.setAttribute('role', 'tabpanel');
    panel.hidden = true;
    app.append(panel);
    panels.set(tab.id, { tab, panel, btn });
  });

  function select(id) {
    if (!panels.has(id)) id = TABS[0].id;
    for (const [key, { panel, btn }] of panels) {
      const on = key === id;
      panel.hidden = !on;
      btn.setAttribute('aria-selected', String(on));
    }
    const { tab, panel } = panels.get(id);
    if (!rendered.has(id)) {
      rendered.add(id);
      try {
        tab.render(panel, data);
      } catch (err) {
        // One broken tab should not take the page down with it.
        panel.innerHTML = `<p class="fatal">The ${tab.label} tab failed to render:
          <code>${String(err && err.message || err)}</code></p>`;
        console.error(err);
      }
    }
    if (location.hash.slice(1) !== id) history.replaceState(null, '', `#${id}`);
  }

  window.addEventListener('hashchange', () => select(location.hash.slice(1)));
  select(location.hash.slice(1) || TABS[0].id);
}

document.readyState === 'loading'
  ? document.addEventListener('DOMContentLoaded', boot)
  : boot();
