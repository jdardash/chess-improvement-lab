// Thin wrapper over chessground: it renders and takes input, but knows no rules.
// chess.js supplies legality; this module is the only place the two meet.
import { Chessground } from '@lichess-org/chessground';
import { Chess } from 'chess.js';

export const COLOR = { w: 'white', b: 'black' };

/** Legal-move map in the shape chessground wants: Map<from, to[]>. */
export function destsOf(chess) {
  const dests = new Map();
  for (const m of chess.moves({ verbose: true })) {
    if (!dests.has(m.from)) dests.set(m.from, []);
    dests.get(m.from).push(m.to);
  }
  return dests;
}

/**
 * A board bound to a chess.js game.
 * onMove receives the chess.js move object after it has been applied.
 */
export function makeBoard(el, fen, { onMove, orientation, viewOnly = false } = {}) {
  const chess = new Chess(fen);
  const turn = COLOR[chess.turn()];

  const cg = Chessground(el, {
    fen,
    orientation: orientation || turn,
    turnColor: turn,
    viewOnly,
    coordinates: true,
    animation: { enabled: true, duration: 180 },
    highlight: { lastMove: true, check: true },
    movable: {
      free: false,
      color: viewOnly ? undefined : turn,
      dests: viewOnly ? new Map() : destsOf(chess),
      showDests: true,
    },
    draggable: { enabled: !viewOnly, showGhost: true },
  });

  if (!viewOnly) {
    cg.set({
      movable: {
        events: {
          after: (orig, dest) => {
            // Drills never need underpromotion; a queen is always at least as good.
            const move = chess.move({ from: orig, to: dest, promotion: 'q' });
            if (!move) return;
            sync();
            onMove?.(move, chess);
          },
        },
      },
    });
  }

  function sync() {
    const t = COLOR[chess.turn()];
    cg.set({
      fen: chess.fen(),
      turnColor: t,
      check: chess.inCheck() ? t : undefined,
      movable: { color: t, dests: destsOf(chess) },
    });
  }

  return {
    cg,
    chess,
    sync,
    /** Play a move the user did not make (engine reply, solution reveal). */
    apply(san) {
      const move = chess.move(san);
      if (!move) return null;
      cg.move(move.from, move.to);
      sync();
      return move;
    },
    lock() {
      cg.set({ viewOnly: true, movable: { color: undefined, dests: new Map() } });
    },
    shapes(list) {
      cg.setAutoShapes(list);
    },
    destroy() {
      cg.destroy();
    },
  };
}

/** Convert a UCI string ("e2e4", "e7e8q") to SAN in the given position, without mutating it. */
export function uciToSan(fen, uci) {
  const c = new Chess(fen);
  const move = c.move({
    from: uci.slice(0, 2),
    to: uci.slice(2, 4),
    promotion: uci.length > 4 ? uci[4] : undefined,
  });
  return move ? move.san : null;
}
