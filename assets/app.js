"use strict";

const $ = (id) => document.getElementById(id);
const elements = {
  authModal: $("loginModal"), authSubmit: $("authSubmit"), authSwitch: $("authSwitch"),
  authTitle: $("authTitle"), chatCard: $("chatCard"), chatInput: $("chatInput"),
  chatStatus: $("chatStatus"), danmakuComposer: $("danmakuComposer"),
  danmakuLayer: $("danmakuLayer"), danmakuToggle: $("danmakuToggle"),
  fullscreenButton: $("fullscreenButton"),
  loginButton: $("loginButton"), messages: $("messages"), muteToggle: $("muteToggle"),
  onlineNumber: $("onlineNumber"), password: $("password"), player: $("player"),
  playerMessage: $("playerMessage"), playerTools: $("playerTools"),
  playToggle: $("playToggle"), sendButton: $("sendButton"),
  streamVideo: $("streamVideo"), userAvatar: $("userAvatar"), userName: $("userName"),
  username: $("username"), viewerCount: $("viewerCount"), volumeSlider: $("volumeSlider"),
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
let authMode = "login";
let currentUser = null;
let socket = null;
let reconnectTimer = 0;
let streamReader = null;
let streamReconnectTimer = 0;
let controlsHideTimer = 0;
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
  const protocol = location.protocol === "https:" ? "https:" : "http:";
  streamReader = new MediaMTXWebRTCReader({
    url: `${protocol}//${location.hostname}:8889/xiaopang/whep`,
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
    : mobile ? elements.chatCard.querySelector(".notice") : null;
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
  if (window.matchMedia("(max-width: 1000px)").matches) {
    elements.chatCard.style.height = "";
    return;
  }
  elements.chatCard.style.height = `${elements.player.offsetHeight}px`;
}

function setConnectionStatus(text) {
  elements.chatStatus.textContent = `● ${text}`;
}

function setSignedIn(user) {
  currentUser = user;
  elements.loginButton.hidden = Boolean(user);
  elements.userAvatar.style.display = user ? "flex" : "none";
  elements.userName.style.display = user ? "block" : "none";
  elements.userAvatar.textContent = user ? user.charAt(0).toUpperCase() : "";
  elements.userName.textContent = user || "";
  elements.chatInput.placeholder = user ? "发送弹幕..." : "登录后发送弹幕...";
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
    elements.viewerCount.textContent = data.count;
    elements.onlineNumber.textContent = data.count;
  },
  register_success() {
    alert("注册成功，请登录");
    elements.password.value = "";
    setAuthMode("login");
  },
  login_success(data) {
    localStorage.setItem("liveAuthToken", data.token);
    elements.authModal.style.display = "none";
    setSignedIn(data.username);
  },
  resume_success(data) {
    setSignedIn(data.username);
  },
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

function addMessage({ username, text, time, role }) {
  const info = roleInfo(role);
  const row = document.createElement("div");
  row.className = "message";
  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = username.charAt(0).toUpperCase();
  const body = document.createElement("div");
  const user = document.createElement("div");
  user.className = "message-user";
  if (info.className) user.classList.add(`${info.className}-name-chat`);
  user.append(document.createTextNode(`${info.icon}${username}`));
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
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function setAuthMode(mode) {
  authMode = mode;
  const isLogin = mode === "login";
  elements.authTitle.textContent = isLogin ? "登录直播间" : "注册账号";
  elements.authSubmit.textContent = isLogin ? "登录" : "注册";
  elements.password.autocomplete = isLogin ? "current-password" : "new-password";
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
  send({ type: authMode, username, password });
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
  item.textContent = `${info.icon}${data.username}：${data.text}`;
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
elements.chatInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.isComposing) sendMessage();
});
elements.password.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.isComposing) submitAuth();
});
elements.authModal.addEventListener("click", (event) => {
  if (event.target === elements.authModal) elements.authModal.style.display = "none";
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
connectStream();
connectChat();
