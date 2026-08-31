#!/usr/bin/env python3
"""One-request probe for thumbnails embedded in the DLsite ranking HTML."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urljoin, urlsplit

from scripts.dlsite_ranking_probe import ID_RE, TreeParser, _container, fetch, parse_ranking, walk


RANKING_URL = "https://www.dlsite.com/maniax/ranking"
IMAGE_EXT_RE = re.compile(r"\.(?:avif|gif|jpe?g|png|webp)(?:[?#]|$)", re.I)
CSS_IMAGE_RE = re.compile(r"background-image\s*:\s*url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)
STANDARD_ATTRIBUTES = ("data-src", "data-original", "src")


def _normalise_image_url(raw: str, base_url: str) -> str | None:
    value = raw.strip()
    if not value or value.startswith(("data:", "javascript:", "blob:")):
        return None
    url = urljoin(base_url, value)
    parts = urlsplit(url)
    return parts._replace(fragment="").geturl() if parts.scheme == "https" and parts.netloc else None


def _srcset_urls(value: str) -> list[str]:
    """Return candidates in author order (normally smallest/list-view first)."""
    return [part.strip().split()[0] for part in value.split(",") if part.strip()]


def _image_candidates(container, base_url: str):
    """Yield explicit image candidates inside one product container only."""
    seen: set[str] = set()
    for node in walk(container):
        if node.tag in {"img", "source"}:
            for attribute in STANDARD_ATTRIBUTES:
                if attribute not in node.attrs:
                    continue
                url = _normalise_image_url(node.attrs[attribute], base_url)
                if url and url not in seen:
                    seen.add(url)
                    yield url, f"{node.tag}[{attribute}]"
            if "srcset" in node.attrs:
                for raw in _srcset_urls(node.attrs["srcset"]):
                    url = _normalise_image_url(raw, base_url)
                    if url and url not in seen:
                        seen.add(url)
                        yield url, f"{node.tag}[srcset]"
            for attribute, raw in node.attrs.items():
                if not attribute.startswith("data-") or attribute in STANDARD_ATTRIBUTES:
                    continue
                if IMAGE_EXT_RE.search(raw):
                    url = _normalise_image_url(raw, base_url)
                    if url and url not in seen:
                        seen.add(url)
                        yield url, f"{node.tag}[{attribute}]"
        style = node.attrs.get("style", "")
        match = CSS_IMAGE_RE.search(style)
        if match:
            url = _normalise_image_url(match.group(2), base_url)
            if url and url not in seen:
                seen.add(url)
                yield url, "style[background-image]"


def parse_thumbnails(html: str, base_url: str, limit: int = 20) -> list[dict]:
    """Associate a thumbnail only with the ranking item's own DOM container."""
    ranking, _ = parse_ranking(html, base_url, limit=limit)
    by_id = {item["product_id"]: item for item in ranking
             if item.get("product_id") and "/work/" in urlsplit(item["url"]).path}
    parser = TreeParser()
    parser.feed(html)
    result: list[dict] = []
    used: set[str] = set()
    for anchor in (node for node in walk(parser.root) if node.tag == "a"):
        match = ID_RE.search(anchor.attrs.get("href", "")) or ID_RE.search(" ".join(anchor.attrs.values()))
        product_id = match.group(1).upper() if match else None
        if not product_id or product_id in used or product_id not in by_id:
            continue
        item = by_id[product_id]
        candidate = next(_image_candidates(_container(anchor), base_url), None)
        result.append({"rank": item["rank"], "product_id": product_id,
                       "title": item["title"], "product_url": item["url"],
                       "thumbnail_url": candidate[0] if candidate else None,
                       "thumbnail_source": candidate[1] if candidate else None})
        used.add(product_id)
        if len(result) >= limit:
            break
    return result


def build_report(html: str, final_url: str, fetched_at: str | None = None) -> dict:
    items = parse_thumbnails(html, final_url)
    found = sum(item["thumbnail_url"] is not None for item in items)
    coverage = round(found * 100 / len(items), 1) if items else 0
    sources = Counter(item["thumbnail_source"] for item in items if item["thumbnail_source"])
    result = "PASS" if items and coverage >= 90 else "PARTIAL" if found else "FAIL"
    return {"probe_version": 1, "fetched_at": fetched_at or datetime.now(timezone.utc).isoformat(),
            "source_url": final_url, "request_count": 1, "additional_product_requests": 0,
            "image_requests": 0, "ranking_items": len(items), "thumbnail_found": found,
            "thumbnail_missing": len(items) - found, "coverage_percent": coverage,
            "sources": dict(sorted(sources.items())), "association": "same_product_container",
            "urls_inferred": False, "items": items, "result": result}


def print_summary(report: dict) -> None:
    print("DLsite Thumbnail Probe\n")
    print(f"Ranking items: {report['ranking_items']}")
    print(f"Thumbnail found: {report['thumbnail_found']}")
    print(f"Coverage: {report['coverage_percent']}%\n")
    print("Sources:")
    for source, count in report["sources"].items():
        print(f"{source}: {count}")
    print(f"\nAdditional product requests: {report['additional_product_requests']}")
    print(f"Image requests: {report['image_requests']}")
    print(f"\nRESULT: {report['result']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=RANKING_URL)
    parser.add_argument("--output", default="tmp/dlsite_thumbnail_probe.json")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    if urlsplit(args.url).scheme != "https":
        parser.error("ranking URL must use https")
    try:
        access, html = fetch(args.url, args.timeout)  # The probe's only HTTP request.
        report = build_report(html, access["final_url"])
        exit_code = 0
    except (URLError, TimeoutError, OSError) as error:
        report = {"probe_version": 1, "fetched_at": datetime.now(timezone.utc).isoformat(),
                  "source_url": args.url, "request_count": 1,
                  "additional_product_requests": 0, "image_requests": 0,
                  "ranking_items": 0, "thumbnail_found": 0, "thumbnail_missing": 0,
                  "coverage_percent": 0, "sources": {},
                  "association": "not_assessed", "urls_inferred": False,
                  "items": [], "result": "FAIL", "access_error": str(error)}
        exit_code = 2
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print_summary(report)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
