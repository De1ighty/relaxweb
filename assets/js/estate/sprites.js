"use strict";

const TILE_SIZE = 16;
const TILE_STEP = 17;
const TILE_COLUMNS = 12;

const sheets = {
  farm: loadSheet("assets/estate/kenney/tiny-farm.png"),
  town: loadSheet("assets/estate/kenney/tiny-town.png"),
};

function loadSheet(src) {
  const image = new Image();
  const sheet = { image, ready: false };
  image.addEventListener("load", () => { sheet.ready = true; });
  image.src = src;
  return sheet;
}

export function spriteReady(name) {
  return Boolean(sheets[name]?.ready);
}

export function drawSprite(ctx, name, index, x, y, scale = 3, options = {}) {
  const sheet = sheets[name];
  if (!sheet?.ready) return false;
  const sx = (index % TILE_COLUMNS) * TILE_STEP;
  const sy = Math.floor(index / TILE_COLUMNS) * TILE_STEP;
  const size = TILE_SIZE * scale;
  ctx.save();
  ctx.globalAlpha = options.alpha ?? 1;
  if (options.flipX) {
    ctx.translate(Math.round(x + size), Math.round(y));
    ctx.scale(-1, 1);
    ctx.drawImage(sheet.image, sx, sy, TILE_SIZE, TILE_SIZE, 0, 0, size, size);
  } else {
    ctx.drawImage(sheet.image, sx, sy, TILE_SIZE, TILE_SIZE,
      Math.round(x), Math.round(y), size, size);
  }
  ctx.restore();
  return true;
}

export function stableSprite(seed, indexes) {
  let hash = 0;
  for (const char of String(seed)) hash = ((hash * 31) + char.charCodeAt(0)) >>> 0;
  return indexes[hash % indexes.length];
}
