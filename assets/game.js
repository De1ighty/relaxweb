"use strict";

const $ = (id) => document.getElementById(id);
const elements = {
  authModal: $("loginModal"), authSubmit: $("authSubmit"),
  authSwitch: $("authSwitch"), authTitle: $("authTitle"),
  coinBalance: $("coinBalance"), coinChip: $("coinChip"),
  dropdownName: $("dropdownName"),
  financeBalance: $("financeBalance"), financeButton: $("financeButton"),
  financeClose: $("financeClose"), financeDetailPanel: $("financeDetailPanel"),
  financeList: $("financeList"), financeModal: $("financeModal"),
  financeTabDetail: $("financeTabDetail"), financeTabTransfer: $("financeTabTransfer"),
  financeTransferPanel: $("financeTransferPanel"),
  gameHeader: $("gameHeader"), gameMain: $("gameMain"),
  inviteCode: $("inviteCode"),
  leaveRoomButton: $("leaveRoomButton"),
  loginButton: $("loginButton"), logoutButton: $("logoutButton"),
  manageButton: $("manageButton"), manageDrawButton: $("manageDrawButton"),
  manageMenu: $("manageMenu"), managePauseButton: $("managePauseButton"),
  manageRestartButton: $("manageRestartButton"), roomManage: $("roomManage"),
  onlineNumber: $("onlineNumber"),
  password: $("password"),
  roomTopName: $("roomTopName"), roomTopbar: $("roomTopbar"),
  transferAmount: $("transferAmount"), transferFeedback: $("transferFeedback"),
  transferSubmit: $("transferSubmit"), transferTo: $("transferTo"),
  userArea: $("userArea"), userAvatar: $("userAvatar"),
  userChip: $("userChip"), userDropdown: $("userDropdown"), userName: $("userName"),
  username: $("username"),
};

const AUTH_TOKEN_KEY = "liveAuthToken";
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
const UNO_COLORS = ["r", "y", "g", "b"];
const UNO_COLOR_NAMES = { r: "红", y: "黄", g: "绿", b: "蓝" };
const UNO_COLOR_TEXT = {
  r: "#e02020", y: "#c77800", g: "#1d9e4f", b: "#1f6fd6", w: "#3a3a3c",
};
const UNO_VALUE_GLYPHS = {
  skip: "⊘", rev: "⇄", d2: "+2", wild: "◎", wd4: "+4",
};
const coinKinds = {
  register: "注册奖励",
  admin: "管理员调整",
  transfer_out: "转账转出",
  transfer_in: "转账转入",
  bet_stake: "竞猜投注",
  bet_win: "竞猜奖励",
  bet_refund: "竞猜退款",
  game_buyin: "游戏厅买入",
  game_settle: "游戏厅结算",
  bet_result: "竞猜结果",
  game_result: "游戏结算",
};
const SUIT_CHARS = ["♠", "♥", "♦", "♣"];
const RANK_CHARS = { 11: "J", 12: "Q", 13: "K", 14: "A" };
const STAGE_NAMES = {
  preflop: "翻牌前",
  flop: "翻牌",
  turn: "转牌",
  river: "河牌",
  showdown: "摊牌",
};

const profiles = new Map();
const pendingProfiles = new Set();
let authMode = "login";
let currentUser = null;
let socket = null;
let reconnectTimer = 0;
let hallRooms = [];
let myRoom = null;
let hallTimer = 0;
let hallDeadlineAt = 0;
let hallBoardCount = 0;
let lastHoleKey = "";
let currentGameId = null;
let hallPage = null;
const createDraft = { name: "", buyin: "100", blind: "5" };
let roomChat = [];
let roomChatDraft = "";
const seatBubbles = new Map();

function formatCoins(value) {
  return Number(value || 0).toFixed(2);
}

function formatClock(epochSeconds) {
  const date = new Date(epochSeconds * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(date.getMonth() + 1)}/${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function displayNameOf(username) {
  const profile = profiles.get(username);
  return profile?.nickname || username;
}

function rememberProfile(data) {
  if (!data?.username) return;
  profiles.set(data.username, {
    nickname: data.nickname || "",
    avatar: data.avatar || "",
  });
  pendingProfiles.delete(data.username);
}

function requestProfile(username) {
  if (!username || profiles.has(username) || pendingProfiles.has(username)) return;
  pendingProfiles.add(username);
  send({ type: "get_profile", username });
}

function send(payload) {
  if (socket?.readyState !== WebSocket.OPEN) {
    alert("游戏厅尚未连接");
    return false;
  }
  socket.send(JSON.stringify(payload));
  return true;
}

function connectGame() {
  clearTimeout(reconnectTimer);
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${protocol}://${location.hostname}:8765/?client=game`);
  socket.addEventListener("open", () => {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    if (token) send({ type: "resume", token });
    else renderGameView();
    send({ type: "list_rooms" });
    send({ type: "get_room" });
  });
  socket.addEventListener("error", () => {});
  socket.addEventListener("close", () => {
    reconnectTimer = window.setTimeout(connectGame, 2000);
  });
  socket.addEventListener("message", ({ data }) => {
    try {
      handleServerMessage(JSON.parse(data));
    } catch (error) {
      console.error("无法解析服务器消息", error);
    }
  });
}

const messageHandlers = {
  online(data) {
    elements.onlineNumber.textContent = data.count;
  },
  register_success() {
    alert("注册成功，请登录");
    elements.password.value = "";
    setAuthMode("login");
  },
  login_success(data) {
    localStorage.setItem(AUTH_TOKEN_KEY, data.token);
    elements.authModal.style.display = "none";
    setSignedIn({
      username: data.username, nickname: data.nickname, avatar: data.avatar,
      coins: data.coins,
    });
  },
  resume_success(data) {
    setSignedIn({
      username: data.username, nickname: data.nickname, avatar: data.avatar,
      coins: data.coins,
    });
  },
  profile(data) {
    rememberProfile(data);
    if (currentUser && data.username === currentUser.username) {
      currentUser.nickname = data.nickname || "";
      currentUser.avatar = data.avatar || "";
      renderIdentity();
    }
    if (myRoom?.result) renderGameView();
  },
  profile_error(data) { alert(data.message); },
  auth_expired() {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    setSignedIn(null);
  },
  auth_error(data) { alert(data.message); },
  finance(data) { renderFinance(data); },
  transfer_success(data) {
    if (currentUser) currentUser.coins = data.coins;
    updateCoinChip();
    elements.transferAmount.value = "";
    TransferSelect.reset();
    elements.transferFeedback.textContent = "转账成功";
    send({ type: "get_finance" });
  },
  coins_error(data) { alert(data.message); },
  coins(data) {
    if (currentUser && data.username === currentUser.username) {
      currentUser.coins = data.coins;
      updateCoinChip();
    }
  },
  room_list(data) {
    hallRooms = data.rooms || [];
    if (!myRoom && hallPage === "rooms") refreshRoomList();
  },
  game_joined(data) {
    myRoom = data.room;
    currentGameId = myRoom.game_type || currentGameId || "holdem";
    roomChat = [];
    roomChatDraft = "";
    updateCoinChip();
    send({ type: "get_finance" });
    renderGameView();
  },
  room_chat_history(data) {
    if (myRoom && data.room_id === myRoom.room_id) {
      roomChat = data.messages || [];
      refillRoomChatList();
    }
  },
  room_chat(data) {
    if (!myRoom || data.room_id !== myRoom.room_id) return;
    roomChat.push(data);
    if (roomChat.length > 60) roomChat.shift();
    appendRoomChatRow(data);
    showSeatBubble(data.username, data.text);
  },
  error(data) { alert(data.message); },
  game_update(data) {
    if (myRoom && data.room_id !== myRoom.room_id) return;
    myRoom = data;
    renderGameView();
  },
  hand_result() {},
  game_restart() {},
  room_closed(data) {
    const hadRoom = Boolean(myRoom);
    myRoom = null;
    roomChat = [];
    roomChatDraft = "";
    seatBubbles.clear();
    closeChatOverlay();
    send({ type: "get_finance" });
    if (hadRoom && data.reason) alert(data.reason);
    renderGameView();
  },
  game_error(data) { alert(data.message); },
  user_list(data) { TransferSelect.setUsers(data.users || []); },
};

function handleServerMessage(data) {
  messageHandlers[data.type]?.(data);
}

function renderIdentity() {
  const user = currentUser;
  const name = user ? user.nickname || user.username : "";
  elements.userAvatar.replaceChildren();
  if (user?.avatar) {
    const image = document.createElement("img");
    image.src = user.avatar;
    image.alt = "";
    elements.userAvatar.append(image);
  } else {
    elements.userAvatar.textContent = user ? user.username.charAt(0).toUpperCase() : "";
  }
  elements.userName.textContent = name;
  elements.dropdownName.textContent = name;
}

function updateCoinChip() {
  if (currentUser) {
    elements.coinBalance.textContent = formatCoins(currentUser.coins);
  }
}

function setUserMenu(open) {
  elements.userDropdown.hidden = !open;
  elements.userChip.setAttribute("aria-expanded", String(open));
}

let manageMenuOpen = false;

function setManageMenu(open) {
  if (elements.roomManage.hidden) open = false;
  manageMenuOpen = open;
  elements.manageMenu.hidden = !open;
  elements.manageButton.setAttribute("aria-expanded", String(open));
}

function setSignedIn(user) {
  currentUser = user;
  elements.loginButton.hidden = Boolean(user);
  elements.coinChip.style.display = user ? "flex" : "none";
  elements.userAvatar.style.display = user ? "flex" : "none";
  elements.userName.style.display = user ? "block" : "none";
  elements.userChip.style.display = user ? "flex" : "none";
  renderIdentity();
  setUserMenu(false);
  updateCoinChip();
  if (user) renderGameView();
  else {
    myRoom = null;
    currentGameId = null;
    hallPage = null;
    renderGameView();
  }
}


/* =========================================================
   登录
========================================================= */

function setAuthMode(mode) {
  authMode = mode;
  const isLogin = mode === "login";
  elements.authTitle.textContent = isLogin ? "登录游戏厅" : "注册账号";
  elements.authSubmit.textContent = isLogin ? "登录" : "注册";
  elements.password.autocomplete = isLogin ? "current-password" : "new-password";
  elements.inviteCode.hidden = isLogin;
  const toggle = document.createElement("button");
  toggle.className = "auth-link";
  toggle.type = "button";
  toggle.textContent = isLogin ? "注册" : "返回登录";
  elements.authSwitch.replaceChildren(
    document.createTextNode(isLogin ? "还没有账号？ " : "已经有账号？ "), toggle,
  );
}

function openLogin() {
  setAuthMode("login");
  elements.authModal.style.display = "flex";
  elements.username.focus();
}

function submitAuth() {
  const username = elements.username.value.trim();
  const password = elements.password.value;
  if (!username || !password) {
    alert("请输入用户名和密码");
    return;
  }
  send({
    type: authMode,
    username,
    password,
    ...(authMode === "register" ? { invite_code: elements.inviteCode.value.trim() } : {}),
  });
}


/* =========================================================
   财务管理
========================================================= */

function switchFinanceTab(tab) {
  const detail = tab === "detail";
  elements.financeTabDetail.classList.toggle("active", detail);
  elements.financeTabTransfer.classList.toggle("active", !detail);
  elements.financeDetailPanel.hidden = !detail;
  elements.financeTransferPanel.hidden = detail;
  elements.transferFeedback.textContent = "";
  if (!detail) TransferSelect.requestUsers();
}

function openFinance() {
  if (!currentUser) return;
  setUserMenu(false);
  switchFinanceTab("detail");
  elements.financeBalance.textContent = formatCoins(currentUser.coins);
  elements.financeList.replaceChildren();
  const loading = document.createElement("div");
  loading.className = "invite-empty";
  loading.textContent = "加载中…";
  elements.financeList.append(loading);
  elements.financeModal.style.display = "flex";
  send({ type: "get_finance" });
}

function renderFinance(data) {
  if (!currentUser) return;
  currentUser.coins = data.coins;
  updateCoinChip();
  elements.financeBalance.textContent = formatCoins(data.coins);
  const list = elements.financeList;
  list.replaceChildren();
  const items = data.transactions || [];
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "invite-empty";
    empty.textContent = "暂无金币明细";
    list.append(empty);
    return;
  }
  for (const tx of items) {
    const row = document.createElement("div");
    row.className = "finance-row";
    const info = document.createElement("div");
    const kind = document.createElement("div");
    kind.className = "finance-row-kind";
    kind.textContent = coinKinds[tx.kind] || tx.kind;
    if (tx.kind === "bet_stake" || tx.kind === "game_buyin") {
      const pending = document.createElement("span");
      pending.className = "finance-row-pending";
      pending.textContent = "未结算";
      kind.append(pending);
    }
    const detail = document.createElement("div");
    detail.className = "finance-row-detail";
    detail.textContent = [tx.detail, formatClock(tx.created_at)].filter(Boolean).join(" · ");
    info.append(kind, detail);
    const side = document.createElement("div");
    const amount = document.createElement("div");
    amount.className = `finance-row-amount ${tx.amount >= 0 ? "plus" : "minus"}`;
    amount.textContent = `${tx.amount >= 0 ? "+" : ""}${formatCoins(tx.amount)}`;
    const balance = document.createElement("div");
    balance.className = "finance-row-balance";
    balance.textContent = `余额 ${formatCoins(tx.balance)}`;
    side.append(amount, balance);
    row.append(info, side);
    list.append(row);
  }
}

function submitTransfer() {
  if (!currentUser) return;
  const to = elements.transferTo.value.trim();
  const amount = Number(elements.transferAmount.value);
  if (!to) {
    alert("请选择转账对象");
    return;
  }
  if (to === currentUser.username) {
    alert("不能转账给自己");
    return;
  }
  if (!Number.isFinite(amount) || amount <= 0) {
    alert("请输入正确的转账金额");
    return;
  }
  elements.transferFeedback.textContent = "";
  send({ type: "transfer_coins", to, amount: Math.round(amount * 100) / 100 });
}


/* =========================================================
   视图骨架
========================================================= */

function renderGameView() {
  if (!currentUser) {
    clearRoomMode();
    renderEntry();
    return;
  }
  if (myRoom) {
    renderRoom();
    return;
  }
  clearRoomMode();
  if (hallPage === "create" && currentGameId) renderCreate();
  else if (hallPage === "rooms" && currentGameId) renderGameRooms();
  else renderHall();
}

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
      currentGameId = game.id;
      hallPage = "rooms";
      renderGameView();
    });
    grid.append(card);
  }
  body.append(grid);
}

function currentGameMeta() {
  return GAME_TYPES.find((g) => g.id === currentGameId) || GAME_TYPES[0];
}

function gameMetaById(id) {
  return GAME_TYPES.find((g) => g.id === id) || GAME_TYPES[0];
}

function fillBlindOptions(select, gameId, selected) {
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
    hallPage = null;
    currentGameId = null;
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
    hallPage = "create";
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
  const rooms = hallRooms.filter((room) => !currentGameId || room.game === currentGameId);
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
    hallPage = "rooms";
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
    if (currentUser && value > currentUser.coins) {
      alert("金币不足");
      return;
    }
    send({
      type: "create_room",
      game: currentGameId,
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

function isRoomOwner() {
  return Boolean(currentUser) && myRoom.owner === currentUser.username;
}

function leaveConfirmText() {
  if (isRoomOwner()) {
    return myRoom.status === "playing"
      ? "确定流局？牌局结束，所有人按当前筹码退回金币。"
      : "解散房间并退还所有人的买入？";
  }
  return "退出房间并取回当前筹码？";
}

function setRoomMode() {
  elements.gameHeader.classList.add("in-room");
  elements.roomTopbar.hidden = false;
  elements.roomTopName.textContent = myRoom.name;
  const showManage = isRoomOwner() && myRoom.status === "playing" && !myRoom.settlement;
  elements.roomManage.hidden = !showManage;
  setManageMenu(manageMenuOpen && showManage);
  elements.managePauseButton.textContent = myRoom.paused ? "继续" : "暂停";
}

function clearRoomMode() {
  elements.gameHeader.classList.remove("in-room");
  elements.roomTopbar.hidden = true;
  setManageMenu(false);
}

function leaveRoom() {
  if (confirm(leaveConfirmText())) send({ type: "leave_room" });
}

function renderRoom() {
  setRoomMode();
  if (myRoom.status === "playing") {
    if (myRoom.settlement) renderSettlementView();
    else if (myRoom.game_type === "uno") renderUnoTable();
    else renderPokerTable();
  } else renderRoomLobby();
}

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
  const rows = roomChat.map((m) => roomChatRowNode(m));
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
  const text = (input?.value || roomChatDraft).trim();
  if (!text) return;
  if (send({ type: "room_chat", text })) {
    roomChatDraft = "";
    if (input) input.value = "";
  }
}

function chatOpenButton() {
  const wrap = document.createElement("div");
  wrap.className = "chat-open-row";
  const btn = document.createElement("button");
  btn.className = "dock-chat-toggle";
  btn.type = "button";
  btn.textContent = `💬 房间聊天（${roomChat.length}）`;
  btn.addEventListener("click", openChatOverlay);
  wrap.append(btn);
  return wrap;
}

function showSeatBubble(username, text) {
  if (!myRoom) return;
  seatBubbles.set(username, { text: text.length > 60 ? `${text.slice(0, 60)}…` : text, until: Date.now() + 3000 });
  applySeatBubble(username);
  window.setTimeout(() => {
    const bubble = seatBubbles.get(username);
    if (bubble && bubble.until <= Date.now()) {
      seatBubbles.delete(username);
      if (!myRoom) return;
      const idx = myRoom.players.findIndex((p) => p.username === username);
      if (idx >= 0) removeSeatBubble(seatNodeByIndex(idx));
    }
  }, 3100);
}

function seatNodeByIndex(index) {
  const seatSelector = myRoom.game_type === "uno"
    ? `#gameMain .uno-seats .uno-seat:nth-child(${index + 1})`
    : `#gameMain .poker-seats .seat:nth-child(${index + 1})`;
  return document.querySelector(seatSelector);
}

function applySeatBubble(username) {
  if (!myRoom) return;
  const index = myRoom.players.findIndex((p) => p.username === username);
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

function renderRoomLobby() {
  stopHallTicker();
  const body = elements.gameMain;
  body.replaceChildren();
  const meta = gameMetaById(myRoom.game_type);

  const page = document.createElement("div");
  page.className = "game-card-page";
  body.append(page);

  const info = document.createElement("div");
  info.className = "game-hint";
  info.style.marginTop = "0";
  info.textContent = `${meta.name} · ${myRoom.game_type === "uno" ? "每张赔付" : "小盲注"} ${myRoom.blind} · 买入 ${formatCoins(myRoom.buy_in)} · 房主 ${myRoom.owner_name}`;
  page.append(info);

  const title = document.createElement("div");
  title.className = "hall-section-title";
  title.textContent = `等待玩家加入（${myRoom.players.length}）`;
  page.append(title);

  const list = document.createElement("div");
  list.className = "game-players";
  for (const p of myRoom.players) {
    const row = document.createElement("div");
    row.className = "game-player-row";
    const name = document.createElement("span");
    name.textContent = p.nickname;
    if (p.username === myRoom.owner) {
      const badge = document.createElement("span");
      badge.className = "badge-owner";
      badge.textContent = "房主";
      name.append(badge);
    }
    if (currentUser && p.username === currentUser.username) {
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
    start.disabled = myRoom.players.filter((p) => p.stack > 0).length < 2;
    start.addEventListener("click", () => send({ type: "start_game" }));
    page.append(start);
  }

  const hint = document.createElement("div");
  hint.className = "game-hint";
  hint.textContent = isRoomOwner()
    ? "满 2 名有筹码的玩家即可开局。开局后可在顶部「管理」中流局、暂停或重新开始。"
    : myRoom.game_type === "uno"
      ? "等待房主开局。中途退出会自动离局，当前筹码原封退回。"
      : "等待房主开局。中途退出会自动弃牌，已投入的筹码留在底池。";
  page.append(hint);

  body.append(chatOpenButton());
}

function seatNode(p) {
  const seat = document.createElement("div");
  seat.className = "seat";
  if (myRoom.to_act === p.username) seat.classList.add("active");
  if (p.folded) seat.classList.add("folded");
  if (currentUser && p.username === currentUser.username) seat.classList.add("me");
  const name = document.createElement("div");
  name.className = "seat-name";
  name.textContent = p.nickname;
  if (p.dealer) {
    const chip = document.createElement("span");
    chip.className = "dchip";
    chip.textContent = "D";
    name.append(chip);
  }
  const stack = document.createElement("div");
  stack.className = "seat-stack";
  stack.textContent = formatCoins(p.stack);
  const bet = document.createElement("div");
  bet.className = "seat-bet";
  bet.textContent = p.bet ? `+${formatCoins(p.bet)}` : "";
  const status = document.createElement("div");
  status.className = "seat-status";
  if (p.folded) {
    status.textContent = "弃牌";
    status.classList.add("fold");
  } else if (p.allin) {
    status.textContent = "全下";
    status.classList.add("allin");
  } else if (myRoom.to_act === p.username) {
    status.textContent = "思考中…";
    status.classList.add("think");
  } else {
    status.textContent = p.in_hand ? "" : "观战";
  }
  seat.append(name, stack, bet, status);
  return seat;
}

function startHallTicker(fill, seconds) {
  stopHallTicker();
  hallDeadlineAt = Date.now() + seconds * 1000;
  const update = () => {
    const left = Math.max(0, hallDeadlineAt - Date.now());
    fill.style.width = `${Math.max(0, Math.min(100, (left / (seconds * 1000)) * 100))}%`;
    if (left <= 0) stopHallTicker();
  };
  update();
  hallTimer = window.setInterval(update, 500);
}

function stopHallTicker() {
  if (hallTimer) {
    window.clearInterval(hallTimer);
    hallTimer = 0;
  }
}

function actionBarNode(options) {
  const me = myRoom.players.find((p) => p.username === currentUser?.username);
  const bar = document.createElement("div");
  bar.className = "action-bar";
  const act = (payload) => send({ type: "poker_action", ...payload });

  const fold = document.createElement("button");
  fold.className = "action-btn danger";
  fold.type = "button";
  fold.textContent = "弃牌";
  fold.addEventListener("click", () => act({ action: "fold" }));
  bar.append(fold);

  if (options.check) {
    const check = document.createElement("button");
    check.className = "action-btn";
    check.type = "button";
    check.textContent = "看牌";
    check.addEventListener("click", () => act({ action: "check" }));
    bar.append(check);
  }
  if (options.call) {
    const call = document.createElement("button");
    call.className = "action-btn primary";
    call.type = "button";
    call.textContent = options.call_amount >= (me?.stack || 0)
      ? `全下跟注 ${formatCoins(options.call_amount)}`
      : `跟注 ${formatCoins(options.call_amount)}`;
    call.addEventListener("click", () => act({ action: "call" }));
    bar.append(call);
  }
  if (options.can_raise) {
    const input = document.createElement("input");
    input.className = "raise-input";
    input.type = "number";
    input.inputMode = "decimal";
    input.min = String(options.raise_min);
    input.max = String(options.raise_max);
    input.step = "1";
    input.value = String(options.raise_min);
    bar.append(input);
    const raise = document.createElement("button");
    raise.className = "action-btn primary";
    raise.type = "button";
    raise.textContent = "加注到";
    raise.addEventListener("click", () => {
      let value = Number(input.value);
      if (!Number.isFinite(value)) return;
      value = Math.round(
        Math.min(Math.max(value, options.raise_min), options.raise_max) * 100,
      ) / 100;
      act({ action: "raise", raise_to: value });
    });
    bar.append(raise);
  }
  if (options.allin) {
    const allin = document.createElement("button");
    allin.className = "action-btn danger";
    allin.type = "button";
    allin.textContent = `全下 ${formatCoins(options.allin_to)}`;
    allin.addEventListener("click", () => act({ action: "raise", raise_to: options.allin_to }));
    bar.append(allin);
  }
  return bar;
}

function resultNode(result) {
  const box = document.createElement("div");
  box.className = "poker-result";
  for (const item of result.reveal || []) {
    requestProfile(item.username);
    const row = document.createElement("div");
    row.className = "poker-result-row";
    const left = document.createElement("span");
    left.textContent = item.hand_name
      ? `${displayNameOf(item.username)} · ${item.hand_name}`
      : displayNameOf(item.username);
    const cards = document.createElement("span");
    cards.className = "reveal-cards";
    for (const c of item.cards) cards.append(cardNode(c, { settled: true }));
    row.append(left, cards);
    box.append(row);
  }
  for (const [username, amount] of Object.entries(result.payouts || {})) {
    if (amount <= 0) continue;
    requestProfile(username);
    const row = document.createElement("div");
    row.className = "poker-result-row";
    const left = document.createElement("span");
    left.textContent = `${displayNameOf(username)} 收取底池`;
    const right = document.createElement("span");
    right.className = "win";
    right.textContent = `+${formatCoins(amount)}`;
    row.append(left, right);
    box.append(row);
  }
  return box;
}

function cardNode(card, opts = {}) {
  const node = document.createElement("span");
  node.className = `pcard${card.s === 1 || card.s === 2 ? " red" : ""}${opts.big ? " big" : ""}`;
  if (opts.settled) node.style.animation = "none";
  else if (opts.delay) node.style.animationDelay = `${opts.delay}ms`;
  const rank = document.createElement("span");
  rank.className = "pc-rank";
  rank.textContent = RANK_CHARS[card.r] || String(card.r);
  const suit = document.createElement("span");
  suit.className = "pc-suit";
  suit.textContent = SUIT_CHARS[card.s];
  node.append(rank, suit);
  return node;
}

function renderSettlementView() {
  const body = elements.gameMain;
  body.replaceChildren();

  const heading = document.createElement("div");
  heading.className = "hall-page-title";
  heading.textContent = `${myRoom.name} · 本局结算`;
  body.append(heading);

  const resultCard = document.createElement("div");
  resultCard.className = "game-card-page";
  if (myRoom.result) {
    resultCard.append(myRoom.game_type === "uno"
      ? unoResultNode(myRoom.result)
      : resultNode(myRoom.result));
  } else {
    const note = document.createElement("div");
    note.className = "game-hint";
    note.style.marginTop = "0";
    note.textContent = "牌局已结束。";
    resultCard.append(note);
  }
  body.append(resultCard);

  const settlement = myRoom.settlement;
  const votes = settlement?.votes || {};
  const total = settlement?.total || myRoom.players.length;
  const nextCount = Object.values(votes).filter((v) => v.choice === "next").length;
  const dissolveCount = Object.values(votes).filter((v) => v.choice === "dissolve").length;
  const myChoice = currentUser ? votes[currentUser.username]?.choice : null;

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
  const isUno = myRoom.game_type === "uno";
  const blindRow = document.createElement("div");
  blindRow.className = "settle-blind-row";
  const blindLabel = document.createElement("span");
  blindLabel.className = "settle-blind-label";
  blindLabel.textContent = isUno ? "下一局底注" : "下一局盲注";
  const blind = document.createElement("select");
  blind.className = "login-input";
  blind.id = "settleBlindSelect";
  fillBlindOptions(blind, myRoom.game_type, settlement?.blind || myRoom.blind);
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
    : isUno
      ? "有玩家筹码已输光，过半数投「解散」后房间将按当前筹码退还所有人。"
      : "有玩家筹码不足下一局门槛（20 倍小盲注），过半数投「解散」后房间将按当前筹码退还所有人。";
  voteCard.append(hint);
  body.append(voteCard);

  body.append(chatOpenButton());
}

function renderPokerTable() {
  const body = elements.gameMain;
  body.replaceChildren();

  const wrap = document.createElement("div");
  wrap.className = "poker-page";
  body.append(wrap);

  const table = document.createElement("div");
  table.className = "poker-table";

  const topbar = document.createElement("div");
  topbar.className = "poker-topbar";
  const left = document.createElement("span");
  left.textContent = `第 ${myRoom.hand_no || "-"} 手 · 盲注 ${myRoom.blind}/${myRoom.blind * 2}`;
  const right = document.createElement("span");
  right.textContent = myRoom.paused ? "⏸ 已暂停" : (STAGE_NAMES[myRoom.stage] || "");
  topbar.append(left, right);
  table.append(topbar);

  // 状态栏：最新状态变化一目了然
  const status = document.createElement("div");
  status.className = "poker-status";
  const la = myRoom.last_action;
  status.textContent = la
    ? `${la.nickname} ${la.text}`
    : myRoom.to_act
      ? `等待 ${displayNameOf(myRoom.to_act)} 行动…`
      : "发牌中…";
  table.append(status);

  const pot = document.createElement("div");
  pot.className = "poker-pot";
  pot.textContent = myRoom.pot ? `底池 ${formatCoins(myRoom.pot)}` : "";
  table.append(pot);

  const board = document.createElement("div");
  board.className = "poker-board";
  const cards = myRoom.board || [];
  if (!cards.length) hallBoardCount = 0;
  for (let i = 0; i < 5; i += 1) {
    if (i < cards.length) {
      const opts = {};
      if (i >= hallBoardCount) opts.delay = (i - hallBoardCount) * 140;
      else opts.settled = true;
      board.append(cardNode(cards[i], opts));
    } else {
      const slot = document.createElement("div");
      slot.className = "pcard-slot";
      board.append(slot);
    }
  }
  hallBoardCount = cards.length;
  table.append(board);

  const seats = document.createElement("div");
  seats.className = "poker-seats";
  for (const p of myRoom.players) seats.append(seatNode(p));
  table.append(seats);

  if (myRoom.result) table.append(resultNode(myRoom.result));

  if (myRoom.paused) {
    const overlay = document.createElement("div");
    overlay.className = "paused-overlay";
    overlay.textContent = "⏸ 牌局已暂停，等待房主继续";
    table.append(overlay);
  }
  wrap.append(table);

  const dock = document.createElement("div");
  dock.className = "poker-dock";
  const dockHead = document.createElement("div");
  dockHead.className = "dock-head";
  const label = document.createElement("div");
  label.className = "my-cards-label";
  label.textContent = "你的手牌";
  const chatToggle = document.createElement("button");
  chatToggle.className = "dock-chat-toggle";
  chatToggle.type = "button";
  chatToggle.textContent = "💬 聊天";
  chatToggle.addEventListener("click", openChatOverlay);
  dockHead.append(label, chatToggle);
  dock.append(dockHead);
  const myCards = document.createElement("div");
  myCards.className = "my-cards";
  const holeKey = myRoom.your_hole ? JSON.stringify(myRoom.your_hole) : "";
  if (myRoom.your_hole) {
    const fresh = holeKey !== lastHoleKey;
    myCards.append(cardNode(myRoom.your_hole[0], { big: true, settled: !fresh }));
    myCards.append(cardNode(myRoom.your_hole[1], { big: true, settled: !fresh, delay: fresh ? 120 : 0 }));
  } else {
    lastHoleKey = "";
    const waiting = document.createElement("span");
    waiting.className = "my-cards-label";
    waiting.textContent = "等待下一手发牌…";
    myCards.append(waiting);
  }
  lastHoleKey = holeKey;
  dock.append(myCards);

  const isMyTurn = Boolean(currentUser) && myRoom.to_act === currentUser.username;
  const countdown = document.createElement("div");
  countdown.className = "countdown";
  const fill = document.createElement("div");
  fill.className = "countdown-fill";
  countdown.append(fill);
  dock.append(countdown);

  if (!myRoom.paused) {
    if (isMyTurn && myRoom.your_options) {
      dock.append(actionBarNode(myRoom.your_options));
      if (myRoom.turn_left > 0) startHallTicker(fill, myRoom.turn_left);
    }
  } else {
    const pausedNote = document.createElement("div");
    pausedNote.className = "last-action";
    pausedNote.textContent = "牌局已暂停";
    dock.append(pausedNote);
  }
  wrap.append(dock);

  for (const username of seatBubbles.keys()) applySeatBubble(username);
}

function openChatOverlay() {
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
  input.value = roomChatDraft;
  input.autocomplete = "off";
  input.addEventListener("input", () => { roomChatDraft = input.value; });
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

function closeChatOverlay() {
  document.getElementById("chatOverlay")?.remove();
}


/* =========================================================
   UNO 牌桌
========================================================= */

let pendingWildCard = null;   // 已点选、等待选色的万能牌下标
let unoActionLock = false;    // 出牌/摸牌后到下一帧视图前忽略重复点击

function unoAct(payload) {
  if (unoActionLock) return;
  unoActionLock = true;
  send({ type: "poker_action", ...payload });
}

function isMyTurn() {
  return Boolean(currentUser) && myRoom.to_act === currentUser.username;
}

function unoMatches(card, active) {
  if (!active) return false;
  if (card.c === "w") return true;
  return card.c === active.c || card.v === active.v;
}

function unoCardNode(card, opts = {}) {
  const node = document.createElement("span");
  node.className = `ucard${opts.back ? " back" : ` ${card.c}`}${opts.big ? " big" : ""}`;
  if (opts.tint && UNO_COLOR_TEXT[opts.tint]) {
    node.style.boxShadow = `0 0 0 3px ${UNO_COLOR_TEXT[opts.tint]}, 0 8px 18px rgba(0,0,0,.3)`;
  }
  if (opts.back) {
    const logo = document.createElement("span");
    logo.className = "uc-back-logo";
    logo.textContent = "UNO";
    node.append(logo);
    return node;
  }
  const glyph = UNO_VALUE_GLYPHS[card.v] || card.v;
  const top = document.createElement("span");
  top.className = "uc-corner";
  top.textContent = glyph;
  const mid = document.createElement("span");
  mid.className = "uc-mid";
  mid.textContent = glyph;
  const bottom = document.createElement("span");
  bottom.className = "uc-corner uc-flip";
  bottom.textContent = glyph;
  node.append(top, mid, bottom);
  return node;
}

function unoSeatNode(p) {
  const seat = document.createElement("div");
  seat.className = "uno-seat";
  if (myRoom.status === "playing" && myRoom.to_act === p.username) {
    seat.classList.add("active");
  }
  if (currentUser && p.username === currentUser.username) seat.classList.add("me");
  const name = document.createElement("div");
  name.className = "us-name";
  name.textContent = p.nickname;
  const info = document.createElement("div");
  info.className = "us-info";
  const stack = document.createElement("span");
  stack.className = "us-stack";
  stack.textContent = formatCoins(p.stack);
  const count = document.createElement("span");
  count.className = "us-count";
  count.textContent = myRoom.status === "playing"
    ? (p.in_hand ? `🂠 ${p.cards}` : "观战")
    : `${formatCoins(p.stack)} 筹码`;
  info.append(stack, count);
  const uno = document.createElement("div");
  uno.className = "us-uno";
  uno.textContent = "UNO!";
  if (p.in_hand && p.cards === 1) uno.classList.add("show");
  seat.append(name, info, uno);
  return seat;
}

function unoResultNode(result) {
  const box = document.createElement("div");
  box.className = "poker-result";
  const total = Object.values(result.payouts || {}).reduce((sum, n) => sum + n, 0);
  if (result.winner) {
    requestProfile(result.winner);
    const head = document.createElement("div");
    head.className = "poker-result-row";
    const left = document.createElement("span");
    left.textContent = `🏆 ${displayNameOf(result.winner)} 先出完`;
    const right = document.createElement("span");
    right.className = "win";
    right.textContent = total ? `+${formatCoins(total)}` : "";
    head.append(left, right);
    box.append(head);
  }
  for (const [username, amount] of Object.entries(result.payouts || {})) {
    requestProfile(username);
    const row = document.createElement("div");
    row.className = "poker-result-row";
    const left = document.createElement("span");
    left.textContent = `${displayNameOf(username)} 剩 ${result.penalties?.[username] ?? "?"} 张`;
    const right = document.createElement("span");
    right.textContent = `-${formatCoins(amount)}`;
    row.append(left, right);
    box.append(row);
  }
  const reveal = document.createElement("div");
  reveal.className = "uno-reveal";
  for (const [username, cards] of Object.entries(result.cards || {})) {
    requestProfile(username);
    if (!cards.length) continue;
    const line = document.createElement("div");
    line.className = "uno-reveal-row";
    const name = document.createElement("span");
    name.className = "uno-reveal-name";
    name.textContent = displayNameOf(username);
    const cardsBox = document.createElement("span");
    cardsBox.className = "uno-reveal-cards";
    for (const card of cards) cardsBox.append(unoCardNode(card));
    line.append(name, cardsBox);
    reveal.append(line);
  }
  box.append(reveal);
  return box;
}

function unoActionBarNode() {
  const bar = document.createElement("div");
  bar.className = "action-bar";
  const options = myRoom.your_options || {};
  const act = (payload) => unoAct(payload);

  if (options.draw) {
    const draw = document.createElement("button");
    draw.className = "action-btn primary";
    draw.type = "button";
    draw.textContent = "摸一张";
    draw.addEventListener("click", () => act({ action: "draw" }));
    bar.append(draw);
  }
  if (options.pass) {
    const pass = document.createElement("button");
    pass.className = "action-btn danger";
    pass.type = "button";
    pass.textContent = "保留摸牌 · 跳过";
    pass.addEventListener("click", () => {
      pendingWildCard = null;
      act({ action: "pass" });
    });
    bar.append(pass);
  }
  if (options.uno) {
    const uno = document.createElement("button");
    uno.className = "action-btn primary uno-btn";
    uno.type = "button";
    uno.textContent = "UNO!";
    uno.addEventListener("click", () => act({ action: "uno" }));
    bar.append(uno);
  }

  // 万能牌选色条：点选万能牌后出现
  if (pendingWildCard !== null) {
    const picker = document.createElement("div");
    picker.className = "uno-color-picker";
    const label = document.createElement("span");
    label.className = "uno-color-label";
    label.textContent = "选颜色：";
    picker.append(label);
    for (const color of UNO_COLORS) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `uno-color-dot ${color}`;
      btn.title = UNO_COLOR_NAMES[color];
      btn.addEventListener("click", () => {
        const index = pendingWildCard;
        pendingWildCard = null;
        act({ action: "play", card: index, color });
      });
      picker.append(btn);
    }
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "uno-color-cancel";
    cancel.textContent = "✕";
    cancel.addEventListener("click", () => {
      pendingWildCard = null;
      renderGameView();
    });
    picker.append(cancel);
    bar.append(picker);
  }
  return bar;
}

function renderUnoTable() {
  const body = elements.gameMain;
  unoActionLock = false;
  body.replaceChildren();

  const wrap = document.createElement("div");
  wrap.className = "poker-page";
  body.append(wrap);

  const table = document.createElement("div");
  table.className = "uno-table";

  const topbar = document.createElement("div");
  topbar.className = "poker-topbar";
  const left = document.createElement("span");
  left.textContent = `第 ${myRoom.hand_no || "-"} 局 · 每张赔付 ${myRoom.blind}`;
  const right = document.createElement("span");
  right.textContent = myRoom.paused
    ? "⏸ 已暂停"
    : `方向 ${myRoom.direction === -1 ? "↺" : "↻"}`;
  topbar.append(left, right);
  table.append(topbar);

  const status = document.createElement("div");
  status.className = "poker-status";
  const la = myRoom.last_action;
  status.textContent = la
    ? `${la.nickname} ${la.text}`
    : myRoom.to_act
      ? `等待 ${displayNameOf(myRoom.to_act)} 出牌…`
      : "发牌中…";
  table.append(status);

  const seats = document.createElement("div");
  seats.className = "uno-seats";
  for (const p of myRoom.players) seats.append(unoSeatNode(p));
  table.append(seats);

  const center = document.createElement("div");
  center.className = "uno-center";
  const active = myRoom.active;
  if (active?.card) {
    const myTurn = isMyTurn();
    const drawPile = document.createElement("div");
    drawPile.className = "uno-pile";
    drawPile.append(unoCardNode(null, { big: true, back: true }));
    const deckLeft = document.createElement("span");
    deckLeft.className = "uno-deck-count";
    deckLeft.textContent = `牌堆 ${myRoom.deck_left ?? 0}`;
    drawPile.append(deckLeft);
    if (myTurn && myRoom.your_options?.draw) {
      drawPile.classList.add("clickable");
      drawPile.addEventListener("click", () => {
        unoAct({ action: "draw" });
      });
    }

    const discard = document.createElement("div");
    discard.className = "uno-discard";
    discard.append(unoCardNode(active.card, {
      big: true,
      tint: active.card.c === "w" ? active.c : null,
    }));

    const strip = document.createElement("div");
    strip.className = "uno-color-strip";
    strip.style.background = UNO_COLOR_TEXT[active.c] || "#3a3a3c";
    strip.textContent = UNO_COLOR_NAMES[active.c]
      ? `当前颜色 ${UNO_COLOR_NAMES[active.c]}`
      : "";
    center.append(drawPile, discard, strip);
  }
  table.append(center);

  if (myRoom.result) table.append(unoResultNode(myRoom.result));

  if (myRoom.paused) {
    const overlay = document.createElement("div");
    overlay.className = "paused-overlay";
    overlay.textContent = "⏸ 牌局已暂停，等待房主继续";
    table.append(overlay);
  }
  wrap.append(table);

  const dock = document.createElement("div");
  dock.className = "poker-dock";
  const dockHead = document.createElement("div");
  dockHead.className = "dock-head";
  const label = document.createElement("div");
  label.className = "my-cards-label";
  label.textContent = isMyTurn() ? "你的手牌 · 轮到你出牌" : "你的手牌";
  const chatToggle = document.createElement("button");
  chatToggle.className = "dock-chat-toggle";
  chatToggle.type = "button";
  chatToggle.textContent = "💬 聊天";
  chatToggle.addEventListener("click", openChatOverlay);
  dockHead.append(label, chatToggle);
  dock.append(dockHead);

  const myCards = document.createElement("div");
  myCards.className = "uno-hand";
  const hand = myRoom.your_hand || [];
  const options = myRoom.your_options || {};
  if (!hand.length) {
    const waiting = document.createElement("span");
    waiting.className = "my-cards-label";
    waiting.textContent = "等待下一局发牌…";
    myCards.append(waiting);
  }
  const drawnOnly = options.pass && myRoom.your_drawn != null;
  hand.forEach((card, index) => {
    const playable = isMyTurn() && !myRoom.paused
      && (!drawnOnly || index === myRoom.your_drawn)
      && unoMatches(card, myRoom.active);
    const node = unoCardNode(card, {});
    if (drawnOnly && index === myRoom.your_drawn) node.classList.add("drawn");
    if (pendingWildCard === index) node.classList.add("picked");
    if (playable) {
      node.classList.add("playable");
      node.addEventListener("click", () => {
        if (card.c === "w") {
          pendingWildCard = index;
          renderGameView();
          return;
        }
        pendingWildCard = null;
        unoAct({ action: "play", card: index });
      });
    }
    myCards.append(node);
  });
  dock.append(myCards);

  const countdown = document.createElement("div");
  countdown.className = "countdown";
  const fill = document.createElement("div");
  fill.className = "countdown-fill";
  countdown.append(fill);
  dock.append(countdown);

  if (!myRoom.paused) {
    if (isMyTurn() || options.uno || pendingWildCard !== null) {
      dock.append(unoActionBarNode());
      if (isMyTurn() && myRoom.turn_left > 0) startHallTicker(fill, myRoom.turn_left);
    }
  } else {
    const pausedNote = document.createElement("div");
    pausedNote.className = "last-action";
    pausedNote.textContent = "牌局已暂停";
    dock.append(pausedNote);
  }
  wrap.append(dock);

  for (const username of seatBubbles.keys()) applySeatBubble(username);
}


/* =========================================================
   事件绑定
========================================================= */

elements.loginButton.addEventListener("click", openLogin);
elements.authSubmit.addEventListener("click", submitAuth);
elements.authSwitch.addEventListener("click", () => setAuthMode(authMode === "login" ? "register" : "login"));
elements.userChip.addEventListener("click", () => setUserMenu(elements.userDropdown.hidden));
elements.financeButton.addEventListener("click", openFinance);
elements.coinChip.addEventListener("click", openFinance);
elements.financeClose.addEventListener("click", () => {
  elements.financeModal.style.display = "none";
});
elements.financeModal.addEventListener("click", (event) => {
  if (event.target === elements.financeModal) elements.financeModal.style.display = "none";
});
elements.financeTabDetail.addEventListener("click", () => switchFinanceTab("detail"));
elements.financeTabTransfer.addEventListener("click", () => switchFinanceTab("transfer"));
elements.transferSubmit.addEventListener("click", submitTransfer);
elements.transferAmount.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.isComposing) submitTransfer();
});
elements.logoutButton.addEventListener("click", () => {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (token) send({ type: "logout", token });
  localStorage.removeItem(AUTH_TOKEN_KEY);
  setSignedIn(null);
});
elements.leaveRoomButton.addEventListener("click", leaveRoom);
elements.manageButton.addEventListener("click", () => {
  setManageMenu(elements.manageMenu.hidden);
});
elements.manageDrawButton.addEventListener("click", () => {
  setManageMenu(false);
  if (confirm("确定流局？牌局结束，所有人按当前筹码退回金币。")) {
    send({ type: "leave_room" });
  }
});
elements.managePauseButton.addEventListener("click", () => {
  setManageMenu(false);
  send({ type: "pause_game", paused: !myRoom.paused });
});
elements.manageRestartButton.addEventListener("click", () => {
  setManageMenu(false);
  const detail = myRoom?.game_type === "uno"
    ? "确定重新开始？将收回本局所有手牌并重新发牌。"
    : "确定重新开始？本手已投注的筹码将退回各家，并重新发牌。";
  if (confirm(detail)) {
    send({ type: "restart_game" });
  }
});
document.addEventListener("click", (event) => {
  if (!elements.userArea.contains(event.target)) setUserMenu(false);
  if (!elements.roomManage.contains(event.target)) setManageMenu(false);
});
elements.password.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.isComposing) submitAuth();
});
elements.authModal.addEventListener("click", (event) => {
  if (event.target === elements.authModal) elements.authModal.style.display = "none";
});
window.addEventListener("beforeunload", () => {
  clearTimeout(reconnectTimer);
  stopHallTicker();
  closeChatOverlay();
});

TransferSelect.init(
  {
    toggle: $("transferSelectToggle"),
    menu: $("transferSelectMenu"),
    list: $("transferSelectList"),
    hidden: $("transferTo"),
  },
  () => send({ type: "list_users" }),
  () => currentUser?.username,
);
connectGame();
