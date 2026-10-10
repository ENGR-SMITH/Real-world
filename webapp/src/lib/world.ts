// The walkable world, ported from the UPBGE build's game.py.  Every number here
// was measured from the Blender scene, so the browser and the desktop game agree
// on where the pavement, shop, counter and doorway are.
import raw from "../world.json";

export type Region = [string, number, number, number, number, number];

export type VehicleData = {
  yaw: number;
  lane: number;
  cruise: number;
  road: [number, number];
  wrap: [number, number];
  width: number;
  length: number;
  body_fwd: number;
  reach: number;
  getout_side: number;
  tuktuk: boolean;
  door_angle: number;
  door: string | null;
  seat: [number, number, number];
};

export type WorldData = {
  regions: Region[];
  wall: [number, number];
  doorway: [number, number];
  blockers: [number, number, number, number][];
  clips: Record<string, [number, number]>;
  props: Record<string, { stand: [number, number]; yaw: number }>;
  props_world: Record<string, [number, number, number]>;
  vehicles: Record<string, VehicleData>;
  shop_doors: [string, number][];
  shop_door_angle: number;
  shop_door_centre: [number, number];
};

const bundle = raw as unknown as { world: WorldData; tuning: Record<string, number> };

export const WORLD = bundle.world;
export const T = bundle.tuning;
export const REGIONS = WORLD.regions;
export const BLOCKERS = WORLD.blockers;
export const WALL = WORLD.wall;
export const DOORWAY = WORLD.doorway;
export const PLAYER_R = T.PLAYER_R;

/** how far a point may sit outside a region and still count as standing in it */
const REGION_EPS = 0.08;

export function regionAt(x: number, y: number): Region | null {
  for (const r of REGIONS) {
    if (r[1] <= x && x <= r[3] && r[2] <= y && y <= r[4]) return r;
  }
  // The pavement slab and the road slab were measured 4 cm apart, and that seam
  // had no region at all: groundZ() returned null there, so the boy stopped dead
  // at the kerb and could never step onto the road.  Snap to the nearest region
  // instead of refusing to stand.
  for (const r of REGIONS) {
    if (r[1] - REGION_EPS <= x && x <= r[3] + REGION_EPS && r[2] - REGION_EPS <= y && y <= r[4] + REGION_EPS) return r;
  }
  return null;
}

export function groundZ(x: number, y: number): number | null {
  const r = regionAt(x, y);
  return r ? r[5] : null;
}

export function blocked(x: number, y: number, r: number): boolean {
  for (const b of BLOCKERS) {
    if (b[0] - r < x && x < b[2] + r && b[1] - r < y && y < b[3] + r) return true;
  }
  return false;
}

/**
 * Collision taken from the rendered geometry.  The blocker rectangles were
 * measured back when the world was a blockout; the real shop walls, shelves and
 * counters have since been dropped in on top, and they are not where those
 * rectangles are, so the boy walked through them.  The scene answers for itself:
 * every static mesh tall enough to be an obstacle becomes a solid box.
 */
export type SolidTest = {
  blocked(x: number, y: number, r: number, groundZ: number): boolean;
  contains(x: number, y: number, z: number): boolean;
  count: number;
};

let solids: SolidTest | null = null;

/** called once the GLB is in the scene; until then the old blockers are all we have */
export function setSolids(s: SolidTest | null) {
  solids = s;
}

export function solidsActive(): boolean {
  return solids !== null;
}

/** the geometry's own verdict, for diagnosing a spot the sim refuses to stand on */
export function solidsBlocked(x: number, y: number, r: number, z: number): boolean {
  return solids ? solids.blocked(x, y, r, z) : false;
}

/**
 * Is this exact point inside a solid mesh?  Unlike solidsBlocked() there is no
 * allowance for the width of a body, so it answers "is this thing buried in the
 * wall", which is what the trolley asks about its own nose.
 */
export function solidAt(x: number, y: number, height = 0.9): boolean {
  return solids ? solids.contains(x, height, -y) : false;
}

/** drop blocker rectangles that no longer cover anything you can see */
export function pruneBlockers(
  isSolid: (x: number, y: number) => boolean,
  keep?: (b: [number, number, number, number]) => boolean,
  samples = 4,
): number {
  const kept: [number, number, number, number][] = [];
  let dropped = 0;
  for (const b of BLOCKERS) {
    if (keep && keep(b)) {
      kept.push(b);
      continue;
    }
    let hits = 0;
    for (let i = 0; i < samples; i++) {
      for (let j = 0; j < samples; j++) {
        const x = b[0] + ((i + 0.5) / samples) * (b[2] - b[0]);
        const y = b[1] + ((j + 0.5) / samples) * (b[3] - b[1]);
        if (isSolid(x, y)) hits += 1;
      }
    }
    if (hits > 0) kept.push(b);
    else dropped += 1;
  }
  BLOCKERS.length = 0;
  BLOCKERS.push(...kept);
  return dropped;
}

/**
 * How far the doorway reaches past the wall it is cut into.  The wall band is
 * only a quarter of a metre thick, but the door's frame, its reveals and the
 * shopfront's side posts stick out roughly half a metre on either side and were
 * catching the boy on the pavement just before the opening -- he could not get
 * near enough to walk through a door the simulation says is open.  The doorway is
 * a short tunnel, and the simulation owns all of it.
 */
const DOOR_APRON = 0.9;

export function canStand(x: number, y: number, r = PLAYER_R, doorsOpen = true): boolean {
  const z = groundZ(x, y);
  if (z === null) return false;
  // The shop front is the simulation's own: the wall band with a doorway cut in
  // it.  Inside the band the answer is nothing but "is this the doorway?" -- the
  // geometry cannot know where the opening is (the glass is one pane across the
  // whole front).
  const inWall = WALL[0] - r < x && x < WALL[1] + r;
  const inDoor = doorsOpen && DOORWAY[0] + r * 0.5 <= y && y <= DOORWAY[1] - r * 0.5;
  if (inWall) return inDoor;
  if (inDoor && x > WALL[0] - DOOR_APRON && x < WALL[1] + DOOR_APRON) return true;
  if (blocked(x, y, r)) return false;
  if (solids && solids.blocked(x, y, r, z)) return false;
  return true;
}

/** the four props sit on the counter: carried items ride in front of the boy */
export const PROP_SPAWNS = WORLD.props_world;
export const SHOP_DOOR_CENTRE = WORLD.shop_door_centre;
export const SHOP_DOOR_ANGLE = WORLD.shop_door_angle;
