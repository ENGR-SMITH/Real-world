// Lights and sky, taken from the Blender scene rather than invented.
//
// The glTF export dropped the blend's 5 lights and its procedural sky texture, so
// the web build was lit by a flat studio environment map — which is why every
// surface read as washed-out grey.  `9g_fix_materials.py` writes the real values
// to /assets/lights.json; this turns them into three.js objects.
//
// Units are kept consistent with Blender's: a directional light's intensity is
// irradiance (W/m²) and a point light's is radiant intensity (W/sr = energy/4π)
// with decay 2, so the *ratios* between lights match the blend exactly.
import * as THREE from "three";
import { Sky } from "three/examples/jsm/objects/Sky.js";

export type BlenderLight = {
  name: string;
  type: string; // POINT | SUN | SPOT
  energy: number;
  color: [number, number, number];
  loc: [number, number, number];
  dir: [number, number, number];
  radius: number;
};

export type BlenderSky = {
  sun_elevation?: number;
  sun_rotation?: number;
  sun_intensity?: number;
  altitude?: number;
  air_density?: number;
  dust_density?: number;
  turbidity?: number;
  ground_albedo?: number;
  bg_color?: [number, number, number, number];
  bg_strength?: number;
};

export type LightsFile = { lights: BlenderLight[]; sky: BlenderSky };

/** Blender (x, y, z) -> three (x, z, -y), matching realScene.simToThree */
function bl2three(x: number, y: number, z: number) {
  return new THREE.Vector3(x, z, -y);
}

export function buildLights(
  file: LightsFile,
  opts: { shadows?: boolean; pointShadows?: boolean; shadowMapSize?: number } = {},
): THREE.Object3D[] {
  const shadows = opts.shadows ?? true;
  // the four interior point lights would each cost a full shadow pass over a
  // million triangles; the sun's shadow is the one that reads as "real"
  const pointShadows = opts.pointShadows ?? false;
  const mapSize = opts.shadowMapSize ?? 2048;
  const out: THREE.Object3D[] = [];

  for (const l of file.lights || []) {
    const colour = new THREE.Color(l.color[0], l.color[1], l.color[2]);
    const pos = bl2three(l.loc[0], l.loc[1], l.loc[2]);

    if (l.type === "SUN") {
      // Blender sun strength is irradiance in W/m², which is what a three
      // directional light's intensity already means: pass it straight through.
      const sun = new THREE.DirectionalLight(colour, l.energy);
      const dir = bl2three(l.dir[0], l.dir[1], l.dir[2]).normalize();
      sun.position.copy(dir.clone().multiplyScalar(-60).add(new THREE.Vector3(0, 0, 0)));
      sun.target.position.set(0, 0, 0);
      if (shadows) {
        sun.castShadow = true;
        sun.shadow.mapSize.set(mapSize, mapSize);
        // the street runs ~90 m; bias tuned against the shop facade
        const cam = sun.shadow.camera;
        cam.left = -45;
        cam.right = 45;
        cam.top = 45;
        cam.bottom = -45;
        cam.near = 1;
        cam.far = 220;
        sun.shadow.bias = -0.0006;
        sun.shadow.normalBias = 0.04;
      }
      sun.name = l.name;
      out.push(sun, sun.target);
      continue;
    }

    // point/spot: radiant intensity in W/sr, and decay 2 like Blender's falloff
    const intensity = l.energy / (4 * Math.PI);
    if (l.type === "SPOT") {
      const spot = new THREE.SpotLight(colour, intensity, 0, Math.PI / 4, 0.3, 2);
      spot.position.copy(pos);
      if (pointShadows) {
        spot.castShadow = true;
        spot.shadow.mapSize.set(1024, 1024);
        spot.shadow.bias = -0.0008;
      }
      spot.name = l.name;
      out.push(spot, spot.target);
    } else {
      const p = new THREE.PointLight(colour, intensity, 0, 2);
      p.position.copy(pos);
      if (pointShadows) {
        p.castShadow = true;
        p.shadow.mapSize.set(1024, 1024);
        p.shadow.bias = -0.0025;
        p.shadow.normalBias = 0.05;
      }
      p.name = l.name;
      out.push(p);
    }
  }
  return out;
}

/**
 * Blender's procedural sky (ShaderNodeTexSky) as a three.js Sky, used both as the
 * background and — via PMREM — as the image-based lighting for every material.
 * Without this the scene's ambient light comes from nowhere near the same sky.
 */
/** A Sky configured from the blend's ShaderNodeTexSky parameters. */
function makeSky(sky: BlenderSky, sunDir?: THREE.Vector3): Sky {
  const mesh = new Sky();
  mesh.scale.setScalar(4_500_000);
  // uniform sets differ between three versions (e.g. `up` was removed), so set
  // only what this build actually has rather than assuming a fixed layout
  const u = mesh.material.uniforms as Record<string, { value: unknown }>;
  const set = (k: string, v: unknown) => {
    if (u[k]) u[k].value = v;
  };
  // Blender dust_density ~1 is a clear day; three's turbidity is roughly 2x that
  set("turbidity", sky.turbidity ?? 2.0 + (sky.dust_density ?? 1) * 1.5);
  set("rayleigh", sky.air_density ?? 1.0);
  set("mieCoefficient", 0.005);
  set("mieDirectionalG", 0.8);
  set("up", new THREE.Vector3(0, 1, 0));

  let dir = sunDir ? sunDir.clone() : null;
  if (!dir) {
    const elevation = sky.sun_elevation ?? 0.45;
    const rotation = sky.sun_rotation ?? 0;
    const theta = Math.PI / 2 - elevation; // polar angle measured from up
    dir = new THREE.Vector3().setFromSphericalCoords(1, theta, rotation);
  }
  const sunPos = dir.normalize().clone();
  // the shader's gradient is driven by sunPosition; keep it off the nadir
  set("sunPosition", sunPos.y < 0.2 ? sunPos.setY(0.2).normalize() : sunPos);
  return mesh;
}

/**
 * Blender's procedural sky (ShaderNodeTexSky) as a three.js Sky, used both as the
 * background and — via PMREM — as the image-based lighting for every material.
 * Without this the scene's ambient light comes from nowhere near the same sky.
 */
export function applySky(
  scene: THREE.Scene,
  renderer: THREE.WebGLRenderer,
  sky: BlenderSky,
  sunDir?: THREE.Vector3,
): Sky {
  const skyMesh = makeSky(sky, sunDir);
  scene.add(skyMesh);
  // a Sky is a mesh, not a texture: three renders it as the backdrop because it
  // is enormous, which is the documented usage of this shader
  scene.background = skyMesh as unknown as THREE.Texture;

  // image-based lighting from the same sky, so metals have the real sky to mirror
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envScene = new THREE.Scene();
  envScene.add(makeSky(sky, sunDir));
  // the sky is bright enough to light the street on its own; a full-strength
  // environment blows the whole frame out (measured mean luminance 218/255), so
  // keep just enough to give the metals something to mirror -- Blender's own
  // world is nearly black here (Background strength 0.02) and its 5 lamps do the work
  const rt = pmrem.fromScene(envScene, 0, 0.1, 5000);
  scene.environment = rt.texture;
  scene.environmentIntensity = 0.08;
  pmrem.dispose();

  return skyMesh;
}
