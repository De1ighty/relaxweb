"use strict";

import { estateNow, estateStore } from "./state.js";

const WORLD = { width: 960, height: 600 };
const BLOCKS = [
  { x: 32, y: 24, w: 250, h: 168 },
  { x: 675, y: 30, w: 245, h: 160 },
  { x: 686, y: 400, w: 250, h: 176 },
  { x: 0, y: 0, w: 960, h: 18 },
];
const PLOT_POSITIONS = [
  [330, 108], [430, 108], [530, 108], [330, 204],
  [430, 204], [530, 204], [330, 300], [430, 300],
];
const ZONES = [
  { kind: "shop", label: "种子商店", x: 150, y: 205 },
  { kind: "warehouse", label: "谷仓", x: 790, y: 208 },
];

function pixelRect(ctx, x, y, w, h, color) {
  ctx.fillStyle = color;
  ctx.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h));
}

function drawTree(ctx, x, y, tone = 0) {
  pixelRect(ctx, x + 15, y + 30, 10, 25, "#69452b");
  pixelRect(ctx, x + 7, y + 8, 28, 34, tone ? "#3e8c50" : "#347d45");
  pixelRect(ctx, x, y + 18, 42, 20, tone ? "#55a85c" : "#489c55");
  pixelRect(ctx, x + 9, y + 2, 24, 12, "#66bb65");
  pixelRect(ctx, x + 7, y + 18, 7, 7, "#94d16e");
}

function drawBuilding(ctx, x, y, w, h, wall, roof, sign) {
  pixelRect(ctx, x + 12, y + 70, w - 24, h - 70, "#493224");
  pixelRect(ctx, x + 16, y + 66, w - 32, h - 74, wall);
  pixelRect(ctx, x, y + 38, w, 34, roof);
  pixelRect(ctx, x + 20, y + 16, w - 40, 32, roof);
  pixelRect(ctx, x + 34, y + 4, w - 68, 18, "#f1d19b");
  pixelRect(ctx, x + w / 2 - 20, y + h - 52, 40, 48, "#70472d");
  pixelRect(ctx, x + 30, y + 86, 30, 24, "#9ee0ec");
  pixelRect(ctx, x + w - 60, y + 86, 30, 24, "#9ee0ec");
  ctx.fillStyle = "#513524"; ctx.font = "bold 15px sans-serif"; ctx.textAlign = "center";
  ctx.fillText(sign, x + w / 2, y + 38);
}

function drawGround(ctx) {
  pixelRect(ctx, 0, 0, WORLD.width, WORLD.height, "#91c95d");
  for (let y = 0; y < WORLD.height; y += 24) {
    for (let x = (y / 24) % 2 * 12; x < WORLD.width; x += 48) {
      pixelRect(ctx, x, y, 3, 3, "#78b64c");
    }
  }
  pixelRect(ctx, 286, 72, 346, 410, "#cdb16a");
  pixelRect(ctx, 300, 84, 318, 386, "#e3cb82");
  pixelRect(ctx, 0, 470, 960, 42, "#dbbd75");
  for (let x = 0; x < 960; x += 32) pixelRect(ctx, x, 488, 18, 4, "#c39e59");
  pixelRect(ctx, 680, 390, 280, 210, "#5db7c0");
  for (let y = 405; y < 590; y += 28) {
    for (let x = 692; x < 950; x += 54) pixelRect(ctx, x, y, 24, 3, "#8ad8d1");
  }
}

function drawPlot(ctx, plot) {
  const [x, y] = PLOT_POSITIONS[plot.index];
  const locked = plot.locked;
  pixelRect(ctx, x, y, 82, 70, locked ? "#9a966e" : "#75472d");
  pixelRect(ctx, x + 4, y + 4, 74, 62, locked ? "#aaa780" : plot.land_level > 1 ? "#a55b35" : "#8c5232");
  for (let row = 0; row < 3; row += 1) pixelRect(ctx, x + 8, y + 13 + row * 18, 66, 3, locked ? "#8b896b" : "#653c29");
  if (locked) {
    pixelRect(ctx, x + 31, y + 22, 20, 24, "#5d625c");
    pixelRect(ctx, x + 35, y + 15, 12, 12, "#d6c588");
    return;
  }
  if (!plot.crop_id) return;
  const mature = Number(plot.ready_at) <= estateNow();
  const progress = mature ? 1 : Math.max(.12, (estateNow() - plot.planted_at) / (plot.ready_at - plot.planted_at));
  const color = plot.crop_id === "carrot" ? "#f28b36" : plot.crop_id === "corn" ? "#f4cf46" : plot.crop_id === "pumpkin" ? "#ee7a2d" : "#e6cb63";
  for (let row = 0; row < 3; row += 1) {
    for (let col = 0; col < 4; col += 1) {
      const px = x + 13 + col * 17; const py = y + 17 + row * 18;
      pixelRect(ctx, px + 4, py, 3, 13, "#378446");
      pixelRect(ctx, px, py + 4, 6, 5, "#56ad55");
      if (progress > .48) pixelRect(ctx, px + 5, py - 3, mature ? 9 : 6, mature ? 10 : 7, color);
    }
  }
  if (mature) {
    ctx.fillStyle = "#fff2a4"; ctx.font = "bold 18px sans-serif"; ctx.textAlign = "center";
    ctx.fillText("✦", x + 70, y + 16);
  }
}

function nearTarget(player, snapshot) {
  let best = null;
  const candidates = [...ZONES];
  for (const plot of snapshot?.plots || []) {
    const pos = PLOT_POSITIONS[plot.index];
    candidates.push({ kind: "plot", label: plot.locked ? "解锁土地" : plot.crop_id ? "查看作物" : "播种", plot, x: pos[0] + 41, y: pos[1] + 35 });
  }
  for (const zone of candidates) {
    const distance = Math.hypot(player.x - zone.x, player.y - zone.y);
    if (distance < 78 && (!best || distance < best.distance)) best = { ...zone, distance };
  }
  return best;
}

function collides(x, y) {
  const size = 12;
  if (x < 18 || y < 24 || x > WORLD.width - 18 || y > WORLD.height - 18) return true;
  return BLOCKS.some((block) => x + size > block.x && x - size < block.x + block.w && y + size > block.y && y - size < block.y + block.h);
}

export function createEstateMap(canvas, input, onInteract, onTarget) {
  const ctx = canvas.getContext("2d");
  const player = { x: 292, y: 420, facing: 1, walking: 0 };
  let frame = 0;
  let last = performance.now();
  let target = null;

  function resize() {
    const box = canvas.getBoundingClientRect();
    const ratio = Math.min(2, globalThis.devicePixelRatio || 1);
    canvas.width = Math.max(1, Math.floor(box.width * ratio));
    canvas.height = Math.max(1, Math.floor(box.height * ratio));
    ctx.imageSmoothingEnabled = false;
  }

  function draw() {
    const scale = Math.max(canvas.width / WORLD.width, canvas.height / WORLD.height);
    const ox = Math.min(0, Math.max(canvas.width - WORLD.width * scale,
      canvas.width / 2 - player.x * scale));
    const oy = Math.min(0, Math.max(canvas.height - WORLD.height * scale,
      canvas.height / 2 - player.y * scale));
    ctx.setTransform(scale, 0, 0, scale, ox, oy);
    drawGround(ctx);
    drawBuilding(ctx, 34, 24, 242, 166, "#f3c77c", "#bb5740", "种子铺");
    drawBuilding(ctx, 684, 28, 230, 164, "#e8b86a", "#8c4635", "谷 仓");
    drawBuilding(ctx, 704, 414, 210, 154, "#99816b", "#555568", "矿洞 · 敬请期待");
    for (let x = 8; x < 650; x += 74) drawTree(ctx, x, 520 + (x % 3) * 4, x % 2);
    (estateStore.snapshot?.plots || []).forEach((plot) => drawPlot(ctx, plot));
    pixelRect(ctx, 620, 450, 50, 8, "#91653c");
    pixelRect(ctx, 636, 432, 7, 30, "#6f4a2f");
    ctx.fillStyle = "#e6f7e4"; ctx.font = "bold 13px sans-serif"; ctx.textAlign = "center";
    ctx.fillText("湖畔钓场 · 即将开放", 798, 382);
    if (target) {
      ctx.strokeStyle = "#fff4a8"; ctx.lineWidth = 3; ctx.setLineDash([6, 4]);
      ctx.strokeRect(target.x - 24, target.y - 24, 48, 48); ctx.setLineDash([]);
    }
    const bob = Math.sin(player.walking) > 0 ? 1 : 0;
    pixelRect(ctx, player.x - 8, player.y + 10, 16, 5, "rgba(32,48,35,.3)");
    pixelRect(ctx, player.x - 7, player.y - 13 + bob, 14, 12, "#f2b37f");
    pixelRect(ctx, player.x - 9, player.y - 17 + bob, 18, 7, "#6b3d29");
    pixelRect(ctx, player.x - 9, player.y - 1 + bob, 18, 14, "#4d78b8");
    pixelRect(ctx, player.x - 8, player.y + 12 + bob, 6, 8, "#463b42");
    pixelRect(ctx, player.x + 2, player.y + 12 + bob, 6, 8, "#463b42");
    ctx.setTransform(1, 0, 0, 1, 0, 0);
  }

  function tick(now) {
    const dt = Math.min(.05, (now - last) / 1000); last = now;
    const length = Math.hypot(input.vector.x, input.vector.y) || 1;
    const dx = input.vector.x / length * 125 * dt;
    const dy = input.vector.y / length * 125 * dt;
    if (dx && !collides(player.x + dx, player.y)) player.x += dx;
    if (dy && !collides(player.x, player.y + dy)) player.y += dy;
    if (dx || dy) { player.walking += dt * 12; if (dx) player.facing = Math.sign(dx); }
    const nextTarget = nearTarget(player, estateStore.snapshot);
    if (nextTarget?.kind !== target?.kind || nextTarget?.plot?.index !== target?.plot?.index) {
      target = nextTarget; onTarget(target);
    } else target = nextTarget;
    if (input.consumeAction() && target) onInteract(target);
    draw();
    frame = requestAnimationFrame(tick);
  }

  resize();
  window.addEventListener("resize", resize);
  frame = requestAnimationFrame(tick);
  return {
    player,
    destroy() { cancelAnimationFrame(frame); window.removeEventListener("resize", resize); },
  };
}
