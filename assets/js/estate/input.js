"use strict";

export function createEstateInput(root) {
  const keys = new Set();
  const vector = { x: 0, y: 0 };
  let actionPressed = false;
  let stickPointer = null;
  const stick = root.querySelector(".estate-stick");
  const nub = root.querySelector(".estate-stick-nub");
  const action = root.querySelector(".estate-action");

  const recalc = () => {
    vector.x = Number(keys.has("ArrowRight") || keys.has("KeyD")) - Number(keys.has("ArrowLeft") || keys.has("KeyA"));
    vector.y = Number(keys.has("ArrowDown") || keys.has("KeyS")) - Number(keys.has("ArrowUp") || keys.has("KeyW"));
  };
  const keydown = (event) => {
    if (!root.querySelector(".estate-sheet")?.hidden) return;
    if (["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName)) return;
    if (["KeyE", "Space"].includes(event.code) && !event.repeat) actionPressed = true;
    keys.add(event.code);
    recalc();
    if (event.code.startsWith("Arrow") || event.code === "Space") event.preventDefault();
  };
  const keyup = (event) => { keys.delete(event.code); recalc(); };
  const resetStick = () => {
    stickPointer = null;
    vector.x = 0; vector.y = 0;
    nub.style.transform = "translate(-50%, -50%)";
  };
  const moveStick = (event) => {
    if (event.pointerId !== stickPointer) return;
    const box = stick.getBoundingClientRect();
    const dx = event.clientX - (box.left + box.width / 2);
    const dy = event.clientY - (box.top + box.height / 2);
    const distance = Math.hypot(dx, dy) || 1;
    const radius = box.width * .3;
    const scale = Math.min(1, radius / distance);
    const px = dx * scale;
    const py = dy * scale;
    vector.x = px / radius;
    vector.y = py / radius;
    nub.style.transform = `translate(calc(-50% + ${px}px), calc(-50% + ${py}px))`;
  };
  const stickDown = (event) => {
    stickPointer = event.pointerId;
    stick.setPointerCapture(event.pointerId);
    moveStick(event);
  };
  const stickUp = (event) => { if (event.pointerId === stickPointer) resetStick(); };
  const actionDown = (event) => { event.preventDefault(); actionPressed = true; };
  const clear = () => { keys.clear(); resetStick(); actionPressed = false; };

  window.addEventListener("keydown", keydown, { passive: false });
  window.addEventListener("keyup", keyup);
  window.addEventListener("blur", clear);
  stick.addEventListener("pointerdown", stickDown);
  stick.addEventListener("pointermove", moveStick);
  stick.addEventListener("pointerup", stickUp);
  stick.addEventListener("pointercancel", stickUp);
  action.addEventListener("pointerdown", actionDown);

  return {
    vector,
    consumeAction() { const value = actionPressed; actionPressed = false; return value; },
    clear,
    destroy() {
      window.removeEventListener("keydown", keydown);
      window.removeEventListener("keyup", keyup);
      window.removeEventListener("blur", clear);
      stick.removeEventListener("pointerdown", stickDown);
      stick.removeEventListener("pointermove", moveStick);
      stick.removeEventListener("pointerup", stickUp);
      stick.removeEventListener("pointercancel", stickUp);
      action.removeEventListener("pointerdown", actionDown);
    },
  };
}
