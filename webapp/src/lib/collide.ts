// Collision from the geometry that is actually on screen.
//
// world.json carries blocker rectangles that were measured from the blockout that
// came before the real shop, so the boy walked straight through the walls, shelves
// and counters standing on top of it.  Here every static mesh that is tall enough
// to be an obstacle is turned into a solid box in its own local space (so rotated
// walls stay the shape they look), bucketed into a coarse grid for fast lookup.
import * as THREE from "three";

import { pruneBlockers, setSolids, WALL } from "./world";

const CELL = 3;

type Solid = {
  inv: THREE.Matrix4;
  min: THREE.Vector3;
  max: THREE.Vector3;
  /** local units per world unit, so a world radius can be compared to a local box */
  invScale: number;
  yLo: number;
  yHi: number;
  name: string;
};

/** the boy is blocked by anything taller than a step that he would walk into */
const STEP_OVER = 0.26;

export class SolidSet {
  private solids: Solid[] = [];
  private grid = new Map<number, number[]>();
  count = 0;
  /** meshes rejected as too flat / too low, for the log */
  skipped = 0;
  /** meshes the caller asked to leave out, judged on their world x span */
  reject: ((mnx: number, mxx: number) => boolean) | null = null;

  private static key(cx: number, cz: number) {
    return (cx + 2048) * 8192 + (cz + 2048);
  }

  add(name: string, mesh: THREE.Mesh): "solid" | "flat" | "wall" {
    const geo = mesh.geometry;
    if (!geo) return "flat";
    if (!geo.boundingBox) geo.computeBoundingBox();
    const bb = geo.boundingBox;
    if (!bb) return "flat";

    const e = mesh.matrixWorld.elements;
    // world AABB of the local box: cheap and only used for filtering + broadphase
    let mnx = Infinity, mny = Infinity, mnz = Infinity, mxx = -Infinity, mxy = -Infinity, mxz = -Infinity;
    for (let i = 0; i < 8; i++) {
      const x = i & 1 ? bb.max.x : bb.min.x;
      const y = i & 2 ? bb.max.y : bb.min.y;
      const z = i & 4 ? bb.max.z : bb.min.z;
      const wx = e[0] * x + e[4] * y + e[8] * z + e[12];
      const wy = e[1] * x + e[5] * y + e[9] * z + e[13];
      const wz = e[2] * x + e[6] * y + e[10] * z + e[14];
      if (wx < mnx) mnx = wx;
      if (wy < mny) mny = wy;
      if (wz < mnz) mnz = wz;
      if (wx > mxx) mxx = wx;
      if (wy > mxy) mxy = wy;
      if (wz > mxz) mxz = wz;
    }
    if (this.reject && this.reject(mnx, mxx)) return "wall";
    // floors, kerbs and stickers are not walls
    if (mxy - mny < 0.22 || mxy < 0.32) {
      this.skipped += 1;
      return "flat";
    }
    const scale = Math.max(
      Math.hypot(e[0], e[1], e[2]),
      Math.hypot(e[4], e[5], e[6]),
      Math.hypot(e[8], e[9], e[10]),
    );
    if (!(scale > 1e-6)) return "flat";

    const idx = this.solids.length;
    this.solids.push({
      inv: mesh.matrixWorld.clone().invert(),
      min: bb.min.clone(),
      max: bb.max.clone(),
      invScale: 1 / scale,
      yLo: mny,
      yHi: mxy,
      name,
    });
    this.count = this.solids.length;

    const c0x = Math.floor(mnx / CELL), c1x = Math.floor(mxx / CELL);
    const c0z = Math.floor(mnz / CELL), c1z = Math.floor(mxz / CELL);
    // a wall spanning the map would flood the grid; give up on it, nothing is that big
    if ((c1x - c0x + 1) * (c1z - c0z + 1) > 900) {
      this.solids[idx].yLo = Infinity;
      return "solid";
    }
    for (let cx = c0x; cx <= c1x; cx++) {
      for (let cz = c0z; cz <= c1z; cz++) {
        const k = SolidSet.key(cx, cz);
        const cell = this.grid.get(k);
        if (cell) cell.push(idx);
        else this.grid.set(k, [idx]);
      }
    }
    return "solid";
  }

  private cells(x: number, z: number) {
    return this.grid.get(SolidSet.key(Math.floor(x / CELL), Math.floor(z / CELL)));
  }

  private inside(s: Solid, x: number, y: number, z: number): boolean {
    if (y > s.yHi || y < s.yLo) return false;
    const e = s.inv.elements;
    const lx = e[0] * x + e[4] * y + e[8] * z + e[12];
    const ly = e[1] * x + e[5] * y + e[9] * z + e[13];
    const lz = e[2] * x + e[6] * y + e[10] * z + e[14];
    return lx >= s.min.x && lx <= s.max.x && ly >= s.min.y && ly <= s.max.y && lz >= s.min.z && lz <= s.max.z;
  }

  /** is this single point inside a solid (used to test whether a blocker is real) */
  contains(x: number, y: number, z: number): boolean {
    const cell = this.cells(x, z);
    if (!cell) return false;
    for (const i of cell) if (this.inside(this.solids[i], x, y, z)) return true;
    return false;
  }

  /** names of the solids swallowing a point -- the answer to "what is he stuck in?" */
  hit(x: number, y: number, z: number): string[] {
    const cell = this.cells(x, z);
    if (!cell) return [];
    const out: string[] = [];
    for (const i of cell) {
      const s = this.solids[i];
      if (this.inside(s, x, y, z)) out.push(s.name || "(unnamed)");
    }
    return out;
  }

  /**
   * The boy's body is a small cylinder: test a few points of it against each
   * solid.  (x, y) are simulation coordinates; the world's z is -y, because
   * Blender's y (the direction the street runs) became three's -z.  Getting that
   * sign wrong made the boy collide with whatever stood mirrored across the
   * street: he was stopped at the shop door by a wall four metres further on.
   */
  blocked(x: number, y: number, r: number, groundZ: number): boolean {
    const cell = this.cells(x, -y);
    if (!cell) return false;
    const feet = groundZ + STEP_OVER;
    const head = groundZ + 1.7;
    for (const i of cell) {
      const s = this.solids[i];
      if (s.yHi < feet || s.yLo > head) continue;
      const e = s.inv.elements;
      const h = groundZ + 0.9;
      for (let k = 0; k < 5; k++) {
        const dx = k === 0 ? 0 : k === 1 ? r : k === 2 ? -r : 0;
        const dz = k === 0 ? 0 : k === 3 ? r : k === 4 ? -r : 0;
        const px = x + dx, pz = -(y + dz);
        const lx = e[0] * px + e[4] * h + e[8] * pz + e[12];
        const ly = e[1] * px + e[5] * h + e[9] * pz + e[13];
        const lz = e[2] * px + e[6] * h + e[10] * pz + e[14];
        const pad = r * s.invScale;
        if (
          lx >= s.min.x - pad && lx <= s.max.x + pad &&
          lz >= s.min.z - pad && lz <= s.max.z + pad &&
          ly >= s.min.y && ly <= s.max.y
        ) return true;
      }
    }
    return false;
  }
}

const IGNORE = /^HUD_|^P_|^WGT|widget|Shop_Door|Prop_|Sky|LightProbe|^Cube392$/;

/**
 * Build the solid set from the loaded scene and hand it to the simulation.  The
 * blocker rectangles that the geometry does not back are dropped at the same time
 * (they were the reason the boy got stuck in the middle of the road).
 */
export function installSolids(
  root: THREE.Object3D,
  skip: THREE.Object3D[],
): {
  solids: number;
  skippedFlat: number;
  skippedWall: number;
  blockersDropped: number;
  hit: (x: number, y: number, z: number) => string[];
} {
  root.updateMatrixWorld(true);
  const set = new SolidSet();
  let wallSkipped = 0;
  const hidden = new Set<THREE.Object3D>();
  root.traverse((o) => {
    if (!o.visible) hidden.add(o);
  });
  const inHidden = (o: THREE.Object3D) => {
    for (let p: THREE.Object3D | null = o; p; p = p.parent) if (hidden.has(p)) return true;
    return false;
  };
  const inSkip = (o: THREE.Object3D) => {
    for (let p: THREE.Object3D | null = o; p; p = p.parent) if (skip.includes(p)) return true;
    return false;
  };

  // The shop's front wall belongs to the simulation: world.json knows where the
  // wall is and where the doorway is, and canStand enforces exactly that.  The
  // export also carries the front wall and its glass as single meshes -- the glass
  // is one pane stretching across the whole shopfront, door opening included -- so
  // leaving them in the solid set seals the door.  Anything that reaches out past
  // the outer face of the wall is front-wall structure; drop it here.
  const wallCrosser = (mnx: number, mxx: number) =>
    mnx < WALL[0] - 0.15 && mxx > WALL[0] && mnx < WALL[1];
  set.reject = wallCrosser;

  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh || (mesh as THREE.SkinnedMesh).isSkinnedMesh) return;
    if (inHidden(mesh) || inSkip(mesh)) return;
    if (IGNORE.test(mesh.name)) return;
    if (Array.isArray(mesh.material) && mesh.material.length === 0) return;
    if (set.add(mesh.name, mesh) === "wall") wallSkipped += 1;
  });

  const dropped = pruneBlockers(
    (x, y) => set.contains(x, 0.9, -y) || set.contains(x, 0.35, -y),
    // keep whatever stands in the wall band: the sim enforces the wall and its
    // doorway itself, and the geometry there is no longer in the solid set
    (b) => b[0] < WALL[1] && b[2] > WALL[0],
  );
  setSolids({
    blocked: (x, y, r, ground) => set.blocked(x, y, r, ground),
    contains: (x, y, z) => set.contains(x, y, z),
    count: set.count,
  });
  return {
    solids: set.count,
    skippedFlat: set.skipped,
    skippedWall: wallSkipped,
    blockersDropped: dropped,
    hit: (x, y, z) => set.hit(x, y, z),
  };
}
