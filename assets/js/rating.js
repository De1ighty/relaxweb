/* 段位概览、公开计分规则与逐局收益明细。分数只取服务端结果。 */
import { formatClock, formatCoins, ratingBadge, renderGameView, renderIdentity, send, state } from "./core.js";
import { onMessage } from "./registry.js";

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
