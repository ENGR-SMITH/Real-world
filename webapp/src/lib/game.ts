// The playable simulation, ported from game.py.  No rendering, no React: this is
// the same arithmetic the UPBGE build runs, so behaviour matches stage for stage.
import { canStand, groundZ, regionAt, T, WALL, WORLD, type VehicleData } from "./world";
import { applyPhysics } from "./physics";
import { findPath, type Point } from "./path";

export type V3 = { x: number; y: number; z: number };
export type Input = {
  mx: number;
  my: number;
  run: boolean;
  use: boolean;
  /** the left hand: goods only -- take what he is looking at, or put down */
  alt: boolean;
  tab: boolean;
  /** a product picked from the shelf carousel, for this step only */
  collect: string | null;
};
export type Anim = "idle" | "walk" | "reach" | "sit";

export type Actor = {
  id: string;
  name: string;
  pos: V3;
  yaw: number;
  anim: Anim;
  animT: number;
  /** ground speed last frame, so the walk cycle can be played at the right rate */
  speed: number;
  carrying: string | null;
  pending: string | null;
  busyUntil: number;
  vehicle: string | null;
};

export type Vehicle = {
  id: string;
  data: VehicleData;
  pos: V3;
  yaw: number;
  speed: number;
  /** 0 shut, 1 wide open: the car's own door swings by this much */
  doorFrac: number;
  /** where the door is heading, so it swings rather than snaps */
  doorTarget: number;
  /** the door stays open until this moment, then swings shut by itself */
  doorHold: number;
  hailed: boolean;
  driver: string | null;
};

export type Prop = {
  name: string;
  pos: V3;
  held: boolean;
  /** true once it has left its shelf, so only moved items are re-positioned */
  moved: boolean;
  /** how far the item reaches from its middle: it rests on its own base */
  r?: number;
  /** riding in the trolley, and sold once the till has rung it up */
  inCart?: boolean;
  sold?: boolean;
  /** the colour of the packet itself, for the carousel tile */
  colour?: string;
  /** on the counter, waiting to be scanned or already scanned */
  onTill?: "mine" | "scanned";
  /** velocity while it is loose -- it falls, and slides when it is put down */
  v?: V3;
};

/** the shop's trolley: the boy can take hold of it and push it about */
export type Cart = {
  pos: V3;
  yaw: number;
  /** the actor pushing it, or null when it stands where it was left */
  driver: string | null;
  /** what is in the basket, by product name, in the order it went in */
  items: string[];
};

export type Prompt =
  | "take"
  | "drop"
  | "dooropen"
  | "doorclose"
  | "stop"
  | "vehdoor"
  | "enter"
  | "grab"
  | "release"
  | "unload"
  | "takebag"
  | null;

/**
 * The check-out, measured from the blend's own till: the counter runs down the
 * left of the shop with the cashier behind it.  `table` is where the boy's
 * shopping goes when he unloads, `scan` is the cashier's side of the same top and
 * `bag` is where the packed bag ends up.
 */
export const TILL = {
  /**
   * The shop's own till: a counter running down the aisle's east side, a metre
   * and a quarter up.  The boy works from the walkable aisle beside it and the
   * cashier takes over from the far end, so the counter is between them.
   */
  table: [1.95, -7.0, 1.24] as [number, number, number],
  /** the scanner, further along the same top */
  scan: [1.95, -6.0, 1.24] as [number, number, number],
  /** the bag, at the till */
  bag: [1.95, -5.4, 1.24] as [number, number, number],
  /** the cashier, at the far end of the counter */
  stand: [0.45, -7.9] as [number, number],
  yaw: 2.28,
  /** how close the boy has to be to hand things over */
  reach: 2.2,
};

export type ShelfItem = { name: string; colour: string; price: number };

/**
 * One row of the carousel: the goods of a single kind that are on the shelves
 * beside him, in the order he would meet them.  The shop's shelves are branded in
 * runs -- tins on one run, bottles on the next, the brand boxes after them -- so
 * the carousel is laid out the same way, a banner per kind, rather than as one
 * undifferentiated river of things.
 */
export type ShelfRow = {
  /** the kind, used as a key */
  type: string;
  /** what the banner says */
  label: string;
  /** the banner's own colour, taken from the first packet on the run */
  colour: string;
  items: ShelfItem[];
};

/** which run of shelves a product stands on, read from the name the blend gave it */
export function productType(name: string): { type: string; label: string } {
  if (/^dose/i.test(name)) return { type: "tin", label: "Tins" };
  if (/^pul/i.test(name)) return { type: "bottle", label: "Bottles" };
  if (/^cube/i.test(name)) return { type: "box", label: "Packets" };
  return { type: "other", label: "Goods" };
}

/**
 * The colour a run of shelves reads as when the packets themselves have nothing
 * to say.  The blend's brand packets are textured rather than tinted, so the
 * material's colour is plain white and a tile painted from it is a blank square;
 * the shelf banners are the thing that tells one run from the next.
 */
const RUN_COLOUR: Record<string, string> = {
  tin: "#c2410c",
  bottle: "#1d4ed8",
  box: "#b45309",
  other: "#475569",
};

function bannerColour(hex: string, type: string): string {
  const fallback = RUN_COLOUR[type] ?? "#475569";
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return fallback;
  const v = parseInt(m[1], 16);
  const r = (v >> 16) & 255;
  const g = (v >> 8) & 255;
  const b = v & 255;
  const max = Math.max(r, g, b);
  const sat = max === 0 ? 0 : (max - Math.min(r, g, b)) / max;
  if (sat < 0.25 || max > 242) return fallback;
  return `#${m[1].toLowerCase()}`;
}

/**
 * Is he in the mall?  The carousel is the shelf he is standing at, and there are
 * no shelves out on the street, so the whole strip stays away until he is through
 * the shop door -- the simulation owns the region, so it answers.
 */
export function inShop(x: number, y: number): boolean {
  return regionAt(x, y)?.[0] === "shop";
}

export type Snapshot = {
  prompt: Prompt;
  target: string | null;
  active: number;
  carrying: string | null;
  inVehicle: boolean;
  speed: number;
  doorOpen: number;
  /** true while the boy is pushing the trolley */
  cart: boolean;
  /** true while he is on his way to a clicked spot */
  walking: boolean;
  /** the shelves beside him, one row per kind of goods, for the carousel */
  shelf: ShelfRow[];
  /** how many things are in the trolley */
  trolley: number;
  /** what the till has rung up */
  receipt: { name: string; price: number }[];
  total: number;
  /** the packed bag is on the counter, waiting for him */
  bag: boolean;
  /** the product he is off to fetch, or null */
  task: string | null;
  /** true while he is inside the mall, which is what the carousel waits for */
  inShop: boolean;
};

const clamp = (v: number, a: number, b: number) => (v < a ? a : v > b ? b : v);

export const fwd = (yaw: number) => ({ x: Math.sin(yaw), y: -Math.cos(yaw) });
const rightOf = (yaw: number) => ({ x: Math.cos(yaw), y: Math.sin(yaw) });

function makeActor(id: string, name: string, x: number, y: number): Actor {
  return {
    id,
    name,
    pos: { x, y, z: groundZ(x, y) ?? 0 },
    yaw: 0,
    anim: "idle",
    animT: 0,
    speed: 0,
    carrying: null,
    pending: null,
    busyUntil: 0,
    vehicle: null,
  };
}

export class Game {
  time = 0;
  doorOpen = 0;
  doorTarget = 0;
  active = 0;
  actors: Actor[];
  vehicles: Vehicle[] = [];
  props: Prop[] = [];
  /** the same props, by name: hundreds of shelf items would be slow to scan */
  propIndex = new Map<string, Prop>();
  /** the trolley */
  cart: Cart = { pos: { x: 0.2, y: -3.88, z: 0.046 }, yaw: 0, driver: null, items: [] };
  cartReach = 0.45;
  /** where a click asked the boy to walk, or null */
  walkTarget: { x: number; y: number } | null = null;
  /** the corners of the route to walkTarget; null until a click works one out */
  walkPath: Point[] | null = null;
  /** an action picked from a highlight: the boy walks over, then does it */
  queued: { kinds: Prompt[]; x: number; y: number; at: number } | null = null;
  /** what the physics did on the last step, for the scripted checks */
  physics: ReturnType<typeof applyPhysics> = { bumped: 0, moving: 0, jammed: false };
  private stuckFor = 0;
  note = "";

  constructor() {
    // the two boys spawn where the blend puts them
    this.actors = [
      makeActor("P1", "Boy 1 (blue)", -5.35, 6.0),
      makeActor("P2", "Boy 2 (white)", -5.55, 7.4),
    ];
    for (const [id, data] of Object.entries(WORLD.vehicles as Record<string, VehicleData>)) {
      this.vehicles.push({
        id,
        data,
        pos: { x: data.lane, y: id === "SUV_root" ? -18.5 : 15.65, z: 0 },
        yaw: data.yaw,
        speed: data.cruise,
        doorFrac: 0,
        doorTarget: 0,
        doorHold: 0,
        hailed: false,
        driver: null,
      });
    }
    for (const [name, p] of Object.entries(WORLD.props_world)) {
      this.addProp(name, { x: p[0], y: p[1], z: p[2] });
    }
  }

  private addProp(name: string, pos: V3, r?: number): Prop {
    const p: Prop = { name, pos: { ...pos }, held: false, moved: false, r };
    this.props.push(p);
    this.propIndex.set(name, p);
    return p;
  }

  /**
   * Everything on the shelves, handed over once the scene has been read.  The
   * export names no products -- they are tins, bottles and plain boxes -- so the
   * renderer worked them out from their size and handed the list here.
   */
  setProducts(list: { name: string; pos: V3; r?: number; colour?: string }[]) {
    for (const it of list) {
      const known = this.propIndex.get(it.name);
      if (known) {
        known.r = it.r;
        known.colour = it.colour;
      } else {
        const added = this.addProp(it.name, it.pos, it.r);
        added.colour = it.colour;
      }
    }
  }

  /** the trolley's own place in the blend */
  setCart(home: { x: number; y: number }, reach: number) {
    if (this.cart.driver === null) this.cart.pos = { x: home.x, y: home.y, z: groundZ(home.x, home.y) ?? 0.046 };
    this.cartReach = reach;
  }

  get player(): Actor {
    return this.actors[this.active];
  }

  // ---------------------------------------------------------------- movement
  /** keyboard, click and scripted walking all end up here */
  moveActor(a: Actor, mx: number, my: number, run: boolean, camYaw: number, dt: number) {
    if (mx === 0 && my === 0) {
      a.speed = 0;
      if (a.anim !== "reach" && a.anim !== "sit") a.anim = "idle";
      return 0;
    }
    const f = fwd(camYaw);
    const r = rightOf(camYaw);
    // rightOf() is really his left: the simulation's axes are Blender's, where a
    // positive turn about +z is anticlockwise on the floor plan.  Feeding the
    // arrow keys through it walked him the wrong way -- press right, go left.
    let dx = f.x * my - r.x * mx;
    let dy = f.y * my - r.y * mx;
    const len = Math.hypot(dx, dy);
    if (len < 1e-6) return 0;
    dx /= len;
    dy /= len;
    const wantYaw = Math.atan2(dx, -dy);
    const diff = ((wantYaw - a.yaw + Math.PI) % (2 * Math.PI)) - Math.PI;
    a.yaw += clamp(diff, -T.TURN_RATE * dt, T.TURN_RATE * dt);

    const speed = run ? T.RUN_SPEED : T.WALK_SPEED;
    const ff = fwd(a.yaw);
    const step = { x: ff.x * speed * dt, y: ff.y * speed * dt };
    const doors = this.doorOpen > 0.5;
    // If the boy is standing where he could not stand (a solid that reaches over
    // the spot he walked into, a spawn point inside a step) every direction looks
    // blocked and he freezes.  When that happens, let him walk out.
    const stuck = !canStand(a.pos.x, a.pos.y, undefined, doors);
    const free = (x: number, y: number) => stuck || canStand(x, y, undefined, doors);
    let moved = 0;
    const nx = a.pos.x + step.x;
    const ny = a.pos.y + step.y;
    if (free(nx, ny)) {
      a.pos.x = nx;
      a.pos.y = ny;
      moved = speed;
    } else if (free(nx, a.pos.y)) {
      a.pos.x = nx;
      moved = speed;
    } else if (free(a.pos.x, ny)) {
      a.pos.y = ny;
      moved = speed;
    }
    a.pos.z = groundZ(a.pos.x, a.pos.y) ?? a.pos.z;
    a.speed = moved;
    if (a.carrying === null && a.anim !== "reach") a.anim = moved > 0 ? "walk" : "idle";
    return moved;
  }

  // ---------------------------------------------------------------- trolley
  cartDist(a: Actor) {
    return Math.hypot(a.pos.x - this.cart.pos.x, a.pos.y - this.cart.pos.y);
  }

  /** the trolley rides in front of whoever is pushing it, at their heading */
  private updateCart(a: Actor) {
    const c = this.cart;
    if (c.driver === null || c.driver !== a.id) return;
    const f = fwd(a.yaw);
    const hold = this.cartReach + 0.42;
    c.pos.x = a.pos.x + f.x * hold;
    c.pos.y = a.pos.y + f.y * hold;
    c.pos.z = groundZ(c.pos.x, c.pos.y) ?? a.pos.z;
    c.yaw = a.yaw;
  }

  grabCart(a: Actor) {
    this.cart.driver = a.id;
    this.note = "took hold of the trolley";
  }

  releaseCart() {
    this.cart.driver = null;
    this.note = "let go of the trolley";
  }

  // ---------------------------------------------------------------- the shopping
  /** what the boy has put on the counter, and what the till has rung up */
  till: { mine: string[]; scanned: string[] } = { mine: [], scanned: [] };
  receipt: { name: string; price: number }[] = [];
  total = 0;
  /** the packed bag: on the counter until he picks it up, then in his hand */
  bag: "none" | "counter" | "carried" = "none";
  /** his errand -- fetch one product and put it in the trolley */
  task: {
    want: string;
    stage: "cart" | "walk" | "putin";
    at: number;
    /** where the errand last told him to go, so the route is not re-planned */
    aim: { x: number; y: number } | null;
  } | null = null;
  /** the cashier, behind the counter: she works through whatever he unloads */
  cashier = {
    pos: { x: TILL.stand[0], y: TILL.stand[1], z: 0.046 } as V3,
    yaw: TILL.yaw,
    anim: "idle" as Anim,
    holding: null as string | null,
    stage: "idle" as "idle" | "reach" | "scan" | "pack",
    until: 0,
  };

  /** the price on the tin: the same product always costs the same */
  priceOf(name: string) {
    let h = 7;
    for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) % 99991;
    return Math.round((0.89 + (h % 411) / 100) * 100) / 100;
  }

  /**
   * What is on the shelves beside him, gathered into one row per kind of goods and
   * nearest run first.  This is what the carousel shows: the actual goods within a
   * few steps, so the tiles always match the shelf he is standing at -- and nothing
   * at all when he is out on the street.
   */
  shelfNear(a: Actor, range = 4.6, max = 12): ShelfRow[] {
    if (!inShop(a.pos.x, a.pos.y)) return [];
    const near: { d: number; item: ShelfItem; type: string; label: string }[] = [];
    const doors = this.doorOpen > 0.5;
    for (const p of this.props) {
      if (p.held || p.inCart || p.sold || p.onTill) continue;
      const d = Math.hypot(p.pos.x - a.pos.x, p.pos.y - a.pos.y);
      if (d > range) continue;
      // Only what he can actually get to.  The carousel is a promise that the boy
      // will fetch the tile that was clicked, and a shelf whose whole front is
      // another shelf is a promise this place cannot keep.
      if (!this.reachable(p, doors)) continue;
      const kind = productType(p.name);
      near.push({
        d,
        type: kind.type,
        label: kind.label,
        item: {
          name: p.name,
          colour: bannerColour(p.colour ?? "#c8a24a", kind.type),
          price: this.priceOf(p.name),
        },
      });
    }
    near.sort((x, y) => x.d - y.d);
    // walk outwards, filling a row per kind as it is met, so the nearest run of
    // shelves leads the strip and each row keeps its shelf order
    const rows = new Map<string, ShelfRow>();
    const cap = Math.max(4, Math.ceil(max / 3));
    for (const n of near) {
      let row = rows.get(n.type);
      if (!row) {
        row = { type: n.type, label: n.label, colour: n.item.colour, items: [] };
        rows.set(n.type, row);
      }
      if (row.items.length < cap) row.items.push(n.item);
    }
    return [...rows.values()];
  }

  /** is there anywhere to stand within arm's reach of this thing? */
  reachable(p: Prop, doors: boolean) {
    const r = T.PLAYER_R;
    for (let i = 0; i < 8; i++) {
      const ang = (i / 8) * Math.PI * 2;
      const x = p.pos.x + Math.cos(ang) * 0.6;
      const y = p.pos.y + Math.sin(ang) * 0.6;
      if (canStand(x, y, r, doors) && !this.cartOccupies(x, y)) return true;
    }
    return false;
  }

  /** the trolley is a body in the world: do not send him to stand inside it */
  private cartOccupies(x: number, y: number) {
    return Math.hypot(x - this.cart.pos.x, y - this.cart.pos.y) < this.cartReach + 0.35;
  }

  /** a tile was clicked: go to that product, pick it up and trolley it */
  collect(name: string) {
    const p = this.propIndex.get(name);
    const a = this.player;
    if (!p || p.held || p.inCart || p.sold || a.vehicle !== null) return false;
    if (this.cart.driver !== null && this.cart.driver !== a.id) {
      this.note = "the trolley is not mine to fill";
      return false;
    }
    this.queued = null;
    this.walkPath = null;
    this.task = { want: name, stage: this.cart.driver === a.id ? "walk" : "cart", at: this.time, aim: null };
    this.walkTarget = { x: p.pos.x, y: p.pos.y };
    this.note = `fetching ${name}`;
    return true;
  }

  /** out of his hand and into the basket */
  putInTrolley(a: Actor, name: string) {
    const p = this.propIndex.get(name);
    if (!p) return;
    p.held = false;
    p.moved = true;
    p.inCart = true;
    p.v = { x: 0, y: 0, z: 0 };
    if (a.carrying === name) a.carrying = null;
    if (a.pending === name) a.pending = null;
    this.cart.items.push(name);
    this.note = `${name} in the trolley`;
  }

  /** one thing out of the trolley and onto the counter, for the cashier */
  unloadOne(): string | null {
    const name = this.cart.items.pop() ?? null;
    if (!name) return null;
    const p = this.propIndex.get(name);
    if (p) {
      p.inCart = false;
      p.moved = true;
      p.onTill = "mine";
    }
    this.till.mine.push(name);
    this.note = `${name} on the counter`;
    return name;
  }

  nearTill(a: Actor) {
    return Math.hypot(a.pos.x - TILL.table[0], a.pos.y - TILL.table[1]) < TILL.reach;
  }

  bagDist(a: Actor) {
    return Math.hypot(a.pos.x - TILL.bag[0], a.pos.y - TILL.bag[1]);
  }

  /**
   * The cashier's job, in four beats: pick the next thing off the counter, run it
   * over the scanner (which puts it on the receipt and adds it up), and when the
   * counter is clear, bag the lot and leave the bag for the boy.
   */
  updateCashier(dt: number) {
    const c = this.cashier;
    if (dt <= 0 || this.time < c.until) return;
    if (c.stage === "idle") {
      if (this.till.mine.length > 0) {
        c.stage = "reach";
        c.anim = "reach";
        c.until = this.time + 0.5;
      } else if (this.till.scanned.length > 0 && this.bag === "none") {
        c.stage = "pack";
        c.anim = "reach";
        c.until = this.time + 0.8;
      } else {
        c.anim = "idle";
      }
      return;
    }
    if (c.stage === "reach") {
      const name = this.till.mine[0];
      if (!name) {
        c.stage = "idle";
        return;
      }
      c.holding = name;
      const p = this.propIndex.get(name);
      if (p) {
        p.moved = true;
        p.onTill = "scanned";
      }
      c.stage = "scan";
      c.until = this.time + 0.65;
      return;
    }
    if (c.stage === "scan") {
      const name = this.till.mine.shift();
      if (name) {
        const price = this.priceOf(name);
        this.receipt.push({ name, price });
        this.total = Math.round((this.total + price) * 100) / 100;
        this.till.scanned.push(name);
        this.note = `${name} — ${price.toFixed(2)}`;
      }
      c.holding = null;
      c.stage = "idle";
      c.until = this.time + 0.3;
      return;
    }
    if (c.stage === "pack") {
      for (const n of this.till.scanned) {
        const p = this.propIndex.get(n);
        if (p) {
          p.sold = true;
          p.onTill = undefined;
          p.moved = true;
        }
      }
      this.till.scanned = [];
      this.bag = "counter";
      c.stage = "idle";
      c.until = this.time + 0.6;
      this.note = "your shopping is bagged";
    }
  }

  /** aim the errand at a point, working out a fresh route only when it moves: a
   *  route recomputed every step dithers between two equally good cells and the
   *  boy paces back and forth instead of walking */
  private aimTask(x: number, y: number) {
    const t = this.task;
    if (!t) return;
    const changed =
      !t.aim || Math.abs(t.aim.x - x) >= 0.05 || Math.abs(t.aim.y - y) >= 0.05;
    if (changed) {
      t.aim = { x, y };
      this.walkPath = null;
    }
    // always restore it: the walk below drops a target it has been led to for
    // three quarters of a second, and a task that did not put it back would leave
    // him standing in the middle of the aisle until it gave up
    this.walkTarget = { x, y };
  }

  /** the boy's own errand, run from the step so it can walk him about */
  private runTask(dt: number) {
    const t = this.task;
    if (!t) return;
    const a = this.player;
    const cart = this.cart;
    // a stage that has not moved on in twenty-five seconds is not going to: the
    // way is shut, the product is gone, or the trolley has been taken by someone else
    if (this.time - t.at > 25) {
      this.task = null;
      this.walkTarget = null;
      this.walkPath = null;
      this.note = "left it — I cannot get there";
      return;
    }
    if (t.stage === "cart") {
      if (cart.driver === a.id) {
        t.stage = "walk";
        this.walkPath = null;
        return;
      }
      if (cart.driver !== null) {
        this.task = null;
        return;
      }
      if (this.cartDist(a) < T.TAKE_RANGE + 0.35) {
        this.grabCart(a);
        t.stage = "walk";
        t.at = this.time;
        this.walkPath = null;
        return;
      }
      this.aimTask(cart.pos.x, cart.pos.y);
      return;
    }
    const p = this.propIndex.get(t.want);
    if (!p || p.sold || p.onTill) {
      this.task = null;
      this.walkTarget = null;
      return;
    }
    if (t.stage === "walk") {
      if (a.carrying === t.want) {
        t.stage = "putin";
        this.walkPath = null;
        return;
      }
      const d = this.propDist(a, p);
      if (this.time < a.busyUntil) return; // his hand is still out
      if (d < T.TAKE_RANGE * 0.9) {
        // Turn on the spot rather than walking: he is holding the trolley, and
        // a step forward shoves it between him and the shelf for ever.
        const want = Math.atan2(p.pos.x - a.pos.x, -(p.pos.y - a.pos.y));
        const diff = ((want - a.yaw + Math.PI) % (2 * Math.PI)) - Math.PI;
        a.yaw += clamp(diff, -T.TURN_RATE * dt, T.TURN_RATE * dt);
        a.speed = 0;
        // close enough to reach round it, or pointed straight at it: take it
        if (d < 1.1 || this.facingAngle(a, p) < T.FACE_CONE) {
          this.doInteraction(a, { kind: "take", payload: p });
          t.stage = "putin";
          t.at = this.time;
          this.walkPath = null;
          this.walkTarget = null;
          return;
        }
        return;
      }
      this.aimTask(p.pos.x, p.pos.y);
      return;
    }
    // putin: still carrying it -- walk back to the trolley and drop it in
    if (a.carrying !== t.want) {
      // he put it down somewhere else, or the trolley changed hands
      this.task = null;
      this.walkTarget = null;
      return;
    }
    if (cart.driver !== a.id) {
      if (cart.driver === null && this.cartDist(a) < T.TAKE_RANGE + 0.35) this.grabCart(a);
      else {
        this.aimTask(cart.pos.x, cart.pos.y);
        return;
      }
    }
    const d = Math.hypot(a.pos.x - cart.pos.x, a.pos.y - cart.pos.y);
    if (d < this.cartReach + 0.8) {
      this.putInTrolley(a, t.want);
      this.task = null;
      this.walkTarget = null;
      this.walkPath = null;
      return;
    }
    this.aimTask(cart.pos.x, cart.pos.y);
  }

  // ---------------------------------------------------------------- doors
  shopDoorDist(a: Actor) {
    const c = WORLD.shop_door_centre;
    return Math.hypot(a.pos.x - c[0], a.pos.y - c[1]);
  }

  updateDoors(dt: number) {
    this.doorOpen += clamp(this.doorTarget - this.doorOpen, -1.6 * dt, 1.6 * dt);
  }

  // ---------------------------------------------------------------- props
  propDist(a: Actor, p: Prop) {
    return Math.hypot(a.pos.x - p.pos.x, a.pos.y - p.pos.y);
  }

  /** radians between the way the boy is looking and the item */
  facingAngle(a: Actor, p: Prop) {
    const dx = p.pos.x - a.pos.x;
    const dy = p.pos.y - a.pos.y;
    const d = Math.hypot(dx, dy);
    if (d < 1e-6) return 0;
    const f = fwd(a.yaw);
    return Math.acos(clamp((f.x * dx + f.y * dy) / d, -1, 1));
  }

  carryPoint(a: Actor): V3 {
    const f = fwd(a.yaw);
    const left = { x: -f.y, y: f.x };
    return {
      x: a.pos.x + f.x * 0.3 + left.x * 0.17,
      y: a.pos.y + f.y * 0.3 + left.y * 0.17,
      z: a.pos.z + 1.02,
    };
  }

  pickUp(a: Actor, p: Prop) {
    a.carrying = p.name;
    a.pending = p.name;
    p.held = true;
    p.moved = true;
    p.v = { x: 0, y: 0, z: 0 };
    a.busyUntil = this.time + T.REACH_TIME;
    a.anim = "reach";
    a.animT = 0;
    this.note = `taking ${p.name}`;
  }

  drop(a: Actor) {
    const p = this.props.find((q) => q.name === a.carrying);
    if (p) {
      const f = fwd(a.yaw);
      // it leaves his hand and has its own life from here: a little way ahead,
      // a little of the speed he was moving, and it stands on the floor rather
      // than floating at the height of his hand
      p.pos = {
        x: a.pos.x + f.x * 0.42,
        y: a.pos.y + f.y * 0.42,
        z: a.pos.z + 0.9,
      };
      p.v = { x: f.x * 0.5 + a.speed * 0.3, y: f.y * 0.5 + a.speed * 0.3, z: 0 };
      p.held = false;
      p.moved = true;
    }
    this.note = `put down ${a.carrying}`;
    a.carrying = null;
    a.pending = null;
  }

  // ---------------------------------------------------------------- vehicles
  nearVehicle(a: Actor): { v: Vehicle; d: number } | null {
    let best: { v: Vehicle; d: number } | null = null;
    for (const v of this.vehicles) {
      const f = fwd(v.yaw);
      const cx = v.pos.x + f.x * v.data.body_fwd;
      const cy = v.pos.y + f.y * v.data.body_fwd;
      const d = Math.hypot(a.pos.x - cx, a.pos.y - cy);
      if (d < v.data.reach && (best === null || d < best.d)) best = { v, d };
    }
    return best;
  }

  cabin(v: Vehicle, seat: [number, number, number]): V3 {
    const f = fwd(v.yaw);
    const r = rightOf(v.yaw);
    return {
      x: v.pos.x + f.x * seat[0] + r.x * seat[1],
      y: v.pos.y + f.y * seat[0] + r.y * seat[1],
      z: v.pos.z + seat[2],
    };
  }

  wrapVehicle(v: Vehicle) {
    const d = v.data;
    const span = d.wrap[1] - d.wrap[0];
    if (v.pos.y > d.wrap[1]) v.pos.y -= span;
    else if (v.pos.y < d.wrap[0]) v.pos.y += span;
    v.pos.x = clamp(v.pos.x, d.road[0], d.road[1]);
  }

  autoDrive(v: Vehicle, dt: number) {
    const d = v.data;
    let target = v.hailed ? 0 : d.cruise;
    const f = fwd(v.yaw);
    const r = rightOf(v.yaw);
    for (const a of this.actors) {
      if (a.vehicle !== null || a.id !== this.player.id) continue;
      const rx = a.pos.x - v.pos.x;
      const ry = a.pos.y - v.pos.y;
      const ahead = rx * f.x + ry * f.y;
      const lat = rx * r.x + ry * r.y;
      // brake for the player standing in the lane ahead
      if (ahead > 0.5 && ahead < T.CAR_SEES_PLAYER && Math.abs(lat) < d.width * 0.6) target = 0;
    }
    v.speed += clamp(target - v.speed, -T.CAR_BRAKE * dt, 2.5 * dt);
    const sign = f.y >= 0 ? 1 : -1;
    const tox = d.lane - v.pos.x;
    const toy = v.pos.y + sign * 8 - v.pos.y;
    if (Math.hypot(tox, toy) > 0.01) {
      const want = Math.atan2(tox, -toy);
      const err = ((want - v.yaw + Math.PI) % (2 * Math.PI)) - Math.PI;
      v.yaw += clamp(err, -0.8 * dt, 0.8 * dt);
    }
    const ff = fwd(v.yaw);
    v.pos.x += ff.x * v.speed * dt;
    v.pos.y += ff.y * v.speed * dt;
    this.wrapVehicle(v);
  }

  drive(v: Vehicle, mx: number, my: number, dt: number) {
    if (my > 0) v.speed += T.CAR_ACC * dt * my;
    else if (my < 0) {
      if (v.speed > 0.15) v.speed -= T.CAR_BRAKE * dt;
      else v.speed -= T.CAR_ACC * 0.6 * dt;
    } else v.speed -= clamp(v.speed, -T.CAR_COAST * dt, T.CAR_COAST * dt);
    v.speed = clamp(v.speed, -T.CAR_MAX_REV, T.CAR_MAX_FWD);
    if (Math.abs(v.speed) > 0.2 && mx !== 0) {
      const grip = 1 - 0.45 * Math.min(1, Math.abs(v.speed) / T.CAR_MAX_FWD);
      v.yaw += mx * T.CAR_STEER * dt * grip * (v.speed >= 0 ? 1 : -1);
    }
    const f = fwd(v.yaw);
    const nx = v.pos.x + f.x * v.speed * dt;
    const ny = v.pos.y + f.y * v.speed * dt;
    const d = v.data;
    const inside =
      nx >= d.road[0] && nx <= d.road[1] && ny >= d.wrap[0] + 0.4 && ny <= d.wrap[1] - 0.4;
    if (inside) {
      v.pos.x = nx;
      v.pos.y = ny;
    } else {
      v.speed *= 0.25;
      v.pos.x = clamp(v.pos.x, d.road[0], d.road[1]);
      v.pos.y = clamp(v.pos.y, d.wrap[0] + 0.4, d.wrap[1] - 0.4);
    }
  }

  enterVehicle(v: Vehicle, a: Actor) {
    v.driver = a.id;
    a.vehicle = v.id;
    v.speed = 0;
    v.hailed = true;
    // the door swings shut behind him a moment after he is in his seat
    v.doorTarget = 0;
    v.doorHold = this.time + 0.5;
    a.carrying = null;
    a.pending = null;
    a.anim = "sit";
    a.animT = 0;
    this.note = `entered ${v.id}`;
  }

  leaveVehicle(v: Vehicle, a: Actor) {
    // he has got out: the car is nobody's now, so it pulls away again instead of
    // standing in the road waiting forever
    v.hailed = false;
    const f = fwd(v.yaw);
    const r = rightOf(v.yaw);
    const side = v.data.getout_side;
    const cx = v.pos.x + f.x * v.data.body_fwd;
    const cy = v.pos.y + f.y * v.data.body_fwd;
    const doors = this.doorOpen > 0.5;
    const spots: V3[] = [];
    for (const dist of [v.data.width * 0.5 + 0.8, v.data.width * 0.5 + 1.3, 2.8]) {
      for (const s of [side, -side]) {
        const x = cx + r.x * dist * s;
        const y = cy + r.y * dist * s;
        spots.push({ x, y, z: 0 });
        spots.push({ x: x + f.x * 2.2, y: y + f.y * 2.2, z: 0 });
        spots.push({ x: x - f.x * 2.2, y: y - f.y * 2.2, z: 0 });
      }
    }
    const spot = spots.find((s) => canStand(s.x, s.y, undefined, doors));
    const at = spot ?? { x: cx, y: cy, z: 0 };
    a.pos = { x: at.x, y: at.y, z: groundZ(at.x, at.y) ?? 0 };
    a.yaw = v.yaw;
    a.anim = "idle";
    v.driver = null;
    a.vehicle = null;
    // he is standing on the pavement: the door opens wide for him, then swings
    // shut again a moment later
    v.doorTarget = 1;
    v.doorHold = this.time + 0.9;
    this.note = `left ${v.id}`;
  }

  updateVehicles(dt: number) {
    for (const v of this.vehicles) {
      // The door is a hinge, not a switch: it swings at its own rate towards
      // wherever it is heading, and a door nobody is waiting at heads shut.  A
      // door that snaps open reads as a glitch, which is exactly what it was.
      if (this.time > v.doorHold && v.doorTarget > 0) v.doorTarget = 0;
      const swing = 2.2 * dt;
      if (v.doorFrac < v.doorTarget) v.doorFrac = Math.min(v.doorTarget, v.doorFrac + swing);
      else if (v.doorFrac > v.doorTarget) v.doorFrac = Math.max(v.doorTarget, v.doorFrac - swing);
      if (v.driver === null) {
        this.autoDrive(v, dt);
      } else {
        const a = this.actors.find((x) => x.id === v.driver);
        if (a) {
          a.pos = this.cabin(v, v.data.seat);
          a.yaw = v.yaw;
        }
      }
    }
  }

  // ---------------------------------------------------------------- context action
  interaction(a: Actor): { kind: Exclude<Prompt, null>; d: number; payload: Prop | Vehicle | null } | null {
    const cands: { kind: Exclude<Prompt, null>; d: number; payload: Prop | Vehicle | null }[] = [];
    if (a.carrying !== null) cands.push({ kind: "drop", d: 0, payload: null });

    // the till: hand things over one at a time, and take the bag when it is ready
    if (a.vehicle === null) {
      if (this.cart.items.length > 0 && this.nearTill(a)) {
        cands.push({ kind: "unload", d: 0.9, payload: null });
      }
      if (this.bag === "counter" && this.bagDist(a) < T.TAKE_RANGE + 0.5) {
        cands.push({ kind: "takebag", d: 0.6, payload: null });
      }
    }

    // items within reach: the one the boy is looking at wins, else the nearest
    const reach = this.props
      .filter((p) => !p.held && p.name !== a.carrying)
      .map((p) => ({ ang: this.facingAngle(a, p), d: this.propDist(a, p), p }))
      .filter((c) => c.d < T.TAKE_RANGE);
    let facedTake: Prop | null = null;
    if (reach.length) {
      const faced = reach.filter((c) => c.ang < T.FACE_CONE);
      const pick = faced.length
        ? faced.reduce((m, c) => (c.ang < m.ang ? c : m))
        : reach.reduce((m, c) => (c.d < m.d ? c : m));
      if (faced.length) facedTake = pick.p;
      cands.push({ kind: "take", d: pick.d, payload: pick.p });
    }

    // the trolley: take hold of it, or let it go once you are pushing it
    if (a.vehicle === null) {
      if (this.cart.driver === a.id) cands.push({ kind: "release", d: 0, payload: null });
      else if (this.cart.driver === null) {
        const cd = this.cartDist(a);
        if (cd < T.TAKE_RANGE + 0.35) cands.push({ kind: "grab", d: cd, payload: null });
      }
    }

    const nv = this.nearVehicle(a);
    if (nv) {
      const { v, d } = nv;
      if (v.driver === null) {
        if (v.data.door !== null && v.doorFrac > 0.8) cands.push({ kind: "enter", d: 0.4, payload: v });
        else if (Math.abs(v.speed) > 0.35) cands.push({ kind: "stop", d, payload: v });
        else if (v.data.door !== null) cands.push({ kind: "vehdoor", d, payload: v });
        else cands.push({ kind: "enter", d, payload: v });
      }
    }
    if (this.shopDoorDist(a) < 2.3) {
      cands.push({ kind: this.doorTarget > 0.5 ? "doorclose" : "dooropen", d: this.shopDoorDist(a), payload: null });
    }
    if (!cands.length) return null;
    cands.sort((x, y) => x.d - y.d);
    // A product he is looking at beats everything else he could be doing from
    // where he stands -- letting go of the trolley, opening the door.  Standing at
    // a shelf means he means to buy something, and the carousel's click depends on
    // that being the thing the next key press does.
    if (a.carrying === null && facedTake) {
      const taken = cands.find((c) => c.kind === "take");
      const best = cands[0];
      const atTheTill = best.kind === "unload" || best.kind === "takebag";
      if (taken && taken.payload === facedTake && !atTheTill) return taken;
    }
    // Letting go of the trolley costs nothing and so always ranks first by
    // distance -- which meant that pushing the trolley up to the till and
    // pressing the button let go of the handle instead of emptying it, and the
    // shopping could never reach the counter at all.  The till is the work in
    // front of him while there is anything on it to hand over: letting go is
    // what the button falls back to once the trolley is empty, or once he steps
    // away from the counter.
    if (cands[0].kind === "release") {
      const tillWork = cands.find((c) => c.kind === "unload" || c.kind === "takebag");
      if (tillWork) return tillWork;
    }
    return cands[0];
  }

  doInteraction(a: Actor, it: { kind: Exclude<Prompt, null>; payload: Prop | Vehicle | null }) {
    switch (it.kind) {
      case "drop":
        this.drop(a);
        break;
      case "take":
        this.pickUp(a, it.payload as Prop);
        break;
      case "dooropen":
        this.doorTarget = 1;
        this.note = "shop door opening";
        break;
      case "doorclose":
        this.doorTarget = 0;
        this.note = "shop door closing";
        break;
      case "stop": {
        const v = it.payload as Vehicle;
        v.speed = 0;
        v.hailed = true;
        this.note = `signalled ${v.id} to stop`;
        break;
      }
      case "vehdoor": {
        const v = it.payload as Vehicle;
        v.doorTarget = 1;
        // it waits for him at the kerb rather than swinging shut straight away
        v.doorHold = this.time + 8;
        this.note = `opened ${v.id} door`;
        break;
      }
      case "enter": {
        const v = it.payload as Vehicle;
        if (v.driver === null) this.enterVehicle(v, a);
        break;
      }
      case "grab":
        this.grabCart(a);
        break;
      case "release":
        this.releaseCart();
        break;
      case "unload":
        this.unloadOne();
        a.busyUntil = this.time + 0.5;
        a.anim = "reach";
        a.animT = 0;
        break;
      case "takebag":
        this.bag = "carried";
        this.note = "took the bag of shopping";
        break;
    }
  }

  /**
   * A highlight was clicked.  Nothing happens from a distance: the click asks the
   * boy to go and do it, and the action fires the moment it becomes available on
   * the way (or he is already standing where he can).
   */
  request(kinds: Prompt[], x: number, y: number) {
    const a = this.player;
    if (a.vehicle !== null) return false;
    const it = this.interaction(a);
    if (it && kinds.includes(it.kind)) {
      this.doInteraction(a, it);
      this.walkTarget = null;
      this.queued = null;
      return true;
    }
    this.queued = { kinds, x, y, at: this.time };
    this.walkPath = null;
    this.walkTarget = { x, y };
    this.note = "on my way";
    return false;
  }

  /** a click landed on the ground: walk there */
  setWalkTarget(x: number, y: number) {
    const a = this.player;
    if (a.vehicle !== null) return;
    this.queued = null;
    this.stuckFor = 0;
    this.walkPath = null;
    this.walkTarget = { x, y };
    this.note = "walking there";
  }

  /**
   * Work out how to get somewhere rather than heading straight at it: the shop's
   * shelving stands between the door and the aisles, so a click on the far side
   * of the room has to go round.  The search is allowed to pass through the shop
   * door, and asks for it to be opened when the route goes that way -- a click
   * from the pavement into the shop ends with him opening the door himself.
   */
  planRoute(x: number, y: number) {
    const a = this.player;
    const route = findPath({ x: a.pos.x, y: a.pos.y }, { x, y }, true);
    this.walkPath = route ?? [];
    if (!route || route.length < 2) return;
    // Does the way there cross the shop front?  The corners come out a step apart
    // on either side of the wall, so it is the segment between them that has to be
    // asked -- looking at the corners themselves misses the crossing entirely.
    let prev = { x: a.pos.x, y: a.pos.y };
    for (const p of route) {
      const out = Math.min(prev.x, p.x) < WALL[0] && Math.max(prev.x, p.x) > WALL[1];
      if (out && this.doorTarget < 0.5) {
        this.doorTarget = 1;
        this.note = "opening the shop door";
      }
      prev = p;
    }
  }

  /** where should the boy stand to reach this?  just short of it, in sim metres */
  static approach(from: { x: number; y: number }, to: { x: number; y: number }, stand = 1.0) {
    const dx = from.x - to.x;
    const dy = from.y - to.y;
    const d = Math.hypot(dx, dy) || 1;
    return { x: to.x + (dx / d) * stand, y: to.y + (dy / d) * stand };
  }

  // ---------------------------------------------------------------- frame
  step(input: Input, camYawSetter: (yaw: number) => void, camYaw: number, dt: number) {
    this.time += dt;
    const a = this.player;

    if (input.tab && a.vehicle === null && this.actors[1 - this.active].vehicle === null) {
      this.active = 1 - this.active;
      a.anim = "idle";
      camYawSetter(this.player.yaw);
      this.note = `switched to ${this.player.name}`;
    }

    // The reach takes a moment, and while the hand is out the boy must not be
    // listening for another instruction: pressing E again mid-reach used to fire
    // the "put it down" action and drop whatever he had just picked up.
    if (input.collect) this.collect(input.collect);

    const busy = this.time < a.busyUntil;
    if (input.alt && !busy && a.vehicle === null) {
      // the left hand: only ever goods
      const it = this.interaction(a);
      if (it && (it.kind === "take" || it.kind === "drop")) this.doInteraction(a, it);
    }
    if (input.use && !busy) {
      if (a.vehicle !== null) {
        // E at the wheel climbs out; there is no interaction list to consult
        const v = this.vehicles.find((x) => x.id === a.vehicle);
        if (v) this.leaveVehicle(v, a);
        a.busyUntil = this.time + 0.4;
      } else {
        const it = this.interaction(a);
        if (it) this.doInteraction(a, it);
      }
    }

    if (a.vehicle !== null) {
      const v = this.vehicles.find((x) => x.id === a.vehicle);
      if (v) {
        this.drive(v, input.mx, input.my, dt);
        this.updateVehicles(dt);
      } else a.vehicle = null;
    } else {
      if (busy) {
        a.speed = 0;
        if (this.time >= a.busyUntil) {
          a.anim = "idle";
          if (a.pending) a.pending = null; // the hand has arrived
        }
      } else {
        // an action picked from a highlight waits until the boy can reach it
        if (this.queued) {
          const it = this.interaction(a);
          if (it && this.queued.kinds.includes(it.kind)) {
            this.doInteraction(a, it);
            this.queued = null;
            this.walkTarget = null;
          } else if (this.time - this.queued.at > 20) {
            this.queued = null;
            this.walkTarget = null;
          } else {
            this.walkTarget = { x: this.queued.x, y: this.queued.y };
          }
        }
        if (this.task) this.runTask(dt);
        if (input.mx !== 0 || input.my !== 0) {
          // the arrow keys always win over a standing click instruction
          this.walkTarget = null;
          this.queued = null;
          this.task = null;
          this.moveActor(a, input.mx, input.my, input.run, camYaw, dt);
        } else if (this.walkTarget) {
          const t = this.walkTarget;
          if (this.walkPath === null) this.planRoute(t.x, t.y);
          // head for the next corner of the route, not for the target itself
          let aim = t;
          while (this.walkPath && this.walkPath.length) {
            const at = this.walkPath[0];
            if (Math.hypot(at.x - a.pos.x, at.y - a.pos.y) > 0.3) {
              aim = at;
              break;
            }
            this.walkPath.shift();
          }
          const dx = aim.x - a.pos.x;
          const dy = aim.y - a.pos.y;
          const d = Math.hypot(t.x - a.pos.x, t.y - a.pos.y);
          if (d < 0.3) {
            this.walkTarget = null;
            this.walkPath = null;
            this.moveActor(a, 0, 0, false, camYaw, dt);
          } else {
            const bx = a.pos.x;
            const by = a.pos.y;
            this.moveActor(a, 0, 1, false, Math.atan2(dx, -dy), dt);
            const adv = Math.hypot(a.pos.x - bx, a.pos.y - by);
            this.stuckFor = adv < 0.002 ? this.stuckFor + dt : 0;
            // Waiting at the shop door while it swings open is not being stuck.
            const waiting = this.doorTarget > 0.5 && this.doorOpen < 0.9;
            // if the way is shut, give up rather than run at the wall forever
            if (this.stuckFor > 0.7 && !waiting) {
              this.stuckFor = 0;
              // An errand re-plans from where he actually is -- the first route
              // may have asked him to pass through the end of a shelf -- while a
              // bare click has nothing to fall back on and is abandoned.
              if (this.task) this.walkPath = null;
              else {
                this.walkTarget = null;
                this.queued = null;
                this.walkPath = null;
              }
            }
          }
        } else {
          this.moveActor(a, 0, 0, false, camYaw, dt);
        }
      }
      this.updateVehicles(dt);
    }
    this.updateCart(a);
    this.updateCashier(dt);
    // last word on where anything is: the disks on the floor plan settle the
    // world again after everything above has moved
    this.physics = applyPhysics(this, dt);
    this.updateDoors(dt);
  }

  snapshot(): Snapshot {
    const a = this.player;
    const it = this.interaction(a);
    return {
      prompt: it ? it.kind : null,
      target: it && it.payload && "name" in it.payload ? (it.payload as Prop).name : null,
      active: this.active,
      carrying: a.carrying,
      inVehicle: a.vehicle !== null,
      speed: a.vehicle ? (this.vehicles.find((v) => v.id === a.vehicle)?.speed ?? 0) : 0,
      doorOpen: this.doorOpen,
      cart: this.cart.driver !== null,
      walking: this.walkTarget !== null,
      shelf: this.shelfNear(a),
      trolley: this.cart.items.length,
      receipt: this.receipt,
      total: this.total,
      bag: this.bag === "counter",
      task: this.task ? this.task.want : null,
      inShop: inShop(a.pos.x, a.pos.y),
    };
  }

  carriedPos(): V3 | null {
    const a = this.player;
    const p = this.props.find((q) => q.name === a.carrying);
    if (!p) return null;
    return a.pending ? p.pos : this.carryPoint(a);
  }
}
