from typing import Dict, List, Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field


class UserRequirement(BaseModel):
    """Parsed user shopping requirements across any product category."""
    category: str = Field(description="Product category, e.g. footwear, kitchen appliances, cosmetics, furniture, tech, etc.")
    budget_max: Optional[float] = Field(default=None, description="Maximum budget in BDT")
    budget_min: Optional[float] = Field(default=None, description="Minimum budget in BDT if specified")
    currency: str = Field(default="BDT", description="Currency symbol/code")
    location: str = Field(default="Bangladesh", description="Target region/country")
    usage_purposes: List[str] = Field(default_factory=list, description="Intended usage, preferences, or target application")
    priorities: List[str] = Field(default_factory=list, description="Feature priorities sorted by importance")
    must_have_specs: List[str] = Field(default_factory=list, description="Specific must-have requirements, attributes, or features")
    preferred_stores: List[str] = Field(default_factory=list, description="Stores to filter by (empty means open web across all stores)")
    detected_language: str = Field(default="en", description="Language detected: en, bn, or banglish")


class StoreOffer(BaseModel):
    """Offer from an individual store for a canonical product."""
    model_config = {"extra": "ignore"}
    id: Optional[int] = None
    store_name: str = "Store"
    price_bdt: float = 0.0
    regular_price_bdt: Optional[float] = None
    url: str = ""
    product_url: Optional[str] = None
    in_stock: bool = True
    warranty: Optional[str] = None
    last_checked_at: Optional[str] = None

    def __init__(self, **data):
        super().__init__(**data)
        if not self.url and self.product_url:
            self.url = self.product_url


class ProductSpec(BaseModel):
    """Normalized canonical product data with multi-seller store offers."""
    id: Optional[int] = None
    name: str
    brand: Optional[str] = None
    price: Optional[float] = None  # Lowest in-stock price
    currency: str = "BDT"
    store: str = "Multiple Sellers"
    url: str
    image_url: Optional[str] = None
    specs: Dict[str, str] = Field(default_factory=dict)
    pros: List[str] = Field(default_factory=list)
    cons: List[str] = Field(default_factory=list)
    warranty: Optional[str] = None
    is_official: Optional[bool] = None
    in_stock: Optional[bool] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    raw_snippet: Optional[str] = None
    offers: List[StoreOffer] = Field(default_factory=list, description="All competing store offers")
    lowest_price: Optional[float] = None
    highest_price: Optional[float] = None
    savings: Optional[float] = None


class RecommendationCard(BaseModel):
    """Curated recommendation card with purchase advice and trade-offs."""
    rank: int
    product: ProductSpec
    verdict: str  # e.g., "Top Pick", "Best Value", "Alternative Option"
    score: float = Field(description="Value rating from 1.0 to 10.0")
    why_buy: List[str] = Field(default_factory=list)
    why_not_buy: List[str] = Field(default_factory=list)
    who_should_buy: str = ""
    buyer_advice: Optional[str] = None
    bangladesh_note: Optional[str] = None
    best_seller: Optional[str] = None
    savings_text: Optional[str] = None


class ShoppingAgentState(TypedDict, total=False):
    """LangGraph execution state."""
    user_query: str
    requirements: Optional[UserRequirement]
    search_queries: List[str]
    candidate_urls: List[Dict[str, str]]
    extracted_products: List[ProductSpec]
    recommendations: List[RecommendationCard]
    comparison_summary: str
    final_answer: str
    logs: List[str]

