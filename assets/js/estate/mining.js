"use strict";

import { estateRequest } from "./protocol.js";

const ICONS = { empty: "·", extra: "+2", bomb: "💣", stone: "🪨", coal: "◆", copper: "⬟", iron: "⬢", amethyst: "♦", star_gem: "✦" };

export function openMiningGame(root, run) {
  const layer = document.createElement("div"); layer.className = `estate-minigame mining-game mine-depth-${run.mine_level}`;
  layer.innerHTML = `
    <div class="mine-cave-glow"></div>
    <div class="mine-timbers"><i></i><i></i><i></i></div>
    <div class="minigame-title"><b>小胖矿洞 · ${run.mine_name}</b><span>第 ${run.mine_level} 层 · 小心藏在岩层里的炸弹</span></div>
    <div class="mine-status"><b>剩余敲击 <span data-strikes>${run.strikes_left}</span></b><span data-loot>背包还是空的</span></div>
    <div class="mine-grid" role="grid"></div>
    <div class="mine-blast" hidden><b>BOOM!</b><span>挖到炸弹，本轮采矿结束</span></div>
    <button class="minigame-exit" type="button">带着收获离开</button>`;
  root.append(layer);
  const grid = layer.querySelector(".mine-grid"); let active = true; let loot = {};
  for (let index = 0; index < 25; index += 1) {
    const cell = document.createElement("button"); cell.type = "button"; cell.className = `mine-cell vein-${(index * 7 + run.mine_level) % 5}`;
    cell.setAttribute("aria-label", `矿格 ${index + 1}`); cell.dataset.cell = index; cell.innerHTML = "<i></i><i></i><i></i>";
    cell.addEventListener("click", async () => {
      if (!active || cell.disabled) return; cell.disabled = true; cell.classList.add("striking");
      try {
        const result = await estateRequest("estate_mine_cell", { run_id: run.run_id, cell: index });
        loot = result.loot || {}; cell.className = `mine-cell revealed outcome-${result.outcome}`; cell.textContent = ICONS[result.outcome] || "◆";
        layer.querySelector("[data-strikes]").textContent = result.strikes_left;
        layer.querySelector("[data-loot]").textContent = Object.entries(loot).map(([id, count]) => `${ICONS[id] || "◆"}×${count}`).join("  ") || "这块是空洞";
        if (result.exploded) {
          layer.classList.add("mine-explosion");
          layer.querySelector(".mine-blast").hidden = false;
        }
        if (result.finished) window.setTimeout(() => showResult(result.result), result.exploded ? 650 : 0);
      } catch { cell.disabled = false; cell.classList.remove("striking"); }
    });
    if (run.revealed?.includes(index)) {
      const outcome = run.revealed_cells?.[String(index)] || "empty";
      cell.disabled = true; cell.className = `mine-cell revealed outcome-${outcome}`; cell.textContent = ICONS[outcome] || "◆";
    }
    grid.append(cell);
  }
  function showResult(result) {
    active = false; grid.querySelectorAll("button").forEach((cell) => { cell.disabled = true; });
    layer.classList.add("is-result");
    const summary = Object.entries(result?.loot || loot).map(([id, count]) => `${ICONS[id] || "◆"} × ${count}`).join("　") || "没有挖到矿物";
    const exploded = result?.reason === "bomb";
    layer.querySelector(".minigame-title").innerHTML = `<b>${exploded ? "💥 炸弹引爆，采矿结束" : "本次采矿结束"}</b><span>${exploded ? "已找到的矿物成功带回 · " : ""}${summary}</span>`;
    layer.querySelector(".minigame-exit").textContent = "返回庄园";
  }
  layer.querySelector(".minigame-exit").addEventListener("click", async () => {
    if (!active) { layer.remove(); return; }
    active = false;
    try { showResult(await estateRequest("estate_finish_mining", { run_id: run.run_id })); }
    catch { active = true; }
  });
}
