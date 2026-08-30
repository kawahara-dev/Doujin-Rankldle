const HOUR = 60 * 60 * 1000;
const SCANNING_TIME = 5000;
const POLL_INTERVAL = 15000;
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
let weeklyGenreExpanded = false;
let mobileGenresExpanded = false;
let onboardingExpanded = false;

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

function nextScheduledRun(now = new Date()) {
  for (let day = 0; day < 2; day += 1) for (const hour of SCHEDULE_UTC_HOURS) {
    const candidate = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + day, hour, 17));
    if (candidate > now) return candidate.getTime();
  }
}
// Kept as pure compatibility helpers for candidate-generation tests; rendering lives in ops.js.
function candidatePriority(item) {
  return item.ranking_type === "cross" ? 5
    : item.event_type || item.ranking_type === "sale" ? 1
    : item.current_rank <= 10 && (item.previous_rank == null || item.previous_rank > 10) ? 4
    : item.rank_change >= 5 ? 3
    : item.status === "new" || item.status === "reentry" || item.previous_rank == null ? 2
    : 0;
}
function selectCandidates(candidates) {
  const isNewFormat = (item) => Object.prototype.hasOwnProperty.call(item, "comment") || String(item.text || "").includes("💬 RankIdleメモ");
  const byPostingValueAndDate = (a, b) => candidatePriority(b) - candidatePriority(a) || (Date.parse(b.generated_at || 0) || 0) - (Date.parse(a.generated_at || 0) || 0);
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
    const completedText = item.text || "";
    const pre = document.createElement("pre"); pre.textContent = completedText;
    const button = document.createElement("button"); button.textContent = "COPY POST";
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

function safeImageUrl(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const url = new URL(value.trim());
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch (_) { return null; }
}

function createThumbnail(item) {
  const thumbnail = document.createElement("span"); thumbnail.className = "product-thumbnail no-image";
  const placeholder = document.createElement("span"); placeholder.className = "thumbnail-placeholder"; placeholder.textContent = "NO IMAGE"; thumbnail.append(placeholder);
  const source = safeImageUrl(item.image_url);
  if (!source) return thumbnail;
  const image = document.createElement("img"); image.src = source;
  image.alt = String(item.title || "").trim() ? `${String(item.title).trim()} サムネイル` : "";
  image.loading = "lazy"; image.decoding = "async";
  image.addEventListener("load", () => thumbnail.classList.remove("no-image"), { once: true });
  image.addEventListener("error", () => image.remove(), { once: true });
  thumbnail.append(image); return thumbnail;
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
    const genres = document.createElement("small"); genres.className = "rising-genres"; const genreNames=uniqueGenreNames(meaningfulGenres(item)); genres.textContent=genreNames.length ? `🏷 ${genreNames.slice(0,2).join(" / ")}` : "";
    if (genreNames.length) genres.dataset.mobileText = `🏷 ${genreNames[0]}`;
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
    const content = document.createElement("span"); content.className = "product-content";
    const productBody = isApi ? content : link;
    const rank = document.createElement("span"); rank.className = "rank"; rank.textContent = `#${item.current_rank || item.rank}`;
    const title = document.createElement("span"); title.className = "title"; title.textContent = item.title;
    const price = document.createElement("span"); price.className = "price"; price.textContent = `¥${number(item.price).toLocaleString("ja-JP")}`;
    productBody.append(rank, title);
    if (isApi) {
      const metadata=document.createElement("small"); metadata.className="product-metadata";
      if (item.circle?.name) { const circle=document.createElement("span"); circle.className="metadata-circle"; circle.textContent=`🎨 ${item.circle.name}`; metadata.append(circle); }
      const meaningful=uniqueGenreNames(meaningfulGenres(item));
      const genreNames=meaningful.length ? meaningful : uniqueGenreNames(Array.isArray(item.genres) ? item.genres : []);
      if (genreNames.length) {
        const genres=document.createElement("span"); genres.className="metadata-genres desktop-genres"; genres.textContent=`🏷 ${genreNames.slice(0,3).join(" / ")}${genreNames.length>3 ? ` +${genreNames.length-3}` : ""}`;
        const mobileGenres=document.createElement("span"); mobileGenres.className="metadata-genres mobile-genres"; mobileGenres.textContent=`🏷 ${genreNames.slice(0,2).join(" / ")}${genreNames.length>2 ? ` +${genreNames.length-2}` : ""}`;
        metadata.append(genres,mobileGenres);
      }
      if (item.release_date) { const release=document.createElement("span"); release.className="metadata-release"; release.textContent=`📅 ${String(item.release_date).replaceAll("-", ".")}`; metadata.append(release); }
      if (metadata.childElementCount) productBody.append(metadata);
    }
    if (isApi && number(item.current_rank || item.rank) <= 10) { const badge=document.createElement("b"); badge.className="top10-badge"; badge.textContent="TOP10"; productBody.append(badge); }
    if (isApi && isNewRelease(item.release_date)) { const badge=document.createElement("b"); badge.className="new-release-badge"; badge.textContent="🆕 NEW RELEASE"; productBody.append(badge); }
    if (selectedRanking === "24h" && item.on_sale) { const badge=document.createElement("b"); badge.className="sale-badge"; badge.textContent=`${number(item.discount_rate)}% OFF`; link.append(badge); }
    productBody.append(price);
    if (selectedRanking === "24h" && item.regular_price) { const regular=document.createElement("small"); regular.textContent=`通常 ¥${number(item.regular_price).toLocaleString("ja-JP")}`; link.append(regular); }
    if (isApi) link.append(createThumbnail(item), content);
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
  el("weeklyGenreWatch").hidden = !isApi;
  el("observedCount").hidden = !isApi;
  el("observedCount").textContent = `観測中 ${items.length.toLocaleString("ja-JP")}作品`;
  document.querySelectorAll("[data-api-filter]").forEach(button => button.classList.toggle("active", button.dataset.apiFilter === apiFilter));
  document.querySelectorAll("[data-api-price-filter]").forEach(button => button.classList.toggle("active", button.dataset.apiPriceFilter === apiPriceFilter));
  const counts=new Map(); items.forEach(item=>new Set(uniqueGenreNames(meaningfulGenres(item))).forEach(name=>counts.set(name,(counts.get(name)||0)+1)));
  const choices=[...counts].sort((a,b)=>b[1]-a[1] || a[0].localeCompare(b[0],"ja")).slice(0,10);
  if (apiGenreFilter !== "all" && !counts.has(apiGenreFilter)) apiGenreFilter="all";
  const genreBox=el("apiGenreFilters");
  const genreButtons=[["all",null],...choices].map(([name,count],index)=>{ const button=document.createElement("button"); button.type="button"; button.dataset.apiGenreFilter=name; button.classList.toggle("active",name===apiGenreFilter); if(index>5) button.classList.add("mobile-extra-genre"); button.hidden=index>5&&!mobileGenresExpanded; button.textContent=name==="all" ? "ALL" : `${name} ${count}`; button.addEventListener("click",()=>{apiGenreFilter=name;apiExpanded=false;updateApiControls(items);renderItems(items);}); return button; });
  if(choices.length>5) { const more=document.createElement("button"); more.type="button"; more.className="more-genres"; more.textContent=mobileGenresExpanded?"FEWER GENRES":"MORE GENRES"; more.setAttribute("aria-expanded",String(mobileGenresExpanded)); more.addEventListener("click",()=>{mobileGenresExpanded=!mobileGenresExpanded;updateApiControls(items);}); genreButtons.push(more); }
  genreBox.replaceChildren(...genreButtons);
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

function createWeeklyGenreCard(genre, rank) {
  const observed=number(genre?.observed_products),top10=number(genre?.top10_products);
  const rate=observed>0 ? top10/observed*100 : 0;
  const card=document.createElement("article"),rankLabel=document.createElement("b"),name=document.createElement("strong"),counts=document.createElement("span"),top=document.createElement("small"),rateRow=document.createElement("div"),rateLabel=document.createElement("small"),bar=document.createElement("i");
  rankLabel.textContent=`#${rank}`; name.textContent=String(genre?.name||"名称不明"); counts.textContent=`${observed.toLocaleString("ja-JP")}作品`; top.textContent=`TOP10 ${top10.toLocaleString("ja-JP")}`;
  rateRow.className="genre-watch-rate"; rateLabel.textContent=`TOP10観測率 ${rate.toFixed(1)}%`; bar.setAttribute("role","img"); bar.setAttribute("aria-label",`TOP10観測率 ${rate.toFixed(1)}%`); bar.style.setProperty("--genre-rate",`${Math.min(100,Math.max(0,rate))}%`); rateRow.append(rateLabel,bar);
  card.append(rankLabel,name,counts,top,rateRow); return card;
}

function renderWeeklyGenreWatch(report) {
  if (!report || typeof report !== "object") {
    el("weeklyGenreContent").innerHTML = '<p class="genre-watch-empty">まだ週次データがないよ。<br>観測データが溜まるのを待ってね📡</p>';
    el("weeklyGenreStatus").hidden = true; el("weeklyGenrePartial").hidden = true;
    el("weeklyGenrePeriod").textContent = ""; el("weeklyGenreUpdated").textContent = "";
    el("weeklyGenreDetailsButton").hidden = true; el("weeklyGenreDetails").hidden = true; return;
  }
  const partial=report.data_status==="PARTIAL"; el("weeklyGenreStatus").hidden=!partial; el("weeklyGenrePartial").hidden=!partial;
  el("weeklyGenrePeriod").textContent=report.week_start&&report.week_end?`PERIOD ${report.week_start} → ${report.week_end}`:"";
  const generated=report.generated_at?new Date(report.generated_at):null; el("weeklyGenreUpdated").textContent=generated&&!Number.isNaN(generated.getTime())?`GENERATED ${generated.toLocaleString("ja-JP",{year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"})}`:"";
  const genres=Array.isArray(report.top_genres)?report.top_genres:[],topGenres=genres.slice(0,3),detailGenres=genres.slice(3,10),group=document.createElement("div"),heading=document.createElement("h4"),list=document.createElement("div"); group.className="genre-watch-group"; heading.textContent="🏷 TOP GENRES"; list.className="genre-watch-list"; group.append(heading);
  if(topGenres.length) list.append(...topGenres.map((genre,index)=>createWeeklyGenreCard(genre,index+1))); else { const empty=document.createElement("p"); empty.className="genre-watch-empty compact"; empty.textContent="ジャンル観測データなし"; list.append(empty); } group.append(list);
  const summary=document.createElement("div");summary.className="genre-watch-summary";[["🆕 NEW RELEASE",`${number(report.new_release_products).toLocaleString("ja-JP")}作品`,`${number(report.new_release_share).toLocaleString("ja-JP")}%`],["🔥 NEW × TOP10",`${number(report.new_release_top10_products).toLocaleString("ja-JP")}作品`,""]].forEach(([title,value,note])=>{const card=document.createElement("article"),h=document.createElement("h4"),strong=document.createElement("strong"),small=document.createElement("small");h.textContent=title;strong.textContent=value;small.textContent=note;card.append(h,strong);if(note)card.append(small);summary.append(card);});el("weeklyGenreContent").replaceChildren(group,summary);
  const detailList=el("weeklyGenreDetailList"); if(detailGenres.length) detailList.replaceChildren(...detailGenres.map((genre,index)=>createWeeklyGenreCard(genre,index+4))); else { const empty=document.createElement("p"); empty.className="genre-watch-empty compact"; empty.textContent="追加のジャンル観測データなし"; detailList.replaceChildren(empty); }
  const prices=(Array.isArray(report.genre_price_summary)?report.genre_price_summary:[]).slice(0,10);el("weeklyGenrePrices").replaceChildren(...prices.map(item=>{const row=document.createElement("p"),name=document.createElement("span"),price=document.createElement("b");name.textContent=String(item?.name||"名称不明");price.textContent=`¥${number(item?.median_price).toLocaleString("ja-JP")}`;row.append(name,price);return row;}));
  const coverage=report.metadata_coverage||{},total=number(coverage.total_products);el("weeklyGenreCoverage").replaceChildren(...[["GENRE",coverage.genre],["RELEASE DATE",coverage.release_date]].map(([label,value])=>{const row=document.createElement("p"),name=document.createElement("span"),count=document.createElement("b");name.textContent=label;count.textContent=`${number(value).toLocaleString("ja-JP")} / ${total.toLocaleString("ja-JP")}`;row.append(name,count);return row;}));
  const hasDetails=detailGenres.length>0||prices.length>0||total>0||report.week_start||report.week_end||report.generated_at||report.methodology_note;el("weeklyGenreDetailsButton").hidden=!hasDetails;el("weeklyGenreDetailsButton").textContent=weeklyGenreExpanded?"HIDE DETAILS":"DETAILS";el("weeklyGenreDetailsButton").setAttribute("aria-expanded",String(weeklyGenreExpanded));el("weeklyGenreDetails").hidden=!hasDetails||!weeklyGenreExpanded;
  el("weeklyGenreMethodology").textContent=report.methodology_note?String(report.methodology_note):"※RankIdleが保存したFANZA APIランキング観測データによる集計です。\n販売数・売上を示すものではありません。";
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

async function loadDashboard() {
  if (loading) return;
  loading = true;
  try {
    const [latestResponse, statusResponse, rankApi, rank1h, rank24h, analyticsApi, analytics1h, analytics24h, weekly] = await Promise.all([fetch("data/latest.json", { cache: "no-store" }), fetch("data/status.json", { cache: "no-store" }), fetch("data/fanza/api/current.json", { cache: "no-store" }).catch(() => null), fetch("data/fanza/1h/current.json", { cache: "no-store" }).catch(() => null), fetch("data/fanza/24h/current.json", { cache: "no-store" }).catch(() => null), fetch("data/analytics/fanza_api.json", { cache: "no-store" }).catch(() => null), fetch("data/analytics/fanza_1h.json", { cache: "no-store" }).catch(() => null), fetch("data/analytics/fanza_24h.json", { cache: "no-store" }).catch(() => null), fetch("data/reports/weekly/latest.json", { cache: "no-store" }).catch(() => null)]);
    if (!latestResponse.ok || !statusResponse.ok) throw new Error("データ取得に失敗しました");
    const [latest, status] = await Promise.all([latestResponse.json(), statusResponse.json()]);
    const items = Array.isArray(latest.items) ? latest.items : [];
    rankingData = { "api": rankApi?.ok ? await rankApi.json() : { items: [] }, "1h": rank1h?.ok ? await rank1h.json() : { items: [] }, "24h": rank24h?.ok ? await rank24h.json() : { items: [] } };
    analyticsData = { "api": analyticsApi?.ok ? await analyticsApi.json() : { items: [] }, "1h": analytics1h?.ok ? await analytics1h.json() : { items: [] }, "24h": analytics24h?.ok ? await analytics24h.json() : { items: [] } };
    selectRanking(selectedRanking);
    renderSaleWatch(rankingData["24h"]?.items || []);
    let weeklyReport = null;
    if (weekly?.ok) { try { weeklyReport = await weekly.json(); } catch (_) { weeklyReport = null; } }
    if (weeklyReport) renderWeekly(weeklyReport);
    renderWeeklyGenreWatch(weeklyReport);
    const signals = status.market_signals || {};
    el("marketSignals").innerHTML = [["1H MAX RISE", signals["1h_max_rise"]], ["24H MAX RISE", signals["24h_max_rise"]], ["CROSS TREND", signals.cross_trend], ["ACTIVE SALES",signals.active_sales],["HOT SALES",signals.hot_sales],["MAX DISCOUNT",`${number(signals.max_discount)}%`]].map(([label,value]) => `<article><small>${label}</small><strong>${label.includes("RISE") && number(value) ? "+" : ""}${value ?? 0}</strong></article>`).join("");
    if (status.last_run || latest.updated_at) {
      const timestamp = status.last_run || latest.updated_at;
      const updated = new Date(timestamp);
      el("updatedAt").textContent = `UPDATED ${updated.toLocaleString("ja-JP")}`;
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
el("weeklyGenreDetailsButton").addEventListener("click", () => { weeklyGenreExpanded=!weeklyGenreExpanded; el("weeklyGenreDetails").hidden=!weeklyGenreExpanded; el("weeklyGenreDetailsButton").textContent=weeklyGenreExpanded?"HIDE DETAILS":"DETAILS"; el("weeklyGenreDetailsButton").setAttribute("aria-expanded",String(weeklyGenreExpanded)); });
function setOnboardingExpanded(expanded) {
  onboardingExpanded = expanded;
  el("onboardingGuide").hidden = !expanded;
  el("onboardingGuide").setAttribute("aria-hidden", String(!expanded));
  el("onboardingToggle").setAttribute("aria-expanded", String(expanded));
  el("onboardingToggle").textContent = expanded ? "HIDE GUIDE" : "HOW TO READ";
}
el("onboardingToggle").addEventListener("click", () => setOnboardingExpanded(!onboardingExpanded));
el("onboardingClose").addEventListener("click", () => setOnboardingExpanded(false));
updateCountdown(); setInterval(updateCountdown, 1000); setInterval(loadDashboard, POLL_INTERVAL); loadDashboard();
