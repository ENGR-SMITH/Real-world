"use client";

import * as React from "react";
import { collectProduct, pressHand, pressUse, setRun } from "@/lib/input";
import { useGame } from "@/store/gameStore";

/** what the context button is offering, in words */
const WHAT: Record<string, string> = {
  take: "Take it",
  drop: "Put it down",
  dooropen: "Open shop door",
  doorclose: "Close shop door",
  stop: "Stop the vehicle",
  vehdoor: "Open vehicle door",
  enter: "Get in",
  getout: "Get out",
  grab: "Take the trolley",
  release: "Leave the trolley",
  unload: "Unload one onto the till",
  takebag: "Take the bag",
};

const money = (v: number) => v.toFixed(2);

/**
 * The shelf, laid out across the top of the screen: everything within arm's reach
 * and a step, gathered into one row per kind of goods.  Each row leads with a
 * banner in the packets' own colour, the way the shelves themselves are branded --
 * tins on one run, bottles on the next, the brand boxes after them -- and the tiles
 * carry the colour of the packet, so the strip reads like the shelf he is at.  A
 * click sends him to fetch that product and trolley it.
 *
 * None of this exists outside the mall: the simulation returns no shelves on the
 * street, so the strip is absent until he is through the shop door.
 */
function Shelf() {
  const shelf = useGame((s) => s.snap.shelf);
  const inShop = useGame((s) => s.snap.inShop);
  const task = useGame((s) => s.snap.task);
  const trolley = useGame((s) => s.snap.trolley);
  if (!inShop || shelf.length === 0) return null;
  return (
    <div className="pointer-events-auto absolute inset-x-0 top-2 flex justify-center px-2">
      <div className="max-w-[94vw] rounded-2xl border border-slate-700/80 bg-slate-950/85 p-1.5 shadow-2xl backdrop-blur-sm">
        <div className="flex items-center gap-2 pb-0.5">
          <span className="shrink-0 pl-1 pr-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            shelves
          </span>
          <div className="flex flex-1 gap-2 overflow-x-auto pb-0.5">
            {shelf.map((row) => (
              <div
                key={row.type}
                className="flex shrink-0 items-stretch overflow-hidden rounded-xl border border-slate-700 bg-slate-900/70"
              >
                {/* the banner: the run's name, in the packets' own colour */}
                <div
                  className="flex w-[54px] shrink-0 flex-col items-center justify-center gap-0.5 px-1 text-center"
                  style={{ background: row.colour }}
                >
                  <span className="text-[10px] font-extrabold uppercase leading-tight text-slate-950 drop-shadow">
                    {row.label}
                  </span>
                  <span className="text-[9px] font-semibold leading-none text-slate-900/70">
                    {row.items.length}
                  </span>
                </div>
                <div className="flex items-center gap-1 p-1">
                  {row.items.map((it) => (
                    <button
                      key={it.name}
                      onClick={() => collectProduct(it.name)}
                      title={`${it.name} — ${money(it.price)}`}
                      className={
                        "flex h-14 w-14 shrink-0 flex-col items-center justify-center gap-0.5 rounded-lg border text-[9px] leading-none transition " +
                        (task === it.name
                          ? "border-emerald-400 bg-emerald-500/25 text-emerald-100"
                          : "border-slate-700 bg-slate-900/80 text-slate-300 hover:border-sky-400/70 hover:bg-slate-800")
                      }
                    >
                      <span
                        className="h-5 w-5 rounded-md border border-white/20"
                        style={{ background: it.colour }}
                      />
                      <span className="text-slate-500">{money(it.price)}</span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
          {trolley > 0 && (
            <span className="shrink-0 self-center rounded-lg bg-emerald-500/20 px-2 py-1 text-[10px] font-semibold text-emerald-200">
              🛒 {trolley}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * The phone: the boy's control panel, bottom right.  Everything he can do lives
 * here, fronted by the one thing he can do from where he is standing, and the
 * rest of the screen is left to the world itself -- the door and the trolley and
 * the cars carry their own highlights now.
 */
function Phone() {
  const snap = useGame((s) => s.snap);
  const camMode = useGame((s) => s.camMode);
  const setCam = useGame((s) => s.setCam);
  const connected = useGame((s) => s.connected);
  const [run, setRunMode] = React.useState(false);

  const action = snap.prompt ? WHAT[snap.prompt] ?? snap.prompt : null;

  const App = ({
    label,
    icon,
    onClick,
    hot,
    on,
  }: {
    label: string;
    icon: string;
    onClick: () => void;
    hot?: boolean;
    on?: boolean;
  }) => (
    <button
      onClick={onClick}
      className={
        "flex h-14 flex-col items-center justify-center gap-0.5 rounded-xl border text-[10px] leading-none transition " +
        (hot
          ? "border-emerald-400/70 bg-emerald-500/25 text-emerald-100 shadow-[0_0_12px_-2px_rgba(52,211,153,0.7)]"
          : on
            ? "border-sky-400/60 bg-sky-500/20 text-sky-100"
            : "border-slate-700 bg-slate-800/70 text-slate-300 hover:bg-slate-700/70")
      }
    >
      <span className="text-base">{icon}</span>
      {label}
    </button>
  );

  return (
    <div className="pointer-events-auto absolute bottom-4 right-4 w-[236px] rounded-[26px] border-4 border-slate-700 bg-slate-950 shadow-2xl">
      <div className="flex justify-center pt-1.5">
        <span className="h-1 w-9 rounded-full bg-slate-700" />
      </div>
      <div className="flex items-center justify-between px-3 py-1.5">
        <b className="text-[11px] text-slate-200">Boy</b>
        <span className="text-[10px] text-slate-500">
          {snap.inVehicle
            ? `${snap.speed.toFixed(1)} m/s`
            : snap.cart
              ? "pushing trolley"
              : snap.walking
                ? "on the way"
                : connected
                  ? "online"
                  : "solo"}
        </span>
        <span
          className={"h-1.5 w-1.5 rounded-full " + (connected ? "bg-emerald-400" : "bg-slate-600")}
          title={connected ? "realtime connected" : "offline — playing solo"}
        />
      </div>

      <div className="mx-2 mb-2 rounded-2xl bg-slate-900/80 p-2">
        <div className="grid grid-cols-3 gap-1.5">
          <App
            label={snap.inVehicle ? "Get out" : "Door"}
            icon="🚪"
            hot={
              snap.prompt === "dooropen" ||
              snap.prompt === "doorclose" ||
              snap.prompt === "enter" ||
              snap.prompt === "getout"
            }
            onClick={pressUse}
          />
          <App
            label="Trolley"
            icon="🛒"
            hot={snap.prompt === "grab" || snap.prompt === "release"}
            on={snap.cart}
            onClick={pressUse}
          />
          <App
            label="Till"
            icon="🧾"
            hot={snap.prompt === "unload" || snap.prompt === "takebag"}
            onClick={pressUse}
          />
          <App
            label={snap.carrying ? "Drop" : "Take"}
            icon={snap.carrying ? "🤲" : "🤏"}
            hot={snap.prompt === "take" || snap.prompt === "drop"}
            onClick={pressUse}
          />
          <App
            label="Hurry"
            icon="🏃"
            on={run}
            onClick={() => {
              const v = !run;
              setRunMode(v);
              setRun(v);
            }}
          />
          <App label="View" icon="🎥" onClick={() => setCam(camMode === "iso" ? "third" : "iso")} />
        </div>

        <button
          onClick={pressUse}
          className={
            "mt-1.5 w-full rounded-xl px-2 py-2 text-xs font-semibold transition " +
            (action ? "bg-emerald-500 text-slate-950 hover:bg-emerald-400" : "bg-slate-800 text-slate-500")
          }
        >
          {action ?? "nothing here to do"}
        </button>

        <div className="mt-1.5 rounded-xl border border-slate-700 bg-slate-950/70 p-1.5 text-[10px]">
          <div className="flex justify-between text-slate-400">
            <span>{camMode === "iso" ? "isometric view" : "behind him"}</span>
            <span>arrows to walk · click the floor</span>
          </div>
          {snap.receipt.length > 0 && (
            <div className="mt-1 border-t border-slate-800 pt-1">
              <div className="mb-0.5 flex justify-between text-slate-300">
                <b>Receipt</b>
                <b>{money(snap.total)}</b>
              </div>
              <div className="max-h-24 overflow-y-auto">
                {snap.receipt.map((r, i) => (
                  <div key={`${r.name}-${i}`} className="flex justify-between text-slate-500">
                    <span className="truncate pr-2">{r.name}</span>
                    <span>{money(r.price)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {snap.bag && (
            <div className="mt-1 rounded-lg bg-emerald-500/15 px-1.5 py-1 text-center font-semibold text-emerald-200">
              your bag is on the counter
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * His two hands, at the middle of either edge, where they belong: the right hand
 * does whatever is in front of him, the left hand only ever handles goods.
 */
function Hands() {
  const prompt = useGame((s) => s.snap.prompt);
  const Hand = ({ side }: { side: "left" | "right" }) => (
    <button
      onClick={() => pressHand(side)}
      title={side === "left" ? "left hand — take or put down" : "right hand — open, push, use"}
      className={
        "pointer-events-auto absolute top-1/2 h-16 w-16 -translate-y-1/2 rounded-full border-2 text-2xl shadow-xl transition " +
        (side === "left" ? "left-2 " : "right-2 ") +
        ((side === "left" && (prompt === "take" || prompt === "drop")) ||
        (side === "right" &&
          (prompt === "dooropen" ||
            prompt === "doorclose" ||
            prompt === "vehdoor" ||
            prompt === "stop" ||
            prompt === "enter" ||
            prompt === "grab" ||
            prompt === "release" ||
            prompt === "unload" ||
            prompt === "takebag"))
          ? "border-emerald-400/80 bg-emerald-500/30 text-emerald-100"
          : "border-slate-600/80 bg-slate-950/70 text-slate-300 hover:bg-slate-800/80")
      }
    >
      {side === "left" ? "🫲" : "🫱"}
    </button>
  );
  return (
    <>
      <Hand side="left" />
      <Hand side="right" />
    </>
  );
}

export function Hud() {
  return (
    <div className="pointer-events-none absolute inset-0 select-none">
      <Shelf />
      <Hands />
      <Phone />
    </div>
  );
}
