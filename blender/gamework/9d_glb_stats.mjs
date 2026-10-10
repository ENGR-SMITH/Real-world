// 9d_glb_stats.mjs -- what is actually inside shop2.glb?
import { readFileSync } from "node:fs";

const file = process.argv[2] || "E:/Reality/webapp/public/assets/shop2.glb";
const buf = readFileSync(file);
if (buf.readUInt32LE(0) !== 0x46546c67) throw new Error("not a glb");
let off = 12;
let json = null;
let binLen = 0;
while (off < buf.length) {
  const len = buf.readUInt32LE(off);
  const type = buf.readUInt32LE(off + 4);
  const body = buf.subarray(off + 8, off + 8 + len);
  if (type === 0x4e4f534a) json = JSON.parse(new TextDecoder().decode(body));
  else if (type === 0x004e4942) binLen = len;
  off += 8 + len + ((4 - (len % 4)) % 4) * 0;
  off = off + (0);
  // chunks are 4-byte aligned already; advance
  off = off;
  if (len % 4) off += 4 - (len % 4);
}

const g = json;
console.log("### file", file, (buf.length / 1048576).toFixed(1), "MB   bin", (binLen / 1048576).toFixed(1), "MB");
console.log("### generator:", g.asset?.generator);
console.log("### extensionsUsed:", JSON.stringify(g.extensionsUsed || []));
console.log("### counts: nodes", g.nodes?.length, " meshes", g.meshes?.length,
  " materials", g.materials?.length, " textures", (g.textures || []).length,
  " images", (g.images || []).length, " skins", (g.skins || []).length,
  " animations", (g.animations || []).length, " lights?", g.extensions?.KHR_lights_punctual ? "YES" : "no");
console.log("### animations:", (g.animations || []).map((a) => a.name).join(", "));

// how many primitives use a base-colour texture vs a plain factor
let tex = 0, flat = 0, noMat = 0;
const flatColours = new Map();
for (const mesh of g.meshes || []) {
  for (const p of mesh.primitives || []) {
    if (p.material == null) { noMat++; continue; }
    const m = g.materials[p.material];
    const pbr = m.pbrMetallicRoughness || {};
    if (pbr.baseColorTexture) tex++;
    else {
      flat++;
      const c = (pbr.baseColorFactor || [1, 1, 1, 1]).map((v) => Math.round(v * 255));
      const k = `${m.name} rgb(${c[0]},${c[1]},${c[2]}) metal=${pbr.metallicFactor ?? 1} rough=${pbr.roughnessFactor ?? 1}`;
      flatColours.set(k, (flatColours.get(k) || 0) + 1);
    }
  }
}
console.log("### primitives: textured", tex, " flat-colour", flat, " no-material", noMat);

const top = [...flatColours.entries()].sort((a, b) => b[1] - a[1]);
console.log("### top flat materials (name, colour, metal/rough, primitives):");
for (const [k, n] of top.slice(0, 30)) console.log("   ", n, "x", k);

// list the images so we can see what textures actually shipped
console.log("### images:");
for (const im of (g.images || []).slice(0, 40)) console.log("   ", im.name || "(unnamed)", im.mimeType, "bv", im.bufferView);
