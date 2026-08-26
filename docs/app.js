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
const SCHEDULE_UTC_HOURS = [0, 5, 13, 18];
let nextScan = null;
let knownLastRun = null;
let loading = false;
let selectedRanking = "api";
let rankingData = { "api": { items: [] }, "1h": { items: [] }, "24h": { items: [] } };
let analyticsData = { "api": { items: [] }, "1h": { items: [] }, "24h": { items: [] } };
const expandedAnalytics = { "api": new Set(), "1h": new Set(), "24h": new Set() };
let apiExpanded = false;
let apiFilter = "all";
let apiPriceFilter = "all";
let apiGenreFilter = "all";

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

function renderModules(mode, rankings = {}) {
  const modules = ["api", "1h", "24h"].map(type => ({ name: type === "api" ? "FANZA API AUTO" : `FANZA ${type.toUpperCase()} · SPECIAL OBSERVATION`, enabled: true, status: rankings[`fanza_${type}`] || {} }));
  el("modules").replaceChildren(...modules.filter((module) => module.enabled).map((module) => {
    const card = document.createElement("article");
    card.className = "module active";
    const date = module.status.last_run ? new Date(module.status.last_run).toLocaleString("ja-JP") : "NO DATA";
    card.innerHTML = `<strong>🟢 ${module.name}</strong><small>LAST SCAN ${date}<br>ITEMS ${number(module.status.items_collected)}<br>TREND EVENTS ${number(module.status.trend_events)}</small>`;
    return card;
  }));
}

function nextScheduledRun(now = new Date()) {
  for (let day = 0; day < 2; day += 1) for (const hour of SCHEDULE_UTC_HOURS) {
    const candidate = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + day, hour, 17));
    if (candidate > now) return candidate.getTime();
  }
}
async function copyPost(text, button) {
  try { if (!navigator.clipboard) throw new Error(); await navigator.clipboard.writeText(text); }
  catch (_) { const area = document.createElement("textarea"); area.value = text; document.body.append(area); area.select(); document.execCommand("copy"); area.remove(); }
  button.textContent = "COPIED!"; setTimeout(() => { button.textContent = "COPY POST"; }, 1500);
}
function candidatePriority(item) {
  return item.ranking_type === "cross" ? 5
    : item.event_type || item.ranking_type === "sale" ? 1
    : item.current_rank <= 10 && (item.previous_rank == null || item.previous_rank > 10) ? 4
    : item.rank_change >= 5 ? 3
    : item.status === "new" || item.status === "reentry" || item.previous_rank == null ? 2
    : 0;
}

function selectCandidates(candidates) {
  const isNewFormat = (item) => Object.prototype.hasOwnProperty.call(item, "comment")
    || String(item.text || "").includes("💬 RankIdleメモ");
  const byPostingValueAndDate = (a, b) => candidatePriority(b) - candidatePriority(a)
    || (Date.parse(b.generated_at || 0) || 0) - (Date.parse(a.generated_at || 0) || 0);
  const current = candidates.filter(isNewFormat).sort(byPostingValueAndDate);
  const legacy = candidates.filter((item) => !isNewFormat(item)).sort(byPostingValueAndDate);
  return current.concat(current.length < 3 ? legacy : []).slice(0, 3);
}

function renderCandidates(candidates) {
  if (!candidates.length) return;
  const featured = selectCandidates(candidates);
  el("postCandidates").replaceChildren(...featured.map((item) => {
    const card = document.createElement("article"); card.className = "candidate";
    const heading = document.createElement("strong"); heading.textContent = `🔥 Trend Score ${item.trend_score}`;
    const title = document.createElement("p"); title.textContent = item.title;
    const movement = document.createElement("p"); movement.textContent = `${item.previous_rank ?? "NEW"} → ${item.current_rank}  ${item.rank_change > 0 ? `+${item.rank_change}` : ""}`;
    // New candidates already include their memo in text; legacy candidates remain safe.
    const completedText = item.text || "";
    const pre = document.createElement("pre"); pre.textContent = completedText;
    const button = document.createElement("button"); button.textContent = "COPY POST"; button.addEventListener("click", () => copyPost(completedText, button));
    card.append(heading, title, movement, pre, button); return card;
  }));
}

function movementFor(item) {
  const status = String(item.status || "stay").toLowerCase();
  const change = Math.abs(Number(item.rank_change) || 0);
  if (status === "up") return { status, label: `↑ +${change}` };
  if (status === "down") return { status, label: `↓ -${change}` };
  if (status === "new") return { status, label: "NEW" };
  if (status === "reentry") return { status, label: "REENTRY" };
  return { status: "stay", label: "STAY" };
}

function matchesApiFilter(item) {
  if (apiFilter === "up") return item.status === "up";
  if (apiFilter === "new") return item.status === "new" || item.status === "reentry";
  if (apiFilter === "momentum") return item.momentum === "UP" || item.strong_momentum === true;
  return true;
}

function matchesApiPriceFilter(item) {
  if (apiPriceFilter === "all") return true;
  if (item.price == null) return false;
  const price = Number(item.price);
  if (!Number.isFinite(price)) return false;
  if (apiPriceFilter === "under1000") return price >= 0 && price <= 999;
  if (apiPriceFilter === "1000to1999") return price >= 1000 && price <= 1999;
  if (apiPriceFilter === "2000to2999") return price >= 2000 && price <= 2999;
  if (apiPriceFilter === "3000plus") return price >= 3000;
  return true;
}

const GENRE_ANALYTICS_EXCLUDE_IDS = new Set(["156023", "156022", "156021"]);
const GENRE_ANALYTICS_EXCLUDE_NAMES = new Set(["成人向け", "男性向け", "専売"]);

function meaningfulGenres(item) {
  return (Array.isArray(item?.genres) ? item.genres : []).filter((genre) => {
    const name = String(genre?.name || "").trim();
    return name && !GENRE_ANALYTICS_EXCLUDE_IDS.has(String(genre?.id || "")) && !GENRE_ANALYTICS_EXCLUDE_NAMES.has(name);
  });
}

function uniqueGenreNames(genres) {
  return [...new Set(genres.map((genre) => String(genre?.name || "").trim()).filter(Boolean))];
}

function matchesApiFilters(item) {
  const genres = meaningfulGenres(item);
  return matchesApiFilter(item) && matchesApiPriceFilter(item) && (apiGenreFilter === "all" || genres.some(genre => genre?.name === apiGenreFilter));
}

function metadataLines(item) {
  const lines=[];
  if (item.circle?.name) lines.push(`🎨 ${item.circle.name}`);
  const meaningful=uniqueGenreNames(meaningfulGenres(item));
  const names=meaningful.length ? meaningful : uniqueGenreNames(Array.isArray(item.genres) ? item.genres : []);
  if (names.length) lines.push(`🏷 ${names.slice(0,3).join(" / ")}${names.length>3 ? ` +${names.length-3}` : ""}`);
  if (item.release_date) lines.push(`📅 ${String(item.release_date).replaceAll("-",".")}`);
  return lines;
}

function isNewRelease(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))) return false;
  const today=new Date(new Date().toLocaleString("en-US",{timeZone:"Asia/Tokyo"}));
  const released=new Date(`${value}T00:00:00+09:00`); const days=(today-released)/HOUR/24;
  return days>=0 && days<=7;
}

function renderRising(items) {
  const rising = items.filter((item) => item.status === "up" && Number(item.rank_change) > 0)
    .sort((a, b) => Number(b.rank_change) - Number(a.rank_change)
      || Number(a.current_rank) - Number(b.current_rank)
      || String(a.title || "").localeCompare(String(b.title || ""), "ja"))
    .slice(0, 5);
  if (!rising.length) {
    el("risingList").innerHTML = '<p class="rising-empty">まだ急上昇データはないよ。次の観測を待ってね📡</p>';
    return;
  }
  el("risingList").replaceChildren(...rising.map((item, index) => {
    const link = document.createElement("a"); link.className = "rising-item"; link.href = item.affiliate_url || item.url; link.target = "_blank"; link.rel = "noopener noreferrer sponsored";
    const order = document.createElement("small"); order.className = "rising-order"; order.textContent = `${index + 1}.`;
    const ranks = document.createElement("span"); ranks.className = "rising-ranks"; ranks.textContent = `#${item.previous_rank} → #${item.current_rank}`;
    const change = document.createElement("strong"); change.className = "rising-change"; change.textContent = `↑ +${Number(item.rank_change)}`;
    const title = document.createElement("span"); title.className = "rising-title"; title.textContent = item.title;
    const genres = document.createElement("small"); genres.className = "rising-genres"; const genreNames=uniqueGenreNames(meaningfulGenres(item)).slice(0,2); genres.textContent=genreNames.length ? `🏷 ${genreNames.join(" / ")}` : "";
    const price = document.createElement("span"); price.className = "rising-price"; price.textContent = `¥${number(item.price).toLocaleString("ja-JP")}`;
    link.append(order, ranks, change, title); if (genres.textContent) link.append(genres); link.append(price); return link;
  }));
}

function renderItems(items) {
  if (!items.length) { el("productList").innerHTML = '<p class="empty">まだ商品データがないよ。次回巡回を待ってね。</p>'; return; }
  const isApi = selectedRanking === "api";
  const filteredItems = isApi ? items.filter(matchesApiFilters) : items;
  const visibleItems = isApi && !apiExpanded ? filteredItems.slice(0, 20) : filteredItems;
  const analytics = new Map((analyticsData[selectedRanking]?.items || []).map(item => [item.key, item]));
  if (!visibleItems.length) { el("productList").innerHTML = '<p class="empty">この条件に一致する作品はないよ。</p>'; return; }
  el("productList").replaceChildren(...visibleItems.map((item) => {
    const movement = movementFor(item);
    const row = document.createElement("article");
    row.className = `product-row${isApi ? ` api-product-row rank-${movement.status}` : ""}${isApi && number(item.current_rank || item.rank) <= 10 ? " top10" : ""}`;
    const link = document.createElement("a"); link.className = "product"; link.href = isApi ? (item.affiliate_url || item.url) : item.url; link.target = "_blank"; link.rel = "noopener noreferrer sponsored";
    const rank = document.createElement("span"); rank.className = "rank"; rank.textContent = `#${item.current_rank || item.rank}`;
    const title = document.createElement("span"); title.className = "title"; title.textContent = item.title;
    const price = document.createElement("span"); price.className = "price"; price.textContent = `¥${number(item.price).toLocaleString("ja-JP")}`;
    link.append(rank, title);
    if (isApi) { const metadata=document.createElement("small"); metadata.className="product-metadata"; metadata.textContent=metadataLines(item).join("  "); if (metadata.textContent) link.append(metadata); }
    if (isApi && number(item.current_rank || item.rank) <= 10) { const badge=document.createElement("b"); badge.className="top10-badge"; badge.textContent="TOP10"; link.append(badge); }
    if (isApi && isNewRelease(item.release_date)) { const badge=document.createElement("b"); badge.className="new-release-badge"; badge.textContent="🆕 NEW RELEASE"; link.append(badge); }
    if (selectedRanking === "24h" && item.on_sale) { const badge=document.createElement("b"); badge.className="sale-badge"; badge.textContent=`${number(item.discount_rate)}% OFF`; link.append(badge); }
    link.append(price);
    if (selectedRanking === "24h" && item.regular_price) { const regular=document.createElement("small"); regular.textContent=`通常 ¥${number(item.regular_price).toLocaleString("ja-JP")}`; link.append(regular); }
    row.append(link);
    if (isApi) {
      const signals=document.createElement("div"); signals.className="api-signals";
      const change=document.createElement("strong"); change.className=`rank-change rank-${movement.status}`; change.textContent=movement.label; signals.append(change);
      if (item.strong_momentum === true) { const momentum=document.createElement("b"); momentum.className="momentum-badge strong"; momentum.textContent="🔥 MOMENTUM"; signals.append(momentum); }
      else if (item.momentum === "UP") { const momentum=document.createElement("small"); momentum.className="momentum-badge"; momentum.textContent="MOMENTUM ↑"; signals.append(momentum); }
      row.append(signals);
    }
    const key = String(item.key || item.id || item.url || "").split("?")[0];
    const insight = analytics.get(key);
    const expanded = expandedAnalytics[selectedRanking].has(key);
    const button = document.createElement("button"); button.className = "analytics-toggle"; button.type = "button"; button.textContent = expanded ? "CLOSE" : "ANALYTICS"; button.setAttribute("aria-expanded", String(expanded));
    const detail = document.createElement("div"); detail.className = "analytics-detail"; detail.hidden = !expanded;
    if (insight) {
      const history = insight.rank_history.map(rankValue => `<span>${rankValue ?? "OUT"}</span>`).join("<i>→</i>");
      const statusClass = insight.analytics_status.toLowerCase().replaceAll(" ", "-");
      detail.innerHTML = `<div><small>RANK HISTORY</small><div class="rank-history">${history}</div></div><div class="analytics-stay"><small>TOP10 / SAMPLES</small><strong>${insight.top10_count} / ${insight.sample_count}</strong><b>${insight.top10_rate}%</b></div><div><small>ANALYTICS STATUS</small><strong class="analytics-status ${statusClass}">${insight.analytics_status}</strong></div>`;
    } else detail.innerHTML = '<span class="analytics-status insufficient-data">INSUFFICIENT DATA</span>';
    if (isApi) { const meta=document.createElement("div"); meta.className="analytics-metadata"; const lines=metadataLines(item); meta.textContent=lines.length ? lines.join("\n") : "METADATA NOT AVAILABLE"; detail.append(meta); }
    button.addEventListener("click", () => {
      detail.hidden = !detail.hidden;
      if (detail.hidden) expandedAnalytics[selectedRanking].delete(key); else expandedAnalytics[selectedRanking].add(key);
      button.setAttribute("aria-expanded", String(!detail.hidden)); button.textContent = detail.hidden ? "ANALYTICS" : "CLOSE";
    });
    row.append(button, detail); return row;
  }));
}

function updateApiControls(items) {
  const isApi = selectedRanking === "api";
  el("apiFilters").hidden = !isApi;
  el("risingSection").hidden = !isApi;
  el("observedCount").hidden = !isApi;
  el("observedCount").textContent = `観測中 ${items.length.toLocaleString("ja-JP")}作品`;
  document.querySelectorAll("[data-api-filter]").forEach(button => button.classList.toggle("active", button.dataset.apiFilter === apiFilter));
  document.querySelectorAll("[data-api-price-filter]").forEach(button => button.classList.toggle("active", button.dataset.apiPriceFilter === apiPriceFilter));
  const counts=new Map(); items.forEach(item=>new Set(uniqueGenreNames(meaningfulGenres(item))).forEach(name=>counts.set(name,(counts.get(name)||0)+1)));
  const choices=[...counts].sort((a,b)=>b[1]-a[1] || a[0].localeCompare(b[0],"ja")).slice(0,10);
  if (apiGenreFilter !== "all" && !counts.has(apiGenreFilter)) apiGenreFilter="all";
  const genreBox=el("apiGenreFilters"); genreBox.replaceChildren(...[["all",null],...choices].map(([name,count])=>{ const button=document.createElement("button"); button.type="button"; button.dataset.apiGenreFilter=name; button.classList.toggle("active",name===apiGenreFilter); button.textContent=name==="all" ? "ALL" : `${name} ${count}`; button.addEventListener("click",()=>{apiGenreFilter=name;apiExpanded=false;updateApiControls(items);renderItems(items);}); return button; }));
  const matches = items.filter(matchesApiFilters).length;
  const filtered = apiFilter !== "all" || apiPriceFilter !== "all" || apiGenreFilter !== "all";
  el("filteredCount").hidden = !isApi || !filtered;
  el("filteredCount").textContent = `FILTERED ${matches}`;
  el("rankingMore").hidden = !isApi || matches <= 20;
  el("rankingMore").textContent = apiExpanded ? "閉じる" : `もっと見る（残り${matches - 20}件）`;
  el("rankingMore").setAttribute("aria-expanded", String(apiExpanded));
}

function renderSaleWatch(items) {
  const active=items.filter(item=>item.on_sale), hot=active.filter(item=>item.hot_sale);
  const soon=active.filter(item=>item.sale_end && new Date(`${item.sale_end}T23:59:59+09:00`)-Date.now()<=3*24*HOUR && new Date(`${item.sale_end}T23:59:59+09:00`)>Date.now());
  el("saleMetrics").innerHTML=[["ACTIVE SALES",active.length],["MAX DISCOUNT",`${Math.max(0,...active.map(x=>number(x.discount_rate)))}%`],["HOT SALES",hot.length],["ENDING SOON",soon.length]].map(([l,v])=>`<article><small>${l}</small><strong>${v}</strong></article>`).join("");
  const chosen=active.slice().sort((a,b)=>number(b.sale_score)-number(a.sale_score)).slice(0,5);
  if (!chosen.length) return;
  el("saleList").replaceChildren(...chosen.map((item) => {
    const card=document.createElement("article"); card.className="sale-card";
    const head=document.createElement("div"); head.className="sale-card-head";
    const discount=document.createElement("b"); discount.className="sale-badge"; discount.textContent=`${number(item.discount_rate)}% OFF`; head.append(discount);
    if (item.hot_sale) { const hotBadge=document.createElement("b"); hotBadge.className="hot-sale-badge"; hotBadge.textContent="🔥 HOT SALE"; head.append(hotBadge); }
    const title=document.createElement("h3"); title.className="sale-card-title"; title.textContent=`#${item.rank} ${item.title}`;
    const price=document.createElement("p"); price.className="sale-card-price";
    price.textContent=item.regular_price ? `通常 ¥${number(item.regular_price).toLocaleString("ja-JP")} → ¥${number(item.price).toLocaleString("ja-JP")}` : `現在 ¥${number(item.price).toLocaleString("ja-JP")}`;
    const meta=document.createElement("div"); meta.className="sale-card-meta";
    if (item.sale_end) {
      const [,month,day]=item.sale_end.split("-").map(Number);
      const remaining=new Date(`${item.sale_end}T23:59:59+09:00`)-Date.now();
      const end=document.createElement("span"); end.textContent=`END ${month}/${day}`; meta.append(end);
      if (remaining<=24*HOUR && remaining>0) { const alert=document.createElement("strong"); alert.className="ending-alert"; alert.textContent="ENDING TODAY"; meta.append(alert); }
      else if (remaining<=3*24*HOUR && remaining>0) { const alert=document.createElement("strong"); alert.className="ending-alert"; alert.textContent="ENDING SOON"; meta.append(alert); }
    }
    card.append(head,title,price,meta); return card;
  }));
}

function renderWeekly(report) {
  const partial = report.data_status !== "COMPLETE";
  el("weeklyStatus").textContent = partial ? "PARTIAL DATA" : "COMPLETE";
  el("weeklyStatus").classList.toggle("partial", partial);
  el("weeklyPeriod").textContent = `${report.week_start} — ${report.week_end} / 観測 ${number(report.observed_days)}日 / 1H ${number(report.snapshot_counts?.["1h"])}・24H ${number(report.snapshot_counts?.["24h"])} snapshots`;
  const overview=report.market_overview||{}, sale=report.sale_analysis||{}, behavior=report.ranking_behavior||{};
  el("weeklyMetrics").innerHTML=[["OBSERVED WORKS",overview.unique_products],["TOP10 WORKS",overview.top10_unique_products],["SALE SHARE",`${number(sale.sale_share)}%`],["NEW / REENTRY",`${number(overview.new_entries)} / ${number(overview.reentries)}`],["1H → 24H",overview.cross_trend_events],["RISE 10+",behavior.large_rise_10_plus]].map(([label,value])=>`<article><small>${label}</small><strong>${value??0}</strong></article>`).join("");
  el("weeklyPrices").innerHTML=(report.price_analysis?.price_buckets||[]).map(bucket=>`<p><span>${bucket.label}</span><b>${bucket.count}</b><small>TOP10 ${bucket.top10_count}</small></p>`).join("");
  const stays=report.stable_top10||report.top10_stays||[];
  el("weeklyStays").innerHTML=stays.length?stays.map(item=>`<li><span>${item.title}</span><b>${item.top10_snapshots}回観測</b></li>`).join(""):"<li>観測データなし</li>";
}

function selectRanking(type) {
  selectedRanking = type;
  document.querySelectorAll("[data-ranking]").forEach(button => button.classList.toggle("active", button.dataset.ranking === type));
  el("trendLabel").textContent = type === "api" ? "📡 API RANKING / FANZA API 人気順" : type === "1h" ? "🔥 SPECIAL OBSERVATION / 1H" : "📊 SPECIAL OBSERVATION / 24H";
  const items = rankingData[type]?.items || [];
  updateApiControls(items);
  if (type === "api") renderRising(rankingData.api.items || []);
  renderItems(items);
  const timestamp = rankingData[type]?.fetched_at;
  el("updatedAt").textContent = timestamp ? `UPDATED ${new Date(timestamp).toLocaleString("ja-JP")}` : "未取得";
}

function validateImport(value) {
  let data; try { data = JSON.parse(value); } catch (_) { return { valid: false, errors: ["JSONを解析できません"], items: [] }; }
  const items = Array.isArray(data) ? data : data?.items;
  if (!Array.isArray(data) && !["1h", "24h"].includes(data?.ranking_type)) return { valid: false, errors: ["ranking_typeは1hまたは24hが必要です"], items: [] };
  if (!Array.isArray(items) || !items.length) return { valid: false, errors: ["itemsが空です"], items: [] };
  const errors = [], ranks = new Set(), products = new Set();
  items.forEach((item, i) => {
    const at = `Item ${i + 1}`;
    if (!Number.isInteger(item?.rank) || item.rank < 1) errors.push(`${at}: rankは正の整数が必要です`);
    else if (ranks.has(item.rank)) errors.push(`${at}: rank ${item.rank} が重複しています`); else ranks.add(item.rank);
    if (!String(item?.title || "").trim()) errors.push(`${at}: titleが空です`);
    if (!String(item?.url || "").trim()) errors.push(`${at}: URLが不足しています`);
    if (!Number.isInteger(item?.price)) errors.push(`${at}: priceは整数が必要です`);
    const key = String(item?.id || item?.url || "").split("?")[0];
    if (key && products.has(key)) errors.push(`${at}: 同じ商品が重複しています`); else if (key) products.add(key);
  });
  return { valid: !errors.length, errors, items };
}

async function setupImportTools() {
  el("copyBookmarklet").addEventListener("click", async () => {
    const source = await fetch("bookmarklet.js").then((response) => response.text());
    const bookmarklet = RankIdleBookmarklet.minify(source);
    await copyPost(bookmarklet, el("copyBookmarklet"));
    el("bookmarkletResult").textContent = " ブックマークのURL欄へ貼り付けてください";
  });
  el("importJson").addEventListener("input", ({ target }) => {
    if (!target.value.trim()) return;
    const result = validateImport(target.value), box = el("validationResult"); box.className = `validation ${result.valid ? "valid" : "invalid"}`;
    const ranks = result.items.map((item) => item.rank).filter(Number.isInteger);
    box.textContent = result.valid ? `VALID / IMPORT READY\nItems: ${result.items.length}\nRank: ${Math.min(...ranks)} - ${Math.max(...ranks)}\nErrors: 0` : `INVALID\n${result.errors.join("\n")}`;
    el("importPreview").replaceChildren(...(result.valid ? result.items : []).map((item) => { const card=document.createElement("article"); card.className="product"; card.textContent=`#${item.rank} ${item.title}\n¥${number(item.price).toLocaleString("ja-JP")}`; return card; }));
  });
}

async function loadDashboard() {
  if (loading) return;
  loading = true;
  try {
    const [latestResponse, statusResponse, postsApi, posts1h, posts24h, rankApi, rank1h, rank24h, analyticsApi, analytics1h, analytics24h, weekly] = await Promise.all([fetch("data/latest.json", { cache: "no-store" }), fetch("data/status.json", { cache: "no-store" }), fetch("data/posts/fanza_api_candidates.json", { cache: "no-store" }).catch(() => null), fetch("data/posts/fanza_1h_candidates.json", { cache: "no-store" }).catch(() => null), fetch("data/posts/fanza_24h_candidates.json", { cache: "no-store" }).catch(() => null), fetch("data/fanza/api/current.json", { cache: "no-store" }).catch(() => null), fetch("data/fanza/1h/current.json", { cache: "no-store" }).catch(() => null), fetch("data/fanza/24h/current.json", { cache: "no-store" }).catch(() => null), fetch("data/analytics/fanza_api.json", { cache: "no-store" }).catch(() => null), fetch("data/analytics/fanza_1h.json", { cache: "no-store" }).catch(() => null), fetch("data/analytics/fanza_24h.json", { cache: "no-store" }).catch(() => null), fetch("data/reports/weekly/latest.json", { cache: "no-store" }).catch(() => null)]);
    if (!latestResponse.ok || !statusResponse.ok) throw new Error("データ取得に失敗しました");
    const [latest, status] = await Promise.all([latestResponse.json(), statusResponse.json()]);
    const items = Array.isArray(latest.items) ? latest.items : [];
    rankingData = { "api": rankApi?.ok ? await rankApi.json() : { items: [] }, "1h": rank1h?.ok ? await rank1h.json() : { items: [] }, "24h": rank24h?.ok ? await rank24h.json() : { items: [] } };
    analyticsData = { "api": analyticsApi?.ok ? await analyticsApi.json() : { items: [] }, "1h": analytics1h?.ok ? await analytics1h.json() : { items: [] }, "24h": analytics24h?.ok ? await analytics24h.json() : { items: [] } };
    const candidates = [...(postsApi?.ok ? await postsApi.json() : []), ...(posts1h?.ok ? await posts1h.json() : []), ...(posts24h?.ok ? await posts24h.json() : [])];
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
    const mode = ["live", "public", "import"].includes(status.mode) ? status.mode : "mock";
    const publicError = mode === "public" && status.public_watch_status === "error";
    const ageGate = mode === "public" && status.public_watch_status === "age_gate";
    el("modeBadge").textContent = ageGate ? "PUBLIC WATCH: AGE GATE" : publicError ? "PUBLIC WATCH ERROR" : mode === "live" ? "LIVE MODE" : mode === "import" ? "🟡 FANZA SEMI AUTO" : mode === "public" ? "PUBLIC WATCH" : "DEMO MODE";
    el("modeSubtitle").textContent = ageGate ? "FANZA AGE VERIFICATION REACHED / NO BYPASS" : mode === "live" ? "DMM API CONNECTED" : mode === "import" ? "MANUAL RANKING IMPORT" : mode === "public" ? "PUBLIC RANKING DATA" : "SAMPLE DATA"; el("modeBadge").className = `mode-badge ${mode}`; el("demoNote").hidden = mode !== "mock";
    renderModules(mode, status.rankings); renderAchievements(scans, totalItems); selectRanking(selectedRanking); renderCandidates(candidates);
    renderSaleWatch(rankingData["24h"]?.items || []);
    if (weekly?.ok) renderWeekly(await weekly.json());
    const signals = status.market_signals || {};
    el("marketSignals").innerHTML = [["1H MAX RISE", signals["1h_max_rise"]], ["24H MAX RISE", signals["24h_max_rise"]], ["CROSS TREND", signals.cross_trend], ["ACTIVE SALES",signals.active_sales],["HOT SALES",signals.hot_sales],["MAX DISCOUNT",`${number(signals.max_discount)}%`]].map(([label,value]) => `<article><small>${label}</small><strong>${label.includes("RISE") && number(value) ? "+" : ""}${value ?? 0}</strong></article>`).join("");
    if (status.last_run || latest.updated_at) {
      const timestamp = status.last_run || latest.updated_at;
      const updated = new Date(timestamp);
      el("lastRun").textContent = updated.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" }); el("lastDate").textContent = updated.toLocaleDateString("ja-JP"); el("updatedAt").textContent = `UPDATED ${updated.toLocaleString("ja-JP")}`;
      if (timestamp !== knownLastRun) { knownLastRun = timestamp; nextScan = nextScheduledRun(); }
      el("botStatus").classList.add("active"); el("botStatus").querySelector("span").textContent = "ONLINE";
    }
  } catch (error) {
    el("botStatus").classList.remove("active"); el("botStatus").querySelector("span").textContent = "OFFLINE";
    if (!knownLastRun) el("productList").innerHTML = `<p class="empty">${error.message}</p>`;
  } finally { loading = false; updateCountdown(); }
}

document.querySelectorAll("[data-ranking]").forEach(button => button.addEventListener("click", () => selectRanking(button.dataset.ranking)));
document.querySelectorAll("[data-api-filter]").forEach(button => button.addEventListener("click", () => { apiFilter = button.dataset.apiFilter; apiExpanded = false; updateApiControls(rankingData.api.items || []); renderItems(rankingData.api.items || []); }));
document.querySelectorAll("[data-api-price-filter]").forEach(button => button.addEventListener("click", () => { apiPriceFilter = button.dataset.apiPriceFilter; apiExpanded = false; updateApiControls(rankingData.api.items || []); renderItems(rankingData.api.items || []); }));
el("rankingMore").addEventListener("click", () => { apiExpanded = !apiExpanded; updateApiControls(rankingData.api.items || []); renderItems(rankingData.api.items || []); if (!apiExpanded) el("trendLabel").scrollIntoView({ behavior: "smooth", block: "start" }); });
updateCountdown(); setInterval(updateCountdown, 1000); setInterval(loadDashboard, POLL_INTERVAL); setupImportTools(); loadDashboard();
