# DLsite Ranking Probe v1

This is an isolated, one-shot technical probe. It is not connected to the collector,
scheduled workflows, production data, or the Pages UI. It never visits product detail
pages and does not save response HTML.

```bash
python scripts/dlsite_ranking_probe.py --url "<public-ranking-url>"
# Add --check-robots only when one additional robots.txt request is intended.
```

The URL must be supplied with `--url` or `DLSITE_RANKING_URL`; the probe does not try
alternative endpoints. Its JSON is written to `tmp/dlsite_probe_result.json` by default.
Only explicit RJ/BJ/VJ identifiers, displayed ranks, titles, links, and prices are
reported. DOM order is separately recorded as `dom_position` and is never treated as
an official rank. Block pages, CAPTCHA, login requirements, and an impassable age gate
produce `ACCESS_BLOCKED`; the probe implements no bypass.

Before any production automation, a human must review DLsite's latest terms of use,
robots.txt, and public-access conditions. robots.txt alone is not a legal or contractual
determination. Even after approval, a conservative proposal is one to four runs per day.

If a successful probe supports integration, the future (not implemented here) shape is:

`DLsite public ranking → GitHub Actions → DLsiteProvider → snapshot → rank comparison → docs/data → Cloudflare`

The minimum proposed schema is `rank`, `id`, `title`, `price`, and `url`; RankIdle can
derive `previous_rank`, `rank_change`, and `status`. HTML classes and hierarchy are an
unstable dependency, so URL-pattern fallback, fixture monitoring, failure-safe snapshot
retention, request throttling, and manual review are recommended.
