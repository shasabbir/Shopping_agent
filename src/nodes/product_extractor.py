import re
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from src.models import ShoppingAgentState, ProductSpec
from src.tools.search import identify_store


def extract_price_from_text(text: str) -> Optional[float]:
    """Extract price in BDT from text using pattern matching."""
    if not text:
        return None

    # Matches patterns like '115,000 ৳', 'Tk 45,000', '45,999 BDT', 'Price: 112,000', '2,400৳'
    patterns = [
        r"(?:tk|bdt|price|৳)\s*[:.-]?\s*([\d,]{3,8})",
        r"([\d,]{3,8})\s*(?:tk|bdt|৳|taka)",
        r"(?:regular price|special price|cash discount price|price)\s*[:.-]?\s*([\d,]{3,8})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            clean_num = m.group(1).replace(",", "").strip()
            try:
                val = float(clean_num)
                if 200 <= val <= 3000000:
                    return val
            except ValueError:
                continue

    # Standalone number fallback if preceded by currency context
    num_match = re.search(r"([\d,]{4,7})", text)
    if num_match:
        try:
            val = float(num_match.group(1).replace(",", ""))
            if 500 <= val <= 2500000:
                return val
        except ValueError:
            pass

    return None


def extract_specs_from_text(text: str) -> Dict[str, str]:
    """Extract common tech specs from raw text."""
    specs = {}

    # RAM
    ram_match = re.search(r"(\d+\s*GB)\s*(?:DDR\d|RAM|LPDDR\d)?", text, re.IGNORECASE)
    if ram_match:
        specs["RAM"] = ram_match.group(0).strip()

    # GPU
    gpu_match = re.search(r"(RTX\s*\d{4}(?:\s*Ti)?|GTX\s*\d{4}|Radeon\s*[\w\d]+|Apple\s*M\d|Intel\s*Iris|Intel\s*Arc)", text, re.IGNORECASE)
    if gpu_match:
        specs["GPU"] = gpu_match.group(0).strip()

    # Processor
    cpu_match = re.search(r"(Core\s*i[3579]-[\w\d]+|Ryzen\s*[3579]\s*[\w\d]+|Snapdragon\s*[\w\d\s]+|Dimensity\s*[\w\d]+|Exynos\s*[\w\d]+|Apple\s*A\d+)", text, re.IGNORECASE)
    if cpu_match:
        specs["CPU"] = cpu_match.group(0).strip()

    # Storage
    storage_match = re.search(r"(\d+\s*(?:GB|TB)\s*(?:SSD|NVMe|UFS|ROM)?)", text, re.IGNORECASE)
    if storage_match:
        specs["Storage"] = storage_match.group(0).strip()

    # Display
    disp_match = re.search(r"(\d+(?:\.\d+)?\s*(?:inch|\")\s*(?:FHD|QHD|4K|AMOLED|OLED|IPS)?)", text, re.IGNORECASE)
    if disp_match:
        specs["Display"] = disp_match.group(0).strip()

    # Camera
    cam_match = re.search(r"(\d+\s*MP(?:\s*\+\s*\d+\s*MP)*)", text, re.IGNORECASE)
    if cam_match:
        specs["Camera"] = cam_match.group(0).strip()

    # Keyboard specific
    switch_match = re.search(r"(Blue|Red|Brown|Mechanical|Membrane|Optical|Magnetic)\s+Switch", text, re.IGNORECASE)
    if switch_match:
        specs["Switch Type"] = switch_match.group(0).strip()

    rgb_match = re.search(r"(RGB|Backlit|Rainbow|Monochrome)", text, re.IGNORECASE)
    if rgb_match:
        specs["Lighting"] = rgb_match.group(0).strip()

    keys_match = re.search(r"(\d+)\s*Keys?", text, re.IGNORECASE)
    if keys_match:
        specs["Key Count"] = keys_match.group(0).strip()

    conn_match = re.search(r"(Tri-mode|Wireless|Wired|Bluetooth|2\.4GHz)", text, re.IGNORECASE)
    if conn_match:
        specs["Connectivity"] = conn_match.group(0).strip()

    return specs


def detect_warranty(text: str) -> Optional[str]:
    """Detect warranty info in Bangladesh market context."""
    t = text.lower()
    if "official warranty" in t or "brand warranty" in t or "official replacement" in t:
        return "Official Warranty"
    if "seller warranty" in t or "service warranty" in t or "unofficial" in t:
        return "Seller / Unofficial Warranty"
    if "3 years" in t or "3 year" in t:
        return "3 Years Warranty"
    if "2 years" in t or "2 year" in t:
        return "2 Years Brand Warranty"
    if "1 year" in t or "1-year" in t:
        return "1 Year Warranty"
    return "Standard Retail Warranty"


def clean_product_title(title: str) -> str:
    """Strip store branding, SEO noise, and trailing pipes from product title."""
    clean = title
    for noise in [
        "| Star Tech", "| Ryans", "| Ryans Computers", "- Daraz", "| Pickaboo",
        "| Tech Land BD", "| Gadget & Gear", "| Apple Gadgets BD",
        "Price in Bangladesh", "Price in BD", "Price in BD 2026", "2026",
        "Lowest price in Bangladesh", "Buy Online"
    ]:
        clean = re.sub(re.escape(noise), "", clean, flags=re.IGNORECASE)
    return clean.strip(" -|:\t\n")


def parse_page_to_product(url: str, title: str, snippet: str, raw_markdown: Optional[str] = None) -> ProductSpec:
    """Parse raw page content or search snippet into a ProductSpec."""
    combined_text = (raw_markdown or "") + "\n" + title + "\n" + snippet
    store = identify_store(url)
    clean_title = clean_product_title(title)

    price = extract_price_from_text(combined_text)
    specs = extract_specs_from_text(combined_text)
    warranty = detect_warranty(combined_text)

    # Brand extraction
    brand = None
    common_brands = [
        "Lenovo", "Asus", "HP", "Dell", "Acer", "Apple", "Samsung", "Xiaomi", "Redmi",
        "Nothing", "Motorola", "Realme", "OnePlus", "MSI", "Gigabyte", "Sony", "Logitech",
        "Fantech", "Dareu", "Magegee", "Royal Kludge", "Monka", "Jedel", "Xtreme", "Walton"
    ]
    for b in common_brands:
        if re.search(rf"\b{re.escape(b)}\b", clean_title, re.IGNORECASE):
            brand = b
            break

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
        raw_snippet=snippet,
    )


def extract_elements_from_live_page(url: str, timeout: float = 3.5) -> Dict[str, Any]:
    """Fetch live web page and extract structured elements (Title, Price, Specs, Image, Warranty)."""
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

                # 1. Title
                h1 = soup.find("h1")
                if h1 and h1.get_text(strip=True):
                    elements["name"] = clean_product_title(h1.get_text(strip=True))

                # 2. Price
                price_tag = (
                    soup.find(class_="product-price") or
                    soup.find(class_="price") or
                    soup.find(class_="p-price") or
                    soup.find(class_="ins") or
                    soup.find(attrs={"itemprop": "price"})
                )
                if price_tag:
                    p_val = extract_price_from_text(price_tag.get_text(strip=True))
                    if p_val:
                        elements["price"] = p_val

                # 3. Image URL
                og_img = soup.find("meta", property="og:image")
                if og_img and og_img.get("content"):
                    elements["image_url"] = og_img["content"]
                else:
                    main_img = soup.select_one(".product-image img, .p-item-img img, #image")
                    if main_img and main_img.get("src"):
                        elements["image_url"] = main_img["src"]

                # 4. Specifications table
                specs_dict = {}
                for tr in soup.select(".data-table tr, table.specification tr"):
                    cols = tr.find_all(["td", "th"])
                    if len(cols) >= 2:
                        k = cols[0].get_text(strip=True)
                        v = cols[1].get_text(strip=True)
                        if k and v and len(k) < 35 and len(v) < 80:
                            specs_dict[k] = v

                # Short description list if table not found
                if not specs_dict:
                    for li in soup.select(".short-description li, .specification-tab li"):
                        text = li.get_text(strip=True)
                        if ":" in text:
                            parts = text.split(":", 1)
                            specs_dict[parts[0].strip()] = parts[1].strip()
                        elif text:
                            specs_dict[f"Feature {len(specs_dict)+1}"] = text

                if specs_dict:
                    elements["specs"] = specs_dict

                # 5. Warranty
                warranty_elem = soup.find(string=re.compile(r"warranty", re.IGNORECASE))
                if warranty_elem:
                    elements["warranty"] = detect_warranty(str(warranty_elem))

    except Exception:
        pass

    return elements


def product_extractor_node(state: ShoppingAgentState) -> ShoppingAgentState:
    """Extract structured elements from up to 10 candidate pages."""
    candidates = state.get("candidate_urls", [])
    extracted: List[ProductSpec] = []
    seen_names = set()

    # Target up to 10 products
    for item in candidates[:14]:
        if len(extracted) >= 10:
            break

        url = item.get("url", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        pre_image = item.get("image_url")
        pre_price_text = item.get("price_text", "")
        pre_specs_list = item.get("specs_list", [])

        # Start with base product parsed from candidate data
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

        # For the top 5 candidates with live pages, fetch live elements for deeper specs
        if len(extracted) < 5 and url.startswith("http"):
            live_elements = extract_elements_from_live_page(url, timeout=3.0)
            if live_elements.get("name"):
                product.name = live_elements["name"]
            if live_elements.get("price"):
                product.price = live_elements["price"]
            if live_elements.get("image_url") and not product.image_url:
                product.image_url = live_elements["image_url"]
            if live_elements.get("specs"):
                product.specs.update(live_elements["specs"])
            if live_elements.get("warranty"):
                product.warranty = live_elements["warranty"]

        # Deduplication and quality validation
        norm_name = re.sub(r"[^a-zA-Z0-9]", "", product.name.lower())[:25]
        if norm_name and norm_name not in seen_names and len(product.name) > 3:
            seen_names.add(norm_name)
            extracted.append(product)

    # Fallback to make sure at least a set of products exists if search was completely empty
    if not extracted and candidates:
        for c in candidates[:10]:
            p = parse_page_to_product(c.get("url", ""), c.get("title", ""), c.get("snippet", ""))
            extracted.append(p)

    logs = list(state.get("logs", []))
    logs.append(f"Product extractor retrieved elements for {len(extracted)} products.")

    return {
        **state,
        "extracted_products": extracted,
        "logs": logs,
    }
