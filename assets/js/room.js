/* 房间外壳：等待开局、房间聊天与座位气泡、结算投票页。 */

import { elements, formatCoins, isRoomOwner, renderGameView, send, setRoomMode, state, stopHallTicker, updateCoinChip } from "./core.js";
import { fillBlindOptions, gameMetaById } from "./hall.js";
import { gameView, onMessage, registerView } from "./registry.js";

const seatBubbles = new Map();

function roomChatRowNode(m) {
  const row = document.createElement("div");
  row.className = "rc-message";
  const name = document.createElement("span");
  name.className = "rc-name";
  name.textContent = m.nickname || m.username;
  const time = document.createElement("span");
  time.className = "rc-time";
  time.textContent = m.time || "";
  const text = document.createElement("div");
  text.className = "rc-text";
  text.textContent = m.text;
  row.append(name, time, text);
  return row;
}

function scrollRoomChat() {
  const list = document.getElementById("roomChatList");
  if (list) list.scrollTop = list.scrollHeight;
}

function refillRoomChatList() {
  const lists = document.querySelectorAll(".room-chat-list");
  if (!lists.length) return;
  const rows = state.roomChat.map((m) => roomChatRowNode(m));
  for (const list of lists) {
    list.replaceChildren(...rows.map((r) => r.cloneNode(true)));
    list.scrollTop = list.scrollHeight;
  }
}

function appendRoomChatRow(m) {
  const row = roomChatRowNode(m);
  for (const list of document.querySelectorAll(".room-chat-list")) {
    list.append(row.cloneNode(true));
    while (list.children.length > 60) list.firstElementChild.remove();
    list.scrollTop = list.scrollHeight;
  }
}

function sendRoomChat() {
  const input = document.getElementById("roomChatInput");
  const text = (input?.value || state.roomChatDraft).trim();
  if (!text) return;
  if (send({ type: "room_chat", text })) {
    state.roomChatDraft = "";
    if (input) input.value = "";
  }
}

function chatOpenButton() {
  const wrap = document.createElement("div");
  wrap.className = "chat-open-row";
  const btn = document.createElement("button");
  btn.className = "dock-chat-toggle";
  btn.type = "button";
  btn.textContent = `💬 房间聊天（${state.roomChat.length}）`;
  btn.addEventListener("click", openChatOverlay);
  wrap.append(btn);
  return wrap;
}

function showSeatBubble(username, text) {
  if (!state.myRoom) return;
  seatBubbles.set(username, { text: text.length > 60 ? `${text.slice(0, 60)}…` : text, until: Date.now() + 3000 });
  applySeatBubble(username);
  window.setTimeout(() => {
    const bubble = seatBubbles.get(username);
    if (bubble && bubble.until <= Date.now()) {
      seatBubbles.delete(username);
      if (!state.myRoom) return;
      const idx = state.myRoom.players.findIndex((p) => p.username === username);
      if (idx >= 0) removeSeatBubble(seatNodeByIndex(idx));
    }
  }, 3100);
}

function applySeatBubble(username) {
  if (!state.myRoom) return;
  const index = state.myRoom.players.findIndex((p) => p.username === username);
  if (index < 0) return;
  const seat = seatNodeByIndex(index);
  if (!seat) return;
  removeSeatBubble(seat);
  const bubble = seatBubbles.get(username);
  if (!bubble || bubble.until <= Date.now()) return;
  const node = document.createElement("div");
  node.className = "seat-bubble";
  node.textContent = bubble.text;
  seat.append(node);
}

function removeSeatBubble(seat) {
  seat.querySelector(".seat-bubble")?.remove();
}

export function openChatOverlay() {
  closeChatOverlay();
  const overlay = document.createElement("div");
  overlay.className = "chat-overlay";
  overlay.id = "chatOverlay";
  const head = document.createElement("div");
  head.className = "chat-overlay-head";
  const title = document.createElement("div");
  title.textContent = "房间聊天";
  const close = document.createElement("button");
  close.className = "chat-overlay-close";
  close.type = "button";
  close.textContent = "✕";
  close.addEventListener("click", closeChatOverlay);
  head.append(title, close);
  const list = document.createElement("div");
  list.className = "room-chat-list chat-overlay-list";
  list.replaceChildren(...roomChat.map((m) => roomChatRowNode(m)));
  // 聊天输入整合进二级菜单（浮层），桌面与手机横屏共用
  const composer = document.createElement("div");
  composer.className = "chat-overlay-composer";
  const input = document.createElement("input");
  input.className = "chat-input";
  input.id = "roomChatInput";
  input.maxLength = 200;
  input.placeholder = "说点什么…（对全桌可见）";
  input.value = state.roomChatDraft;
  input.autocomplete = "off";
  input.addEventListener("input", () => { state.roomChatDraft = input.value; });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.isComposing) sendRoomChat();
  });
  const sendBtn = document.createElement("button");
  sendBtn.className = "send-button";
  sendBtn.type = "button";
  sendBtn.textContent = "发送";
  sendBtn.addEventListener("click", sendRoomChat);
  composer.append(input, sendBtn);
  overlay.append(head, list, composer);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) closeChatOverlay();
  });
  document.body.append(overlay);
  list.scrollTop = list.scrollHeight;
  input.focus({ preventScroll: true });
}

export function closeChatOverlay() {
  document.getElementById("chatOverlay")?.remove();
}


/* =========================================================
   UNO 牌桌
========================================================= */

export function renderRoom() {
  setRoomMode();
  if (state.myRoom.status === "playing") {
    if (state.myRoom.settlement) renderSettlementView();
    else gameView(state.myRoom.game_type)?.renderTable();
  } else renderRoomLobby();
}

function seatNodeByIndex(index) {
  // 座位 DOM 由各游戏模块自己认领（扑克 .poker-seats / UNO .uno-seats）
  return gameView(state.myRoom?.game_type)?.seatElement(index) || null;
}

/** 牌桌重绘后把仍在有效期内的聊天气泡贴回座位。 */
export function reapplySeatBubbles() {
  for (const username of seatBubbles.keys()) applySeatBubble(username);
}

export function renderRoomLobby() {
  stopHallTicker();
  const game = gameView(state.myRoom.game_type);
  const body = elements.gameMain;
  body.replaceChildren();
  const meta = gameMetaById(state.myRoom.game_type);

  const page = document.createElement("div");
  page.className = "game-card-page";
  body.append(page);

  const info = document.createElement("div");
  info.className = "game-hint";
  info.style.marginTop = "0";
  info.textContent = `${meta.name} · ${game?.stakeLabel || "小盲注"} ${state.myRoom.blind} · 买入 ${formatCoins(state.myRoom.buy_in)} · 房主 ${state.myRoom.owner_name}`;
  page.append(info);

  const title = document.createElement("div");
  title.className = "hall-section-title";
  title.textContent = `等待玩家加入（${state.myRoom.players.length}）`;
  page.append(title);

  const list = document.createElement("div");
  list.className = "game-players";
  for (const p of state.myRoom.players) {
    const row = document.createElement("div");
    row.className = "game-player-row";
    const name = document.createElement("span");
    name.textContent = p.nickname;
    if (p.username === state.myRoom.owner) {
      const badge = document.createElement("span");
      badge.className = "badge-owner";
      badge.textContent = "房主";
      name.append(badge);
    }
    if (state.currentUser && p.username === state.currentUser.username) {
      const badge = document.createElement("span");
      badge.className = "badge-owner me-badge";
      badge.textContent = "我";
      name.append(badge);
    }
    const stack = document.createElement("span");
    stack.className = "badge-stack";
    stack.textContent = `${formatCoins(p.stack)} 筹码`;
    row.append(name, stack);
    list.append(row);
  }
  page.append(list);

  if (isRoomOwner()) {
    const start = document.createElement("button");
    start.className = "login-submit";
    start.type = "button";
    start.textContent = "开始游戏";
    start.disabled = state.myRoom.players.filter((p) => p.stack > 0).length < 2;
    start.addEventListener("click", () => send({ type: "start_game" }));
    page.append(start);
  }

  const hint = document.createElement("div");
  hint.className = "game-hint";
  hint.textContent = isRoomOwner()
    ? "满 2 名有筹码的玩家即可开局。开局后可在顶部「管理」中流局、暂停或重新开始。"
    : (game?.waitingHint || "等待房主开局。");
  page.append(hint);

  body.append(chatOpenButton());
}

export function renderSettlementView() {
  const game = gameView(state.myRoom.game_type);
  const body = elements.gameMain;
  body.replaceChildren();

  const heading = document.createElement("div");
  heading.className = "hall-page-title";
  heading.textContent = `${state.myRoom.name} · 本局结算`;
  body.append(heading);

  const resultCard = document.createElement("div");
  resultCard.className = "game-card-page";
  if (state.myRoom.result && game) {
    resultCard.append(game.renderReview(state.myRoom.result));
  } else {
    const note = document.createElement("div");
    note.className = "game-hint";
    note.style.marginTop = "0";
    note.textContent = "牌局已结束。";
    resultCard.append(note);
  }
  body.append(resultCard);

  const settlement = state.myRoom.settlement;
  const votes = settlement?.votes || {};
  const total = settlement?.total || state.myRoom.players.length;
  const nextCount = Object.values(votes).filter((v) => v.choice === "next").length;
  const dissolveCount = Object.values(votes).filter((v) => v.choice === "dissolve").length;
  const myChoice = state.currentUser ? votes[state.currentUser.username]?.choice : null;

  const voteCard = document.createElement("div");
  voteCard.className = "game-card-page";
  const voteTitle = document.createElement("div");
  voteTitle.className = "hall-section-title";
  voteTitle.style.marginTop = "0";
  voteTitle.textContent = "接下来做什么？（过半数生效）";
  voteCard.append(voteTitle);

  const progress = document.createElement("div");
  progress.className = "settle-progress";
  progress.textContent = `已投 ${nextCount + dissolveCount} / ${total} 票 · 再来一局 ${nextCount} 票 · 解散 ${dissolveCount} 票`;
  voteCard.append(progress);

  const canNext = Boolean(settlement?.can_next);
  const blindRow = document.createElement("div");
  blindRow.className = "settle-blind-row";
  const blindLabel = document.createElement("span");
  blindLabel.className = "settle-blind-label";
  blindLabel.textContent = game?.blindLabel || "下一局盲注";
  const blind = document.createElement("select");
  blind.className = "login-input";
  blind.id = "settleBlindSelect";
  fillBlindOptions(blind, state.myRoom.game_type, settlement?.blind || state.myRoom.blind);
  blind.disabled = !canNext;
  blindRow.append(blindLabel, blind);
  voteCard.append(blindRow);

  const btnRow = document.createElement("div");
  btnRow.className = "game-btn-row";
  const again = document.createElement("button");
  again.className = "login-submit";
  again.type = "button";
  again.textContent = myChoice === "next" ? "已投：再来一局" : "结算并再来一局";
  again.disabled = !canNext;
  if (!canNext) again.title = "有人筹码不足下一局盲注";
  again.addEventListener("click", () => {
    send({ type: "settle_vote", choice: "next", blind: Number(blind.value) });
  });
  btnRow.append(again);

  const dissolve = document.createElement("button");
  dissolve.className = "login-submit danger";
  dissolve.type = "button";
  dissolve.textContent = myChoice === "dissolve" ? "已投：结算并解散房间" : "结算并解散房间";
  dissolve.addEventListener("click", () => {
    send({ type: "settle_vote", choice: "dissolve" });
  });
  btnRow.append(dissolve);
  voteCard.append(btnRow);

  const hint = document.createElement("div");
  hint.className = "game-hint";
  hint.textContent = canNext
    ? "过半数玩家投「再来一局」即开下一局；过半数投「解散」则按当前筹码退还所有人并关闭房间。"
    : (game?.noNextHint?.() || "过半数投「解散」后房间将按当前筹码退还所有人。");
  voteCard.append(hint);
  body.append(voteCard);

  body.append(chatOpenButton());
}

onMessage("game_joined", (data) => {
  state.myRoom = data.room;
  state.currentGameId = state.myRoom.game_type || state.currentGameId || "holdem";
  state.roomChat = [];
  state.roomChatDraft = "";
  updateCoinChip();
  send({ type: "get_finance" });
  renderGameView();
});

onMessage("room_chat_history", (data) => {
  if (state.myRoom && data.room_id === state.myRoom.room_id) {
    state.roomChat = data.messages || [];
    refillRoomChatList();
  }
});

onMessage("room_chat", (data) => {
  if (!state.myRoom || data.room_id !== state.myRoom.room_id) return;
  state.roomChat.push(data);
  if (state.roomChat.length > 60) state.roomChat.shift();
  appendRoomChatRow(data);
  showSeatBubble(data.username, data.text);
});

onMessage("error", (data) => { alert(data.message); });

onMessage("game_update", (data) => {
  if (state.myRoom && data.room_id !== state.myRoom.room_id) return;
  state.myRoom = data;
  renderGameView();
});

onMessage("hand_result", () => {});
onMessage("game_restart", () => {});

onMessage("room_closed", (data) => {
  const hadRoom = Boolean(state.myRoom);
  state.myRoom = null;
  state.roomChat = [];
  state.roomChatDraft = "";
  seatBubbles.clear();
  closeChatOverlay();
  send({ type: "get_finance" });
  if (hadRoom && data.reason) alert(data.reason);
  renderGameView();
});

onMessage("game_error", (data) => { alert(data.message); });

registerView("room", renderRoom);
