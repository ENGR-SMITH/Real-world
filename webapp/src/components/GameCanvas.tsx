"use client";

// The rendered world: shop.glb, exported from Shop_with_people.blend, driven by
// the simulation.  Blender's axes become three's through simToThree() (x, z, -y)
// with yaw keeping its sign, so the view matches the blend rather than mirroring it.
//
// The look is deliberately Blender's: an environment map (glTF materials are PBR,
// a metallic surface with nothing to reflect renders black), AgX tone mapping
// (Blender 4's default view transform) and no fog washing the colours out.
import * as React from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { applySky, buildLights, type LightsFile } from "@/lib/lights";
import { installSolids } from "@/lib/collide";

import { T, WORLD, blocked, canStand, groundZ, solidsBlocked } from "@/lib/world";
import { Game, fwd, type Prompt } from "@/lib/game";
import {
  clearPulses,
  heldKeys,
  inputState,
  keyToAction,
  pressTab as pressTabPulse,
  pressUse as pressUsePulse,
  setMove,
  syncInput,
} from "@/lib/input";
import {
  driveRealScene,
  gaitRate,
  loadRealScene,
  makeAvatar,
  simToThree,
  type RealScene,
} from "@/lib/realScene";
import { useGame, type RemotePlayer } from "@/store/gameStore";
import type { Net } from "@/lib/net";

const GLB_URL = "/assets/shop3.glb";

const GameRef: { current: Game | null } = { current: null };
const RemoteRef: { current: Map<string, RemotePlayer> } = { current: new Map() };
const RealRef: { current: RealScene | null } = { current: null };
const MarkerRef: { current: THREE.Group | null } = { current: null };

const scratch = new THREE.Vector3();
const scratch2 = new THREE.Vector3();

/** the plan view: eight metres up and six back, so it looks over his shoulder */
const ISO_BACK = 6.0;
const ISO_UP = 8.0;

/**
 * The blend's own lighting: 4 point lights and a sun, plus its sky.  glTF carried
 * none of it, so without this the scene is lit by a flat studio environment map.
 */
function SceneLighting() {
  const { scene, gl } = useThree();
  const [data, setData] = React.useState<LightsFile | null>(null);

  React.useEffect(() => {
    let alive = true;
    fetch("/assets/lights.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => alive && setData(d))
      .catch(() => alive && setData(null));
    return () => {
      alive = false;
    };
  }, []);

  React.useEffect(() => {
    if (!data) return;
    const prevBg = scene.background;
    const prevEnv = scene.environment;
    const sky = applySky(scene, gl, data.sky || {});
    const lights = buildLights(data, { shadows: true, shadowMapSize: 2048 });
    for (const l of lights) scene.add(l);
    return () => {
      for (const l of lights) scene.remove(l);
      scene.remove(sky);
      sky.geometry.dispose();
      (sky.material as THREE.Material).dispose();
      scene.background = prevBg;
      scene.environment = prevEnv;
    };
  }, [data, scene, gl]);

  return null;
}

/** other shoppers: capsules, because cloning a 1037-bone rig per player is not affordable */
/**
 * Another shopper, drawn as the real boy model rather than a coloured capsule.
 * The rig is cloned with SkeletonUtils (the only correct way to duplicate a
 * skinned mesh) and driven by the same walk clip as the player.
 */
function Ghost({ id }: { colour: string; id: string }) {
  const holder = React.useRef<THREE.Group>(null!);
  const avatar = React.useRef<ReturnType<typeof makeAvatar> | null>(null);
  const last = React.useRef<{ x: number; y: number } | null>(null);

  useFrame((_, dt) => {
    const g = holder.current;
    if (!g) return;
    // the 58 MB scene arrives long after this component mounts, so build the
    // clone on the first frame the rig actually exists rather than in an effect
    if (!avatar.current && RealRef.current) {
      const a = makeAvatar(RealRef.current, 1);
      g.add(a.root);
      avatar.current = a;
    }
    const a = avatar.current;
    if (!a) return;

    const r = RemoteRef.current.get(id);
    if (!r) {
      a.root.visible = false;
      return;
    }
    a.root.visible = true;
    a.root.position.set(r.x, r.z, -r.y);
    a.root.rotation.y = r.yaw;

    // walk only while they are actually moving, judged from their own motion, and
    // at the rate their own speed implies so the feet do not skate
    const prev = last.current;
    const moved = prev ? Math.hypot(r.x - prev.x, r.y - prev.y) : 0;
    last.current = { x: r.x, y: r.y };
    if (a.walk) {
      const speed = dt > 0 ? moved / dt : 0;
      a.walk.timeScale = speed > 0.08 ? gaitRate(speed, a.naturalSpeed) : 0;
      if (a.walk.timeScale === 0) a.walk.time = a.passing;
    }
    a.mixer.update(dt);
  });

  React.useEffect(
    () => () => {
      const a = avatar.current;
      if (a) {
        a.mixer.stopAllAction();
        a.root.removeFromParent();
      }
    },
    [],
  );

  return <group ref={holder} />;
}

/**
 * The highlights that replaced the messages at the top of the screen.
 *
 * Anything the boy can act on wears a ring on the floor: the shop door, the
 * trolley, each vehicle's door, and the things on the shelves near him.  A ring
 * turns green when the action is in reach, and clicking it tells the simulation
 * what to do -- from a distance the boy simply walks over and does it himself.
 */
const RING = new THREE.RingGeometry(0.3, 0.42, 28);
const RING_HOT = new THREE.MeshBasicMaterial({
  color: 0x34d399,
  transparent: true,
  opacity: 0.9,
  side: THREE.DoubleSide,
  depthWrite: false,
});
const RING_IDLE = new THREE.MeshBasicMaterial({
  color: 0x38bdf8,
  transparent: true,
  opacity: 0.55,
  side: THREE.DoubleSide,
  depthWrite: false,
});

type Marker = { key: string; kinds: Prompt[]; x: number; y: number; h: number; ready: boolean };

/** what deserves a highlight right now */
function markerSpecs(game: Game, real: RealScene): Marker[] {
  const out: Marker[] = [];
  const a = game.player;
  const doors = game.doorOpen > 0.5;
  const floor = (x: number, y: number, lift = 0.04) => (groundZ(x, y) ?? 0) + lift;

  // the shop door
  const c = WORLD.shop_door_centre;
  out.push({
    key: "door",
    kinds: [game.doorTarget > 0.5 ? "doorclose" : "dooropen"],
    x: c[0],
    y: c[1],
    h: floor(c[0], c[1], 0.12),
    ready: game.shopDoorDist(a) < 2.3,
  });

  // the trolley
  if (a.vehicle === null) {
    const cart = game.cart;
    if (cart.driver === null || cart.driver === a.id) {
      out.push({
        key: "cart",
        kinds: [cart.driver === a.id ? "release" : "grab"],
        x: cart.pos.x,
        y: cart.pos.y,
        h: floor(cart.pos.x, cart.pos.y, 0.05),
        ready: cart.driver === a.id || game.cartDist(a) < T.TAKE_RANGE + 0.35,
      });
    }
  }

  // a vehicle's door, whenever the boy is on foot
  if (a.vehicle === null) {
    for (const v of game.vehicles) {
      if (v.driver !== null) continue;
      const f = fwd(v.yaw);
      const r = { x: Math.cos(v.yaw), y: Math.sin(v.yaw) };
      const side = v.data.getout_side;
      const cx = v.pos.x + f.x * v.data.body_fwd + r.x * v.data.width * 0.5 * side;
      const cy = v.pos.y + f.y * v.data.body_fwd + r.y * v.data.width * 0.5 * side;
      const kinds: Prompt[] = [];
      if (v.data.door !== null && v.doorFrac <= 0.8) kinds.push("vehdoor");
      if (v.data.door === null || v.doorFrac > 0.8) kinds.push("enter");
      kinds.push("stop");
      const dist = Math.hypot(a.pos.x - cx, a.pos.y - cy);
      out.push({ key: v.id, kinds, x: cx, y: cy, h: floor(cx, cy, 0.05), ready: dist < 3.4 });
    }
  }

  // the things on the shelves within arm's length of a walk
  if (a.vehicle === null && real.products.length) {
    const near = real.products
      .map((p) => ({ p, d: Math.hypot(a.pos.x - p.pos.x, a.pos.y - p.pos.y) }))
      .filter((e) => e.d < 4.2)
      .sort((x, y) => x.d - y.d)
      .slice(0, 8);
    for (const e of near) {
      out.push({
        key: e.p.name,
        kinds: [a.carrying === e.p.name ? "drop" : "take"],
        x: e.p.pos.x,
        y: e.p.pos.y,
        h: floor(e.p.pos.x, e.p.pos.y, 0.05),
        ready: e.d < T.TAKE_RANGE,
      });
    }
  }
  return out;
}

function WorldMarkers() {
  const group = React.useRef<THREE.Group>(null!);
  const pool = React.useRef<THREE.Mesh[]>([]);

  useFrame(({ clock }) => {
    const g = group.current;
    const game = GameRef.current;
    const real = RealRef.current;
    if (!g || !game || !real) return;
    const specs = markerSpecs(game, real);
    while (pool.current.length < specs.length) {
      const m = new THREE.Mesh(RING, RING_IDLE);
      m.rotation.x = -Math.PI / 2;
      m.renderOrder = 4;
      g.add(m);
      pool.current.push(m);
    }
    const t = clock.elapsedTime;
    pool.current.forEach((m, i) => {
      const s = specs[i];
      m.visible = !!s;
      if (!s) return;
      simToThree(s.x, s.y, s.h, scratch);
      m.position.copy(scratch);
      m.scale.setScalar((s.ready ? 1.15 : 0.8) * (1 + 0.07 * Math.sin(t * 4 + i)));
      m.material = s.ready ? RING_HOT : RING_IDLE;
      m.userData.kinds = s.kinds;
      m.userData.mx = s.x;
      m.userData.my = s.y;
    });
  });

  React.useEffect(() => {
    MarkerRef.current = group.current;
  }, []);

  return <group ref={group} />;
}

function RealWorld() {
  const setGlb = useGame((s) => s.setGlb);
  const [ready, setReady] = React.useState<RealScene | null>(null);

  React.useEffect(() => {
    let alive = true;
    loadRealScene(GLB_URL, (f) => {
      if (alive) setGlb({ progress: f, error: null });
    })
      .then((real) => {
        if (!alive) return;
        RealRef.current = real;
        setReady(real);
        // collision from the geometry that is on screen (the blend's own blockers
        // were measured off a blockout, so the boy walked through the real walls)
        const vehicles: THREE.Object3D[] = [];
        for (const id of ["SUV_root", "TukTuk_root"]) {
          const o = real.root.getObjectByName(id);
          if (o) vehicles.push(o);
        }
        // the trolley is pushed about, so it cannot be a wall bolted to the floor
        if (real.cart) vehicles.push(real.cart.group);
        const info = installSolids(real.root, vehicles);
        // the shelves are the simulation's business now: hundreds of tins and
        // bottles became things the boy can pick up, and the trolley moved
        const game = GameRef.current;
        if (game) {
          game.setProducts(
            real.products.map((p) => ({ name: p.name, pos: p.pos, r: p.r, colour: p.colour })),
          );
          if (real.cart) game.setCart(real.cart.home, real.cart.reach);
        }
        const S = ((window as unknown as { __shop?: Record<string, unknown> }).__shop ??= {});
        S.real = real;
        S.collision = info;
        console.info(
          `[collision] ${info.solids} solids (${info.skippedFlat} flat parts ignored, ` +
            `${info.skippedWall} front-wall parts left to the sim), ` +
            `${info.blockersDropped} stale blockers dropped`,
        );
        setGlb({ progress: 1, meshes: real.meshes, skinned: real.skinned, error: null });
      })
      .catch((e: unknown) => {
        if (alive) setGlb({ error: String(e) });
      });
    return () => {
      alive = false;
    };
  }, [setGlb]);

  if (!ready) return null;
  return <primitive object={ready.root} />;
}

function Simulation({
  net,
  onSnapshot,
}: {
  net: React.RefObject<Net | null>;
  onSnapshot: (s: ReturnType<Game["snapshot"]>) => void;
}) {
  const { camera, gl, scene } = useThree();
  const camYaw = React.useRef(0);
  const camPos = React.useRef(new THREE.Vector3());
  const probe = React.useRef(0);
  const remoteMap = useGame((s) => s.players);
  const camMode = useGame((s) => s.camMode);
  const loaded = useGame((s) => s.glb.progress);
  const push = React.useRef(0);
  const netPush = React.useRef(0);

  React.useEffect(() => {
    RemoteRef.current = new Map(remoteMap.map((p) => [p.id, p]));
  }, [remoteMap]);

  // In plan view the roof is between the camera and everything worth looking at,
  // and the simulation is already drawn inside the shop: take the roof off.
  React.useEffect(() => {
    const real = RealRef.current;
    if (!real) return;
    for (const r of real.roof) r.visible = camMode !== "iso";
  }, [camMode, loaded]);

  /**
   * Clicks: a highlight does what it says, bare ground makes the boy walk there.
   * Both need the camera, so the listener lives here rather than in the HUD.
   */
  React.useEffect(() => {
    const el = gl.domElement;
    const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -0.05);
    const ndc = new THREE.Vector2();
    const ray = new THREE.Raycaster();
    const at = new THREE.Vector3();
    const onDown = (e: PointerEvent) => {
      if (e.button !== 0) return;
      const game = GameRef.current;
      if (!game) return;
      const box = el.getBoundingClientRect();
      ndc.set(
        ((e.clientX - box.left) / box.width) * 2 - 1,
        -((e.clientY - box.top) / box.height) * 2 + 1,
      );
      ray.setFromCamera(ndc, camera);
      const marks: THREE.Object3D[] = [];
      MarkerRef.current?.traverse((o) => {
        if (o.visible && o.userData.kinds) marks.push(o);
      });
      const hit = ray.intersectObjects(marks, false)[0];
      if (hit) {
        const ud = hit.object.userData as { kinds: Prompt[]; mx: number; my: number };
        game.request(ud.kinds, ud.mx, ud.my);
        return;
      }
      if (ray.ray.intersectPlane(plane, at)) {
        const sx = at.x;
        const sy = -at.z;
        if (groundZ(sx, sy) !== null) game.setWalkTarget(sx, sy);
      }
    };
    el.addEventListener("pointerdown", onDown);
    return () => el.removeEventListener("pointerdown", onDown);
  }, [gl, camera]);

  useFrame((_, rawDt) => {
    const g = GameRef.current;
    if (!g) return;
    const dt = Math.min(rawDt, 1 / 30);

    if (camMode === "iso") camYaw.current = Math.PI * 0.25;
    g.step({ ...inputState }, (y) => (camYaw.current = y), camYaw.current, dt);
    clearPulses();

    if (camMode === "third" && (inputState.mx !== 0 || inputState.my !== 0)) {
      const diff = ((g.player.yaw - camYaw.current + Math.PI) % (2 * Math.PI)) - Math.PI;
      camYaw.current += diff * Math.min(1, dt * 3.2);
    }

    const real = RealRef.current;
    if (real) driveRealScene(real, g, dt);

    const a = g.player;
    const driving = a.vehicle !== null ? g.vehicles.find((v) => v.id === a.vehicle) ?? null : null;
    if (camMode === "iso") {
      // Plan view, but hung behind the boy rather than over a fixed corner of the
      // world: whatever he is walking behind -- a shelf, a car, the shop wall --
      // is between the camera and him in a fixed view, and he disappears.
      const f = fwd(a.yaw);
      simToThree(a.pos.x - f.x * ISO_BACK, a.pos.y - f.y * ISO_BACK, a.pos.z + ISO_UP, scratch);
      camera.position.lerp(scratch, Math.min(1, dt * 4));
    } else if (driving) {
      // At the wheel the view belongs to the car, not to the boy: third person
      // again, but behind the boot and looking over the roof down the road.
      const f = fwd(driving.yaw);
      simToThree(
        driving.pos.x - f.x * T.CHASE_BACK,
        driving.pos.y - f.y * T.CHASE_BACK,
        driving.pos.z + T.CHASE_UP,
        scratch,
      );
      camPos.current.lerp(scratch, Math.min(1, dt * T.CAM_LAG * 0.6));
      camera.position.copy(camPos.current);
    } else {
      const f = fwd(camYaw.current);
      simToThree(a.pos.x - f.x * T.CAM_BACK, a.pos.y - f.y * T.CAM_BACK, a.pos.z + T.CAM_UP, scratch);
      camPos.current.lerp(scratch, Math.min(1, dt * T.CAM_LAG));
      camera.position.copy(camPos.current);
    }
    if (driving) {
      const f = fwd(driving.yaw);
      simToThree(
        driving.pos.x + f.x * driving.data.body_fwd * 0.5,
        driving.pos.y + f.y * driving.data.body_fwd * 0.5,
        driving.pos.z + 0.9,
        scratch2,
      );
    } else if (camMode === "iso") {
      const f = fwd(a.yaw);
      simToThree(a.pos.x + f.x * 2.0, a.pos.y + f.y * 2.0, a.pos.z + 0.6, scratch2);
    } else {
      simToThree(a.pos.x, a.pos.y, a.pos.z + T.CAM_LOOK_UP, scratch2);
    }
    camera.lookAt(scratch2);

    probe.current += 1;
    if (probe.current % 20 === 0) {
      const S = (window as unknown as { __shop?: Record<string, unknown> }).__shop;
      if (S) {
        S.perf = {
          frames: probe.current,
          frameMs: +(rawDt * 1000).toFixed(1),
          calls: gl.info.render.calls,
          triangles: gl.info.render.triangles,
          geometries: gl.info.memory.geometries,
          textures: gl.info.memory.textures,
        };
        S.three = { gl, scene, camera };
      }
    }

    push.current += dt;
    if (push.current > 0.12) {
      push.current = 0;
      onSnapshot(g.snapshot());
    }
    netPush.current += dt;
    if (netPush.current > 0.1) {
      netPush.current = 0;
      const p = g.player;
      net.current?.send({
        x: p.pos.x,
        y: p.pos.y,
        z: p.pos.z,
        yaw: p.yaw,
        anim: p.anim,
        carrying: p.carrying,
        active: g.active,
      });
    }
  });
  return null;
}

export default function GameCanvas({ net }: { net: React.RefObject<Net | null> }) {
  const setSnapshot = useGame((s) => s.setSnapshot);
  const players = useGame((s) => s.players);

  React.useEffect(() => {
    if (!GameRef.current) GameRef.current = new Game();
    // merge rather than replace: onCreated() may already have published gl/scene/camera
    const S = ((window as unknown as { __shop?: Record<string, unknown> }).__shop ??= {});
    Object.assign(S, {
      game: GameRef.current,
      store: useGame,
      input: inputState,
      setMove,
      pressUse: pressUsePulse,
      pressTab: pressTabPulse,
      // deterministic stepping: a hidden tab throttles rAF to 1 Hz, so scripted
      // playthroughs drive the simulation directly
      stepHeadless: (seconds: number, dt = 1 / 60) => {
        const gg = GameRef.current as Game;
        const n = Math.max(1, Math.round(seconds / dt));
        for (let i = 0; i < n; i++) gg.step({ ...inputState }, () => {}, gg.player.yaw, dt);
        clearPulses();
        return n;
      },
      walkTo: (x: number, y: number, tol = 0.35, maxSeconds = 25) => {
        const gg = GameRef.current as Game;
        const dt = 1 / 60;
        const steps = Math.round(maxSeconds / dt);
        for (let i = 0; i < steps; i++) {
          const a = gg.player.pos;
          const dx = x - a.x;
          const dy = y - a.y;
          if (Math.hypot(dx, dy) < tol) break;
          gg.step({ ...inputState, mx: 0, my: 1, run: false }, () => {}, Math.atan2(dx, -dy), dt);
        }
        const a = gg.player.pos;
        return { d: +Math.hypot(x - a.x, y - a.y).toFixed(3), at: [+a.x.toFixed(2), +a.y.toFixed(2)] };
      },
      /** why can (or can't) the boy stand here?  for the scripted checks */
      probe: (x: number, y: number, r = T.PLAYER_R) => {
        const z = groundZ(x, y);
        return {
          ground: z,
          blockers: blocked(x, y, r),
          solids: z === null ? null : solidsBlocked(x, y, r, z),
          canStand: canStand(x, y, r),
        };
      },
      face: (x: number, y: number, seconds = 0.7) => {
        const gg = GameRef.current as Game;
        const dt = 1 / 60;
        const n = Math.round(seconds / dt);
        for (let i = 0; i < n; i++) {
          const a = gg.player.pos;
          gg.step({ ...inputState, mx: 0, my: 1, run: false }, () => {},
                  Math.atan2(x - a.x, -(y - a.y)), dt);
        }
        return +gg.player.yaw.toFixed(3);
      },
      use: () => {
        const gg = GameRef.current as Game;
        gg.step({ ...inputState, use: true }, () => {}, gg.player.yaw, 1 / 60);
        clearPulses();
        return true;
      },
      tab: () => {
        const gg = GameRef.current as Game;
        gg.step({ ...inputState, tab: true }, () => {}, gg.player.yaw, 1 / 60);
        clearPulses();
        return gg.active;
      },
      /** what the physics settled on the last step, for the scripted checks */
      physics: () => GameRef.current?.physics ?? null,
      /** the route a click would take, for the scripted checks */
      route: (x: number, y: number) => {
        const gg = GameRef.current as Game;
        gg.setWalkTarget(x, y);
        gg.planRoute(x, y);
        return gg.walkPath;
      },
    });

    const down = (e: KeyboardEvent) => {
      const a = keyToAction(e.code);
      if (!a) return;
      e.preventDefault();
      if (e.repeat) return;
      if (a === "use") inputState.use = true;
      else if (a === "tab") inputState.tab = true;
      else {
        heldKeys.add(e.code);
        syncInput();
      }
    };
    const up = (e: KeyboardEvent) => {
      heldKeys.delete(e.code);
      syncInput();
    };
    const blur = () => {
      heldKeys.clear();
      syncInput();
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", blur);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", blur);
    };
  }, []);

  const onSnapshot = React.useCallback(
    (s: ReturnType<Game["snapshot"]>) => setSnapshot(s),
    [setSnapshot],
  );

  return (
    <Canvas
      shadows
      dpr={[1, 1.75]}
      camera={{ fov: 55, near: 0.05, far: 260, position: [-5.35, 3.5, -10] }}
      gl={{
        antialias: true,
        toneMapping: THREE.AgXToneMapping,
        toneMappingExposure: 0.85,
      }}
      onCreated={({ gl, scene, camera }) => {
        gl.shadowMap.type = THREE.PCFSoftShadowMap;
        // publish straight away: the throttled tab may take a minute to reach 20 frames
        const S = ((window as unknown as { __shop?: Record<string, unknown> }).__shop ??= {});
        S.three = { gl, scene, camera };
      }}
    >
      <SceneLighting />
      <RealWorld />
      <WorldMarkers />
      <Simulation net={net} onSnapshot={onSnapshot} />
    </Canvas>
  );
}
