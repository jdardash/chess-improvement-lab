// The Train tab. This is the part of the page that exists to change behaviour
// rather than to inform: every card is gated behind a think timer and an explicit
// Real Chess safety check, because the diagnosis in Personalized Plan.md is a
// discipline failure, not a knowledge failure.

import { makeBoard, uciToSan, COLOR } from './board.js';
import { createEngine } from './engine.js';
import { createEmptyCard, fsrs, generatorParameters, Rating } from 'ts-fsrs';
import { Chess } from 'chess.js';

const STORE_KEY = 'chess-page/train-v1';
const SNAP_SECONDS = 3;   // the plan's definition of a snap move
const scheduler = fsrs(generatorParameters({ enable_fuzz: true }));

// ---------------------------------------------------------------- persistence

function loadStore() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
    for (const card of Object.values(raw.cards || {})) {
      card.due = new Date(card.due);
      card.last_review = card.last_review ? new Date(card.last_review) : undefined;
    }
    return { cards: {}, sessions: [], settings: {}, ...raw };
  } catch {
    return { cards: {}, sessions: [], settings: {} };
  }
}

function saveStore(store) {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(store));
  } catch {
    // A full or disabled localStorage costs scheduling memory, not the drill itself.
  }
}

// ---------------------------------------------------------------------- decks

/** Own blunders become one-move "find the move you missed" cards. */
function ownCard(b, i) {
  return {
    id: `own:${b.url}:${b.move_no}:${b.color}`,
    kind: 'own',
    fen: b.fen,
    solution: [b.best],
    played: b.played,
    cpLoss: b.cp_loss,
    evalBefore: b.eval_before,
    thinkSeconds: b.think_seconds,
    phase: b.phase,
    motifs: b.motifs,
    date: b.date,
    color: b.color,
    moveNo: b.move_no,
    url: b.url,
    index: i,
  };
}

/** Lichess puzzles: moves[0] is the opponent's setup move, then we alternate. */
function puzzleCard(p) {
  return {
    id: `lichess:${p.id}`,
    kind: 'puzzle',
    fen: p.fen,
    line: p.moves,
    rating: p.rating,
    motifs: p.themes,
    url: p.url,
  };
}

/** Endgame drills: verified positions played out against the engine to the goal. */
function endgameCard(d) {
  return {
    id: `eg:${d.id}`,
    kind: 'endgame',
    fen: d.fen,
    label: d.label,
    side: d.side,
    goal: d.goal,
    hint: d.hint,
  };
}

export function buildDecks(data) {
  const own = data.blunders.map(ownCard);
  const winning = own.filter((c, i) => data.blunders[i].eval_before >= 200);
  const rushed = own.filter((c, i) => data.blunders[i].think_seconds < 5);
  const puzzles = data.puzzles.map(puzzleCard);
  const endgames = (data.endgame_drills || []).map(endgameCard);
  const unconverted = data.stats.winning_blunders_unconverted;
  return [
    { key: 'winning', label: 'Winning positions', cards: winning,
      blurb: `Blunders you made while already at +2 or better. ${unconverted} of these games were then not won — the largest recoverable leak in your data.` },
    { key: 'rushed', label: 'Rushed (under 5s)', cards: rushed,
      blurb: 'Blunders played in under five seconds. Free rating: you already knew better, you just moved.' },
    { key: 'all', label: 'All own blunders', cards: own,
      blurb: 'Every position where you lost 200cp or more, at depth 16.' },
    { key: 'lichess', label: 'Lichess motifs', cards: puzzles,
      blurb: 'CC0 Lichess puzzles filtered to the motifs your own blunders give away: hanging piece, pin, fork, skewer.' },
    { key: 'endgames', label: 'Endgames', cards: endgames,
      blurb: 'The must-know endgames, played out against the engine until you reach the goal — ' +
             'no credit for knowing the idea, only for converting it. Every position verified at depth 26.' },
  ];
}

// ------------------------------------------------------------------ scheduling

/** Due cards first (oldest due first), then unseen, then the rest. */
function orderDeck(cards, store, now) {
  const seen = [], unseen = [], future = [];
  for (const c of cards) {
    const rec = store.cards[c.id];
    if (!rec) unseen.push(c);
    else if (rec.due <= now) seen.push(c);
    else future.push(c);
  }
  seen.sort((a, b) => store.cards[a.id].due - store.cards[b.id].due);
  future.sort((a, b) => store.cards[a.id].due - store.cards[b.id].due);
  return [...seen, ...unseen, ...future];
}

function gradeCard(store, id, rating, now) {
  const card = store.cards[id] || createEmptyCard(now);
  const { card: next } = scheduler.next(card, now, rating);
  store.cards[id] = next;
  return next;
}

const humanDue = (due, now) => {
  const mins = Math.round((due - now) / 60000);
  if (mins < 60) return `${Math.max(1, mins)}m`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
};

// ----------------------------------------------------------------------- view

export function renderTrain(root, data) {
  const store = loadStore();
  const decks = buildDecks(data);
  const settings = { minThink: 15, requireChecklist: true, ...store.settings };

  let deck = decks[0];
  let queue = [];
  let pos = 0;
  let session = { shown: 0, solved: 0, snap: 0, moved: 0 };
  let engine = null;

  root.innerHTML = `
    <section class="train">
      <header class="deck-picker" role="tablist" aria-label="Drill deck"></header>
      <p class="deck-blurb"></p>
      <div class="train-grid">
        <div class="board-col"><div class="board-host cg-wrap"></div><div class="board-under"></div></div>
        <aside class="card-col"></aside>
      </div>
      <footer class="session-bar"></footer>
    </section>`;

  const picker = root.querySelector('.deck-picker');
  const blurbEl = root.querySelector('.deck-blurb');
  const boardHost = root.querySelector('.board-host');
  const boardUnder = root.querySelector('.board-under');
  const cardCol = root.querySelector('.card-col');
  const sessionBar = root.querySelector('.session-bar');

  decks.forEach((d) => {
    const b = document.createElement('button');
    b.className = 'deck-tab';
    b.role = 'tab';
    b.innerHTML = `<span>${d.label}</span><em>${d.cards.length}</em>`;
    b.onclick = () => selectDeck(d);
    picker.append(b);
  });

  function selectDeck(d) {
    deck = d;
    [...picker.children].forEach((b, i) => b.setAttribute('aria-selected', decks[i] === d));
    blurbEl.textContent = d.blurb;
    queue = orderDeck(d.cards, store, new Date());
    pos = 0;
    showCard();
  }

  function drawSession() {
    const snapRate = session.moved ? Math.round((session.snap / session.moved) * 100) : 0;
    const accuracy = session.shown ? Math.round((session.solved / session.shown) * 100) : 0;
    sessionBar.innerHTML = `
      <span>this session</span>
      <strong>${session.solved}/${session.shown}</strong><span class="unit">solved (${accuracy}%)</span>
      <strong class="${snapRate > 10 ? 'bad' : 'good'}">${snapRate}%</strong>
      <span class="unit">snap moves — target under 10%</span>
      <button class="link-btn" id="reset-session">reset</button>`;
    sessionBar.querySelector('#reset-session').onclick = () => {
      session = { shown: 0, solved: 0, snap: 0, moved: 0 };
      drawSession();
    };
  }

  function showCard() {
    const card = queue[pos];
    boardUnder.innerHTML = '';
    if (!card) {
      boardHost.innerHTML = '';
      cardCol.innerHTML = `<div class="empty">This deck is empty.</div>`;
      return;
    }
    session.shown++;
    if (card.kind === 'own') runOwnCard(card);
    else if (card.kind === 'endgame') runEndgameCard(card);
    else runPuzzleCard(card);
    drawSession();
  }

  const next = () => { pos = (pos + 1) % Math.max(1, queue.length); showCard(); };

  // ------------------------------------------------------------ card chrome

  /**
   * The gate. Returns { unlock, onFirstMove, panel } — the reveal button stays
   * disabled until the timer has run AND every safety box is ticked.
   */
  function mountPanel(card, { heading, sub, solutionLabel }) {
    const startedAt = performance.now();
    let firstMoveLogged = false;
    let elapsed = 0;

    cardCol.innerHTML = `
      <div class="card-head">
        <div class="card-count">${pos + 1} / ${queue.length}</div>
        <h3>${heading}</h3>
        <p class="card-sub">${sub}</p>
      </div>
      <div class="checklist">
        <p class="checklist-title">Real Chess check — his replies</p>
        <label><input type="checkbox" data-k="checks"> Checks</label>
        <label><input type="checkbox" data-k="captures"> Captures</label>
        <label><input type="checkbox" data-k="threats"> Threats</label>
      </div>
      <div class="timer-row">
        <div class="timer"><span class="timer-fill"></span><span class="timer-text">0.0s</span></div>
        <span class="timer-min">min ${settings.minThink}s</span>
      </div>
      <div class="card-actions">
        <button class="btn reveal" disabled>${solutionLabel}</button>
      </div>
      <div class="verdict" aria-live="polite"></div>`;

    const boxes = [...cardCol.querySelectorAll('.checklist input')];
    const reveal = cardCol.querySelector('.reveal');
    const fill = cardCol.querySelector('.timer-fill');
    const text = cardCol.querySelector('.timer-text');
    const verdict = cardCol.querySelector('.verdict');

    const allTicked = () => !settings.requireChecklist || boxes.every((b) => b.checked);
    const refresh = () => {
      const ready = elapsed >= settings.minThink && allTicked();
      reveal.disabled = !ready;
      reveal.title = ready ? '' :
        elapsed < settings.minThink ? `Wait ${(settings.minThink - elapsed).toFixed(0)}s more`
                                    : 'Tick all three safety checks first';
    };
    boxes.forEach((b) => (b.onchange = refresh));

    const tick = setInterval(() => {
      elapsed = (performance.now() - startedAt) / 1000;
      const pct = Math.min(100, (elapsed / settings.minThink) * 100);
      fill.style.width = `${pct}%`;
      fill.classList.toggle('is-full', pct >= 100);
      text.textContent = `${elapsed.toFixed(1)}s`;
      refresh();
    }, 100);
    refresh();

    return {
      verdict,
      reveal,
      stop: () => clearInterval(tick),
      secondsSoFar: () => (performance.now() - startedAt) / 1000,
      logFirstMove() {
        if (firstMoveLogged) return;
        firstMoveLogged = true;
        const t = (performance.now() - startedAt) / 1000;
        session.moved++;
        if (t < SNAP_SECONDS) session.snap++;
        drawSession();
        return t;
      },
    };
  }

  /** Grading row; FSRS decides when the position comes back. */
  function mountGrades(card, panel, wasCorrect) {
    const now = new Date();
    const row = document.createElement('div');
    row.className = 'grades';
    row.innerHTML = `<span>schedule it:</span>`;
    const options = [
      ['Again', Rating.Again], ['Hard', Rating.Hard],
      ['Good', Rating.Good], ['Easy', Rating.Easy],
    ];
    for (const [label, rating] of options) {
      const b = document.createElement('button');
      b.className = 'btn grade';
      const preview = scheduler.next(store.cards[card.id] || createEmptyCard(now), now, rating).card;
      b.innerHTML = `${label}<em>${humanDue(preview.due, now)}</em>`;
      b.onclick = () => {
        gradeCard(store, card.id, rating, now);
        store.settings = settings;
        saveStore(store);
        panel.stop();
        next();
      };
      row.append(b);
    }
    if (!wasCorrect) row.classList.add('after-miss');
    panel.verdict.append(row);
  }

  // --------------------------------------------------------- own-blunder card

  function runOwnCard(card) {
    const mover = card.color === 'white' ? 'White' : 'Black';
    const evalTxt = card.evalBefore >= 0 ? `+${(card.evalBefore / 100).toFixed(1)}` : (card.evalBefore / 100).toFixed(1);
    // The motif list repeats the phase as one of its tags; drop it so the line
    // does not read "middlegame · middlegame, pin".
    const tactics = (card.motifs || []).filter((m) => m !== card.phase);
    const panel = mountPanel(card, {
      heading: `${card.date} · move ${card.moveNo} as ${mover}`,
      sub: `You were <strong>${evalTxt}</strong> here and lost <strong>${card.cpLoss}cp</strong>. ` +
           `Thought for ${card.thinkSeconds.toFixed(1)}s. ${card.phase}${tactics.length ? ' · ' + tactics.join(', ') : ''}`,
      solutionLabel: 'Reveal the move',
    });

    boardHost.innerHTML = '';
    let settled = false;

    const board = makeBoard(boardHost, card.fen, {
      orientation: card.color,
      onMove: (move) => {
        panel.logFirstMove();
        if (settled) return;
        if (move.san === card.solution[0]) {
          settled = true;
          board.lock();
          panel.verdict.innerHTML = `<p class="hit">Correct — <strong>${move.san}</strong> was the move.</p>`;
          session.solved++;
          drawSession();
          mountGrades(card, panel, true);
        } else if (move.san === card.played) {
          panel.verdict.innerHTML =
            `<p class="miss">That is exactly what you played in the game. It cost ${card.cpLoss}cp. Try again, or reveal.</p>`;
          board.chess.undo();
          board.sync();
        } else {
          panel.verdict.innerHTML = `<p class="miss">${move.san} is not it. Try again, or reveal.</p>`;
          board.chess.undo();
          board.sync();
        }
      },
    });

    panel.reveal.onclick = () => {
      if (settled) return;
      settled = true;
      const move = board.apply(card.solution[0]);
      board.lock();
      panel.verdict.innerHTML =
        `<p class="revealed">The move was <strong>${card.solution[0]}</strong>. You played ${card.played}.</p>`;
      if (move) board.shapes([{ orig: move.from, dest: move.to, brush: 'green' }]);
      mountGrades(card, panel, false);
    };

    boardUnder.innerHTML = `<a class="game-link" href="${card.url}" target="_blank" rel="noopener">open the game on chess.com</a>`;
    if (card.evalBefore >= 200) mountConversionDrill(card);
  }

  // --------------------------------------------------------------- puzzle card

  function runPuzzleCard(card) {
    // Apply the opponent's setup move so the player sees the position they must solve.
    const setup = new Chess(card.fen);
    const first = card.line[0];
    setup.move({ from: first.slice(0, 2), to: first.slice(2, 4), promotion: first[4] });
    const fen = setup.fen();
    const toMove = COLOR[setup.turn()];
    let step = 1;

    const panel = mountPanel(card, {
      heading: `Lichess puzzle · rated ${card.rating}`,
      sub: `${toMove} to play. ${card.motifs.slice(0, 5).join(', ')}`,
      solutionLabel: 'Reveal the line',
    });

    boardHost.innerHTML = '';
    let settled = false;

    const board = makeBoard(boardHost, fen, {
      orientation: toMove,
      onMove: (move) => {
        panel.logFirstMove();
        if (settled) return;
        // chess.js Move carries the FEN it was made from, which is what we need
        // to name the expected UCI reply in SAN.
        const expected = uciToSan(move.before, card.line[step]);
        if (move.san !== expected) {
          panel.verdict.innerHTML = `<p class="miss">${move.san} is not the line. Try again, or reveal.</p>`;
          board.chess.undo();
          board.sync();
          return;
        }
        step++;
        board.sync();
        if (step >= card.line.length) return finish(true);
        // Opponent's forced reply.
        setTimeout(() => {
          const reply = uciToSan(board.chess.fen(), card.line[step]);
          board.apply(reply);
          step++;
          if (step >= card.line.length) finish(true);
        }, 260);
      },
    });

    function finish(correct) {
      settled = true;
      board.lock();
      panel.verdict.innerHTML = correct
        ? `<p class="hit">Solved.</p>`
        : `<p class="revealed">Line played out.</p>`;
      if (correct) { session.solved++; drawSession(); }
      mountGrades(card, panel, correct);
    }

    panel.reveal.onclick = () => {
      if (settled) return;
      const play = () => {
        if (step >= card.line.length) return finish(false);
        const san = uciToSan(board.chess.fen(), card.line[step]);
        if (!san) return finish(false);
        board.apply(san);
        step++;
        setTimeout(play, 320);
      };
      play();
    };

    boardUnder.innerHTML = `<a class="game-link" href="${card.url}" target="_blank" rel="noopener">open on lichess</a>`;
  }

  // -------------------------------------------------------------- endgame card

  /**
   * A must-know endgame, played out against the engine until the goal state.
   * No think-timer gate here: the skill being drilled is technique over many
   * moves, not the single-move safety check. FSRS still schedules the position.
   */
  function runEndgameCard(card) {
    const goalTxt = card.goal === 'win' ? 'Win this position' : 'Hold the draw';
    cardCol.innerHTML = `
      <div class="card-head">
        <div class="card-count">${pos + 1} / ${queue.length}</div>
        <h3>${card.label}</h3>
        <p class="card-sub"><strong class="goal-${card.goal}">${goalTxt}</strong> as ${card.side} — the engine plays on at full strength.</p>
      </div>
      <blockquote class="endgame-hint">${card.hint}</blockquote>
      <div class="card-actions"><button class="btn restart">Restart the position</button></div>
      <div class="verdict" aria-live="polite"></div>`;

    const verdict = cardCol.querySelector('.verdict');
    const panel = { verdict, stop() {}, logFirstMove() {} };
    let graded = false;

    boardUnder.innerHTML = `<p class="convert-status">starting engine…</p>`;
    const status = boardUnder.querySelector('.convert-status');

    const outcome = (chess) => {
      if (chess.isCheckmate()) {
        const winner = COLOR[chess.turn()] === 'white' ? 'black' : 'white';
        return winner === card.side ? 'win' : 'loss';
      }
      if (chess.isStalemate() || chess.isDraw()) return 'draw';
      return null;
    };

    async function start() {
      graded = false;
      verdict.innerHTML = '';
      if (!engine) engine = createEngine(data.engineSource);
      if (!engine.ok) {
        status.className = 'convert-status is-error';
        status.textContent = engine.reason;
        return;
      }
      try {
        await engine.ready;
        await engine.setSkill(20); // technique drills deserve honest defence
      } catch (err) {
        status.className = 'convert-status is-error';
        status.textContent = `Engine failed to start: ${err.message}`;
        return;
      }

      status.className = 'convert-status';
      status.textContent = 'Your move.';
      boardHost.innerHTML = '';

      const board = makeBoard(boardHost, card.fen, {
        orientation: card.side,
        onMove: async (move, chess) => {
          const done = outcome(chess);
          if (done) return finish(done);
          status.textContent = 'engine thinking…';
          const uci = await engine.bestMove(chess.fen(), { movetime: 500 });
          if (!uci) return finish(outcome(chess) || 'draw');
          const san = uciToSan(chess.fen(), uci);
          if (san) board.apply(san);
          const after = outcome(chess);
          if (after) return finish(after);
          status.textContent = `Your move. ${chess.history().length} plies played.`;
        },
      });

      function finish(result) {
        board.lock();
        const success = card.goal === 'win' ? result === 'win' : result !== 'loss';
        status.className = `convert-status ${success ? 'is-win' : 'is-error'}`;
        status.textContent =
          result === 'win' ? 'Converted. That is the technique.'
          : result === 'draw' && card.goal === 'draw' ? 'Held. That is the technique.'
          : result === 'draw' ? 'Drawn — a won position not won. Restart it and find the winning plan.'
          : 'Lost. Restart it — this one is supposed to be held.';
        if (!graded) {
          graded = true;
          if (success) { session.solved++; drawSession(); }
          mountGrades(card, panel, success);
        }
      }
    }

    cardCol.querySelector('.restart').onclick = start;
    start();
  }

  // ---------------------------------------------------- conversion drill (engine)

  /**
   * The drill the data most demands: you were winning here and did not win.
   * Play the position out against a deliberately capped engine.
   */
  function mountConversionDrill(card) {
    const wrap = document.createElement('div');
    wrap.className = 'convert';
    wrap.innerHTML = `
      <button class="btn convert-start">Play this position out</button>
      <span class="convert-note">you were winning here — finish the job</span>`;
    boardUnder.append(wrap);

    wrap.querySelector('.convert-start').onclick = async () => {
      wrap.innerHTML = `<p class="convert-status">starting engine…</p>`;
      const status = wrap.querySelector('.convert-status');

      if (!engine) engine = createEngine(data.engineSource);
      if (!engine.ok) {
        status.className = 'convert-status is-error';
        status.textContent = engine.reason;
        return;
      }
      try {
        await engine.ready;
        await engine.setSkill(8); // roughly club strength; the point is technique, not survival
      } catch (err) {
        status.className = 'convert-status is-error';
        status.textContent = `Engine failed to start: ${err.message}`;
        return;
      }

      status.textContent = 'Your move. Convert it.';
      boardHost.innerHTML = '';
      cardCol.querySelector('.card-actions')?.remove();

      const play = makeBoard(boardHost, card.fen, {
        orientation: card.color,
        onMove: async (move, chess) => {
          if (chess.isGameOver()) return done(chess);
          status.textContent = 'engine thinking…';
          const uci = await engine.bestMove(chess.fen(), { movetime: 400 });
          if (!uci) return done(chess);
          const san = uciToSan(chess.fen(), uci);
          if (san) play.apply(san);
          if (chess.isGameOver()) return done(chess);
          status.textContent = `Your move. ${moveCount(chess)}`;
        },
      });

      const moveCount = (chess) => `${chess.history().length} plies played`;

      function done(chess) {
        play.lock();
        const iWon = chess.isCheckmate() && COLOR[chess.turn()] !== card.color;
        status.className = `convert-status ${iWon ? 'is-win' : 'is-draw'}`;
        status.textContent = iWon
          ? 'Converted. That is the habit.'
          : chess.isCheckmate() ? 'Checkmated — the same way the real game went.'
          : 'Drawn. A won position drawn is the 28% problem in miniature.';
      }
    };
  }

  selectDeck(decks[0]);

  return {
    destroy() { engine?.destroy(); },
  };
}
