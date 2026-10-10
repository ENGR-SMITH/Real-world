// One mutable input record for the whole app: the keyboard, the on-screen pad and
// the automated checks all write here, and the render loop reads it.  Keeping it
// out of React state means walking never re-renders the tree.
import type { Input } from "./game";

export const inputState: Input = {
  mx: 0,
  my: 0,
  run: false,
  use: false,
  alt: false,
  tab: false,
  collect: null,
};

/** physical keys currently down, and pad buttons currently pressed */
export const heldKeys = new Set<string>();
export const padKeys = new Set<string>();

export function pressUse() {
  inputState.use = true;
}

export function pressTab() {
  inputState.tab = true;
}

/** the action keys are pulses: true for exactly one simulation step */
export function clearPulses() {
  inputState.use = false;
  inputState.alt = false;
  inputState.tab = false;
  inputState.collect = null;
}

/**
 * The other hand: the buttons that live at the left and right edges of the screen.
 * The right hand does whatever the place in front of him offers -- a door, a car,
 * the trolley, the till -- and the left hand only ever handles goods, taking the
 * one he is looking at or putting down the one he is carrying.
 */
export function pressHand(which: "left" | "right") {
  if (which === "left") inputState.alt = true;
  else inputState.use = true;
}

/**
 * A tile was clicked on the shelf carousel: the boy should go and fetch that
 * product and put it in his trolley.  Like the action keys this is a pulse -- it
 * belongs to exactly one simulation step -- so the handler only has to set it.
 */
export function collectProduct(name: string) {
  inputState.collect = name;
}

export function setMove(mx: number, my: number) {
  inputState.mx = mx;
  inputState.my = my;
}

export function setRun(on: boolean) {
  inputState.run = on;
}

export function stopMoving() {
  inputState.mx = 0;
  inputState.my = 0;
}

export function keyToAction(code: string): "up" | "down" | "left" | "right" | "run" | "use" | "tab" | null {
  switch (code) {
    case "KeyW":
    case "ArrowUp":
      return "up";
    case "KeyS":
    case "ArrowDown":
      return "down";
    case "KeyA":
    case "ArrowLeft":
      return "left";
    case "KeyD":
    case "ArrowRight":
      return "right";
    case "ShiftLeft":
    case "ShiftRight":
      return "run";
    case "KeyE":
      return "use";
    case "Tab":
      return "tab";
    default:
      return null;
  }
}

/** fold keyboard and pad into the single axis/run state the simulation reads */
export function syncInput() {
  let mx = 0;
  let my = 0;
  let run = false;
  for (const set of [heldKeys, padKeys]) {
    for (const code of set) {
      const a = keyToAction(code);
      if (a === "up") my += 1;
      else if (a === "down") my -= 1;
      else if (a === "left") mx -= 1;
      else if (a === "right") mx += 1;
      else if (a === "run") run = true;
    }
  }
  setMove(Math.max(-1, Math.min(1, mx)), Math.max(-1, Math.min(1, my)));
  setRun(run);
}
