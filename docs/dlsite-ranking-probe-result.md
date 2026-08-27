# DLsite Ranking Probe v1 — one-shot result

Probe date: 2026-08-27 (UTC)

The single attempted ranking request used
`https://www.dlsite.com/maniax/ranking` and the explicit user agent
`RankIdle-DLsite-Probe/0.1`. The execution environment's outbound HTTP tunnel rejected
the connection with `403 Forbidden` before an origin response was received. This is an
environment/network failure, not evidence that DLsite returned HTTP 403.

| Observation | Result |
| --- | --- |
| Requested URL | `https://www.dlsite.com/maniax/ranking` |
| Final URL | Not available (no origin response) |
| Origin HTTP status/content type/size | Not available |
| Ranking items | 0 (not assessed) |
| rank / product ID / title / URL / price | Not assessed |
| circle / maker / release date / genres | Not assessed |
| robots.txt | Not requested because the ranking request failed first |
| HTML/DOM dependency | Not assessed; no HTML was received or saved |
| Feasibility | **LOW / inconclusive**, not `BLOCKED` by the target site |

No retry, alternate endpoint discovery, detail-page request, access-control bypass, or
HTML persistence was performed. A human should rerun the command once from an approved
network before making an integration decision. Only after a successful result and a
human review of current terms, robots.txt, and public-access conditions should the
isolated provider/snapshot design in the probe documentation be considered. No
production collection or schedule has been added.
