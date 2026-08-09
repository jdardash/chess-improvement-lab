// The Study tab: the plan as something you tick, the resources as something you
// can trust. Every external link here was fetched and confirmed live on the build
// date; the ones that died are listed too, so they don't get rediscovered.

import { makeBoard } from './board.js';

const CHECK_KEY = 'chess-page/study-checks-v1';

const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function loadChecks() {
  try { return JSON.parse(localStorage.getItem(CHECK_KEY) || '{}'); } catch { return {}; }
}
function saveChecks(state) {
  try { localStorage.setItem(CHECK_KEY, JSON.stringify(state)); } catch { /* non-fatal */ }
}

/** A checklist whose ticks survive a reload — the plan is a habit, not a document. */
function checklist(items, keyPrefix, state) {
  const ul = document.createElement('ul');
  ul.className = 'checklist-block';
  items.forEach((text, i) => {
    const id = `${keyPrefix}:${i}`;
    const li = document.createElement('li');
    const box = document.createElement('input');
    box.type = 'checkbox';
    box.id = id;
    box.checked = !!state[id];
    box.onchange = () => { state[id] = box.checked; saveChecks(state); li.classList.toggle('done', box.checked); };
    const label = document.createElement('label');
    label.htmlFor = id;
    label.innerHTML = text;
    li.classList.toggle('done', box.checked);
    li.append(box, label);
    ul.append(li);
  });
  return ul;
}

function details(summary, open = false) {
  const d = document.createElement('details');
  d.open = open;
  d.innerHTML = `<summary>${summary}</summary>`;
  return d;
}

const LOG_KEY = 'chess-page/session-log-v1';

function loadLog() {
  try { return JSON.parse(localStorage.getItem(LOG_KEY) || '[]'); } catch { return []; }
}
function saveLog(entries) {
  try { localStorage.setItem(LOG_KEY, JSON.stringify(entries)); } catch { /* non-fatal */ }
}

const ACTIVITIES = ['puzzles', 'slow game', 'game analysis', 'endgames', 'study', 'other'];

/**
 * The session log. Charness: what predicts rating is accumulated *serious* study,
 * and what gets measured gets done. Stored locally, like everything else here.
 */
function renderLog() {
  const sec = document.createElement('section');
  sec.className = 'study-section session-log';

  function draw() {
    const entries = loadLog();
    const now = Date.now();
    const week = entries.filter((e) => now - new Date(e.d).getTime() < 7 * 86400e3);
    const weekMin = week.reduce((s, e) => s + e.m, 0);
    const hours = (weekMin / 60).toFixed(1);
    const inBand = weekMin >= 210;
    sec.innerHTML = `<h3>Session log</h3>
      <p class="sub">Log every real session — played, solved, or analyzed; watching does not count.
        The evidence band is 3.5&ndash;7 focused hours a week; past ~15 it stops paying.</p>
      <div class="log-week">this week <strong class="${inBand ? 'good' : ''}">${hours}h</strong>
        <span class="unit">of 3.5&ndash;7h target</span></div>
      <form class="log-form">
        <input type="number" name="minutes" min="1" max="600" placeholder="min" required>
        <select name="activity">${ACTIVITIES.map((a) => `<option>${a}</option>`).join('')}</select>
        <button class="btn" type="submit">log it</button>
      </form>
      <table class="data-table log-table"><tbody>${entries.slice(-10).reverse().map((e, i) => `
        <tr><td>${e.d}</td><td>${e.a}</td><td>${e.m} min</td>
            <td><button class="link-btn log-del" data-i="${entries.length - 1 - i}">remove</button></td></tr>`).join('')}
      </tbody></table>`;

    sec.querySelector('.log-form').onsubmit = (ev) => {
      ev.preventDefault();
      const f = ev.target;
      const m = parseInt(f.minutes.value, 10);
      if (!m) return;
      const entries2 = loadLog();
      entries2.push({ d: new Date().toISOString().slice(0, 10), a: f.activity.value, m });
      saveLog(entries2);
      draw();
    };
    sec.querySelectorAll('.log-del').forEach((b) => {
      b.onclick = () => {
        const entries2 = loadLog();
        entries2.splice(parseInt(b.dataset.i, 10), 1);
        saveLog(entries2);
        draw();
      };
    });
  }

  draw();
  return sec;
}

export function renderStudy(root, data) {
  const state = loadChecks();
  const st = data.study;
  root.innerHTML = '';

  // ------------------------------------------------------------------ the plan
  const plan = document.createElement('section');
  plan.className = 'study-section plan-card';
  plan.innerHTML = `<h3>The plan</h3>
    <p class="sub">One habit, one setting, one ritual. From <code>docs/personal-plan.md</code>.</p>`;

  const habit = document.createElement('div');
  habit.className = 'plan-block';
  habit.innerHTML = `<h4>1 · The habit — Real Chess, every move</h4>
    <blockquote>${st.habit_quote}</blockquote>`;
  habit.append(checklist(st.habit, 'habit', state));
  plan.append(habit);

  const setting = document.createElement('div');
  setting.className = 'plan-block';
  setting.innerHTML = `<h4>2 · The setting</h4>`;
  setting.append(checklist(st.setting, 'setting', state));
  plan.append(setting);

  const ritual = document.createElement('div');
  ritual.className = 'plan-block';
  ritual.innerHTML = `<h4>3 · The monthly ritual — about 30 minutes</h4>`;
  ritual.append(checklist(st.ritual, 'ritual', state));
  plan.append(ritual);

  const weekly = document.createElement('div');
  weekly.className = 'plan-block';
  weekly.innerHTML = `<h4>Weekly shape</h4>`;
  weekly.append(checklist(st.weekly, 'weekly', state));
  plan.append(weekly);

  const avoid = document.createElement('div');
  avoid.className = 'plan-block avoid';
  avoid.innerHTML = `<h4>Avoid</h4><ul>${st.avoid.map((a) => `<li>${a}</li>`).join('')}</ul>`;
  plan.append(avoid);

  const reset = document.createElement('button');
  reset.className = 'link-btn';
  reset.textContent = 'clear all ticks';
  reset.onclick = () => { saveChecks({}); renderStudy(root, data); };
  plan.append(reset);
  root.append(plan);

  // ------------------------------------------------------------ what works
  // The deep-research synthesis, with the honest audit of whether this system
  // actually supports each practice. Content baked by build_page.py.
  if (data.evidence) {
    const ev = data.evidence;
    const BADGE = {
      covered: ['on this page', 'covered'],
      partial: ['partial', 'partial'],
      external: ['outside this page', 'external'],
      gated: ['gated', 'gated'],
    };
    const sec = document.createElement('section');
    sec.className = 'study-section evidence';
    sec.innerHTML = `<h3>What actually works — and whether you are doing it here</h3>
      <p class="sub">${ev.intro}</p>
      <ol class="practices">${ev.practices.map((p) => {
        const [label, cls] = BADGE[p.status] || BADGE.external;
        return `<li class="practice is-${cls}">
          <div class="practice-head">
            <strong>${p.title}</strong>
            <span class="badge badge-${cls}">${label}</span>
          </div>
          <p class="practice-who">${p.who}</p>
          <p class="practice-where">${p.where}</p>
        </li>`;
      }).join('')}</ol>`;

    const fail = details(`The failure modes — ${ev.failure_modes.length} ways adult improvers stall`);
    fail.insertAdjacentHTML('beforeend', `<ul class="failure-list">${ev.failure_modes.map((f) =>
      `<li><strong>${f.what}.</strong> ${f.why}</li>`).join('')}</ul>`);
    sec.append(fail);

    const myths = details('Checked and not true');
    myths.insertAdjacentHTML('beforeend', `<ul class="failure-list">${ev.myths.map((m) =>
      `<li>${m}</li>`).join('')}</ul>`);
    sec.append(myths);
    root.append(sec);
  }

  // ------------------------------------------------------------- session log
  // Studer: schedule the slots, log every session. The log is the difference
  // between a plan and a habit; 3.5-7 focused hours a week is the target band.
  root.append(renderLog());

  // ----------------------------------------------------------------- the gates
  const gates = document.createElement('section');
  gates.className = 'study-section';
  gates.innerHTML = `<h3>Gates, not dates</h3>
    <p class="sub">${st.timeline_note}</p>
    <ol class="gates">${st.gates.map((g) => `
      <li><span class="gate-at">${g.at}</span><div><strong>${g.what}</strong><p>${g.why}</p></div></li>`).join('')}
    </ol>`;
  root.append(gates);

  // ------------------------------------------------------------- the book ladder
  const books = document.createElement('section');
  books.className = 'study-section';
  books.innerHTML = `<h3>Book ladder</h3>
    <ol class="ladder">${st.books.map((b) => `
      <li class="${b.have ? 'have' : ''}">
        <strong>${b.title}</strong> <span class="author">${b.author}</span>
        ${b.have ? '<em class="badge">in this folder</em>' : `<em class="badge gate">${b.gate}</em>`}
        <p>${b.note}</p>
        ${b.url ? `<a href="${b.url}" target="_blank" rel="noopener">${b.url_label || 'read free'}</a>` : ''}
      </li>`).join('')}
    </ol>`;
  root.append(books);

  // -------------------------------------------------------------------- openings
  const openings = document.createElement('section');
  openings.className = 'study-section';
  openings.innerHTML = `<h3>Openings</h3>
    <p class="sub">${st.openings_note}</p>`;

  const leaks = document.createElement('div');
  leaks.className = 'leak-grid';
  data.openings.leaks.forEach((p) => {
    const cell = document.createElement('figure');
    cell.className = 'leak';
    const host = document.createElement('div');
    host.className = 'mini-board cg-wrap';
    cell.append(host);
    const cap = document.createElement('figcaption');
    cap.innerHTML = `<strong>${esc(p.side)}: ${esc(p.line_san || '(start)')}</strong>
      <span class="leak-move">you play ${esc(p.my_move)}</span>
      <span class="leak-score">${p.n} games · ${p.my_score.toFixed(0)}% score</span>
      <span class="leak-eval">cloud eval ${(p.cloud_cp / 100).toFixed(2)} — ${esc(p.verdict)}</span>
      <span class="leak-eco">${esc(p.eco)}</span>`;
    cell.append(cap);
    leaks.append(cell);
    // Boards are mounted after insertion so chessground can measure them.
    queueMicrotask(() => makeBoard(host, p.fen, { viewOnly: true, orientation: p.side }));
  });
  openings.append(leaks);

  if (data.openings.explorer_available === false) {
    const warn = document.createElement('p');
    warn.className = 'notice';
    warn.textContent =
      'The Lichess opening explorer was unreachable on this run, so there are no pool-comparison ' +
      'columns — these scores are measured against yourself, not against your rating band.';
    openings.append(warn);
  }

  const rep = details(`Repertoire — deprioritised <em>${st.repertoire_note}</em>`);
  rep.className = 'repertoire';
  rep.insertAdjacentHTML('beforeend', `<div class="link-list">${st.repertoire.map((r) => `
    <a href="${r.url}" target="_blank" rel="noopener"><strong>${esc(r.label)}</strong><span>${esc(r.note)}</span></a>`).join('')}</div>`);
  openings.append(rep);
  root.append(openings);

  // ------------------------------------------------------------------ resources
  data.resources.forEach((group) => {
    const sec = document.createElement('section');
    sec.className = 'study-section';
    sec.innerHTML = `<h3>${group.title}</h3><p class="sub">${group.blurb}</p>
      <div class="link-list">${group.items.map((it) => `
        <a href="${it.url}" target="_blank" rel="noopener">
          <strong>${esc(it.label)}</strong><span>${esc(it.note)}</span>
        </a>`).join('')}</div>`;
    root.append(sec);
  });

  // ---------------------------------------------------------------- dead links
  const dead = document.createElement('section');
  dead.className = 'study-section';
  const d = details(`Checked and <strong>not</strong> worth linking — ${data.dead_links.length} resources`);
  d.insertAdjacentHTML('beforeend',
    `<p class="sub">All verified dead or paywalled on ${data.meta.built}. Several still rank highly in search results.</p>
     <table class="data-table"><thead><tr><th>Resource</th><th>Status</th></tr></thead>
     <tbody>${data.dead_links.map((l) => `
       <tr><td>${esc(l.label)}</td><td>${esc(l.status)}</td></tr>`).join('')}</tbody></table>`);
  dead.append(d);
  root.append(dead);

  // -------------------------------------------------------------------- toolkit
  const tools = document.createElement('section');
  tools.className = 'study-section';
  tools.innerHTML = `<h3>Your own toolkit</h3>
    <p class="sub">Already built, already tuned to your measured weaknesses. Run in this order — ` +
    `<code>puzzles profile</code> reads what <code>engine_review</code> writes.</p>
    <table class="data-table"><thead><tr><th>Command</th><th>What it does</th></tr></thead>
    <tbody>${st.toolkit.map((t) => `
      <tr><td><code>${esc(t.cmd)}</code></td><td>${esc(t.does)}</td></tr>`).join('')}</tbody></table>`;
  root.append(tools);
}
