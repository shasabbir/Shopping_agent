import re
from typing import List, Optional
from src.models import ShoppingAgentState, ProductSpec
from src.tools.jina_reader import fetch_page_content
from src.tools.search import identify_store


def extract_price_from_text(text: str) -> Optional[float]:
    """Extract price in BDT from text using pattern matching."""
    # Matches patterns like '115,000 ৳', 'Tk 45,000', '45,999 BDT', 'Price: 112,000'
    patterns = [
        r"(?:tk|bdt|price|৳)\s*[:.-]?\s*([\d,]{4,7})",
        r"([\d,]{4,7})\s*(?:tk|bdt|৳|taka)",
        r"(?:regular price|special price|cash discount price)\s*[:.-]?\s*([\d,]{4,7})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            clean_num = m.group(1).replace(",", "").strip()
            try:
                val = float(clean_num)
                if 500 <= val <= 2000000:
                    return val
            except ValueError:
                continue
    return None


def extract_specs_from_text(text: str) -> dict:
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

    # Camera (for phones)
    cam_match = re.search(r"(\d+\s*MP(?:\s*\+\s*\d+\s*MP)*)", text, re.IGNORECASE)
    if cam_match:
        specs["Camera"] = cam_match.group(0).strip()

    return specs


def detect_warranty(text: str) -> Optional[str]:
    """Detect warranty info in Bangladesh market context."""
    t = text.lower()
    if "official warranty" in t or "brand warranty" in t or "official replacement" in t:
        return "Official Warranty"
    if "seller warranty" in t or "service warranty" in t or "unofficial" in t:
        return "Seller / Unofficial Warranty"
    if "2 years" in t or "2 year" in t:
        return "2 Years Brand Warranty"
    if "1 year" in t or "1-year" in t:
        return "1 Year Warranty"
    return "Standard Retail Warranty"


def parse_page_to_product(url: str, title: str, snippet: str, raw_markdown: Optional[str]) -> ProductSpec:
    """Parse raw page content or search snippet into a ProductSpec."""
    combined_text = (raw_markdown or "") + "\n" + title + "\n" + snippet
    store = identify_store(url)

    # Clean product title
    clean_title = title
    for suffix in ["| Star Tech", "| Ryans", "| Pickaboo", "- Daraz", "Price in BD", "Price in Bangladesh"]:
        clean_title = clean_title.split(suffix)[0].strip()

    price = extract_price_from_text(combined_text)
    specs = extract_specs_from_text(combined_text)
    warranty = detect_warranty(combined_text)

    # Simple brand extraction
    brand = None
    common_brands = ["Lenovo", "Asus", "HP", "Dell", "Acer", "Apple", "Samsung", "Xiaomi", "Redmi", "Nothing", "Motorola", "Realme", "OnePlus", "MSI", "Gigabyte"]
    for b in common_brands:
        if b.lower() in clean_title.lower():
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


def product_extractor_node(state: ShoppingAgentState) -> ShoppingAgentState:
    """Fetch product pages via Jina Reader and extract normalized product details."""
    candidates = state.get("candidate_urls", [])
    extracted: List[ProductSpec] = []

    # Process up to 5 top candidates to balance depth and speed
    for item in candidates[:5]:
        url = item.get("url", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")

        # Try fetching full markdown page via Jina Reader
        raw_md = fetch_page_content(url, timeout=10.0)
        product = parse_page_to_product(url, title, snippet, raw_md)

        # Only retain products with identifiable names
        if product.name and len(product.name) > 3:
            extracted.append(product)

    logs = list(state.get("logs", []))
    logs.append(f"Product extractor processed {len(extracted)} products with specs and BDT prices.")

    return {
        **state,
        "extracted_products": extracted,
        "logs": logs,
    }

