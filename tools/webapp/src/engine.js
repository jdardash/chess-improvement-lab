// Stockfish 10, asm.js build, inlined into the page and started from a Blob URL.
// asm.js was chosen over the WASM builds deliberately: no cross-origin isolation,
// no wasm-unsafe-eval, no companion .wasm file to fetch. ~2900 Elo, which is about
// 1300 more than this page will ever need.
//
// Verified working from file:// in Chromium (blob-URL workers are permitted
// there), but some browsers and hardened configurations refuse to construct a
// Worker from an opaque origin. That is the one failure mode, and it is reported
// rather than silently degraded.

export const ENGINE_UNAVAILABLE =
  'The engine could not start — this browser refused to create a Web Worker. ' +
  'Run `python -m http.server 8000` in this folder and open ' +
  'http://localhost:8000/chess.html instead.';

export function createEngine(source) {
  let worker;
  try {
    const url = URL.createObjectURL(new Blob([source], { type: 'application/javascript' }));
    worker = new Worker(url);
  } catch (err) {
    return { ok: false, reason: ENGINE_UNAVAILABLE, error: err };
  }

  const listeners = new Set();
  worker.onmessage = (e) => {
    const line = typeof e.data === 'string' ? e.data : e.data?.data;
    if (typeof line === 'string') for (const fn of [...listeners]) fn(line);
  };

  const send = (cmd) => worker.postMessage(cmd);

  /** Resolve on the first line matching `test`, rejecting if the engine goes quiet. */
  const waitFor = (test, timeoutMs = 20000) =>
    new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        listeners.delete(fn);
        reject(new Error('engine timeout'));
      }, timeoutMs);
      const fn = (line) => {
        const hit = test(line);
        if (!hit) return;
        clearTimeout(timer);
        listeners.delete(fn);
        resolve(hit === true ? line : hit);
      };
      listeners.add(fn);
    });

  const ready = (async () => {
    send('uci');
    await waitFor((l) => l.startsWith('uciok'));
    send('isready');
    await waitFor((l) => l.startsWith('readyok'));
  })();

  return {
    ok: true,
    ready,
    /** Cap engine strength so a conversion drill stays a drill, not a humiliation. */
    async setSkill(level) {
      await ready;
      send(`setoption name Skill Level value ${Math.max(0, Math.min(20, level))}`);
    },
    async bestMove(fen, { movetime = 500 } = {}) {
      await ready;
      send('ucinewgame');
      send(`position fen ${fen}`);
      const wait = waitFor((l) => {
        const m = /^bestmove\s+(\S+)/.exec(l);
        return m ? m[1] : false;
      });
      send(`go movetime ${movetime}`);
      const uci = await wait;
      return uci === '(none)' ? null : uci;
    },
    /** Centipawn score from the side-to-move's point of view. */
    async evaluate(fen, { depth = 12 } = {}) {
      await ready;
      let score = null;
      const collect = (line) => {
        const m = /score (cp|mate) (-?\d+)/.exec(line);
        if (m) score = m[1] === 'cp' ? Number(m[2]) : (m[2] > 0 ? 10000 : -10000);
      };
      listeners.add(collect);
      send('ucinewgame');
      send(`position fen ${fen}`);
      const wait = waitFor((l) => l.startsWith('bestmove'));
      send(`go depth ${depth}`);
      await wait;
      listeners.delete(collect);
      return score;
    },
    destroy() {
      try { worker.terminate(); } catch { /* already gone */ }
    },
  };
}
