"use strict";

import { estateRequest } from "./protocol.js";

export function openFishingGame(root, session) {
  const layer = document.createElement("div");
  layer.className = "estate-minigame fishing-game";
  layer.innerHTML = `
    <canvas aria-label="小胖湖钓鱼"></canvas>
    <div class="minigame-title"><b>小胖湖钓场</b><span>按住收线 · 松开卸力</span></div>
    <div class="fishing-meters">
      <label>捕获进度<i><span data-catch></span></i></label>
      <label>鱼线张力<i class="tension"><span data-tension></span></i></label>
    </div>
    <button class="fishing-reel" type="button">按住<br><b>收线</b></button>
    <button class="minigame-exit" type="button">放弃本次</button>`;
  root.append(layer);
  const canvas = layer.querySelector("canvas");
  const ctx = canvas.getContext("2d");
  const reel = layer.querySelector(".fishing-reel");
  const catchBar = layer.querySelector("[data-catch]");
  const tensionBar = layer.querySelector("[data-tension]");
  const trace = [];
  let held = false; let tension = .18; let progress = .08; let elapsed = 0;
  let accumulator = 0; let last = performance.now(); let frame = 0; let finished = false;
  const factor = { 1: 1, 2: .82, 3: .68 }[session.rod_level] || 1;

  function resize() {
    const box = canvas.getBoundingClientRect(); const ratio = Math.min(2, globalThis.devicePixelRatio || 1);
    canvas.width = box.width * ratio; canvas.height = box.height * ratio;
  }
  function draw(now) {
    const w = canvas.width; const h = canvas.height;
    const gradient = ctx.createLinearGradient(0, 0, 0, h);
    gradient.addColorStop(0, "#75d5d2"); gradient.addColorStop(1, "#176f8c");
    ctx.fillStyle = gradient; ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = "rgba(225,255,239,.45)";
    for (let y = 30; y < h; y += 58) for (let x = -40 + (now * .04 % 90); x < w; x += 120) ctx.fillRect(x, y, 45, 4);
    const fishX = w * (.5 + Math.sin(now * .0023) * .25);
    const fishY = h * (.56 + Math.sin(now * .0041) * .08);
    ctx.fillStyle = "rgba(15,70,85,.65)"; ctx.fillRect(fishX - 34, fishY, 58, 14);
    ctx.beginPath(); ctx.moveTo(fishX - 34, fishY + 7); ctx.lineTo(fishX - 55, fishY - 8); ctx.lineTo(fishX - 55, fishY + 22); ctx.fill();
    ctx.strokeStyle = tension > .78 ? "#ffdf89" : "#edf7d4"; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(w * .5, 0); ctx.quadraticCurveTo(w * .58, h * .3, fishX, fishY); ctx.stroke();
    ctx.fillStyle = "#ef6951"; ctx.fillRect(w * .5 - 5, h * .25, 10, 22);
    ctx.fillStyle = "#fff0c1"; ctx.fillRect(w * .5 - 5, h * .25, 10, 6);
  }
  function step() {
    const force = session.pattern[Math.min(session.pattern.length - 1, Math.floor(elapsed))];
    trace.push(Boolean(held));
    if (held) { tension += .026 * (.68 + force) * factor; progress += .013 * (1.12 - force * .3); }
    else { tension = Math.max(0, tension - .045); progress = Math.max(0, progress - .0035 * (.5 + force)); }
    elapsed += .1;
    catchBar.style.width = `${Math.min(100, progress * 100)}%`;
    tensionBar.style.width = `${Math.min(100, tension * 100)}%`;
    tensionBar.dataset.danger = String(tension > .78);
    if (tension >= 1 || progress >= 1 || elapsed >= session.duration_limit) void finish();
  }
  async function finish() {
    if (finished) return; finished = true; held = false;
    while (trace.length < 20) trace.push(false);
    reel.disabled = true; reel.textContent = "结算中";
    try {
      const result = await estateRequest("estate_finish_fishing", { session_id: session.session_id, trace });
      const caught = result.outcome === "caught";
      layer.classList.add("is-result");
      layer.querySelector(".minigame-title").innerHTML = caught
        ? `<b>捕获成功！</b><span>${result.fish_name} 已放入仓库 · 经验 +${result.xp_awarded}</span>`
        : `<b>${result.outcome === "snapped" ? "鱼线断了" : "鱼儿逃走了"}</b><span>鱼饵和耐久已经消耗，下次注意张力。</span>`;
      reel.textContent = caught ? "🐟" : "🌊";
      layer.querySelector(".minigame-exit").textContent = "返回庄园";
    } catch { layer.remove(); }
  }
  function tick(now) {
    const delta = Math.min(200, now - last); last = now; accumulator += delta;
    while (!finished && accumulator >= 100) { step(); accumulator -= 100; }
    draw(now); frame = requestAnimationFrame(tick);
  }
  const down = (event) => { event.preventDefault(); if (!finished) { held = true; reel.classList.add("held"); } };
  const up = () => { held = false; reel.classList.remove("held"); };
  const keyDown = (event) => { if (["Space", "KeyE"].includes(event.code)) down(event); };
  const keyUp = (event) => { if (["Space", "KeyE"].includes(event.code)) up(); };
  reel.addEventListener("pointerdown", down); window.addEventListener("pointerup", up);
  window.addEventListener("keydown", keyDown); window.addEventListener("keyup", keyUp);
  layer.querySelector(".minigame-exit").addEventListener("click", () => { if (finished) layer.remove(); else void finish(); });
  resize(); window.addEventListener("resize", resize); frame = requestAnimationFrame(tick);
  const observer = new MutationObserver(() => { if (!layer.isConnected) {
    cancelAnimationFrame(frame); observer.disconnect(); window.removeEventListener("resize", resize);
    window.removeEventListener("pointerup", up); window.removeEventListener("keydown", keyDown); window.removeEventListener("keyup", keyUp);
  }});
  observer.observe(root, { childList: true });
}
