import re
import time
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable
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
    r"/product/",
    r"/products/",
    r"/item/",
    r"/items/",
    r"/p/",
    r"/details/",
    r"/buy/",
    r"-p-\d+",
    r"\.html?$",
]

PRODUCT_URL_REGEX = re.compile("|".join(PRODUCT_URL_PATTERNS), re.IGNORECASE)

# Ignored non-product links
IGNORED_PATTERNS = [
    r"/cart", r"/checkout", r"/account", r"/login", r"/register",
    r"/privacy", r"/terms", r"/about", r"/contact", r"/blog",
    r"/faq", r"/returns", r"/tag/", r"/category/", r"/collections?/",
    r"/brand/", r"/search", r"/feed", r"/information/", r"/delivery",
    r"/branches", r"/locations", r"/policy", r"/manufacturer",
    r"\.css", r"\.js", r"\.jpg", r"\.png", r"\.webp"
]
IGNORED_REGEX = re.compile("|".join(IGNORED_PATTERNS), re.IGNORECASE)


class UniversalStoreCrawler:
    """
    Sequential crawler engine that processes 20-30 stores sequentially
    without any store-specific hardcoded scrapers.
    """

    def __init__(
        self,
        timeout: float = 6.0,
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
            "Chrome/124.0.0.0 Safari/537.36 ShoppingAgent/2.0"
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
        if not path or IGNORED_REGEX.search(url):
            return False

        # Pattern 1: Explicit product subpath or extension
        if PRODUCT_URL_REGEX.search(url):
            return True

        # Pattern 2: Multi-hyphen descriptive slug (common in OpenCart/WooCommerce BD stores like Star Tech, Ryans)
        # e.g. /deepcool-macube-110-bk-mini-tower-case
        if path.count("-") >= 2 and len(path.split("/")) <= 2:
            return True

        return False

    def discover_product_urls_from_sitemap(self, client: httpx.Client, sitemap_url: str, limit: int = 30) -> List[str]:
        """Fetch XML sitemap and extract product URLs."""
        product_urls: List[str] = []
        try:
            resp = client.get(sitemap_url, headers=self.headers, timeout=self.timeout)
            if resp.status_code == 200 and resp.text:
                # Strip XML namespaces for uniform parsing
                clean_xml = re.sub(r'\sxmlns="[^"]+"', '', resp.text, count=1)
                clean_xml = re.sub(r"\sxmlns='[^']+'", '', clean_xml, count=1)
                root = ET.fromstring(clean_xml)

                # Check if it is a sitemapindex pointing to sub-sitemaps
                sub_sitemaps = [loc.text.strip() for loc in root.findall(".//sitemap/loc") if loc.text]
                if sub_sitemaps:
                    # Pick first product-focused sub-sitemap or first available
                    chosen = next((s for s in sub_sitemaps if "product" in s.lower()), sub_sitemaps[0])
                    return self.discover_product_urls_from_sitemap(client, chosen, limit=limit)

                # Extract individual URLs
                for loc in root.findall(".//url/loc"):
                    if not loc.text:
                        continue
                    url = loc.text.strip()
                    if self._is_probable_product_url(url):
                        product_urls.append(url)
                        if len(product_urls) >= limit:
                            break
        except Exception:
            pass

        return product_urls

    def discover_product_urls_from_homepage(self, client: httpx.Client, base_url: str, limit: int = 30) -> List[str]:
        """Crawl homepage/catalog HTML to extract internal product links."""
        product_urls: List[str] = []
        try:
            resp = client.get(base_url, headers=self.headers, timeout=self.timeout)
            if resp.status_code == 200 and resp.text:
                domain = urlparse(base_url).netloc
                # Extract all href attributes
                found_links = re.findall(r'href=[\'"]([^\'"]+)[\'"]', resp.text)
                for link in found_links:
                    full_url = urljoin(base_url, link.strip())
                    parsed = urlparse(full_url)
                    if parsed.netloc == domain:
                        if self._is_probable_product_url(full_url):
                            if full_url not in product_urls:
                                product_urls.append(full_url)
                                if len(product_urls) >= limit:
                                    break
        except Exception:
            pass

        return product_urls

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
            progress_callback("store_start", {"store": store_name, "message": f"Starting crawl of {store_name}..."})

        discovered_urls: List[str] = []

        with httpx.Client(follow_redirects=True, timeout=self.timeout) as client:
            # 1. Try Sitemap
            if sitemap_url:
                discovered_urls = self.discover_product_urls_from_sitemap(client, sitemap_url, limit=self.max_products_per_store)

            # 2. Try default sitemap paths if not found
            if not discovered_urls:
                for default_path in ["/sitemap.xml", "/sitemap_products.xml"]:
                    test_sitemap = urljoin(base_url, default_path)
                    discovered_urls = self.discover_product_urls_from_sitemap(client, test_sitemap, limit=self.max_products_per_store)
                    if discovered_urls:
                        break

            # 3. Fallback: Parse homepage links
            if not discovered_urls:
                discovered_urls = self.discover_product_urls_from_homepage(client, base_url, limit=self.max_products_per_store)

            stats["urls_discovered"] = len(discovered_urls)
            if progress_callback:
                progress_callback("links_discovered", {
                    "store": store_name,
                    "count": len(discovered_urls),
                    "message": f"Discovered {len(discovered_urls)} candidate product links for {store_name}."
                })

            # 4. Extract product data from discovered URLs
            for url in discovered_urls:
                try:
                    resp = client.get(url, headers=self.headers, timeout=self.timeout)
                    if resp.status_code == 200 and resp.text:
                        extracted = UniversalProductExtractor.extract_from_html(resp.text, url)
                        if extracted.get("name") and extracted.get("price_bdt"):
                            stats["products_extracted"] += 1

                            # Upsert to database
                            p_id, o_id = upsert_crawled_offer(
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

                    # Gentle polite delay between requests to avoid overloading local sellers
                    time.sleep(0.3)

                except Exception as e:
                    stats["errors"] += 1

        update_store_crawl_status(store_id, "completed", total_found_delta=stats["offers_upserted"])
        if progress_callback:
            progress_callback("store_end", {
                "store": store_name,
                "stats": stats,
                "message": f"Finished {store_name}: {stats['offers_upserted']} products indexed."
            })

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
            progress_callback("batch_start", {
                "total_stores": total_stores,
                "message": f"Starting sequential crawl across {total_stores} stores..."
            })

        for idx, store in enumerate(target_stores):
            if progress_callback:
                progress_callback("store_progress", {
                    "current_index": idx + 1,
                    "total_stores": total_stores,
                    "store": store["name"],
                    "message": f"[{idx+1}/{total_stores}] Crawling {store['name']}..."
                })

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
            progress_callback("batch_end", {
                "total_stores": total_stores,
                "results": all_results,
                "message": f"Completed sequential crawl of {total_stores} stores!"
            })

        return all_results
