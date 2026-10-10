// Inspect a .glb without three.js: read the JSON chunk and walk the node tree,
// reporting world-space bounds per mesh.  Used to find the floor title and the
// tricycle's materials.
import { readFileSync } from "node:fs";

const file = process.argv[2] ?? "public/assets/shop3.glb";
const buf = readFileSync(file);
if (buf.readUInt32LE(0) !== 0x46546c67) throw new Error("not a glb");
let off = 12;
let json = null;
while (off < buf.length) {
  const len = buf.readUInt32LE(off);
  const type = buf.readUInt32LE(off + 4);
  const data = buf.subarray(off + 8, off + 8 + len);
  if (type === 0x4e4f534a) json = JSON.parse(data.toString("utf8"));
  off += 8 + len;
}
const g = json;
console.log("generator:", g.asset?.generator);
console.log("nodes", g.nodes.length, "meshes", g.meshes.length, "materials", g.materials.length, "images", (g.images ?? []).length);

// ---- 4x4 matrix helpers (column-major like glTF) ----
const I = () => [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
function mul(a, b) {
  const o = new Array(16).fill(0);
  for (let c = 0; c < 4; c++)
    for (let r = 0; r < 4; r++) {
      let s = 0;
      for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k];
      o[c * 4 + r] = s;
    }
  return o;
}
function trs(t = [0, 0, 0], r = [0, 0, 0, 1], s = [1, 1, 1]) {
  const [x, y, z, w] = r;
  const x2 = x + x, y2 = y + y, z2 = z + z;
  const xx = x * x2, xy = x * y2, xz = x * z2;
  const yy = y * y2, yz = y * z2, zz = z * z2;
  const wx = w * x2, wy = w * y2, wz = w * z2;
  return [
    (1 - (yy + zz)) * s[0], (xy + wz) * s[0], (xz - wy) * s[0], 0,
    (xy - wz) * s[1], (1 - (xx + zz)) * s[1], (yz + wx) * s[1], 0,
    (xz + wy) * s[2], (yz - wx) * s[2], (1 - (xx + yy)) * s[2], 0,
    t[0], t[1], t[2], 1,
  ];
}
const xform = (m, p) => [
  m[0] * p[0] + m[4] * p[1] + m[8] * p[2] + m[12],
  m[1] * p[0] + m[5] * p[1] + m[9] * p[2] + m[13],
  m[2] * p[0] + m[6] * p[1] + m[10] * p[2] + m[14],
];

// ---- world matrices ----
const world = new Array(g.nodes.length).fill(null);
function visit(i, parent) {
  const n = g.nodes[i];
  const local = n.matrix ? n.matrix : trs(n.translation, n.rotation, n.scale);
  world[i] = parent ? mul(parent, local) : local;
  for (const c of n.children ?? []) visit(c, world[i]);
}
for (const s of g.scenes[g.scene ?? 0].nodes) visit(s, null);

// ---- mesh bounds ----
const rows = [];
g.nodes.forEach((n, i) => {
  if (n.mesh === undefined) return;
  const mesh = g.meshes[n.mesh];
  let mn = [Infinity, Infinity, Infinity];
  let mx = [-Infinity, -Infinity, -Infinity];
  const mats = new Set();
  for (const pr of mesh.primitives) {
    if (pr.material !== undefined) mats.add(g.materials[pr.material]?.name ?? `#${pr.material}`);
    const acc = g.accessors[pr.attributes.POSITION];
    if (!acc?.min) continue;
    for (let b = 0; b < 8; b++) {
      const p = xform(world[i], [
        b & 1 ? acc.max[0] : acc.min[0],
        b & 2 ? acc.max[1] : acc.min[1],
        b & 4 ? acc.max[2] : acc.min[2],
      ]);
      for (let k = 0; k < 3; k++) {
        if (p[k] < mn[k]) mn[k] = p[k];
        if (p[k] > mx[k]) mx[k] = p[k];
      }
    }
  }
  rows.push({
    name: n.name ?? mesh.name ?? `node${i}`,
    size: [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]],
    mid: [(mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2],
    mn,
    mx,
    mats: [...mats],
  });
});
console.log("mesh nodes:", rows.length);

const mode = process.argv[3] ?? "flat";
if (mode === "flat") {
  // flat + near the floor + wide: the floor title takes exactly that shape
  const cand = rows
    .filter((r) => r.size[1] < 0.25 && r.mn[1] < 0.6 && Math.max(r.size[0], r.size[2]) > 1.5)
    .sort((a, b) => b.size[0] * b.size[2] - a.size[0] * a.size[2]);
  console.log(`\n--- flat, low, wide candidates (${cand.length}) ---`);
  for (const r of cand.slice(0, 60))
    console.log(
      `${r.name.padEnd(24)} size ${r.size.map((v) => v.toFixed(2)).join(" x ").padEnd(20)} mid ${r.mid.map((v) => v.toFixed(2)).join(", ").padEnd(22)} [${r.mats.join(",")}]`,
    );
}

const want = (str) => new RegExp(str, "i");
for (const str of ["shoprite", "supermarket", "market", "text", "label", "sign", "logo", "banner", "tuktuk", "tuk", "tricycle", "auto"]) {
  const hit = rows.filter((r) => want(str).test(r.name));
  if (hit.length)
    console.log(
      `\n=== /${str}/ (${hit.length})\n` +
        hit
          .slice(0, 40)
          .map(
            (r) =>
              `  ${r.name.padEnd(26)} size ${r.size.map((v) => v.toFixed(2)).join(" x ").padEnd(20)} mid ${r.mid.map((v) => v.toFixed(2)).join(", ").padEnd(22)} [${r.mats.join(",")}]`,
          )
          .join("\n"),
    );
}

if (process.argv.includes("--mats")) {
  console.log("\n--- materials ---");
  for (const m of g.materials) {
    const c = m.pbrMetallicRoughness?.baseColorFactor;
    console.log(
      `${(m.name ?? "?").padEnd(28)} base [${c ? c.slice(0, 3).map((v) => Math.round(v * 255)).join(",") : "-"}] tex ${m.pbrMetallicRoughness?.baseColorTexture?.index ?? "-"} metal ${m.pbrMetallicRoughness?.metallicFactor ?? "-"} rough ${m.pbrMetallicRoughness?.roughnessFactor ?? "-"} alpha ${m.alphaMode ?? "-"} double ${!!m.doubleSided}`,
    );
  }
}
