import os
import re
import sys
import time
import asyncio
import logging
import threading
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
    Production-grade continuous crawler daemon.
    Features:
    1. Interleaved Multi-Store Round-Robin (host spreading).
    2. Persistent Resumable Frontier Queue.
    3. Log-Normal Jitter & Burst-and-Read Cadence.
    4. Per-Store Circuit Breakers with Exponential Backoff.
    5. Adaptive TLS Impersonation & Playwright Stealth Escalation.
    """

    def __init__(self, speed_profile: str = "normal"):
        self.speed_profile = speed_profile
        self.cadence = AntiBotCadence()
        self.circuit_breaker = StoreCircuitBreaker()
        self.stop_requested = threading.Event()
        self.is_running = False
        self.current_task_info: Dict[str, Any] = {
            "current_store": None,
            "current_url": None,
            "status": "idle",
            "last_active_at": None,
        }
        self.stats = {
            "total_requests": 0,
            "products_indexed": 0,
            "urls_discovered": 0,
            "errors": 0,
            "rate_limits_hit": 0,
            "started_at": None,
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

    def get_status(self) -> Dict[str, Any]:
        frontier_metrics = get_frontier_metrics()
        active_stores = get_active_stores()
        cooldown_stores = [
            s["name"] for s in active_stores if not self.circuit_breaker.is_eligible(s["id"])
        ]
        return {
            "is_running": self.is_running,
            "speed_profile": self.speed_profile,
            "current_store": self.current_task_info.get("current_store"),
            "current_url": self.current_task_info.get("current_url"),
            "stats": dict(self.stats),
            "frontier": frontier_metrics,
            "cooldown_stores": cooldown_stores,
            "recent_logs": list(self.recent_logs),
        }

    def stop(self):
        """Signal the crawler to gracefully stop."""
        self.log("Stop requested. Waiting for in-flight requests to conclude...")
        self.stop_requested.set()

    def run_continuous_loop(
        self,
        max_iterations: Optional[int] = None,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
    ):
        """
        Main continuous round-robin crawl loop.
        Rotates across stores so no host is ever requested consecutively.
        """
        self.is_running = True
        self.stop_requested.clear()
        self.stats["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.log(f"Starting Continuous Stealth Crawler daemon (Profile: {self.speed_profile.upper()})...")

        # Ensure seed URLs exist in frontier
        seed_frontier_from_stores()

        iteration = 0
        session, session_type = create_http_session(timeout=12.0)

        try:
            while not self.stop_requested.is_set():
                active_stores = get_active_stores()
                if not active_stores:
                    self.log("No active stores configured in database. Sleeping 10s...")
                    time.sleep(10)
                    continue

                processed_any_store = False

                for store in active_stores:
                    if self.stop_requested.is_set():
                        break

                    store_id = store["id"]
                    store_name = store["name"]

                    # 1. Check Circuit Breaker for this host
                    if not self.circuit_breaker.is_eligible(store_id):
                        rem_sec = self.circuit_breaker.get_remaining_cooldown(store_id)
                        # Silent pass or debug log
                        continue

                    # 2. Pop next eligible URL from frontier for this store
                    frontier_item = pop_next_frontier_item(store_id)
                    if not frontier_item:
                        # If frontier is empty for this store, seed from sitemap or base URL
                        seed_url = store.get("sitemap_url") or store.get("base_url")
                        if seed_url:
                            url_type = "sitemap" if (store.get("sitemap_url") and ".xml" in store.get("sitemap_url")) else "category"
                            ingest_frontier_urls(store_id, [seed_url], url_type=url_type, priority=20, depth=0)
                            frontier_item = pop_next_frontier_item(store_id)

                    if not frontier_item:
                        # Nothing pending for this store right now
                        continue

                    processed_any_store = True
                    target_url = frontier_item["url"]
                    frontier_id = frontier_item["id"]
                    url_type = frontier_item.get("url_type", "product")
                    requires_browser = frontier_item.get("requires_browser", False) or (self.circuit_breaker.get_recommended_mode(store_id) == "browser")

                    self.current_task_info = {
                        "current_store": store_name,
                        "current_url": target_url,
                        "status": "crawling",
                        "last_active_at": time.strftime("%H:%M:%S"),
                    }
                    self.stats["total_requests"] += 1

                    # 3. Apply Persona and Request Cadence
                    persona = PersonaManager.get_persona_for_store(store_id)
                    headers = persona.get_headers(target_url)

                    # 4. Fetch Page Content
                    try:
                        if requires_browser:
                            status_code, html_content = self._fetch_via_browser(target_url, store_name)
                        else:
                            status_code, html_content, _ = fetch_response_content(
                                session, target_url, headers, timeout=12.0
                            )

                        # Check for Bot Challenge or WAF Block
                        if status_code == 429:
                            self.stats["rate_limits_hit"] += 1
                            self.circuit_breaker.record_failure(store_id, 429)
                            update_frontier_item_result(frontier_id, "failed", http_status=429, backoff_seconds=300)
                            self.log(f"⚠️ {store_name} returned 429 (Rate Limited). Enforcing backoff cooldown.")
                            continue

                        if status_code == 403 or (html_content and ("Just a moment..." in html_content or "Attention Required!" in html_content)):
                            self.log(f"🛡️ {store_name} triggered Cloudflare Challenge. Escalating store to browser mode.")
                            self.circuit_breaker.record_failure(store_id, 403, "Cloudflare Challenge")
                            update_frontier_item_result(frontier_id, "failed", http_status=403, backoff_seconds=60)
                            continue

                        if not html_content or status_code not in [200, 201, 204]:
                            update_frontier_item_result(frontier_id, "failed", http_status=status_code or 500)
                            self.stats["errors"] += 1
                            continue

                        # 5. Success - Process by URL Type
                        self.circuit_breaker.record_success(store_id)

                        if url_type == "sitemap" or target_url.endswith(".xml") or ".xml" in target_url:
                            self._process_sitemap_content(store_id, target_url, html_content)
                            update_frontier_item_result(frontier_id, "completed", http_status=status_code)
                            self.log(f"📑 {store_name} parsed sitemap: {target_url[:60]}")

                        elif url_type == "category":
                            # Extract discovered candidate links from category page
                            discovered = self._extract_links_from_category(store, target_url, html_content)
                            new_count = ingest_frontier_urls(store_id, discovered, url_type="product", priority=0)
                            update_frontier_item_result(frontier_id, "completed", http_status=status_code)
                            self.stats["urls_discovered"] += new_count
                            self.log(f"📂 {store_name} category parsed: discovered {new_count} new product links.")

                        else:
                            # Product Page Extraction
                            extracted = UniversalProductExtractor.extract_from_html(html_content, target_url)
                            if extracted.get("name") and extracted.get("price_bdt"):
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
                                self.stats["products_indexed"] += 1
                                update_store_crawl_status(store_id, "crawling", total_found_delta=1)
                                update_frontier_item_result(frontier_id, "completed", http_status=status_code)
                                self.log(f"✅ {store_name} indexed: {extracted['name'][:40]} (BDT {extracted['price_bdt']:,.0f})")
                            else:
                                # Fallback: check if this was a listing or category-like page with links
                                discovered = self._extract_links_from_category(store, target_url, html_content)
                                if discovered:
                                    new_count = ingest_frontier_urls(store_id, discovered, url_type="product", priority=0)
                                    self.stats["urls_discovered"] += new_count
                                    self.log(f"📂 {store_name} listing parsed: discovered {new_count} new links.")
                                update_frontier_item_result(frontier_id, "completed", http_status=status_code)

                    except Exception as e:
                        self.stats["errors"] += 1
                        update_frontier_item_result(frontier_id, "failed", error=str(e), backoff_seconds=120)
                        self.log(f"❌ Error crawling {store_name} ({target_url[:50]}): {e}")

                    # 6. Apply Log-Normal Delay Before Next Host Request
                    delay = self.cadence.calculate_delay(store_id=store_id, speed_profile=self.speed_profile)
                    time.sleep(delay)

                iteration += 1
                if max_iterations and iteration >= max_iterations:
                    self.log(f"Reached max iterations limit ({max_iterations}). Exiting loop.")
                    break

                # If no store had pending eligible items, rest briefly
                if not processed_any_store:
                    self.current_task_info = {
                        "current_store": "Idle / Waiting",
                        "current_url": "All queued URLs currently processed or in cooldown. Standing by...",
                        "status": "idle",
                        "last_active_at": time.strftime("%H:%M:%S")
                    }
                    time.sleep(3.0)

        finally:
            self.is_running = False
            self.current_task_info = {"current_store": "Idle / Stopped", "current_url": "Daemon idle.", "status": "idle"}
            if hasattr(session, "close"):
                session.close()
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

            # Sub-sitemaps
            sub_sitemaps = [loc.text.strip() for loc in root.findall(".//sitemap/loc") if loc.text]
            if sub_sitemaps:
                ingest_frontier_urls(store_id, sub_sitemaps, url_type="sitemap", priority=5, depth=1)

            # Product URLs
            prod_urls = [loc.text.strip() for loc in root.findall(".//url/loc") if loc.text]
            if prod_urls:
                # Filter through product heuristics
                candidate_products = []
                candidate_categories = []
                for u in prod_urls:
                    prio = get_url_product_priority(u)
                    if prio <= 3:
                        candidate_products.append(u)
                    elif not IGNORED_REGEX.search(u):
                        candidate_categories.append(u)

                if candidate_products:
                    ingest_frontier_urls(store_id, candidate_products, url_type="product", priority=0)
                if candidate_categories:
                    ingest_frontier_urls(store_id, candidate_categories, url_type="category", priority=10)

        except Exception as e:
            # Fallback regex extraction
            locs = re.findall(r'<loc>([^<]+)</loc>', text)
            if locs:
                clean_locs = [u.strip() for u in locs if not IGNORED_REGEX.search(u)]
                ingest_frontier_urls(store_id, clean_locs, url_type="product", priority=5)

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
            if get_url_product_priority(full_url) <= 2:
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


def get_crawler_daemon(speed_profile: str = "normal") -> ContinuousStealthCrawler:
    global _daemon_instance
    if _daemon_instance is None:
        _daemon_instance = ContinuousStealthCrawler(speed_profile=speed_profile)
    return _daemon_instance


def start_crawler_daemon(speed_profile: str = "normal") -> ContinuousStealthCrawler:
    """Start the continuous crawler in a persistent background daemon thread."""
    global _daemon_instance, _daemon_thread
    daemon = get_crawler_daemon(speed_profile=speed_profile)
    daemon.speed_profile = speed_profile

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
