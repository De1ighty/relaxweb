"use strict";

const $ = (id) => document.getElementById(id);
const elements = {
  authModal: $("loginModal"), authSubmit: $("authSubmit"), authSwitch: $("authSwitch"),
  avatarButton: $("avatarButton"), avatarFallback: $("avatarFallback"),
  avatarFile: $("avatarFile"), avatarPreview: $("avatarPreview"), avatarReset: $("avatarReset"),
  authTitle: $("authTitle"), chatCard: $("chatCard"), chatInput: $("chatInput"),
  chatStatus: $("chatStatus"), danmakuComposer: $("danmakuComposer"),
  danmakuLayer: $("danmakuLayer"), danmakuToggle: $("danmakuToggle"),
  deleteAccountButton: $("deleteAccountButton"), deleteCancel: $("deleteCancel"),
  deleteModal: $("deleteModal"), deletePassword: $("deletePassword"),
  deleteSubmit: $("deleteSubmit"), dropdownName: $("dropdownName"),
  fullscreenButton: $("fullscreenButton"), inviteButton: $("inviteButton"),
  inviteClose: $("inviteClose"), inviteCreate: $("inviteCreate"),
  inviteCode: $("inviteCode"), inviteList: $("inviteList"),
  inviteModal: $("inviteModal"),
  leftHeader: $("leftHeader"), loginButton: $("loginButton"),
  logoutButton: $("logoutButton"), messages: $("messages"),
  muteToggle: $("muteToggle"),
  nicknameInput: $("nicknameInput"), onlineNumber: $("onlineNumber"),
  onlinePopover: $("onlinePopover"), onlinePopoverCount: $("onlinePopoverCount"),
  onlinePopoverList: $("onlinePopoverList"), onlineStat: $("onlineStat"),
  password: $("password"), player: $("player"),
  playerMessage: $("playerMessage"), playerTools: $("playerTools"),
  playToggle: $("playToggle"), profileButton: $("profileButton"),
  profileModal: $("profileModal"), profileSubmit: $("profileSubmit"),
  sendButton: $("sendButton"),
  streamVideo: $("streamVideo"), userArea: $("userArea"), userAvatar: $("userAvatar"),
  userChip: $("userChip"), userDropdown: $("userDropdown"), userName: $("userName"),
  username: $("username"), volumeSlider: $("volumeSlider"),
};

const roles = {
  streamer: { icon: "👑 ", className: "streamer" },
  admin: { icon: "🛡 ", className: "admin" },
  user: { icon: "", className: "" },
};
const danmaku = {
  enabled: localStorage.getItem("danmakuEnabled") !== "false",
  queue: [], busyUntil: [], timer: 0,
  trackHeight: 34, topReserved: 58, bottomReserved: 72, speed: 125, gap: 45,
};

const AUTH_TOKEN_KEY = "liveAuthToken";
const CONTROLS_HIDE_DELAY = 2500;
const profiles = new Map();
const pendingProfiles = new Set();
let authMode = "login";
let currentUser = null;
let socket = null;
let reconnectTimer = 0;
let streamReader = null;
let streamReconnectTimer = 0;
let controlsHideTimer = 0;
let pendingAvatar;
let chatHeightObserver = null;

function roleInfo(role) {
  return roles[role] || roles.user;
}

function setPlayerMessage(message) {
  elements.playerMessage.textContent = message;
  elements.playerMessage.hidden = !message;
}

function describeButton(button, label) {
  button.title = label;
  button.setAttribute("aria-label", label);
}

function updatePlaybackButton() {
  const paused = elements.streamVideo.paused;
  elements.playToggle.textContent = paused ? "▶" : "⏸";
  describeButton(elements.playToggle, paused ? "播放" : "暂停");
}

function updateMuteButton() {
  const muted = elements.streamVideo.muted;
  elements.muteToggle.textContent = muted ? "🔇" : "🔊";
  elements.muteToggle.classList.toggle("active", !muted);
  elements.volumeSlider.value = String(elements.streamVideo.volume);
  describeButton(elements.muteToggle, muted ? "开启声音" : "静音");
}

function updateFullscreenButton() {
  const fullscreen = document.fullscreenElement === elements.player;
  elements.fullscreenButton.textContent = fullscreen ? "⤡" : "⤢";
  describeButton(elements.fullscreenButton, fullscreen ? "退出全屏" : "进入全屏");
}

function setVolume() {
  elements.streamVideo.volume = Number(elements.volumeSlider.value);
  elements.streamVideo.muted = elements.streamVideo.volume === 0;
  updateMuteButton();
}

function connectStream() {
  clearTimeout(streamReconnectTimer);
  streamReader?.close();
  streamReader = null;
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (!currentUser || !token) {
    setPlayerMessage("登录后观看直播");
    return;
  }
  const protocol = location.protocol === "https:" ? "https:" : "http:";
  streamReader = new MediaMTXWebRTCReader({
    url: `${protocol}//${location.hostname}:8889/xiaopang/whep`,
    user: currentUser.username,
    pass: token,
    onError: () => {
      setPlayerMessage("等待直播信号…");
      streamReconnectTimer = window.setTimeout(connectStream, 3000);
    },
    onTrack: (event) => {
      setPlayerMessage("");
      elements.streamVideo.srcObject = event.streams[0];
      elements.streamVideo.play().catch(() => setPlayerMessage("点击播放以开始观看"));
    },
    onDataChannel: () => {},
  });
}

async function togglePlayback() {
  if (elements.streamVideo.paused) {
    try {
      await elements.streamVideo.play();
      setPlayerMessage("");
    } catch {
      setPlayerMessage("暂时无法播放直播");
    }
  } else {
    elements.streamVideo.pause();
  }
}

function toggleMute() {
  if (elements.streamVideo.muted && elements.streamVideo.volume === 0) {
    elements.streamVideo.volume = 0.5;
  }
  elements.streamVideo.muted = !elements.streamVideo.muted;
  updateMuteButton();
}

function showPlayerControls() {
  clearTimeout(controlsHideTimer);
  elements.player.classList.remove("controls-hidden");
  if (document.fullscreenElement === elements.player) {
    controlsHideTimer = window.setTimeout(() => {
      if (document.activeElement !== elements.chatInput) {
        elements.player.classList.add("controls-hidden");
      }
    }, CONTROLS_HIDE_DELAY);
  }
}

function syncComposerPosition() {
  const fullscreen = document.fullscreenElement === elements.player;
  const mobile = window.matchMedia("(max-width: 1000px)").matches;
  elements.danmakuComposer.classList.toggle("in-player-controls", fullscreen);
  elements.danmakuComposer.classList.toggle("at-chat-top", !fullscreen && mobile);

  // 手机软键盘弹出/收起会触发 resize；输入框已在目标位置时绝不能再移动它，
  // 否则正在聚焦的输入框会失焦，输入法立即收起，导致无法发送弹幕。
  const composer = elements.danmakuComposer;
  const targetParent = fullscreen ? elements.playerTools : elements.chatCard;
  const targetBefore = fullscreen
    ? elements.playerTools.querySelector(".player-tools-right")
    : mobile ? elements.messages : null;
  if (composer.parentElement === targetParent
    && composer.nextElementSibling === targetBefore) {
    return;
  }

  const refocus = document.activeElement === elements.chatInput;
  if (targetBefore) targetParent.insertBefore(composer, targetBefore);
  else targetParent.append(composer);
  if (refocus) elements.chatInput.focus({ preventScroll: true });
}

function handleFullscreenChange() {
  clearTimeout(controlsHideTimer);
  elements.player.classList.remove("controls-hidden");
  syncComposerPosition();
  updateFullscreenButton();
  showPlayerControls();
}

function syncChatHeight() {
  elements.chatCard.style.height = "";
}

function setConnectionStatus(text) {
  elements.chatStatus.textContent = `● ${text}`;
}

function setSignedIn(user) {
  currentUser = user;
  elements.loginButton.hidden = Boolean(user);
  elements.userAvatar.style.display = user ? "flex" : "none";
  elements.userName.style.display = user ? "block" : "none";
  elements.userChip.style.display = user ? "flex" : "none";
  renderIdentity();
  setUserMenu(false);
  if (user) {
    if (!streamReader) connectStream();
  } else {
    clearTimeout(streamReconnectTimer);
    streamReader?.close();
    streamReader = null;
    elements.streamVideo.srcObject = null;
    setPlayerMessage("登录后观看直播");
  }
  elements.chatInput.placeholder = user ? "发送弹幕..." : "登录后发送弹幕...";
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

function refreshMessageIdentity(username) {
  const profile = profiles.get(username);
  for (const row of elements.messages.children) {
    if (row.dataset.username !== username) continue;
    row.querySelector(".display-name").textContent =
      profile?.nickname || row.dataset.nickname || username;
    const avatar = row.querySelector(".message-avatar");
    avatar.replaceChildren();
    if (profile?.avatar) {
      const image = document.createElement("img");
      image.src = profile.avatar;
      image.alt = "";
      avatar.append(image);
    } else {
      avatar.textContent = username.charAt(0).toUpperCase();
    }
  }
}

function setUserMenu(open) {
  elements.userDropdown.hidden = !open;
  elements.userChip.setAttribute("aria-expanded", String(open));
}

function send(payload) {
  if (socket?.readyState !== WebSocket.OPEN) {
    alert("聊天室尚未连接");
    return false;
  }
  socket.send(JSON.stringify(payload));
  return true;
}

function connectChat() {
  clearTimeout(reconnectTimer);
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${protocol}://${location.hostname}:8765`);
  socket.addEventListener("open", () => {
    setConnectionStatus("在线");
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    if (token) send({ type: "resume", token });
  });
  socket.addEventListener("error", () => setConnectionStatus("连接异常"));
  socket.addEventListener("close", () => {
    setConnectionStatus("重连中");
    reconnectTimer = window.setTimeout(connectChat, 2000);
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
  history(data) {
    elements.messages.replaceChildren();
    data.messages.forEach(addMessage);
  },
  chat(data) {
    addMessage(data);
    addDanmaku(data);
  },
  online(data) {
    elements.onlineNumber.textContent = data.count;
  },
  online_users(data) {
    renderOnlineUsers(data.users || []);
  },
  register_success() {
    alert("注册成功，请登录");
    elements.password.value = "";
    setAuthMode("login");
  },
  login_success(data) {
    localStorage.setItem("liveAuthToken", data.token);
    elements.authModal.style.display = "none";
    setSignedIn({
      username: data.username, nickname: data.nickname, avatar: data.avatar,
    });
  },
  resume_success(data) {
    setSignedIn({
      username: data.username, nickname: data.nickname, avatar: data.avatar,
    });
  },
  profile(data) {
    rememberProfile(data);
    if (currentUser && data.username === currentUser.username) {
      currentUser.nickname = data.nickname || "";
      currentUser.avatar = data.avatar || "";
      renderIdentity();
    }
    refreshMessageIdentity(data.username);
  },
  profile_updated() {
    elements.profileModal.style.display = "none";
  },
  profile_error(data) { alert(data.message); },
  invite_list(data) {
    renderInviteList(data.codes || []);
  },
  invite_created() {
    send({ type: "list_invites" });
  },
  invite_error(data) { alert(data.message); },
  account_deleted() {
    elements.deleteModal.style.display = "none";
    localStorage.removeItem(AUTH_TOKEN_KEY);
    setSignedIn(null);
    alert("账号已注销");
  },
  account_error(data) { alert(data.message); },
  auth_expired() {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    setSignedIn(null);
  },
  auth_error(data) { alert(data.message); },
  error(data) { alert(data.message); },
};

function handleServerMessage(data) {
  messageHandlers[data.type]?.(data);
}

function addMessage({ username, nickname, text, time, role }) {
  const info = roleInfo(role);
  const row = document.createElement("div");
  row.className = "message";
  row.dataset.username = username;
  row.dataset.nickname = nickname || "";
  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  const body = document.createElement("div");
  const user = document.createElement("div");
  user.className = "message-user";
  if (info.className) user.classList.add(`${info.className}-name-chat`);
  const nameSpan = document.createElement("span");
  nameSpan.className = "display-name";
  user.append(document.createTextNode(info.icon), nameSpan);
  if (time) {
    const clock = document.createElement("span");
    clock.className = "message-time";
    clock.textContent = time;
    user.append(clock);
  }
  const content = document.createElement("div");
  content.className = "message-text";
  content.textContent = text;
  body.append(user, content);
  row.append(avatar, body);
  elements.messages.append(row);
  refreshMessageIdentity(username);
  requestProfile(username);
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function setAuthMode(mode) {
  authMode = mode;
  const isLogin = mode === "login";
  elements.authTitle.textContent = isLogin ? "登录直播间" : "注册账号";
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

function openProfile() {
  if (!currentUser) return;
  elements.nicknameInput.value = currentUser.nickname || "";
  pendingAvatar = undefined;
  renderAvatarPreview(currentUser.avatar);
  setUserMenu(false);
  elements.profileModal.style.display = "flex";
}

function renderAvatarPreview(src) {
  elements.avatarPreview.hidden = !src;
  elements.avatarFallback.hidden = Boolean(src);
  if (src) {
    elements.avatarPreview.src = src;
  } else {
    elements.avatarFallback.textContent = currentUser
      ? currentUser.username.charAt(0).toUpperCase() : "";
  }
}

async function pickAvatar(file) {
  if (!file || !file.type.startsWith("image/")) return;
  const bitmap = await createImageBitmap(file).catch(() => null);
  if (!bitmap) {
    alert("图片读取失败");
    return;
  }
  const edge = Math.min(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  canvas.getContext("2d").drawImage(
    bitmap,
    (bitmap.width - edge) / 2, (bitmap.height - edge) / 2, edge, edge,
    0, 0, 128, 128,
  );
  const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
  if (dataUrl.length > 180000) {
    alert("图片太大，请换一张试试");
    return;
  }
  pendingAvatar = dataUrl;
  renderAvatarPreview(dataUrl);
}

function submitProfile() {
  if (!currentUser) return;
  send({
    type: "update_profile",
    nickname: elements.nicknameInput.value.trim(),
    ...(pendingAvatar !== undefined ? { avatar: pendingAvatar } : {}),
  });
}

function openInviteModal() {
  if (!currentUser) return;
  setUserMenu(false);
  elements.inviteList.replaceChildren();
  const loading = document.createElement("div");
  loading.className = "invite-empty";
  loading.textContent = "加载中…";
  elements.inviteList.append(loading);
  elements.inviteModal.style.display = "flex";
  send({ type: "list_invites" });
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {}
  const helper = document.createElement("textarea");
  helper.value = text;
  helper.style.position = "fixed";
  helper.style.opacity = "0";
  document.body.append(helper);
  helper.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {}
  helper.remove();
  return copied;
}

function renderInviteList(codes) {
  const list = elements.inviteList;
  list.replaceChildren();
  if (!codes.length) {
    const empty = document.createElement("div");
    empty.className = "invite-empty";
    empty.textContent = "还没有可用的邀请码，点击下方生成";
    list.append(empty);
    return;
  }
  for (const item of codes) {
    const row = document.createElement("div");
    row.className = "invite-row";
    const code = document.createElement("span");
    code.className = "invite-code";
    code.textContent = item.code;
    const copy = document.createElement("button");
    copy.className = "invite-copy";
    copy.type = "button";
    copy.textContent = "复制";
    copy.addEventListener("click", async () => {
      copy.textContent = (await copyText(item.code)) ? "已复制" : "请手动复制";
      window.setTimeout(() => { copy.textContent = "复制"; }, 1500);
    });
    row.append(code, copy);
    list.append(row);
  }
}

function createInvite() {
  if (!currentUser) return;
  send({ type: "create_invite" });
}

function openDeleteModal() {
  if (!currentUser) return;
  elements.deletePassword.value = "";
  setUserMenu(false);
  elements.deleteModal.style.display = "flex";
}

function submitDeleteAccount() {
  if (!elements.deletePassword.value) {
    alert("请输入密码");
    return;
  }
  send({ type: "delete_account", password: elements.deletePassword.value });
}

function toggleOnlinePopover() {
  const willOpen = elements.onlinePopover.hidden;
  elements.onlinePopover.hidden = !willOpen;
  if (!willOpen) return;
  setUserMenu(false);
  if (socket?.readyState === WebSocket.OPEN) {
    send({ type: "get_online" });
  } else {
    renderOnlineUsers([]);
  }
}

function renderOnlineUsers(users) {
  elements.onlinePopoverCount.textContent = users.length;
  const list = elements.onlinePopoverList;
  list.replaceChildren();
  if (!users.length) {
    const empty = document.createElement("div");
    empty.className = "online-user-empty";
    empty.textContent = "当前没有登录的用户在线";
    list.append(empty);
    return;
  }
  for (const info of users) {
    const item = document.createElement("div");
    item.className = "online-user";
    const avatar = document.createElement("div");
    avatar.className = "online-user-avatar";
    if (info.avatar) {
      const image = document.createElement("img");
      image.src = info.avatar;
      image.alt = "";
      avatar.append(image);
    } else {
      avatar.textContent = (info.nickname || info.username).charAt(0).toUpperCase();
    }
    const body = document.createElement("div");
    const name = document.createElement("div");
    name.className = "online-user-name";
    name.textContent = `${roleInfo(info.role).icon}${info.nickname || info.username}`;
    body.append(name);
    if (info.nickname && info.nickname !== info.username) {
      const account = document.createElement("div");
      account.className = "online-user-account";
      account.textContent = info.username;
      body.append(account);
    }
    item.append(avatar, body);
    list.append(item);
  }
}

function sendMessage() {
  const text = elements.chatInput.value.trim();
  if (!text) return;
  if (!currentUser) {
    openLogin();
    return;
  }
  if (send({ type: "chat", text })) elements.chatInput.value = "";
}

function updateDanmakuButton() {
  elements.danmakuToggle.textContent = "💬";
  elements.danmakuToggle.classList.toggle("active", danmaku.enabled);
  elements.danmakuToggle.setAttribute("aria-pressed", String(danmaku.enabled));
  describeButton(elements.danmakuToggle, danmaku.enabled ? "关闭弹幕" : "开启弹幕");
}

function toggleDanmaku() {
  danmaku.enabled = !danmaku.enabled;
  localStorage.setItem("danmakuEnabled", String(danmaku.enabled));
  updateDanmakuButton();
  if (!danmaku.enabled) {
    danmaku.queue.length = 0;
    clearTimeout(danmaku.timer);
    danmaku.timer = 0;
    elements.danmakuLayer.replaceChildren();
  }
}

function resizeDanmakuTracks() {
  const usableHeight = elements.danmakuLayer.clientHeight
    - danmaku.topReserved - danmaku.bottomReserved;
  const count = Math.max(1, Math.floor(usableHeight / danmaku.trackHeight));
  danmaku.busyUntil = Array.from(
    { length: count }, (_, index) => danmaku.busyUntil[index] || 0,
  );
}

function addDanmaku({ username, text, role }) {
  if (!danmaku.enabled) return;
  danmaku.queue.push({
    username, role,
    text: text.length > 80 ? `${text.slice(0, 80)}…` : text,
  });
  pumpDanmakuQueue();
}

function scheduleDanmakuPump(delay) {
  if (danmaku.timer) return;
  danmaku.timer = window.setTimeout(() => {
    danmaku.timer = 0;
    pumpDanmakuQueue();
  }, Math.max(16, delay));
}

function pumpDanmakuQueue() {
  if (!danmaku.enabled || !danmaku.queue.length) return;
  resizeDanmakuTracks();
  const now = performance.now();
  const track = danmaku.busyUntil.findIndex((until) => until <= now);
  if (track < 0) {
    scheduleDanmakuPump(Math.min(...danmaku.busyUntil) - now);
    return;
  }
  launchDanmaku(danmaku.queue.shift(), track);
  if (danmaku.queue.length) pumpDanmakuQueue();
}

function launchDanmaku(data, track) {
  const info = roleInfo(data.role);
  const item = document.createElement("div");
  item.className = `danmaku-item${info.className ? ` ${info.className}` : ""}`;
  const name = profiles.get(data.username)?.nickname || data.nickname || data.username;
  item.textContent = `${info.icon}${name}：${data.text}`;
  item.style.top = `${danmaku.topReserved + track * danmaku.trackHeight}px`;
  elements.danmakuLayer.append(item);
  const itemWidth = item.offsetWidth;
  const totalDistance = elements.danmakuLayer.clientWidth + itemWidth + 30;
  const duration = totalDistance / danmaku.speed * 1000;
  const safeDelay = (itemWidth + danmaku.gap) / danmaku.speed * 1000;
  danmaku.busyUntil[track] = performance.now() + safeDelay;
  const animation = item.animate(
    [{ transform: "translate3d(0,0,0)" }, { transform: `translate3d(-${totalDistance}px,0,0)` }],
    { duration, easing: "linear" },
  );
  animation.addEventListener("finish", () => item.remove(), { once: true });
  scheduleDanmakuPump(safeDelay + 16);
}

function toggleFullscreen() {
  if (!document.fullscreenElement) elements.player.requestFullscreen?.();
  else document.exitFullscreen?.();
}

elements.loginButton.addEventListener("click", openLogin);
elements.playToggle.addEventListener("click", togglePlayback);
elements.muteToggle.addEventListener("click", toggleMute);
elements.volumeSlider.addEventListener("input", setVolume);
elements.streamVideo.addEventListener("play", updatePlaybackButton);
elements.streamVideo.addEventListener("playing", () => setPlayerMessage(""));
elements.streamVideo.addEventListener("pause", updatePlaybackButton);
elements.player.addEventListener("pointermove", showPlayerControls, { passive: true });
elements.player.addEventListener("pointerdown", showPlayerControls, { passive: true });
elements.player.addEventListener("keydown", showPlayerControls);
elements.player.addEventListener("focusin", showPlayerControls);
elements.player.addEventListener("focusout", showPlayerControls);
document.addEventListener("fullscreenchange", handleFullscreenChange);
elements.sendButton.addEventListener("click", sendMessage);
elements.danmakuToggle.addEventListener("click", toggleDanmaku);
elements.fullscreenButton.addEventListener("click", toggleFullscreen);
elements.authSubmit.addEventListener("click", submitAuth);
elements.authSwitch.addEventListener("click", () => setAuthMode(authMode === "login" ? "register" : "login"));
elements.userChip.addEventListener("click", () => setUserMenu(elements.userDropdown.hidden));
elements.onlineStat.addEventListener("click", toggleOnlinePopover);
elements.profileButton.addEventListener("click", openProfile);
elements.avatarButton.addEventListener("click", () => elements.avatarFile.click());
elements.avatarFile.addEventListener("change", () => {
  pickAvatar(elements.avatarFile.files[0]);
  elements.avatarFile.value = "";
});
elements.avatarReset.addEventListener("click", () => {
  pendingAvatar = "";
  renderAvatarPreview("");
});
elements.profileSubmit.addEventListener("click", submitProfile);
elements.nicknameInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.isComposing) submitProfile();
});
elements.inviteButton.addEventListener("click", openInviteModal);
elements.inviteCreate.addEventListener("click", createInvite);
elements.inviteClose.addEventListener("click", () => {
  elements.inviteModal.style.display = "none";
});
elements.deleteAccountButton.addEventListener("click", openDeleteModal);
elements.deleteSubmit.addEventListener("click", submitDeleteAccount);
elements.deletePassword.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.isComposing) submitDeleteAccount();
});
elements.deleteCancel.addEventListener("click", () => {
  elements.deleteModal.style.display = "none";
});
elements.logoutButton.addEventListener("click", () => {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (token) send({ type: "logout", token });
  localStorage.removeItem(AUTH_TOKEN_KEY);
  setSignedIn(null);
});
document.addEventListener("click", (event) => {
  if (!elements.userArea.contains(event.target)) setUserMenu(false);
  if (!elements.leftHeader.contains(event.target)) elements.onlinePopover.hidden = true;
});
elements.chatInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.isComposing) sendMessage();
});
elements.password.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.isComposing) submitAuth();
});
elements.authModal.addEventListener("click", (event) => {
  if (event.target === elements.authModal) elements.authModal.style.display = "none";
});
elements.profileModal.addEventListener("click", (event) => {
  if (event.target === elements.profileModal) elements.profileModal.style.display = "none";
});
elements.deleteModal.addEventListener("click", (event) => {
  if (event.target === elements.deleteModal) elements.deleteModal.style.display = "none";
});
elements.inviteModal.addEventListener("click", (event) => {
  if (event.target === elements.inviteModal) elements.inviteModal.style.display = "none";
});
window.addEventListener("resize", resizeDanmakuTracks, { passive: true });
window.addEventListener("resize", syncChatHeight, { passive: true });
window.addEventListener("resize", syncComposerPosition, { passive: true });
window.addEventListener("beforeunload", () => {
  clearTimeout(streamReconnectTimer);
  clearTimeout(controlsHideTimer);
  chatHeightObserver?.disconnect();
  streamReader?.close();
});

updatePlaybackButton();
updateMuteButton();
updateDanmakuButton();
updateFullscreenButton();
resizeDanmakuTracks();
syncComposerPosition();
chatHeightObserver = new ResizeObserver(syncChatHeight);
chatHeightObserver.observe(elements.player);
syncChatHeight();
setPlayerMessage(localStorage.getItem(AUTH_TOKEN_KEY) ? "正在连接直播…" : "登录后观看直播");
connectChat();
