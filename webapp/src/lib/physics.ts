// Physics: the scene is a real place, so the things standing in it have to be
// real things.  Before this, a body meant nothing: the boy walked through the
// parked cars, through the trolley and through his friend, the trolley was pushed
// through shelves, two cars drove through each other, and an item put down hung
// in the air where his hand had been.
//
// Everything that occupies space is a disc on the floor plan -- the boys, one
// per trolley, three per car, one per loose item -- and each step the discs are
// pushed apart in proportion to how easily they can be moved: a boy shoves a
// trolley, a trolley shoves a tin, a car shoves a boy and is not shoved back.
// Items have weight of their own and fall to the floor when they are let go,
// sliding a little before they stop.
import { canStand, DOORWAY, groundZ, solidAt, WALL } from "./world";
import type { Game } from "./game";

const GRAVITY = 9.81;
/** how quickly a tin sliding across the floor gives up (1/s) */
const SLIDE = 6;
/** below this speed a loose item is simply lying where it is */
const STILL = 0.03;
/** a boy's shoulders, for bumping into things */
const ACTOR_R = 0.28;
const ACTOR_MASS = 78;
const CART_MASS = 22;
const ITEM_MASS = 1.2;
/** discs used to stand in for a car's body */
const CAR_DISCS = 3;
/**
 * How far in front of its own middle the trolley tests for shelving, roughly the
 * far side of the basket.  Measured as an exact point rather than as a body of a
 * given width: the trolley was modelled standing in an aisle with a shelf 22 cm
 * from its centre, so a full-width test had it jammed before it ever moved.
 */
const CART_NOSE = 0.32;

type Body = {
  x: number;
  y: number;
  r: number;
  /** 1/mass: zero means nothing in the world can move this one */
  inv: number;
  /** which object it belongs to, so a thing never collides with itself */
  key: string;
  kind: "actor" | "cart" | "item" | "vehicle";
  /** index into the game's own list for that kind */
  index: number;
};

export type PhysicsReport = {
  /** pairs that had to be separated this step */
  bumped: number;
  /** loose items still sliding or falling */
  moving: number;
  /** true when the trolley was driven into something solid */
  jammed: boolean;
};

type V = { x: number; y: number; z: number };

/** how far off the floor an item of this size rests: it stands on its own base */
function restHeight(r: number) {
  return r;
}

/**
 * Where the trolley stood at the end of the last step.  The simulation has
 * already moved it by the time the physics runs -- it rides in front of whoever
 * is pushing it -- so the only honest "where it was" is the position this module
 * wrote back last time.
 */
let cartLast: { x: number; y: number } | null = null;

export function applyPhysics(game: Game, dt: number): PhysicsReport {
  const report: PhysicsReport = { bumped: 0, moving: 0, jammed: false };
  const bodies: Body[] = [];
  if (!cartLast) cartLast = { x: game.cart.pos.x, y: game.cart.pos.y };

  // ------------------------------------------------------------------ loose items
  // Only the things that have left their shelf are simulated: the other five
  // hundred are standing exactly where the blend put them and cost nothing.
  for (let i = 0; i < game.props.length; i++) {
    const p = game.props[i];
    if (!p.moved || p.held) continue;
    const v: V = (p.v ??= { x: 0, y: 0, z: 0 });
    const r = p.r ?? 0.06;
    const floor = groundZ(p.pos.x, p.pos.y);
    if (floor === null) continue;
    const rest = floor + restHeight(r);
    if (p.pos.z > rest + 0.002) {
      // in the air: it falls like anything else would
      v.z -= GRAVITY * dt;
      p.pos.z += v.z * dt;
      if (p.pos.z <= rest) {
        p.pos.z = rest;
        v.z = 0;
      }
      report.moving += 1;
    } else {
      p.pos.z = rest;
      v.z = 0;
    }
    if (v.x !== 0 || v.y !== 0) {
      const px = p.pos.x;
      const py = p.pos.y;
      p.pos.x += v.x * dt;
      p.pos.y += v.y * dt;
      const damp = Math.max(0, 1 - SLIDE * dt);
      v.x *= damp;
      v.y *= damp;
      if (Math.hypot(v.x, v.y) < STILL) {
        v.x = 0;
        v.y = 0;
      }
      if (!canStand(p.pos.x, p.pos.y, Math.min(r, 0.12), true)) {
        // a wall or a shelf stopped it: it comes to rest against the side
        p.pos.x = px;
        p.pos.y = py;
        v.x = 0;
        v.y = 0;
      }
      report.moving += 1;
    }
    bodies.push({ x: p.pos.x, y: p.pos.y, r, inv: 1 / ITEM_MASS, key: `I${i}`, kind: "item", index: i });
  }

  // ------------------------------------------------------------------ the boys
  for (let i = 0; i < game.actors.length; i++) {
    const a = game.actors[i];
    if (a.vehicle !== null) continue; // at the wheel the car is what takes up space
    bodies.push({
      x: a.pos.x, y: a.pos.y, r: ACTOR_R, inv: 1 / ACTOR_MASS, key: `A${a.id}`, kind: "actor", index: i,
    });
  }

  // ------------------------------------------------------------------ the trolley
  const cart = game.cart;
  const cartR = Math.max(0.25, game.cartReach);
  const cartHome: V = { x: cartLast.x, y: cartLast.y, z: cart.pos.z };
  bodies.push({
    x: cart.pos.x,
    y: cart.pos.y,
    r: cartR,
    // held, it goes where the pusher's arms say; free, it is only as heavy as a
    // trolley and the boy walking into it shoves it along
    inv: cart.driver === null ? 1 / CART_MASS : 0,
    key: "cart",
    kind: "cart",
    index: 0,
  });

  // ------------------------------------------------------------------ the cars
  for (let i = 0; i < game.vehicles.length; i++) {
    const v = game.vehicles[i];
    const d = v.data;
    const f = { x: Math.sin(v.yaw), y: -Math.cos(v.yaw) };
    const half = Math.max(d.length, d.width) * 0.5;
    const r = Math.max(0.6, d.width * 0.5);
    const span = Math.max(0, half - r);
    for (let k = 0; k < CAR_DISCS; k++) {
      const t = (k / (CAR_DISCS - 1)) * 2 - 1;
      bodies.push({
        x: v.pos.x + f.x * t * span,
        y: v.pos.y + f.y * t * span,
        r,
        inv: 0, // cars keep to the road; they do not get shoved
        key: `V${v.id}`,
        kind: "vehicle",
        index: i,
      });
    }
  }

  // ------------------------------------------------------------------ contacts
  for (let i = 0; i < bodies.length; i++) {
    for (let j = i + 1; j < bodies.length; j++) {
      const a = bodies[i];
      const b = bodies[j];
      if (a.key === b.key) continue;
      // a boy pushing his own trolley is holding it, not bumping into it
      if (a.kind === "cart" || b.kind === "cart") {
        const other = a.kind === "cart" ? b : a;
        if (other.kind === "actor" && cart.driver === game.actors[other.index].id) continue;
      }
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const d = Math.hypot(dx, dy);
      const overlap = a.r + b.r - d;
      if (overlap <= 0) continue;
      const wsum = a.inv + b.inv;
      if (wsum <= 0) continue; // two things that cannot move: nothing to settle
      const nx = d > 1e-6 ? dx / d : 1;
      const ny = d > 1e-6 ? dy / d : 0;
      a.x -= nx * overlap * (a.inv / wsum);
      a.y -= ny * overlap * (a.inv / wsum);
      b.x += nx * overlap * (b.inv / wsum);
      b.y += ny * overlap * (b.inv / wsum);
      report.bumped += 1;
    }
  }

  // The trolley is not allowed to be a battering ram: driven into a shelf it
  // stops, and the boy behind it stops with it.
  const doors = game.doorOpen > 0.5;
  const cartBody = bodies.find((b) => b.kind === "cart") as Body;
  // What stops a trolley is the furniture, not the blockout: the shelves are real
  // geometry now, and asking canStand() would have the trolley jam against the
  // same invisible rectangles the blockout left behind -- including the one it
  // was modelled standing in.
  const cartFloor = groundZ(cartBody.x, cartBody.y) ?? 0.05;
  const cf = { x: Math.sin(cart.yaw), y: -Math.cos(cart.yaw) };
  // The shop front is the simulation's own -- its glass is not in the solid set,
  // so the wall itself has to be asked about separately.  The doorway is a hole
  // in it: a trolley can be pushed in and out through the open door.
  const inWall = cartBody.x > WALL[0] - 0.12 && cartBody.x < WALL[1] + 0.12;
  const inDoor = cartBody.y >= DOORWAY[0] && cartBody.y <= DOORWAY[1];
  const buried =
    solidAt(cartBody.x, cartBody.y, cartFloor + 0.3) ||
    solidAt(cartBody.x + cf.x * CART_NOSE, cartBody.y + cf.y * CART_NOSE, cartFloor + 0.5) ||
    (inWall && !inDoor);
  if (buried) {
    cartBody.x = cartHome.x;
    cartBody.y = cartHome.y;
    report.jammed = true;
  }

  // ------------------------------------------------------------------ settle cars
  for (let i = 0; i < game.vehicles.length; i++) {
    for (let j = i + 1; j < game.vehicles.length; j++) {
      const vi = game.vehicles[i];
      const vj = game.vehicles[j];
      const dx = vj.pos.x - vi.pos.x;
      const dy = vj.pos.y - vi.pos.y;
      // Only when two cars are actually in the same place.  This used to allow for
      // a whole car's length, so the two of them, driving in their own lanes three
      // metres apart, kept stopping each other and the street went dead.
      const near = (vi.data.width + vj.data.width) * 0.5 + 0.3;
      if (Math.hypot(dx, dy) > near) continue;
      // two cars in the same place: the one that is moving gives way
      const mover = Math.abs(vi.speed) >= Math.abs(vj.speed) ? vi : vj;
      const other = mover === vi ? vj : vi;
      const f = { x: Math.sin(mover.yaw), y: -Math.cos(mover.yaw) };
      // is the other car in front of the one that is moving, or behind it?
      const ahead = (mover === vi ? 1 : -1) * (dx * f.x + dy * f.y);
      mover.pos.x -= f.x * 0.12 * Math.sign(ahead || 1);
      mover.pos.y -= f.y * 0.12 * Math.sign(ahead || 1);
      mover.speed = 0;
      if (other.driver === null) other.speed = Math.min(other.speed, 0.4);
      report.bumped += 1;
    }
  }

  // ------------------------------------------------------------------ write back
  for (const b of bodies) {
    if (b.kind === "actor") {
      const a = game.actors[b.index];
      const bx = a.pos.x;
      const by = a.pos.y;
      // the solver may not walk him into a wall while it pushes him out of a car
      if (canStand(b.x, b.y, undefined, doors)) {
        a.pos.x = b.x;
        a.pos.y = b.y;
      } else if (canStand(b.x, by, undefined, doors)) {
        a.pos.x = b.x;
      } else if (canStand(bx, b.y, undefined, doors)) {
        a.pos.y = b.y;
      }
      const z = groundZ(a.pos.x, a.pos.y);
      if (z !== null) a.pos.z = z;
    } else if (b.kind === "cart") {
      cart.pos.x = b.x;
      cart.pos.y = b.y;
      const z = groundZ(b.x, b.y);
      if (z !== null) cart.pos.z = z;
      // Run into something, the trolley stops -- and a boy pushing it stops too,
      // rather than walking on and dragging it through the wall a step at a time.
      // He is held where his arms are: the trolley is in front of him by reach +
      // the length of his arms, so his own place follows from where it stands.
      if (report.jammed && cart.driver !== null) {
        const a = game.actors.find((x) => x.id === cart.driver);
        if (a) {
          const f = { x: Math.sin(a.yaw), y: -Math.cos(a.yaw) };
          const want = game.cartReach + 0.42;
          const ahead = (b.x - a.pos.x) * f.x + (b.y - a.pos.y) * f.y;
          if (ahead < want) {
            const back = want - ahead;
            if (canStand(a.pos.x - f.x * back, a.pos.y - f.y * back, undefined, doors)) {
              a.pos.x -= f.x * back;
              a.pos.y -= f.y * back;
              const z2 = groundZ(a.pos.x, a.pos.y);
              if (z2 !== null) a.pos.z = z2;
            }
          }
          a.speed = 0;
        }
      }
    } else if (b.kind === "item") {
      const p = game.props[b.index];
      p.pos.x = b.x;
      p.pos.y = b.y;
    }
  }
  cartLast = { x: cart.pos.x, y: cart.pos.y };
  return report;
}
