import os
import httpx
from typing import Optional

JINA_READER_BASE_URL = os.getenv("JINA_READER_BASE_URL", "https://r.jina.ai/")

# In-memory session cache for reader
_CACHE = {}

BOT_CHALLENGE_KEYWORDS = [
    "performing security verification",
    "just a moment...",
    "cloudflare",
    "requiring captcha",
    "please turn javascript on",
    "access denied",
    "attention required! | cloudflare",
]


def fetch_page_content(url: str, timeout: float = 12.0, max_chars: int = 4000) -> Optional[str]:
    """
    Fetch markdown content of any e-commerce page via Jina AI Reader.
    Detects and rejects bot-protected/CAPTCHA challenge pages so the agent can fall back safely.
    """
    if not url:
        return None

    if url in _CACHE:
        return _CACHE[url]

    endpoint = f"{JINA_READER_BASE_URL.rstrip('/')}/{url.strip()}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ShoppingAgent/1.0",
        "Accept": "text/markdown",
    }

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(endpoint, headers=headers)
            if response.status_code == 200 and response.text.strip():
                content = response.text.strip()
                content_lower = content.lower()

                # Detect if the target site returned a bot/captcha verification page
                if any(kw in content_lower for kw in BOT_CHALLENGE_KEYWORDS):
                    # Reject bot challenge pages
                    return None

                # Truncate to avoid blowing up context window with irrelevant footer links
                if len(content) > max_chars:
                    content = content[:max_chars] + "\n\n...[Page truncated for analysis]..."
                _CACHE[url] = content
                return content
    except Exception as e:
        pass

    return None

