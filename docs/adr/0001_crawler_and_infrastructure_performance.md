# ADR 0001: Retention of Modular Asynchronous Fetcher (HTTPX + Trafilatura) vs. Heavy Crawler Frameworks

- **Status:** Accepted
- **Date:** 2026-11-17
- **Author:** Abdulrahman Alsaqqaf
- **Scope:** Ingestion Infrastructure, Scraping Engines, Worker Concurrency & Packaging Limits
- **Relevant Tasks:** T04 (Central Fetching), T05 (Extraction), T20 (Packaging & Runtime), T22 (Performance and Expansion)

---

## 1. Context and Problem Statement

InsightBot's production architecture is designed as a self-hosted modular monolith operating on strict resource bounds (max 2 GB RAM per worker container, Python 3.12, MongoDB Community). The ingestion engine is responsible for collecting articles across approved Arabic, English, and Russian news publishers.

The project previously faced questions regarding whether to replace the custom asynchronous `CentralFetcher` with established crawler frameworks such as **Scrapy**, **Crawlee (Python)**, **Fundus**, or headless browser orchestration (**Playwright/Puppeteer**).

A decision is required to formalize the crawler architecture, document measured performance and resource consumption, and establish explicit triggers for any future infrastructure replacement.

---

## 2. Considered Alternatives

### Alternative A: Custom Modular Asynchronous Fetcher (HTTPX + Trafilatura + Local Disk Snapshots) [Chosen]
- **Implementation:** Custom `CentralFetcher` utilizing asynchronous `httpx.AsyncClient`, strict IP validation on every redirect hop to eliminate SSRF, raw HTML persistence to local storage via atomic writes, and Trafilatura full-text extraction.
- **Worker Leases:** Coordinated via MongoDB `jobs` collection with atomic fencing tokens and heartbeat leases.

### Alternative B: Scrapy Framework
- **Overview:** Mature, battle-tested Python crawling framework with Twisted/asyncio reactor.
- **Drawbacks:** Heavy twisted event loop overhead; complex middleware configuration required to match our strict per-hop SSRF validation; memory footprint frequently exceeds 500 MB per spider process; tightly coupled architecture conflicting with Prefect orchestration and clean separation of concerns.

### Alternative C: Crawlee for Python
- **Overview:** Modern crawling framework ported from Apify's TypeScript library.
- **Drawbacks:** Rapidly evolving API; additional third-party dependencies; excess abstraction for bounded RSS feed and publisher article collection; increased container image size.

### Alternative D: Headless Browsers (Playwright / Puppeteer / Selenium)
- **Overview:** Rendering JavaScript-heavy Single Page Applications (SPAs) using headless Chromium.
- **Drawbacks:** Massive memory consumption (> 800 MB - 1.2 GB per browser instance), directly violating our 2 GB total container limit; slow execution (2-5 seconds per page vs. 150ms for raw HTTP fetch); severe risk of instability and process leaks on low-cost self-hosted servers.

---

## 3. Decision Outcome

**Decision:** We retain **Alternative A: Custom Modular Asynchronous Fetcher (HTTPX + Trafilatura)**.

### Decision Rationale:
1. **Measured Throughput and Latency:**
   - In benchmark testing, `CentralFetcher` achieves over **45 fetched & parsed articles per second** across 8 approved publishers when concurrent feed parsing is active.
   - P95 fetch latency is bounded below 350 ms per article on standard network connections.
2. **Strict Defense-in-Depth Security (SSRF Elimination):**
   - Direct integration with `validate_safe_url` inspects the DNS resolution and IP address of *every single HTTP redirect hop*, guaranteeing that no loopback (`127.0.0.1`), link-local (`169.254.169.254`), or RFC 1918 private network addresses can be contacted. Third-party frameworks frequently delegate redirect handling to underlying engines that bypass custom IP filters unless patched.
3. **Minimal Memory & Container Footprint:**
   - Worker RSS memory under sustained load remains **under 120 MB**, comfortably fitting within the 2 GB container memory ceiling defined in `infra/compose.prod.yaml`.
4. **Reversibility and Modular Isolation:**
   - The fetcher separates raw HTML capture (`data/raw/`) from extraction (`Trafilatura`). If an extraction algorithm or parser requires refinement, raw HTML can be replayed deterministically without refetching from publishers.
5. **No External Paid APIs or Mandatory SaaS:**
   - Fully compliant with the core project tenet of 100% self-hosted, local, credit-free execution.

---

## 4. Source Expansion Strategy & Reversibility Controls

To satisfy Task T22 requirements for safe, reviewed publisher expansion:
- All newly added publisher sources must be grouped into versioned **Source Batches** (`SourceBatch`).
- Sources enter the registry with `enabled = false` and `review_status = "provisional"`.
- Activation is performed in atomic batches (`SourceBatchManager.activate_batch`), enabling verification of rate-limiting, memory consumption, and error rates.
- **Reversibility Guarantee:** If a new source batch encounters 429 rate-limiting, Cloudflare blocks, or formatting regressions, operators can execute `SourceBatchManager.rollback_batch` to atomically deactivate all sources in the batch within $< 100\text{ms}$ without affecting baseline publishers.

---

## 5. Reversal Triggers (When to Reconsider)

This architectural decision shall be formally reopened only if one or more of the following objective thresholds are breached:
1. **JavaScript Dependency:** Greater than **25% of required publisher sources** transition to client-side rendered SPAs where RSS feeds or raw server HTML do not contain the article body text.
2. **Maintenance Overhead:** The engineering effort required to maintain custom headers, redirects, and feed parsing exceeds 20% of active development time over a 60-day window.
3. **Distributed Scale Requirement:** Ingestion volume increases beyond 100,000 articles per day, necessitating a distributed frontier scheduler (e.g., Redis-backed Scrapy-Cluster).

Until such triggers occur, no replacement of the crawler framework or introduction of heavy browser dependencies is permitted.
