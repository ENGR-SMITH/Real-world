// Walking to a place you clicked.
//
// Straight at the target is fine across an open street, and hopeless the moment
// anything stands in the way: clicking the shop floor from the pavement used to
// have the boy press his nose against the shopfront for a moment and then give
// up.  The walkable world is already a known set of rectangles with a known
// answer to "can a body stand here" (canStand), so the route is found on a grid
// laid over those rectangles -- coarse enough to be instant, fine enough to
// thread the shop doorway.
import { canStand, PLAYER_R, REGIONS } from "./world";

/** grid spacing, in metres: the doorway is 1.9 m wide, so this leaves room to line up */
const CELL = 0.25;
/** never expand more than this many cells; a hopeless click should still be instant */
const MAX_NODES = 20000;

export type Point = { x: number; y: number };

type Bounds = { x0: number; y0: number; nx: number; ny: number };

function bounds(): Bounds {
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const r of REGIONS) {
    if (r[1] < x0) x0 = r[1];
    if (r[3] > x1) x1 = r[3];
    if (r[2] < y0) y0 = r[2];
    if (r[4] > y1) y1 = r[4];
  }
  return {
    x0,
    y0,
    nx: Math.ceil((x1 - x0) / CELL) + 1,
    ny: Math.ceil((y1 - y0) / CELL) + 1,
  };
}

const B = bounds();
const N = B.nx * B.ny;

/** true when a body can stand in this cell; walked once, then remembered */
const open = new Int8Array(N); // -1 unknown, 0 shut, 1 open
let openDoor = false;

function cellOpen(ix: number, iy: number, doors: boolean): boolean {
  if (ix < 0 || iy < 0 || ix >= B.nx || iy >= B.ny) return false;
  const i = iy * B.nx + ix;
  if (open[i] === -1 || openDoor !== doors) {
    const x = B.x0 + ix * CELL;
    const y = B.y0 + iy * CELL;
    if (openDoor !== doors) open.fill(-1);
    openDoor = doors;
    open[i] = canStand(x, y, PLAYER_R, doors) ? 1 : 0;
  }
  return open[i] === 1;
}

function nearestCell(p: Point, doors: boolean): { ix: number; iy: number } | null {
  const ix = Math.round((p.x - B.x0) / CELL);
  const iy = Math.round((p.y - B.y0) / CELL);
  if (cellOpen(ix, iy, doors)) return { ix, iy };
  // a click can land a hand's width inside a shelf: take the closest open cell
  for (let r = 1; r <= 6; r++) {
    for (let dx = -r; dx <= r; dx++) {
      for (let dy = -r; dy <= r; dy++) {
        if (Math.max(Math.abs(dx), Math.abs(dy)) !== r) continue;
        if (cellOpen(ix + dx, iy + dy, doors)) return { ix: ix + dx, iy: iy + dy };
      }
    }
  }
  return null;
}

/**
 * The walkable route from one place to another, as the corners to walk through.
 * Returns null when there is no way there at all, and a single point when the
 * two places can see each other.
 */
export function findPath(from: Point, to: Point, doors: boolean): Point[] | null {
  const start = nearestCell(from, doors);
  const goal = nearestCell(to, doors);
  if (!start || !goal) return null;
  const at = (ix: number, iy: number) => iy * B.nx + ix;
  const si = at(start.ix, start.iy);
  const gi = at(goal.ix, goal.iy);
  const gx = goal.ix;
  const gy = goal.iy;
  if (si === gi) return [{ ...to }];

  const from_ = new Int32Array(N).fill(-1);
  const gScore = new Float32Array(N).fill(Infinity);
  const closed = new Uint8Array(N);
  const heap: { i: number; f: number }[] = [{ i: si, f: 0 }];
  gScore[si] = 0;
  let expanded = 0;

  const push = (i: number, f: number) => {
    heap.push({ i, f });
    let c = heap.length - 1;
    while (c > 0) {
      const p = (c - 1) >> 1;
      if (heap[p].f <= heap[c].f) break;
      const t = heap[p];
      heap[p] = heap[c];
      heap[c] = t;
      c = p;
    }
  };
  const pop = () => {
    const top = heap[0];
    const last = heap.pop() as { i: number; f: number };
    if (heap.length) {
      heap[0] = last;
      let p = 0;
      for (;;) {
        const l = p * 2 + 1;
        const r = l + 1;
        let m = p;
        if (l < heap.length && heap[l].f < heap[m].f) m = l;
        if (r < heap.length && heap[r].f < heap[m].f) m = r;
        if (m === p) break;
        const t = heap[p];
        heap[p] = heap[m];
        heap[m] = t;
        p = m;
      }
    }
    return top;
  };

  const DIAG = Math.SQRT2;
  while (heap.length) {
    const cur = pop();
    if (cur.i === gi) break;
    if (closed[cur.i]) continue;
    closed[cur.i] = 1;
    if (++expanded > MAX_NODES) return null;
    const cx = cur.i % B.nx;
    const cy = (cur.i - cx) / B.nx;
    for (let dy = -1; dy <= 1; dy++) {
      for (let dx = -1; dx <= 1; dx++) {
        if (dx === 0 && dy === 0) continue;
        const ax = cx + dx;
        const ay = cy + dy;
        if (!cellOpen(ax, ay, doors)) continue;
        // no cutting a corner through a shelf
        if (dx !== 0 && dy !== 0 && (!cellOpen(cx + dx, cy, doors) || !cellOpen(cx, cy + dy, doors))) continue;
        const ni = at(ax, ay);
        if (closed[ni]) continue;
        const step = dx !== 0 && dy !== 0 ? DIAG : 1;
        const g = gScore[cur.i] + step;
        if (g < gScore[ni]) {
          gScore[ni] = g;
          from_[ni] = cur.i;
          const h = Math.hypot(ax - gx, ay - gy);
          push(ni, g + h);
        }
      }
    }
  }
  if (from_[gi] < 0 && gi !== si) return null;

  const cell = (i: number): Point => ({
    x: B.x0 + (i % B.nx) * CELL,
    y: B.y0 + ((i - (i % B.nx)) / B.nx) * CELL,
  });
  const raw: Point[] = [];
  for (let i = gi; i >= 0; i = from_[i]) {
    raw.push(cell(i));
    if (i === si) break;
  }
  raw.reverse();
  // straighten: keep only the corners where the direction changes
  const out: Point[] = [];
  for (let i = 0; i < raw.length; i++) {
    const prev = i === 0 ? from : raw[i - 1];
    const next = raw[i + 1];
    if (!next) {
      out.push({ ...to });
      break;
    }
    const a = Math.sign(raw[i].x - prev.x) + "," + Math.sign(raw[i].y - prev.y);
    const b = Math.sign(next.x - raw[i].x) + "," + Math.sign(next.y - raw[i].y);
    if (a !== b) out.push(raw[i]);
  }
  return out.length ? out : null;
}
