#!/usr/bin/env python3
"""One-shot, read-only probe for a caller-supplied DLsite ranking URL."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

USER_AGENT = "RankIdle-DLsite-Probe/0.1"
ID_RE = re.compile(r"(?<![A-Z0-9])((?:RJ|BJ|VJ)\d+)(?!\d)", re.I)
PRICE_RE = re.compile(r"(?:¥|￥)\s*([\d,]+)|([\d,]+)\s*円")
RANK_RE = re.compile(r"(?:rank(?:ing)?|順位)?\s*[#№]?\s*(\d{1,3})\s*(?:位)?", re.I)


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    parent: "Node | None" = None
    children: list["Node"] = field(default_factory=list)
    chunks: list[str] = field(default_factory=list)

    def text(self) -> str:
        return " ".join(" ".join(self.chunks).split())


class TreeParser(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {})
        self.current = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {key: value or "" for key, value in attrs}, self.current)
        self.current.children.append(node)
        if tag not in self.VOID:
            self.current = node

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        node = self.current
        while node.parent and node.tag != tag:
            node = node.parent
        if node.parent:
            self.current = node.parent

    def handle_data(self, data: str) -> None:
        if data.strip():
            node: Node | None = self.current
            while node:
                node.chunks.append(data)
                node = node.parent


def walk(node: Node):
    yield node
    for child in node.children:
        yield from walk(child)


def _container(anchor: Node) -> Node:
    node = anchor
    best = anchor.parent or anchor
    while node.parent and node.parent.tag != "document":
        node = node.parent
        marker = " ".join((node.attrs.get("class", ""), node.attrs.get("id", ""))).lower()
        if node.tag in {"li", "article"} or re.search(r"work|product|item|rank", marker):
            best = node
            if node.tag in {"li", "article"}:
                break
    return best


def _explicit_rank(node: Node) -> int | None:
    for candidate in walk(node):
        for key in ("data-rank", "data-ranking", "rank"):
            value = candidate.attrs.get(key, "")
            if value.isdigit():
                return int(value)
        marker = " ".join((candidate.attrs.get("class", ""), candidate.attrs.get("id", "")))
        if re.search(r"rank|ranking|順位", marker, re.I):
            match = RANK_RE.search(candidate.text())
            if match:
                return int(match.group(1))
    return None


def parse_ranking(html: str, base_url: str, limit: int = 20) -> tuple[list[dict], dict]:
    parser = TreeParser()
    parser.feed(html)
    items: list[dict] = []
    seen: set[str] = set()
    evidence = {"product": set(), "title": set(), "url_pattern": set(), "data_attributes": set()}
    for anchor in (node for node in walk(parser.root) if node.tag == "a"):
        href = anchor.attrs.get("href", "")
        match = ID_RE.search(href) or ID_RE.search(" ".join(anchor.attrs.values()))
        if not match:
            continue
        product_id = match.group(1).upper()
        if product_id in seen:
            continue
        container = _container(anchor)
        text = container.text()
        price_match = PRICE_RE.search(text)
        title = anchor.attrs.get("title", "").strip() or anchor.text().strip() or None
        price = int((price_match.group(1) or price_match.group(2)).replace(",", "")) if price_match else None
        items.append({"rank": _explicit_rank(container), "dom_position": len(items) + 1,
                      "product_id": product_id, "title": title, "url": urljoin(base_url, href),
                      "price": price, "circle": None, "maker": None,
                      "release_date": None, "genres": None})
        seen.add(product_id)
        classes = container.attrs.get("class", "").split()
        evidence["product"].update(f".{name}" for name in classes)
        title_classes = anchor.attrs.get("class", "").split()
        evidence["title"].update(f".{name}" for name in title_classes)
        evidence["url_pattern"].add("product link containing explicit RJ/BJ/VJ identifier")
        evidence["data_attributes"].update(key for key in container.attrs if key.startswith("data-"))
        if len(items) >= limit:
            break
    # Keep explicitly ranked public work links even when DLsite does not expose a
    # supported RJ/BJ/VJ identifier.  They remain intentionally identity-less.
    known_urls = {item["url"] for item in items}
    for anchor in (node for node in walk(parser.root) if node.tag == "a"):
        href = anchor.attrs.get("href", "")
        url = urljoin(base_url, href)
        if url in known_urls or "/work/" not in urlsplit(url).path:
            continue
        container = _container(anchor)
        rank = _explicit_rank(container)
        title = anchor.attrs.get("title", "").strip() or anchor.text().strip() or None
        if rank is None or not title:
            continue
        price_match = PRICE_RE.search(container.text())
        price = int((price_match.group(1) or price_match.group(2)).replace(",", "")) if price_match else None
        items.append({"rank": rank, "dom_position": len(items) + 1, "product_id": None,
                      "title": title, "url": url, "price": price, "circle": None,
                      "maker": None, "release_date": None, "genres": None})
        known_urls.add(url)
        if len(items) >= limit:
            break
    return items, {key: sorted(value)[:10] for key, value in evidence.items() if value}


def _blocked(status: int, final_url: str, html: str) -> str | None:
    if status in {401, 403, 429}:
        return f"HTTP {status}"
    sample = html[:500_000].lower()
    indicators = (("captcha", "CAPTCHA"), ("login required", "login required"),
                  ("access denied", "explicit access denial"), ("bot detected", "explicit bot block"))
    for needle, reason in indicators:
        if needle in sample:
            return reason
    if "age_check" in final_url.lower() or ("年齢確認" in sample and not ID_RE.search(sample)):
        return "age verification prevented ranking access"
    return None


def fetch(url: str, timeout: float) -> tuple[dict, str]:
    started = time.monotonic()
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            status, final_url = response.status, response.geturl()
            content_type = response.headers.get("Content-Type", "")
    except HTTPError as error:
        body, status, final_url = error.read(), error.code, error.geturl()
        content_type = error.headers.get("Content-Type", "")
    elapsed = round(time.monotonic() - started, 3)
    encoding = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    if match:
        encoding = match.group(1)
    html = body.decode(encoding, errors="replace")
    return {"requested_url": url, "final_url": final_url, "http_status": status,
            "content_type": content_type, "response_size": len(body),
            "redirected": final_url != url, "elapsed_time": elapsed}, html


def observe_robots(url: str, timeout: float) -> dict:
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    access, text = fetch(robots_url, timeout)
    path = parts.path or "/"
    disallows = []
    applies = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.lower().startswith("user-agent:"):
            applies = line.split(":", 1)[1].strip() in {"*", USER_AGENT}
        elif applies and line.lower().startswith("disallow:"):
            rule = line.split(":", 1)[1].strip()
            if rule and path.startswith(rule):
                disallows.append(rule)
    return {"checked": True, "url": robots_url, "http_status": access["http_status"],
            "matching_disallow": disallows,
            "note": "robots.txt alone does not determine legal or contractual permission"}


def build_result(access: dict, html: str, robots: dict) -> dict:
    reason = _blocked(access["http_status"], access["final_url"], html)
    items, selectors = ([], {}) if reason else parse_ranking(html, access["final_url"])
    fields = ("rank", "product_id", "title", "url", "price", "circle", "release_date", "genres")
    availability = {f"{key}_available": any(item[key] is not None for item in items) for key in fields}
    if reason:
        confidence, feasible, status = "BLOCKED", False, "ACCESS_BLOCKED"
    elif len(items) >= 20 and all(availability[f"{key}_available"] for key in ("rank", "product_id", "title", "url")):
        confidence, feasible, status = "HIGH", True, "SUCCESS"
    elif items:
        confidence, feasible, status = "MEDIUM", True, "SUCCESS"
    else:
        confidence, feasible, status = "LOW", False, "SUCCESS" if access["http_status"] == 200 else "ERROR"
    return {"probe_version": 1, "access": {"status": status, **access, "block_reason": reason},
            "robots_observation": robots,
            "ranking": {"detected": bool(items), "items_detected": len(items), **availability,
                        "not_available_on_ranking_page": [key for key in ("release_date", "genres") if not availability[f"{key}_available"]]},
            "selector_candidates": selectors, "sample_items": items[:3],
            "assessment": {"automatic_collection_feasible": feasible, "confidence": confidence,
                           "html_dom_dependency": "Selectors and product-link URL patterns may change without notice."}}


def print_recommendation(result: dict) -> None:
    assessment = result["assessment"]
    print("\nDLsite Ranking Integration Recommendation")
    print(f"RESULT: {'FEASIBLE' if assessment['automatic_collection_feasible'] else assessment['confidence']}")
    print("\nMinimum data available:")
    for key in ("rank", "product_id", "title", "url", "price", "circle", "genres", "release_date"):
        print(f"{'✅' if result['ranking'][key + '_available'] else '❌'} {key}")
    print("\nSuggested RankIdle v1 schema: rank, id, title, price, url")
    print("previous_rank, rank_change, and status can be generated by RankIdle.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("DLSITE_RANKING_URL"))
    parser.add_argument("--output", default="tmp/dlsite_probe_result.json")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--check-robots", action="store_true", help="Make exactly one additional robots.txt GET")
    args = parser.parse_args()
    if not args.url:
        parser.error("--url or DLSITE_RANKING_URL is required; no URLs will be discovered")
    if urlsplit(args.url).scheme not in {"http", "https"}:
        parser.error("URL must use http or https")
    try:
        access, html = fetch(args.url, args.timeout)
        robots = observe_robots(args.url, args.timeout) if args.check_robots else {"checked": False, "note": "not requested"}
    except (URLError, TimeoutError, OSError) as error:
        result = {"probe_version": 1,
                  "access": {"status": "ACCESS_ERROR", "requested_url": args.url,
                             "final_url": None, "http_status": None, "content_type": None,
                             "response_size": 0, "redirected": None, "elapsed_time": None,
                             "block_reason": None, "error": str(error)},
                  "robots_observation": {"checked": False,
                                         "note": "ranking request failed before robots check"},
                  "ranking": {"detected": False, "items_detected": 0,
                              **{f"{key}_available": False for key in ("rank", "product_id", "title", "url", "price", "circle", "release_date", "genres")},
                              "not_available_on_ranking_page": ["release_date", "genres"]},
                  "selector_candidates": {}, "sample_items": [],
                  "assessment": {"automatic_collection_feasible": False, "confidence": "LOW",
                                 "html_dom_dependency": "Not assessed because no response was received."}}
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print_recommendation(result)
        return 2
    result = build_result(access, html, robots)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print_recommendation(result)
    return 0 if result["access"]["status"] in {"SUCCESS", "ACCESS_BLOCKED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
