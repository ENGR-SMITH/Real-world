"use client";

import * as React from "react";
import dynamic from "next/dynamic";

import { Hud } from "@/components/Hud";
import { connectNet, type Net } from "@/lib/net";
import { useGame, type RemotePlayer } from "@/store/gameStore";

// the world is browser-only: no server rendering for the renderer
const GameCanvas = dynamic(() => import("@/components/GameCanvas"), { ssr: false });

export default function Page() {
  const net = React.useRef<Net | null>(null);
  const addChat = useGame((s) => s.addChat);
  const setPlayers = useGame((s) => s.setPlayers);
  const setConnected = useGame((s) => s.setConnected);
  const myName = useGame((s) => s.myName);
  const nameRef = React.useRef(myName);
  nameRef.current = myName;
  const roster = React.useRef<Map<string, RemotePlayer>>(new Map());

  React.useEffect(() => {
    const flush = () => setPlayers([...roster.current.values()]);
    net.current = connectNet({
      name: () => nameRef.current,
      onStatus: (v) => setConnected(v),
      onWelcome: (id, list) => {
        setConnected(true, id);
        roster.current = new Map(list.map((p) => [p.id, p]));
        roster.current.delete(id);
        flush();
      },
      onMove: (p) => {
        roster.current.set(p.id, p);
        flush();
      },
      onLeave: (id) => {
        roster.current.delete(id);
        flush();
      },
      onChat: (m) => addChat(m),
    });
    return () => net.current?.close();
  }, [addChat, setConnected, setPlayers]);

  return (
    <main className="relative h-dvh w-full overflow-hidden bg-slate-950 text-slate-100">
      <GameCanvas net={net} />
      <Hud />
    </main>
  );
}
