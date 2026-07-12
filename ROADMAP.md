# SchemaSnap Roadmap

## Phase 1: Launch (Week 1-2) — DONE

- [x] Extract `schema_snap.py` from shadow-web as standalone module
- [x] Inline semantic grouping from `grouping.py`
- [x] Fix tree-mutation bug in compressor (collect nodes before removal)
- [x] Add `extract_from_url()` orchestrator with Playwright
- [x] Add `extract_from_html()` for stateless/browserless use
- [x] FastAPI server: `POST /v1/extract`, `POST /v1/compress`, `GET /v1/health`
- [x] Input validation: 5 MB HTML cap, URL format check
- [x] Rate limiter with LRU-like pruning
- [x] Unit tests for compressor + schema extraction
- [x] Integration test for full extract_from_url pipeline
- [x] pyproject.toml, README, ROADMAP, CLAUDE.md

## Phase 2: Validation (Week 2-3)

- [ ] Ship to PyPI as `schemasnap`
- [ ] Free tier API endpoint (50 calls/day, no auth)
- [ ] Post to Show HN, r/Python, r/MCP
- [ ] Metric: 500+ unique API calls in first week → PMF signal
- [ ] Metrics dashboard (PostHog or similar)
- [ ] `/v1/extract` with `format=csv` output option

## Phase 3: Monetization (Week 4-6) — if PMF confirmed

- [ ] API key generation + management
- [ ] Stripe billing integration
- [ ] Tiered pricing:
  - Free: 50 calls/day, rate-limited
  - Pro ($29/mo): 5,000 calls/month, 50 calls/hour burst
  - Enterprise ($299/mo): dedicated pool, SLA, priority
- [ ] Usage dashboard for customers
- [ ] Abuse prevention: domain allowlist/blocklist, content-type check

## Phase 4: Distribution (Week 6-8)

- [x] MCP server: `compress_html` tool (stdio, Cursor/Claude)
- [ ] Claude plugin / MCP marketplace listing
- [ ] Python SDK improvements: async API, batch extraction
- [ ] `/v1/batch` endpoint — extract from multiple URLs in one request
- [ ] Caching layer: same URL + hash → cached result (5 min TTL)

## Phase 5: Enterprise (Month 3-4)

- [ ] `/v1/schema` with OpenAPI-like output format for agent consumption
- [ ] Webhook notifications for long-running batch jobs
- [ ] Self-hosted deployment option
- [ ] SOC2 compliance documentation
- [ ] Browser pool management for high-throughput enterprise

## Phase 6: Beyond Extraction (Month 5-6)

- [ ] `/v1/diff` — extract only changes between two page states
- [ ] `/v1/monitor` — recurring extraction with alerting on changes
- [ ] Integration marketplace (Zapier, Make, n8n)
- [ ] Agent auto-fill: schema → fill form with JSON profile

## Kill Criteria

- **No PMF by Week 4:** < 500 unique API calls in first week after launch → pivot or archive
- **Anthropic ships native compression:** schema extraction remains differentiated, but pricing must shift to enterprise-only
- **Playwright infra costs exceed $200/month at < $500 MRR:** sunset /v1/extract, keep /v1/compress only
- **Abuse/fraud overwhelms moderation:** add mandatory auth before scaling further

## Success Criteria

- **Month 3:** $500+ MRR from 15-25 paid users
- **Month 6:** $2K+ MRR with 1-2 enterprise deals
- **Month 12:** $10K MRR — sustainable solo-dev business
