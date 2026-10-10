"use client";

// Multiplayer transport.  The shop works perfectly well alone, so a missing or
// dead realtime server only means no other shoppers and no chat.
import { io, type Socket } from "socket.io-client";
import type { ChatMsg, RemotePlayer } from "@/store/gameStore";

export const SOCKET_URL =
  process.env.NEXT_PUBLIC_SOCKET_URL ?? "http://localhost:3011";

export type MovePacket = {
  x: number;
  y: number;
  z: number;
  yaw: number;
  anim: string;
  carrying: string | null;
  active: number;
};

export type Net = {
  socket: Socket | null;
  send: (p: MovePacket) => void;
  chat: (text: string) => void;
  close: () => void;
};

export const PLAYER_COLOURS = [
  "#38bdf8",
  "#f472b6",
  "#a3e635",
  "#fbbf24",
  "#c084fc",
  "#fb7185",
  "#2dd4bf",
  "#f97316",
];

export function connectNet(opts: {
  name: () => string;
  onWelcome: (id: string, players: RemotePlayer[]) => void;
  onMove: (p: RemotePlayer) => void;
  onLeave: (id: string) => void;
  onChat: (m: ChatMsg) => void;
  onStatus: (connected: boolean) => void;
}): Net {
  let socket: Socket | null = null;
  try {
    socket = io(SOCKET_URL, {
      transports: ["websocket", "polling"],
      reconnectionAttempts: 5,
      timeout: 4000,
    });
  } catch {
    return { socket: null, send: () => {}, chat: () => {}, close: () => {} };
  }

  socket.on("connect", () => {
    opts.onStatus(true);
    socket?.emit("join", { name: opts.name() });
  });
  socket.on("disconnect", () => opts.onStatus(false));
  socket.on("connect_error", () => opts.onStatus(false));
  socket.on("welcome", (p: { id: string; players: RemotePlayer[] }) => opts.onWelcome(p.id, p.players));
  socket.on("move", (p: RemotePlayer) => opts.onMove(p));
  socket.on("left", (p: { id: string }) => opts.onLeave(p.id));
  socket.on("chat", (m: ChatMsg) => opts.onChat(m));

  return {
    socket,
    send: (p) => socket?.volatile.emit("move", p),
    chat: (text) => socket?.emit("chat", { text }),
    close: () => socket?.close(),
  };
}
