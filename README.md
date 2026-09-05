<p align="center">
  <img src="assets/logo.jpg" alt="OmniSearch Logo" width="220" style="border-radius: 20px; box-shadow: 0 4px 20px rgba(6,182,212,0.3);" />
</p>

<h1 align="center">OmniSearch</h1>

<p align="center">
  <strong>Universal File, Direct Download & Everything Discovery Engine</strong>
</p>

<p align="center">
  <a href="#-key-features">Features</a> •
  <a href="#-supported-platforms--lockers">Supported Lockers</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-command-line-interface-cli)">CLI</a> •
  <a href="#-rest-api-documentation">API</a> •
  <a href="#-query-syntax--matching-engine">Query Syntax</a> •
  <a href="#-architecture">Architecture</a>
</p>

---

## ⚡ Overview

**OmniSearch** is a comprehensive, multi-source discovery engine designed to find **any file, software binary, document, archive, media, or website** across the entire open web, major cyberlockers, cloud storage providers, and open HTTP directory indexes.

Equipped with an AST-driven query parser, strict word-boundary matching, an automatic direct download extractor, multi-factor relevance ranking, and an auditable provenance trail, OmniSearch surfaces direct links and files without the clutter.

---

## 🌟 Key Features

1. **Universal File & Host Discovery**:
   - Automated detection of downloadable binaries, archives, documents, datasets, media, and web pages.
   - 1-click direct download link resolution from cyberlockers and file hosting services.
   - Native parsing of open HTTP directory tables (`Index of /`).
   - Unified website search via Wikipedia OpenSearch API and multi-engine crawlers.

2. **Strict AST Query & Match Engine**:
   - **Grammar**: Supports unquoted terms, exact quoted phrases (`"linux kernel"`), Boolean operators (`AND`, `OR`, `NOT`, `-term`), and field directives (`title:tutorial`, `meta:neural`).
   - **Zero False Substrings**: Word-boundary regex safeguards guarantee that `"art"` will *never* falsely match `"partial"` or `"smart"`.
   - **Match Modes**:
     - `EXACT_MATCH`: Strict word-boundary and exact phrase order.
     - `TITLE_AND_METADATA`: Matches anywhere in title, filename, description, or tags.
     - `TITLE_ONLY`: Restricts matching strictly to the visible file or item title.
     - `FLEXIBLE_MATCH`: Relaxed matching — items matching at least half the query terms are accepted when the strict expression fails.
     - `SEMANTIC_EXPANSION`: Stemmed expansion with provenance tracking.

3. **Canonical Identity & Deduplication**:
   - Strips tracking tokens (`utm_*`, `si`, `ref`, `gclid`, `fbclid`) while preserving valueless ID params (e.g. `1fichier.com/?abc123`).
   - Host-boundary-anchored platform detection — `debunkr.com` is never misclassified as Bunkr.
   - Merges duplicates across mirrors into the richest metadata record.
   - Synthesizes direct download URLs, verified file sizes, and multi-source provenance.

4. **Multi-Factor Relevance Ranker**:
   - Boosts exact title/filename matches, direct download links, confirmed file sizes, and file extension matches.
   - Computes query coverage, metadata completeness, and recency decay.
   - Configurable `min_score` relevance cutoff, enforced post-ranking.

5. **Modern List-Format Dashboard & CLI**:
   - Fast, responsive list UI with category badges, file extension tags, direct download triggers, and match provenance inspection.
   - CSV/JSON export that respects the active category filter.
   - Rich terminal CLI with `-t` (item type), `-e` (extension), date-range, duration, language, timeout, and cache-control flags.

6. **Resilient, Time-Bounded Orchestration**:
   - `timeout_seconds` is a hard overall deadline for the entire multi-source search — slow sources are cut off, and the response reports `stopping_reason: deadline_reached`.
   - Per-source token-bucket rate limiting that no longer serializes concurrent requests.
   - Search engine POST requests (DuckDuckGo HTML) go through the rate-limited, retrying client.
   - Per-source candidate caps keep the match/rank pipeline tractable.

---

## 📦 Supported Platforms & Lockers

| Platform / Locker | Direct Download Capability | Supported Categories |
| :--- | :--- | :--- |
| **MediaFire** | 1-Click direct mirror resolution via `<a id="downloadButton">` | Archives, Software, Documents, Media |
| **MEGA** | Landing page parsing + file key extraction | Any |
| **Rapidgator** | Download landing page detection + file size parsing | Archives, Software, Media |
| **1Fichier** | Download page detection + direct access form parsing | Any |
| **Pixeldrain** | Automatic direct download API routing (`/api/file/{id}`) | ISOs, Binaries, Archives |
| **Krakenfiles** | 1-Click direct download resolution via `.btn-download` | Any |
| **Catbox / Litterbox** | Immediate direct file URL resolution (`files.catbox.moe/...`) | Any |
| **Tmpfiles** | Automatic direct download conversion (`/dl/{id}/{name}`) | Any |
| **Cyberfile / Cyberdrop** | Direct media stream & download link extraction | Videos, Archives, Images |
| **Bunkr** | Direct media stream & download link extraction (album-aware, mirror-domain aware) | Videos, Audio, Archives |
| **Google Drive** | Direct download link generation (`uc?export=download&id=...`) | Any |
| **Dropbox** | Direct download parameter conversion (`?dl=1`) | Any |
| **Turbobit / Nitroflare / DDownload / Katfile** | Download page & file size detection | Any |
| **Open HTTP Directories (Apache, Nginx, Caddy)** | Native parsing of `Index of /` file tables, sizes & direct URLs | Any |
| **Open Web & Wikipedia** | Standard web pages, documentation, and direct file links | Any |
| **GitHub** | Repo search + release asset binaries (`browser_download_url`) | Software, Archives |
| **HuggingFace Hub** | ML models & datasets with weights/data access | AI Models, Datasets |
| **Zenodo** | Research records with direct file downloads (`/files/.../content`) | Research Data, Documents, Datasets |
| **arXiv** | Papers with direct PDF links (`/pdf/{id}`) | Papers, PDFs |
| **OpenLibrary** | Books with public-domain ebook PDF downloads (via IA) | Books, Ebooks |
| **Wikimedia Commons** | Free media files with direct `upload.wikimedia.org` URLs | Images, Audio, Video, PDFs |
| **Openverse** | CC-licensed images & audio aggregated from 20+ providers | Images, Audio |
| **Nyaa / Sukebei** | Torrents via RSS: direct `.torrent` files, seeders, infoHash | Software, Anime, Data, Adult |
| **npm / crates.io** | Package pages + direct tarball downloads (`.tgz` / `.crate`) | Software Packages |
| **Explicit Content** | Tagged explicit networks with a toggleable filter (`OMNISEARCH_ADULT_ENABLED=0` disables) | Video & Media |

---

## 🚀 Quick Start

### 1. One-Click Launch (Recommended)

Run the launch script:
```bash
./run.sh
```
or with Python:
```bash
python run.py
```

Configuration via environment variables:
| Variable | Default | Effect |
| :--- | :--- | :--- |
| `OMNISEARCH_PORT` | `8000` | Server port |
| `OMNISEARCH_HOST` | `0.0.0.0` | Bind address |
| `OMNISEARCH_ADULT_ENABLED` | `1` | Set `0` to disable the explicit-content source |

This starts the Uvicorn web server and opens the discovery dashboard:
```
======================================================================
  🚀 OmniSearch Universal Discovery Engine v2.2.0
======================================================================
  🌐 Live Dashboard:  http://localhost:8000
  📡 API Docs:        http://localhost:8000/docs
  🔍 Local URL:       http://127.0.0.1:8000
======================================================================
```

---

## 💻 Command Line Interface (CLI)

```bash
# General search
python -m omnisearch.cli "blender 4.0"

# Search for exact phrase in title/filename only
python -m omnisearch.cli '"ubuntu 24.04"' --title-only --limit 10

# Filter by item category (SOFTWARE, ARCHIVE, DOCUMENT, WEB_PAGE, VIDEO, AUDIO, DATASET)
python -m omnisearch.cli "python 3.12" -t SOFTWARE,ARCHIVE

# Filter by file extension
python -m omnisearch.cli "setup" -e exe,iso,dmg

# Boolean logic with specific sources
python -m omnisearch.cli 'linux AND (kernel OR iso) NOT ubuntu' --sources open_web,file_hosts

# Time-bounded search (20s overall deadline), fresh results (bypass cache)
python -m omnisearch.cli "financial report" -e pdf --timeout 20 --no-cache

# Date-range and duration filters
python -m omnisearch.cli "mars rover" --after 2025-01-01 --before 2026-01-01
python -m omnisearch.cli "lecture" -t VIDEO --min-duration 600

# Output machine-readable JSON
python -m omnisearch.cli "financial report" -e pdf --json
```

---

## 📖 REST API Documentation

### `POST /api/search`
Execute a discovery query across files, lockers, and web pages.

**Request Body:**
```json
{
  "query": "\"blender\" AND installer",
  "match_mode": "EXACT_MATCH",
  "title_only": false,
  "sources": ["open_web", "file_hosts"],
  "item_types": ["SOFTWARE", "ARCHIVE"],
  "file_extensions": ["exe", "zip", "dmg"],
  "max_results": 30,
  "max_pages_per_source": 3,
  "timeout_seconds": 35,
  "min_score": 0.1,
  "language": "en",
  "published_after": "2025-01-01T00:00:00Z",
  "published_before": null,
  "allow_cache": true,
  "cache_ttl_seconds": 3600
}
```

### `POST /api/extract`
Directly extract structured file/metadata from any target URL (SSRF-protected: private/loopback/metadata IPs are rejected, redirects re-validated).

**Request Body:**
```json
{
  "url": "https://www.mediafire.com/file/example/package.zip/file"
}
```

### `GET /api/sources`
List all registered discovery adapters and their real-time rate limits.

### `GET /api/cache/stats`
Current query cache occupancy (`entries`, `max_entries`).

### `POST /api/cache/clear`
Flush all cached query responses.

### `GET /api/health`
Liveness probe.

---

## 🔍 Query Syntax & Matching Engine

| Syntax | Example | Description |
| :--- | :--- | :--- |
| **Quoted Phrase** | `"machine learning"` | Exact contiguous phrase matching in exact word order. |
| **Boolean AND** | `blender AND linux` | Both terms must be present. |
| **Boolean OR** | `iso OR img` | At least one term must be present. |
| **Negation / NOT** | `python NOT django` or `python -django` | Excludes any item containing the term. |
| **Field Directives** | `title:firmware` or `meta:release` | Restricts term matching to specific metadata fields. |
| **Extension Filter** | `ext:iso` or `ext:zip` | Restricts discovery and matching to specific file extension. |
| **Type Filter** | `type:software` or `type:archive` | Restricts results to specific category (SOFTWARE, ARCHIVE, etc.). |
| **Site Filter** | `site:mediafire.com` or `site:github` | Matches the canonical domain OR platform name (e.g. `site:MediaFire` also works). |

---

## 🧪 Running Automated Tests

OmniSearch includes a comprehensive test suite:

```bash
.venv/bin/pytest -v
```

Verified test coverage (94 tests):
- SSRF security protection rejecting private LANs, link-local, loopback, and cloud metadata (169.254.169.254)
- Deterministic cache key generation (no collision across filters) and LRU capacity eviction
- Async application lifespan with complete HTTP connection pool teardown
- Cyberlocker direct download generation (MediaFire, MEGA, Pixeldrain, Krakenfiles, GDrive, Dropbox, Catbox, Tmpfiles, Bunkr)
- Open HTTP directory table parser (`Index of /`)
- Web page extraction (`ItemType.WEB_PAGE`) and website search filtering
- Word-boundary regex safety (preventing false substrings)
- Exact phrase matching and AST boolean operations
- Canonical URL normalization and duplicate merging (incl. valueless 1fichier params)
- Multi-factor relevance scoring and rank ordering
- `site:` directive domain/platform matching and rejection of wrong hosts
- FLEXIBLE_MATCH partial-term salvage and EXACT_MATCH strictness
- `min_score` enforcement and structured date/duration/language filters
- Host-boundary platform resolution (no `debunkr.com` → Bunkr false positives)
- Overall search deadline enforcement and per-source candidate caps
- MRSS query-term filtering and explicit-content source toggle
- HTTP client POST path exercising rate limiter and retries
- v2.2 adapters: GitHub (repos + release assets), HuggingFace (models/datasets),
  Zenodo (direct file links), arXiv (Atom→PDF), OpenLibrary (public ebooks),
  Commons (direct upload URLs, utm-stripped), Openverse (image+audio),
  Nyaa (RSS torrents w/ seeders+infoHash), npm/crates.io (tarballs)

---

## 📂 Architecture

```
├── omnisearch/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py                    # Rich CLI tool (timeout/date/duration/cache flags)
│   ├── models/
│   │   ├── item.py               # Canonical ItemRecord, ItemType & MatchProvenance
│   │   ├── video.py              # Backward-compatible alias forwarding to item.py
│   │   └── query.py              # SearchQuery, ASTNodes & Options
│   ├── core/
│   │   ├── normalizer.py         # Unicode NFKC, word boundary regex, stemmer
│   │   ├── query_parser.py       # Grammar lexer and recursive descent parser
│   │   ├── matcher.py            # Match evaluator, FLEXIBLE salvage & provenance generator
│   │   ├── dedup.py              # Canonical resolution (host-anchored) & metadata merger
│   │   ├── ranker.py             # Multi-factor relevance scoring
│   │   ├── http_client.py        # Token-bucket rate limiter (non-blocking) & resilient GET/POST
│   │   ├── cache.py              # TTL cache engine
│   │   └── orchestrator.py       # Multi-source concurrent search with overall deadline
│   ├── extractors/
│   │   ├── file_hosts.py         # Cyberlocker resolvers & Open Directory parser
│   │   ├── html_meta.py          # Standard HTML Meta & Web page extractor
│   │   ├── json_ld.py            # Schema.org structured data parser
│   │   ├── opengraph.py          # OpenGraph metadata parser
│   │   ├── oembed.py             # oEmbed endpoint discoverer
│   │   └── page_extractor.py     # Unified page extractor
│   ├── adapters/
│   │   ├── base.py               # Abstract BaseSourceAdapter
│   │   ├── file_hosts.py         # Cyberlocker & cloud storage adapter
│   │   ├── open_web.py           # Multi-engine crawler & Wikipedia OpenSearch
│   │   ├── adult_web.py          # Explicit Content adapter (env-toggleable)
│   │   ├── youtube.py            # YouTube Data API & Invidious
│   │   ├── vimeo.py              # Vimeo API & oEmbed
│   │   ├── dailymotion.py        # Dailymotion Graph API
│   │   ├── internet_archive.py   # Internet Archive search
│   │   ├── peertube.py           # PeerTube federated network
│   │   ├── mrss.py               # MediaRSS XML feeds (query-filtered)
│   │   ├── github.py             # GitHub repos & release binaries
│   │   ├── huggingface.py        # HuggingFace models & datasets
│   │   ├── academic.py           # Zenodo (research files) & arXiv (paper PDFs)
│   │   ├── library_media.py      # OpenLibrary (books) & Wikimedia Commons (media)
│   │   ├── openverse.py          # Openverse CC images & audio
│   │   ├── torrents.py           # Nyaa/Sukebei torrents via RSS
│   │   ├── registries.py         # npm & crates.io package registries
│   │   └── generic_web.py        # Generic web structured discovery
│   ├── api/
│   │   ├── app.py                # FastAPI app & static file routing
│   │   └── routes.py             # REST API endpoints (+ cache stats/clear)
│   └── web/
│       └── static/
│           ├── index.html        # Clean discovery dashboard
│           ├── style.css         # Modern list view CSS design system
│           └── app.js            # Interactive client with search highlights
├── tests/                        # Full automated test suite (94 tests)
├── assets/
│   └── logo.jpg                  # OmniSearch logo
├── pyproject.toml
├── LICENSE                       # GNU General Public License v3.0
├── run.py
├── run.sh
└── README.md
```

---

## 📄 License

OmniSearch is licensed under the **GNU General Public License v3.0 (GPL-3.0)**. See the [LICENSE](LICENSE) file for the full text.

