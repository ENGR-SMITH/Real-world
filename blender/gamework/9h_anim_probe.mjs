// Read a .glb's animation table without a browser: which clips exist, how long
// they are, which nodes they drive, and whether those nodes are even in the file.
// The boys only seemed to carry a walk cycle, and tracks pointing at objects the
// exporter dropped are exactly what makes a rig look crumpled, so measure both.
import { readFileSync } from "node:fs";

const path = process.argv[2] || "../webapp/public/assets/shop3.glb";
const buf = readFileSync(path);
const magic = buf.readUInt32LE(0);
if (magic !== 0x46546c67) throw new Error("not a glb");
const jsonLen = buf.readUInt32LE(12);
const json = JSON.parse(buf.subarray(20, 20 + jsonLen).toString("utf8"));

const nodes = json.nodes || [];
const names = nodes.map((n) => n.name || "");
const byName = new Map();
names.forEach((n, i) => {
  if (n && !byName.has(n)) byName.set(n, i);
});

const accessors = json.accessors || [];
const dur = (i) => {
  const a = accessors[i];
  return a && a.max ? Number(a.max[0]).toFixed(3) : "?";
};

console.log(`nodes ${nodes.length}  meshes ${(json.meshes || []).length}  animations ${(json.animations || []).length}`);
for (const anim of json.animations || []) {
  const targets = new Set();
  const missing = new Set();
  const paths = {};
  let inputs = new Set();
  for (const ch of anim.channels) {
    const t = ch.target || {};
    if (t.node === undefined) continue;
    const nm = names[t.node] || "(unnamed)";
    targets.add(nm);
    paths[t.path] = (paths[t.path] || 0) + 1;
    if (!byName.has(nm)) missing.add(nm);
    if (ch.sampler !== undefined) inputs.add(anim.samplers[ch.sampler].input);
  }
  let d = 0;
  for (const i of inputs) {
    const v = parseFloat(dur(i));
    if (Number.isFinite(v) && v > d) d = v;
  }
  const sample = [...targets].slice(0, 6).join(",");
  console.log(
    `\n${anim.name}: ${anim.channels.length} channels, ${targets.size} nodes, ${d.toFixed(3)}s  ${JSON.stringify(paths)}` +
      (missing.size ? `  MISSING ${missing.size}: ${[...missing].slice(0, 5).join(",")}` : "") +
      `\n   targets: ${sample}`,
  );
}
