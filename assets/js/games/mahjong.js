/* 国标麻将牌桌：方形桌面、四方座位、牌河/副露/花牌展示、吃碰杠胡操作与结算回顾。
   起和判定与番种计算以服务器为准，客户端只做展示与操作入口。 */

import {
  displayNameOf, elements, formatCoins, ratingBadge, renderGameView, requestProfile,
  send, startHallTicker, state,
} from "../core.js";
import { registerGame } from "../registry.js";
import { openChatOverlay, reapplySeatBubbles } from "../room.js";

const WIND_NAMES = ["东", "南", "西", "北"];
const SUIT_NAMES = ["万", "条", "筒"];
const FAN_ORDER_HINT = "国标麻将：八番起和，花牌每张 1 分。";

let actionLock = false;
let selected = new Set();
let lastHandJson = "";

function tileLabel(code) {
  if (code >= 34) return "春夏秋冬梅兰竹菊"[code - 34];
  if (code >= 27) return "东南西北中发白"[code - 27];
  return `${code % 9 + 1}${SUIT_NAMES[Math.floor(code / 9)]}`;
}

function isHonor(code) {
  return code >= 27 && code < 34;
}

function sortHand(hand) {
  return hand.map((code, index) => ({ code, index }))
    .sort((a, b) => Math.floor(a.code / 9) - Math.floor(b.code / 9)
      || a.code - b.code);
}

/* =========================================================
   牌面渲染
========================================================= */

function mjTileNode(code, opts = {}) {
  const node = document.createElement("span");
  node.className = "mj-tile";
  if (opts.small) node.classList.add("small");
  if (opts.tiny) node.classList.add("tiny");
  if (opts.picked) node.classList.add("picked");
  if (opts.win) node.classList.add("win");
  if (code >= 34) {
    node.classList.add("flower");
    node.textContent = tileLabel(code);
    node.title = "花牌（每张 1 分）";
    return node;
  }
  if (isHonor(code)) {
    node.classList.add(code === 31 ? "suit-z" : code === 32 ? "suit-f" : "suit-w");
    const face = document.createElement("span");
    face.className = "mt-face";
    face.textContent = tileLabel(code);
    node.append(face);
    return node;
  }
  node.classList.add(`suit${Math.floor(code / 9)}`);
  const face = document.createElement("span");
  face.className = "mt-face";
  face.textContent = String(code % 9 + 1);
  const suit = document.createElement("span");
  suit.className = "mt-suit";
  suit.textContent = SUIT_NAMES[Math.floor(code / 9)];
  node.append(face, suit);
  return node;
}

function mjBackNode(opts = {}) {
  const node = document.createElement("span");
  node.className = "mj-tile back";
  if (opts.tiny) node.classList.add("tiny");
  return node;
}

/* =========================================================
   操作
========================================================= */

function mjAct(payload) {
  if (actionLock) return;
  actionLock = send({ type: "poker_action", ...payload });
  if (actionLock) {
    document.querySelectorAll(".mj-dock button").forEach((b) => { b.disabled = true; });
  }
}

document.addEventListener("gameactionerror", () => {
  if (state.myRoom?.game_type !== "mahjong") return;
  actionLock = false;
  renderGameView();
});

function isMyTurn() {
  return Boolean(state.currentUser) && state.myRoom.to_act === state.currentUser.username;
}

function mySeatIndex() {
  const players = state.myRoom.players || [];
  return Math.max(0, players.findIndex((p) => p.username === state.currentUser?.username));
}

/* =========================================================
   牌桌渲染
========================================================= */

function seatNode(p) {
  const room = state.myRoom;
  const seat = document.createElement("div");
  seat.className = "mj-seat";
  seat.dataset.username = p.username;
  if (room.status === "playing" && room.to_act === p.username) seat.classList.add("active");
  if (state.currentUser && p.username === state.currentUser.username) seat.classList.add("me");
  const name = document.createElement("div");
  name.className = "ms-name";
  const wind = document.createElement("span");
  wind.className = "ms-wind";
  wind.textContent = p.seat_wind;
  if (p.is_dealer) {
    wind.classList.add("dealer");
    wind.title = "庄家";
  }
  name.append(wind, document.createTextNode(p.nickname));
  const info = document.createElement("div");
  info.className = "ms-info";
  const stack = document.createElement("span");
  stack.className = "ms-stack";
  stack.textContent = formatCoins(p.stack);
  if (p.flowers) {
    const flowers = document.createElement("span");
    flowers.className = "ms-flowers";
    flowers.textContent = `🌸${p.flowers}`;
    flowers.title = `花牌 ${p.flowers} 张`;
    info.append(flowers);
  }
  info.append(stack);
  seat.append(name, ratingBadge(p.rating), info);
  const melds = document.createElement("div");
  melds.className = "ms-melds";
  for (const meld of p.melds || []) {
    const group = document.createElement("span");
    group.className = `ms-meld meld-${meld.type}`;
    for (const code of meld.tiles) group.append(mjTileNode(code, { tiny: true }));
    if (meld.type === "angang") group.title = "暗杠";
    melds.append(group);
  }
  if (melds.children.length) seat.append(melds);
  if (room.status === "playing" && p.in_hand && p.concealed) {
    const backs = document.createElement("div");
    backs.className = "ms-backs";
    for (let i = 0; i < p.concealed; i += 1) backs.append(mjBackNode({ tiny: true }));
    seat.append(backs);
  }
  return seat;
}

function topbarNode() {
  const room = state.myRoom;
  const bar = document.createElement("div");
  bar.className = "poker-topbar";
  const left = document.createElement("span");
  const rules = room.rules || {};
  left.textContent = `第 ${room.hand_no || "-"} 局 · ${room.round_wind || "东"}风圈 · 庄家 ${displayNameOf(room.dealer)} · 底注 ${room.blind}`
    + ` · 起和${rules.min_fan ?? 8}番`
    + (rules.flowers ? " · 花牌开" : " · 花牌关")
    + (rules.chow ? " · 吃开" : " · 吃关");
  const right = document.createElement("span");
  right.textContent = room.paused ? "⏸ 已暂停" : `牌墙余 ${room.wall_count ?? 0} 张`;
  bar.append(left, right);
  return bar;
}

function statusNode() {
  const room = state.myRoom;
  const status = document.createElement("div");
  status.className = "poker-status";
  const la = room.last_action;
  status.textContent = la ? `${la.nickname} ${la.text}`
    : room.claim ? `${displayNameOf(room.claim.by)} 打出 ${tileLabel(room.claim.tile)}，等待响应…`
      : room.to_act ? `等待 ${displayNameOf(room.to_act)} 出牌…` : "发牌中…";
  return status;
}

function pileNode(username, position) {
  const room = state.myRoom;
  const pile = document.createElement("div");
  pile.className = `mj-pile pile-${position}`;
  const tiles = (room.discards?.[username] || []).slice(-12);
  for (const code of tiles) {
    const isLast = room.last_discard && room.last_discard.by === username
      && room.last_discard.tile === code
      && (room.discards[username] || []).length
      && room.discards[username][room.discards[username].length - 1] === code;
    const node = mjTileNode(code, { tiny: true });
    if (isLast) node.classList.add("just-discarded");
    pile.append(node);
  }
  return pile;
}

function centerNode() {
  const room = state.myRoom;
  const center = document.createElement("div");
  center.className = "mj-center";
  const badge = document.createElement("div");
  badge.className = "mj-center-badge";
  badge.textContent = `${room.round_wind || "东"}风圈 · 墙 ${room.wall_count ?? 0}`;
  center.append(badge);
  const me = mySeatIndex();
  const positions = ["pile-bottom", "pile-right", "pile-top", "pile-left"];
  for (const p of room.players) {
    const relative = (room.players.indexOf(p) - me + room.players.length) % room.players.length;
    center.append(pileNode(p.username, positions[relative] || "pile-top"));
  }
  if (room.claim) {
    const claim = document.createElement("div");
    claim.className = "mj-claim-badge";
    claim.textContent = `${displayNameOf(room.claim.by)} 打出 ${tileLabel(room.claim.tile)}`
      + (room.claim.waiting?.length ? ` · 等待 ${room.claim.waiting.map(displayNameOf).join("、")}` : "");
    center.append(claim);
  }
  return center;
}

function tenpaiNode() {
  const tenpai = state.myRoom.tenpai;
  if (!tenpai || !tenpai.waits?.length) return null;
  const node = document.createElement("div");
  node.className = "mj-tenpai";
  const label = document.createElement("span");
  label.className = "mj-tenpai-label";
  label.textContent = "听";
  node.append(label);
  for (const code of tenpai.waits) {
    const chip = document.createElement("span");
    chip.className = "mj-tenpai-chip";
    const remaining = tenpai.remaining?.[code];
    chip.title = remaining != null ? `可见余 ${remaining} 张` : "";
    chip.append(mjTileNode(code, { tiny: true }));
    const count = document.createElement("span");
    count.textContent = remaining != null ? `×${remaining}` : "";
    chip.append(count);
    node.append(chip);
  }
  return node;
}

function resultNode(result) {
  const box = document.createElement("div");
  box.className = "poker-result mj-result";
  if (result.aborted) {
    const note = document.createElement("div");
    note.className = "poker-result-row";
    note.textContent = "有人离桌，本局作废，筹码原封不动。";
    box.append(note);
    return box;
  }
  if (result.draw_game) {
    const note = document.createElement("div");
    note.className = "poker-result-row";
    note.textContent = "牌墙摸空，荒庄流局：不计分，庄家连庄。";
    box.append(note);
  } else if (result.winner) {
    const head = document.createElement("div");
    head.className = "poker-result-row mj-win-row";
    const left = document.createElement("span");
    left.textContent = `🏆 ${result.winner_name || displayNameOf(result.winner)} `
      + `${result.zimo ? "自摸" : `胡 ${displayNameOf(result.loser)} 打出的 ${tileLabel(result.win_tile)}`}`
      + ` · ${result.fan_total} 番`;
    const right = document.createElement("span");
    right.className = "win";
    right.textContent = `+${formatCoins(result.gains?.[result.winner] || 0)}`;
    head.append(left, right);
    box.append(head);
    const fans = document.createElement("div");
    fans.className = "mj-fans";
    for (const fan of result.fans || []) {
      const chip = document.createElement("span");
      chip.className = "mj-fan-chip";
      chip.textContent = `${fan.name} ${fan.value}`;
      fans.append(chip);
    }
    if (fans.children.length) box.append(fans);
  }
  const rows = document.createElement("div");
  for (const name of Object.keys(result.hands || {})) {
    requestProfile(name);
  }
  const paying = Object.entries(result.payouts || {});
  if (paying.length && !result.draw_game) {
    for (const [name, amount] of paying) {
      requestProfile(name);
      const row = document.createElement("div");
      row.className = "poker-result-row";
      const who = document.createElement("span");
      who.textContent = `${displayNameOf(name)} 支付`;
      const amt = document.createElement("span");
      amt.className = "lose";
      amt.textContent = `-${formatCoins(amount)}`;
      row.append(who, amt);
      rows.append(row);
    }
    box.append(rows);
  }
  const reveal = document.createElement("div");
  reveal.className = "uno-reveal";
  for (const [name, tiles] of Object.entries(result.hands || {})) {
    requestProfile(name);
    const line = document.createElement("div");
    line.className = "uno-reveal-row";
    const label = document.createElement("span");
    label.className = "uno-reveal-name";
    const won = name === result.winner;
    label.textContent = `${won ? "👑 " : ""}${displayNameOf(name)}`;
    const cardsBox = document.createElement("span");
    cardsBox.className = "uno-reveal-cards";
    for (const meld of result.melds?.[name] || []) {
      for (const code of meld.tiles) cardsBox.append(mjTileNode(code, { small: true }));
    }
    for (const code of tiles || []) {
      cardsBox.append(mjTileNode(code, { small: true, win: won && code === result.win_tile }));
    }
    for (const code of result.flowers?.[name] || []) {
      cardsBox.append(mjTileNode(code, { small: true }));
    }
    line.append(label, cardsBox);
    reveal.append(line);
  }
  if (reveal.children.length) box.append(reveal);
  return box;
}

function actionBarNode() {
  const room = state.myRoom;
  const bar = document.createElement("div");
  bar.className = "action-bar";
  const options = room.your_options || {};
  const claim = options.claim;

  if (options.discard && isMyTurn() && !room.paused) {
    const legal = selected.size === 1;
    const play = document.createElement("button");
    play.type = "button";
    play.className = "action-btn primary";
    play.textContent = legal ? `出牌 · ${tileLabel([...selected][0])}` : "选中要打出的牌";
    play.disabled = !legal;
    play.addEventListener("click", () => {
      if (!legal) return;
      mjAct({ action: "discard", index: [...selected][0] });
    });
    bar.append(play);
    for (const code of options.angang || []) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "action-btn";
      btn.textContent = `暗杠 ${tileLabel(code)}`;
      btn.addEventListener("click", () => mjAct({ action: "angang", index: (room.your_hand || []).indexOf(code) }));
      bar.append(btn);
    }
    for (const code of options.bugang || []) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "action-btn";
      btn.textContent = `补杠 ${tileLabel(code)}`;
      btn.addEventListener("click", () => mjAct({ action: "bugang", index: (room.your_hand || []).indexOf(code) }));
      bar.append(btn);
    }
    if (options.zimo) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "action-btn danger";
      btn.textContent = "自摸胡";
      btn.addEventListener("click", () => mjAct({ action: "hu" }));
      bar.append(btn);
    }
    return bar;
  }

  if (claim && !room.paused) {
    if (claim.hu) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "action-btn danger";
      btn.textContent = "胡";
      btn.addEventListener("click", () => mjAct({ action: "claim", kind: "hu" }));
      bar.append(btn);
    }
    if (claim.gang) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "action-btn";
      btn.textContent = `杠 ${tileLabel(room.claim.tile)}`;
      btn.addEventListener("click", () => mjAct({ action: "claim", kind: "gang" }));
      bar.append(btn);
    }
    if (claim.peng) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "action-btn";
      btn.textContent = `碰 ${tileLabel(room.claim.tile)}`;
      btn.addEventListener("click", () => mjAct({ action: "claim", kind: "peng" }));
      bar.append(btn);
    }
    for (const pair of claim.chi || []) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "action-btn";
      const tiles = [...pair, room.claim.tile].sort((a, b) => a - b);
      btn.textContent = `吃 ${tiles.map(tileLabel).join(" ")}`;
      btn.addEventListener("click", () => mjAct({ action: "claim", kind: "chi", tiles: pair }));
      bar.append(btn);
    }
    const pass = document.createElement("button");
    pass.type = "button";
    pass.className = "action-btn quiet";
    pass.textContent = "过";
    pass.addEventListener("click", () => mjAct({ action: "pass" }));
    bar.append(pass);
  }
  return bar;
}

function renderMahjongTable() {
  const room = state.myRoom;
  const body = elements.gameMain;
  actionLock = false;
  body.replaceChildren();

  const handJson = JSON.stringify(room.your_hand || []);
  if (handJson !== lastHandJson) {
    selected = new Set();
    lastHandJson = handJson;
  }

  const wrap = document.createElement("div");
  wrap.className = "poker-page mj-page";
  body.append(wrap);

  const table = document.createElement("div");
  table.className = "mj-table";
  table.append(topbarNode(), statusNode());

  const seats = document.createElement("div");
  seats.className = "mj-seats";
  const players = room.players;
  const me = mySeatIndex();
  const positions = ["pos-bottom", "pos-right", "pos-top", "pos-left"];
  players.forEach((p, index) => {
    const seat = seatNode(p);
    const relative = (index - me + players.length) % players.length;
    seat.classList.add(positions[relative] || "pos-top");
    seats.append(seat);
  });
  table.append(seats, centerNode());

  if (room.result) table.append(resultNode(room.result));
  if (room.paused) {
    const overlay = document.createElement("div");
    overlay.className = "paused-overlay";
    overlay.textContent = "⏸ 牌局已暂停，等待房主继续";
    table.append(overlay);
  }
  wrap.append(table);

  const dock = document.createElement("div");
  dock.className = "poker-dock mj-dock";
  dock.classList.toggle("is-my-turn", isMyTurn() && !room.paused && room.phase === "discard");
  const dockHead = document.createElement("div");
  dockHead.className = "dock-head";
  const label = document.createElement("div");
  label.className = "my-cards-label";
  const hand = room.your_hand || [];
  const claimMine = room.your_options?.claim;
  label.textContent = room.claim && claimMine && !room.your_options?.passed
    ? "有人打出的牌可以响应"
    : isMyTurn() && room.phase === "discard"
      ? "轮到你出牌 · 选中一张打出"
      : `你的手牌 · ${hand.length} 张`;
  const chatToggle = document.createElement("button");
  chatToggle.className = "dock-chat-toggle";
  chatToggle.type = "button";
  chatToggle.textContent = "💬 聊天";
  chatToggle.addEventListener("click", openChatOverlay);
  dockHead.append(label, chatToggle);
  dock.append(dockHead);

  if (room.your_flowers?.length) {
    const flowers = document.createElement("div");
    flowers.className = "mj-my-flowers";
    const flabel = document.createElement("span");
    flabel.className = "my-cards-label";
    flabel.textContent = "花牌";
    flowers.append(flabel);
    for (const code of room.your_flowers) flowers.append(mjTileNode(code, { small: true }));
    dock.append(flowers);
  }

  const tenpai = tenpaiNode();
  if (tenpai) dock.append(tenpai);

  const myCards = document.createElement("div");
  myCards.className = "mj-hand";
  if (!hand.length) {
    const waiting = document.createElement("span");
    waiting.className = "my-cards-label";
    waiting.textContent = room.status === "playing" ? "等待本局结束…" : "等待发牌…";
    myCards.append(waiting);
  }
  for (const { code, index } of sortHand(hand)) {
    const node = document.createElement("button");
    node.type = "button";
    node.className = "mj-hand-card";
    node.append(mjTileNode(code, { picked: selected.has(index) }));
    node.setAttribute("aria-label", tileLabel(code));
    node.addEventListener("click", () => {
      if (selected.has(index)) selected.delete(index);
      else {
        selected.clear();
        selected.add(index);
      }
      renderGameView();
    });
    myCards.append(node);
  }
  dock.append(myCards);

  const countdown = document.createElement("div");
  countdown.className = "countdown";
  const fill = document.createElement("div");
  fill.className = "countdown-fill";
  countdown.append(fill);
  dock.append(countdown);

  if (!room.paused && ((isMyTurn() && room.phase === "discard") || claimMine)) {
    dock.append(actionBarNode());
    if (room.turn_left > 0) startHallTicker(fill, Math.max(1, room.turn_left));
  }
  wrap.append(dock);

  reapplySeatBubbles();
}

/* =========================================================
   事件绑定
========================================================= */

registerGame("mahjong", {
  stakeLabel: "底注",
  blindLabel: "下一局底注",
  waitingHint: `国标麻将需要正好 4 名玩家：吃碰杠胡、八番起和，花牌每张 1 分。${FAN_ORDER_HINT}等待房主开局，中途退出本局作废、筹码原封退回。`,
  noNextHint: () => "人数不足 4 人或有人筹码已输光，过半数投「解散」后房间将按当前筹码退还所有人。",
  renderTable: renderMahjongTable,
  renderReview: (result) => {
    const review = document.createElement("div");
    const title = document.createElement("div");
    title.className = "hall-section-title";
    title.style.marginTop = "0";
    title.textContent = "本局回顾";
    review.append(title, resultNode(result));
    return review;
  },
  seatElement: (index) => document.querySelector(
    `#gameMain .mj-seats .mj-seat:nth-child(${index + 1})`),
});
