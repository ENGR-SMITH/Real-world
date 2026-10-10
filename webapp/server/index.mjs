// Realtime layer: player positions (10 Hz) and chat for everyone in the shop.
// Run with `npm run server` (defaults to port 3011).
import { createServer } from "node:http";
import { Server } from "socket.io";

// note: an inherited PORT of 0 must fall back, not bind to a random port
const PORT = Number(process.env.PORT) || 3011;
const COLOURS = [
  "#38bdf8", "#f472b6", "#a3e635", "#fbbf24",
  "#c084fc", "#fb7185", "#2dd4bf", "#f97316",
];

const http = createServer((req, res) => {
  res.writeHead(200, { "content-type": "application/json" });
  res.end(JSON.stringify({ ok: true, players: players.size, room: "shop" }));
});

const io = new Server(http, { cors: { origin: "*", methods: ["GET", "POST"] } });

/** id -> { id, name, x, y, z, yaw, anim, carrying, colour, active } */
const players = new Map();

const spawn = () => ({
  x: -5.4 + (Math.random() - 0.5) * 1.6,
  y: 6.0 + (Math.random() - 0.5) * 1.6,
  z: 0.06,
});

io.on("connection", (socket) => {
  const colour = COLOURS[players.size % COLOURS.length];
  const at = spawn();

  socket.on("join", (payload = {}) => {
    const name = String(payload?.name ?? "Shopper").slice(0, 24);
    const me = {
      id: socket.id,
      name,
      colour,
      yaw: 0,
      anim: "idle",
      carrying: null,
      active: 0,
      ...at,
    };
    players.set(socket.id, me);
    socket.emit("welcome", {
      id: socket.id,
      players: [...players.values()].filter((p) => p.id !== socket.id),
    });
    socket.broadcast.emit("move", me);
    console.log(`+ ${name} (${socket.id}) — ${players.size} online`);
  });

  socket.on("move", (p = {}) => {
    const me = players.get(socket.id);
    if (!me) return;
    me.x = Number(p.x) || 0;
    me.y = Number(p.y) || 0;
    me.z = Number(p.z) || 0;
    me.yaw = Number(p.yaw) || 0;
    me.anim = typeof p.anim === "string" ? p.anim : "idle";
    me.carrying = p.carrying ?? null;
    me.active = Number(p.active) || 0;
    socket.broadcast.volatile.emit("move", me);
  });

  socket.on("chat", (p = {}) => {
    const me = players.get(socket.id);
    const text = String(p?.text ?? "").trim().slice(0, 200);
    if (!me || !text) return;
    io.emit("chat", { id: `${socket.id}-${Date.now()}`, name: me.name, text, at: Date.now() });
  });

  socket.on("disconnect", () => {
    players.delete(socket.id);
    io.emit("left", { id: socket.id });
    console.log(`- ${socket.id} — ${players.size} online`);
  });
});

http.listen(PORT, () => console.log(`shop-street realtime on http://localhost:${PORT}`));
