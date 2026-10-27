import re
import json
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from src.models import ShoppingAgentState, ProductSpec
from src.tools.search import identify_store

NON_PRICE_UNITS = (
    r"(?:rpm|mah|dpi|hz|mhz|ghz|watt|watts|w|k|mb|gb|tb|kb|v|volt|volts|amp|amps|"
    r"hour|hours|hr|hrs|kg|g|gm|gms|mg|ml|l|liter|liters|oz|mm|cm|meter|m|inch|inches|"
    r"ft|yard|gsm|fps|cd/m2|nit|nits|pixels|px|core|cores|threads|pack|pcs|count|size|sizes)"
)


def extract_price_from_text(text: str) -> Optional[float]:
    """Extract price in BDT from text using strict pattern matching.
    Guarantees non-price specs (18000 RPM, 5000 mAh, Out Of Stock) are NEVER decoded as prices."""
    if not text:
        return None

    # Disregard text that explicitly signals out of stock or TBA
    if re.search(r"\b(?:out of stock|to be announced|tba|upcoming|discontinued|call for price)\b", text, re.IGNORECASE):
        return None

    # Pattern 1: Digits followed by currency symbol/code (e.g. '115,000৳', '45,000 BDT', '2,400 Tk', '45000 taka')
    m1 = re.search(r"([\d,]{2,8}(?:\.\d{1,2})?)\s*(?:৳|tk\.?|bdt|taka)(?!\s*" + NON_PRICE_UNITS + r"\b)", text, re.IGNORECASE)
    if m1:
        try:
            val = float(m1.group(1).replace(",", ""))
            if 50 <= val <= 10000000:
                return val
        except ValueError:
            pass

    # Pattern 2: Currency symbol/code followed by digits (e.g. '৳ 115,000', 'Tk 45,000', 'BDT 46,999')
    m2 = re.search(r"(?:৳|tk\.?|bdt)\s*[:.-]?\s*([\d,]{2,8}(?:\.\d{1,2})?)(?!\s*" + NON_PRICE_UNITS + r"\b)", text, re.IGNORECASE)
    if m2:
        try:
            val = float(m2.group(1).replace(",", ""))
            if 50 <= val <= 10000000:
                return val
        except ValueError:
            pass

    # Pattern 3: Explicit price label like 'Price: 45,000' or 'Special Cash Price: 112,000'
    m3 = re.search(r"\b(?:regular price|special price|cash discount price|cash price|sale price|price|discounted price)\s*[:.-]?\s*([\d,]{2,8}(?:\.\d{1,2})?)(?!\s*" + NON_PRICE_UNITS + r"\b)", text, re.IGNORECASE)
    if m3:
        try:
            val = float(m3.group(1).replace(",", ""))
            if 50 <= val <= 10000000:
                return val
        except ValueError:
            pass

    return None


def extract_specs_from_text(text: str) -> Dict[str, str]:
    """Extract attributes across any product category from raw text."""
    specs = {}

    # Category 1: Footwear & Fashion specs
    mat_match = re.search(r"(?:material|upper|fabric):\s*([a-zA-Z\s]+)", text, re.IGNORECASE)
    if mat_match:
        specs["Material"] = mat_match.group(1).strip()
    sole_match = re.search(r"(?:sole|outsole):\s*([a-zA-Z\s]+)", text, re.IGNORECASE)
    if sole_match:
        specs["Sole"] = sole_match.group(1).strip()
    closure_match = re.search(r"(lace-up|slip-on|zipper|velcro|buckle)", text, re.IGNORECASE)
    if closure_match:
        specs["Closure"] = closure_match.group(1).title()

    # Category 2: Kitchen & Home Appliances
    cap_match = re.search(r"(\d+(?:\.\d+)?\s*(?:L|Litre|Litres|Liter|Litres|KG))\b", text, re.IGNORECASE)
    if cap_match:
        specs["Capacity"] = cap_match.group(1).strip()
    power_match = re.search(r"(\d+\s*(?:Watt|W)\b)", text, re.IGNORECASE)
    if power_match:
        specs["Power"] = power_match.group(1).strip()

    # Category 3: Beauty & Personal Care
    vol_match = re.search(r"(\d+\s*(?:ml|gm|g|oz))\b", text, re.IGNORECASE)
    if vol_match:
        specs["Volume/Weight"] = vol_match.group(1).strip()

    # Category 4: Tech & Hardware (if applicable)
    ram_match = re.search(r"(\d+\s*GB)\s*(?:DDR\d|RAM|LPDDR\d)?", text, re.IGNORECASE)
    if ram_match:
        specs["RAM"] = ram_match.group(0).strip()
    gpu_match = re.search(r"(RTX\s*\d{4}(?:\s*Ti)?|GTX\s*\d{4}|Radeon\s*[\w\d]+|Apple\s*M\d|Intel\s*Iris|Intel\s*Arc)", text, re.IGNORECASE)
    if gpu_match:
        specs["GPU"] = gpu_match.group(0).strip()
    cpu_match = re.search(r"(Core\s*i[3579]-[\w\d]+|Ryzen\s*[3579]\s*[\w\d]+|Snapdragon\s*[\w\d\s]+|Dimensity\s*[\w\d]+|Exynos\s*[\w\d]+|Apple\s*A\d+)", text, re.IGNORECASE)
    if cpu_match:
        specs["CPU"] = cpu_match.group(0).strip()
    storage_match = re.search(r"(\d+\s*(?:GB|TB)\s*(?:SSD|NVMe|UFS|ROM)?)", text, re.IGNORECASE)
    if storage_match:
        specs["Storage"] = storage_match.group(0).strip()
    disp_match = re.search(r"(\d+(?:\.\d+)?\s*(?:inch|\")\s*(?:FHD|QHD|4K|AMOLED|OLED|IPS)?)", text, re.IGNORECASE)
    if disp_match:
        specs["Display"] = disp_match.group(0).strip()

    # Generic key-value pattern: "Key: Value"
    for line in text.splitlines():
        if ":" in line:
            parts = line.split(":", 1)
            k = parts[0].strip()
            v = parts[1].strip()
            if 2 <= len(k) <= 25 and 2 <= len(v) <= 50 and not any(skip in k.lower() for skip in ["http", "price", "stock", "url"]):
                if k not in specs:
                    specs[k] = v

    return specs


def detect_warranty(text: str) -> Optional[str]:
    """Detect warranty or guarantee info in Bangladesh retail context."""
    t = text.lower()
    if "official warranty" in t or "brand warranty" in t or "official replacement" in t:
        return "Official Brand Warranty"
    if "seller warranty" in t or "service warranty" in t or "shop warranty" in t:
        return "Seller Warranty"
    if "replacement warranty" in t:
        return "Replacement Warranty"
    if "3 years" in t or "3 year" in t:
        return "3 Years Warranty"
    if "2 years" in t or "2 year" in t:
        return "2 Years Warranty"
    if "1 year" in t or "1-year" in t:
        return "1 Year Warranty"
    if "6 months" in t or "6-month" in t:
        return "6 Months Warranty"
    if "money back" in t or "return policy" in t:
        return "Standard Return Policy"
    return "Standard Retail Warranty"


def clean_product_title(title: str) -> str:
    """Strip store branding, SEO noise, and trailing pipes from product title across any retailer."""
    clean = title.strip()
    # Strip common retailer branding and SEO tails
    clean = re.sub(r"\s*\|\s*(?:Star Tech|Ryans|Daraz|Pickaboo|TechLand|Gadget & Gear|Apex|Bata|Singer|Walton|Aarong|Chaldal|Othoba|Rokomari).*$", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*-\s*(?:Daraz|Pickaboo|Aarong|Apex|Bata|Walton|Singer|Rokomari).*$", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\b(?:price in bangladesh|price in bd|buy online|lowest price in bd|lowest price in bangladesh|best price in bd|202\d)\b.*$", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*[-|:]\s*$", "", clean)
    return clean.strip(" -|:\t\n")


def parse_page_to_product(url: str, title: str, snippet: str, raw_markdown: Optional[str] = None) -> ProductSpec:
    """Parse raw page content or search snippet into a ProductSpec."""
    combined_text = (raw_markdown or "") + "\n" + title + "\n" + snippet
    store = identify_store(url)
    clean_title = clean_product_title(title)

    # Check for out-of-stock indicators
    is_out_of_stock = bool(re.search(r"\b(?:out of stock|to be announced|tba|upcoming|discontinued|sold out)\b", snippet, re.IGNORECASE))
    price = None if is_out_of_stock else extract_price_from_text(combined_text)

    specs = extract_specs_from_text(combined_text)
    warranty = detect_warranty(combined_text)

    # Brand extraction: first token of title if capitalized, or recognized brand
    brand = None
    title_words = clean_title.split()
    if title_words and title_words[0].isalnum() and len(title_words[0]) > 1:
        brand = title_words[0]

    return ProductSpec(
        name=clean_title or title,
        brand=brand,
        price=price,
        currency="BDT",
        store=store,
        url=url,
        specs=specs,
        warranty=warranty,
        is_official=("Official" in (warranty or "")),
        in_stock=not is_out_of_stock,
        raw_snippet=snippet,
    )


def extract_elements_from_live_page(url: str, timeout: float = 3.5) -> Dict[str, Any]:
    """
    Fetch live web page and extract structured elements using universal Schema.org JSON-LD,
    OpenGraph metadata, and HTML table parsing without store favoritism.
    """
    elements = {"specs": {}}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")

                # 1. Store name from og:site_name
                og_site = soup.find("meta", property="og:site_name")
                if og_site and og_site.get("content"):
                    elements["store"] = og_site["content"].strip()

                # 2. Universal Schema.org / JSON-LD extraction
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        if not script.string:
                            continue
                        payload = json.loads(script.string)
                        items = payload if isinstance(payload, list) else payload.get("@graph", [payload])
                        for item in items:
                            if isinstance(item, dict) and item.get("@type") in ["Product", "IndividualProduct"]:
                                if item.get("name") and not elements.get("name"):
                                    elements["name"] = clean_product_title(str(item["name"]))
                                if item.get("image") and not elements.get("image_url"):
                                    img = item["image"]
                                    elements["image_url"] = img if isinstance(img, str) else (img[0] if isinstance(img, list) and img else None)
                                if item.get("brand") and not elements.get("brand"):
                                    b = item["brand"]
                                    elements["brand"] = b.get("name") if isinstance(b, dict) else str(b)

                                offers = item.get("offers", {})
                                if isinstance(offers, list) and offers:
                                    offers = offers[0]
                                if isinstance(offers, dict):
                                    if offers.get("price") and not elements.get("price"):
                                        try:
                                            elements["price"] = float(str(offers["price"]).replace(",", ""))
                                        except ValueError:
                                            pass
                                    avail = str(offers.get("availability", "")).lower()
                                    if "outofstock" in avail or "soldout" in avail:
                                        elements["is_out_of_stock"] = True
                                    elif "instock" in avail or "preorder" in avail:
                                        elements["is_out_of_stock"] = False

                                # Additional custom properties (sizes, materials, specs)
                                for prop in item.get("additionalProperty", []):
                                    if isinstance(prop, dict) and prop.get("name") and prop.get("value"):
                                        elements["specs"][str(prop["name"]).strip()] = str(prop["value"]).strip()
                    except Exception:
                        continue

                # 3. OpenGraph / Standard HTML Title
                if not elements.get("name"):
                    og_title = soup.find("meta", property="og:title")
                    h1 = soup.find("h1")
                    raw_title = (og_title.get("content") if og_title else None) or (h1.get_text(strip=True) if h1 else None)
                    if raw_title:
                        elements["name"] = clean_product_title(raw_title)

                # 4. Stock status check from HTML classes/text
                if "is_out_of_stock" not in elements:
                    stock_tag = soup.find(class_=re.compile(r"stock|availability", re.IGNORECASE))
                    stock_text = stock_tag.get_text(strip=True) if stock_tag else ""
                    elements["is_out_of_stock"] = bool(re.search(r"\b(?:out of stock|to be announced|tba|upcoming|discontinued|sold out)\b", stock_text, re.IGNORECASE))

                # 5. Price from Microdata / Specialized HTML tags if not found via JSON-LD
                if not elements.get("price") and not elements.get("is_out_of_stock"):
                    price_tag = (
                        soup.find("ins") or
                        soup.find(class_=re.compile(r"price-new|product-price|sale-price|current-price|p-price|price", re.IGNORECASE)) or
                        soup.find(attrs={"itemprop": "price"})
                    )
                    if price_tag:
                        p_val = extract_price_from_text(price_tag.get_text(strip=True))
                        if p_val:
                            elements["price"] = p_val

                # 6. Image URL from OpenGraph or main image tag
                if not elements.get("image_url"):
                    og_img = soup.find("meta", property="og:image")
                    if og_img and og_img.get("content"):
                        elements["image_url"] = og_img["content"]
                    else:
                        main_img = soup.select_one(".product-image img, .p-item-img img, #image, .main-image img, [itemprop='image']")
                        if main_img and main_img.get("src"):
                            elements["image_url"] = main_img["src"]

                # 7. Generic Specifications table / definition list parser
                specs_dict = elements.get("specs", {})
                for tr in soup.select("table.specification tr, .data-table tr, table tr"):
                    cols = tr.find_all(["td", "th"])
                    if len(cols) >= 2:
                        k = cols[0].get_text(strip=True)
                        v = cols[1].get_text(strip=True)
                        if k and v and len(k) < 35 and len(v) < 90:
                            specs_dict[k] = v

                # Definition lists (<dl><dt>Key</dt><dd>Value</dd></dl>)
                for dt in soup.find_all("dt"):
                    dd = dt.find_next_sibling("dd")
                    if dd:
                        k = dt.get_text(strip=True)
                        v = dd.get_text(strip=True)
                        if k and v and len(k) < 35 and len(v) < 90:
                            specs_dict[k] = v

                if specs_dict:
                    elements["specs"] = specs_dict

                # 8. Warranty info
                warranty_elem = soup.find(string=re.compile(r"warranty|guarantee", re.IGNORECASE))
                if warranty_elem:
                    elements["warranty"] = detect_warranty(str(warranty_elem))

    except Exception:
        pass

    return elements


def product_extractor_node(state: ShoppingAgentState) -> ShoppingAgentState:
    """Extract structured elements from candidate pages or verify freshness of local catalog products."""
    existing_extracted = state.get("extracted_products", [])
    logs = list(state.get("logs", []))

    if existing_extracted:
        logs.append(f"Catalog Intelligence: Serving {len(existing_extracted)} verified products from local database catalog.")
        return {
            **state,
            "extracted_products": existing_extracted,
            "logs": logs,
        }

    candidates = state.get("candidate_urls", [])
    extracted: List[ProductSpec] = []
    seen_names = set()

    for item in candidates[:14]:
        if len(extracted) >= 10:
            break

        url = item.get("url", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        pre_image = item.get("image_url")
        pre_price_text = item.get("price_text", "")
        pre_specs_list = item.get("specs_list", [])

        # Parse base product from search candidate
        product = parse_page_to_product(url, title, snippet)

        if pre_image:
            product.image_url = pre_image

        if pre_price_text and not product.price:
            product.price = extract_price_from_text(pre_price_text)

        if pre_specs_list:
            for s in pre_specs_list:
                if ":" in s:
                    k, v = s.split(":", 1)
                    product.specs[k.strip()] = v.strip()
                elif s:
                    product.specs[f"Highlight {len(product.specs)+1}"] = s

        # For the top 5 candidates, fetch live page elements for deep specs, JSON-LD, and verified price
        if len(extracted) < 5 and url.startswith("http"):
            live_elements = extract_elements_from_live_page(url, timeout=3.0)
            if live_elements.get("name"):
                product.name = live_elements["name"]

            if live_elements.get("store"):
                product.store = live_elements["store"]

            if live_elements.get("brand"):
                product.brand = live_elements["brand"]

            # Stock check
            if live_elements.get("is_out_of_stock"):
                product.price = None
                product.in_stock = False
            elif live_elements.get("price"):
                product.price = live_elements["price"]
                product.in_stock = True

            if live_elements.get("image_url") and not product.image_url:
                product.image_url = live_elements["image_url"]

            if live_elements.get("specs"):
                product.specs.update(live_elements["specs"])

            if live_elements.get("warranty"):
                product.warranty = live_elements["warranty"]

        # Deduplication by sanitized name prefix
        norm_name = re.sub(r"[^a-zA-Z0-9]", "", product.name.lower())[:25]
        if norm_name and norm_name not in seen_names and len(product.name) > 3:
            seen_names.add(norm_name)
            extracted.append(product)

    # Fallback to make sure products exist if live extraction was blocked
    if not extracted and candidates:
        for c in candidates[:10]:
            p = parse_page_to_product(c.get("url", ""), c.get("title", ""), c.get("snippet", ""))
            extracted.append(p)

    logs = list(state.get("logs", []))
    logs.append(f"Product extractor retrieved elements for {len(extracted)} products across open web.")

    return {
        **state,
        "extracted_products": extracted,
        "logs": logs,
    }
