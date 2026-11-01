import pytest
from datetime import datetime, timezone
from src.database import (
    init_db,
    get_session,
    Store,
    CrawlFrontier,
    ingest_frontier_urls,
    pop_next_frontier_item,
    update_frontier_item_result,
    get_frontier_metrics,
    seed_frontier_from_stores,
)
from src.crawler.stealth_engine import (
    PersonaManager,
    AntiBotCadence,
    StoreCircuitBreaker,
)
from src.crawler.daemon_crawler import ContinuousStealthCrawler


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    init_db()


def test_persona_manager_coherence():
    persona = PersonaManager.get_random_persona()
    assert persona.tls_impersonate in ["chrome124", "edge124", "chrome120", "safari17_0"]
    headers = persona.get_headers("https://www.startech.com.bd/product/123")

    assert "User-Agent" in headers
    assert "Sec-Ch-Ua" in headers
    assert "Sec-Ch-Ua-Platform" in headers
    assert headers["Referer"] == "https://www.startech.com.bd/"


def test_antibot_cadence_delays():
    cadence = AntiBotCadence()

    # Stealth profile
    stealth_delays = [cadence.calculate_delay(store_id=None, speed_profile="stealth") for _ in range(10)]
    assert all(3.0 <= d <= 12.0 for d in stealth_delays)

    # Turbo profile (base delays without burst pause)
    turbo_delays = [cadence.calculate_delay(store_id=None, speed_profile="turbo") for _ in range(10)]
    assert all(0.8 <= d <= 3.5 for d in turbo_delays)

    # Normal profile with store_id to verify burst pause triggers
    store_delays = [cadence.calculate_delay(store_id=999, speed_profile="normal") for _ in range(15)]
    assert any(d >= 15.0 for d in store_delays)  # At least one burst pause occurred
    assert all(1.5 <= d <= 35.0 for d in store_delays)


def test_store_circuit_breaker():
    cb = StoreCircuitBreaker()
    store_id = 9999

    assert cb.is_eligible(store_id) is True

    # 429 trigger exponential backoff
    cb.record_failure(store_id, status_code=429)
    assert cb.is_eligible(store_id) is False
    assert cb.get_remaining_cooldown(store_id) > 0

    # Success clears cooldown
    cb.record_success(store_id)
    assert cb.is_eligible(store_id) is True
    assert cb.get_remaining_cooldown(store_id) == 0

    # 403 switches mode to browser
    cb.record_failure(store_id, status_code=403, error_msg="Cloudflare Challenge")
    assert cb.get_recommended_mode(store_id) == "browser"


def test_frontier_queue_lifecycle():
    session = get_session()
    store = session.query(Store).first()
    session.close()
    assert store is not None

    test_urls = [
        f"https://example.com/test-prod-{i}" for i in range(5)
    ]

    # Ingest test URLs
    inserted = ingest_frontier_urls(store.id, test_urls, url_type="product", priority=0)
    assert inserted >= 1

    # Pop item
    popped = pop_next_frontier_item(store.id)
    assert popped is not None
    assert popped["status"] == "in_progress"

    # Update item result
    update_frontier_item_result(popped["id"], status="completed", http_status=200)

    # Verify metrics
    metrics = get_frontier_metrics()
    assert metrics["total_urls"] >= 1
    assert metrics["completed"] >= 1

    # Cleanup test items
    session = get_session()
    session.query(CrawlFrontier).filter(CrawlFrontier.url.like("%example.com/test-prod%")).delete(synchronize_session=False)
    session.commit()
    session.close()


def test_continuous_daemon_single_iteration():
    crawler = ContinuousStealthCrawler(speed_profile="turbo")
    # Run 1 round-robin iteration
    crawler.run_continuous_loop(max_iterations=1)
    status = crawler.get_status()
    assert "stats" in status
    assert "frontier" in status
    assert status["is_running"] is False


def test_daemon_sitemap_and_category_processing():
    crawler = ContinuousStealthCrawler(speed_profile="turbo")
    sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://www.startech.com.bd/product-detail/lenovo-loq-15</loc></url>
      <url><loc>https://www.startech.com.bd/category/laptops</loc></url>
    </urlset>"""
    # Verify no NameError or regex parsing exception
    crawler._process_sitemap_content(store_id=1, sitemap_url="https://www.startech.com.bd/sitemap.xml", text=sample_xml)

    sample_html = """<html><body>
    <a href="/lenovo-laptop-core-i5">Lenovo Laptop</a>
    <a href="/category/laptops">All Laptops</a>
    </body></html>"""
    store = {"id": 1, "name": "Star Tech", "base_url": "https://www.startech.com.bd"}
    links = crawler._extract_links_from_category(store, "https://www.startech.com.bd/category/laptops", sample_html)
    assert isinstance(links, list)
