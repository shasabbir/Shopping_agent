import os
import re
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    desc,
    or_,
    and_,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, scoped_session, backref

Base = declarative_base()


def utc_now() -> datetime:
    """Return naive UTC datetime for universal SQLite and PostgreSQL compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    base_url = Column(String(500), unique=True, nullable=False)
    sitemap_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    crawl_frequency_hours = Column(Integer, default=12)
    last_crawled_at = Column(DateTime, nullable=True)
    total_products_found = Column(Integer, default=0)
    status = Column(String(50), default="idle")  # 'idle', 'crawling', 'completed', 'error'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    offers = relationship("Offer", back_populates="store", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "base_url": self.base_url,
            "sitemap_url": self.sitemap_url,
            "is_active": self.is_active,
            "crawl_frequency_hours": self.crawl_frequency_hours,
            "last_crawled_at": self.last_crawled_at.isoformat() if self.last_crawled_at else None,
            "total_products_found": self.total_products_found,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    canonical_name = Column(String(500), nullable=False, index=True)
    brand = Column(String(100), nullable=True, index=True)
    category = Column(String(100), nullable=False, index=True)
    model_number = Column(String(100), nullable=True, index=True)
    normalized_specs_json = Column(Text, default="{}")
    primary_image_url = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    offers = relationship("Offer", back_populates="product", cascade="all, delete-orphan")

    @property
    def specs(self) -> Dict[str, Any]:
        try:
            return json.loads(self.normalized_specs_json or "{}")
        except Exception:
            return {}

    @specs.setter
    def specs(self, val: Dict[str, Any]):
        self.normalized_specs_json = json.dumps(val or {})

    def to_dict(self, include_offers: bool = True) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "canonical_name": self.canonical_name,
            "brand": self.brand,
            "category": self.category,
            "model_number": self.model_number,
            "specs": self.specs,
            "primary_image_url": self.primary_image_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_offers:
            data["offers"] = [o.to_dict() for o in self.offers]
            # Computed lowest price among in-stock offers
            in_stock_prices = [o.price_bdt for o in self.offers if o.price_bdt and o.in_stock]
            data["lowest_price"] = min(in_stock_prices) if in_stock_prices else None
            data["offers_count"] = len(self.offers)
        return data


class Offer(Base):
    __tablename__ = "offers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)
    store_product_title = Column(String(500), nullable=False)
    product_url = Column(String(1000), unique=True, nullable=False)
    price_bdt = Column(Float, nullable=False, index=True)
    regular_price_bdt = Column(Float, nullable=True)
    in_stock = Column(Boolean, default=True, index=True)
    warranty = Column(String(255), nullable=True)
    raw_specs_json = Column(Text, default="{}")
    image_url = Column(String(1000), nullable=True)
    last_checked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    product = relationship("Product", back_populates="offers")
    store = relationship("Store", back_populates="offers")
    price_history = relationship("PriceHistory", back_populates="offer", cascade="all, delete-orphan")

    @property
    def specs(self) -> Dict[str, Any]:
        try:
            return json.loads(self.raw_specs_json or "{}")
        except Exception:
            return {}

    @specs.setter
    def specs(self, val: Dict[str, Any]):
        self.raw_specs_json = json.dumps(val or {})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "store_id": self.store_id,
            "store_name": self.store.name if self.store else "Store",
            "store_product_title": self.store_product_title,
            "product_url": self.product_url,
            "price_bdt": self.price_bdt,
            "regular_price_bdt": self.regular_price_bdt,
            "in_stock": self.in_stock,
            "warranty": self.warranty,
            "specs": self.specs,
            "image_url": self.image_url,
            "last_checked_at": self.last_checked_at.isoformat() if self.last_checked_at else None,
        }


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True)
    price_bdt = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    offer = relationship("Offer", back_populates="price_history")


class CrawlFrontier(Base):
    __tablename__ = "crawl_frontier"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String(1000), unique=True, nullable=False, index=True)
    url_type = Column(String(50), default="product")  # 'sitemap', 'category', 'product'
    priority = Column(Integer, default=10, index=True)  # 0: product, 10: category, 20: sitemap
    status = Column(String(50), default="pending", index=True)  # 'pending', 'in_progress', 'completed', 'failed', 'dead'
    depth = Column(Integer, default=0)
    requires_browser = Column(Boolean, default=False)
    retry_count = Column(Integer, default=0)
    http_status = Column(Integer, nullable=True)
    last_error = Column(Text, nullable=True)
    next_eligible_at = Column(DateTime, default=utc_now, index=True)
    last_crawled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    store = relationship("Store", backref=backref("frontier_items", cascade="all, delete-orphan"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "store_id": self.store_id,
            "store_name": self.store.name if self.store else "Store",
            "url": self.url,
            "url_type": self.url_type,
            "priority": self.priority,
            "status": self.status,
            "depth": self.depth,
            "requires_browser": self.requires_browser,
            "retry_count": self.retry_count,
            "http_status": self.http_status,
            "last_error": self.last_error,
            "next_eligible_at": self.next_eligible_at.isoformat() if self.next_eligible_at else None,
            "last_crawled_at": self.last_crawled_at.isoformat() if self.last_crawled_at else None,
        }


# 25 Default Bangladesh Stores
DEFAULT_BANGLADESH_STORES = [
    {"name": "Star Tech", "base_url": "https://www.startech.com.bd", "sitemap_url": "https://www.startech.com.bd/sitemap.xml"},
    {"name": "Ryans Computers", "base_url": "https://www.ryans.com", "sitemap_url": "https://www.ryans.com/sitemap.xml"},
    {"name": "TechLand BD", "base_url": "https://www.techlandbd.com", "sitemap_url": "https://www.techlandbd.com/sitemaps/product-sitemap-1.xml"},
    {"name": "Pickaboo", "base_url": "https://www.pickaboo.com", "sitemap_url": "https://www.pickaboo.com/product/smartphone"},
    {"name": "Daraz Bangladesh", "base_url": "https://www.daraz.com.bd", "sitemap_url": "https://www.daraz.com.bd/sitemap.xml"},
    {"name": "Apple Gadgets BD", "base_url": "https://www.applegadgetsbd.com", "sitemap_url": "https://www.applegadgetsbd.com/product/sitemap.xml"},
    {"name": "Gadget & Gear", "base_url": "https://gadgetandgear.com", "sitemap_url": "https://gadgetandgear.com/sitemap.xml"},
    {"name": "Skyland BD", "base_url": "https://www.skyland.com.bd", "sitemap_url": "https://www.skyland.com.bd/sitemap.xml"},
    {"name": "Custom Mac BD", "base_url": "https://custommacbd.com", "sitemap_url": "https://custommacbd.com/sitemap.xml"},
    {"name": "BDStall", "base_url": "https://www.bdstall.com", "sitemap_url": "https://www.bdstall.com/monitor/"},
    {"name": "Vibe Gaming", "base_url": "https://vibegaming.com.bd", "sitemap_url": "https://vibegaming.com.bd/product-sitemap1.xml"},
    {"name": "Walton Plaza", "base_url": "https://waltonbd.com", "sitemap_url": "https://waltonbd.com/sitemap.xml"},
    {"name": "Singer Bangladesh", "base_url": "https://www.singerbd.com", "sitemap_url": "https://www.singerbd.com/sitemap.xml"},
    {"name": "Transcom Digital", "base_url": "https://transcomdigital.com", "sitemap_url": "https://transcomdigital.com/sitemap.xml"},
    {"name": "Butterfly Group", "base_url": "https://butterflygroupbd.com", "sitemap_url": "https://butterflygroupbd.com/sitemap.xml"},
    {"name": "Apex Footwear", "base_url": "https://apex4u.com", "sitemap_url": "https://apex4u.com/sitemap_products.xml"},
    {"name": "Bata Bangladesh", "base_url": "https://www.batabd.com", "sitemap_url": "https://www.batabd.com/sitemap.xml"},
    {"name": "Lotto Bangladesh", "base_url": "https://www.lottobd.com", "sitemap_url": "https://lottobd.com/sitemap.xml"},
    {"name": "Aarong", "base_url": "https://www.aarong.com", "sitemap_url": "https://www.aarong.com/bgd/men/panjabi"},
    {"name": "Rokomari", "base_url": "https://www.rokomari.com", "sitemap_url": "https://www.rokomari.com/sitemap.xml"},
    {"name": "Othoba", "base_url": "https://www.othoba.com", "sitemap_url": None},
    {"name": "Chaldal", "base_url": "https://chaldal.com", "sitemap_url": "https://chaldal.com/sitemap.xml"},
    {"name": "Shwapno", "base_url": "https://www.shwapno.com", "sitemap_url": "https://www.shwapno.com/sitemap.xml"},
    {"name": "Potaka BD", "base_url": "https://potakait.com", "sitemap_url": "https://potakait.com/sitemap.xml"},
    {"name": "UCC BD", "base_url": "https://www.ucc.com.bd", "sitemap_url": "https://www.ucc.com.bd/sitemaps/product-sitemap.xml"},
]


# Database Connection Manager
_engine = None
_SessionFactory = None


def get_db_url() -> str:
    """Return database URL from environment or fallback to SQLite."""
    pg_url = os.getenv("DATABASE_URL")
    if pg_url and (pg_url.startswith("postgresql://") or pg_url.startswith("postgres://")):
        return pg_url
    # Local fallback SQLite database
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shopping_agent.db")
    return f"sqlite:///{db_path}"


def get_engine():
    global _engine
    if _engine is None:
        url = get_db_url()
        try:
            if url.startswith("sqlite"):
                _engine = create_engine(url, connect_args={"check_same_thread": False})
            else:
                _engine = create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)
        except Exception as e:
            print(f"[Database] Failed to connect to primary DB ({url}): {e}. Falling back to SQLite.")
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shopping_agent.db")
            _engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    return _engine


def get_session():
    global _SessionFactory
    if _SessionFactory is None:
        engine = get_engine()
        _SessionFactory = scoped_session(sessionmaker(bind=engine))
    return _SessionFactory()


def init_db():
    """Create all tables and seed default stores if empty."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    seed_default_stores()


def seed_default_stores():
    """Populate or update default 25 Bangladesh stores."""
    session = get_session()
    try:
        for s in DEFAULT_BANGLADESH_STORES:
            existing = session.query(Store).filter(
                (Store.name == s["name"]) | (Store.base_url == s["base_url"])
            ).first()
            if not existing:
                store_obj = Store(
                    name=s["name"],
                    base_url=s["base_url"],
                    sitemap_url=s.get("sitemap_url"),
                    is_active=True,
                    status="idle",
                )
                session.add(store_obj)
            else:
                existing.name = s["name"]
                existing.base_url = s["base_url"]
                existing.sitemap_url = s.get("sitemap_url")
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"[Database] Seed stores warning: {e}")
    finally:
        session.close()


# Store Management Functions
def get_all_stores() -> List[Dict[str, Any]]:
    session = get_session()
    try:
        stores = session.query(Store).order_by(Store.id.asc()).all()
        return [s.to_dict() for s in stores]
    finally:
        session.close()


def get_active_stores() -> List[Dict[str, Any]]:
    session = get_session()
    try:
        stores = session.query(Store).filter(Store.is_active == True).order_by(Store.id.asc()).all()
        return [s.to_dict() for s in stores]
    finally:
        session.close()


def add_or_update_store(name: str, base_url: str, sitemap_url: Optional[str] = None, is_active: bool = True) -> Dict[str, Any]:
    session = get_session()
    try:
        base_clean = base_url.strip().rstrip("/")
        store = session.query(Store).filter(Store.base_url == base_clean).first()
        if not store:
            store = Store(name=name.strip(), base_url=base_clean, sitemap_url=sitemap_url.strip() if sitemap_url else None, is_active=is_active)
            session.add(store)
        else:
            store.name = name.strip()
            if sitemap_url:
                store.sitemap_url = sitemap_url.strip()
            store.is_active = is_active
        session.commit()
        return store.to_dict()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def toggle_store_active(store_id: int) -> bool:
    session = get_session()
    try:
        store = session.query(Store).filter(Store.id == store_id).first()
        if store:
            store.is_active = not store.is_active
            session.commit()
            return store.is_active
        return False
    finally:
        session.close()


def delete_store(store_id: int) -> bool:
    session = get_session()
    try:
        store = session.query(Store).filter(Store.id == store_id).first()
        if store:
            session.delete(store)
            session.commit()
            return True
        return False
    finally:
        session.close()


def update_store_crawl_status(store_id: int, status: str, total_found_delta: int = 0):
    session = get_session()
    try:
        store = session.query(Store).filter(Store.id == store_id).first()
        if store:
            store.status = status
            store.last_crawled_at = datetime.now(timezone.utc)
            if total_found_delta:
                store.total_products_found = (store.total_products_found or 0) + total_found_delta
            session.commit()
    except Exception as e:
        session.rollback()
    finally:
        session.close()


# Product and Offer Upsert with Canonical Matching
def normalize_model_key(title: str) -> str:
    """Extract a canonical normalized key from product title for cross-store clustering."""
    t = re.sub(r"[^a-zA-Z0-9\s]", " ", title.lower())
    words = [w for w in t.split() if len(w) > 1 and w not in ["laptop", "phone", "mobile", "gaming", "price", "bd", "bangladesh", "buy", "online", "official", "unofficial"]]
    return " ".join(words[:6])


def upsert_crawled_offer(
    store_id: int,
    store_product_title: str,
    product_url: str,
    price_bdt: float,
    category: str = "general",
    brand: Optional[str] = None,
    regular_price_bdt: Optional[float] = None,
    in_stock: bool = True,
    warranty: Optional[str] = None,
    specs: Optional[Dict[str, Any]] = None,
    image_url: Optional[Any] = None,
    model_number: Optional[str] = None,
) -> Tuple[int, int]:
    """
    Matches candidate against existing canonical products or creates a new one,
    then creates or updates the offer and records price history.
    Returns (product_id, offer_id).
    """
    if isinstance(image_url, dict):
        image_url = image_url.get("contentUrl") or image_url.get("url") or image_url.get("thumbnailUrl") or ""
    elif isinstance(image_url, list) and image_url:
        image_url = str(image_url[0])
    elif image_url is not None:
        image_url = str(image_url)

    session = get_session()
    try:
        norm_key = normalize_model_key(store_product_title)
        
        # 1. Check if offer already exists by exact URL
        existing_offer = session.query(Offer).filter(Offer.product_url == product_url).first()
        
        if existing_offer:
            product = existing_offer.product
            # Check price change for history
            old_price = existing_offer.price_bdt
            existing_offer.price_bdt = price_bdt
            existing_offer.regular_price_bdt = regular_price_bdt or existing_offer.regular_price_bdt
            existing_offer.in_stock = in_stock
            existing_offer.last_checked_at = datetime.now(timezone.utc)
            if warranty:
                existing_offer.warranty = warranty
            if specs:
                existing_offer.specs = specs
            if image_url:
                existing_offer.image_url = image_url

            if old_price != price_bdt:
                ph = PriceHistory(offer_id=existing_offer.id, price_bdt=price_bdt)
                session.add(ph)

            session.commit()
            return product.id, existing_offer.id

        # 2. Match with existing Canonical Product
        product = None
        # Strategy A: Check model_number if available
        if model_number and len(model_number) >= 3:
            product = session.query(Product).filter(
                Product.model_number.ilike(f"%{model_number}%")
            ).first()

        # Strategy B: Intelligent cross-store token overlap matching
        if not product:
            STOP_WORDS = {"laptop", "phone", "mobile", "gaming", "price", "bd", "bangladesh", "buy", "online", "official", "unofficial", "in", "for", "with", "and", "the", "edition"}
            new_tokens = set(re.findall(r"[a-z0-9]+", store_product_title.lower())) - STOP_WORDS
            
            # Fetch candidate products in same category or matching brand
            candidate_query = session.query(Product)
            if category and category != "general":
                candidate_query = candidate_query.filter(Product.category == category)
            if brand:
                candidate_query = candidate_query.filter(Product.brand.ilike(f"%{brand}%"))
            
            candidates = candidate_query.limit(50).all()
            best_match = None
            best_score = 0.0

            for cand in candidates:
                cand_tokens = set(re.findall(r"[a-z0-9]+", cand.canonical_name.lower())) - STOP_WORDS
                if not cand_tokens:
                    continue
                intersection = new_tokens & cand_tokens
                union = new_tokens | cand_tokens
                jaccard = len(intersection) / len(union) if union else 0.0
                
                # Check for critical tokens (brand + model/spec signature)
                brand_match = (brand and cand.brand and brand.lower() == cand.brand.lower()) or (brand and brand.lower() in cand_tokens)
                
                # Match threshold: high Jaccard OR (same brand and at least 3 matching spec/model tokens)
                if (jaccard >= 0.40) or (brand_match and len(intersection) >= 3):
                    if jaccard > best_score:
                        best_score = jaccard
                        best_match = cand

            if best_match:
                product = best_match

        # 3. If no matching canonical product, create one
        if not product:
            product = Product(
                canonical_name=store_product_title,
                brand=brand,
                category=category,
                model_number=model_number,
                primary_image_url=image_url,
            )
            if specs:
                product.specs = specs
            session.add(product)
            session.flush()

        # 4. Create new Offer
        new_offer = Offer(
            product_id=product.id,
            store_id=store_id,
            store_product_title=store_product_title,
            product_url=product_url,
            price_bdt=price_bdt,
            regular_price_bdt=regular_price_bdt,
            in_stock=in_stock,
            warranty=warranty,
            image_url=image_url,
        )
        if specs:
            new_offer.specs = specs

        session.add(new_offer)
        session.flush()

        # Initial price history entry
        ph = PriceHistory(offer_id=new_offer.id, price_bdt=price_bdt)
        session.add(ph)

        # Update store stats
        store = session.query(Store).filter(Store.id == store_id).first()
        if store:
            store.total_products_found = (store.total_products_found or 0) + 1

        session.commit()
        return product.id, new_offer.id

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def search_catalog(
    query_text: str,
    category: Optional[str] = None,
    budget_max: Optional[float] = None,
    budget_min: Optional[float] = None,
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """
    Search catalog across canonical products and attach all available store offers.
    Supports token matching, category filtering, and budget boundaries.
    """
    session = get_session()
    try:
        # Build query
        q = session.query(Product)

        if category and category.lower() not in ["general", "all"]:
            q = q.filter(Product.category.ilike(f"%{category.lower()}%"))

        # Clean search tokens
        clean_text = re.sub(r"[^a-zA-Z0-9\s]", " ", query_text.lower()).strip()
        tokens = [t for t in clean_text.split() if len(t) > 2 and t not in ["under", "best", "price", "taka", "bdt", "tk", "bangladesh", "need", "want"]]

        if tokens:
            token_filters = []
            for t in tokens:
                token_filters.append(
                    or_(
                        Product.canonical_name.ilike(f"%{t}%"),
                        Product.brand.ilike(f"%{t}%"),
                        Product.model_number.ilike(f"%{t}%"),
                        Product.normalized_specs_json.ilike(f"%{t}%")
                    )
                )
            q = q.filter(and_(*token_filters))

        products = q.order_by(Product.updated_at.desc()).limit(limit * 2).all()

        results = []
        for p in products:
            p_dict = p.to_dict(include_offers=True)
            offers = p_dict.get("offers", [])

            # Filter offers by budget if specified
            if budget_max:
                valid_offers = [o for o in offers if o.get("price_bdt") and o.get("price_bdt") <= budget_max * 1.05]
            else:
                valid_offers = offers

            if budget_min:
                valid_offers = [o for o in valid_offers if o.get("price_bdt") and o.get("price_bdt") >= budget_min * 0.95]

            if valid_offers:
                # Sort offers with lowest price first
                valid_offers.sort(key=lambda o: (not o.get("in_stock", True), o.get("price_bdt", float("inf"))))
                p_dict["offers"] = valid_offers
                p_dict["lowest_price"] = valid_offers[0]["price_bdt"]
                results.append(p_dict)
            elif not budget_max and not budget_min and offers:
                p_dict["offers"].sort(key=lambda o: (not o.get("in_stock", True), o.get("price_bdt", float("inf"))))
                results.append(p_dict)

            if len(results) >= limit:
                break

        return results

    finally:
        session.close()


def get_catalog_stats() -> Dict[str, Any]:
    """Return overview metrics of database size and status."""
    session = get_session()
    try:
        total_stores = session.query(Store).count()
        active_stores = session.query(Store).filter(Store.is_active == True).count()
        total_products = session.query(Product).count()
        total_offers = session.query(Offer).count()
        in_stock_offers = session.query(Offer).filter(Offer.in_stock == True).count()
        latest_crawl = session.query(Store.last_crawled_at).filter(Store.last_crawled_at.isnot(None)).order_by(desc(Store.last_crawled_at)).first()

        return {
            "total_stores": total_stores,
            "active_stores": active_stores,
            "total_products": total_products,
            "total_offers": total_offers,
            "in_stock_offers": in_stock_offers,
            "latest_crawl": latest_crawl[0].isoformat() if latest_crawl and latest_crawl[0] else None,
        }
    finally:
        session.close()


# ----------------------------------------------------
# Crawl Frontier Queue Management
# ----------------------------------------------------
def ingest_frontier_urls(
    store_id: int,
    urls: List[str],
    url_type: str = "product",
    priority: int = 10,
    depth: int = 0,
    requires_browser: bool = False
) -> int:
    """Batch ingest URLs into crawl_frontier, ignoring duplicates. Returns count of newly inserted URLs."""
    if not urls:
        return 0
    session = get_session()
    inserted = 0
    try:
        clean_urls = list(dict.fromkeys(u.split("#")[0].strip() for u in urls if u and u.startswith("http")))
        existing_urls = set(
            u[0] for u in session.query(CrawlFrontier.url).filter(CrawlFrontier.url.in_(clean_urls)).all()
        )
        new_items = []
        for u in clean_urls:
            if u not in existing_urls:
                new_items.append(
                    CrawlFrontier(
                        store_id=store_id,
                        url=u,
                        url_type=url_type,
                        priority=priority,
                        depth=depth,
                        requires_browser=requires_browser,
                        status="pending"
                    )
                )
                existing_urls.add(u)
                inserted += 1
        if new_items:
            session.bulk_save_objects(new_items)
            session.commit()
        return inserted
    except Exception as e:
        session.rollback()
        print(f"[Database] Frontier ingest warning: {e}")
        return 0
    finally:
        session.close()


def pop_next_frontier_item(store_id: int) -> Optional[Dict[str, Any]]:
    """Fetch and lock the next eligible pending item for a specific store."""
    session = get_session()
    now_utc = utc_now()
    try:
        # Auto-recover stale in_progress items older than 10 minutes
        stale_threshold = now_utc - timedelta(minutes=10)
        session.query(CrawlFrontier).filter(
            CrawlFrontier.store_id == store_id,
            CrawlFrontier.status == "in_progress",
            CrawlFrontier.last_crawled_at < stale_threshold
        ).update({"status": "pending"}, synchronize_session=False)

        item = session.query(CrawlFrontier).filter(
            CrawlFrontier.store_id == store_id,
            CrawlFrontier.status == "pending",
            CrawlFrontier.next_eligible_at <= now_utc
        ).order_by(CrawlFrontier.priority.asc(), CrawlFrontier.id.asc()).first()
        if item:
            item.status = "in_progress"
            item.last_crawled_at = now_utc
            session.commit()
            return item.to_dict()
        session.commit()
        return None
    except Exception as e:
        session.rollback()
        print(f"[Database] Frontier pop error: {e}")
        return None
    finally:
        session.close()


def update_frontier_item_result(
    frontier_id: int,
    status: str,
    http_status: Optional[int] = None,
    error: Optional[str] = None,
    backoff_seconds: int = 0
):
    """Update status, http_status, error, and next retry time for a frontier item."""
    session = get_session()
    try:
        item = session.query(CrawlFrontier).filter(CrawlFrontier.id == frontier_id).first()
        if item:
            item.status = status
            if http_status is not None:
                item.http_status = http_status
            if error:
                item.last_error = str(error)[:500]
            if status == "failed":
                item.retry_count += 1
                if item.retry_count > 3:
                    item.status = "dead"
                else:
                    item.status = "pending"
                    item.next_eligible_at = utc_now() + timedelta(seconds=backoff_seconds or 120)
            session.commit()
    except Exception as e:
        session.rollback()
        print(f"[Database] Frontier update error: {e}")
    finally:
        session.close()


def get_frontier_metrics() -> Dict[str, Any]:
    """Return aggregated frontier queue health stats."""
    session = get_session()
    try:
        total = session.query(CrawlFrontier).count()
        pending = session.query(CrawlFrontier).filter(CrawlFrontier.status == "pending").count()
        in_progress = session.query(CrawlFrontier).filter(CrawlFrontier.status == "in_progress").count()
        completed = session.query(CrawlFrontier).filter(CrawlFrontier.status == "completed").count()
        failed = session.query(CrawlFrontier).filter(CrawlFrontier.status == "failed").count()
        dead = session.query(CrawlFrontier).filter(CrawlFrontier.status == "dead").count()

        # Per store breakdown
        store_records = [
            {"id": s.id, "name": s.name}
            for s in session.query(Store).filter(Store.is_active == True).order_by(Store.id.asc()).all()
        ]
        store_stats = []
        for s in store_records:
            s_pending = session.query(CrawlFrontier).filter(CrawlFrontier.store_id == s["id"], CrawlFrontier.status == "pending").count()
            s_completed = session.query(CrawlFrontier).filter(CrawlFrontier.store_id == s["id"], CrawlFrontier.status == "completed").count()
            store_stats.append({
                "store_id": s["id"],
                "store_name": s["name"],
                "pending": s_pending,
                "completed": s_completed,
            })

        return {
            "total_urls": total,
            "pending": pending,
            "in_progress": in_progress,
            "completed": completed,
            "failed": failed,
            "dead": dead,
            "store_stats": store_stats
        }
    finally:
        session.close()


def seed_frontier_from_stores(reset_dead: bool = True):
    """Ensure every active store has at least its sitemap or base_url in the frontier."""
    session = get_session()
    now_utc = utc_now()
    try:
        stores = [
            {"id": s.id, "name": s.name, "sitemap_url": s.sitemap_url, "base_url": s.base_url}
            for s in session.query(Store).filter(Store.is_active == True).all()
        ]

        for s in stores:
            seed_url = s["sitemap_url"] or s["base_url"]
            if not seed_url:
                continue
            clean_seed = seed_url.split("#")[0].strip()
            url_type = "sitemap" if (s["sitemap_url"] and ".xml" in s["sitemap_url"]) else "category"

            existing = session.query(CrawlFrontier).filter(CrawlFrontier.url == clean_seed).first()
            if existing:
                if reset_dead and existing.status in ["dead", "failed", "in_progress"]:
                    existing.status = "pending"
                    existing.retry_count = 0
                    existing.next_eligible_at = now_utc
                    existing.last_error = None
                    existing.http_status = None
            else:
                session.add(
                    CrawlFrontier(
                        store_id=s["id"],
                        url=clean_seed,
                        url_type=url_type,
                        priority=5 if url_type == "sitemap" else 10,
                        depth=0,
                        status="pending",
                        next_eligible_at=now_utc
                    )
                )
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"[Database] Error seeding frontier: {e}")
    finally:
        session.close()


def reset_failed_frontier_urls(store_id: Optional[int] = None, include_dead: bool = True) -> int:
    """Reset failed and optionally dead URLs back to pending state for retry."""
    session = get_session()
    now_utc = utc_now()
    try:
        statuses = ["failed", "dead"] if include_dead else ["failed"]
        query = session.query(CrawlFrontier).filter(CrawlFrontier.status.in_(statuses))
        if store_id:
            query = query.filter(CrawlFrontier.store_id == store_id)

        items = query.all()
        count = len(items)
        for item in items:
            item.status = "pending"
            item.retry_count = 0
            item.next_eligible_at = now_utc
            item.last_error = None
        session.commit()
        return count
    except Exception as e:
        session.rollback()
        print(f"[Database] Error resetting failed URLs: {e}")
        return 0
    finally:
        session.close()
