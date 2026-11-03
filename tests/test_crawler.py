import pytest
from src.crawler.universal_extractor import UniversalProductExtractor
from src.database import init_db, upsert_crawled_offer, search_catalog, get_catalog_stats, get_all_stores


def test_universal_extractor_json_ld():
    html = """
    <html>
    <head>
        <title>Lenovo LOQ 15 Gaming Laptop - Star Tech</title>
        <script type="application/ld+json">
        {
            "@type": "Product",
            "name": "Lenovo LOQ 15 Gaming Laptop",
            "brand": {"name": "Lenovo"},
            "image": "https://img.com/laptop.jpg",
            "offers": {
                "@type": "Offer",
                "price": "115000",
                "priceCurrency": "BDT",
                "availability": "https://schema.org/InStock"
            },
            "additionalProperty": [
                {"name": "RAM", "value": "16GB DDR5"},
                {"name": "GPU", "value": "RTX 4050 6GB"}
            ]
        }
        </script>
    </head>
    <body>
        <h1>Lenovo LOQ 15 Gaming Laptop</h1>
    </body>
    </html>
    """
    res = UniversalProductExtractor.extract_from_html(html, "https://www.startech.com.bd/product/123")
    assert res["name"] == "Lenovo LOQ 15 Gaming Laptop"
    assert res["brand"] == "Lenovo"
    assert res["price_bdt"] == 115000.0
    assert res["in_stock"] is True
    assert res["image_url"] == "https://img.com/laptop.jpg"
    assert res["category"] == "laptop"
    assert "RAM" in res["specs"]
    assert res["specs"]["RAM"] == "16GB DDR5"


def test_universal_extractor_html_dom_fallback():
    html = """
    <html>
    <head>
        <meta property="og:title" content="Samsung Galaxy A55 5G - Pickaboo">
        <meta property="og:image" content="https://img.com/a55.jpg">
    </head>
    <body>
        <h1>Samsung Galaxy A55 5G</h1>
        <div class="product-price">
            <span class="price">46,999 ৳</span>
            <del class="regular-price">49,999 Tk</del>
        </div>
        <div class="stock-status">In Stock</div>
        <table class="specification">
            <tr><td>Display</td><td>6.6 inch Super AMOLED 120Hz</td></tr>
            <tr><td>Battery</td><td>5000 mAh</td></tr>
        </table>
    </body>
    </html>
    """
    res = UniversalProductExtractor.extract_from_html(html, "https://www.pickaboo.com/product/a55")
    assert "Samsung Galaxy A55" in res["name"]
    assert res["price_bdt"] == 46999.0
    assert res["regular_price_bdt"] == 49999.0
    assert res["in_stock"] is True
    assert res["category"] == "smartphone"
    assert res["specs"]["Display"] == "6.6 inch Super AMOLED 120Hz"


def test_strict_price_rejection_of_specs():
    # Non-price measurements should never become prices
    assert UniversalProductExtractor.extract_price_from_text("18000 RPM high speed motor") is None
    assert UniversalProductExtractor.extract_price_from_text("Battery 5000 mAh") is None
    assert UniversalProductExtractor.extract_price_from_text("120 Watt fast charger") is None
    assert UniversalProductExtractor.extract_price_from_text("Out Of Stock") is None
    assert UniversalProductExtractor.extract_price_from_text("To be announced") is None

    # Valid prices
    assert UniversalProductExtractor.extract_price_from_text("Special Price: 115,000 BDT") == 115000.0
    assert UniversalProductExtractor.extract_price_from_text("৳ 45,000") == 45000.0
    assert UniversalProductExtractor.extract_price_from_text("3,500 Tk.") == 3500.0


def test_db_upsert_and_multi_seller_clustering():
    init_db()
    from src.database import get_session, Product, Offer
    session = get_session()
    session.query(Offer).filter(Offer.store_product_title.like("%Lenovo LOQ%")).delete(synchronize_session=False)
    session.query(Product).filter(Product.canonical_name.like("%Lenovo LOQ%")).delete(synchronize_session=False)
    session.commit()
    session.close()

    stores = get_all_stores()
    assert len(stores) >= 20
    startech = next(s for s in stores if "Star Tech" in s["name"])
    ryans = next(s for s in stores if "Ryans" in s["name"])

    # Store 1 offers Lenovo LOQ
    p_id_1, o_id_1 = upsert_crawled_offer(
        store_id=startech["id"],
        store_product_title="Lenovo LOQ 15 Gaming Laptop (i5-12450HX, 16GB, RTX 4050)",
        product_url="https://www.startech.com.bd/lenovo-loq-15",
        price_bdt=115000.0,
        category="laptop",
        brand="Lenovo",
        in_stock=True,
        specs={"RAM": "16GB", "GPU": "RTX 4050"},
    )

    # Store 2 offers the exact same laptop with slightly different title
    p_id_2, o_id_2 = upsert_crawled_offer(
        store_id=ryans["id"],
        store_product_title="Lenovo LOQ 15IAX9 Core i5 12th Gen RTX 4050 Laptop",
        product_url="https://www.ryans.com/lenovo-loq-15iax9",
        price_bdt=118000.0,
        category="laptop",
        brand="Lenovo",
        in_stock=True,
        specs={"RAM": "16GB", "GPU": "RTX 4050"},
    )

    # Verify both offers clustered into the SAME canonical product!
    assert p_id_1 == p_id_2

    # Query catalog and verify multi-seller offers are attached
    results = search_catalog("lenovo loq", category="laptop")
    assert len(results) >= 1
    loq_product = next(r for r in results if r["id"] == p_id_1)
    assert len(loq_product["offers"]) >= 2
    assert loq_product["lowest_price"] == 115000.0
    # Star Tech offer should be first because it is cheaper (115k vs 118k)
    assert loq_product["offers"][0]["price_bdt"] == 115000.0
    assert loq_product["offers"][1]["price_bdt"] == 118000.0


def test_universal_crawler_sitemap_discovery():
    from src.crawler.universal_crawler import UniversalStoreCrawler
    import httpx

    crawler = UniversalStoreCrawler()

    # Mock XML sitemap response
    sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://example.com/product/laptop-1</loc></url>
        <url><loc>https://example.com/product/phone-2</loc></url>
        <url><loc>https://example.com/about-us</loc></url>
        <url><loc>https://example.com/cart</loc></url>
    </urlset>
    """

    class MockClient:
        def get(self, url, **kwargs):
            class MockResponse:
                status_code = 200
                text = sample_xml
            return MockResponse()

    discovered = crawler.discover_product_urls_from_sitemap(MockClient(), "https://example.com/sitemap.xml")
    assert len(discovered) == 2
    assert "https://example.com/product/laptop-1" in discovered
    assert "https://example.com/product/phone-2" in discovered
    assert "https://example.com/cart" not in discovered


def test_nextjs_and_escaped_script_extraction():
    """Test extracting prices and names from Next.js App Router / RSC payloads and escaped JSON."""
    # Singer BD-style embedded JSON state with escaped quotes and sell_price
    singer_html = """
    <html><head><title>Google TV | Singer Bangladesh Limited</title></head>
    <body>
    <script>
    self.__next_f.push([1,"{\\\"product\\\":{\\\"slug\\\":\\\"singer-google-tv-32-inch-slg32d3200wtv\\\",\\\"regular_price\\\":30990,\\\"sell_price\\\":27990,\\\"name\\\":\\\"Google TV\\\"}}"]);
    </script>
    </body></html>
    """
    res = UniversalProductExtractor.extract_from_html(singer_html, "https://www.singerbd.com/product/singer-google-tv-32-inch-slg32d3200wtv")
    assert res["price_bdt"] in [27990.0, 30990.0]
    assert "Singer Google Tv 32 Inch Slg32D3200Wtv" in res["name"]

    # Shwapno-style Next.js RSC payload with formatted currency string
    shwapno_html = """
    <html><head><title>Shop Parachute Advanced Extra Care Hair Oil 150ml at Shwapno.com | Grocery</title></head>
    <body>
    <script>
    self.__next_f.push([1,"{\\\"price\\\":{\\\"price\\\":\\\"৳210\\\"},\\\"in_stock\\\":true}"]);
    </script>
    </body></html>
    """
    res2 = UniversalProductExtractor.extract_from_html(shwapno_html, "https://www.shwapno.com/parachute-advanced-extra-care-hair-oil-150ml-2")
    assert res2["price_bdt"] == 210.0
    assert "Parachute Advanced Extra Care Hair Oil 150ml" in res2["name"]
    assert "Shop" not in res2["name"]


def test_url_priority_filtering_of_assets_and_categories():
    """Verify that images, utility links, and categories are filtered out from product priorities."""
    from src.crawler.universal_crawler import get_url_product_priority

    # Assets & utility links must return 99 (ignored)
    assert get_url_product_priority("https://www.skyland.com.bd/image/cache/catalog/A4TECH/a4tech-bloody.webp") == 99
    assert get_url_product_priority("https://potakait.com/account/review?product_id=2711") == 99
    assert get_url_product_priority("https://www.skyland.com.bd/product/compare") == 99

    # Category / brand pages must return 10 (not a product <= 3)
    assert get_url_product_priority("https://www.ryans.com/category/all-laptop-gaming") == 10
    assert get_url_product_priority("https://www.daraz.com.bd/sensodyne-1-26797/") == 10
    assert get_url_product_priority("https://www.daraz.com.bd/green-tea-14565/") == 10

    # Real products must return <= 3
    assert get_url_product_priority("https://www.daraz.com.bd/i452410383-s2164530023.html") == 0
    assert get_url_product_priority("https://www.daraz.com.bd/products/samsung-galaxy-s24-ultra-i452410383-s2164530023.html") == 0
    assert get_url_product_priority("https://www.singerbd.com/product/singer-google-tv-32-inch-slg32d3200wtv") == 1
    assert get_url_product_priority("https://www.startech.com.bd/fantech-helios-ux3-space-edition-gaming-mouse") == 3
    assert get_url_product_priority("https://www.techlandbd.com/asus-rog-strix-g16-gaming-laptop") == 3

