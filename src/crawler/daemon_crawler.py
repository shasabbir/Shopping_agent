import os
import re
import sys
import time
import math
import random
import asyncio
import logging
import threading
from collections import deque
from typing import Dict, List, Optional, Any, Callable, Tuple
from urllib.parse import urlparse, urljoin
import xml.etree.ElementTree as ET

from src.database import (
    get_active_stores,
    pop_next_frontier_item,
    update_frontier_item_result,
    ingest_frontier_urls,
    seed_frontier_from_stores,
    get_frontier_metrics,
    upsert_crawled_offer,
    update_store_crawl_status,
    reset_failed_frontier_urls,
)
from src.crawler.stealth_engine import (
    PersonaManager,
    AntiBotCadence,
    StoreCircuitBreaker,
    PlaywrightHumanizer,
)
from src.crawler.universal_extractor import UniversalProductExtractor
from src.crawler.universal_crawler import (
    PRODUCT_URL_REGEX,
    SPECIFIC_PRODUCT_REGEX,
    IGNORED_REGEX,
    get_url_product_priority,
    create_http_session,
    fetch_response_content,
)

logger = logging.getLogger("ContinuousStealthCrawler")


class ContinuousStealthCrawler:
    """
    High-Performance Multi-Host Concurrent Stealth Crawler Daemon.
    Features:
    1. Concurrent Multi-Host Workers (ThreadPoolExecutor / Worker threads) with non-blocking per-host scheduling.
    2. Zero Cross-Host Head-of-Line Blocking: Independent host dwell times.
    3. Per-Store AntiBot Cadence & Circuit Breakers (429/403 backoff).
    4. Fair Interleaved Host Round-Robin (no single domain is starved or hammered).
    5. Real-Time Telemetry: Rolling 60s requests/min and products/min throughput.
    6. Adaptive TLS Impersonation & Playwright Stealth Escalation.
    """

    def __init__(self, speed_profile: str = "normal", concurrency: int = 6):
        self.speed_profile = speed_profile
        self.concurrency = max(1, min(concurrency, 80))
        self.cadence = AntiBotCadence()
        self.circuit_breaker = StoreCircuitBreaker()
        self.stop_requested = threading.Event()
        self.is_running = False

        self._in_flight_stores: set = set()
        self._in_flight_counts: Dict[int, int] = {}
        self._empty_frontiers: set = set()
        self._large_stores: set = {1, 2, 3, 5, 6, 8, 12, 20, 22, 23, 24}
        self._stores_lock = threading.Lock()
        self._store_cursor: int = 0

        self.worker_slots: Dict[int, Dict[str, Any]] = {}
        self._slots_lock = threading.Lock()

        self.stats: Dict[str, Any] = {
            "total_requests": 0,
            "products_indexed": 0,
            "urls_discovered": 0,
            "errors": 0,
            "rate_limits_hit": 0,
            "started_at": None,
        }
        self._stats_lock = threading.Lock()

        self._recent_requests: deque = deque(maxlen=3000)
        self._recent_products: deque = deque(maxlen=3000)

        self.current_task_info: Dict[str, Any] = {
            "current_store": None,
            "current_url": None,
            "status": "idle",
            "last_active_at": None,
        }
        self.recent_logs: List[str] = []
        self._log_lock = threading.Lock()

    def log(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        with self._log_lock:
            self.recent_logs.append(entry)
            if len(self.recent_logs) > 60:
                self.recent_logs.pop(0)
        logger.info(message)

    def get_throughput(self) -> Dict[str, float]:
        now = time.time()
        cutoff = now - 60.0
        with self._stats_lock:
            while self._recent_requests and self._recent_requests[0] < cutoff:
                self._recent_requests.popleft()
            while self._recent_products and self._recent_products[0] < cutoff:
                self._recent_products.popleft()
            req_per_min = float(len(self._recent_requests))
            prod_per_min = float(len(self._recent_products))
        return {
            "req_per_min": req_per_min,
            "prod_per_min": prod_per_min,
        }

    def get_status(self) -> Dict[str, Any]:
        frontier_metrics = get_frontier_metrics()
        active_stores = get_active_stores()
        cooldown_stores = [
            s["name"] for s in active_stores if not self.circuit_breaker.is_eligible(s["id"])
        ]
        throughput = self.get_throughput()
        with self._slots_lock:
            worker_slots_copy = dict(self.worker_slots)
        with self._stats_lock:
            stats_copy = dict(self.stats)

        # Dynamically refresh large stores and empty frontiers
        store_stats = frontier_metrics.get("store_stats", [])
        if store_stats:
            with self._stores_lock:
                self._large_stores = {
                    s["store_id"] for s in store_stats if s.get("pending", 0) >= 500
                }
                self._empty_frontiers = {
                    s["store_id"] for s in store_stats if s.get("pending", 0) == 0
                }

        active_worker_count = sum(
            1 for w in worker_slots_copy.values() if w.get("status") in ["crawling", "active"]
        )

        return {
            "is_running": self.is_running,
            "speed_profile": self.speed_profile,
            "concurrency": self.concurrency,
            "active_worker_count": active_worker_count,
            "current_store": self.current_task_info.get("current_store"),
            "current_url": self.current_task_info.get("current_url"),
            "stats": stats_copy,
            "throughput": throughput,
            "worker_slots": worker_slots_copy,
            "frontier": frontier_metrics,
            "cooldown_stores": cooldown_stores,
            "recent_logs": list(self.recent_logs),
        }

    def stop(self):
        """Signal the crawler to gracefully stop."""
        self.log("Stop requested. Waiting for in-flight requests to conclude...")
        self.stop_requested.set()

    def _claim_next_eligible_store(self, active_stores: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Fair round-robin claim of an active store with pending work:
        1. Skips stores currently known to have empty frontiers.
        2. Large stores (>= 500 URLs) accommodate up to 2 concurrent workers.
        3. Is eligible under StoreCircuitBreaker (no 429/403 backoff).
        4. Is eligible under AntiBotCadence (human dwell time has elapsed).
        """
        if not active_stores:
            return None

        with self._stores_lock:
            num_stores = len(active_stores)
            start_idx = self._store_cursor % num_stores

            for offset in range(num_stores):
                idx = (start_idx + offset) % num_stores
                store = active_stores[idx]
                store_id = store["id"]

                # 1. Skip stores known to have empty queues
                if store_id in self._empty_frontiers:
                    continue

                # 2. Check in-flight worker capacity (2 for large stores, 1 for others)
                cur_in_flight = self._in_flight_counts.get(store_id, 0)
                max_capacity = 2 if store_id in self._large_stores else 1
                if cur_in_flight >= max_capacity:
                    continue

                # 3. Check Circuit Breaker
                if not self.circuit_breaker.is_eligible(store_id):
                    continue

                # 4. Check Cadence Cooldown
                if not self.cadence.is_store_cadence_eligible(store_id):
                    continue

                # Claim 1 worker slot for this store
                self._in_flight_counts[store_id] = cur_in_flight + 1
                self._in_flight_stores.add(store_id)
                self._store_cursor = (idx + 1) % num_stores
                return store

        return None

    def _release_store_claim(self, store_id: int):
        with self._stores_lock:
            cur = self._in_flight_counts.get(store_id, 1)
            if cur <= 1:
                self._in_flight_counts.pop(store_id, None)
                self._in_flight_stores.discard(store_id)
            else:
                self._in_flight_counts[store_id] = cur - 1

    def _crawl_single_store_url(self, store: Dict[str, Any], session: Any, worker_id: int) -> bool:
        """Fetch and process 1 item from this store's frontier. Returns True if item crawled, False if queue empty."""
        store_id = store["id"]
        store_name = store["name"]

        frontier_item = pop_next_frontier_item(store_id)
        if not frontier_item:
            seed_url = store.get("sitemap_url") or store.get("base_url")
            if seed_url:
                url_type = "sitemap" if (store.get("sitemap_url") and ".xml" in store.get("sitemap_url")) else "category"
                ingest_frontier_urls(store_id, [seed_url], url_type=url_type, priority=20, depth=0)
                frontier_item = pop_next_frontier_item(store_id)

        if not frontier_item:
            return False

        target_url = frontier_item["url"]
        frontier_id = frontier_item["id"]
        url_type = frontier_item.get("url_type", "product")
        requires_browser = frontier_item.get("requires_browser", False) or (self.circuit_breaker.get_recommended_mode(store_id) == "browser")

        # Immediate pre-filter: Skip assets, media, and utility links
        url_prio = get_url_product_priority(target_url)
        if url_prio == 99:
            update_frontier_item_result(frontier_id, "dead")
            return True

        now_str = time.strftime("%H:%M:%S")
        with self._slots_lock:
            self.worker_slots[worker_id] = {
                "worker_id": worker_id,
                "store": store_name,
                "url": target_url,
                "status": "crawling",
                "updated_at": now_str,
            }
        self.current_task_info = {
            "current_store": store_name,
            "current_url": target_url,
            "status": "crawling",
            "last_active_at": now_str,
        }

        now_ts = time.time()
        with self._stats_lock:
            self.stats["total_requests"] += 1
            self._recent_requests.append(now_ts)

        persona = PersonaManager.get_persona_for_store(store_id)
        headers = persona.get_headers(target_url)

        try:
            if requires_browser:
                status_code, html_content = self._fetch_via_browser(target_url, store_name)
            else:
                status_code, html_content, _ = fetch_response_content(
                    session, target_url, headers, timeout=12.0
                )

            # Check for Bot Challenge or WAF Block
            if status_code == 429:
                with self._stats_lock:
                    self.stats["rate_limits_hit"] += 1
                self.circuit_breaker.record_failure(store_id, 429)
                update_frontier_item_result(frontier_id, "failed", http_status=429, backoff_seconds=300)
                self.log(f"⚠️ {store_name} returned 429 (Rate Limited). Enforcing backoff cooldown.")
                return True

            if status_code == 403 or (html_content and ("Just a moment..." in html_content or "Attention Required!" in html_content)):
                self.log(f"🛡️ {store_name} triggered Cloudflare Challenge. Escalating store to browser mode.")
                self.circuit_breaker.record_failure(store_id, 403, "Cloudflare Challenge")
                update_frontier_item_result(frontier_id, "failed", http_status=403, backoff_seconds=60)
                return True

            if not html_content or status_code not in [200, 201, 204]:
                update_frontier_item_result(frontier_id, "failed", http_status=status_code or 500)
                with self._stats_lock:
                    self.stats["errors"] += 1
                return True

            # Success - Process by URL Type
            self.circuit_breaker.record_success(store_id)

            if url_type == "sitemap" or target_url.endswith(".xml") or ".xml" in target_url:
                self._process_sitemap_content(store_id, target_url, html_content)
                update_frontier_item_result(frontier_id, "completed", http_status=status_code)
                self.log(f"📑 {store_name} parsed sitemap: {target_url[:60]}")

            else:
                extracted = None
                if url_prio <= 3 or url_type != "category":
                    extracted = UniversalProductExtractor.extract_from_html(html_content, target_url)

                if extracted and extracted.get("name") and extracted.get("price_bdt"):
                    upsert_crawled_offer(
                        store_id=store_id,
                        store_product_title=extracted["name"],
                        product_url=target_url,
                        price_bdt=extracted["price_bdt"],
                        category=extracted.get("category", "general"),
                        brand=extracted.get("brand"),
                        regular_price_bdt=extracted.get("regular_price_bdt"),
                        in_stock=extracted.get("in_stock", True),
                        warranty=extracted.get("warranty"),
                        specs=extracted.get("specs"),
                        image_url=extracted.get("image_url"),
                        model_number=extracted.get("model_number"),
                    )
                    with self._stats_lock:
                        self.stats["products_indexed"] += 1
                        self._recent_products.append(time.time())
                    update_store_crawl_status(store_id, "crawling", total_found_delta=1)
                    update_frontier_item_result(frontier_id, "completed", http_status=status_code)
                    self.log(f"✅ {store_name} indexed: {extracted['name'][:40]} (BDT {extracted['price_bdt']:,.0f})")

                elif extracted and extracted.get("name") and not extracted.get("price_bdt"):
                    update_frontier_item_result(frontier_id, "completed", http_status=status_code)
                    self.log(f"ℹ️ {store_name} skipped: {extracted['name'][:40]} (No price / Out of stock)")

                else:
                    discovered = self._extract_links_from_category(store, target_url, html_content)
                    if discovered:
                        new_count = ingest_frontier_urls(store_id, discovered, url_type="product", priority=0)
                        with self._stats_lock:
                            self.stats["urls_discovered"] += new_count
                        if new_count > 0:
                            self.log(f"📂 {store_name} category parsed: discovered {new_count} new product links.")
                            with self._stores_lock:
                                self._empty_frontiers.discard(store_id)
                    update_frontier_item_result(frontier_id, "completed", http_status=status_code)

        except Exception as e:
            with self._stats_lock:
                self.stats["errors"] += 1
            update_frontier_item_result(frontier_id, "failed", error=str(e), backoff_seconds=120)
            self.log(f"❌ Error crawling {store_name} ({target_url[:50]}): {e}")

        return True

    def _worker_loop(self, worker_id: int, max_items: Optional[int] = None):
        """Worker thread loop handling non-blocking requests to assigned stores."""
        session, _ = create_http_session(timeout=12.0)
        items_processed = 0

        try:
            while not self.stop_requested.is_set():
                if max_items is not None and items_processed >= max_items:
                    break

                active_stores = get_active_stores()
                if not active_stores:
                    time.sleep(0.5)
                    continue

                store = self._claim_next_eligible_store(active_stores)
                if not store:
                    with self._slots_lock:
                        if worker_id in self.worker_slots and self.worker_slots[worker_id].get("status") != "idle":
                            self.worker_slots[worker_id] = {
                                "worker_id": worker_id,
                                "store": "Interleaving hosts...",
                                "url": "Standing by for next host cooldown...",
                                "status": "idle",
                                "updated_at": time.strftime("%H:%M:%S"),
                            }
                    time.sleep(0.15)
                    continue

                store_id = store["id"]
                store_name = store["name"]

                # Process a continuous mini-session of 2 to 4 URLs for this store
                # Keeps the worker 100% productive and reuses the HTTP/2 connection
                batch_size = 1 if max_items is not None else random.randint(2, 4)

                try:
                    for b_idx in range(batch_size):
                        if self.stop_requested.is_set():
                            break
                        if max_items is not None and items_processed >= max_items:
                            break

                        had_work = self._crawl_single_store_url(store, session, worker_id)
                        if not had_work:
                            with self._stores_lock:
                                self._empty_frontiers.add(store_id)
                            break

                        items_processed += 1

                        # Humanized micro-pause between URLs within the same store session
                        if b_idx < batch_size - 1:
                            delay = self.cadence.calculate_delay(store_id=store_id, speed_profile=self.speed_profile)
                            dwell = max(0.5, min(1.6, delay * 0.4))
                            time.sleep(dwell)

                finally:
                    # Enforce per-host cadence dwell time for this store
                    self.cadence.record_store_request(store_id, speed_profile=self.speed_profile)
                    self._release_store_claim(store_id)
                    with self._slots_lock:
                        self.worker_slots[worker_id] = {
                            "worker_id": worker_id,
                            "store": "Rotating host...",
                            "url": "Selecting next target...",
                            "status": "active",
                            "updated_at": time.strftime("%H:%M:%S"),
                        }
        finally:
            if hasattr(session, "close"):
                try:
                    session.close()
                except Exception:
                    pass

    def run_continuous_loop(
        self,
        max_iterations: Optional[int] = None,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
    ):
        """
        Main multi-host concurrent crawl loop.
        Spawns concurrent worker threads across distinct hosts with per-host cadence.
        """
        self.is_running = True
        self.stop_requested.clear()
        self.stats["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.log(f"Starting Continuous Stealth Crawler daemon (Profile: {self.speed_profile.upper()} | Concurrency: {self.concurrency} hosts)...")

        # Ensure seed URLs exist in frontier
        seed_frontier_from_stores()

        max_items_per_worker = None
        if max_iterations is not None:
            active_stores = get_active_stores()
            num_stores = len(active_stores) if active_stores else 1
            max_items_per_worker = max(1, math.ceil((max_iterations * num_stores) / self.concurrency))

        threads = []
        try:
            for w_id in range(self.concurrency):
                t = threading.Thread(
                    target=self._worker_loop,
                    args=(w_id, max_items_per_worker),
                    name=f"HostWorker-{w_id}",
                    daemon=True
                )
                threads.append(t)
                t.start()

            # Supervisor loop
            while not self.stop_requested.is_set():
                alive = [t for t in threads if t.is_alive()]
                if not alive:
                    break
                time.sleep(0.5)

            # Await wind-down if stopped
            for t in threads:
                t.join(timeout=3.0)

        finally:
            self.is_running = False
            self.current_task_info = {
                "current_store": "Idle / Stopped",
                "current_url": "Daemon idle.",
                "status": "idle",
                "last_active_at": time.strftime("%H:%M:%S"),
            }
            self.log("Continuous Stealth Crawler daemon stopped.")

    def _fetch_via_browser(self, target_url: str, store_name: str) -> Tuple[int, str]:
        """Offscreen stealth Playwright browser fetch with humanized physics."""
        async def _run():
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=False,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--window-position=-2000,-2000",
                        "--window-size=1200,800",
                        "--no-sandbox"
                    ]
                )
                page = await browser.new_page()
                await PlaywrightHumanizer.apply_stealth_scripts(page)
                resp = await page.goto(target_url, timeout=25000)
                await PlaywrightHumanizer.human_scroll(page, steps=2)
                await asyncio.sleep(2.5)
                html = await page.content()
                status = resp.status if resp else 200
                await browser.close()
                return status, html

        try:
            return asyncio.run(_run())
        except Exception as e:
            return 500, ""

    def _process_sitemap_content(self, store_id: int, sitemap_url: str, text: str):
        """Parse XML sitemap, extracting nested sitemaps and product URLs."""
        try:
            clean_xml = re.sub(r'\s*xmlns(:[a-zA-Z0-9_]+)?=[\x27\x22][^\x27\x22]*[\x27\x22]', '', text)
            root = ET.fromstring(clean_xml)

            # Sub-sitemaps (prioritize dedicated product sitemaps)
            sub_sitemaps = [loc.text.strip() for loc in root.findall(".//sitemap/loc") if loc.text]
            if sub_sitemaps:
                prod_sitemaps = [sm for sm in sub_sitemaps if "product" in sm.lower()]
                other_sitemaps = [sm for sm in sub_sitemaps if "product" not in sm.lower()]
                if prod_sitemaps:
                    ingest_frontier_urls(store_id, prod_sitemaps, url_type="sitemap", priority=1, depth=1)
                if other_sitemaps:
                    ingest_frontier_urls(store_id, other_sitemaps, url_type="sitemap", priority=25, depth=1)

            # Product and Category URLs
            prod_urls = [loc.text.strip() for loc in root.findall(".//url/loc") if loc.text]
            if prod_urls:
                candidate_products = []
                candidate_categories = []
                for u in prod_urls:
                    prio = get_url_product_priority(u)
                    if prio <= 3:
                        candidate_products.append(u)
                    elif prio == 10:
                        candidate_categories.append(u)

                if candidate_products:
                    ingest_frontier_urls(store_id, candidate_products, url_type="product", priority=0)
                if candidate_categories:
                    ingest_frontier_urls(store_id, candidate_categories, url_type="category", priority=10)

        except Exception as e:
            # Fallback regex extraction
            locs = re.findall(r'<loc>([^<]+)</loc>', text)
            if locs:
                candidate_products = []
                candidate_categories = []
                for u in locs:
                    clean_u = u.strip()
                    prio = get_url_product_priority(clean_u)
                    if prio <= 3:
                        candidate_products.append(clean_u)
                    elif prio == 10:
                        candidate_categories.append(clean_u)

                if candidate_products:
                    ingest_frontier_urls(store_id, candidate_products, url_type="product", priority=0)
                if candidate_categories:
                    ingest_frontier_urls(store_id, candidate_categories, url_type="category", priority=10)

    def _extract_links_from_category(self, store: Dict[str, Any], page_url: str, html: str) -> List[str]:
        """Extract internal product links from category or listing pages."""
        base_domain = urlparse(store["base_url"]).netloc.lower().replace("www.", "")
        found_links = re.findall(r'href=[\'"]([^\'"]+)[\'"]', html)
        candidates = []

        for link in found_links:
            clean = link.split("#")[0].strip()
            if not clean:
                continue
            full_url = urljoin(page_url, clean)
            parsed = urlparse(full_url)
            if parsed.netloc.lower().replace("www.", "") != base_domain:
                continue
            if full_url.rstrip("/") == page_url.split("#")[0].rstrip("/"):
                continue
            if get_url_product_priority(full_url) <= 3:
                candidates.append(full_url)

        return list(dict.fromkeys(candidates))

    def _is_strictly_product_page(self, url: str, html: str) -> bool:
        """Determines if a page is definitively a product page rather than a listing."""
        if get_url_product_priority(url) == 0:
            return True
        if "schema.org" in html and ('"Product"' in html or '"IndividualProduct"' in html):
            return True
        return False


# Singleton daemon manager for application-wide control
_daemon_instance: Optional[ContinuousStealthCrawler] = None
_daemon_thread: Optional[threading.Thread] = None


def get_crawler_daemon(speed_profile: str = "normal", concurrency: int = 6) -> ContinuousStealthCrawler:
    global _daemon_instance
    if _daemon_instance is None:
        _daemon_instance = ContinuousStealthCrawler(speed_profile=speed_profile, concurrency=concurrency)
    return _daemon_instance


def start_crawler_daemon(speed_profile: str = "normal", concurrency: int = 6) -> ContinuousStealthCrawler:
    """Start the continuous crawler in a persistent background daemon thread."""
    global _daemon_instance, _daemon_thread
    daemon = get_crawler_daemon(speed_profile=speed_profile, concurrency=concurrency)
    daemon.speed_profile = speed_profile
    daemon.concurrency = max(1, min(concurrency, 80))

    if _daemon_thread is not None and _daemon_thread.is_alive():
        return daemon

    daemon.stop_requested.clear()
    _daemon_thread = threading.Thread(
        target=daemon.run_continuous_loop,
        name="ContinuousStealthCrawlerThread",
        daemon=True
    )
    _daemon_thread.start()
    return daemon


def stop_crawler_daemon():
    """Stop the continuous crawler background daemon."""
    global _daemon_instance
    if _daemon_instance:
        _daemon_instance.stop()


def is_crawler_daemon_running() -> bool:
    global _daemon_thread, _daemon_instance
    return bool(_daemon_thread and _daemon_thread.is_alive() and _daemon_instance and _daemon_instance.is_running)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("=================================================================")
    print("STARTING CONTINUOUS STEALTH CRAWLER DAEMON (STANDALONE CLI MODE)")
    print("=================================================================")
    crawler = ContinuousStealthCrawler(speed_profile="normal")
    try:
        crawler.run_continuous_loop()
    except KeyboardInterrupt:
        crawler.stop()
        print("\nExiting continuous crawler cleanly.")
