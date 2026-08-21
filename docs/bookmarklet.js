(() => {
  const PRODUCT_HOST = /(^|\.)(?:dmm|fanza)\.co\.jp$/i;
  const PRODUCT_PATH = /\/detail\/|\/cid=[^/?#]+/i;
  const compact = value => (value || "").replace(/\s+/g, " ").trim();

  const productUrl = href => {
    try {
      const url = new URL(href, location.href);
      return PRODUCT_HOST.test(url.hostname) &&
        (PRODUCT_PATH.test(url.pathname) || url.searchParams.has("cid")) ? url : null;
    } catch (_) { return null; }
  };

  const cidOf = url => {
    const pathCid = url.pathname.match(/\/cid=([^/?#]+)/i);
    return decodeURIComponent(pathCid ? pathCid[1] : (url.searchParams.get("cid") || ""));
  };

  const cleanUrl = url => {
    const cid = cidOf(url);
    url = new URL(url.href); url.search = "";
    if (cid) url.searchParams.set("cid", cid);
    url.hash = "";
    return url.href;
  };

  const productCids = element => new Set([...element.querySelectorAll("a[href]")]
    .map(link => productUrl(link.href)).filter(Boolean).map(cidOf).filter(Boolean));
  const ownText = element => compact([...element.childNodes]
    .filter(node => node.nodeType === 3).map(node => node.textContent).join(" "));
  const rankNumber = element => {
    if (!element) return 0;
    const text = ownText(element) || compact(element.innerText);
    const match = text.match(/^(?:第\s*)?(\d{1,3})\s*(?:位|[.．])?$/);
    const rank = match ? Number(match[1]) : 0;
    return rank >= 1 && rank <= 100 ? rank : 0;
  };

  /* Rank lookup never leaves the already-confirmed one-product card. */
  const rankOf = card => {
    const attr = Number((card.getAttribute("data-rank") || "").match(/^\s*(\d{1,3})\s*$/)?.[1]);
    if (attr >= 1 && attr <= 100) return attr;
    const salesNodes = [...card.querySelectorAll("*")].filter(node => /販売数/.test(ownText(node)));
    for (const sales of salesNodes) {
      const siblings = [...(sales.parentElement?.children || [])];
      const candidates = [sales.previousElementSibling,
        ...siblings.slice(0, Math.max(0, siblings.indexOf(sales))).reverse(),
        sales.parentElement?.previousElementSibling];
      for (const candidate of candidates) {
        if (candidate && card.contains(candidate)) {
          const rank = rankNumber(candidate);
          if (rank) return rank;
        }
      }
    }
    for (const child of card.children) {
      if (/rank|順位|position/i.test(`${child.className || ""} ${child.id || ""}`)) {
        const rank = rankNumber(child);
        if (rank) return rank;
      }
    }
    return 0;
  };

  const titleOf = (card, originalLink, cid) => {
    const links = [...card.querySelectorAll("a[href]")].filter(link => {
      const url = productUrl(link.href); return url && cidOf(url) === cid;
    });
    const ordered = [originalLink, ...links.filter(link => link !== originalLink)];
    for (const link of ordered) { const title = compact(link.innerText); if (title) return title; }
    for (const link of ordered) { const title = compact(link.getAttribute("title")); if (title) return title; }
    for (const link of ordered) { const title = compact(link.querySelector("img[alt]")?.alt); if (title) return title; }
    return "";
  };

  const priceOf = card => {
    if (productCids(card).size !== 1) return 0;
    const pattern = /(?:[¥￥]\s*([\d,]+)|([\d,]+)\s*円)/g;
    const current = [...card.querySelectorAll("*")].filter(element => {
      const text = ownText(element);
      return /(?:[¥￥]\s*[\d,]+|[\d,]+\s*円)/.test(text) &&
        !element.closest("del,s,[class*='old'],[class*='before'],[class*='regular']");
    });
    const text = compact((current.at(-1) || card).innerText);
    const match = [...text.matchAll(pattern)].at(-1);
    return match ? Number((match[1] || match[2]).replace(/,/g, "")) : 0;
  };

  const extract = (doc = document, debug = {}) => {
    const links = [...doc.querySelectorAll("a[href]")];
    const productLinks = links.filter(link => productUrl(link.href));
    const uniqueProducts = new Set(productLinks.map(link => cidOf(productUrl(link.href))).filter(Boolean));
    const oneCidCards = new Set(), multipleCidCards = new Set(), seen = new Set(), out = [];
    for (const link of productLinks) {
      const url = productUrl(link.href), cid = cidOf(url);
      if (!cid || seen.has(cid)) continue;
      let card = link.parentElement;
      for (let depth = 0; card && depth < 10; depth += 1, card = card.parentElement) {
        const cids = productCids(card);
        if (cids.size > 1) { multipleCidCards.add(card); break; }
        if (cids.size !== 1 || !cids.has(cid)) continue;
        const text = compact(card.innerText);
        if (!text.includes("販売数") || !titleOf(card, link, cid) ||
            !/(?:[¥￥]\s*[\d,]+|[\d,]+\s*円)/.test(text)) continue;
        oneCidCards.add(card);
        out.push({ rank: rankOf(card), title: titleOf(card, link, cid), price: priceOf(card),
          url: cleanUrl(url), id: cid, _card: card });
        seen.add(cid);
        break;
      }
    }
    out.sort((a, b) => {
      if (a._card === b._card) return 0;
      return a._card.compareDocumentPosition(b._card) & 4 ? -1 : 1;
    });
    const explicitRanks = out.filter(item => item.rank).length;
    let domOrderFallbackUsed = false;
    if (out.length > 1 && explicitRanks === 0 && out.length === uniqueProducts.size) {
      out.forEach((item, index) => { item.rank = index + 1; });
      domOrderFallbackUsed = true;
    }
    out.forEach(item => { delete item._card; });
    Object.assign(debug, { links: links.length, productLinks: productLinks.length,
      candidateCards: oneCidCards.size, ranksFound: explicitRanks,
      uniqueProducts: uniqueProducts.size, cardsWithOneCid: oneCidCards.size,
      cardsWithMultipleCid: multipleCidCards.size, explicitRanks, domOrderFallbackUsed,
      itemsParsed: out.length });
    return out.sort((a, b) => a.rank - b.rank);
  };

  const validate = items => {
    if (!items.length) return "ランキング商品を検出できませんでした";
    const ranks = items.map(item => item.rank);
    if (items.length > 1 && new Set(ranks).size === 1) return "全商品の順位が同一です";
    if (new Set(ranks).size !== ranks.length) return "順位が重複しています";
    if (ranks.some(rank => !rank)) return "順位を取得できない商品があります";
    if (items.length === 20 && !ranks.slice().sort((a, b) => a - b).every((rank, i) => rank === i + 1))
      return "20商品の順位が1〜20の並びではありません";
    if (items.length > 1 && new Set(items.map(item => item.price)).size === 1)
      return "全商品の価格が同一です";
    return "";
  };

  const debugText = debug => `Links: ${debug.links || 0}\nProduct Links: ${debug.productLinks || 0}\nCandidate Cards: ${debug.candidateCards || 0}\nRanks Found: ${debug.ranksFound || 0}\nUnique Products: ${debug.uniqueProducts || 0}\nCards with 1 CID: ${debug.cardsWithOneCid || 0}\nCards with multiple CID: ${debug.cardsWithMultipleCid || 0}\nExplicit Ranks: ${debug.explicitRanks || 0}\nDOM Order Fallback Used: ${debug.domOrderFallbackUsed ? "Yes" : "No"}\nItems Parsed: ${debug.itemsParsed || 0}`;
  const run = async () => {
    const debug = {}, items = extract(document, debug), problem = validate(items);
    if (problem) { alert(`${problem}\n\nRankIdle Import Debug\n\n${debugText(debug)}`); return; }
    const json = JSON.stringify({ source: "fanza_manual", captured_at: new Date().toISOString(), items }, null, 2);
    try {
      if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(json); alert(`ランキングを${items.length}件取得しました\nJSONをコピーしました`);
    } catch (_) {
      const box = document.createElement("textarea"); box.value = json;
      box.setAttribute("style", "position:fixed;inset:5%;z-index:2147483647;width:90%;height:80%;padding:1em");
      document.body.append(box); box.select();
      alert(`ランキングを${items.length}件取得しました\n表示されたJSONを手動でコピーしてください`);
    }
  };
  if (typeof module !== "undefined") module.exports = { extract, validate, productUrl, cidOf };
  else run().catch(error => alert(`RankIdle Import Debug\n\n${error?.message || error}`));
})();
