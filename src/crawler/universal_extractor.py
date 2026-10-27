import re
import json
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup


NON_PRICE_UNITS = (
    r"(?:rpm|mah|dpi|hz|mhz|ghz|watt|watts|w|k|mb|gb|tb|kb|v|volt|volts|amp|amps|"
    r"hour|hours|hr|hrs|kg|g|gm|gms|mg|ml|l|liter|liters|oz|mm|cm|meter|m|inch|inches|"
    r"ft|yard|gsm|fps|cd/m2|nit|nits|pixels|px|core|cores|threads|pack|pcs|count|size|sizes)"
)


class UniversalProductExtractor:
    """
    100% store-agnostic product data extractor.
    Extracts structured e-commerce data using Schema.org JSON-LD, Microdata, OpenGraph,
    and semantic HTML heuristics across any Bangladeshi shopping website.
    """

    @classmethod
    def clean_title(cls, title: str) -> str:
        """Strip SEO boilerplate, seller names, and price tails from title."""
        if not title:
            return ""
        clean = title.strip()
        # Remove seller prefixes or suffixes separated by pipe, dash, or colon
        clean = re.sub(r"\s*\|\s*.*$", "", clean)
        clean = re.sub(r"\s*-\s*(?:Buy Online|Price in BD|Lowest Price|Best Price|Daraz|Star Tech|Ryans|Pickaboo|Techland|Apex|Bata|Aarong|Walton|Singer).*$", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\b(?:price in bangladesh|price in bd|buy online|lowest price in bd|lowest price in bangladesh|best price in bd|official price|bd price|202\d)\b.*$", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s*[-|:]\s*$", "", clean)
        return clean.strip(" -|:\t\n")

    @classmethod
    def extract_price_from_text(cls, text: str) -> Optional[float]:
        """Strict price extractor preventing technical specs (e.g. 18000 RPM, 5000 mAh) from matching."""
        if not text:
            return None

        # Check for out of stock signals
        if re.search(r"\b(?:out of stock|to be announced|tba|upcoming|discontinued|sold out|call for price)\b", text, re.IGNORECASE):
            return None

        # Pattern 1: Digits followed by BDT/Tk/৳ symbol (e.g. '115,000৳', '45,000 BDT', '2,400 Tk')
        m1 = re.search(r"([\d,]{2,9}(?:\.\d{1,2})?)\s*(?:৳|tk\.?|bdt|taka)(?!\s*" + NON_PRICE_UNITS + r"\b)", text, re.IGNORECASE)
        if m1:
            try:
                val = float(m1.group(1).replace(",", ""))
                if 50 <= val <= 15000000:
                    return val
            except ValueError:
                pass

        # Pattern 2: Currency symbol followed by digits (e.g. '৳ 115,000', 'Tk 45,000', 'BDT 46,999')
        m2 = re.search(r"(?:৳|tk\.?|bdt)\s*[:.-]?\s*([\d,]{2,9}(?:\.\d{1,2})?)(?!\s*" + NON_PRICE_UNITS + r"\b)", text, re.IGNORECASE)
        if m2:
            try:
                val = float(m2.group(1).replace(",", ""))
                if 50 <= val <= 15000000:
                    return val
            except ValueError:
                pass

        # Pattern 3: Explicit price label
        m3 = re.search(r"\b(?:regular price|special price|cash discount price|cash price|sale price|price|discounted price)\s*[:.-]?\s*([\d,]{2,9}(?:\.\d{1,2})?)(?!\s*" + NON_PRICE_UNITS + r"\b)", text, re.IGNORECASE)
        if m3:
            try:
                val = float(m3.group(1).replace(",", ""))
                if 50 <= val <= 15000000:
                    return val
            except ValueError:
                pass

        return None

    @classmethod
    def detect_category(cls, title: str, breadcrumb_text: str = "") -> str:
        """Infer high-level category neutrally from product title and breadcrumbs."""
        text = f"{title} {breadcrumb_text}".lower()
        if any(k in text for k in ["laptop", "notebook", "ultrabook", "macbook"]):
            return "laptop"
        if any(k in text for k in ["smartphone", "phone", "mobile", "iphone", "galaxy"]):
            return "smartphone"
        if any(k in text for k in ["monitor", "display", "gaming monitor"]):
            return "monitor"
        if any(k in text for k in ["shoe", "sneaker", "boot", "sandal", "footwear", "loafer"]):
            return "footwear"
        if any(k in text for k in ["shirt", "t-shirt", "pant", "jacket", "hoodie", "panjabi", "dress", "saree"]):
            return "clothing"
        if any(k in text for k in ["air fryer", "blender", "oven", "cooker", "kettle", "pot", "refrigerator", "fridge"]):
            return "kitchen appliance"
        if any(k in text for k in ["headphone", "earbuds", "earphone", "speaker", "soundbar", "smartwatch", "keyboard", "mouse"]):
            return "gadgets"
        if any(k in text for k in ["chair", "desk", "table", "sofa", "bed", "furniture"]):
            return "furniture"
        if any(k in text for k in ["perfume", "serum", "sunscreen", "lotion", "cream", "shampoo", "trimmer"]):
            return "beauty & personal care"
        return "general"

    @classmethod
    def detect_warranty(cls, text: str) -> Optional[str]:
        """Detect warranty terms in Bangladesh retail context."""
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
        return "Standard Retail Warranty"

    @classmethod
    def extract_from_html(cls, html_content: str, url: str) -> Dict[str, Any]:
        """
        Extract all product attributes from raw HTML string.
        Returns a dictionary with standardized keys:
        {
            "name": str,
            "brand": Optional[str],
            "price_bdt": Optional[float],
            "regular_price_bdt": Optional[float],
            "in_stock": bool,
            "category": str,
            "warranty": Optional[str],
            "specs": Dict[str, str],
            "image_url": Optional[str],
            "model_number": Optional[str],
        }
        """
        result: Dict[str, Any] = {
            "name": None,
            "brand": None,
            "price_bdt": None,
            "regular_price_bdt": None,
            "in_stock": True,
            "category": "general",
            "warranty": "Standard Retail Warranty",
            "specs": {},
            "image_url": None,
            "model_number": None,
        }

        if not html_content:
            return result

        soup = BeautifulSoup(html_content, "html.parser")

        # ----------------------------------------------------
        # TIER 1: Schema.org JSON-LD Extraction
        # ----------------------------------------------------
        for script in soup.find_all("script", type="application/ld+json"):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else data.get("@graph", [data])
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if item.get("@type") in ["Product", "IndividualProduct"]:
                        if item.get("name") and not result["name"]:
                            result["name"] = cls.clean_title(str(item["name"]))
                        if item.get("brand") and not result["brand"]:
                            b = item["brand"]
                            result["brand"] = b.get("name") if isinstance(b, dict) else str(b)
                        if item.get("image") and not result["image_url"]:
                            img = item["image"]
                            if isinstance(img, list) and img:
                                result["image_url"] = img[0]
                            elif isinstance(img, str):
                                result["image_url"] = img
                        if item.get("model") and not result["model_number"]:
                            result["model_number"] = str(item["model"])

                        # Offers
                        offers = item.get("offers")
                        if isinstance(offers, list) and offers:
                            offers = offers[0]
                        if isinstance(offers, dict):
                            if offers.get("price") and not result["price_bdt"]:
                                try:
                                    val = float(str(offers["price"]).replace(",", ""))
                                    if 50 <= val <= 15000000:
                                        result["price_bdt"] = val
                                except ValueError:
                                    pass
                            avail = str(offers.get("availability", "")).lower()
                            if "outofstock" in avail or "soldout" in avail:
                                result["in_stock"] = False
                            elif "instock" in avail:
                                result["in_stock"] = True

                        # Additional properties
                        for prop in item.get("additionalProperty", []):
                            if isinstance(prop, dict) and prop.get("name") and prop.get("value"):
                                result["specs"][str(prop["name"]).strip()] = str(prop["value"]).strip()
            except Exception:
                continue

        # ----------------------------------------------------
        # TIER 2: OpenGraph & Microdata Fallback
        # ----------------------------------------------------
        # Title
        if not result["name"]:
            og_title = soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"name": "og:title"})
            h1 = soup.find("h1")
            title_tag = soup.title.get_text(strip=True) if soup.title else None
            raw_title = (og_title.get("content") if og_title else None) or (h1.get_text(strip=True) if h1 else None) or title_tag
            if raw_title:
                result["name"] = cls.clean_title(raw_title)

        # Image
        if not result["image_url"]:
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                result["image_url"] = og_img["content"]
            else:
                main_img = soup.select_one(".product-image img, .p-item-img img, #image, .main-image img, [itemprop='image']")
                if main_img and main_img.get("src"):
                    result["image_url"] = urljoin(url, main_img["src"])

        # Price
        if not result["price_bdt"]:
            og_price = soup.find("meta", property="product:price:amount") or soup.find("meta", property="og:price:amount")
            if og_price and og_price.get("content"):
                try:
                    p = float(str(og_price["content"]).replace(",", ""))
                    if 50 <= p <= 15000000:
                        result["price_bdt"] = p
                except ValueError:
                    pass

        # ----------------------------------------------------
        # TIER 3: HTML DOM Heuristics for Price, Stock, Specs
        # ----------------------------------------------------
        # Stock detection from text/badges
        stock_badge = soup.find(class_=re.compile(r"stock|availability|status", re.IGNORECASE))
        stock_text = stock_badge.get_text(strip=True) if stock_badge else ""
        if re.search(r"\b(?:out of stock|to be announced|tba|upcoming|discontinued|sold out|stock out)\b", stock_text, re.IGNORECASE):
            result["in_stock"] = False

        # Regular vs Cash Price in DOM
        if not result["price_bdt"]:
            price_elem = (
                soup.find(attrs={"itemprop": "price"}) or
                soup.find("ins") or
                soup.find(class_=re.compile(r"price-new|product-price|sale-price|current-price|p-price|special-price", re.IGNORECASE)) or
                soup.find(class_=re.compile(r"price", re.IGNORECASE))
            )
            if price_elem:
                p_val = cls.extract_price_from_text(price_elem.get_text(strip=True))
                if p_val:
                    result["price_bdt"] = p_val

        # Regular (Old) Price
        old_price_elem = soup.find("del") or soup.find(class_=re.compile(r"price-old|regular-price|old-price|strike", re.IGNORECASE))
        if old_price_elem:
            old_p = cls.extract_price_from_text(old_price_elem.get_text(strip=True))
            if old_p:
                result["regular_price_bdt"] = old_p

        # Universal Specs from HTML Tables and Lists
        spec_containers = soup.select("table.data-table, table.specification, .specification-table, table, dl, .product-attributes")
        for container in spec_containers:
            for row in container.find_all("tr"):
                cols = row.find_all(["th", "td"])
                if len(cols) == 2:
                    k = cols[0].get_text(strip=True)
                    v = cols[1].get_text(strip=True)
                    if 2 <= len(k) <= 40 and 2 <= len(v) <= 150:
                        result["specs"][k] = v

        # Breadcrumbs for category
        bc = soup.find(class_=re.compile(r"breadcrumb", re.IGNORECASE))
        bc_text = bc.get_text(" ", strip=True) if bc else ""
        result["category"] = cls.detect_category(result["name"] or "", bc_text)

        # Warranty text check
        page_text = soup.get_text(" ", strip=True)[:5000]
        result["warranty"] = cls.detect_warranty(page_text)

        # Model number heuristic from title
        if not result["model_number"] and result["name"]:
            model_match = re.search(r"\b([A-Z0-9]{3,10}-[A-Z0-9]{2,10}|[A-Z]{2,4}\d{3,5}[A-Z]?)\b", result["name"])
            if model_match:
                result["model_number"] = model_match.group(1)

        return result
