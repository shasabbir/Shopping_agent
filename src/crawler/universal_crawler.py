import re
import time
import gzip
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable, Tuple
from urllib.parse import urlparse, urljoin
import httpx
from src.database import (
    get_all_stores,
    get_active_stores,
    update_store_crawl_status,
    upsert_crawled_offer,
)
from src.crawler.universal_extractor import UniversalProductExtractor

# Common product URL path patterns across e-commerce platforms
PRODUCT_URL_PATTERNS = [
    r"/product-detail/",
    r"/product_detail/",
    r"/product/",
    r"/products/",
    r"/item/",
    r"/items/",
    r"/p/",
    r"/details/",
    r"/buy/",
    r"/book/\d+",
    r"-p-\d+",
    r"-p-[a-zA-Z0-9_-]+",
    r"route=product/product",
    r"product_id=\d+",
    r"-i\d+-s\d+",
    r"-\d{5,}\b",
    r"\.html?$",
]

# Asset extensions and media files
ASSET_PATTERNS = [
    r"\.(?:webp|jpg|jpeg|png|gif|svg|css|js|pdf|ico|woff|woff2|ttf|mp4|webm)(?:\?.*)?$",
    r"/image/cache/", r"/images/cache/", r"/wp-content/uploads/",
]
ASSET_REGEX = re.compile("|".join(ASSET_PATTERNS), re.IGNORECASE)

# Utility / Account non-product pages
UTILITY_PATTERNS = [
    r"/(?:account|cart|checkout|login|register|wishlist|compare|review|question|faq|terms|privacy|about|contact|help|delivery|policy|track-order|store-locator)(?:/|\?|$)",
    r"/(?:my-account|customer-service|refund-policy|terms-conditions|contact-us|help-request|reward-points|spin-the-wheel|service-request|book-a-store-visit)\b",
    r"/(?:privacy-policy|terms-and-conditions|about-us|cookie-policy|affiliate|careers?)\b",
    r"/details/(?:privacy|about|terms|cookie|help|faq)\b",
    r"/(?:daraz-affiliate-program|daraz-exclusive-products|daraz-cares)\b",
]
UTILITY_REGEX = re.compile("|".join(UTILITY_PATTERNS), re.IGNORECASE)

# Category / Brand / Listing paths
CATEGORY_PATTERNS = [
    r"/(?:category|categories|brand|brands|tag|tags|collections?|collection|manufacturer|all-products|new-arrival|deals|search|catalog)(?:/|\?|$)",
    r"daraz\.com\.bd/[^/?]+-\d{4,}/?$",
]
CATEGORY_LISTING_REGEX = re.compile("|".join(CATEGORY_PATTERNS), re.IGNORECASE)

DARAZ_PRODUCT_REGEX = re.compile(
    r"daraz\.com\.bd/(?:products/[^/]+-)?i\d+-s\d+\.html?",
    re.IGNORECASE
)

SPECIFIC_PRODUCT_REGEX = re.compile(
    r"/product-detail/|/product_detail/|/buy/|/item/|/book/\d+|"
    r"route=product/product|-p-\d+|-p-[a-zA-Z0-9_-]+|-i\d+-s\d+\.html?|"
    r"/products/[^/]+-i\d+|-p\d{4,}\.html?",
    re.IGNORECASE
)

PRODUCT_URL_REGEX = re.compile("|".join(PRODUCT_URL_PATTERNS), re.IGNORECASE)

# Ignored non-product links (combined)
IGNORED_PATTERNS = ASSET_PATTERNS + UTILITY_PATTERNS
IGNORED_REGEX = re.compile("|".join(IGNORED_PATTERNS), re.IGNORECASE)


def get_url_product_priority(url: str) -> int:
    r"""
    Priority ranking for URL candidates:
    99: Ignored assets / media files / account / utility links
    10: Category, brand, search, or listing pages
    0:  Explicit high-confidence product detail patterns (e.g. /product-detail/, route=product/product, -i-s.html, -p-sku)
    1:  Explicit product path (/product/, /products/) with 2+ hyphens in slug
    2:  Explicit product path (/product/, /products/)
    3:  Descriptive root slug with 2+ hyphens (e.g. Star Tech, TechLand, Potaka, Shwapno)
    """
    if ASSET_REGEX.search(url) or UTILITY_REGEX.search(url):
        return 99

    if DARAZ_PRODUCT_REGEX.search(url):
        return 0

    if CATEGORY_LISTING_REGEX.search(url):
        return 10

    if SPECIFIC_PRODUCT_REGEX.search(url):
        return 0

    p = urlparse(url)
    clean_path = p.path.rstrip("/")
    if not clean_path:
        return 10

    # Explicit product path
    if re.search(r"^/products?/", clean_path, re.IGNORECASE):
        return 1 if clean_path.count("-") >= 2 else 2

    # Root-level multi-hyphen descriptive slug (Star Tech, TechLand, Potaka, Shwapno)
    if clean_path.count("/") == 1 and clean_path.count("-") >= 2:
        return 3

    return 10


def create_http_session(timeout: float = 8.0) -> Tuple[Any, str]:
    """
    Factory creating a browser-impersonating HTTP session.
    Prioritizes curl_cffi (Chrome JA3/HTTP2 fingerprint) to bypass Cloudflare and WAFs.
    Falls back gracefully to httpx.Client if curl_cffi is unavailable.
    """
    try:
        from curl_cffi import requests as cffi_requests
        session = cffi_requests.Session(impersonate="chrome124")
        return session, "curl_cffi"
    except Exception:
        client = httpx.Client(follow_redirects=True, timeout=timeout)
        return client, "httpx"


def fetch_response_content(client: Any, url: str, headers: dict, timeout: float) -> Tuple[Optional[int], str, bytes]:
    """Uniform HTTP fetch supporting automatic gzip decompression and mock objects."""
    try:
        resp = client.get(url, headers=headers, timeout=timeout)
        status = getattr(resp, "status_code", 200)
        content = getattr(resp, "content", b"")

        # Auto-decompress if gzip
        if content and content.startswith(b"\x1f\x8b"):
            try:
                text = gzip.decompress(content).decode("utf-8", errors="ignore")
            except Exception:
                text = getattr(resp, "text", "")
        else:
            text = getattr(resp, "text", "")

        return status, text, content
    except Exception:
        return None, "", b""


class UniversalStoreCrawler:
    """
    Sequential crawler engine that processes 20-30 stores sequentially
    without any store-specific hardcoded scrapers.
    Employs hybrid architecture: fast TLS-impersonating HTTP for 95% of stores,
    with an offscreen Playwright fallback for Cloudflare Turnstile challenges.
    """

    def __init__(
        self,
        timeout: float = 8.0,
        max_products_per_store: int = 15,
        concurrency: int = 3,
        user_agent: Optional[str] = None
    ):
        self.timeout = timeout
        self.max_products_per_store = max_products_per_store
        self.concurrency = concurrency
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,bn;q=0.8",
        }

    def _is_probable_product_url(self, url: str) -> bool:
        """Universal heuristic checking if a URL is an e-commerce product page."""
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        full_path_and_query = parsed.path + ("?" + parsed.query if parsed.query else "")
        if not path and not parsed.query:
            return False
        if IGNORED_REGEX.search(url):
            return False

        # Ignore directory category URLs ending in '/' unless matching explicit product pattern
        if parsed.path.endswith("/") and not PRODUCT_URL_REGEX.search(full_path_and_query):
            return False

        # Pattern 1: Explicit product subpath, book ID, query param, or extension
        if PRODUCT_URL_REGEX.search(full_path_and_query):
            return True

        # Pattern 2: Multi-hyphen descriptive slug (common in OpenCart/WooCommerce/Custom BD stores)
        # e.g. /deepcool-macube-110-bk-mini-tower-case
        if path.count("-") >= 2 and len(path.split("/")) <= 2:
            return True

        return False

    def discover_product_urls_from_sitemap(
        self,
        client: Any,
        sitemap_url: str,
        limit: int = 30,
        depth: int = 0
    ) -> List[str]:
        """Fetch XML sitemap and extract product URLs, recursing through sitemapindex files."""
        if depth > 2:
            return []
        product_urls: List[str] = []
        try:
            status, text, _ = fetch_response_content(client, sitemap_url, self.headers, self.timeout)
            if status == 200 and text:
                # Strip XML namespaces for uniform parsing
                clean_xml = re.sub(r'\sxmlns="[^"]+"', '', text, count=1)
                clean_xml = re.sub(r"\sxmlns='[^']+'", '', clean_xml, count=1)

                try:
                    root = ET.fromstring(clean_xml)

                    # Check if it is a sitemapindex pointing to sub-sitemaps
                    sub_sitemaps = [loc.text.strip() for loc in root.findall(".//sitemap/loc") if loc.text]
                    if sub_sitemaps:
                        # Prioritize product-focused sub-sitemaps
                        chosen_subs = sorted(sub_sitemaps, key=lambda s: 0 if "product" in s.lower() else 1)
                        for sub in chosen_subs[:3]:
                            sub_found = self.discover_product_urls_from_sitemap(
                                client, sub, limit=limit - len(product_urls), depth=depth + 1
                            )
                            for u in sub_found:
                                if u not in product_urls:
                                    product_urls.append(u)
                                    if len(product_urls) >= limit:
                                        return product_urls
                        return product_urls

                    # Extract individual URLs
                    loc_urls = [loc.text.strip() for loc in root.findall(".//url/loc") if loc.text]
                    # Prioritize explicit product URLs over generic slugs
                    loc_urls.sort(key=get_url_product_priority)
                    for url in loc_urls:
                        if self._is_probable_product_url(url):
                            if url not in product_urls:
                                product_urls.append(url)
                                if len(product_urls) >= limit:
                                    break

                    # Category hopping: If no direct product URLs were found, treat locs as category listing pages
                    if not product_urls and loc_urls:
                        for cat_loc in loc_urls[:3]:
                            cat_found = self.discover_product_urls_from_homepage(client, cat_loc, limit=limit - len(product_urls))
                            for cu in cat_found:
                                if cu not in product_urls:
                                    product_urls.append(cu)
                                    if len(product_urls) >= limit:
                                        break
                except ET.ParseError:
                    # Regex fallback for non-strict or slightly malformed XML
                    locs = re.findall(r'<loc>([^<]+)</loc>', text)
                    locs.sort(key=get_url_product_priority)
                    for l in locs:
                        l = l.strip()
                        if self._is_probable_product_url(l):
                            if l not in product_urls:
                                product_urls.append(l)
                                if len(product_urls) >= limit:
                                    break
                    if not product_urls and locs:
                        for cat_loc in locs[:3]:
                            cat_found = self.discover_product_urls_from_homepage(client, cat_loc.strip(), limit=limit - len(product_urls))
                            for cu in cat_found:
                                if cu not in product_urls:
                                    product_urls.append(cu)
                                    if len(product_urls) >= limit:
                                        break
        except Exception:
            pass

        return product_urls

    def discover_sitemaps_from_robots(self, client: Any, base_url: str) -> List[str]:
        """Parse robots.txt to discover declared Sitemap directives."""
        sitemaps = []
        try:
            robots_url = urljoin(base_url, "/robots.txt")
            status, text, _ = fetch_response_content(client, robots_url, self.headers, self.timeout)
            if status == 200 and text:
                found = re.findall(r'Sitemap:\s*(\S+)', text, re.IGNORECASE)
                for s in found:
                    s_clean = s.strip()
                    if s_clean not in sitemaps:
                        sitemaps.append(s_clean)
        except Exception:
            pass
        return sitemaps

    def discover_product_urls_from_homepage(
        self,
        client: Any,
        base_url: str,
        limit: int = 30
    ) -> List[str]:
        """Crawl homepage/catalog HTML to extract internal product links."""
        product_urls: List[str] = []
        try:
            status, text, _ = fetch_response_content(client, base_url, self.headers, self.timeout)
            if status == 200 and text:
                domain = urlparse(base_url).netloc.lower().replace("www.", "")
                found_links = re.findall(r'href=[\'"]([^\'"]+)[\'"]', text)
                full_links = [urljoin(base_url, link.strip()) for link in found_links]
                # Prioritize explicit product URLs over generic links
                full_links.sort(key=get_url_product_priority)
                for full_url in full_links:
                    clean_url = full_url.split("#")[0].strip()
                    parsed = urlparse(clean_url)
                    if parsed.netloc.lower().replace("www.", "") == domain:
                        if self._is_probable_product_url(clean_url):
                            if clean_url not in product_urls:
                                product_urls.append(clean_url)
                                if len(product_urls) >= limit:
                                    break
        except Exception:
            pass

        return product_urls

    def crawl_store_with_browser_fallback(
        self,
        base_url: str,
        limit: int = 15,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        store_name: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Offscreen Playwright browser fallback for stores guarded by Cloudflare
        Turnstile challenges or dynamic client-side SPA rendering.
        """
        async def _run_browser():
            extracted_items = []
            try:
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
                    await page.goto(base_url, timeout=25000)
                    await asyncio.sleep(4)

                    # Extract all internal candidate links
                    raw_links = await page.locator("a").evaluate_all("list => list.map(a => a.href)")
                    base_domain = urlparse(base_url).netloc.lower().replace("www.", "")
                    prod_links = []
                    seen_urls = set()

                    # Prioritize explicit product detail URLs
                    raw_links.sort(key=get_url_product_priority)

                    for link in raw_links:
                        clean_link = link.split('#')[0].strip()
                        if not clean_link or clean_link in seen_urls:
                            continue
                        parsed_link = urlparse(clean_link)
                        # Ensure link belongs to the same store domain (ignoring www. prefix)
                        if parsed_link.netloc.lower().replace("www.", "") != base_domain:
                            continue
                        # Never treat current landing/category page as a product link
                        if clean_link.rstrip('/') == base_url.split('#')[0].rstrip('/'):
                            continue

                        if self._is_probable_product_url(clean_link):
                            seen_urls.add(clean_link)
                            prod_links.append(clean_link)
                            if len(prod_links) >= limit:
                                break

                    if progress_callback:
                        try:
                            progress_callback("links_discovered", {
                                "store": store_name,
                                "count": len(prod_links),
                                "message": f"Discovered {len(prod_links)} candidate product links via dynamic browser."
                            })
                        except Exception:
                            pass

                    for u in prod_links:
                        try:
                            await page.goto(u, timeout=20000)
                            await asyncio.sleep(2)
                            html = await page.content()
                            data = UniversalProductExtractor.extract_from_html(html, u)
                            if data.get("name") and data.get("price_bdt"):
                                data["url"] = u
                                extracted_items.append(data)
                        except Exception:
                            continue

                    await browser.close()
            except Exception:
                pass
            return extracted_items

        try:
            return asyncio.run(_run_browser())
        except Exception:
            return []

    def crawl_single_store(
        self,
        store: Dict[str, Any],
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Crawl a single store sequentially and upsert discovered products.
        """
        store_id = store["id"]
        store_name = store["name"]
        base_url = store["base_url"]
        sitemap_url = store.get("sitemap_url")

        stats = {
            "store_id": store_id,
            "store_name": store_name,
            "urls_discovered": 0,
            "products_extracted": 0,
            "offers_upserted": 0,
            "errors": 0,
            "status": "completed",
        }

        update_store_crawl_status(store_id, "crawling")
        if progress_callback:
            try:
                progress_callback("store_start", {"store": store_name, "message": f"Starting crawl of {store_name}..."})
            except Exception:
                pass

        session, session_type = create_http_session(timeout=self.timeout)

        try:
            # Check base connectivity
            base_status, base_text, _ = fetch_response_content(session, base_url, self.headers, self.timeout)

            # Check if store requires browser rendering (Cloudflare Challenge or 403)
            requires_browser = (
                base_status == 403 or
                "Just a moment..." in base_text or
                "Attention Required!" in base_text or
                "cf-browser-verification" in base_text
            )

            if requires_browser:
                if progress_callback:
                    try:
                        progress_callback("browser_fallback", {
                            "store": store_name,
                            "message": f"{store_name} requires dynamic browser rendering. Launching offscreen browser..."
                        })
                    except Exception:
                        pass

                browser_target = sitemap_url if (sitemap_url and not sitemap_url.endswith(".xml")) else base_url
                browser_items = self.crawl_store_with_browser_fallback(
                    browser_target,
                    limit=self.max_products_per_store,
                    progress_callback=progress_callback,
                    store_name=store_name
                )
                stats["urls_discovered"] = len(browser_items)

                for item in browser_items:
                    try:
                        upsert_crawled_offer(
                            store_id=store_id,
                            store_product_title=item["name"],
                            product_url=item["url"],
                            price_bdt=item["price_bdt"],
                            category=item.get("category", "general"),
                            brand=item.get("brand"),
                            regular_price_bdt=item.get("regular_price_bdt"),
                            in_stock=item.get("in_stock", True),
                            warranty=item.get("warranty"),
                            specs=item.get("specs"),
                            image_url=item.get("image_url"),
                            model_number=item.get("model_number"),
                        )
                        stats["products_extracted"] += 1
                        stats["offers_upserted"] += 1

                        if progress_callback:
                            try:
                                progress_callback("product_saved", {
                                    "store": store_name,
                                    "product": item["name"],
                                    "price": item["price_bdt"],
                                    "url": item["url"],
                                    "message": f"Saved: {item['name']} (BDT {item['price_bdt']:,.0f})"
                                })
                            except Exception:
                                pass
                    except Exception:
                        stats["errors"] += 1

            else:
                # Fast HTTP-based crawling
                discovered_urls: List[str] = []

                # 1. Try Sitemap URL
                if sitemap_url:
                    discovered_urls = self.discover_product_urls_from_sitemap(
                        session, sitemap_url, limit=self.max_products_per_store
                    )

                # 2. Try default sitemap paths
                if not discovered_urls:
                    for default_path in ["/sitemap.xml", "/sitemap_products.xml"]:
                        test_sm = urljoin(base_url, default_path)
                        discovered_urls = self.discover_product_urls_from_sitemap(
                            session, test_sm, limit=self.max_products_per_store
                        )
                        if discovered_urls:
                            break

                # 3. Try robots.txt sitemaps
                if not discovered_urls:
                    rb_sitemaps = self.discover_sitemaps_from_robots(session, base_url)
                    for rb_sm in rb_sitemaps:
                        discovered_urls = self.discover_product_urls_from_sitemap(
                            session, rb_sm, limit=self.max_products_per_store
                        )
                        if discovered_urls:
                            break

                # 4. Fallback: Parse homepage links
                if not discovered_urls:
                    discovered_urls = self.discover_product_urls_from_homepage(
                        session, base_url, limit=self.max_products_per_store
                    )

                stats["urls_discovered"] = len(discovered_urls)
                if progress_callback:
                    try:
                        progress_callback("links_discovered", {
                            "store": store_name,
                            "count": len(discovered_urls),
                            "message": f"Discovered {len(discovered_urls)} candidate product links for {store_name}."
                        })
                    except Exception:
                        pass

                # Extract product data from discovered URLs
                for url in discovered_urls:
                    try:
                        status, html, _ = fetch_response_content(session, url, self.headers, self.timeout)
                        if status == 200 and html:
                            extracted = UniversalProductExtractor.extract_from_html(html, url)
                            if extracted.get("name") and extracted.get("price_bdt"):
                                stats["products_extracted"] += 1

                                # Upsert to database
                                upsert_crawled_offer(
                                    store_id=store_id,
                                    store_product_title=extracted["name"],
                                    product_url=url,
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
                                stats["offers_upserted"] += 1

                                if progress_callback:
                                    try:
                                        progress_callback("product_saved", {
                                            "store": store_name,
                                            "product": extracted["name"],
                                            "price": extracted["price_bdt"],
                                            "url": url,
                                            "message": f"Saved: {extracted['name']} (BDT {extracted['price_bdt']:,.0f})"
                                        })
                                    except Exception:
                                        pass

                        time.sleep(0.2)

                    except Exception:
                        stats["errors"] += 1

                # If HTTP yielded 0 products (e.g. pure SPAs or heavily dynamic sites), try browser fallback
                if stats["offers_upserted"] == 0:
                    if progress_callback:
                        try:
                            progress_callback("browser_fallback", {
                                "store": store_name,
                                "message": f"{store_name} yielded 0 products via HTTP. Attempting dynamic browser fallback..."
                            })
                        except Exception:
                            pass

                    browser_target = sitemap_url if (sitemap_url and not sitemap_url.endswith(".xml")) else base_url
                    browser_items = self.crawl_store_with_browser_fallback(
                        browser_target,
                        limit=self.max_products_per_store,
                        progress_callback=progress_callback,
                        store_name=store_name
                    )
                    stats["urls_discovered"] = max(stats["urls_discovered"], len(browser_items))

                    for item in browser_items:
                        try:
                            upsert_crawled_offer(
                                store_id=store_id,
                                store_product_title=item["name"],
                                product_url=item["url"],
                                price_bdt=item["price_bdt"],
                                category=item.get("category", "general"),
                                brand=item.get("brand"),
                                regular_price_bdt=item.get("regular_price_bdt"),
                                in_stock=item.get("in_stock", True),
                                warranty=item.get("warranty"),
                                specs=item.get("specs"),
                                image_url=item.get("image_url"),
                                model_number=item.get("model_number"),
                            )
                            stats["products_extracted"] += 1
                            stats["offers_upserted"] += 1

                            if progress_callback:
                                try:
                                    progress_callback("product_saved", {
                                        "store": store_name,
                                        "product": item["name"],
                                        "price": item["price_bdt"],
                                        "url": item["url"],
                                        "message": f"Saved: {item['name']} (BDT {item['price_bdt']:,.0f})"
                                    })
                                except Exception:
                                    pass
                        except Exception:
                            stats["errors"] += 1

        finally:
            if hasattr(session, "close"):
                session.close()

        update_store_crawl_status(store_id, "completed", total_found_delta=stats["offers_upserted"])
        if progress_callback:
            try:
                progress_callback("store_end", {
                    "store": store_name,
                    "stats": stats,
                    "message": f"Finished {store_name}: {stats['offers_upserted']} products indexed."
                })
            except Exception:
                pass

        return stats

    def crawl_all_stores_sequentially(
        self,
        stores: Optional[List[Dict[str, Any]]] = None,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Sequentially crawl all active stores one by one.
        Updates database and streams progress events.
        """
        target_stores = stores if stores is not None else get_active_stores()
        total_stores = len(target_stores)
        all_results = []

        if progress_callback:
            try:
                progress_callback("batch_start", {
                    "total_stores": total_stores,
                    "message": f"Starting sequential crawl across {total_stores} stores..."
                })
            except Exception:
                pass

        for idx, store in enumerate(target_stores):
            if progress_callback:
                try:
                    progress_callback("store_progress", {
                        "current_index": idx + 1,
                        "total_stores": total_stores,
                        "store": store["name"],
                        "message": f"[{idx+1}/{total_stores}] Crawling {store['name']}..."
                    })
                except Exception:
                    pass

            try:
                res = self.crawl_single_store(store, progress_callback=progress_callback)
                all_results.append(res)
            except Exception as e:
                update_store_crawl_status(store["id"], "error")
                all_results.append({
                    "store_id": store["id"],
                    "store_name": store["name"],
                    "status": "error",
                    "error": str(e),
                })

        if progress_callback:
            try:
                progress_callback("batch_end", {
                    "total_stores": total_stores,
                    "results": all_results,
                    "message": f"Completed sequential crawl of {total_stores} stores!"
                })
            except Exception:
                pass

        return all_results
