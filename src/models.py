from typing import Dict, List, Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field


class UserRequirement(BaseModel):
    """Parsed user shopping requirements."""
    category: str = Field(description="Product category, e.g. laptop, smartphone, monitor")
    budget_max: Optional[float] = Field(default=None, description="Maximum budget in BDT")
    budget_min: Optional[float] = Field(default=None, description="Minimum budget in BDT if specified")
    currency: str = Field(default="BDT", description="Currency symbol/code")
    location: str = Field(default="Bangladesh", description="Target region/country")
    usage_purposes: List[str] = Field(default_factory=list, description="Primary intended usage, e.g. gaming, coding, camera, battery")
    priorities: List[str] = Field(default_factory=list, description="Feature priorities sorted by importance")
    must_have_specs: List[str] = Field(default_factory=list, description="Specific must-have requirements, e.g. RTX 4060, 16GB RAM, OLED")
    preferred_stores: List[str] = Field(default_factory=lambda: ["Star Tech", "Ryans", "Daraz"], description="Stores to search")
    detected_language: str = Field(default="en", description="Language detected: en, bn, or banglish")


class ProductSpec(BaseModel):
    """Normalized product data extracted from retailer or web search."""
    name: str
    brand: Optional[str] = None
    price: Optional[float] = None
    currency: str = "BDT"
    store: str = "Unknown Store"
    url: str
    image_url: Optional[str] = None
    specs: Dict[str, str] = Field(default_factory=dict)
    pros: List[str] = Field(default_factory=list)
    cons: List[str] = Field(default_factory=list)
    warranty: Optional[str] = None
    is_official: Optional[bool] = None
    raw_snippet: Optional[str] = None


class RecommendationCard(BaseModel):
    """Curated recommendation card with purchase advice and trade-offs."""
    rank: int
    product: ProductSpec
    verdict: str  # e.g., "Top Pick", "Best Value", "Alternative Option"
    score: float = Field(description="Value rating from 1.0 to 10.0")
    why_buy: List[str] = Field(default_factory=list)
    why_not_buy: List[str] = Field(default_factory=list)
    who_should_buy: str = ""
    bangladesh_note: Optional[str] = None


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

