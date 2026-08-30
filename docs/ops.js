const EXP_PER_LEVEL = 100;
const POLL_INTERVAL = 15000;
const ACHIEVEMENTS = [
  { name: "FIRST BOOT", kind: "scans", target: 1 }, { name: "SCANNER I", kind: "scans", target: 10 },
  { name: "SCANNER II", kind: "scans", target: 100 }, { name: "SCANNER III", kind: "scans", target: 1000 },
  { name: "DATA COLLECTOR I", kind: "items", target: 100 }, { name: "DATA COLLECTOR II", kind: "items", target: 1000 },
  { name: "DATA COLLECTOR III", kind: "items", target: 10000 },
];
const el = (id) => document.getElementById(id);
const number = (value) => Math.max(0, Number(value) || 0);
const formatDate = (value) => value ? new Date(value).toLocaleString("ja-JP") : "NO DATA";

function renderAchievements(scans, items) {
  el("achievements").replaceChildren(...ACHIEVEMENTS.map((achievement) => {
    const current = achievement.kind === "scans" ? scans : items;
    const unlocked = current >= achievement.target;
    const card = document.createElement("article"); card.className = `achievement ${unlocked ? "unlocked" : "locked"}`;
    const title = document.createElement("strong"); title.textContent = `${unlocked ? "🏆" : "🔒"} ${achievement.name}`;
    const progress = document.createElement("small"); progress.textContent = unlocked ? "UNLOCKED" : `${Math.min(current, achievement.target).toLocaleString("ja-JP")} / ${achievement.target.toLocaleString("ja-JP")} ${achievement.kind}`;
    card.append(title, progress); return card;
  }));
}
function renderModules(rankings = {}) {
  const modules = ["api", "1h", "24h"].map((type) => ({ name: type === "api" ? "FANZA API AUTO" : `FANZA ${type.toUpperCase()} · SPECIAL OBSERVATION`, status: rankings[`fanza_${type}`] || {} }));
  el("modules").replaceChildren(...modules.map((module) => {
    const card = document.createElement("article"); card.className = "module active";
    card.innerHTML = `<strong>🟢 ${module.name}</strong><small>LAST SCAN ${formatDate(module.status.last_run)}<br>ITEMS ${number(module.status.items_collected)}<br>TOTAL RUNS ${number(module.status.total_runs)}<br>TREND EVENTS ${number(module.status.trend_events)}</small>`;
    return card;
  }));
}
async function copyText(text, button) {
  try { if (!navigator.clipboard) throw new Error(); await navigator.clipboard.writeText(text); }
  catch (_) { const area = document.createElement("textarea"); area.value = text; document.body.append(area); area.select(); document.execCommand("copy"); area.remove(); }
  button.textContent = "COPIED!"; setTimeout(() => { button.textContent = button.id === "copyBookmarklet" ? "COPY BOOKMARKLET" : "COPY POST"; }, 1500);
}
function candidatePriority(item) { return item.ranking_type === "cross" ? 5 : item.event_type || item.ranking_type === "sale" ? 1 : item.current_rank <= 10 && (item.previous_rank == null || item.previous_rank > 10) ? 4 : item.rank_change >= 5 ? 3 : item.status === "new" || item.status === "reentry" || item.previous_rank == null ? 2 : 0; }
function renderCandidates(candidates) {
  const current = candidates.filter((item) => Object.prototype.hasOwnProperty.call(item, "comment") || String(item.text || "").includes("💬 RankIdleメモ"));
  const featured = (current.length >= 3 ? current : current.concat(candidates.filter((item) => !current.includes(item)))).sort((a, b) => candidatePriority(b) - candidatePriority(a) || (Date.parse(b.generated_at || 0) || 0) - (Date.parse(a.generated_at || 0) || 0)).slice(0, 3);
  if (!featured.length) return;
  el("postCandidates").replaceChildren(...featured.map((item) => { const card=document.createElement("article");card.className="candidate";const heading=document.createElement("strong");heading.textContent=`🔥 Trend Score ${item.trend_score}`;const title=document.createElement("p");title.textContent=item.title;const movement=document.createElement("p");movement.textContent=`${item.previous_rank ?? "NEW"} → ${item.current_rank}  ${item.rank_change > 0 ? `+${item.rank_change}` : ""}`;const pre=document.createElement("pre");pre.textContent=item.text || "";const button=document.createElement("button");button.textContent="COPY POST";button.addEventListener("click",()=>copyText(item.text || "",button));card.append(heading,title,movement,pre,button);return card;}));
}
function validateImport(value) {
  let data; try { data = JSON.parse(value); } catch (_) { return { valid:false, errors:["JSONを解析できません"], items:[] }; }
  const items=Array.isArray(data)?data:data?.items;if(!Array.isArray(data)&&!["1h","24h"].includes(data?.ranking_type))return{valid:false,errors:["ranking_typeは1hまたは24hが必要です"],items:[]};if(!Array.isArray(items)||!items.length)return{valid:false,errors:["itemsが空です"],items:[]};
  const errors=[],ranks=new Set(),products=new Set();items.forEach((item,i)=>{const at=`Item ${i+1}`;if(!Number.isInteger(item?.rank)||item.rank<1)errors.push(`${at}: rankは正の整数が必要です`);else if(ranks.has(item.rank))errors.push(`${at}: rank ${item.rank} が重複しています`);else ranks.add(item.rank);if(!String(item?.title||"").trim())errors.push(`${at}: titleが空です`);if(!String(item?.url||"").trim())errors.push(`${at}: URLが不足しています`);if(!Number.isInteger(item?.price))errors.push(`${at}: priceは整数が必要です`);const key=String(item?.id||item?.url||"").split("?")[0];if(key&&products.has(key))errors.push(`${at}: 同じ商品が重複しています`);else if(key)products.add(key);});return{valid:!errors.length,errors,items};
}
function setupTools() {
  el("copyBookmarklet").addEventListener("click",async()=>{const source=await fetch("../bookmarklet.js").then((response)=>response.text());await copyText(RankIdleBookmarklet.minify(source),el("copyBookmarklet"));el("bookmarkletResult").textContent=" ブックマークのURL欄へ貼り付けてください";});
  el("importJson").addEventListener("input",({target})=>{if(!target.value.trim())return;const result=validateImport(target.value),box=el("validationResult"),ranks=result.items.map((item)=>item.rank).filter(Number.isInteger);box.className=`validation ${result.valid?"valid":"invalid"}`;box.textContent=result.valid?`VALID / IMPORT READY\nItems: ${result.items.length}\nRank: ${Math.min(...ranks)} - ${Math.max(...ranks)}\nErrors: 0`:`INVALID\n${result.errors.join("\n")}`;el("importPreview").replaceChildren(...(result.valid?result.items:[]).map((item)=>{const card=document.createElement("article");card.className="product";card.textContent=`#${item.rank} ${item.title}\n¥${number(item.price).toLocaleString("ja-JP")}`;return card;}));});
}
function diagnostic(label, value) { const row=document.createElement("div"),term=document.createElement("dt"),detail=document.createElement("dd");term.textContent=label;detail.textContent=String(value ?? "NO DATA");row.append(term,detail);return row; }
async function loadOps() {
  try {
    const responses=await Promise.all([fetch("../data/status.json",{cache:"no-store"}),...['fanza_api','fanza_1h','fanza_24h'].map((name)=>fetch(`../data/posts/${name}_candidates.json`,{cache:"no-store"}).catch(()=>null))]);if(!responses[0].ok)throw new Error("status.json unavailable");const status=await responses[0].json(),rankings=status.rankings||{},api=rankings.fanza_api||{},scans=number(status.total_runs),items=number(status.total_items_collected??status.items_collected),exp=number(status.exp??scans*5+items),level=number(status.level)||Math.floor(exp/EXP_PER_LEVEL)+1,levelExp=status.level_exp==null?exp%EXP_PER_LEVEL:number(status.level_exp),target=number(status.exp_to_next_level)||EXP_PER_LEVEL;
    el("systemState").textContent="ONLINE";el("modeBadge").textContent=String(status.mode||"UNKNOWN").toUpperCase();el("modeBadge").className=`mode-badge ${status.mode||"mock"}`;el("level").textContent=level;el("levelExp").textContent=levelExp;el("expTarget").textContent=target;el("totalExp").textContent=`TOTAL ${exp.toLocaleString("ja-JP")} EXP`;el("expBar").style.width=`${Math.min(100,levelExp/target*100)}%`;
    const collectors=[{name:"FANZA",data:api},{name:"DLsite",data:rankings.dlsite||{}}];el("collectorStatus").replaceChildren(...collectors.map(({name,data})=>{const card=document.createElement("article"),online=Boolean(data.last_run);card.className=`collector-card ${online?"":"offline"}`;card.innerHTML=`<strong>${online?"✅ ONLINE":"○ NO STATUS DATA"} · ${name}</strong><small>LAST RUN ${formatDate(data.last_run)}<br>ITEMS ${number(data.items_collected)}</small>`;return card;}));
    el("collectionStats").innerHTML=[["RUNS TODAY",status.runs_today],["TOTAL RUNS",scans],["LAST ITEMS",status.items_collected],["TOTAL ITEMS",items]].map(([label,value])=>`<article><p class="label">${label}</p><strong>${number(value).toLocaleString("ja-JP")}</strong></article>`).join("");
    el("diagnostics").replaceChildren(diagnostic("LAST RUN",formatDate(status.last_run)),diagnostic("LAST ERROR",status.last_public_watch_error||"NONE"),diagnostic("INPUT SOURCE",status.input_source),diagnostic("DUPLICATE IMPORT",status.duplicate_import),diagnostic("DUPLICATE API SNAPSHOT",status.duplicate_api_snapshot),diagnostic("PROCESSED UPDATES",Array.isArray(status.processed_updates)?status.processed_updates.length:0));renderAchievements(scans,items);renderModules(rankings);const candidates=(await Promise.all(responses.slice(1).map(async(response)=>response?.ok?response.json():[]))).flat();renderCandidates(candidates);
  } catch(error) { el("systemState").textContent="OFFLINE";el("systemState").classList.add("partial");el("collectorStatus").innerHTML=`<p class="empty">${error.message}</p>`; }
}
setupTools();loadOps();setInterval(loadOps,POLL_INTERVAL);
