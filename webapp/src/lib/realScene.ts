// Loads the real Blender scene (shop.glb) and drives its objects from the
// simulation.  Blender wrote glTF with its usual axis change: a point
// (x, y, z) in the game's world becomes (x, z, -y) in three.js, and a yaw about
// Blender's up axis becomes the same rotation about three's +Y.  Everything in
// here converts through simToThree() so the browser view matches the blend
// exactly, mirrors and all.
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";

import { productType, type Game } from "./game";
import { regionAt, WORLD } from "./world";

/** the three-wheeler came out of the blend a fifth too big; this brings it down */
const TUKTUK_SCALE = 0.8;

/**
 * What a boy's walk cycle needs to look like a walk: the speed it implies at
 * timeScale 1, and the moment in the cycle where the feet pass under the body
 * (the only honest pose to hold while standing still, since the export carries no
 * idle clip).
 */
export type Gait = {
  action: THREE.AnimationAction;
  mixer: THREE.AnimationMixer;
  naturalSpeed: number;
  passing: number;
  stride: number;
};

export type RealScene = {
  root: THREE.Object3D;
  boys: Record<number, THREE.Object3D>;
  gaits: Record<number, Gait>;
  mixers: THREE.AnimationMixer[];
  props: Map<string, THREE.Object3D>;
  /** everything on the shelves the boy is allowed to pick up */
  products: ProductNode[];
  /** the building's roof, so the isometric view can see through it */
  roof: THREE.Object3D[];
  /** the shop's trolley, re-hung on a pivot so the simulation can push it */
  cart: CartNode | null;
  /** the cashier: a third rig, behind the counter */
  cashier: { root: THREE.Object3D; mixer: THREE.AnimationMixer; walk: THREE.AnimationAction | null } | null;
  /** the bag his shopping is packed into */
  bag: THREE.Object3D | null;
  vehicles: Map<string, VehicleNode>;
  doors: { node: THREE.Object3D; base: number; sign: number }[];
  walkClip: THREE.AnimationClip | null;
  /** every clip the export carried, by name */
  clips: Record<string, THREE.AnimationClip>;
  animations: THREE.AnimationClip[];
  skinned: number;
  meshes: number;
};

/**
 * A vehicle root as the export left it.  The blend's car objects carry a baked
 * 180-degree flip in their euler (x and z both pi); the UPBGE game overwrote the
 * whole euler when it drove them, so writing only rotation.y here used to leave
 * the flip in place and the cars drove backwards.  Keeping the rest quaternion
 * and turning it about the world up axis reproduces the game exactly.
 */
export type VehicleNode = {
  node: THREE.Object3D;
  baseY: number;
  restQuat: THREE.Quaternion;
  /** radians to add to the simulation yaw so the model's nose leads the way */
  yawOffset: number;
  /** the door that swings open for him, if this car has one */
  door: { node: THREE.Object3D; base: number; open: number } | null;
};

export type ProductNode = {
  name: string;
  pos: { x: number; y: number; z: number };
  /** how far it reaches from its middle, so it can stand on its own base */
  r: number;
  /** the colour of the goods themselves, for the carousel tile */
  colour: string;
  node: THREE.Object3D;
};

/** the trolley: its frame, basket, handle and four wheels, hung on a pivot */
export type CartNode = {
  group: THREE.Group;
  /** where it stood in the blend, in simulation coordinates */
  home: { x: number; y: number };
  /** how far the basket reaches from the pivot, for the boy to stand behind */
  reach: number;
  height: number;
};

/** shelf goods are small; anything bigger than this is furniture */
const PRODUCT_MAX = 0.62;

/**
 * The floor of the ceiling: the shop's own roof slabs start at 7.06 m, and the
 * lamps hang from 6.45 m.  Nothing in the shop that a shopper could see from
 * inside stands above this, so it is all "the roof" as far as the camera goes.
 */
const WORLD_ROOF_Y = 6.2;

/**
 * Every item on every shelf, made into something the boy can pick up.
 *
 * The export has no marker for "this is a product" -- the tins are groups called
 * dose###, the bottles Pulle####, the brand boxes plain Cube###s with the Marken
 * material -- so the shape decides: a thing small enough to hold in one hand that
 * sits above the shop floor and is not part of the building, the boy, a vehicle or
 * the HUD.  The outermost such object wins, so a tin's three material layers are
 * one product and not three.
 */
function collectProducts(
  root: THREE.Object3D,
  skip: THREE.Object3D[],
): ProductNode[] {
  const out: ProductNode[] = [];
  const bb = new THREE.Box3();
  const size = new THREE.Vector3();
  const centre = new THREE.Vector3();
  const inSkip = (o: THREE.Object3D) => {
    for (let q: THREE.Object3D | null = o; q; q = q.parent) if (skip.includes(q)) return true;
    return false;
  };
  const walk = (o: THREE.Object3D): boolean => {
    // true once the subtree has been claimed, so the caller stops descending:
    // a parent whose whole contents fit in a hand is the product, layers and all
    if (!o.visible || inSkip(o)) return true;
    if (/^HUD_|^P_|^WGT|widget|Shop_Door|Sky|LightProbe/i.test(o.name)) return true;
    if ((o as THREE.SkinnedMesh).isSkinnedMesh) return true;
    let any = false;
    o.traverse((c) => {
      if ((c as THREE.Mesh).isMesh) any = true;
    });
    if (!any) return false;
    bb.setFromObject(o);
    if (bb.isEmpty()) return false;
    bb.getSize(size);
    const big = Math.max(size.x, size.y, size.z);
    if (big <= PRODUCT_MAX && big >= 0.05 && Math.min(size.x, size.y, size.z) >= 0.015 && bb.min.y > 0.16) {
      bb.getCenter(centre);
      // only what is inside the shop: the shelves on the pavement are scenery
      const room = regionAt(centre.x, -centre.z);
      if (!room || room[0] !== "shop") return false;
      out.push({
        name: o.name,
        // sim (x, y) is three (x, -z); sim z is three's height
        pos: { x: centre.x, y: -centre.z, z: centre.y },
        // half of the footprint: a tin rests on its own base, not half sunk in it
        r: Math.min(0.3, Math.max(0.03, Math.max(size.x, size.z) * 0.5)),
        colour: packetColour(o),
        node: o,
      });
      return true;
    }
    for (const c of o.children) if (walk(c)) continue;
    return false;
  };
  for (const c of root.children) walk(c);
  return out;
}

/**
 * What a shelf item is actually the size of, in metres.
 *
 * The blend's goods are not all drawn at one scale: a tin comes out up to 62 cm
 * across, which is five times a real tin and half the height of the shelf it is
 * meant to be standing on, and the packets fare no better.  The building, the boy
 * and the trolley are all at true size, so the goods are the things that are
 * wrong -- a shopper with a 62 cm tin under one arm is the giveaway.  Each kind of
 * goods is brought to the size it would be on a real shelf, scaled about its own
 * base so it stays standing where the blend put it.
 */
const REAL_ITEM_SIZE: Record<string, number> = {
  tin: 0.115, // a tin of food: 11.5 cm tall
  bottle: 0.3, // a shelf bottle: 30 cm
  box: 0.21, // a brand packet: 21 cm
};

function sizeProducts(products: ProductNode[]): void {
  const box = new THREE.Box3();
  const size = new THREE.Vector3();
  const after = new THREE.Box3();
  const aSize = new THREE.Vector3();
  const stats = new Map<string, { n: number; lo: number; hi: number; sum: number }>();

  for (const p of products) {
    const kind = productType(p.name).type;
    const target = REAL_ITEM_SIZE[kind];
    if (!target || !p.node.parent) continue;
    box.setFromObject(p.node);
    if (box.isEmpty()) continue;
    box.getSize(size);
    const before = Math.max(size.x, size.y, size.z);
    if (!(before > 0.005)) continue;

    const s = stats.get(kind) ?? { n: 0, lo: Infinity, hi: 0, sum: 0 };
    s.n += 1; s.lo = Math.min(s.lo, before); s.hi = Math.max(s.hi, before); s.sum += before;
    stats.set(kind, s);

    // leave what is already close enough alone: re-scaling a thing that is right
    // only makes it wrong in a new way
    const factor = target / before;
    if (factor > 0.85 && factor < 1.18) continue;

    const beforeCentre = box.getCenter(new THREE.Vector3());
    const beforeBase = box.min.y;
    p.node.scale.multiplyScalar(factor);
    p.node.updateMatrixWorld(true);
    after.setFromObject(p.node);
    if (after.isEmpty()) continue;
    after.getSize(aSize);
    const afterCentre = after.getCenter(new THREE.Vector3());

    // stand it back on the shelf it came off: move it in its parent's own frame,
    // because the shift we want is a world-space one and the parent may be turned
    const inv = new THREE.Matrix4().copy(p.node.parent.matrixWorld).invert();
    const shift = new THREE.Vector3(
      beforeCentre.x - afterCentre.x,
      beforeBase - after.min.y,
      beforeCentre.z - afterCentre.z,
    ).applyMatrix4(inv);
    shift.sub(new THREE.Vector3(0, 0, 0).applyMatrix4(inv));
    p.node.position.add(shift);
    p.node.updateMatrixWorld(true);

    // the simulation's idea of the thing has to move with it
    after.setFromObject(p.node);
    p.pos.x = (after.min.x + after.max.x) / 2;
    p.pos.y = -((after.min.z + after.max.z) / 2);
    p.pos.z = (after.min.y + after.max.y) / 2;
    p.r = Math.min(0.3, Math.max(0.02, Math.max(aSize.x, aSize.z) * 0.5));
  }

  for (const [kind, s] of stats) {
    const target = REAL_ITEM_SIZE[kind] ?? 0;
    console.info(
      `[scale] ${kind}: ${s.n} items, was ${s.lo.toFixed(2)}-${s.hi.toFixed(2)} m ` +
        `(avg ${(s.sum / s.n).toFixed(2)}), real size ${target || "kept"}`,
    );
  }
}

/**
 * The shop's shopping trolley.
 *
 * The blend has it as loose parts -- basket, frame, handle and four wheels --
 * with no parent to hold them together, and it is modelled at nearly twice the
 * boy's height: 2.9 m tall and 2.2 m wide against his 1.49 m.  So the parts are
 * collected by name, hung on a pivot at the cart's own footprint on the floor and
 * scaled down to a real trolley's proportions (about two thirds of the boy, which
 * is what a trolley looks like beside the person pushing it), with the pivot left
 * on the floor so it shrinks towards the ground instead of floating.
 */
const CART_PARTS = /^Circle0(35|38|39|40|41|42|43|44|45|46)$|^Plane03[4-7]$/;
/** a real trolley stands about two thirds of a person's height */
const CART_SCALE = 0.33;

function findCart(root: THREE.Object3D, skip: THREE.Object3D[], extra: string[] = []): CartNode | null {
  const parts: THREE.Object3D[] = [];
  for (const name of [
    "Circle035", "Circle038", "Circle039", "Circle040", "Circle041", "Circle046",
    "Circle042", "Circle043", "Circle044", "Circle045",
    "Plane034", "Plane035", "Plane036", "Plane037",
    ...extra,
  ]) {
    const o = root.getObjectByName(name);
    if (o && !skip.includes(o)) parts.push(o);
  }
  if (parts.length < 4) return null;

  root.updateMatrixWorld(true);
  const bb = new THREE.Box3();
  const box = new THREE.Box3();
  box.makeEmpty();
  for (const p of parts) {
    bb.setFromObject(p);
    if (!bb.isEmpty()) box.union(bb);
  }
  if (box.isEmpty()) return null;
  const size = new THREE.Vector3();
  box.getSize(size);
  const centre = new THREE.Vector3();
  box.getCenter(centre);

  const group = new THREE.Group();
  group.name = "Cart";
  // the pivot stands on the floor under the cart's centre
  group.position.set(centre.x, box.min.y, centre.z);
  root.add(group);
  for (const p of parts) group.attach(p);
  group.scale.setScalar(CART_SCALE);

  const cart: CartNode = {
    group,
    home: { x: centre.x, y: -centre.z },
    reach: (Math.max(size.x, size.z) / 2) * CART_SCALE,
    height: size.y * CART_SCALE,
  };
  console.info(
    `[cart] ${parts.length} parts, ${size.x.toFixed(2)}x${size.y.toFixed(2)}x${size.z.toFixed(2)} m ` +
      `scaled to ${(size.x * CART_SCALE).toFixed(2)}x${cart.height.toFixed(2)}x${(size.z * CART_SCALE).toFixed(2)} m`,
  );
  return cart;
}

/**
 * The colour of the goods themselves, so the carousel tile looks like the packet
 * on the shelf: the first mesh in the subtree that has a material of its own.
 */
function packetColour(o: THREE.Object3D): string {
  let hex = "#c8a24a";
  o.traverse((c) => {
    if (hex !== "#c8a24a") return;
    const m = (c as THREE.Mesh).material as THREE.MeshStandardMaterial | undefined;
    if (m && m.color) hex = `#${m.color.getHexString()}`;
  });
  return hex;
}

/**
 * Three of the shop's display bottles came out of the blend at twenty times their
 * size: they stand 5.8 m tall, taller than the shelf unit beside them, and read as
 * part of the building rather than as shopping.  A real bottle of that shape is
 * about 32 cm, so they are shrunk about their own base -- the ring they stand on
 * stays where it is -- and the whole shop reads at one scale again.
 */
function numberBottles(root: THREE.Object3D): string[] {
  const bb = new THREE.Box3();
  const size = new THREE.Vector3();
  const fixed: string[] = [];
  const targets: THREE.Object3D[] = [];
  root.traverse((o) => {
    // display pieces sit at the top of the scene, not inside a shelf group
    if (o.parent !== root || !/^pulle\d+$/i.test(o.name)) return;
    bb.setFromObject(o);
    if (!bb.isEmpty()) targets.push(o);
  });
  for (const o of targets) {
    bb.setFromObject(o);
    if (bb.isEmpty()) continue;
    bb.getSize(size);
    if (!(size.y > 2.5)) continue;
    o.scale.multiplyScalar(0.32 / size.y);
    const after = new THREE.Box3().setFromObject(o);
    o.position.y += bb.min.y - after.min.y;
    fixed.push(`${o.name} ${size.y.toFixed(2)}m -> 0.32m`);
  }
  return fixed;
}

/**
 * The three-wheeler's paint.
 *
 * The blend built its body as ONE panel carrying six materials, and the export
 * splits that into one mesh per material, hung side by side under the same group
 * -- so each part can be addressed on its own without touching the rest of the
 * tricycle.  Three of them are the customer's: the shell, which the blend painted
 * (204,0,0) and which is the red the tricycle wears; the wide grey band across its
 * nose at screen height; and a small grey pressing low at the very front.  The
 * shell goes yellow, the front pressing goes green, and the band becomes real
 * glass rather than a painted slab.
 *
 * Everything else on the tricycle -- the canopy, the gold trim, the inner shell,
 * the frame posts, the chrome, the seats and the wheels -- keeps the colour the
 * blend gave it.  The materials are cloned before they are changed, so a name
 * shared with the rest of the shop cannot leak the repaint outward.
 */
const TUKTUK_SHELL = "AnodizedMetal"; // the red body shell
const TUKTUK_SCREEN = "Material.020"; // the grey band across the nose
const TUKTUK_YELLOW = 0xffc400;
const TUKTUK_GREEN = 0x1f9d55;

/** real glass: mostly transparent, barely any roughness, a whisper of tint */
function glassMaterial(): THREE.MeshPhysicalMaterial {
  return new THREE.MeshPhysicalMaterial({
    color: 0xdff1f5,
    metalness: 0,
    roughness: 0.03,
    transmission: 0.94,
    thickness: 0.02,
    ior: 1.52,
    transparent: true,
    opacity: 0.42,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
}

function paintTuktuk(root: THREE.Object3D): string[] {
  const tuk = root.getObjectByName("TukTuk_root");
  if (!tuk) return [];
  const notes: string[] = [];
  const matOf = (m: THREE.Mesh): THREE.Material | null =>
    (Array.isArray(m.material) ? m.material[0] : m.material) ?? null;

  const meshes: THREE.Mesh[] = [];
  tuk.traverse((o) => {
    if ((o as THREE.Mesh).isMesh) meshes.push(o as THREE.Mesh);
  });

  // the body panel: the group that carries the red shell, and its own meshes
  const shell = meshes.find((m) => matOf(m)?.name === TUKTUK_SHELL);
  const panel = shell?.parent ?? null;
  const panelMeshes = panel
    ? (panel.children.filter((c) => (c as THREE.Mesh).isMesh) as THREE.Mesh[])
    : meshes;

  // 1. the shell goes yellow
  if (shell) {
    const mat = matOf(shell)!.clone();
    (mat as THREE.MeshStandardMaterial).color.setHex(TUKTUK_YELLOW);
    mat.name = `${TUKTUK_SHELL}_yellow`;
    shell.material = mat;
    notes.push(`body ${TUKTUK_SHELL} -> #${TUKTUK_YELLOW.toString(16)}`);
  }

  // 2. the grey band across the nose becomes glass
  for (const m of panelMeshes) {
    if (matOf(m)?.name !== TUKTUK_SCREEN) continue;
    const glass = glassMaterial();
    glass.name = `${TUKTUK_SCREEN}_glass`;
    // keep the panel's own silhouette, but let the light through it
    m.material = glass;
    m.renderOrder = 2;
    notes.push(`screen ${TUKTUK_SCREEN} -> glass`);
  }

  // 3. the smallest grey pressing among the panel's own meshes is the front
  //    bumper: the others are the shell's liner, which is grey too and must stay
  for (const m of panelMeshes) {
    const mat = matOf(m);
    if (!mat || mat.name !== "Aluminium") continue;
    const box = new THREE.Box3().setFromObject(m);
    if (box.isEmpty()) continue;
    const size = box.getSize(new THREE.Vector3());
    const volume = size.x * size.y * size.z;
    // the liner is metres across; the bumper is a third of that
    if (volume > 1.0) continue;
    const clone = (mat as THREE.MeshStandardMaterial).clone();
    clone.color.setHex(TUKTUK_GREEN);
    clone.name = "Aluminium_bumper_green";
    m.material = clone;
    notes.push(
      `bumper ${m.name} (${size.x.toFixed(2)}x${size.y.toFixed(2)}x${size.z.toFixed(2)}) -> #${TUKTUK_GREEN.toString(16)}`,
    );
  }

  console.info(`[tuktuk] ${notes.join("; ") || "nothing matched"}`);
  return notes;
}

/**
 * The ceiling: the roof slabs and everything hanging off them -- the four lamp
 * housings, their tubes and brackets, and the light panels.  In plan view the
 * camera looks straight down through all of it, and leaving the lamps behind hid
 * half the shop behind white boxes; anything standing in the ceiling zone of the
 * building is part of what the camera should see through.
 */
function findRoof(root: THREE.Object3D): THREE.Object3D[] {
  const out: THREE.Object3D[] = [];
  const bb = new THREE.Box3();
  const size = new THREE.Vector3();
  const roofZone = WORLD_ROOF_Y;
  root.traverse((o) => {
    if (!(o as THREE.Mesh).isMesh) return;
    bb.setFromObject(o);
    if (bb.isEmpty()) return;
    bb.getSize(size);
    if (bb.min.y > roofZone) out.push(o);
  });
  return out;
}

/** the front and rear axle groups of each vehicle, for working out which end is the nose */
const AXLES: Record<string, { front: RegExp; rear: RegExp }> = {
  SUV_root: { front: /WheelFt[LR]$/, rear: /WheelBk[LR]$/ },
  TukTuk_root: { front: /^Wheel$/, rear: /^Wheel\d{3}$/ },
};

/**
 * Where the vehicle's nose points in its own local frame, from the wheels it is
 * standing on: front axle centre minus rear axle centre.
 */
function noseOffset(node: THREE.Object3D, id: string): number {
  const spec = AXLES[id];
  if (!spec) return 0;
  node.updateMatrixWorld(true);
  const p = new THREE.Vector3();
  const mid = (re: RegExp) => {
    let n = 0;
    const sum = new THREE.Vector3();
    node.traverse((o) => {
      if (o.type === "Bone" || !re.test(o.name)) return;
      node.getWorldPosition(p);
      o.getWorldPosition(p);
      sum.add(node.worldToLocal(p));
      n += 1;
    });
    return n ? sum.divideScalar(n) : null;
  };
  const front = mid(spec.front);
  const rear = mid(spec.rear);
  if (!front || !rear) return 0;
  const dx = front.x - rear.x;
  const dz = front.z - rear.z;
  if (Math.hypot(dx, dz) < 0.4) return 0;
  // the model may be rolled, so measure the yaw in its own frame, not the world's
  const e = node.matrixWorld.elements;
  const yawWorld = Math.atan2(dx * Math.sign(e[0]) || dx, dz);
  return Math.atan2(dx, dz) - 0 * yawWorld;
}

/** the one place Blender's axes turn into three's */
export function simToThree(x: number, y: number, z: number, out = new THREE.Vector3()) {
  return out.set(x, z, -y);
}

export async function loadRealScene(
  url: string,
  onProgress?: (fraction: number) => void,
): Promise<RealScene> {
  const loader = new GLTFLoader();
  const gltf = await loader.loadAsync(url, (e) => {
    if (onProgress && e.total) onProgress(Math.min(1, e.loaded / e.total));
  });
  const root = gltf.scene;

  // Hide what Blender would never render: the game's HUD (React draws that now)
  // and the car rig's bone widgets, which only exist as viewport helper shapes.
  const hide: THREE.Object3D[] = [];
  let skinned = 0;
  let meshes = 0;
  root.traverse((o) => {
    if (/^HUD_|^P_|^WGT|widget|_widget/i.test(o.name)) hide.push(o);
    // A leftover text object -- the shop's own name, 7.3 m long and 22 cm thick --
    // is still lying flat on the sales floor at y = 0.11, so the title reads as if
    // it were written across the floor tiles.  It is dead geometry the blend kept
    // as a backup, not a sign: a real shopfront sign belongs on the facade.
    if (/^Text_OLD_backup$/i.test(o.name)) hide.push(o);
    if ((o as THREE.SkinnedMesh).isSkinnedMesh) skinned += 1;
    if ((o as THREE.Mesh).isMesh) meshes += 1;
  });
  for (const o of hide) o.visible = false;

  // the export now carries WGT/HUD lights too; lights.json is the authority, with
  // the units and shadow maps we control, so drop anything the loader created
  const imported: THREE.Object3D[] = [];
  root.traverse((o) => {
    if ((o as THREE.Light).isLight) imported.push(o);
  });
  for (const l of imported) l.parent?.remove(l);

  // the geometry is the real thing now, so let it shadow itself -- but only the
  // parts big enough to read as a shadow: casting from all 1034 meshes doubles
  // the draw calls for no visible gain (a 5 cm shelf item casts nothing you can see)
  const box = new THREE.Box3();
  const size = new THREE.Vector3();
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh) return;
    mesh.receiveShadow = true;
    box.setFromObject(mesh);
    box.getSize(size);
    const span = Math.max(size.x, size.y, size.z);
    mesh.castShadow = span > 0.35;
  });

  // three culls a skinned mesh by its bind-pose bounds, so a limb that leaves
  // those bounds blinks out mid-stride: the classic vanishing body part
  root.traverse((o) => {
    if ((o as THREE.SkinnedMesh).isSkinnedMesh) o.frustumCulled = false;
  });

  // group the rigs: one armature per boy, found from their skinned meshes
  const boys: Record<number, THREE.Object3D> = {};
  const armatures: THREE.Object3D[] = [];
  root.traverse((o) => {
    if ((o as THREE.SkinnedMesh).isSkinnedMesh) {
      let top: THREE.Object3D = o;
      while (top.parent && top.parent !== root && top.parent.type !== "Scene") top = top.parent;
      if (!armatures.includes(top)) armatures.push(top);
    }
  });
  armatures.sort((a, b) => a.name.localeCompare(b.name));
  // the two boys carry the scene's rigs; the car rig is the third armature
  const boyRigs = armatures.filter((a) => /boy|rig/i.test(a.name) && !/car/i.test(a.name));
  const chosen = boyRigs.length >= 2 ? boyRigs.slice(0, 2) : armatures.slice(0, 2);
  chosen.forEach((rig, i) => (boys[i] = rig));

  // animation: the export carries the walk cycle (plus facial clips)
  const mixers: THREE.AnimationMixer[] = [];
  const gaits: Record<number, Gait> = {};
  const walkClip = gltf.animations.find((c) => c.name === "walk");
  chosen.forEach((rig, i) => {
    if (!walkClip) return;
    const mixer = new THREE.AnimationMixer(rig);
    const action = mixer.clipAction(walkClip);
    action.play();
    action.timeScale = 1;
    mixers.push(mixer);
    gaits[i] = { action, mixer, ...calibrateGait(rig, mixer, action, root) };
  });

  const props = new Map<string, THREE.Object3D>();
  for (const name of ["Prop_Item_1", "Prop_Item_2", "Prop_Item_3", "Prop_Item_4"]) {
    const o = root.getObjectByName(name);
    if (o) props.set(name, o);
  }

  const vehicles = new Map<string, VehicleNode>();
  for (const id of ["SUV_root", "TukTuk_root"]) {
    const o = root.getObjectByName(id);
    if (!o) continue;
    // The blend parks these with a half turn baked into the node (the SUV's rest
    // quaternion is a full 180 degrees of yaw), and the UPBGE game always replaced
    // the rotation instead of adding to it.  The car's own wheels say which way it
    // really faces, so work the offset out from them rather than trusting the file.
    const offset = noseOffset(o, id);
    const data = (WORLD.vehicles as Record<string, { door: string | null; door_angle: number }>)[id];
    const doorNode = data?.door ? o.getObjectByName(data.door) ?? null : null;
    vehicles.set(id, {
      node: o,
      baseY: o.position.y,
      restQuat: o.quaternion.clone(),
      yawOffset: offset,
      door: doorNode
        ? {
            node: doorNode,
            base: doorNode.rotation.y,
            open: ((data?.door_angle ?? 48) * Math.PI) / 180,
          }
        : null,
    });
    console.info(
      `[vehicle] ${id}: yaw offset ${((offset * 180) / Math.PI).toFixed(1)} deg` +
        (doorNode ? `, door ${doorNode.name}` : ", no door"),
    );
    // The three-wheeler was exported a fifth too big for the street, and a fifth
    // is exactly what it needed to look right beside the car and the pavement.
    // Its own measurement goes with it, so the simulation keeps agreeing with
    // what is on screen: scale the model, and scale what it collides with.
    if (id === "TukTuk_root") {
      o.scale.multiplyScalar(TUKTUK_SCALE);
      const vd = (WORLD.vehicles as Record<string, { width: number; length: number; body_fwd: number; seat: [number, number, number] }>)[id];
      if (vd) {
        vd.width *= TUKTUK_SCALE;
        vd.length *= TUKTUK_SCALE;
        vd.body_fwd *= TUKTUK_SCALE;
        vd.seat = [vd.seat[0] * TUKTUK_SCALE, vd.seat[1] * TUKTUK_SCALE, vd.seat[2] * TUKTUK_SCALE];
      }
      console.info(`[vehicle] ${id} scaled to ${Math.round(TUKTUK_SCALE * 100)}%`);
      o.updateMatrixWorld(true);
      paintTuktuk(root);
    }
  }

  // these leaves are scene-level nodes, so their transforms are already in the
  // exported Y-up convention: Blender's swing about Z arrives as a turn about Y
  const doors: { node: THREE.Object3D; base: number; sign: number }[] = [];
  const signs: Record<string, number> = { Shop_Door_L: -1, Shop_Door_R: 1 };
  for (const [name, sign] of Object.entries(signs)) {
    const o = root.getObjectByName(name);
    if (o) doors.push({ node: o, base: o.rotation.y, sign });
  }

  const clips: Record<string, THREE.AnimationClip> = {};
  for (const c of gltf.animations) clips[c.name] = c;

  const shrunk = numberBottles(root);
  if (shrunk.length) console.info(`[bottles] left at the blend's display size: ${shrunk.join(", ")}`);

  // the cashier: a third boy, cloned the same way, who works behind the counter
  let cashier: RealScene["cashier"] = null;
  if (chosen[0]) {
    const rig = cloneSkinned(chosen[0]) as THREE.Object3D;
    rig.name = "Cashier";
    root.add(rig);
    const mixer = new THREE.AnimationMixer(rig);
    let action: THREE.AnimationAction | null = null;
    if (walkClip) {
      action = mixer.clipAction(walkClip);
      action.play();
      action.timeScale = 0;
    }
    cashier = { root: rig, mixer, walk: action };
  }

  // the bag the shopping is packed into: a paper carrier, made here rather than
  // looked for, because the blend has none
  const bag = new THREE.Group();
  bag.name = "ShoppingBag";
  {
    const paper = new THREE.MeshStandardMaterial({ color: 0xb98c4a, roughness: 0.85 });
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.34, 0.15), paper);
    body.position.y = 0.17;
    const top = new THREE.Mesh(
      new THREE.BoxGeometry(0.27, 0.07, 0.16),
      new THREE.MeshStandardMaterial({ color: 0x8f6a34, roughness: 0.9 }),
    );
    top.position.y = 0.37;
    bag.add(body, top);
    bag.visible = false;
    body.castShadow = true;
    root.add(bag);
  }

  // the roof stays out of the solid set and out of the way in plan view
  const roof = findRoof(root);
  // Circle036 and Circle037 are the basket's two rims, left loose in the scene
  // beside the rest of the trolley; they belong to it, and hung on the same pivot
  // they come down to the right size with it.
  const cart = findCart(root, [], ["Circle036", "Circle037"]);
  const products = collectProducts(root, [
    ...Object.values(boys),
    ...[...vehicles.values()].map((v) => v.node),
    ...roof,
    ...(cart ? [cart.group] : []),
  ]);
  // everything on the shelves, brought from the blend's drawings to real size
  sizeProducts(products);
  // The trolley is dragged round the shop now, so it cannot start the game full:
  // everything that was modelled standing in its basket comes out of the world.
  const inBasket = cart
    ? products.filter(
        (p) => Math.hypot(p.pos.x - cart.home.x, p.pos.y - cart.home.y) < Math.max(1.0, cart.reach / CART_SCALE),
      )
    : [];
  for (const p of inBasket) p.node.visible = false;
  const shelves = products.filter((p) => !inBasket.includes(p));
  for (const p of shelves) if (!props.has(p.name)) props.set(p.name, p.node);
  console.info(`[products] ${shelves.length} items on the shelves are pickable`);
  if (inBasket.length) console.info(`[cart] emptied: ${inBasket.length} items were modelled in the basket`);
  console.info(`[roof] ${roof.length} roof pieces: ${roof.map((o) => o.name).join(", ")}`);

  return {
    root,
    boys,
    gaits,
    mixers,
    props,
    products: shelves,
    roof,
    cart,
    cashier,
    bag,
    vehicles,
    doors,
    walkClip: walkClip ?? null,
    clips,
    animations: gltf.animations,
    skinned,
    meshes,
  };
}

/**
 * A real boy, cloned for another shopper.  A capsule coloured per player was the
 * cheap stand-in, but it looks nothing like the blend; SkeletonUtils.clone is the
 * only way to duplicate a skinned mesh and its skeleton correctly.
 */
export function makeAvatar(
  real: RealScene,
  template = 0,
): {
  root: THREE.Object3D;
  mixer: THREE.AnimationMixer;
  walk: THREE.AnimationAction | null;
  naturalSpeed: number;
  passing: number;
} {
  const src = real.boys[template] ?? real.boys[0];
  if (!src) throw new Error("no boy rig to clone");
  const root = cloneSkinned(src) as THREE.Object3D;
  const mixer = new THREE.AnimationMixer(root);
  let walk: THREE.AnimationAction | null = null;
  const gait = real.gaits[template] ?? real.gaits[0];
  if (real.walkClip) {
    walk = mixer.clipAction(real.walkClip);
    walk.play();
    walk.timeScale = 0;
  }
  return {
    root,
    mixer,
    walk,
    naturalSpeed: gait ? gait.naturalSpeed : 0,
    passing: gait ? gait.passing : 0,
  };
}

/** the clip plays at the speed the boy actually moves, so the feet do not skate */
export function gaitRate(speed: number, naturalSpeed: number) {
  if (!(naturalSpeed > 0.05)) return 1;
  const r = speed / naturalSpeed;
  // This export's walk is a brisk one: a 0.72 m step, two of them every 0.383 s,
  // so its own speed is nearly 4 m/s and the boy's 1.28 m/s wants about a third
  // of the rate.  The floor used to sit at 0.45 and forced the feet to skate.
  return r < 0.3 ? 0.3 : r > 2.2 ? 2.2 : r;
}

/**
 * Work the walk cycle out from the rig itself: how far the feet travel in one
 * cycle (so the clip can be played at the speed the boy is actually moving, which
 * is what stops the feet skating) and when they pass under the body (the pose to
 * hold when he is standing still).
 *
 * The feet are found rather than named.  This rig has a thousand bones and the
 * names are the rigger's own -- matching /foot|ankle|toe/ picked 128 of them,
 * helper bones and mocap markers included, and measuring between the wrong two
 * gave a stride of five metres.  What actually marks a foot is that it hangs
 * lowest and swings furthest, so: sample the cycle, keep the bones that come
 * down near the floor, and take the two that travel furthest along the rig's
 * forward axis.  Distances are then converted to world metres, because the rig
 * itself is scaled by a tenth and the clip's speed has to come out in metres per
 * second to mean anything.
 */
function calibrateGait(
  rig: THREE.Object3D,
  mixer: THREE.AnimationMixer,
  action: THREE.AnimationAction,
  scene: THREE.Object3D,
): { naturalSpeed: number; passing: number; stride: number } {
  const fallback = { naturalSpeed: 0, passing: 0, stride: 0 };
  const dur = action.getClip().duration || 0;
  if (dur <= 0) return fallback;

  const bones: THREE.Bone[] = [];
  rig.traverse((o) => {
    if (!(o as THREE.Bone).isBone) return;
    if (/ik|ctrl|control|target|helper|twist/i.test(o.name)) return;
    bones.push(o as THREE.Bone);
  });
  if (!bones.length) return fallback;

  const samples = 48;
  const n = bones.length;
  const zs = new Float32Array(n * samples);
  const ys = new Float32Array(n);
  const p = new THREE.Vector3();
  const wasPaused = action.paused;
  const wasTime = action.time;
  action.paused = true;
  for (let k = 0; k < samples; k++) {
    action.time = (k / samples) * dur;
    mixer.update(0);
    scene.updateMatrixWorld(true);
    for (let b = 0; b < n; b++) {
      rig.worldToLocal(bones[b].getWorldPosition(p));
      zs[b * samples + k] = p.z;
      if (k === 0 || p.y < ys[b]) ys[b] = p.y;
    }
  }
  action.paused = wasPaused;
  action.time = wasTime;
  mixer.update(0);

  let lo = Infinity;
  let hi = -Infinity;
  for (let b = 0; b < n; b++) {
    if (ys[b] < lo) lo = ys[b];
    if (ys[b] > hi) hi = ys[b];
  }
  const height = hi - lo;
  if (!(height > 1e-6)) return fallback;

  // a foot is a bone that comes down into the bottom quarter of the rig
  const cand: { b: number; swing: number; x: number }[] = [];
  for (let b = 0; b < n; b++) {
    if (ys[b] > lo + height * 0.25) continue;
    let mn = Infinity;
    let mx = -Infinity;
    for (let k = 0; k < samples; k++) {
      const z = zs[b * samples + k];
      if (z < mn) mn = z;
      if (z > mx) mx = z;
    }
    bones[b].getWorldPosition(p);
    cand.push({ b, swing: mx - mn, x: rig.worldToLocal(p).x });
  }
  if (cand.length < 2) return fallback;
  cand.sort((a, b) => b.swing - a.swing);
  const a = cand[0];
  // the other foot is the furthest-swinging candidate on the other side of the body
  const b = cand.find((c) => c.b !== a.b && Math.sign(c.x) !== Math.sign(a.x) && c.swing > a.swing * 0.35)
    ?? cand[1];

  let maxSep = 0;
  let minSep = Infinity;
  let passing = 0;
  for (let k = 0; k < samples; k++) {
    const gap = Math.abs(zs[a.b * samples + k] - zs[b.b * samples + k]);
    if (gap > maxSep) maxSep = gap;
    if (gap < minSep) {
      minSep = gap;
      passing = (k / samples) * dur;
    }
  }

  // rig space is scaled: three on the same axis, averaged
  const s = new THREE.Vector3();
  rig.getWorldScale(s);
  const scale = (s.x + s.y + s.z) / 3;
  const stride = maxSep * scale;
  if (!(stride > 0.05)) return { ...fallback, passing };
  return { naturalSpeed: (2 * stride) / dur, passing, stride };
}

const V = new THREE.Vector3();
const UP = new THREE.Vector3(0, 1, 0);
const YAW = new THREE.Quaternion();

/** where the boy's shopping goes on the counter, and where the bag is left */
const TILL_TABLE: [number, number, number] = [1.95, -7.0, 1.24];
const TILL_SCAN: [number, number, number] = [1.95, -6.0, 1.24];
const TILL_BAG: [number, number, number] = [1.95, -5.4, 1.24];

/** push the simulation's state onto the loaded Blender objects */
export function driveRealScene(real: RealScene, game: Game, dt: number) {
  // the two boys
  for (let i = 0; i < 2; i++) {
    const rig = real.boys[i];
    if (!rig) continue;
    const a = game.actors[i];
    simToThree(a.pos.x, a.pos.y, a.pos.z, V);
    rig.position.copy(V);
    rig.rotation.y = a.yaw;
    // At the wheel he is inside the car, and the car is what the camera should
    // be looking at: the seat point is only there to hang the cabin's own
    // maths on.  Left visible he stands on the roof of the car he is driving.
    rig.visible = a.vehicle === null;
    const gait = real.gaits[i];
    if (!gait) continue;
    if (a.anim === "walk") {
      gait.action.timeScale = gaitRate(a.speed, gait.naturalSpeed);
    } else if (gait.action.timeScale !== 0) {
      // the export has no idle/reach/sit clip, so hold the pose where the feet
      // pass under the body instead of freezing him mid-stride
      gait.action.timeScale = 0;
      gait.action.time = gait.passing;
    }
  }

  // shelf items.  There are hundreds of them now (everything on every shelf can
  // be picked up), so only the ones that have left their place are touched: the
  // rest still sit exactly where the blend put them.
  for (const [name, node] of real.props) {
    const p = game.propIndex.get(name);
    if (!p || !p.moved) continue;
    const at =
      game.player.carrying === name && game.player.pending === null
        ? game.carriedPos() ?? p.pos
        : p.pos;
    simToThree(at.x, at.y, at.z, V);
    if (node.parent !== real.root) {
      // lift it out of the shelf group it was modelled in, keeping the pose it
      // had, so the simulation's own world position can drive it from here on
      node.updateWorldMatrix(true, false);
      real.root.attach(node);
    }
    node.position.copy(V);
    node.visible = true;
  }

  // the trolley: its place, and the way it is turned, belong to the simulation
  if (real.cart) {
    const c = game.cart;
    simToThree(c.pos.x, c.pos.y, 0, V);
    real.cart.group.position.set(V.x, real.cart.group.position.y, V.z);
    real.cart.group.rotation.y = c.yaw;
  }

  // what is in the trolley rides with it, laid out across the basket in the order
  // it went in, so the shopping is visibly there and visibly growing
  if (game.cart.items.length) {
    const c = game.cart;
    const f = { x: Math.sin(c.yaw), y: -Math.cos(c.yaw) };
    const l = { x: -Math.cos(c.yaw), y: -Math.sin(c.yaw) };
    for (let i = 0; i < game.cart.items.length; i++) {
      const node = real.props.get(game.cart.items[i]);
      if (!node) continue;
      const row = Math.floor(i / 2);
      const side = i % 2 === 0 ? -1 : 1;
      const fx = -0.12 - row * 0.18;
      const lx = side * 0.15;
      simToThree(c.pos.x + f.x * fx + l.x * lx, c.pos.y + f.y * fx + l.y * lx, 0.5 + row * 0.02, V);
      if (node.parent !== real.root) {
        node.updateWorldMatrix(true, false);
        real.root.attach(node);
      }
      node.position.copy(V);
      node.rotation.y = c.yaw;
      node.visible = true;
    }
  }

  // the till: everything he has put on the counter, the cashier's side of it, and
  // her own hands moving each item across
  const tillRow = (name: string, i: number, base: [number, number, number]) => {
    const node = real.props.get(name);
    if (!node) return;
    // the counter is a metre and a quarter wide and a metre long: lay the goods
    // out in two rows of four and start a second layer when the top is full
    const along = 0.26 * (Math.floor(i / 2) % 4);
    const across = i % 2 === 0 ? -0.09 : 0.09;
    const layer = Math.floor(i / 8) * 0.17;
    simToThree(base[0] + across, base[1] + along, base[2] + 0.06 + layer, V);
    if (node.parent !== real.root) {
      node.updateWorldMatrix(true, false);
      real.root.attach(node);
    }
    node.position.copy(V);
    node.rotation.y = 0;
    node.visible = true;
  };
  game.till.mine.forEach((name, i) => tillRow(name, i, TILL_TABLE));
  const holder = game.cashier.holding;
  game.till.scanned.forEach((name, i) => {
    if (name === holder) {
      // in her hand, over the scanner
      const node = real.props.get(name);
      if (node) {
        // over the scanner, just past her hands
        simToThree(TILL_SCAN[0] - 0.75, TILL_SCAN[1] - 1.3, TILL_SCAN[2] + 0.3, V);
        node.position.copy(V);
        node.visible = true;
      }
      return;
    }
    tillRow(name, i, TILL_SCAN);
  });
  // sold and bagged: out of the world
  for (const p of game.props) {
    if (!p.sold) continue;
    const node = real.props.get(p.name);
    if (node) node.visible = false;
  }

  // the carrier bag: on the counter, then in his hand
  if (real.bag) {
    const b = real.bag;
    if (game.bag === "counter") {
      simToThree(TILL_BAG[0], TILL_BAG[1], TILL_BAG[2], V);
      b.position.copy(V);
      b.visible = true;
    } else if (game.bag === "carried") {
      const at = game.carryPoint(game.player);
      simToThree(at.x, at.y, at.z - 0.45, V);
      b.position.copy(V);
      b.visible = true;
    } else {
      b.visible = false;
    }
  }

  // the cashier behind the till
  if (real.cashier) {
    const cs = game.cashier;
    simToThree(cs.pos.x, cs.pos.y, cs.pos.z, V);
    real.cashier.root.position.copy(V);
    real.cashier.root.rotation.y = cs.yaw;
    real.cashier.root.visible = true;
    if (real.cashier.walk) {
      // the export has no reach clip either: she holds the pose where the hands
      // pass the body, which reads as reaching over the counter
      real.cashier.walk.timeScale = 0;
      real.cashier.walk.time = (real.gaits[0]?.passing ?? 0) + (cs.anim === "reach" ? 0.06 : 0);
    }
    real.cashier.mixer.update(dt);
  }

  // vehicles: the simulation owns their place on the road, the blend owns height
  for (const [id, entry] of real.vehicles) {
    const v = game.vehicles.find((x) => x.id === id);
    if (!v) continue;
    simToThree(v.pos.x, v.pos.y, 0, V);
    entry.node.position.set(V.x, entry.baseY, V.z);
    // replace the rotation, exactly like the desktop game did, with the offset the
    // model's own wheels asked for
    YAW.setFromAxisAngle(UP, v.yaw - entry.yawOffset);
    entry.node.quaternion.copy(YAW);
    // the door swings open for him and shuts behind him
    if (entry.door) {
      entry.door.node.rotation.y = entry.door.base + entry.door.open * v.doorFrac;
    }
  }

  // the shop's swinging leaves
  for (const d of real.doors) {
    d.node.rotation.y = d.base + ((Math.PI * 96) / 180) * d.sign * game.doorOpen;
  }

  for (const m of real.mixers) m.update(dt);
}
