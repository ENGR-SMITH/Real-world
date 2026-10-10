# Mini Market — street & shop (web)

The walkable shop/street from `Shop_with_people.blend`, rebuilt as a browser game.
The simulation is a line-for-line port of the desktop build's `game.py`, so both
versions move, collide and interact identically.

## Run it

Two processes (the realtime server is separate so the game still works without it):

```bash
cd E:/Reality/webapp
npm run server     # Socket.IO on :3011 — multiplayer positions + chat
npm run dev        # Next.js on :3010 — open http://localhost:3010
```

Playing alone needs only `npm run dev`; the HUD shows "playing solo" when the
realtime server is not running.

> Note: this machine's `C:` is full, so npm's cache and temp dir must stay on `E:`
> (`npm_config_cache=E:/.npm-cache`, `TEMP=E:\.tmp`).

## Controls

| key | action |
| --- | --- |
| `W A S D` / arrows | walk (relative to the camera) |
| `Shift` | hurry |
| `E` | open/close the shop door · **take the item you are facing** · put one down · signal the bus to stop · open its door · get in · get out |
| `Tab` | swap between Boy 1 and Boy 2 |

On-screen pad buttons (bottom left) do the same, and are how the automated checks
drive the game. The camera switches between third person and isometric in the HUD.

## Stack

- **Next.js 16.4 + React 19** (App Router, Turbopack) — `src/app`
- **Three.js 0.186 + @react-three/fiber 9** — `src/components/GameCanvas.tsx`
- **Zustand 5** — `src/store/gameStore.ts` (HUD state, roster, chat)
- **Tailwind v4 + shadcn-style components** — `src/components/ui`, `src/app/globals.css`
- **TypeScript + Node/Socket.IO 4.8** — `server/index.mjs`

## Layout

```
src/lib/world.json    every measured number from the Blender scene (regions,
                      blockers, doorway, vehicles, props) — exported from game.py
src/lib/world.ts      region/ground/collision predicates (canStand, blocked, ...)
src/lib/game.ts       the simulation: movement, doors, vehicles, interactions
src/lib/input.ts      one input record shared by keyboard, pad and checks
src/lib/net.ts        Socket.IO client (degrades to solo play)
server/index.mjs      authoritative relay: positions at 10 Hz, chat, roster
public/assets/        shop.glb — 56 MB glTF export of the whole scene (not wired in yet)
```

## Checks

The port is verified by driving the simulation deterministically, the same way the
desktop build is (`window.__shop` exposes `walkTo`, `face`, `use`, `tab`,
`stepHeadless`, `perf`). Confirmed in a real browser: door opens (0 → 1), walk
through into the shop, take `Prop_Item_4` off the counter at 1.53 m **by facing it**,
carry it out and drop it, wait for the bus, signal it to stop (6 → 0 m/s), open its
door (0 → 0.97), get in, drive 12 m, get out on foot, `Tab` swaps to Boy 2, and a
second tab appears as a remote shopper with working chat.

## Next

`public/assets/shop.glb` (56 MB, both characters, all four clips, 1037-bone rigs) is
exported and ready: swap the blockout meshes for it. It will need
`GLTFLoader` + decimated rigs to stay fast.
