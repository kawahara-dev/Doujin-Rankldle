from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .providers.fanza_api import SITE, request_json

FLOOR_API_URL = "https://api.dmm.com/affiliate/v3/FloorList"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/verify/dmm_floors.json"


def normalize_floors(payload: dict[str, Any], *, site_code: str = SITE) -> dict[str, Any]:
    """Keep all services and floors returned for the requested site."""
    sites = (payload.get("result") or {}).get("site") or []
    site = next((entry for entry in sites if entry.get("code") == site_code), None)
    if site is None:
        raise RuntimeError(f"DMM Floor API response has no site: {site_code}")
    services = []
    for service in site.get("service") or []:
        services.append(
            {
                "service_code": service.get("code", ""),
                "service_name": service.get("name", ""),
                "floors": [
                    {"floor_code": floor.get("code", ""), "floor_name": floor.get("name", "")}
                    for floor in service.get("floor") or []
                ],
            }
        )
    return {"site": site.get("code", site_code), "services": services}


def run(*, output: Path = OUTPUT) -> dict[str, Any]:
    api_id = os.getenv("DMM_API_ID")
    affiliate_id = os.getenv("DMM_AFFILIATE_ID")
    if not api_id or not affiliate_id:
        raise RuntimeError("DMM_API_ID and DMM_AFFILIATE_ID are required")
    payload = request_json(
        FLOOR_API_URL,
        {"api_id": api_id, "affiliate_id": affiliate_id, "site": SITE, "output": "json"},
    )
    result = normalize_floors(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    return result


def main() -> None:
    result = run()
    print(f"Found {len(result['services'])} FANZA services")
    print(f"Floor inspection artifact written to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
