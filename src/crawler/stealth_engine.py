import os
import math
import time
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlparse


class StealthPersona:
    """Coherent browser identity bundle (TLS fingerprint, UA, Client Hints)."""
    def __init__(
        self,
        name: str,
        tls_impersonate: str,
        user_agent: str,
        sec_ch_ua: str,
        sec_ch_ua_platform: str,
        sec_ch_ua_mobile: str = "?0"
    ):
        self.name = name
        self.tls_impersonate = tls_impersonate
        self.user_agent = user_agent
        self.sec_ch_ua = sec_ch_ua
        self.sec_ch_ua_platform = sec_ch_ua_platform
        self.sec_ch_ua_mobile = sec_ch_ua_mobile

    def get_headers(self, target_url: Optional[str] = None) -> Dict[str, str]:
        parsed = urlparse(target_url) if target_url else None
        origin = f"{parsed.scheme}://{parsed.netloc}" if parsed and parsed.netloc else "https://www.google.com"

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9,bn;q=0.8",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Sec-Ch-Ua": self.sec_ch_ua,
            "Sec-Ch-Ua-Mobile": self.sec_ch_ua_mobile,
            "Sec-Ch-Ua-Platform": self.sec_ch_ua_platform,
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin" if parsed and parsed.netloc else "cross-site",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }
        if target_url and parsed and parsed.netloc:
            headers["Referer"] = f"{origin}/"
        return headers


class PersonaManager:
    """Maintains coherent persona pool preventing cross-fingerprint mismatches."""

    PERSONAS = [
        StealthPersona(
            name="Chrome 124 Windows",
            tls_impersonate="chrome124",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            sec_ch_ua='"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            sec_ch_ua_platform='"Windows"',
        ),
        StealthPersona(
            name="Edge 124 Windows",
            tls_impersonate="edge124",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
            sec_ch_ua='"Chromium";v="124", "Microsoft Edge";v="124", "Not-A.Brand";v="99"',
            sec_ch_ua_platform='"Windows"',
        ),
        StealthPersona(
            name="Chrome 120 macOS",
            tls_impersonate="chrome120",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            sec_ch_ua='"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            sec_ch_ua_platform='"macOS"',
        ),
        StealthPersona(
            name="Safari 17 macOS",
            tls_impersonate="safari17_0",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            sec_ch_ua='"Not A;Brand";v="99", "Safari";v="17"',
            sec_ch_ua_platform='"macOS"',
        ),
    ]

    @classmethod
    def get_random_persona(cls) -> StealthPersona:
        return random.choice(cls.PERSONAS)

    @classmethod
    def get_persona_for_store(cls, store_id: int) -> StealthPersona:
        """Deterministic persona assignment per store session to prevent flapping."""
        idx = store_id % len(cls.PERSONAS)
        return cls.PERSONAS[idx]


class AntiBotCadence:
    """
    Simulates organic human browsing cadence:
    1. Log-normal dwell times.
    2. Burst-and-read emulation.
    3. Bangladesh circadian day/night velocity scaling.
    """

    def __init__(self):
        self.request_counts: Dict[int, int] = {}
        self.burst_thresholds: Dict[int, int] = {}

    def calculate_delay(self, store_id: Optional[int] = None, speed_profile: str = "normal") -> float:
        """
        Calculate human-like log-normal delay in seconds.
        speed_profile: 'stealth' (4-10s), 'normal' (2-6s), 'turbo' (0.8-2.5s)
        """
        # Base log-normal parameters
        if speed_profile == "stealth":
            mu, sigma = 1.6, 0.35  # Median ~ 5.0s
            min_delay, max_delay = 3.0, 12.0
        elif speed_profile == "turbo":
            mu, sigma = 0.4, 0.25  # Median ~ 1.5s
            min_delay, max_delay = 0.8, 3.5
        else:  # normal
            mu, sigma = 1.1, 0.30  # Median ~ 3.0s
            min_delay, max_delay = 1.8, 7.5

        # Sample from log-normal distribution: e^(mu + sigma * Z)
        raw_delay = math.exp(random.gauss(mu, sigma))
        delay = max(min_delay, min(raw_delay, max_delay))

        # Check burst-and-read behavior per store
        if store_id is not None:
            self.request_counts[store_id] = self.request_counts.get(store_id, 0) + 1
            if store_id not in self.burst_thresholds:
                self.burst_thresholds[store_id] = random.randint(6, 9)
            if self.request_counts[store_id] >= self.burst_thresholds[store_id]:
                self.request_counts[store_id] = 0
                self.burst_thresholds[store_id] = random.randint(6, 9)
                reading_pause = random.uniform(15.0, 30.0)
                return reading_pause

        # Bangladesh Circadian Day/Night Modulation (UTC+6)
        # Scale delay up by 1.6x during night hours (02:00 - 07:00 BST)
        now_bst = datetime.now(timezone.utc) + timedelta(hours=6)
        if 2 <= now_bst.hour < 7:
            delay *= 1.6

        return round(delay, 2)


class StoreCircuitBreaker:
    """
    Independent per-store health tracker.
    Prevents slamming a host when it returns 429, 403, or 5xx without affecting other stores.
    """

    def __init__(self):
        # store_id -> {"failures": int, "cooldown_until": datetime, "mode": "http"|"browser", "consecutive_429": int}
        self.health_records: Dict[int, Dict[str, Any]] = {}

    def get_record(self, store_id: int) -> Dict[str, Any]:
        if store_id not in self.health_records:
            self.health_records[store_id] = {
                "failures": 0,
                "cooldown_until": datetime.now(timezone.utc),
                "mode": "http",
                "consecutive_429": 0,
                "last_success": None,
                "last_error": None
            }
        return self.health_records[store_id]

    def is_eligible(self, store_id: int) -> bool:
        """Check if store is currently out of cooldown."""
        rec = self.get_record(store_id)
        return datetime.now(timezone.utc) >= rec["cooldown_until"]

    def get_remaining_cooldown(self, store_id: int) -> int:
        rec = self.get_record(store_id)
        rem = (rec["cooldown_until"] - datetime.now(timezone.utc)).total_seconds()
        return max(0, int(rem))

    def record_success(self, store_id: int):
        rec = self.get_record(store_id)
        rec["failures"] = 0
        rec["consecutive_429"] = 0
        rec["cooldown_until"] = datetime.now(timezone.utc)
        rec["last_success"] = datetime.now(timezone.utc)
        rec["last_error"] = None

    def record_failure(self, store_id: int, status_code: Optional[int], error_msg: Optional[str] = None):
        rec = self.get_record(store_id)
        rec["failures"] += 1
        rec["last_error"] = error_msg or f"HTTP {status_code}"
        now_utc = datetime.now(timezone.utc)

        if status_code == 429:
            rec["consecutive_429"] += 1
            # Exponential backoff: 2^n * 60s + jitter (up to 30 mins)
            backoff_secs = min(1800, (2 ** rec["consecutive_429"]) * 60 + random.randint(15, 60))
            rec["cooldown_until"] = now_utc + timedelta(seconds=backoff_secs)
        elif status_code == 403 or (error_msg and ("challenge" in error_msg.lower() or "moment" in error_msg.lower())):
            # Escalate store to browser mode and apply 60s jitter cooldown
            rec["mode"] = "browser"
            rec["cooldown_until"] = now_utc + timedelta(seconds=random.randint(60, 120))
        elif status_code and 500 <= status_code <= 599:
            # Transient server error: 3-5 min pause
            rec["cooldown_until"] = now_utc + timedelta(seconds=random.randint(180, 300))
        else:
            # General error: small 30s penalty
            rec["cooldown_until"] = now_utc + timedelta(seconds=30)

    def get_recommended_mode(self, store_id: int) -> str:
        """Returns 'http' or 'browser' based on past challenge history."""
        return self.get_record(store_id)["mode"]

    def force_browser_mode(self, store_id: int):
        self.get_record(store_id)["mode"] = "browser"


class PlaywrightHumanizer:
    """Simulates organic human interaction inside Playwright pages."""

    @staticmethod
    async def apply_stealth_scripts(page):
        """Mask webdriver flags and inject realistic runtime environment."""
        stealth_js = """
        // 1. Hide webdriver
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        // 2. Realistic chrome object
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
        // 3. Realistic plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        // 4. Realistic languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en', 'bn']
        });
        """
        try:
            await page.add_init_script(stealth_js)
        except Exception:
            pass

    @staticmethod
    async def human_scroll(page, steps: int = 3):
        """Scroll page in gradual steps with micro-pauses to simulate reading and trigger lazy loading."""
        try:
            for _ in range(steps):
                distance = random.randint(200, 450)
                await page.mouse.wheel(0, distance)
                await page.wait_for_timeout(random.randint(120, 280))
        except Exception:
            pass
