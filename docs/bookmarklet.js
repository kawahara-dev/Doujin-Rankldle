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

  const hasSales = element => /販売数/.test(compact(element.innerText));
  const hasPrice = element => /(?:[¥￥]\s*[\d,]+|[\d,]+\s*円)/.test(compact(element.innerText));

  const extract = (doc = document, debug = {}) => {
    const links = [...doc.querySelectorAll("a[href]")];
    const productLinks = links.filter(link => productUrl(link.href));
    const uniqueProducts = new Set(productLinks.map(link => cidOf(productUrl(link.href))).filter(Boolean));
    const oneCidCards = new Set(), multipleCidCards = new Set(), seen = new Set(), out = [];
    const missingDiagnostics = [];
    for (const link of productLinks) {
      const url = productUrl(link.href), cid = cidOf(url);
      if (!cid || seen.has(cid)) continue;
      const cidLinks = productLinks.filter(candidate => cidOf(productUrl(candidate.href)) === cid);
      let inspectedDepth = -1, closestOneCid = null;
      let card = link.parentElement;
      for (let depth = 0; card && depth < 10; depth += 1, card = card.parentElement) {
        inspectedDepth = depth;
        const cids = productCids(card);
        if (cids.size > 1) { multipleCidCards.add(card); break; }
        if (cids.size !== 1 || !cids.has(cid)) continue;
        closestOneCid = card;
        if (!hasSales(card) || !titleOf(card, link, cid)) continue;
        oneCidCards.add(card);
        out.push({ rank: rankOf(card), title: titleOf(card, link, cid), price: priceOf(card),
          url: cleanUrl(url), id: cid, _card: card });
        seen.add(cid);
        break;
      }
      if (!seen.has(cid) && !missingDiagnostics.some(item => item.cid === cid)) {
        const scope = closestOneCid || link.parentElement;
        missingDiagnostics.push({ cid, productLinks: cidLinks.length, parentDepth: inspectedDepth,
          sales: Boolean(scope && hasSales(scope)), price: Boolean(scope && hasPrice(scope)),
          uniqueCidCount: scope ? productCids(scope).size : 0,
          innerTextLength: compact(scope?.innerText).length });
      }
    }
    out.sort((a, b) => {
      if (a._card === b._card) return 0;
      return a._card.compareDocumentPosition(b._card) & 4 ? -1 : 1;
    });
    const explicitRanks = out.filter(item => item.rank).length;
    const stableDomOrder = out.length === new Set(out.map(item => item._card)).size &&
      out.every((item, index) => index === 0 ||
        Boolean(out[index - 1]._card.compareDocumentPosition(item._card) & 4));
    let domOrderFallbackUsed = false;
    /* A partial list is useful only above this conservative floor; missing products are never invented. */
    if (out.length >= 10 && explicitRanks === 0 && stableDomOrder) {
      out.forEach((item, index) => { item.rank = index + 1; });
      domOrderFallbackUsed = true;
    }
    const priceMissing = out.filter(item => item.price === 0).length;
    const salesMissing = missingDiagnostics.filter(item => !item.sales).length;
    out.forEach(item => { delete item._card; });
    Object.assign(debug, { links: links.length, productLinks: productLinks.length,
      candidateCards: oneCidCards.size, ranksFound: explicitRanks,
      uniqueProducts: uniqueProducts.size, cardsWithOneCid: oneCidCards.size,
      cardsWithMultipleCid: multipleCidCards.size, explicitRanks, domOrderFallbackUsed,
      itemsParsed: out.length, parsedProducts: out.length,
      missingProducts: uniqueProducts.size - out.length, priceMissing, salesMissing,
      stableDomOrder, missingDiagnostics });
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
    if (items.length > 1 && items[0].price > 0 && new Set(items.map(item => item.price)).size === 1)
      return "全商品の価格が同一です";
    return "";
  };

  const debugText = debug => {
    const missing = (debug.missingDiagnostics || []).map(item =>
      `cid=${item.cid} links=${item.productLinks} depth=${item.parentDepth} sales=${item.sales ? "Yes" : "No"} price=${item.price ? "Yes" : "No"} unique_cids=${item.uniqueCidCount} text_length=${item.innerTextLength}`).join("\n");
    return `Links: ${debug.links || 0}\nProduct Links: ${debug.productLinks || 0}\nCandidate Cards: ${debug.candidateCards || 0}\nRanks Found: ${debug.ranksFound || 0}\nUnique Products: ${debug.uniqueProducts || 0}\nParsed Products: ${debug.parsedProducts || 0}\nMissing Products: ${debug.missingProducts || 0}\nCards with 1 CID: ${debug.cardsWithOneCid || 0}\nCards with multiple CID: ${debug.cardsWithMultipleCid || 0}\nPrice Missing: ${debug.priceMissing || 0}\nSales Missing: ${debug.salesMissing || 0}\nExplicit Ranks: ${debug.explicitRanks || 0}\nDOM Order Fallback Used: ${debug.domOrderFallbackUsed ? "Yes" : "No"}\nStable DOM Order: ${debug.stableDomOrder ? "Yes" : "No"}\nItems Parsed: ${debug.itemsParsed || 0}${missing ? `\nMissing Product Diagnostics:\n${missing}` : ""}`;
  };
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
