/* 段位概览、公开计分规则与逐局收益明细。分数只取服务端结果。 */
import { elements, formatClock, formatCoins, ratingBadge, renderGameView, renderIdentity, send, state } from "./core.js";
import { onMessage, registerView } from "./registry.js";

function signed(value) {
  return `${value > 0 ? "+" : ""}${value}`;
}

export function ratingResultsNode(results) {
  const box = document.createElement("section");
  box.className = "rating-results";
  const heading = document.createElement("h3");
  heading.textContent = "本局段位结算";
  box.append(heading);
  for (const [username, entry] of Object.entries(results)) {
    const row = document.createElement("div");
    row.className = "rating-result-row";
    const info = document.createElement("div");
    const label = document.createElement("strong");
    label.textContent = state.myRoom?.players.find((p) => p.username === username)?.nickname || username;
    const detail = document.createElement("div");
    detail.className = "rating-detail";
    const roi = ((entry.final / entry.initial - 1) * 100).toFixed(1);
    detail.textContent = `${formatCoins(entry.initial)} → ${formatCoins(entry.final)} · 收益率 ${Number(roi) > 0 ? "+" : ""}${roi}%`;
    info.append(label, detail);
    const outcome = document.createElement("div");
    outcome.className = "rating-outcome";
    const delta = document.createElement("strong");
    delta.className = entry.delta > 0 ? "rating-gain" : entry.delta < 0 ? "rating-loss" : "";
    delta.textContent = `${signed(entry.delta)} 分`;
    outcome.append(delta, ratingBadge(entry.rating));
    row.append(info, outcome);
    box.append(row);
  }
  return box;
}

export function ratingCard() {
  const card = document.createElement("section");
  card.className = "game-card-page rating-card";
  const heading = document.createElement("h2");
  heading.textContent = "我的段位";
  const rating = state.currentUser?.rating;
  heading.append(ratingBadge(rating));
  const rankingButton = document.createElement("button");
  rankingButton.type = "button";
  rankingButton.className = "online-stat rating-ranking-button";
  rankingButton.textContent = "查看段位排行 →";
  rankingButton.addEventListener("click", () => {
    state.hallPage = "rankings";
    state.ratingLeaderboard = null;
    send({ type: "get_rating_leaderboard" });
    renderGameView();
  });
  heading.append(rankingButton);
  const progress = document.createElement("p");
  progress.className = "rating-detail";
  progress.textContent = rating
    ? `已结算 ${rating.games} 局 · ${rating.next_score == null ? "已达最高段位" : `距${rating.next_tier}还差 ${rating.next_score - rating.score} 分`}`
    : "正在读取段位…";
  const rules = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "积分怎么算？";
  const copy = document.createElement("p");
  copy.textContent = "从 1000 分起步，德州与 UNO 共用段位。每局收益率 =（结余 − 开局筹码）÷ 开局筹码；盈利 × 40，亏损 × 20，加扣系数 2:1，更容易上分。四舍五入到整数，最多 +40 / −20，最低 0 分。例：100 → 120 加 8 分，100 → 80 扣 4 分，保本不变。";
  const tiers = document.createElement("p");
  tiers.textContent = "青铜 0–799 · 白银 800–1199 · 黄金 1200–1599 · 铂金 1600–1999 · 钻石 2000–2399 · 大师 2400+";
  const scope = document.createElement("p");
  scope.textContent = "再来一局以新的开局筹码计分。中途离桌按实际取回筹码立即结算（UNO 原规则原额退出，收益为 0）；未完成的流局、重开及重启退款不计分，已完成的结算保留。转账、竞猜和金币调整不影响段位。";
  rules.append(summary, copy, tiers, scope);
  const history = document.createElement("details");
  const historyTitle = document.createElement("summary");
  historyTitle.textContent = "最近 20 局积分明细";
  history.append(historyTitle);
  if (!state.ratingEntries.length) {
    const empty = document.createElement("p");
    empty.textContent = "暂无积分结算，完成一局后会记录在这里。";
    history.append(empty);
  }
  for (const entry of state.ratingEntries) {
    const row = document.createElement("div");
    row.className = "rating-history-row";
    const title = document.createElement("strong");
    title.textContent = `${entry.game_type === "uno" ? "UNO" : "德州"} · ${entry.room_name} · 第 ${entry.hand_no} 局 · ${signed(entry.delta)} 分`;
    const detail = document.createElement("div");
    detail.className = "rating-detail";
    detail.textContent = `${formatClock(entry.created_at)} · ${formatCoins(entry.initial)} → ${formatCoins(entry.final)} · ${entry.rating.tier} ${entry.rating.score}`;
    row.append(title, detail);
    history.append(row);
  }
  card.append(heading, progress, rules, history);
  return card;
}

onMessage("rating_update", (data) => {
  if (state.currentUser && !state.myRoom && state.hallPage === "rankings") {
    send({ type: "get_rating_leaderboard" });
  }
  if (data.username !== state.currentUser?.username) return;
  state.currentUser.rating = data.rating;
  renderIdentity();
  send({ type: "get_rating_history" });
});

onMessage("rating_history", (data) => {
  if (!state.currentUser) return;
  state.currentUser.rating = data.rating;
  state.ratingEntries = data.entries || [];
  renderIdentity();
  if (!state.myRoom && !state.hallPage) renderGameView();
});

function renderRankings() {
  const toolbar = document.createElement("div");
  toolbar.className = "rooms-toolbar rating-toolbar";
  const back = document.createElement("button");
  back.type = "button";
  back.className = "online-stat hall-back";
  back.textContent = "← 游戏厅";
  back.addEventListener("click", () => {
    state.hallPage = null;
    renderGameView();
  });
  const heading = document.createElement("h1");
  heading.className = "hall-page-title";
  heading.textContent = "段位排行榜";
  const refresh = document.createElement("button");
  refresh.type = "button";
  refresh.className = "online-stat";
  refresh.textContent = "刷新排行";
  refresh.addEventListener("click", () => send({ type: "get_rating_leaderboard" }));
  toolbar.append(back, heading, refresh);

  const board = document.createElement("section");
  board.className = "game-card-page rating-leaderboard";
  board.setAttribute("aria-label", "段位排行");
  const data = state.ratingLeaderboard;
  if (!data) {
    const loading = document.createElement("p");
    loading.className = "rating-detail";
    loading.setAttribute("role", "status");
    loading.textContent = "正在读取排行，未显示时可点击刷新。";
    board.append(loading);
    elements.gameMain.replaceChildren(toolbar, board);
    return;
  }

  if (data.self) {
    const own = document.createElement("div");
    own.className = "rating-own-rank";
    const rank = document.createElement("strong");
    rank.textContent = `我的名次 · 第 ${data.self.rank} 名`;
    own.append(rank, ratingBadge(data.self.rating));
    board.append(own);
  }
  const note = document.createElement("p");
  note.className = "rating-detail";
  note.textContent = `共 ${data.total} 位玩家 · 展示前 ${data.limit} 位 · 按段位分排序，同分并列（如 1、1、3）。所有账号均参与，德州与 UNO 共用积分。`;
  board.append(note);

  const list = document.createElement("ol");
  list.className = "rating-ranking-list";
  for (const entry of data.entries) {
    const row = document.createElement("li");
    row.className = "rating-ranking-row";
    row.value = entry.rank;
    if (entry.username === state.currentUser.username) row.classList.add("is-self");
    const place = document.createElement("strong");
    place.className = "rating-place";
    place.textContent = String(entry.rank);
    place.setAttribute("aria-label", `第 ${entry.rank} 名`);
    if (entry.rank <= 3) place.dataset.podium = String(entry.rank);
    const player = document.createElement("div");
    player.className = "rating-player";
    const name = document.createElement("strong");
    name.textContent = entry.nickname || entry.username;
    const username = document.createElement("div");
    username.className = "rating-detail";
    username.textContent = `@${entry.username}${entry.username === state.currentUser.username ? " · 我" : ""}`;
    player.append(name, username);
    const outcome = document.createElement("div");
    outcome.className = "rating-ranking-score";
    const games = document.createElement("div");
    games.className = "rating-detail";
    games.textContent = `已结算 ${entry.rating.games} 局`;
    outcome.append(ratingBadge(entry.rating), games);
    row.append(place, player, outcome);
    list.append(row);
  }
  board.append(list);
  if (!data.entries.length) {
    const empty = document.createElement("p");
    empty.className = "rating-detail";
    empty.textContent = "暂无排行数据。";
    board.append(empty);
  }

  const legend = document.createElement("section");
  legend.className = "game-card-page rating-tier-guide";
  const title = document.createElement("h2");
  title.textContent = "段位标志";
  const tiers = document.createElement("div");
  tiers.className = "rating-tier-grid";
  for (const tier of data.tiers) {
    const item = document.createElement("div");
    item.className = "rating-tier-item";
    const badge = ratingBadge(tier);
    badge.textContent = tier.tier;
    badge.title = `${tier.tier} · ${tier.floor} 分起`;
    const range = document.createElement("div");
    range.className = "rating-detail";
    range.textContent = tier.next_score == null ? `${tier.floor}+` : `${tier.floor}–${tier.next_score - 1}`;
    item.append(badge, range);
    tiers.append(item);
  }
  legend.append(title, tiers);
  elements.gameMain.replaceChildren(toolbar, legend, board);
}

onMessage("rating_leaderboard", (data) => {
  if (!state.currentUser) return;
  state.ratingLeaderboard = data;
  if (!state.myRoom && state.hallPage === "rankings") renderGameView();
});

registerView("rankings", renderRankings);
