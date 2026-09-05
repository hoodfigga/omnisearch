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
  <a href="#-command-line-interface-cli">CLI</a> •
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
     - `FLEXIBLE_MATCH`: Term proximity matching.
     - `SEMANTIC_EXPANSION`: Stemmed expansion with provenance tracking.

3. **Canonical Identity & Deduplication**:
   - Strips tracking tokens (`utm_*`, `si`, `ref`, `gclid`, `fbclid`).
   - Merges duplicates across mirrors into the richest metadata record.
   - Synthesizes direct download URLs, verified file sizes, and multi-source provenance.

4. **Multi-Factor Relevance Ranker**:
   - Boosts exact title/filename matches, direct download links (+0.25 bonus), confirmed file sizes (+0.10 bonus), and file extension matches.
   - Computes query coverage, metadata completeness, and recency decay.

5. **Modern List-Format Dashboard & CLI**:
   - Fast, responsive list UI with category badges, file extension tags, direct download triggers, and match provenance inspection.
   - Rich terminal CLI with `-t` (item type) and `-e` (file extension) filters.

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
| **Bunkr** | Direct media stream & download link extraction | Videos, Audio, Archives |
| **Google Drive** | Direct download link generation (`uc?export=download&id=...`) | Any |
| **Dropbox** | Direct download parameter conversion (`?dl=1`) | Any |
| **Turbobit / Nitroflare / DDownload / Katfile** | Download page & file size detection | Any |
| **Open HTTP Directories (Apache, Nginx, Caddy)** | Native parsing of `Index of /` file tables, sizes & direct URLs | Any |
| **Open Web & Wikipedia** | Standard web pages, documentation, and direct file links | Any |
| **Explicit Content** | Tagged explicit networks with toggleable filters | Video & Media |

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

This starts the Uvicorn web server and opens the discovery dashboard:
```
======================================================================
  🚀 OmniSearch Universal Discovery Engine
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
  "allow_cache": true
}
```

### `POST /api/extract`
Directly extract structured file/metadata from any target URL.

**Request Body:**
```json
{
  "url": "https://www.mediafire.com/file/example/package.zip/file"
}
```

### `GET /api/sources`
List all registered discovery adapters and their real-time rate limits.

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
| **Site Filter** | `site:mediafire.com` or `site:github` | Filters by platform host or site domain. |

---

## 🧪 Running Automated Tests

OmniSearch includes a comprehensive test suite with 100% passing coverage:

```bash
.venv/bin/pytest -v
```

Verified test coverage:
- SSRF security protection rejecting private LANs, link-local, loopback, and cloud metadata (169.254.169.254)
- Deterministic cache key generation (no collision across filters) and LRU capacity eviction
- Async application lifespan with complete HTTP connection pool teardown
- Cyberlocker direct download generation (MediaFire, MEGA, Pixeldrain, Krakenfiles, GDrive, Dropbox, Catbox, Tmpfiles, Bunkr)
- Open HTTP directory table parser (`Index of /`)
- Web page extraction (`ItemType.WEB_PAGE`) and website search filtering
- Word-boundary regex safety (preventing false substrings)
- Exact phrase matching and AST boolean operations
- Canonical URL normalization and duplicate merging
- Multi-factor relevance scoring and rank ordering


---

## 📂 Architecture

```
├── omnisearch/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py                    # Rich CLI tool
│   ├── models/
│   │   ├── item.py               # Canonical ItemRecord, ItemType & MatchProvenance
│   │   ├── video.py              # Backward-compatible alias forwarding to item.py
│   │   └── query.py              # SearchQuery, ASTNodes & Options
│   ├── core/
│   │   ├── normalizer.py         # Unicode NFKC, word boundary regex, stemmer
│   │   ├── query_parser.py       # Grammar lexer and recursive descent parser
│   │   ├── matcher.py            # Match evaluator & provenance generator
│   │   ├── dedup.py              # Canonical resolution & metadata merger
│   │   ├── ranker.py             # Multi-factor relevance scoring
│   │   ├── http_client.py        # Token-bucket rate limiter & resilient client
│   │   ├── cache.py              # TTL cache engine
│   │   └── orchestrator.py       # Multi-source concurrent search orchestrator
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
│   │   ├── adult_web.py          # Explicit Content adapter
│   │   ├── youtube.py            # YouTube Data API & Invidious
│   │   ├── vimeo.py              # Vimeo API & oEmbed
│   │   ├── dailymotion.py        # Dailymotion Graph API
│   │   ├── internet_archive.py   # Internet Archive search
│   │   ├── peertube.py           # PeerTube federated network
│   │   ├── mrss.py               # MediaRSS XML feeds
│   │   └── generic_web.py        # Generic web structured discovery
│   ├── api/
│   │   ├── app.py                # FastAPI app & static file routing
│   │   └── routes.py             # REST API endpoints
│   └── web/
│       └── static/
│           ├── index.html        # Clean discovery dashboard
│           ├── style.css         # Modern list view CSS design system
│           └── app.js            # Interactive client with search highlights
├── tests/                        # Full automated test suite (48 tests)
├── assets/
│   └── logo.jpg                  # OmniSearch logo
├── pyproject.toml
├── run.py
├── run.sh
└── README.md
```
