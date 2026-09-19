"use strict";

import { confirmDialog } from "../dialog.js";
import { estateCommand, pendingEstateAction } from "./protocol.js";
import { estateNow, estateStore } from "./state.js";

const ICONS = { wheat: "🌾", carrot: "🥕", corn: "🌽", pumpkin: "🎃" };

function button(label, action, className = "estate-button") {
  const node = document.createElement("button");
  node.type = "button"; node.className = className; node.textContent = label;
  node.disabled = pendingEstateAction();
  node.addEventListener("click", action);
  return node;
}

function timeLeft(seconds) {
  const value = Math.max(0, Math.ceil(seconds));
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor(value % 3600 / 60);
  const secs = value % 60;
  return hours ? `${hours}时 ${minutes}分` : `${minutes}:${String(secs).padStart(2, "0")}`;
}

export function createEstateUI(root) {
  const hudCoins = root.querySelector("[data-estate-coins]");
  const hudLevel = root.querySelector("[data-estate-level]");
  const hudWarehouse = root.querySelector("[data-estate-warehouse]");
  const xpFill = root.querySelector(".estate-xp-fill");
  const sheet = root.querySelector(".estate-sheet");
  const sheetTitle = root.querySelector(".estate-sheet-title");
  const sheetBody = root.querySelector(".estate-sheet-body");
  const close = root.querySelector(".estate-sheet-close");
  let active = null;
  let timer = 0;

  function closeSheet() {
    active = null; sheet.hidden = true; sheetBody.replaceChildren();
  }
  close.addEventListener("click", closeSheet);
  sheet.addEventListener("click", (event) => { if (event.target === sheet) closeSheet(); });

  function show(title) {
    sheetTitle.textContent = title; sheetBody.replaceChildren(); sheet.hidden = false;
  }

  function cropCard(crop, actionLabel, action) {
    const card = document.createElement("div"); card.className = "estate-item-card";
    const icon = document.createElement("span"); icon.className = "estate-item-icon"; icon.textContent = ICONS[crop.id] || "🌱";
    const info = document.createElement("div"); info.className = "estate-item-info";
    const title = document.createElement("b"); title.textContent = crop.name;
    const meta = document.createElement("span"); meta.textContent = `成熟 ${timeLeft(crop.grow_seconds)} · 收购 ${crop.sell_price} 金币`;
    info.append(title, meta); card.append(icon, info, button(actionLabel, action));
    return card;
  }

  function renderShop() {
    const snapshot = estateStore.snapshot; if (!snapshot) return;
    show("露露的种子铺");
    const intro = document.createElement("p"); intro.className = "estate-sheet-note"; intro.textContent = "种子会占用仓库空间。价格与收购价固定，不会突然波动。";
    sheetBody.append(intro);
    Object.values(snapshot.catalog.crops).forEach((crop) => {
      const locked = snapshot.profile.level < crop.unlock_level;
      sheetBody.append(cropCard(crop, locked ? `${crop.unlock_level}级解锁` : `${crop.seed_price} 金币 · 买1颗`, () => {
        if (!locked) estateCommand("estate_buy", { kind: "seed", item_id: crop.id, quantity: 1 });
      }));
      sheetBody.lastElementChild.querySelector("button").disabled ||= locked;
    });
  }

  function renderWarehouse() {
    const snapshot = estateStore.snapshot; if (!snapshot) return;
    show("谷仓库存");
    if (!snapshot.inventory.length) {
      const empty = document.createElement("p"); empty.className = "estate-sheet-note"; empty.textContent = "谷仓空空的，先去商店买种子吧。"; sheetBody.append(empty);
    }
    for (const item of snapshot.inventory) {
      const row = document.createElement("div"); row.className = "estate-inventory-row";
      const name = document.createElement("div"); name.innerHTML = `<b>${item.name}</b><span> × ${item.quantity}</span>`;
      row.append(name);
      if (item.sellable) row.append(button(`出售1个 · +${item.sell_price}`, () => estateCommand("estate_sell", { item_id: item.id, quantity: 1 })));
      else { const keep = document.createElement("span"); keep.className = "estate-tag"; keep.textContent = "种植用品"; row.append(keep); }
      sheetBody.append(row);
    }
    const actions = document.createElement("div"); actions.className = "estate-sheet-actions";
    actions.append(button("一键出售全部农产品", async () => {
      if (await confirmDialog("种子会保留，只出售所有成熟农产品。", { title: "确认出售？" })) estateCommand("estate_sell_all");
    }, "estate-button estate-button-gold"));
    const level = snapshot.profile.warehouse_level;
    const rule = snapshot.catalog.warehouse_levels[String(level)] || snapshot.catalog.warehouse_levels[level];
    if (rule?.upgrade_price != null) {
      const locked = snapshot.profile.level < rule.unlock_level;
      const upgrade = button(locked ? `${rule.unlock_level}级可扩容` : `扩容仓库 · ${rule.upgrade_price}金币`, () => estateCommand("estate_buy", { kind: "warehouse", item_id: level, quantity: 1 }));
      upgrade.disabled ||= locked; actions.append(upgrade);
    }
    sheetBody.append(actions);
  }

  function renderPlot(plot) {
    const snapshot = estateStore.snapshot; if (!snapshot) return;
    active = { kind: "plot", index: plot.index };
    show(`第 ${plot.index + 1} 块土地`);
    if (plot.locked) {
      const rule = snapshot.catalog.plot_unlocks[String(plot.index)] || snapshot.catalog.plot_unlocks[plot.index];
      const note = document.createElement("p"); note.className = "estate-sheet-note";
      note.textContent = rule ? `需要庄园 ${rule.unlock_level} 级，购买价格 ${rule.price} 金币。` : "这块土地暂未开放。";
      sheetBody.append(note);
      if (rule) {
        const buy = button(`解锁土地 · ${rule.price}金币`, () => estateCommand("estate_buy", { kind: "plot", item_id: plot.index, quantity: 1 }));
        buy.disabled ||= snapshot.profile.level < rule.unlock_level; sheetBody.append(buy);
      }
      return;
    }
    if (plot.crop_id) {
      const crop = snapshot.catalog.crops[plot.crop_id];
      const ready = Number(plot.ready_at) <= estateNow();
      const hero = document.createElement("div"); hero.className = "estate-crop-hero";
      hero.innerHTML = `<span>${ICONS[crop.id]}</span><div><b>${crop.name}</b><small>${ready ? "已经成熟，可以收获啦！" : `距离成熟 ${timeLeft(plot.ready_at - estateNow())}`}</small></div>`;
      sheetBody.append(hero);
      const harvest = button(ready ? "收获" : "还在生长", () => estateCommand("estate_harvest", { plot_id: plot.index }), "estate-button estate-button-gold");
      harvest.disabled ||= !ready; sheetBody.append(harvest); return;
    }
    const seeds = new Map(snapshot.inventory.filter((item) => item.kind === "seed").map((item) => [item.crop_id, item.quantity]));
    const note = document.createElement("p"); note.className = "estate-sheet-note"; note.textContent = `Lv.${plot.land_level} 土地 · 选择一种仓库里的种子。`;
    sheetBody.append(note);
    Object.values(snapshot.catalog.crops).forEach((crop) => {
      const amount = seeds.get(crop.id) || 0;
      const card = cropCard(crop, amount ? `播种 · 库存${amount}` : "没有种子", () => estateCommand("estate_plant", { plot_id: plot.index, crop_id: crop.id }));
      card.querySelector("button").disabled ||= !amount; sheetBody.append(card);
    });
    const landRule = snapshot.catalog.land_levels[String(plot.land_level)] || snapshot.catalog.land_levels[plot.land_level];
    if (landRule?.upgrade_price != null) {
      const upgrade = button(`升级土地 · ${landRule.upgrade_price}金币`, () => estateCommand("estate_buy", { kind: "land", item_id: plot.index, quantity: 1 }));
      upgrade.disabled ||= snapshot.profile.level < landRule.unlock_level; sheetBody.append(upgrade);
    }
  }

  function render() {
    const snapshot = estateStore.snapshot; if (!snapshot) return;
    hudCoins.textContent = Number(snapshot.coins).toFixed(2);
    hudLevel.textContent = `Lv.${snapshot.profile.level}`;
    hudWarehouse.textContent = `${snapshot.profile.warehouse_used}/${snapshot.profile.warehouse_capacity}`;
    xpFill.style.width = `${Math.min(100, snapshot.profile.xp / snapshot.profile.xp_next * 100)}%`;
    if (!sheet.hidden) {
      if (active?.kind === "shop") renderShop();
      else if (active?.kind === "warehouse") renderWarehouse();
      else if (active?.kind === "plot") {
        const plot = snapshot.plots.find((item) => item.index === active.index);
        if (plot) renderPlot(plot);
      }
    }
  }

  function interact(target) {
    active = target.kind === "plot" ? { kind: "plot", index: target.plot.index } : { kind: target.kind };
    if (target.kind === "shop") renderShop();
    else if (target.kind === "warehouse") renderWarehouse();
    else if (target.kind === "plot") renderPlot(target.plot);
  }

  timer = window.setInterval(() => {
    if (!sheet.hidden && active?.kind === "plot") {
      const plot = estateStore.snapshot?.plots.find((item) => item.index === active.index);
      if (plot?.crop_id) renderPlot(plot);
    }
  }, 1000);
  return { render, interact, closeSheet, destroy() { window.clearInterval(timer); close.removeEventListener("click", closeSheet); } };
}
