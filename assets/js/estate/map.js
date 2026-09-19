"use strict";

import { estateNow, estateStore } from "./state.js";
import {
  PIXEL, drawBuilding, drawBush, drawCharacter, drawCrate, drawFence, drawGroundDetails,
  drawSignpost, drawTree, drawWater, pixelRect,
} from "./art.js";
import { drawSprite, stableSprite } from "./sprites.js";

const WORLD = { width: 960, height: 600 };
const BLOCKS = [
  { x: 32, y: 24, w: 250, h: 168 },
  { x: 675, y: 30, w: 245, h: 160 },
  { x: 24, y: 326, w: 230, h: 155 },
  { x: 680, y: 302, w: 280, h: 298 },
  { x: 0, y: 0, w: 960, h: 18 },
];
const PLOT_POSITIONS = [
  [330, 108], [430, 108], [530, 108], [330, 204],
  [430, 204], [530, 204], [330, 300], [430, 300],
];
const ZONES = [
  { kind: "shop", label: "小胖种子铺", x: 150, y: 205 },
  { kind: "warehouse", label: "小胖谷仓", x: 790, y: 208 },
  { kind: "fishing", label: "小胖湖钓场", x: 650, y: 430 },
  { kind: "mining", label: "小胖矿洞", x: 140, y: 500 },
];
function drawGround(ctx, tick) {
  drawGroundDetails(ctx, WORLD.width, WORLD.height, tick);
  pixelRect(ctx, 286, 72, 346, 410, "#cdb16a");
  pixelRect(ctx, 300, 84, 318, 386, "#e3cb82");
  for (let y = 92; y < 466; y += 32) {
    pixelRect(ctx, 306 + (y % 3) * 4, y, 16, 4, "#c6a761");
    pixelRect(ctx, 586 - (y % 4) * 5, y + 8, 20, 3, "#f1dc98");
  }
  pixelRect(ctx, 0, 500, 680, 42, "#dbbd75");
  pixelRect(ctx, 250, 450, 46, 92, "#dbbd75");
  for (let x = 0; x < 680; x += 32) pixelRect(ctx, x, 518, 18, 4, "#c39e59");
  drawWater(ctx, 690, 310, 270, 290, tick);
  for (let y = 316; y < 585; y += 30) {
    pixelRect(ctx, 678, y, 5, 17, "#5c9a49"); pixelRect(ctx, 684, y + 4, 3, 15, "#80b955");
  }
  // Tiny Town tiles add crisp, hand-drawn texture while the procedural layer remains
  // as a resilient fallback during loading or when an asset is unavailable.
  for (let x = 0; x < WORLD.width; x += 48) {
    drawSprite(ctx, "town", 12, x, 492, 3);
    drawSprite(ctx, "town", 24, x, 540, 3);
  }
  for (let y = 72; y < 480; y += 48) {
    drawSprite(ctx, "town", 13, 282, y, 3);
    drawSprite(ctx, "town", 25, 618, y, 3);
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
  const color = estateStore.snapshot?.catalog?.crops?.[plot.crop_id]?.color || "#e6cb63";
  const cropSprites = [4, 5, 6, 8, 17, 18, 20, 29, 30, 32, 41, 42, 44, 53, 54, 56, 65, 66, 68, 80, 81, 83];
  const cropSprite = stableSprite(plot.crop_id, cropSprites);
  for (let row = 0; row < 3; row += 1) {
    for (let col = 0; col < 4; col += 1) {
      const px = x + 13 + col * 17; const py = y + 17 + row * 18;
      if (progress < .25) pixelRect(ctx, px + 4, py + 7, 4, 5, "#86b752");
      else {
        pixelRect(ctx, px + 4, py, 3, 13, "#378446");
        pixelRect(ctx, px, py + 4, 6, 5, "#56ad55");
        if (progress > .48) pixelRect(ctx, px + 5, py - 3, mature ? 9 : 6, mature ? 10 : 7, color);
      }
      if (progress > .42) drawSprite(ctx, "farm", cropSprite, px - 3, py - 7, mature ? 1.05 : .85);
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
  const player = { x: 275, y: 440, facing: 1, walking: 0, lastMove: 0 };
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
    drawGround(ctx, performance.now());
    drawBuilding(ctx, 34, 24, 242, 166, "#efbd70", "#b8503d", "小胖种子铺");
    drawBuilding(ctx, 684, 28, 230, 164, "#dca75d", "#844237", "小胖谷仓");
    drawBuilding(ctx, 24, 326, 230, 155, "#776d66", "#4d4655", "小胖矿洞", "#b9a7bd");
    drawFence(ctx, 302, 72, 316);
    drawFence(ctx, 302, 478, 316);
    drawBush(ctx, 280, 28, true); drawBush(ctx, 622, 42); drawBush(ctx, 642, 164, true);
    drawCrate(ctx, 652, 158); drawCrate(ctx, 658, 134);
    drawSprite(ctx, "farm", 74, 55, 150, 2.5);
    drawSprite(ctx, "farm", 90, 218, 145, 2.5);
    drawSprite(ctx, "farm", 98, 707, 144, 2.5);
    drawSprite(ctx, "farm", 123, 752, 145, 2.5);
    drawSprite(ctx, "town", 115, 52, 430, 3);
    drawSprite(ctx, "town", 116, 93, 430, 3);
    drawSprite(ctx, "town", 117, 184, 430, 3, { flipX: true });
    drawSignpost(ctx, 604, 370, "小胖湖");
    for (let x = 6; x < 650; x += 72) {
      drawTree(ctx, x, 540 + (x % 3) * 3, x % 2, performance.now());
      drawSprite(ctx, "town", stableSprite(x, [3, 4, 5, 8, 9, 10]), x - 4, 526, 4);
    }
    [[292, 30, 29], [317, 43, 2], [638, 64, 16], [650, 214, 93], [278, 500, 94]].forEach(([x, y, sprite]) => {
      drawSprite(ctx, "town", sprite, x, y, 2.5);
    });
    (estateStore.snapshot?.plots || []).forEach((plot) => drawPlot(ctx, plot));
    pixelRect(ctx, 625, 420, 75, 12, "#835431");
    pixelRect(ctx, 645, 397, 8, 38, "#67452f");
    pixelRect(ctx, 682, 397, 8, 38, "#67452f");
    ctx.fillStyle = "#f5eed2"; ctx.font = "bold 13px sans-serif"; ctx.textAlign = "center";
    ctx.fillText("小胖湖钓场", 820, 292);
    if (target) {
      ctx.strokeStyle = "#fff4a8"; ctx.lineWidth = 3; ctx.setLineDash([6, 4]);
      ctx.strokeRect(target.x - 24, target.y - 24, 48, 48); ctx.setLineDash([]);
    }
    drawCharacter(ctx, player, performance.now());
    ctx.setTransform(1, 0, 0, 1, 0, 0);
  }

  function tick(now) {
    const dt = Math.min(.05, (now - last) / 1000); last = now;
    const length = Math.hypot(input.vector.x, input.vector.y) || 1;
    const dx = input.vector.x / length * 125 * dt;
    const dy = input.vector.y / length * 125 * dt;
    if (dx && !collides(player.x + dx, player.y)) player.x += dx;
    if (dy && !collides(player.x, player.y + dy)) player.y += dy;
    if (dx || dy) { player.walking += dt * 12; player.lastMove = now; if (dx) player.facing = Math.sign(dx); }
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
