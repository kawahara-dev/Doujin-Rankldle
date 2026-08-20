const HOUR = 60 * 60 * 1000;
let nextScan = Date.now() + HOUR;

const el = (id) => document.getElementById(id);
const pad = (number) => String(number).padStart(2, "0");

function updateCountdown() {
  const remaining = Math.max(0, nextScan - Date.now());
  const seconds = Math.floor(remaining / 1000);
  el("countdown").textContent = `${pad(Math.floor(seconds / 3600))}:${pad(Math.floor(seconds % 3600 / 60))}:${pad(seconds % 60)}`;
}

function renderItems(items) {
  if (!items.length) {
    el("productList").innerHTML = '<p class="empty">まだ商品データがないよ。次回巡回を待ってね。</p>';
    return;
  }
  el("productList").replaceChildren(...items.map((item) => {
    const link = document.createElement("a");
    link.className = "product";
    link.href = item.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer sponsored";
    const rank = document.createElement("span"); rank.className = "rank"; rank.textContent = `#${item.rank}`;
    const title = document.createElement("span"); title.className = "title"; title.textContent = item.title;
    const price = document.createElement("span"); price.className = "price"; price.textContent = `¥${Number(item.price).toLocaleString("ja-JP")}`;
    link.append(rank, title, price);
    return link;
  }));
}

async function loadDashboard() {
  try {
    const [latestResponse, statusResponse] = await Promise.all([
      fetch("data/latest.json", { cache: "no-store" }),
      fetch("data/status.json", { cache: "no-store" }),
    ]);
    if (!latestResponse.ok || !statusResponse.ok) throw new Error("データ取得に失敗しました");
    const [latest, status] = await Promise.all([latestResponse.json(), statusResponse.json()]);
    const items = Array.isArray(latest.items) ? latest.items : [];
    el("runs").textContent = status.runs_today ?? 0;
    el("itemCount").textContent = items.length;
    const isLive = status.mode === "live";
    el("modeBadge").textContent = isLive ? "LIVE MODE" : "DEMO MODE";
    el("modeBadge").classList.toggle("live", isLive);
    el("modeBadge").classList.toggle("mock", !isLive);
    renderItems(items);
    if (latest.updated_at) {
      const updated = new Date(latest.updated_at);
      el("lastRun").textContent = updated.toLocaleTimeString("ja-JP", { hour:"2-digit", minute:"2-digit" });
      el("lastDate").textContent = updated.toLocaleDateString("ja-JP");
      el("updatedAt").textContent = `UPDATED ${updated.toLocaleString("ja-JP")}`;
      nextScan = updated.getTime() + HOUR;
      while (nextScan < Date.now()) nextScan += HOUR;
      el("botStatus").classList.add("active");
      el("botStatus").lastChild.textContent = " ONLINE";
    }
  } catch (error) {
    el("botStatus").lastChild.textContent = " OFFLINE";
    el("productList").innerHTML = `<p class="empty">${error.message}</p>`;
  }
}

updateCountdown();
setInterval(updateCountdown, 1000);
loadDashboard();
