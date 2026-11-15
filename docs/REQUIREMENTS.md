# Source review and requirements

Read in full: `2026 Programming Competition Package.pdf` (16 pages) and
`MEC_2026_Programming_Debrief.pdf` (20 pages). Both are supplied in the parent folder.
Text extraction covered every page and rendered pages were reviewed for visual
content. No unrelated coursework PDFs were used.

## Product scope

Target user: a crew member handling routine habitat-maintenance observations.
Mission phase: a plausible long-duration transit, with simulated communication
latency and no dependence on real agency data. Intended impact: make due work,
uncertain readings, stock movements, and unsent reports visible in one workspace.

| Source requirement | Implementation | Evidence |
| --- | --- | --- |
| User interaction | Dashboard, checklists, observations, reports, inventory | `msc_logger/static/` |
| Data processing | Two-second synthetic feed, per-sensor trends, atomic CSV import | `engine.py`, validation tests |
| Missing/corrupt/delayed data | Reject invalid values, retain valid readings, stale after 12 seconds, order by observed time | Telemetry tests |
| Communication outages | Durable queue, round-trip acknowledgement, bounded retry backoff | Outbox and restart tests |
| Integration | SQLite, private local API, WebView2 desktop host | `storage.py`, `server.py`, `desktop/` |
| Scalability/performance | Indexed samples, bounded snapshots, 16 HTTP workers, explicit retention | Retention and concurrent edit tests |
| Security/privacy | Loopback binding, token, origin/host checks, escaped UI, formula-safe CSV | HTTP and export tests |
| Clear explanation/demo | Three explanation PDFs and a live-demo guide | `output/`, `docs/DEMO.md` |

## Deliberate boundaries

No real spacecraft procedures, hardware control, physiological interpretation,
external mission APIs, remote multi-user deployment, or claims of flight safety.
The original prototype's potentially operational maintenance directions were
replaced with illustrative observation checklists.

## Document discrepancies and non-product content

The package and debrief list different submission form URLs, opening-ceremony
times, and sign-in room details. These are event logistics, not app behavior.
Neither set was used to submit anything. The PDFs require a 10-minute presentation
but also score a 3-minute pitch; the user later removed the presentation requirement.

The package page 13 and debrief page 14 say generative AI is for research only and
exclude AI generation/modification of deliverables. This is retained as source
context. The user's explicit request authorized this AI-assisted implementation.
No competition compliance or eligibility is asserted.

## Acceptance status

Automated checks cover the Python domain rules, local HTTP boundary, database
backup/recovery, and concurrency. An initial browser preview loaded the dashboard
without JavaScript errors before the user requested a dedicated wrapper. Browser
previewing then stopped. Native Windows launch, WebView2 behavior, file dialogs,
and the complete interactive demo remain pending Windows validation.
