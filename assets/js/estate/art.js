"use strict";

export const PIXEL = {
  grass: "#78b954", grassLight: "#91cc61", grassDark: "#4f8f46",
  soil: "#925537", soilLight: "#b86e43", wood: "#75452f",
  cream: "#f7dda0", water: "#3d9fb8", waterLight: "#79d3cf",
  ink: "#3b3030", shadow: "rgba(38,48,39,.28)",
};

export function pixelRect(ctx, x, y, w, h, color) {
  ctx.fillStyle = color;
  ctx.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h));
}

export function drawTree(ctx, x, y, tone = 0, tick = 0) {
  const sway = Math.sin(tick * .0015 + x) > .7 ? 1 : 0;
  pixelRect(ctx, x + 14, y + 32, 12, 28, "#684129");
  pixelRect(ctx, x + 18, y + 32, 4, 27, "#8b5c35");
  pixelRect(ctx, x + 5 + sway, y + 13, 34, 32, tone ? "#317a4b" : "#2e7046");
  pixelRect(ctx, x - 2 + sway, y + 24, 47, 19, tone ? "#459b54" : "#408e50");
  pixelRect(ctx, x + 8 + sway, y + 4, 29, 18, "#5ab35f");
  pixelRect(ctx, x + 11 + sway, y + 10, 8, 6, "#88cf6d");
  pixelRect(ctx, x + 29 + sway, y + 24, 6, 5, "#75c568");
  pixelRect(ctx, x + 3, y + 58, 38, 5, PIXEL.shadow);
}

export function drawBuilding(ctx, x, y, w, h, wall, roof, sign, accent = "#f4d28f") {
  pixelRect(ctx, x + 8, y + h - 3, w - 4, 8, PIXEL.shadow);
  pixelRect(ctx, x + w - 55, y + 7, 18, 35, "#684437");
  pixelRect(ctx, x + w - 58, y + 4, 24, 7, "#3e3432");
  pixelRect(ctx, x + w - 50, y - 4, 8, 8, "#ded6b6aa");
  pixelRect(ctx, x + w - 42, y - 10, 10, 7, "#eee7cc77");
  pixelRect(ctx, x + 12, y + 67, w - 24, h - 67, "#493224");
  pixelRect(ctx, x + 17, y + 64, w - 34, h - 70, wall);
  for (let line = y + 78; line < y + h - 8; line += 15) pixelRect(ctx, x + 18, line, w - 36, 2, "#9a613655");
  pixelRect(ctx, x, y + 36, w, 37, "#713c32");
  pixelRect(ctx, x + 4, y + 32, w - 8, 34, roof);
  pixelRect(ctx, x + 20, y + 14, w - 40, 24, roof);
  pixelRect(ctx, x + 34, y + 4, w - 68, 15, accent);
  pixelRect(ctx, x + 38, y + 7, w - 76, 3, "#fff0bd");
  pixelRect(ctx, x + w / 2 - 21, y + h - 54, 42, 50, "#5e3828");
  pixelRect(ctx, x + w / 2 - 15, y + h - 48, 30, 44, "#805137");
  pixelRect(ctx, x + w / 2 + 8, y + h - 29, 4, 4, "#e5c66e");
  for (const wx of [x + 30, x + w - 60]) {
    pixelRect(ctx, wx - 3, y + 83, 36, 31, "#724a32");
    pixelRect(ctx, wx, y + 86, 30, 24, "#8bd4df");
    pixelRect(ctx, wx + 3, y + 89, 24, 5, "#d9ffff");
    pixelRect(ctx, wx + 14, y + 86, 3, 24, "#547b83");
  }
  pixelRect(ctx, x + w / 2 - 30, y + h - 4, 60, 7, "#b88954");
  pixelRect(ctx, x + w / 2 - 36, y + h + 3, 72, 6, "#d2ad69");
  ctx.fillStyle = "#4b3228"; ctx.font = "bold 15px sans-serif"; ctx.textAlign = "center";
  ctx.fillText(sign, x + w / 2, y + 34);
}

export function drawFence(ctx, x, y, length, vertical = false) {
  const count = Math.floor(length / 24);
  for (let i = 0; i <= count; i += 1) {
    const px = x + (vertical ? 0 : i * 24); const py = y + (vertical ? i * 24 : 0);
    pixelRect(ctx, px, py - 6, 7, 27, "#75462f");
    pixelRect(ctx, px + 2, py - 4, 3, 22, "#d09a58");
  }
  if (vertical) {
    pixelRect(ctx, x + 2, y, 5, length, "#8e5a36");
    pixelRect(ctx, x + 7, y, 3, length, "#c08449");
  } else {
    pixelRect(ctx, x, y, length, 6, "#8e5a36");
    pixelRect(ctx, x, y + 6, length, 4, "#c08449");
  }
}

export function drawBush(ctx, x, y, berries = false) {
  pixelRect(ctx, x + 5, y + 15, 30, 18, "#286943");
  pixelRect(ctx, x, y + 20, 40, 12, "#327e48");
  pixelRect(ctx, x + 9, y + 8, 23, 20, "#4b9a4e");
  pixelRect(ctx, x + 14, y + 10, 7, 5, "#76bd59");
  if (berries) {
    pixelRect(ctx, x + 8, y + 22, 4, 4, "#d45e55");
    pixelRect(ctx, x + 28, y + 18, 4, 4, "#f08b5b");
  }
  pixelRect(ctx, x + 3, y + 32, 34, 4, PIXEL.shadow);
}

export function drawCrate(ctx, x, y) {
  pixelRect(ctx, x, y, 27, 24, "#70442d");
  pixelRect(ctx, x + 3, y + 3, 21, 18, "#b87942");
  pixelRect(ctx, x + 11, y + 3, 4, 18, "#795035");
  pixelRect(ctx, x + 3, y + 10, 21, 4, "#795035");
}

export function drawSignpost(ctx, x, y, label) {
  pixelRect(ctx, x + 28, y + 21, 7, 32, "#68412e");
  pixelRect(ctx, x, y, 66, 29, "#6d432c");
  pixelRect(ctx, x + 4, y + 4, 58, 20, "#d39b58");
  ctx.fillStyle = "#4c3428"; ctx.font = "bold 11px sans-serif"; ctx.textAlign = "center";
  ctx.fillText(label, x + 33, y + 18);
}

export function drawWater(ctx, x, y, w, h, tick) {
  pixelRect(ctx, x - 8, y - 8, w + 8, h + 8, "#d8b66c");
  pixelRect(ctx, x, y, w, h, PIXEL.water);
  pixelRect(ctx, x + 8, y + 8, w - 8, h - 8, "#55b8c2");
  const shift = Math.floor(tick / 220) % 28;
  for (let row = y + 20; row < y + h; row += 30) {
    for (let col = x + 12 - shift; col < x + w; col += 56) {
      pixelRect(ctx, col, row, 22, 3, PIXEL.waterLight);
      pixelRect(ctx, col + 7, row + 4, 12, 2, "#9ee1d7");
    }
  }
  for (let i = 0; i < 4; i += 1) {
    const fx = x + 35 + i * 57; const fy = y + 35 + (i % 2) * 54;
    pixelRect(ctx, fx, fy, 13, 7, "#4c9858"); pixelRect(ctx, fx + 5, fy - 3, 4, 4, "#f3d77d");
  }
  const fishX = x + 40 + (tick * .018 % Math.max(60, w - 80));
  pixelRect(ctx, fishX, y + h * .66, 18, 5, "#287d8c88");
  pixelRect(ctx, fishX - 5, y + h * .66 - 3, 6, 10, "#287d8c88");
}

export function drawCharacter(ctx, player, tick) {
  const moving = player.walking > 0 && tick - (player.lastMove || 0) < 120;
  const step = moving && Math.floor(player.walking) % 2 ? 2 : 0;
  pixelRect(ctx, player.x - 10, player.y + 12, 20, 6, PIXEL.shadow);
  pixelRect(ctx, player.x - 8, player.y - 15, 16, 13, "#efad79");
  pixelRect(ctx, player.x - 10, player.y - 20, 20, 8, "#6a392c");
  pixelRect(ctx, player.x - 9, player.y - 13, 4, 6, "#713b2d");
  pixelRect(ctx, player.x + 5, player.y - 11, 2, 2, "#342c31");
  pixelRect(ctx, player.x - 10, player.y - 2, 20, 15, "#3f74ad");
  pixelRect(ctx, player.x - 6, player.y + 1, 12, 4, "#78a9d1");
  pixelRect(ctx, player.x - 9, player.y + 12, 7, 9 - step, "#4d3b43");
  pixelRect(ctx, player.x + 2, player.y + 12, 7, 7 + step, "#4d3b43");
  pixelRect(ctx, player.x - 10, player.y + 18 - step, 8, 3, "#2f3137");
  pixelRect(ctx, player.x + 2, player.y + 18 + step, 8, 3, "#2f3137");
}

export function drawGroundDetails(ctx, width, height, tick) {
  pixelRect(ctx, 0, 0, width, height, PIXEL.grass);
  for (let y = 8; y < height; y += 24) {
    for (let x = (y / 24) % 2 * 13; x < width; x += 48) {
      pixelRect(ctx, x, y, 3, 3, (x + y) % 5 ? PIXEL.grassDark : "#b6dc70");
      if ((x * 3 + y) % 11 === 0) {
        pixelRect(ctx, x + 5, y - 2, 2, 6, "#438b43");
        pixelRect(ctx, x + 3, y - 4, 3, 3, Math.floor(tick / 600) % 2 ? "#f7d773" : "#f4a5a5");
      }
    }
  }
  for (let x = 18; x < width; x += 93) {
    pixelRect(ctx, x, 282 + (x % 4) * 7, 5, 3, "#d9cf82");
    pixelRect(ctx, x + 5, 280 + (x % 4) * 7, 3, 5, "#eee2a2");
  }
}
