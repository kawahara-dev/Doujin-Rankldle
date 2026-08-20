const HOUR = 60 * 60 * 1000;
const SCANNING_TIME = 5000;
const POLL_INTERVAL = 15000;
const EXP_PER_LEVEL = 100;
const ACHIEVEMENTS = [
  { name: "FIRST BOOT", kind: "scans", target: 1 },
  { name: "SCANNER I", kind: "scans", target: 10 },
  { name: "SCANNER II", kind: "scans", target: 100 },
  { name: "SCANNER III", kind: "scans", target: 1000 },
  { name: "DATA COLLECTOR I", kind: "items", target: 100 },
  { name: "DATA COLLECTOR II", kind: "items", target: 1000 },
  { name: "DATA COLLECTOR III", kind: "items", target: 10000 },
];
const MODULES = [{ name: "FANZA", enabled: true }];
let nextScan = null;
let knownLastRun = null;
let loading = false;

const el = (id) => document.getElementById(id);
const pad = (number) => String(number).padStart(2, "0");
const number = (value) => Math.max(0, Number(value) || 0);

function updateCountdown() {
  if (!nextScan) return;
  const remaining = nextScan - Date.now();
  if (remaining > 0) {
    const seconds = Math.floor(remaining / 1000);
    el("countdown").textContent = `${pad(Math.floor(seconds / 3600))}:${pad(Math.floor(seconds % 3600 / 60))}:${pad(seconds % 60)}`;
    el("scanState").textContent = "SCHEDULED";
  } else if (remaining > -SCANNING_TIME) {
    el("countdown").textContent = "SCANNING...";
    el("scanState").textContent = "ACTION RUNNING";
  } else {
    el("countdown").textContent = "WAITING FOR UPDATE...";
    el("scanState").textContent = "VERIFYING STATUS.JSON";
  }
}

function botAge(firstRun) {
  const elapsed = firstRun ? Math.max(0, Date.now() - new Date(firstRun).getTime()) : 0;
  const hours = Math.floor(elapsed / HOUR);
  return hours >= 24 ? `${Math.floor(hours / 24)}d ${hours % 24}h` : `${hours}h`;
}

function renderAchievements(scans, items) {
  el("achievements").replaceChildren(...ACHIEVEMENTS.map((achievement) => {
    const current = achievement.kind === "scans" ? scans : items;
    const unlocked = current >= achievement.target;
    const card = document.createElement("article");
    card.className = `achievement ${unlocked ? "unlocked" : "locked"}`;
    const title = document.createElement("strong");
    title.textContent = `${unlocked ? "🏆" : "🔒"} ${achievement.name}`;
    const progress = document.createElement("small");
    progress.textContent = unlocked ? "UNLOCKED" : `${Math.min(current, achievement.target).toLocaleString("ja-JP")} / ${achievement.target.toLocaleString("ja-JP")} ${achievement.kind}`;
    card.append(title, progress);
    return card;
  }));
}

function renderModules() {
  el("modules").replaceChildren(...MODULES.filter((module) => module.enabled).map((module) => {
    const card = document.createElement("article");
    card.className = "module active";
    card.textContent = `🟢 ${module.name}`;
    return card;
  }));
}

function renderItems(items) {
  if (!items.length) { el("productList").innerHTML = '<p class="empty">まだ商品データがないよ。次回巡回を待ってね。</p>'; return; }
  el("productList").replaceChildren(...items.map((item) => {
    const link = document.createElement("a"); link.className = "product"; link.href = item.url; link.target = "_blank"; link.rel = "noopener noreferrer sponsored";
    const rank = document.createElement("span"); rank.className = "rank"; rank.textContent = `#${item.rank}`;
    const title = document.createElement("span"); title.className = "title"; title.textContent = item.title;
    const price = document.createElement("span"); price.className = "price"; price.textContent = `¥${number(item.price).toLocaleString("ja-JP")}`;
    link.append(rank, title, price); return link;
  }));
}

async function loadDashboard() {
  if (loading) return;
  loading = true;
  try {
    const [latestResponse, statusResponse] = await Promise.all([fetch("data/latest.json", { cache: "no-store" }), fetch("data/status.json", { cache: "no-store" })]);
    if (!latestResponse.ok || !statusResponse.ok) throw new Error("データ取得に失敗しました");
    const [latest, status] = await Promise.all([latestResponse.json(), statusResponse.json()]);
    const items = Array.isArray(latest.items) ? latest.items : [];
    const scans = number(status.total_runs);
    const totalItems = number(status.total_items_collected ?? status.items_collected);
    const exp = number(status.exp ?? scans * 5 + totalItems);
    const level = number(status.level) || Math.floor(exp / EXP_PER_LEVEL) + 1;
    const levelExp = status.level_exp == null ? exp % EXP_PER_LEVEL : number(status.level_exp);
    const target = number(status.exp_to_next_level) || EXP_PER_LEVEL;
    el("runs").textContent = number(status.runs_today).toLocaleString("ja-JP");
    el("itemCount").textContent = number(status.items_collected ?? items.length).toLocaleString("ja-JP");
    el("totalRuns").textContent = scans.toLocaleString("ja-JP"); el("totalItems").textContent = totalItems.toLocaleString("ja-JP");
    el("botAge").textContent = botAge(status.first_run || status.last_run);
    el("level").textContent = level; el("levelExp").textContent = levelExp; el("expTarget").textContent = target;
    el("totalExp").textContent = `TOTAL ${exp.toLocaleString("ja-JP")} EXP`; el("expBar").style.width = `${Math.min(100, levelExp / target * 100)}%`;
    const isLive = status.mode === "live";
    el("modeBadge").textContent = isLive ? "LIVE MODE" : "DEMO MODE"; el("modeBadge").classList.toggle("live", isLive); el("modeBadge").classList.toggle("mock", !isLive); el("demoNote").hidden = isLive;
    renderAchievements(scans, totalItems); renderItems(items);
    if (status.last_run || latest.updated_at) {
      const timestamp = status.last_run || latest.updated_at;
      const updated = new Date(timestamp);
      el("lastRun").textContent = updated.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" }); el("lastDate").textContent = updated.toLocaleDateString("ja-JP"); el("updatedAt").textContent = `UPDATED ${updated.toLocaleString("ja-JP")}`;
      if (timestamp !== knownLastRun) { knownLastRun = timestamp; nextScan = updated.getTime() + HOUR; }
      el("botStatus").classList.add("active"); el("botStatus").querySelector("span").textContent = "ONLINE";
    }
  } catch (error) {
    el("botStatus").classList.remove("active"); el("botStatus").querySelector("span").textContent = "OFFLINE";
    if (!knownLastRun) el("productList").innerHTML = `<p class="empty">${error.message}</p>`;
  } finally { loading = false; updateCountdown(); }
}

renderModules(); updateCountdown(); setInterval(updateCountdown, 1000); setInterval(loadDashboard, POLL_INTERVAL); loadDashboard();
