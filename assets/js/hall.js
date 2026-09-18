/* 大厅：游戏选择、房间列表、建房表单。 */

import { openLogin } from "./auth.js";
import { elements, formatCoins, renderGameView, send, state } from "./core.js";
import { onMessage, registerView } from "./registry.js";

const GAME_TYPES = [
  {
    id: "holdem",
    name: "德州扑克 · 无限注",
    icon: "♠",
    desc: "经典规则：盲注轮转、边池分配、全下自动跑马。金币买入，离桌自动结算。",
  },
  {
    id: "uno",
    name: "UNO · 经典牌局",
    icon: "🃏",
    desc: "同色同数出牌，功能牌逆转战局。剩牌按张赔给赢家，先出完者通吃本局。",
  },
];

const createDraft = { name: "", buyin: "100", blind: "5" };

function renderEntry() {
  const body = elements.gameMain;
  body.replaceChildren();
  const card = document.createElement("div");
  card.className = "game-entry-card";
  const icon = document.createElement("div");
  icon.className = "hall-game-icon";
  icon.textContent = "♠";
  const title = document.createElement("div");
  title.className = "game-entry-title";
  title.textContent = "欢迎来到游戏厅";
  const desc = document.createElement("div");
  desc.className = "game-entry-desc";
  desc.textContent = "登录后与直播间的朋友们来一局德州扑克，金币通用。";
  const button = document.createElement("button");
  button.className = "login-button";
  button.type = "button";
  button.textContent = "登录 / 注册";
  button.addEventListener("click", openLogin);
  card.append(icon, title, desc, button);
  body.append(card);
}

function renderHall() {
  const body = elements.gameMain;
  body.replaceChildren();
  const heading = document.createElement("div");
  heading.className = "hall-page-title";
  heading.textContent = "选择小游戏";
  body.append(heading);

  const grid = document.createElement("div");
  grid.className = "hall-grid";
  for (const game of GAME_TYPES) {
    const card = document.createElement("button");
    card.className = "hall-game-card";
    card.type = "button";
    const icon = document.createElement("div");
    icon.className = "hall-game-icon";
    icon.textContent = game.icon;
    const info = document.createElement("div");
    const gname = document.createElement("div");
    gname.className = "hall-game-name";
    gname.textContent = game.name;
    const gdesc = document.createElement("div");
    gdesc.className = "hall-game-desc";
    gdesc.textContent = game.desc;
    info.append(gname, gdesc);
    const go = document.createElement("div");
    go.className = "hall-game-go";
    go.textContent = "选择进入 →";
    card.append(icon, info, go);
    card.addEventListener("click", () => {
      state.currentGameId = game.id;
      state.hallPage = "rooms";
      renderGameView();
    });
    grid.append(card);
  }
  body.append(grid);
}

function currentGameMeta() {
  return GAME_TYPES.find((g) => g.id === state.currentGameId) || GAME_TYPES[0];
}

export function gameMetaById(id) {
  return GAME_TYPES.find((g) => g.id === id) || GAME_TYPES[0];
}

export function fillBlindOptions(select, gameId, selected) {
  for (const b of [1, 2, 5, 10]) {
    const opt = document.createElement("option");
    opt.value = String(b);
    opt.textContent = gameId === "uno" ? `每张赔付 ${b}` : `盲注 ${b}/${b * 2}`;
    if (String(b) === String(selected)) opt.selected = true;
    select.append(opt);
  }
}

function backChip(label, onClick) {
  const back = document.createElement("button");
  back.className = "online-stat hall-back";
  back.type = "button";
  back.textContent = label;
  back.addEventListener("click", onClick);
  return back;
}

function renderGameRooms() {
  const game = currentGameMeta();
  const body = elements.gameMain;
  body.replaceChildren();

  const toolbar = document.createElement("div");
  toolbar.className = "rooms-toolbar";
  toolbar.append(backChip("← 游戏厅", () => {
    state.hallPage = null;
    state.currentGameId = null;
    renderGameView();
  }));
  const heading = document.createElement("div");
  heading.className = "hall-page-title";
  heading.textContent = `${game.name} · 房间列表`;
  toolbar.append(heading);
  body.append(toolbar);

  const page = document.createElement("div");
  page.className = "game-card-page";
  body.append(page);

  const roomsBox = document.createElement("div");
  roomsBox.id = "hallRoomsBox";
  page.append(roomsBox);
  fillRoomList(roomsBox);

  const newCard = document.createElement("button");
  newCard.className = "new-room-card";
  newCard.type = "button";
  newCard.title = "新建房间";
  newCard.textContent = "＋";
  newCard.addEventListener("click", () => {
    state.hallPage = "create";
    renderGameView();
  });
  page.append(newCard);
}

function refreshRoomList() {
  const box = document.getElementById("hallRoomsBox");
  if (!box) {
    renderGameView();
    return;
  }
  box.replaceChildren();
  fillRoomList(box);
}

function fillRoomList(box) {
  const rooms = state.hallRooms.filter((room) => !state.currentGameId || room.game === state.currentGameId);
  if (!rooms.length) {
    const empty = document.createElement("div");
    empty.className = "invite-empty";
    empty.textContent = "当前没有房间，点下方 ＋ 新建一个";
    box.append(empty);
    return;
  }
  for (const room of rooms) {
    const row = document.createElement("div");
    row.className = "hall-room";
    const info = document.createElement("div");
    const rname = document.createElement("div");
    rname.className = "hall-room-name";
    rname.textContent = room.name;
    const meta = document.createElement("div");
    meta.className = "hall-room-meta";
    meta.textContent = `${room.status === "playing" ? "🔴 游戏中" : "🟢 等待中"} · 房主 ${room.owner_name} · ${room.players.length} 人 · 买入 ${formatCoins(room.buy_in)}`;
    info.append(rname, meta);
    const join = document.createElement("button");
    join.className = "hall-join";
    join.type = "button";
    join.textContent = "进入";
    join.disabled = room.players.length >= 9;
    join.addEventListener("click", () => send({ type: "join_room", room_id: room.id }));
    row.append(info, join);
    box.append(row);
  }
}

function renderCreate() {
  const game = currentGameMeta();
  const body = elements.gameMain;
  body.replaceChildren();

  const toolbar = document.createElement("div");
  toolbar.className = "rooms-toolbar";
  toolbar.append(backChip("← 返回房间列表", () => {
    state.hallPage = "rooms";
    renderGameView();
  }));
  const heading = document.createElement("div");
  heading.className = "hall-page-title";
  heading.textContent = `新建房间 · ${game.name}`;
  toolbar.append(heading);
  body.append(toolbar);

  const page = document.createElement("div");
  page.className = "game-card-page";
  body.append(page);

  const hint = document.createElement("div");
  hint.className = "game-hint";
  hint.style.marginTop = "0";
  hint.textContent = "设置房间参数，创建后进入房间等待其他玩家加入。";
  page.append(hint);

  const form = document.createElement("div");
  form.className = "create-form-column";
  const name = document.createElement("input");
  name.className = "login-input";
  name.maxLength = 20;
  name.placeholder = "房间名（可留空）";
  name.value = createDraft.name;
  name.addEventListener("input", () => { createDraft.name = name.value; });
  const buyin = document.createElement("input");
  buyin.className = "login-input";
  buyin.type = "number";
  buyin.min = "20";
  buyin.step = "10";
  buyin.value = createDraft.buyin;
  buyin.placeholder = "买入金币";
  buyin.addEventListener("input", () => { createDraft.buyin = buyin.value; });
  const blind = document.createElement("select");
  blind.className = "login-input";
  fillBlindOptions(blind, game.id, createDraft.blind);
  blind.addEventListener("change", () => { createDraft.blind = blind.value; });
  const create = document.createElement("button");
  create.className = "login-submit";
  create.type = "button";
  create.textContent = "创建房间";
  create.addEventListener("click", () => {
    const value = Math.round(Number(buyin.value) * 100) / 100;
    if (!Number.isFinite(value) || value <= 0) {
      alert("请输入正确的买入金额");
      return;
    }
    if (state.currentUser && value > state.currentUser.coins) {
      alert("金币不足");
      return;
    }
    send({
      type: "create_room",
      game: state.currentGameId,
      name: name.value.trim(),
      buy_in: value,
      blind: Number(blind.value),
    });
  });
  form.append(name, buyin, blind, create);
  page.append(form);

  const note = document.createElement("div");
  note.className = "game-hint";
  note.textContent = game.id === "uno"
    ? "买入至少为赔付单位的 20 倍。一手结束赢家按各家剩牌数（每张 × 底注）收注，离桌自动按筹码结算。"
    : "买入至少为小盲注的 20 倍。开局后房主可随时流局，所有人按当前筹码退回金币。";
  page.append(note);
}


/* =========================================================
   房间视图
========================================================= */

onMessage("room_list", (data) => {
  state.hallRooms = data.rooms || [];
  if (!state.myRoom && state.hallPage === "rooms") refreshRoomList();
});

registerView("entry", renderEntry);
registerView("hall", renderHall);
registerView("rooms", renderGameRooms);
registerView("create", renderCreate);
