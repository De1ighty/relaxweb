"use strict";

import { confirmDialog } from "../dialog.js";
import { estateCommand, estateRequest, pendingEstateAction } from "./protocol.js";
import { estateNow, estateStore } from "./state.js";

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

export function createEstateUI(root, activities = {}) {
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

  function cropCard(crop, actionLabel, action, multiplier = 1) {
    const card = document.createElement("div"); card.className = "estate-item-card";
    const icon = document.createElement("span"); icon.className = "estate-item-icon"; icon.textContent = crop.icon || "🌱";
    const info = document.createElement("div"); info.className = "estate-item-info";
    const title = document.createElement("b"); title.textContent = crop.name;
    const meta = document.createElement("span"); meta.textContent = `成熟 ${timeLeft(Math.ceil(crop.grow_seconds * multiplier))} · 售价 ${crop.sell_price} · 净赚 ${Number((crop.sell_price * crop.yield - crop.seed_price).toFixed(2))}金币 · ${crop.xp}经验`;
    info.append(title, meta); card.append(icon, info, button(actionLabel, action));
    return card;
  }

  function renderShop() {
    const snapshot = estateStore.snapshot; if (!snapshot) return;
    show("小胖种子铺");
    const crops = Object.values(snapshot.catalog.crops).sort((a, b) => a.unlock_level - b.unlock_level || a.name.localeCompare(b.name, "zh-CN"));
    const unlockedCount = crops.filter((crop) => snapshot.profile.level >= crop.unlock_level).length;
    const intro = document.createElement("p"); intro.className = "estate-sheet-note";
    intro.textContent = `共 ${crops.length} 种作物 · 已解锁 ${unlockedCount} 种。播种后离线也会生长，不用浇水；净收益已扣除种子成本，升级土地可缩短等待。`;
    sheetBody.append(intro);
    crops.forEach((crop) => {
      const locked = snapshot.profile.level < crop.unlock_level;
      sheetBody.append(cropCard(crop, locked ? `${crop.unlock_level}级解锁` : `${crop.seed_price} 金币 · 买1颗`, () => {
        if (!locked) estateCommand("estate_buy", { kind: "seed", item_id: crop.id, quantity: 1 });
      }));
      sheetBody.lastElementChild.querySelector("button").disabled ||= locked;
    });
  }

  function renderWarehouse() {
    const snapshot = estateStore.snapshot; if (!snapshot) return;
    show("小胖谷仓");
    if (!snapshot.inventory.length) {
      const empty = document.createElement("p"); empty.className = "estate-sheet-note"; empty.textContent = "谷仓空空的，先去商店买种子吧。"; sheetBody.append(empty);
    }
    for (const item of snapshot.inventory) {
      const row = document.createElement("div"); row.className = "estate-inventory-row";
      const name = document.createElement("div"); name.innerHTML = `<b>${item.name}</b><span> × ${item.quantity}</span>`;
      row.append(name);
      if (item.sellable) row.append(button(`出售1个 · +${item.sell_price}`, () => estateCommand("estate_sell", { item_id: item.id, quantity: 1 })));
      else {
        const keep = document.createElement("span"); keep.className = "estate-tag";
        keep.textContent = item.kind === "bait" ? "钓鱼用品" : item.kind === "collectible" ? "稀有收藏" : "种植用品";
        row.append(keep);
      }
      sheetBody.append(row);
    }
    const actions = document.createElement("div"); actions.className = "estate-sheet-actions";
    actions.append(button("一键出售全部产品", async () => {
      if (await confirmDialog("种子和鱼饵会保留，只出售作物、鱼和矿物。", { title: "确认出售？" })) estateCommand("estate_sell_all");
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

  function toolPanel(toolType, icon) {
    const snapshot = estateStore.snapshot;
    const owned = snapshot.tools[toolType];
    const rules = snapshot.catalog.tools[toolType];
    const currentRule = owned ? (rules[String(owned.level)] || rules[owned.level]) : (rules["1"] || rules[1]);
    const card = document.createElement("div"); card.className = "estate-tool-card";
    const visual = document.createElement("span"); visual.className = "estate-tool-icon"; visual.textContent = icon;
    const info = document.createElement("div"); info.className = "estate-item-info";
    const title = document.createElement("b"); title.textContent = owned ? owned.name : currentRule.name;
    const meta = document.createElement("span"); meta.textContent = owned
      ? `Lv.${owned.level} · 耐久 ${owned.durability}/${owned.max_durability}` : "尚未拥有";
    info.append(title, meta); card.append(visual, info);
    if (!owned) card.append(button(`${currentRule.price}金币购买`, () => estateCommand("estate_buy_tool", { tool_type: toolType })));
    else {
      if (owned.durability < owned.max_durability) {
        const cost = Math.max(1, Math.round(currentRule.repair_price * (owned.max_durability - owned.durability) / owned.max_durability * 100) / 100);
        card.append(button(`修理 · ${cost}金币`, () => estateCommand("estate_repair_tool", { tool_type: toolType })));
      }
      if (currentRule.upgrade_price != null) {
        const next = rules[String(owned.level + 1)] || rules[owned.level + 1];
        const upgrade = button(`${currentRule.upgrade_price}金币升级`, () => estateCommand("estate_upgrade_tool", { tool_type: toolType }));
        upgrade.disabled ||= snapshot.profile.level < next.unlock_level; card.append(upgrade);
      }
    }
    sheetBody.append(card);
    return owned;
  }

  function renderFishing() {
    const snapshot = estateStore.snapshot; if (!snapshot) return;
    show("小胖湖钓场");
    const note = document.createElement("p"); note.className = "estate-sheet-note";
    note.textContent = `湖中有 ${Object.keys(snapshot.catalog.fish).length} 种鱼类，还有 ${Object.keys(snapshot.catalog.fishing_treasures || {}).length} 种神秘收藏物。每轮消耗1份鱼饵和1点耐久，失败也会消耗。按住收线，张力过高时松开卸力；高级鱼竿与荧光虫饵能提高稀有鱼机会。`;
    sheetBody.append(note);
    const rod = toolPanel("rod", "🎣");
    if (snapshot.fishing_session) {
      sheetBody.append(button("继续未完成的钓鱼", () => {
        const session = snapshot.fishing_session; closeSheet(); activities.fishing?.(session);
      }, "estate-button estate-button-gold"));
      return;
    }
    const baitCounts = new Map(snapshot.inventory.filter((item) => item.kind === "bait").map((item) => [item.bait_id, item.quantity]));
    Object.values(snapshot.catalog.baits).forEach((bait) => {
      const locked = snapshot.profile.level < bait.unlock_level; const amount = baitCounts.get(bait.id) || 0;
      const row = document.createElement("div"); row.className = "estate-item-card";
      const info = document.createElement("div"); info.className = "estate-item-info";
      const rule = rod && snapshot.catalog.tools.rod[rod.level];
      const cost = rule ? (bait.price + rule.repair_price / rule.max_durability).toFixed(2) : null;
      info.innerHTML = `<b>🪱 ${bait.name}</b><span>库存 ${amount} · 单价 ${bait.price}金币${cost ? ` · 每轮约${cost}金币（含维修分摊）` : ""}</span>`; row.append(info);
      const buy = button(locked ? `${bait.unlock_level}级解锁` : "购买1个", () => estateCommand("estate_buy", { kind: "bait", item_id: bait.id, quantity: 1 }));
      buy.disabled ||= locked; row.append(buy);
      const start = button("开始钓鱼", async () => {
        try { const session = await estateRequest("estate_start_fishing", { bait_id: bait.id }); closeSheet(); activities.fishing?.(session); } catch { /* 弹层由协议统一显示 */ }
      }, "estate-button estate-button-gold");
      start.disabled ||= locked || !rod || rod.durability < 1 || amount < 1; row.append(start); sheetBody.append(row);
    });
  }

  function renderMining() {
    const snapshot = estateStore.snapshot; if (!snapshot) return;
    show("小胖矿洞");
    const note = document.createElement("p"); note.className = "estate-sheet-note";
    note.textContent = "每次下矿消耗一点矿镐耐久，空手或触雷也会消耗。越深奖励越好、炸弹越多；触雷立即结束，已获得的矿物可以保留并结算经验。";
    sheetBody.append(note);
    const pickaxe = toolPanel("pickaxe", "⛏️");
    if (snapshot.mining_run) {
      sheetBody.append(button("继续本次采矿", () => {
        const run = snapshot.mining_run; closeSheet(); activities.mining?.(run);
      }, "estate-button estate-button-gold"));
      return;
    }
    Object.entries(snapshot.catalog.mining_levels).forEach(([level, mine]) => {
      const unlocked = pickaxe && pickaxe.level >= Number(level) && snapshot.profile.level >= mine.unlock_level;
      const row = document.createElement("div"); row.className = "estate-item-card";
      const info = document.createElement("div"); info.className = "estate-item-info";
      const rule = pickaxe && snapshot.catalog.tools.pickaxe[pickaxe.level];
      const cost = rule ? (rule.repair_price / rule.max_durability).toFixed(2) : null;
      info.innerHTML = `<b>第${level}层 · ${mine.name}</b><span>${mine.risk} · ${mine.bombs}枚炸弹 · 庄园 ${mine.unlock_level} 级 · 矿镐 Lv.${level}${cost ? ` · 每轮维修约${cost}金币 · 预留${rule.strikes + 2}格仓位` : ""}</span>`; row.append(info);
      const enter = button(unlocked ? "进入矿层" : "尚未解锁", async () => {
        try { const run = await estateRequest("estate_start_mining", { mine_level: Number(level) }); closeSheet(); activities.mining?.(run); } catch { /* 弹层由协议统一显示 */ }
      }, "estate-button estate-button-gold");
      enter.disabled ||= !unlocked || pickaxe.durability < 1; row.append(enter); sheetBody.append(row);
    });
  }

  function renderPlot(plot) {
    const snapshot = estateStore.snapshot; if (!snapshot) return;
    active = { kind: "plot", index: plot.index };
    show(`小胖农田 · 第 ${plot.index + 1} 块`);
    if (plot.locked) {
      const rule = snapshot.catalog.plot_unlocks[String(plot.index)] || snapshot.catalog.plot_unlocks[plot.index];
      const note = document.createElement("p"); note.className = "estate-sheet-note";
      note.textContent = rule ? `需要庄园 ${rule.unlock_level} 级，购买价格 ${rule.price} 金币。` : "这块土地暂未开放。";
      sheetBody.append(note);
      if (rule) {
        const buy = button(`解锁土地 · ${rule.price}金币`, () => estateCommand("estate_buy", { kind: "plot", item_id: plot.index, quantity: 1 }));
        buy.disabled ||= snapshot.profile.level < rule.unlock_level || plot.index !== snapshot.profile.plot_count; sheetBody.append(buy);
      }
      return;
    }
    if (plot.crop_id) {
      const crop = snapshot.catalog.crops[plot.crop_id];
      const ready = Number(plot.ready_at) <= estateNow();
      const hero = document.createElement("div"); hero.className = "estate-crop-hero";
      hero.innerHTML = `<span>${crop.icon || "🌱"}</span><div><b>${crop.name}</b><small>${ready ? "已经成熟，可以收获啦！" : `距离成熟 ${timeLeft(plot.ready_at - estateNow())}`}</small></div>`;
      sheetBody.append(hero);
      const harvest = button(ready ? "收获" : "还在生长", () => estateCommand("estate_harvest", { plot_id: plot.index }), "estate-button estate-button-gold");
      harvest.disabled ||= !ready; sheetBody.append(harvest); return;
    }
    const seeds = new Map(snapshot.inventory.filter((item) => item.kind === "seed").map((item) => [item.crop_id, item.quantity]));
    const note = document.createElement("p"); note.className = "estate-sheet-note"; note.textContent = `Lv.${plot.land_level} 土地 · 选择一种仓库里的种子。`;
    sheetBody.append(note);
    Object.values(snapshot.catalog.crops).forEach((crop) => {
      const amount = seeds.get(crop.id) || 0;
      const card = cropCard(crop, amount ? `播种 · 库存${amount}` : "没有种子", () => estateCommand("estate_plant", { plot_id: plot.index, crop_id: crop.id }), snapshot.catalog.land_levels[plot.land_level].multiplier);
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
      else if (active?.kind === "fishing") renderFishing();
      else if (active?.kind === "mining") renderMining();
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
    else if (target.kind === "fishing") renderFishing();
    else if (target.kind === "mining") renderMining();
    else if (target.kind === "plot") renderPlot(target.plot);
  }

  timer = window.setInterval(() => {
    if (!sheet.hidden && active?.kind === "plot") {
      const plot = estateStore.snapshot?.plots.find((item) => item.index === active.index);
      if (plot?.crop_id) renderPlot(plot);
    }
  }, 1000);
  function openFishing() { active = { kind: "fishing" }; renderFishing(); }
  return { render, interact, openFishing, closeSheet, destroy() { window.clearInterval(timer); close.removeEventListener("click", closeSheet); } };
}
