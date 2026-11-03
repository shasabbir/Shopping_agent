# 🇧🇩 Bangladesh AI Shopping Decision Agent & Multi-Store Price Comparison Engine

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-orange.svg)](https://github.com/langchain-ai/langgraph)
[![Google Gemini](https://img.shields.io/badge/LLM-Google%20Gemini-4285F4.svg)](https://aistudio.google.com/)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit%201.38+-FF4B4B.svg)](https://streamlit.io/)
[![SQLite / PostgreSQL](https://img.shields.io/badge/Database-SQLite%20(WAL)%20%7C%20PostgreSQL-336791.svg)](https://www.sqlalchemy.org/)
[![Anti-Bot Stealth](https://img.shields.io/badge/Stealth-curl--cffi%20TLS-009688.svg)](https://github.com/yifeikong/curl_cffi)
[![Tests](https://img.shields.io/badge/Tests-29%20Passing-brightgreen.svg)](#-testing-suite--verification)

An autonomous, agentic AI shopping assistant specialized in Bangladesh's e-commerce ecosystem. Unlike traditional search engines or simple affiliate scrapers, this system combines **a local-first multi-store continuous web crawler**, an **anti-bot stealth daemon**, a **universal Schema.org JSON-LD / semantic extractor**, a **dual-model database** (`Product` vs. `Offer`), and a **4-node LangGraph agentic reasoning engine** powered by Google Gemini.

It autonomously aggregates products across **25+ Bangladeshi retail stores** (e.g., Star Tech, Ryans Computers, TechLand BD, Pickaboo, Daraz, Apple Gadgets BD, Skyland, Custom Mac, Bata, Apex, etc.), clusters identical models under canonical product cards, computes live multi-seller price spreads, analyzes warranty risks (Official Brand Warranty vs. Gray Market / Shop Warranty), and delivers transparent **"Why Buy"** and **"Why NOT Buy"** recommendations in **English, Bangla, and Banglish**.

---

## 📑 Table of Contents
1. [Architecture Overview](#-architecture-overview)
2. [Key Capabilities & Features](#-key-capabilities--features)
3. [Project Directory & File Structure](#-project-directory--file-structure)
4. [Deep Developer Implementation Details](#-deep-developer-implementation-details)
   - [Relational Dual-Model Architecture (`Product` vs. `Offer`)](#1-relational-dual-model-architecture-product-vs-offer)
   - [Continuous Multi-Host Stealth Crawler Daemon](#2-continuous-multi-host-stealth-crawler-daemon)
   - [Anti-Bot Cadence & TLS Impersonation Engine](#3-anti-bot-cadence--tls-impersonation-engine)
   - [Store-Agnostic Universal Extractor](#4-store-agnostic-universal-extractor)
   - [LangGraph 4-Node Reasoning Pipeline](#5-langgraph-4-node-reasoning-pipeline)
   - [Real-Time Streamlit Live-Streaming Dashboard](#6-real-time-streamlit-live-streaming-dashboard)
5. [Quickstart Setup for Developers (New PC Setup)](#-quickstart-setup-for-developers-new-pc-setup)
   - [Prerequisites](#prerequisites)
   - [Installation & Virtual Environment](#installation--virtual-environment)
   - [Environment Configuration](#environment-configuration)
   - [Database Seeding](#database-seeding)
6. [Running the Application](#-running-the-application)
   - [Web UI Dashboard](#1-launch-the-streamlit-web-dashboard)
   - [CLI Interactive Query Mode](#2-run-via-command-line-cli)
   - [Docker & Docker-Compose Deployment](#3-run-with-docker--docker-compose)
7. [Testing Suite & Verification](#-testing-suite--verification)
8. [Developer Upgrade Roadmap & Extension Guide](#-developer-upgrade-roadmap--extension-guide)

---

## 🏛️ Architecture Overview

The system operates as a hybrid, local-first intelligence network:

```mermaid
graph TD
    subgraph Web_Sources["25+ Bangladeshi E-Commerce Stores"]
        S1["Star Tech"]
        S2["Ryans Computers"]
        S3["TechLand BD"]
        S4["Pickaboo"]
        S5["Apple Gadgets BD"]
        S6["Daraz BD, Skyland, etc."]
    end

    subgraph Crawler_Core["Stealth Engine & Frontier Queue (src/crawler/)"]
        F["CrawlFrontier (DB Queue)<br/>Priorities: Sitemap (20), Category (10), Product (0)"]
        PE["PersonaManager<br/>TLS Impersonation: Chrome 124, Edge 124, Safari 17"]
        CAD["AntiBotCadence<br/>Poisson/Pareto delays, Log-normal jitter"]
        CB["StoreCircuitBreaker<br/>Per-host cooldowns & 429/403 backoff"]
        DAEMON["ContinuousStealthCrawler Daemon<br/>Non-blocking Multi-Worker Pool"]
    end

    subgraph Extraction["Universal Extractor (src/crawler/universal_extractor.py)"]
        UE["Store-Agnostic Parser"]
        JSONLD["Schema.org JSON-LD & Microdata"]
        OG["OpenGraph & Semantic HTML"]
        REGEX["Strict BDT Regex & Bengali Numerals (০-৯)"]
        SPEC["Spec Filter (Rejects mAh, Hz, RPM, etc.)"]
    end

    subgraph Database_Layer["Database Layer (src/database.py)"]
        DB[("SQLite WAL / PostgreSQL")]
        STORES[("stores")]
        PRODUCTS[("products (Canonical Models)")]
        OFFERS[("offers (Store URLs & Live Prices)")]
        HIST[("price_history")]
    end

    subgraph LangGraph_Agent["Agentic Shopping Pipeline (src/graph.py)"]
        N1["requirement_analyzer Node<br/>Multilingual Intent (EN / BN / Banglish)"]
        N2["search_coordinator Node<br/>Local Catalog Search + Multi-Offer Grouping"]
        N3["product_extractor Node<br/>Normalization & Spec Enrichment"]
        N4["recommendation_agent Node<br/>Gemini 1.5/2.5 Flash Value Scoring"]
    end

    subgraph User_Interfaces["User Experience Layer"]
        UI["Streamlit 3-Tab Web UI (app.py)<br/>Auto-Refresh Live Stream (@st.fragment)"]
        CLI["Interactive CLI (main.py)"]
    end

    S1 & S2 & S3 & S4 & S5 & S6 --> DAEMON
    F --> DAEMON
    PE & CAD & CB --> DAEMON
    DAEMON --> UE
    UE --> JSONLD & OG & REGEX & SPEC
    JSONLD & OG & REGEX & SPEC --> DB
    DB --> STORES & PRODUCTS & OFFERS & HIST

    UI & CLI --> N1
    N1 --> N2
    N2 --> DB
    N2 --> N3
    N3 --> N4
    N4 --> UI & CLI
```

---

## 🌟 Key Capabilities & Features

1. **Local-First Zero Search Engine Bottleneck**:
   - Instead of scraping live search engine result pages during user queries (which triggers search engine CAPTCHAs, rate-limits, and 30-second delays), products are continuously crawled into a high-concurrency local database.
2. **Dual-Model Multi-Seller Aggregation**:
   - Solves the store duplication problem. When 4 retailers sell the same *Lenovo Legion Pro 5*, the user sees **one canonical product card** containing a live breakdown of all 4 competing store offers, lowest price, price differences, and respective warranty terms.
3. **Advanced Anti-Bot Stealth Architecture**:
   - Rotates browser identities with coherent TLS Client Hello fingerprints (`chrome124`, `edge124`, `safari17_0`), matching User-Agents, and `Sec-Ch-Ua` client hints using `curl-cffi`.
   - Simulates human browsing cadence with Poisson process request intervals, Pareto browsing bursts, diurnal day-night activity cycles, and log-normal jitter.
   - Independent per-host circuit breakers isolate rate limits (429/403) so one rate-limited store never stalls crawling for the other 24 stores.
4. **100% Store-Agnostic Universal Extraction**:
   - Zero hardcoded CSS selectors per website. Extracts structured catalog data from Schema.org JSON-LD scripts, OpenGraph meta tags, and semantic tables.
   - Rejects non-price technical specifications (e.g. `5000 mAh`, `144 Hz`, `1200 RPM`, `65 Watts`) from being mistakenly parsed as currency.
   - Converts Bengali numerals (`০১২৩৪৫৬৭৮৯` to `0123456789`) and cleans SEO titles.
5. **LangGraph Multilingual Decision Engine**:
   - Understands native English, Bengali script (বাংলা), and Banglish (*"amar 40k er moddhe bhalo camera phone lagbe"*).
   - Gemini comparative decision agent assigns value scores (0–10), highlights "Why Buy" and "Why NOT Buy", notes Bangladesh official vs. unofficial warranty warnings, and calculates verified monetary savings.
6. **Real-Time Streamlit Auto-Refresh Dashboard**:
   - Utilizes Streamlit's `@st.fragment` architecture to live-stream crawler throughput (requests/min, items/min), active parallel worker statuses, frontier queue health, and store catalog rosters without page reloading.

---

## 📂 Project Directory & File Structure

```
Shopping agent/
├── app.py                      # Main Streamlit 3-Tab Web UI (Live-Streaming Dashboard)
├── main.py                     # Interactive CLI interface for ad-hoc shopping queries
├── requirements.txt            # Python dependencies (LangChain, LangGraph, curl-cffi, Streamlit, etc.)
├── Dockerfile                  # Production hardened non-root container configuration
├── docker-compose.yml          # Multi-container setup (Streamlit app + PostgreSQL 16)
├── deploy.sh                   # Deployment script for Docker environments
├── .env.example                # Template for environment variables (Gemini API key, DB URL)
├── .gitignore                  # Git ignore rules (includes shopping_agent.db*)
├── upgrade_master_plan.md      # Strategic architecture upgrade blueprint
├── README.md                   # Complete developer & user documentation (this file)
│
├── src/
│   ├── __init__.py
│   ├── models.py               # Pydantic schemas (UserRequirement, ProductSpec, StoreOffer, State)
│   ├── database.py             # SQLAlchemy models, SQLite WAL tuning, 25 seed stores & queries
│   ├── graph.py                # LangGraph 4-node StateGraph compilation & execution entrypoint
│   ├── llm.py                  # Google Gemini client initialization with graceful mock fallbacks
│   ├── ui_helpers.py           # Custom CSS, product cards, seller pills, and comparison tables
│   │
│   ├── crawler/                # Core Web Crawling & Anti-Bot Infrastructure
│   │   ├── __init__.py
│   │   ├── stealth_engine.py   # PersonaManager, AntiBotCadence, StoreCircuitBreaker
│   │   ├── universal_extractor.py # JSON-LD, Microdata, OpenGraph, strict price & spec parsers
│   │   ├── universal_crawler.py   # Synchronous / ad-hoc single-store crawler & URL classifier
│   │   └── daemon_crawler.py      # Multi-worker continuous background crawler daemon
│   │
│   ├── nodes/                  # LangGraph Workflow Nodes
│   │   ├── __init__.py
│   │   ├── requirement_analyzer.py # Intent extraction (English / Bangla / Banglish)
│   │   ├── search_coordinator.py   # Local database retrieval & multi-offer aggregation
│   │   ├── product_extractor.py    # Spec normalization & Jina Reader fallback
│   │   └── recommendation_agent.py # Gemini price-performance comparative decision agent
│   │
│   └── tools/                  # Auxiliary Tools & Open-Web Fallbacks
│       ├── __init__.py
│       ├── search.py           # DuckDuckGo fallback search with Bangladesh domain targeting
│       └── jina_reader.py      # Jina AI Reader client for markdown extraction
│
└── tests/                      # Automated Test Suite (29 unit & end-to-end integration tests)
    ├── __init__.py
    ├── test_crawler.py         # JSON-LD, HTML fallback, unit-filtering, DB clustering tests
    ├── test_stealth_and_frontier.py # Persona coherence, cadence delays, circuit breakers, daemon
    ├── test_requirements.py    # English, Bangla, Banglish requirement parsing tests
    ├── test_search_and_jina.py # BDT price extraction, store recognition, DDG coordinator tests
    ├── test_ui.py              # Currency formatting, HTML seller badges, comparison dataframes
    └── test_end_to_end.py      # End-to-end LangGraph pipeline tests for laptops and phones
```

---

## 🔬 Deep Developer Implementation Details

### 1. Relational Dual-Model Architecture (`Product` vs. `Offer`)
Located in [`src/database.py`](file:///d:/Shopping%20agent/src/database.py). The data layer decouples the physical concept of a product from specific retailer offerings:

- **`Store` (`stores`)**: Stores metadata for each retailer (`name`, `base_url`, `sitemap_url`, `is_active`, `status`, `total_products_found`, `last_crawled_at`). Pre-seeded with 25 top Bangladeshi e-commerce stores.
- **`Product` (`products`)**: Canonical entity (`canonical_name`, `brand`, `category`, `model_number`, `normalized_specs_json`, `primary_image_url`). Independent of any single retailer.
- **`Offer` (`offers`)**: Links a `Product` to a specific `Store` (`price_bdt`, `regular_price_bdt`, `product_url`, `in_stock`, `warranty`, `raw_specs_json`, `last_checked_at`).
- **`PriceHistory` (`price_history`)**: Appends historical price snapshots whenever an offer is re-scraped, enabling future price-drop charts and volatility tracking.
- **`CrawlFrontier` (`crawl_frontier`)**: Priority queue for continuous crawling (`url`, `url_type`, `priority`, `status`, `depth`, `requires_browser`, `retry_count`, `next_eligible_at`, `last_crawled_at`).
  - **Priority Hierarchy**: Sitemaps (`priority=20`), Category Catalog Pages (`priority=10`), Direct Product URLs (`priority=0`).

#### SQLite WAL Mode & Concurrency Tuning
To allow parallel crawler background threads to write while the Streamlit UI and LangGraph nodes read simultaneously without `database is locked` errors, [`src/database.py`](file:///d:/Shopping%20agent/src/database.py) configures the SQLite connection with:
```python
cursor.execute("PRAGMA journal_mode=WAL")       # Write-Ahead Logging allows concurrent reads & writes
cursor.execute("PRAGMA synchronous=NORMAL")     # Faster writes while maintaining durability
cursor.execute("PRAGMA busy_timeout=30000")     # Wait up to 30 seconds on locked tables before erroring
cursor.execute("PRAGMA cache_size=-64000")      # 64 MB memory cache for rapid index lookups
```

#### Canonical Clustering & Deduplication
When the crawler discovers an offer, [`upsert_crawled_offer()`](file:///d:/Shopping%20agent/src/database.py) executes fuzzy token clustering (`normalize_model_key()`) to match existing canonical products by category, brand, and normalized model tokens before creating a new canonical product.

---

### 2. Continuous Multi-Host Stealth Crawler Daemon
Located in [`src/crawler/daemon_crawler.py`](file:///d:/Shopping%20agent/src/crawler/daemon_crawler.py).
Designed to gather vast product catalogs without being blocked:

- **Non-Blocking Multi-Worker Architecture**: Runs configurable parallel worker threads (default: 6, max: 16).
- **Fair Interleaved Host Scheduling**: Workers rotate among distinct active store hosts. If Worker 1 is crawling Star Tech, Worker 2 crawls Ryans, Worker 3 crawls TechLand, and Worker 4 crawls Pickaboo. No single store receives consecutive rapid hits.
- **Zero Head-of-Line Blocking**: Each store host maintains its own next eligible timestamp (`next_eligible_at`). If one store requires a 10-second dwell time, other workers continue crawling other stores uninterrupted.
- **Rolling Telemetry**: Computes rolling 60-second throughput metrics (`req_per_min`, `prod_per_min`) displayed live in the Streamlit UI.

---

### 3. Anti-Bot Cadence & TLS Impersonation Engine
Located in [`src/crawler/stealth_engine.py`](file:///d:/Shopping%20agent/src/crawler/stealth_engine.py).

#### A. TLS Fingerprint Impersonation (`curl-cffi`)
Standard Python `requests` or `urllib` headers are trivially identified by Cloudflare and Akamai via JA3/JA4 TLS handshake fingerprints. The engine uses `curl-cffi` to simulate authentic browser handshakes:
- **`PersonaManager`**: Assigns coherent personas (`Chrome 124 Windows`, `Edge 124 Windows`, `Chrome 120 macOS`, `Safari 17 macOS`).
- **Coherence Guarantee**: Matches `curl-cffi`'s `impersonate` target directly with authentic User-Agents, `Sec-Ch-Ua`, and `Sec-Ch-Ua-Platform` headers so no client-hint contradictions exist.

#### B. Biological & Human Cadence (`AntiBotCadence`)
- **Poisson Arrival Process**: Request intervals follow exponential and Poisson distributions rather than detectable fixed timers.
- **Pareto Burst Browsing**: Simulates human behavior (browsing 3–5 items in rapid succession, followed by a longer 15–30s reading pause).
- **Circadian Cycle Factor**: Automatically varies dwell times depending on the time of day in Bangladesh (slower overnight cadence, normal daytime activity).
- **Speed Profiles**:
  - `stealth`: 3.0s – 12.0s delays + 20s browsing pauses.
  - `normal`: 1.8s – 7.5s log-normal jitter (recommended default).
  - `turbo`: 0.8s – 3.5s rapid gathering for resilient or local mirrors.

#### C. Store Circuit Breakers (`StoreCircuitBreaker`)
- Tracks HTTP response codes per store.
- On HTTP `429 (Too Many Requests)` or `403 (Forbidden)`, the circuit trips into exponential cooldown (60s, 120s, 300s, up to 900s).
- During cooldown, other workers skip the affected host entirely, allowing the target server's rate-limiting window to expire naturally.

---

### 4. Store-Agnostic Universal Extractor
Located in [`src/crawler/universal_extractor.py`](file:///d:/Shopping%20agent/src/crawler/universal_extractor.py).
Zero hardcoded per-store extraction scripts:

1. **Schema.org JSON-LD Parser**: Inspects `<script type="application/ld+json">` for `@type: "Product"` or nested `@graph` nodes. Extracts `name`, `brand`, `model`, `image`, `offers.price`, `offers.priceCurrency`, and `offers.availability`.
2. **OpenGraph & Microdata Fallback**: Parses `og:title`, `og:image`, `og:price:amount`, `meta[itemprop="price"]`, and `itemprop="availability"`.
3. **Strict Price & Bengali Numeral Extraction**:
   - Converts Bengali digits (`০১২৩৪৫৬৭৮৯` -> `0123456789`).
   - Rejects technical specs using a negative lookahead regex:
     ```regex
     ([\d,]{2,9}(?:\.\d{1,2})?)\s*(?:৳|tk\.?|bdt|taka|টাকা)(?!\s*(?:rpm|mah|dpi|hz|w|watt|gb|tb|v|volt|fps|nits)\b)
     ```
   - Prevents `5000 mAh Battery` or `144 Hz Display` from overwriting the actual price.
4. **Warranty Detection**: Identifies official warranty markers in Bangladesh (*"Official Brand Warranty"*, *"1 Year Replacement"*, *"Unofficial / Shop Warranty"*).

---

### 5. LangGraph 4-Node Reasoning Pipeline
Located in [`src/graph.py`](file:///d:/Shopping%20agent/src/graph.py) and [`src/nodes/`](file:///d:/Shopping%20agent/src/nodes/).

```mermaid
graph LR
    START([User Query]) --> N1[requirement_analyzer]
    N1 --> N2[search_coordinator]
    N2 --> N3[product_extractor]
    N3 --> N4[recommendation_agent]
    N4 --> END([Ranked Recommendations])
```

1. **`requirement_analyzer`**:
   - Parses budget in BDT (recognizes *"120k"*, *"1.2 lakh"*, *"৳১,২০,০০০"*, *"under 45000"*).
   - Identifies product category (Laptop, Phone, Monitor, Footwear, Kitchen Appliance, etc.).
   - Extracts usage constraints (e.g., *gaming*, *coding*, *camera*, *office work*).
   - Fully supports Bengali script, English, and Banglish.
2. **`search_coordinator`**:
   - Queries the local database first using canonical name and category matching.
   - Groups multi-store offers into unified `ProductSpec` objects.
   - If local database results are insufficient, falls back to DuckDuckGo search across top Bangladeshi domains.
3. **`product_extractor`**:
   - Normalizes specifications and executes Jina Reader fallback when crawling open-web links.
4. **`recommendation_agent`**:
   - Invokes Google Gemini (`gemini-1.5-flash` or `gemini-2.5-flash`).
   - Calculates a normalized Value Score (0 to 10).
   - Generates persuasive **"Why Buy"** bullet points and critical **"Why NOT Buy"** caveats.
   - Outlines specific Bangladesh market purchase considerations (e.g., verifying physical IMEI on BTRC database, official vs. gray market warranty risks).

---

### 6. Real-Time Streamlit Live-Streaming Dashboard
Located in [`app.py`](file:///d:/Shopping%20agent/app.py). Built with three distinct functional tabs:

- **Tab 1: 🛒 AI Shopping Assistant**:
  - Interactive search bar with instant preset category chips.
  - Parsed intent summary badges (Category, Budget BDT, Usage).
  - **Hero Winning Card**: Displays Rank #1 recommendation, lowest price, value score, savings pill, and multi-seller comparison tags.
  - **Product Grid**: Expandable cards with specification tags, "Why Buy", "Why NOT Buy", and direct retailer store links.
  - **Side-by-Side Comparison Matrix**: Interactive DataFrame comparing candidate specs, prices, and warranties.
- **Tab 2: 🏬 Store Manager & Sequential Crawler**:
  - Real-time catalog overview metrics (configured stores, active targets, indexed products, deals).
  - **Continuous Stealth Daemon Controls**: Start/stop background crawler, select anti-bot cadence profile (`stealth`, `normal`, `turbo`), and configure worker concurrency (1–12 threads).
  - **Live Worker Pool Telemetry**: Dynamically renders active worker slots, current host targets, elapsed times, and cooldown warnings via `@st.fragment` without full-page reloads.
  - Store roster management table with toggle, test crawl, and delete controls.
- **Tab 3: 📦 Local Catalog Explorer**:
  - Direct database search with text filter and category dropdown.
  - Displays indexed product images, lowest current BDT prices, multi-store seller badges, and specification chips.

---

## 🚀 Quickstart Setup for Developers (New PC Setup)

Follow these instructions to set up, run, and develop the project on another machine.

### Prerequisites
- **Python 3.11, 3.12, or 3.13** installed.
- **Git** installed.
- *(Optional)* **Docker & Docker Compose** (for containerized deployment).

---

### Installation & Virtual Environment

#### On Windows (PowerShell):
```powershell
# 1. Clone repository
git clone https://github.com/shasabbir/Shopping_agent.git
cd "Shopping agent"

# 2. Create Python virtual environment
py -3.13 -m venv .venv

# 3. Activate virtual environment
.\.venv\Scripts\Activate.ps1

# 4. Upgrade pip and install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
```

#### On Linux / macOS (Bash):
```bash
# 1. Clone repository
git clone https://github.com/shasabbir/Shopping_agent.git
cd "Shopping agent"

# 2. Create virtual environment
python3 -m venv .venv

# 3. Activate virtual environment
source .venv/bin/activate

# 4. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

---

### Environment Configuration

1. Copy the example environment template:
   ```powershell
   # Windows PowerShell
   Copy-Item .env.example .env

   # Linux / macOS
   cp .env.example .env
   ```

2. Edit `.env` with your preferred settings:
   ```env
   # Google Gemini API Key (Get a free key from https://aistudio.google.com/)
   GEMINI_API_KEY=your_gemini_api_key_here

   # LLM Model (e.g. gemini-1.5-flash, gemini-2.5-flash)
   GEMINI_MODEL=gemini-1.5-flash

   # Jina Reader Base URL
   JINA_READER_BASE_URL=https://r.jina.ai/

   # Database Connection (Optional: omit to use local SQLite shopping_agent.db)
   # DATABASE_URL=postgresql://postgres:postgrespassword@localhost:5432/shopping_agent
   ```

> [!NOTE]
> If `GEMINI_API_KEY` is not provided, the agent automatically runs in **Offline / Mock Mode**, generating deterministic fallback responses so you can test the entire pipeline offline with zero API costs.

---

### Database Seeding
The application automatically creates all necessary database tables and populates the 25 default Bangladesh stores on its first execution. You do not need to run manual SQL migration scripts.

---

## 💻 Running the Application

### 1. Launch the Streamlit Web Dashboard
```powershell
# Make sure your virtual environment is activated
streamlit run app.py
```
Open your browser at **`http://localhost:8501`**.

- To start indexing products immediately, switch to **Tab 2 ("Store Manager & Sequential Crawler")**, select your cadence (`Balanced` or `Turbo`), choose worker concurrency (e.g. 6 workers), and click **"▶ Start Continuous Crawler"**.
- Watch the live telemetry metrics stream in real time.
- Switch to **Tab 1 ("AI Shopping Assistant")** to run natural language shopping queries across the gathered database.

---

### 2. Run via Command-Line (CLI)

Run interactively:
```powershell
python main.py
```

Or pass a query directly as an argument:
```powershell
python main.py --query "Best gaming laptop under 130000 BDT in Bangladesh"
```

Example queries to test:
- `Need a smartphone under 45k taka with excellent camera and AMOLED display`
- `Best ultrabook for coding under 90000 BDT with at least 16GB RAM`
- `amar 30k er moddhe bhalo phone lagbe` *(Banglish query)*
- `Air fryer under 10000 BDT for home kitchen`

---

### 3. Run with Docker & Docker-Compose

To run the full stack in containers with a dedicated PostgreSQL database:

```bash
# Build and run containers in background
docker-compose up -d --build

# View real-time logs
docker-compose logs -f shopping-agent

# Tear down services
docker-compose down
```

The Streamlit interface will be available at `http://localhost:8501`.

---

## 🧪 Testing Suite & Verification

The project includes a comprehensive suite of **29 unit and end-to-end integration tests** covering all modules:

```powershell
# Run all tests with verbose output
pytest -v tests/
```

### Test Suite Breakdown:
| Test Module | Coverage & Validation |
| :--- | :--- |
| [`tests/test_crawler.py`](file:///d:/Shopping%20agent/tests/test_crawler.py) | Schema.org JSON-LD extraction, DOM heuristics, unit-rejection filters (preventing mAh/Hz prices), cross-seller DB clustering, Next.js script extraction. |
| [`tests/test_stealth_and_frontier.py`](file:///d:/Shopping%20agent/tests/test_stealth_and_frontier.py) | `PersonaManager` TLS consistency, `AntiBotCadence` delay intervals, `StoreCircuitBreaker` backoff, queue priority lifecycle, multi-host concurrency. |
| [`tests/test_requirements.py`](file:///d:/Shopping%20agent/tests/test_requirements.py) | Intent extraction across Laptops, Phones, Footwear, Kitchen Appliances, and Bengali / Banglish detection. |
| [`tests/test_search_and_jina.py`](file:///d:/Shopping%20agent/tests/test_search_and_jina.py) | Bangladesh store domain resolution, BDT price regex, specification extraction, DuckDuckGo coordinator fallbacks. |
| [`tests/test_ui.py`](file:///d:/Shopping%20agent/tests/test_ui.py) | BDT currency formatting (`৳ 1,20,000`), HTML store badges, multi-offer comparison DataFrames. |
| [`tests/test_end_to_end.py`](file:///d:/Shopping%20agent/tests/test_end_to_end.py) | Full 4-node LangGraph execution for laptop and smartphone pipelines. |

---

## 🗺️ Developer Upgrade Roadmap & Extension Guide

If you are continuing development on this codebase or extending it on another machine, here are recommended next steps:

### 1. Adding New Bangladesh Stores
To add new stores to the default crawler roster, open [`src/database.py`](file:///d:/Shopping%20agent/src/database.py) and append entries to `DEFAULT_BANGLADESH_STORES`:
```python
{
    "name": "New Store BD",
    "base_url": "https://www.newstorebd.com",
    "sitemap_url": "https://www.newstorebd.com/sitemap.xml",
}
```
Or simply use the **Store Manager UI** in Tab 2 to add the store URL dynamically without modifying code.

### 2. Transitioning SQLite to PostgreSQL
For high-traffic production environments, PostgreSQL is supported out-of-the-box:
1. Provide `DATABASE_URL=postgresql://user:password@localhost:5432/shopping_agent` in `.env`.
2. SQLAlchemy automatically switches connection pooling from SQLite WAL mode to PostgreSQL connection pooling with zero code changes.

### 3. Playwright Dynamic Headless Rendering
For single-page JavaScript applications (e.g. React/Vue storefronts that do not render server-side HTML or JSON-LD):
- The frontier model already tracks `requires_browser=True`.
- Connect [`src/crawler/stealth_engine.py`](file:///d:/Shopping%20agent/src/crawler/stealth_engine.py)'s `PlaywrightHumanizer` into `UniversalStoreCrawler` to evaluate JS-rendered DOMs when static HTTP fetches return no product elements.

### 4. Advanced Entity Resolution
- Upgrade `normalize_model_key()` in [`src/database.py`](file:///d:/Shopping%20agent/src/database.py) to use lightweight vector embeddings or rapid Levenshtein token sorting for even tighter cross-store clustering across irregular product titles.

---

## 🛡️ License & Acknowledgements

- **Engine:** Built with [LangGraph](https://github.com/langchain-ai/langgraph), [LangChain](https://github.com/langchain-ai/langchain), and [Google Gemini](https://aistudio.google.com/).
- **Stealth Networking:** Powered by [curl-cffi](https://github.com/yifeikong/curl_cffi).
- **Frontend:** Powered by [Streamlit](https://streamlit.io/).
- Built specifically for the **Bangladesh E-Commerce Market** 🇧🇩.
