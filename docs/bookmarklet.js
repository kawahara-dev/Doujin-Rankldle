(() => {
  const PRODUCT_HOST = /(^|\.)(?:dmm|fanza)\.co\.jp$/i;
  const PRODUCT_PATH = /\/detail\/|\/cid=[^/?#]+/i;
  const compact = value => (value || "").replace(/\s+/g, " ").trim();

  const productUrl = href => {
    try {
      const url = new URL(href, location.href);
      return PRODUCT_HOST.test(url.hostname) &&
        (PRODUCT_PATH.test(url.pathname) || url.searchParams.has("cid")) ? url : null;
    } catch (_) {
      return null;
    }
  };

  const cidOf = url => {
    const pathCid = url.pathname.match(/\/cid=([^/?#]+)/i);
    return decodeURIComponent(pathCid ? pathCid[1] : (url.searchParams.get("cid") || ""));
  };

  const cleanUrl = url => {
    const cid = cidOf(url);
    url = new URL(url.href);
    url.search = "";
    if (cid) url.searchParams.set("cid", cid);
    url.hash = "";
    return url.href;
  };

  const rankOf = card => {
    const attr = card.getAttribute("data-rank") || "";
    const explicit = attr.match(/\d{1,3}/) || compact(card.innerText).match(/(?:^|\s)(?:第\s*)?(\d{1,3})\s*(?:位|[.．])/);
    if (explicit) return Number(explicit[1] || explicit[0]);

    // The mobile page renders the rank as a bare number.  It is only accepted
    // at the beginning of a card and before a nearby sales-count label, so the
    // price and the number following 販売数 can never become the rank.
    const text = compact(card.innerText);
    const salesAt = text.indexOf("販売数");
    if (salesAt < 0 || salesAt > 80) return 0;
    const prefix = text.slice(0, salesAt);
    const mobile = prefix.match(/^\D{0,30}(\d{1,3})(?=\s|$)/);
    return mobile ? Number(mobile[1]) : 0;
  };

  const hasExplicitRank = card => /\d{1,3}/.test(card.getAttribute("data-rank") || "") ||
    /(?:^|\s)(?:第\s*)?\d{1,3}\s*(?:位|[.．])/.test(compact(card.innerText));

  const titleOf = (card, originalLink, cid) => {
    const links = [...card.querySelectorAll("a[href]")].filter(link => {
      const url = productUrl(link.href);
      return url && (!cid || cidOf(url) === cid);
    });
    const ordered = [originalLink, ...links.filter(link => link !== originalLink)];
    for (const link of ordered) {
      const title = compact(link.innerText);
      if (title) return title;
    }
    for (const link of ordered) {
      const title = compact(link.getAttribute("title"));
      if (title) return title;
    }
    for (const link of ordered) {
      const title = compact(link.querySelector("img[alt]")?.alt);
      if (title) return title;
    }
    return "";
  };

  const priceOf = card => {
    const pattern = /(?:[¥￥]\s*([\d,]+)|([\d,]+)\s*円)/g;
    const current = [...card.querySelectorAll("*")].filter(element => {
      const own = [...element.childNodes].filter(node => node.nodeType === 3).map(node => node.textContent).join(" ");
      return /(?:[¥￥]\s*[\d,]+|[\d,]+\s*円)/.test(own) &&
        !element.closest("del,s,[class*='old'],[class*='before'],[class*='regular']");
    });
    pattern.lastIndex = 0;
    const text = compact((current.at(-1) || card).innerText);
    const matches = [...text.matchAll(pattern)];
    const match = matches.at(-1);
    return match ? Number((match[1] || match[2]).replace(/,/g, "")) : 0;
  };

  const extract = (doc = document, debug = {}) => {
    const links = [...doc.querySelectorAll("a[href]")];
    const productLinks = links.filter(link => productUrl(link.href));
    const cards = new Set();
    let ranksFound = 0;
    const out = [], seen = new Set();

    for (const link of productLinks) {
      const url = productUrl(link.href);
      const cid = cidOf(url);
      let card = link.parentElement;
      for (let depth = 0; card && depth < 10; depth += 1, card = card.parentElement) {
        const text = compact(card.innerText);
        const rank = rankOf(card);
        if (!rank || (!hasExplicitRank(card) && !text.includes("販売数")) || !titleOf(card, link, cid)) continue;
        if (!/(?:[¥￥]\s*[\d,]+|[\d,]+\s*円)/.test(text)) continue;
        if (![...card.querySelectorAll("a[href]")].some(a => productUrl(a.href))) continue;
        cards.add(card);
        ranksFound += 1;
        const title = titleOf(card, link, cid);
        const cleaned = cleanUrl(url);
        const key = cid || cleaned;
        if (!seen.has(key)) {
          out.push({ rank, title, price: priceOf(card), url: cleaned, id: cid });
          seen.add(key);
        }
        break; // The first matching ancestor is the smallest product card.
      }
    }
    Object.assign(debug, { links: links.length, productLinks: productLinks.length,
      candidateCards: cards.size, ranksFound, itemsParsed: out.length });
    return out.sort((a, b) => a.rank - b.rank);
  };

  const run = async () => {
    const debug = {};
    const items = extract(document, debug);
    if (!items.length) {
      alert(`ランキング商品を検出できませんでした\n\nRankIdle Import Debug\n\nLinks: ${debug.links}\nProduct Links: ${debug.productLinks}\nCandidate Cards: ${debug.candidateCards}\nRanks Found: ${debug.ranksFound}\nItems Parsed: 0`);
      return;
    }
    const json = JSON.stringify({ source: "fanza_manual", captured_at: new Date().toISOString(), items }, null, 2);
    try {
      if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(json);
      alert(`ランキングを${items.length}件取得しました\nJSONをコピーしました`);
    } catch (_) {
      const box = document.createElement("textarea");
      box.value = json;
      box.setAttribute("style", "position:fixed;inset:5%;z-index:2147483647;width:90%;height:80%;padding:1em");
      document.body.append(box);
      box.select();
      alert(`ランキングを${items.length}件取得しました\n表示されたJSONを手動でコピーしてください`);
    }
  };
  if (typeof module !== "undefined") module.exports = { extract, productUrl, cidOf };
  else run();
})();
