"use client";

// Local game state: what the HUD shows, who else is online, and the live chat.
// The simulation itself lives outside React (see lib/game.ts) and only pushes a
// snapshot here when something the player can see actually changes.
import { create } from "zustand";

export type CamMode = "third" | "iso";

export type RemotePlayer = {
  id: string;
  name: string;
  x: number;
  y: number;
  z: number;
  yaw: number;
  anim: string;
  carrying: string | null;
  colour: string;
};

export type ChatMsg = { id: string; name: string; text: string; at: number };

/** one tile of the shelf carousel: something the boy could pick up from here */
export type ShelfItem = {
  name: string;
  /** the colour of the goods themselves, so the carousel reads as the shelf does */
  colour: string;
  price: number;
};

/** one run of the carousel: a single kind of goods, under its own banner */
export type ShelfRow = {
  type: string;
  label: string;
  /** the banner's colour, taken from the packets on that run */
  colour: string;
  items: ShelfItem[];
};

export type Snapshot = {
  prompt: string | null;
  target: string | null;
  active: number;
  carrying: string | null;
  inVehicle: boolean;
  speed: number;
  doorOpen: number;
  cart: boolean;
  walking: boolean;
  /** the shelves beside him, one row per kind of goods, nearest run first */
  shelf: ShelfRow[];
  /** how many things are in the trolley */
  trolley: number;
  /** what the till has rung up, and what it comes to */
  receipt: { name: string; price: number }[];
  total: number;
  /** the packed bag is on the counter, waiting for him */
  bag: boolean;
  /** the product he is off to fetch, or null */
  task: string | null;
  /** true while he is inside the mall, which is what the carousel waits for */
  inShop: boolean;
};

export type GlbState = {
  progress: number;
  meshes?: number;
  skinned?: number;
  error: string | null;
};

type Store = {
  snap: Snapshot;
  camMode: CamMode;
  glb: GlbState;
  setGlb: (g: Partial<GlbState>) => void;
  connected: boolean;
  onlineCount: number;
  players: RemotePlayer[];
  chat: ChatMsg[];
  note: string;
  myId: string | null;
  myName: string;
  setSnapshot: (s: Snapshot) => void;
  setCam: (m: CamMode) => void;
  setConnected: (v: boolean, id?: string | null) => void;
  setPlayers: (p: RemotePlayer[]) => void;
  addChat: (m: ChatMsg) => void;
  setMyName: (n: string) => void;
  setNote: (s: string) => void;
};

const EMPTY: Snapshot = {
  prompt: null,
  target: null,
  active: 0,
  carrying: null,
  inVehicle: false,
  speed: 0,
  doorOpen: 0,
  cart: false,
  walking: false,
  shelf: [],
  trolley: 0,
  receipt: [],
  total: 0,
  bag: false,
  task: null,
  inShop: false,
};

function sameSnap(a: Snapshot, b: Snapshot) {
  return (
    a.prompt === b.prompt &&
    a.target === b.target &&
    a.active === b.active &&
    a.carrying === b.carrying &&
    a.inVehicle === b.inVehicle &&
    a.cart === b.cart &&
    a.walking === b.walking &&
    a.trolley === b.trolley &&
    a.total === b.total &&
    a.bag === b.bag &&
    a.task === b.task &&
    a.inShop === b.inShop &&
    (a.shelf?.length ?? 0) === (b.shelf?.length ?? 0) &&
    (a.shelf ?? []).every(
      (row, i) =>
        row.type === b.shelf?.[i]?.type &&
        (row.items?.length ?? 0) === (b.shelf?.[i]?.items?.length ?? 0) &&
        (row.items ?? []).every((it, j) => it.name === b.shelf?.[i]?.items?.[j]?.name),
    ) &&
    (a.receipt?.length ?? 0) === (b.receipt?.length ?? 0) &&
    Math.abs(a.speed - b.speed) < 0.05 &&
    Math.abs(a.doorOpen - b.doorOpen) < 0.02
  );
}

export const useGame = create<Store>((set, get) => ({
  snap: EMPTY,
  camMode: "third",
  glb: { progress: 0, error: null },
  setGlb: (g) => set((st) => ({ glb: { ...st.glb, ...g } })),
  connected: false,
  onlineCount: 1,
  players: [],
  chat: [],
  note: "",
  myId: null,
  myName: "Shopper",
  setSnapshot: (s) => {
    if (!sameSnap(get().snap, s)) set({ snap: s });
  },
  setCam: (camMode) => set({ camMode }),
  setConnected: (connected, id) =>
    set((st) => ({ connected, myId: id !== undefined ? id : st.myId })),
  setPlayers: (players) => set({ players, onlineCount: players.length + 1 }),
  addChat: (m) => set((st) => ({ chat: [...st.chat, m].slice(-60) })),
  setMyName: (myName) => set({ myName }),
  setNote: (note) => set({ note }),
}));
