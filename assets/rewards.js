/* 两个页面共用的签到抽奖面板；次数和中奖金额均以服务端为准。 */
(() => {
  function create({send, onCoins}) {
    let username = "";
    let snapshot = null;
    let busy = false;
    let pendingDraw = "";
    const pendingByUser = new Map();
    let timeout = 0;
    let rollover = 0;
    const trigger = document.getElementById("rewardsButton");
    const dialog = document.createElement("dialog");
    dialog.id = "rewardsDialog";
    dialog.className = "rewards-dialog";
    dialog.setAttribute("aria-labelledby", "rewardsTitle");
    dialog.innerHTML = `
      <div class="rewards-heading"><div><div class="rewards-eyebrow">每日小惊喜</div>
        <h2 id="rewardsTitle">签到抽奖</h2></div>
        <button type="button" class="rewards-close" aria-label="关闭签到抽奖">×</button></div>
      <p class="rewards-copy">每天签到领 5 次机会，攒着也可以。每抽必得金币。</p>
      <div class="rewards-summary"><div><span>剩余抽奖机会</span>
        <strong id="rewardsTickets">—</strong></div><div><span>我的金币</span>
        <strong id="rewardsCoins">—</strong></div></div>
      <p id="rewardsDay" class="rewards-copy">正在读取签到状态…</p>
      <div class="rewards-actions"><button type="button" id="dailyCheckin">签到领取 5 次</button>
        <button type="button" id="lotteryDraw">抽一次 · 消耗 1 次</button></div>
      <p id="rewardsFeedback" class="rewards-feedback" role="status" aria-live="polite"></p>
      <details class="rewards-rules"><summary>奖池与规则</summary>
        <ul id="rewardsPrizes"></ul>
        <p>每个区间内的整数金币等概率。北京时间每天 00:00 可再次签到；机会可叠加、不会过期，中奖金币立即到账。</p></details>
      <details class="rewards-history"><summary>最近 10 次中奖记录</summary>
        <ul id="rewardsHistory"></ul></details>`;
    document.body.append(dialog);
    const tickets = dialog.querySelector("#rewardsTickets");
    const coins = dialog.querySelector("#rewardsCoins");
    const day = dialog.querySelector("#rewardsDay");
    const checkin = dialog.querySelector("#dailyCheckin");
    const draw = dialog.querySelector("#lotteryDraw");
    const feedback = dialog.querySelector("#rewardsFeedback");
    const storageKey = () => `liveLotteryPending:${username}`;

    function savePending(value) {
      pendingDraw = value;
      if (value) pendingByUser.set(username, value);
      else pendingByUser.delete(username);
      try {
        if (value) sessionStorage.setItem(storageKey(), value);
        else sessionStorage.removeItem(storageKey());
      } catch (_) { /* 禁用浏览器存储时，当前页面内仍保留重试 ID。 */ }
    }

    function render() {
      tickets.textContent = snapshot ? String(snapshot.tickets) : "—";
      coins.textContent = snapshot ? Number(snapshot.coins).toFixed(2) : "—";
      day.textContent = snapshot ? `${snapshot.day} · 北京时间 · ${snapshot.checked_in ? "今日已签到" : "今日尚未签到"}` : "正在读取签到状态…";
      checkin.disabled = busy || !snapshot || snapshot.checked_in;
      checkin.textContent = snapshot?.checked_in ? "今日已签到" : "签到领取 5 次";
      draw.disabled = busy || !snapshot || (!pendingDraw && snapshot.tickets < 1);
      draw.textContent = busy ? "处理中…" : pendingDraw ? "重试上次抽奖" : "抽一次 · 消耗 1 次";
    }

    function finish() {
      clearTimeout(timeout);
      busy = false;
    }

    function request(payload) {
      busy = true;
      feedback.textContent = "处理中…";
      render();
      if (send(payload) === false) {
        finish();
        feedback.textContent = "连接尚未就绪，请重连后重试。";
        render();
        return;
      }
      clearTimeout(timeout);
      timeout = setTimeout(() => {
        busy = false;
        feedback.textContent = payload.type === "draw_lottery"
          ? "暂未收到结果，可以重试；上次抽奖不会重复扣次数。"
          : "暂未收到签到结果，可以重试；今日不会重复领取。";
        render();
      }, 8000);
    }

    function open() {
      if (!username) return;
      document.getElementById("userDropdown").hidden = true;
      document.getElementById("userChip").setAttribute("aria-expanded", "false");
      if (!dialog.open) dialog.showModal();
      render();
      send({type: "get_daily_rewards"});
    }

    trigger.addEventListener("click", open);
    dialog.querySelector(".rewards-close").addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => document.getElementById("userChip").focus());
    checkin.addEventListener("click", () => request({type: "daily_checkin"}));
    draw.addEventListener("click", () => {
      if (!pendingDraw) {
        const bytes = crypto.getRandomValues(new Uint8Array(16));
        savePending(Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join(""));
      }
      request({type: "draw_lottery", request_id: pendingDraw});
    });
    document.addEventListener("visibilitychange", () => {
      if (username && document.visibilityState === "visible") send({type: "get_daily_rewards"});
    });

    function setUser(user) {
      finish();
      clearTimeout(rollover);
      username = user?.username || "";
      snapshot = null;
      pendingDraw = pendingByUser.get(username) || "";
      feedback.textContent = "";
      trigger.textContent = "每日签到 / 抽奖";
      if (!username) {
        dialog.close();
      } else {
        try { pendingDraw = sessionStorage.getItem(storageKey()) || pendingDraw; } catch (_) {}
        send({type: "get_daily_rewards"});
        if (pendingDraw) request({type: "draw_lottery", request_id: pendingDraw});
      }
      render();
    }

    function handle(data) {
      if (!username || (data.username && data.username !== username)) return;
      if (data.type === "rewards_error") {
        finish();
        // 确定失败不消耗机会；超时/断线没有此响应，必须保留原请求 ID。
        if (data.request_id === pendingDraw) savePending("");
        feedback.textContent = data.message;
        if (data.request_id) send({type: "get_daily_rewards"});
        render();
        return;
      }
      snapshot = data;
      onCoins(data.coins);
      trigger.textContent = `每日签到 / 抽奖 · ${data.tickets} 次`;
      if (data.type === "checkin_result") {
        finish();
        feedback.textContent = data.awarded ? `签到成功，获得 ${data.awarded} 次抽奖机会！` : "今天已经签到过了，明天再来。";
      } else if (data.type === "lottery_result") {
        if (data.request_id === pendingDraw) { savePending(""); finish(); }
        feedback.textContent = `抽中 ${data.amount} 金币，已到账！${data.replayed ? "（已恢复上次结果）" : ""}`;
      }
      const prizes = dialog.querySelector("#rewardsPrizes");
      prizes.replaceChildren();
      for (const tier of data.prize_tiers || []) {
        const item = document.createElement("li");
        item.textContent = `${tier.min}–${tier.max} 金币：${tier.percent}%`;
        prizes.append(item);
      }
      const records = dialog.querySelector("#rewardsHistory");
      records.replaceChildren();
      for (const entry of data.history || []) {
        const item = document.createElement("li");
        const time = new Date(entry.created_at * 1000).toLocaleString("zh-CN", {timeZone: "Asia/Shanghai"});
        item.textContent = `${time} · +${entry.amount} 金币`;
        records.append(item);
      }
      if (!data.history?.length) records.textContent = "还没有抽奖记录，签到后试试手气吧。";
      clearTimeout(rollover);
      if (data.next_reset_at) {
        rollover = setTimeout(() => {
          if (username) send({type: "get_daily_rewards"});
        }, Math.min(86400000, Math.max(1000, (data.next_reset_at - data.server_time) * 1000 + 250)));
      }
      render();
    }
    return {setUser, handle};
  }
  window.DailyRewards = {create};
})();
