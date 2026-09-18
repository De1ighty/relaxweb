// Local deploy/serve.py + Playwright. Uses real DOM/CSS and the WebSocket message handlers.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({headless: true,
    executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', args: ['--no-sandbox']});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 900}, hasTouch: true});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript(() => {
      window.sent = [];
      window.sockets = [];
      window.WebSocket = class {
        static OPEN = 1;
        constructor() { this.readyState = 1; this.listeners = {}; sockets.push(this); }
        send(data) { sent.push(JSON.parse(data)); }
        addEventListener(type, callback) { this.listeners[type] = callback; }
        close() {}
      };
    });
    await page.goto('http://localhost:8000/game.html');
    const deliver = data => page.evaluate(data => sockets[0].listeners.message({data: JSON.stringify(data)}), data);
    const tiers = ['青铜', '白银', '黄金', '铂金', '钻石', '大师'].map((tier, i) => ({
      tier, score: i ? 400 + i * 400 : 0, floor: i ? 400 + i * 400 : 0,
      next_score: i === 5 ? null : 800 + i * 400, games: 0,
    }));
    const user = {type: 'resume_success', username: 'alice', nickname: '爱丽丝',
      coins: 900, rating: {...tiers[1], score: 1000}};
    const entries = Array.from({length: 100}, (_, i) => ({username: `player${i}`,
      nickname: i === 2 ? '<img src=x onerror=alert(1)>' : i === 3 ? '一个很长很长很长很长很长很长的玩家昵称' : `玩家 ${i + 1}`,
      rank: i < 2 ? 1 : i + 1, rating: {...tiers[Math.max(0, 5 - i)], games: i}}));
    entries[1].rating = entries[0].rating;
    const board = {type: 'rating_leaderboard', entries, limit: 100, total: 108, tiers,
      self: {username: 'alice', nickname: '爱丽丝', rank: 106, rating: user.rating}};
    await deliver(user);
    await page.getByRole('button', {name: '查看段位排行 →'}).click();
    assert.deepEqual(await page.evaluate(() => sent.at(-1)), {type: 'get_rating_leaderboard'});
    assert.match(await page.locator('.rating-leaderboard').innerText(), /正在读取排行/);
    await deliver(board);
    assert.equal(await page.locator('.rating-ranking-row').count(), 100);
    assert.match(await page.locator('.rating-own-rank').innerText(), /第 106 名/);
    assert.deepEqual(await page.locator('.rating-place').allTextContents().then(a => a.slice(0, 3)), ['1', '1', '3']);
    assert.equal(await page.locator('.rating-player img').count(), 0);
    assert.match(await page.locator('.rating-player').nth(2).innerText(), /<img src=x/);
    assert.equal(await page.locator('.rating-tier-item').count(), 6);
    const icons = await page.locator('.rating-tier-item .rating-badge').evaluateAll(nodes =>
      nodes.map(node => getComputedStyle(node, '::before').backgroundImage));
    assert.equal(new Set(icons).size, 6);
    for (const icon of icons) {
      const url = icon.match(/url\("(.*)"\)/)[1];
      assert.equal((await page.request.get(url)).status(), 200, url);
    }
    for (const [width, height] of [[1440, 900], [320, 568], [390, 844], [844, 390]]) {
      await page.setViewportSize({width, height});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false,
        `${width}px fits without horizontal overflow`);
      assert.equal(await page.locator('.rating-ranking-row').evaluateAll(rows => rows.every(row => {
        const [rank, player, score] = [...row.children].map(el => el.getBoundingClientRect());
        return rank.right <= player.left && player.right <= score.left;
      })), true, `${width}px rank, nickname and badge do not overlap`);
      if (width === 390 && process.env.RANKING_SCREENSHOT) {
        await page.screenshot({path: `${process.env.RANKING_SCREENSHOT}-mobile.png`});
      }
    }
    await page.setViewportSize({width: 1440, height: 900});
    if (process.env.RANKING_SCREENSHOT) await page.screenshot({path: `${process.env.RANKING_SCREENSHOT}-desktop.png`});
    await page.getByRole('button', {name: '刷新排行'}).click();
    assert.deepEqual(await page.evaluate(() => sent.at(-1)), {type: 'get_rating_leaderboard'});
    // A different player's settlement can change our rank too, so it refreshes the open board.
    await page.evaluate(() => { sent.length = 0; });
    await deliver({type: 'rating_update', username: 'player0', rating: tiers[5]});
    assert.deepEqual(await page.evaluate(() => sent), [{type: 'get_rating_leaderboard'}]);
    const own = {...board.self, rank: 1, rating: {...tiers[5], score: 2500, games: 10}};
    await deliver({...board, entries: [own, ...entries.slice(1)], self: own});
    assert.equal(await page.locator('.rating-ranking-row.is-self').count(), 1);
    assert.match(await page.locator('.rating-own-rank').innerText(), /大师 2500/);
    // Reconnect refreshes the currently open board; late messages must not change navigation.
    await page.evaluate(() => { sent.length = 0; });
    await deliver(user);
    assert.equal(await page.evaluate(() => sent.some(m => m.type === 'get_rating_leaderboard')), true);
    await page.getByRole('button', {name: '← 游戏厅'}).click();
    await deliver(board);
    assert.equal(await page.locator('.rating-leaderboard').count(), 0);
    await page.getByRole('button', {name: '查看段位排行 →'}).click();
    await deliver({...board, entries: [], self: null, total: 0});
    assert.match(await page.locator('.rating-leaderboard').innerText(), /暂无排行数据/);
    await deliver({type: 'auth_expired'});
    await deliver(board);
    assert.equal(await page.locator('.rating-leaderboard').count(), 0);
    assert.equal(await page.locator('.game-entry-card').count(), 1);

    // The live room account menu uses the same tier emblems as the game hall.
    await page.goto('http://localhost:8000/index.html');
    await page.evaluate(() => { window.MediaMTXWebRTCReader = class { close() {} }; });
    await deliver(user);
    await page.locator('#userChip').click();
    const badge = page.locator('#dropdownName .rating-badge');
    assert.equal(await badge.getAttribute('data-tier'), '白银');
    assert.match(await badge.evaluate(el => getComputedStyle(el, '::before').backgroundImage), /silver\.svg/);
    await deliver({type: 'rating_update', username: 'alice', rating: tiers[5]});
    assert.equal(await badge.getAttribute('data-tier'), '大师');
    assert.deepEqual(errors, []);
    console.log('PASS leaderboard entry, ties, own rank, six SVG emblems, safe text, refresh/reconnect/logout, both account menus and responsive layouts');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
