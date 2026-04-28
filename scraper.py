#!/usr/bin/env python3
"""
TrendScope - Advanced Web Scraper Module
Uses Playwright (JS rendering) + curl_cffi (TLS impersonation) to bypass anti-bot.
"""

import random
import logging
import time
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ─── Try advanced libraries with graceful fallback ────────────────────────────

# curl_cffi - Mimics real Chrome TLS fingerprint (bypasses Cloudflare basic checks)
try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
    logger.info("✅ curl_cffi loaded - TLS fingerprint impersonation enabled")
except ImportError:
    HAS_CURL_CFFI = False
    logger.warning("⚠️ curl_cffi not installed. Install with: pip install curl-cffi")
    import requests as cffi_requests  # Plain requests fallback

# Playwright - Headless browser for JS-heavy sites
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    HAS_PLAYWRIGHT = True
    logger.info("✅ Playwright loaded - JS rendering enabled")
except ImportError:
    HAS_PLAYWRIGHT = False
    logger.warning("⚠️ Playwright not installed. Install with: pip install playwright && playwright install chromium")

# Plain requests as ultimate fallback
import requests

# ─── Constants ────────────────────────────────────────────────────────────────

# Realistic browser impersonation profiles (curl_cffi supports these)
IMPERSONATE_PROFILES = [
    "chrome120", "chrome119", "chrome116", "chrome110",
    "edge101", "safari17_0", "safari15_5",
]

# Real Chrome user agents (rotated)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Realistic browser headers (mimics what Chrome actually sends)
def get_browser_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "max-age=0",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Referer": "https://www.google.com/",
    }


# Fallback images for products without scraped images
FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1593030761757-71fae45fa0e7?w=400&h=500&fit=crop",
    "https://images.unsplash.com/photo-1598033129183-c4f50c736c10?w=400&h=500&fit=crop",
    "https://images.unsplash.com/photo-1591047139829-d91aecb6caea?w=400&h=500&fit=crop",
    "https://images.unsplash.com/photo-1588099768531-a72d4a198538?w=400&h=500&fit=crop",
    "https://images.unsplash.com/photo-1576566588028-4147f3842f27?w=400&h=500&fit=crop",
    "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=400&h=500&fit=crop",
    "https://images.unsplash.com/photo-1618354691373-d851c5c3a990?w=400&h=500&fit=crop",
    "https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=400&h=500&fit=crop",
    "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&h=500&fit=crop",
    "https://images.unsplash.com/photo-1554568218-0f1715e72254?w=400&h=500&fit=crop",
]

COLOR_NAMES = [
    "Black", "Navy", "Dark Blue", "Red", "Purple", "Charcoal", "Coral",
    "Orange", "Teal", "Dark Gray", "Mauve", "Rose", "Steel Blue", "Salmon",
    "Sage", "Crimson", "Pink", "Ivory", "Peach", "Olive", "Brown", "Rust",
    "Espresso", "Tan", "Blush",
]

# Category detection keywords (used to auto-categorize products)
CATEGORY_KEYWORDS = {
    "Polo Shirts": ["polo", "pique"],
    "T-Shirts": ["t-shirt", "tshirt", "tee ", " tee", "graphic tee"],
    "Shirts": ["shirt", "oxford", "button-down", "button down", "blouse", "dress shirt"],
    "Jeans": ["jean", "denim pant"],
    "Pants": ["pant", "trouser", "chino", "slack"],
    "Shorts": ["short"],
    "Hoodies": ["hoodie", "hooded"],
    "Sweaters": ["sweater", "cardigan", "knit", "pullover", "jumper", "cashmere"],
    "Jackets": ["jacket", "bomber", "windbreaker"],
    "Coats": ["coat", "parka", "trench", "peacoat", "overcoat"],
    "Suits": ["suit", "tuxedo"],
    "Blazers": ["blazer", "sport coat"],
    "Dresses": ["dress", "gown"],
    "Skirts": ["skirt"],
    "Shoes": ["shoe", "sneaker", "boot", "loafer", "sandal", "heel", "trainer"],
    "Accessories": ["belt", "scarf", "hat", "tie ", " tie", "wallet", "sunglasses", "bag", "watch", "cap"],
}

# Default category for fallback
DEFAULT_CATEGORY = "T-Shirts"

# Price regex patterns
PRICE_REGEX = re.compile(r'[\$£€¥]\s?\d{1,4}(?:[.,]\d{1,2})?|\d{1,4}(?:[.,]\d{1,2})?\s?[\$£€¥]')


# ─── Main Scraper Class ──────────────────────────────────────────────────────

class WebScraper:
    """
    Multi-strategy scraper:
    1. Playwright (full JS rendering) — for SPAs like ZARA, Lululemon
    2. curl_cffi with chrome impersonation — for protected sites with TLS checks
    3. Plain requests + BeautifulSoup — for simple sites
    4. Intelligent mock data — last resort if all else fails
    """

    # Sites that REQUIRE Playwright (JS-heavy SPAs)
    JS_HEAVY_SITES = {
        "zara.com", "lululemon.com", "uniqlo.com", "bershka.com",
        "ralphlauren.com", "hm.com", "nike.com", "adidas.com",
    }

    def __init__(self):
        self._playwright = None
        self._browser = None

    # ─── Strategy Selection ──────────────────────────────────────────────────

    def _needs_javascript(self, url: str) -> bool:
        """Determine if a site requires JS rendering."""
        domain = urlparse(url).netloc.lower().replace("www.", "")
        return any(js_site in domain for js_site in self.JS_HEAVY_SITES)

    # ─── STRATEGY 1: Playwright (Headless Browser) ───────────────────────────

    def _fetch_with_playwright(self, url: str, wait_selector: str = None, timeout: int = 30000) -> str:
        """
        Fetch a page using Playwright headless Chromium.
        Handles JavaScript, cookies, and modern anti-bot measures.
        """
        if not HAS_PLAYWRIGHT:
            raise RuntimeError("Playwright not installed")

        logger.info(f"🎭 [Playwright] Fetching: {url}")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ]
            )

            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
                # Hide webdriver flag
                java_script_enabled=True,
            )

            # Inject stealth scripts (hide automation indicators)
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };
            """)

            page = context.new_page()

            try:
                # Navigate and wait for content
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)

                # Wait extra for JS to render product cards
                try:
                    if wait_selector:
                        page.wait_for_selector(wait_selector, timeout=10000)
                    else:
                        # Wait for any image to load (good signal that products rendered)
                        page.wait_for_selector("img", timeout=8000)
                except PlaywrightTimeoutError:
                    logger.warning(f"⏱️  Selector wait timed out for {url}, continuing anyway")

                # Scroll to trigger lazy-loaded products
                self._human_scroll(page)

                # Get the fully-rendered HTML
                html = page.content()
                logger.info(f"✅ [Playwright] Got {len(html):,} chars from {url}")
                return html

            finally:
                page.close()
                context.close()
                browser.close()

    def _human_scroll(self, page):
        """Simulate human scrolling to trigger lazy-loaded content."""
        try:
            for i in range(3):
                page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {(i + 1) * 0.3})")
                time.sleep(random.uniform(0.5, 1.2))
        except Exception as e:
            logger.debug(f"Scroll error: {e}")

    # ─── STRATEGY 2: curl_cffi (TLS Fingerprint Impersonation) ───────────────

    def _fetch_with_cffi(self, url: str, timeout: int = 20) -> str:
        """
        Fetch using curl_cffi with browser TLS fingerprint impersonation.
        Bypasses Cloudflare/Akamai checks that detect 'requests' library.
        """
        if not HAS_CURL_CFFI:
            raise RuntimeError("curl_cffi not installed")

        impersonate = random.choice(IMPERSONATE_PROFILES)
        logger.info(f"🔐 [curl_cffi/{impersonate}] Fetching: {url}")

        response = cffi_requests.get(
            url,
            impersonate=impersonate,
            headers=get_browser_headers(),
            timeout=timeout,
            allow_redirects=True,
        )
        response.raise_for_status()
        logger.info(f"✅ [curl_cffi] Status {response.status_code} from {url}")
        return response.text

    # ─── STRATEGY 3: Plain requests (Simple Fallback) ────────────────────────

    def _fetch_with_requests(self, url: str, timeout: int = 15) -> str:
        """Fetch using plain requests library (last network attempt)."""
        logger.info(f"🌐 [requests] Fetching: {url}")
        response = requests.get(url, headers=get_browser_headers(), timeout=timeout)
        response.raise_for_status()
        return response.text

    # ─── Smart Multi-Strategy Fetch ──────────────────────────────────────────

    def _smart_fetch(self, url: str) -> str:
        """
        Try multiple strategies in order until one works.
        """
        errors = []

        # Strategy 1: Playwright (for JS-heavy sites or if first attempt fails)
        if HAS_PLAYWRIGHT and self._needs_javascript(url):
            try:
                return self._fetch_with_playwright(url)
            except Exception as e:
                errors.append(f"Playwright: {e}")
                logger.warning(f"❌ Playwright failed for {url}: {e}")

        # Strategy 2: curl_cffi (TLS impersonation)
        if HAS_CURL_CFFI:
            try:
                return self._fetch_with_cffi(url)
            except Exception as e:
                errors.append(f"curl_cffi: {e}")
                logger.warning(f"❌ curl_cffi failed for {url}: {e}")

        # Strategy 3: Playwright (for non-JS sites if curl_cffi failed)
        if HAS_PLAYWRIGHT and not self._needs_javascript(url):
            try:
                return self._fetch_with_playwright(url)
            except Exception as e:
                errors.append(f"Playwright: {e}")
                logger.warning(f"❌ Playwright fallback failed for {url}: {e}")

        # Strategy 4: Plain requests
        try:
            return self._fetch_with_requests(url)
        except Exception as e:
            errors.append(f"requests: {e}")

        raise Exception(f"All fetch strategies failed for {url}: {' | '.join(errors)}")

    # ─── Main Entry Point ────────────────────────────────────────────────────

    def scrape_website(self, website_name: str, website_url: str, progress_callback=None):
        """
        Scrape a fashion website using the best available strategy.
        """
        if progress_callback:
            progress_callback(5)

        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"🚀 Starting scrape: {website_name} ({website_url})")
        logger.info(f"   JS-heavy site: {self._needs_javascript(website_url)}")
        logger.info(f"   Playwright available: {HAS_PLAYWRIGHT}")
        logger.info(f"   curl_cffi available: {HAS_CURL_CFFI}")

        products = []

        try:
            if progress_callback:
                progress_callback(15)

            # Fetch the homepage with smart strategy selection
            html = self._smart_fetch(website_url)

            if progress_callback:
                progress_callback(40)

            soup = BeautifulSoup(html, "lxml")

            # Try to extract products from homepage
            products = self._extract_products(soup, website_name, website_url)

            if progress_callback:
                progress_callback(60)

            # If we didn't get enough products, try category pages
            if len(products) < 5:
                logger.info(f"Only found {len(products)} on homepage, trying category pages...")
                category_links = self._find_category_links(soup, website_url)

                for i, (cat_name, cat_url) in enumerate(category_links[:3]):
                    if progress_callback:
                        progress_callback(60 + (i * 10))

                    try:
                        # Be polite — random delay
                        time.sleep(random.uniform(1.5, 3.5))

                        cat_html = self._smart_fetch(cat_url)
                        cat_soup = BeautifulSoup(cat_html, "lxml")
                        cat_products = self._extract_products(
                            cat_soup, website_name, cat_url, suggested_category=cat_name
                        )
                        products.extend(cat_products)
                        logger.info(f"   + {len(cat_products)} from category '{cat_name}'")
                    except Exception as e:
                        logger.warning(f"Failed scraping category {cat_name}: {e}")
                        continue

            # Deduplicate by name
            seen_names = set()
            unique_products = []
            for p in products:
                key = (p.get("name", "").lower(), p.get("source_website"))
                if key not in seen_names and p.get("name"):
                    seen_names.add(key)
                    unique_products.append(p)
            products = unique_products

        except Exception as e:
            logger.error(f"❌ Real scraping failed for {website_name}: {e}")
            logger.info(f"   Falling back to mock data generation")

        # Final fallback to mock data only if real scraping returned nothing
        if not products:
            if progress_callback:
                progress_callback(70)
            logger.warning(f"⚠️ No products extracted from {website_name}, using mock data")
            products = self._generate_mock_products(website_name, website_url)

        if progress_callback:
            progress_callback(100)

        logger.info(f"✅ Completed {website_name}: {len(products)} products")
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return products

    # ─── Product Extraction ──────────────────────────────────────────────────

    def _extract_products(self, soup, website_name: str, base_url: str,
                          suggested_category: str = None):
        """Extract product items from HTML using multi-pass strategies."""
        products = []

        # Pass 1: Try common product container selectors
        selectors = [
            'li.product', '.product-item', '.product-card', '.product-tile',
            '[data-product]', '[data-product-id]', '[data-testid*="product"]',
            'article.product', '.product', 'li[class*="product"]',
            'div[class*="product-card"]', 'div[class*="product-tile"]',
            '.catalog-grid-item', '.product-grid-item', '.collection-item',
            '[class*="ProductCard"]', '[class*="product_card"]',
            '[class*="ProductTile"]', 'a[href*="/product"]',
        ]

        product_elements = []
        for selector in selectors:
            try:
                found = soup.select(selector)
                if len(found) >= 3:
                    product_elements = found
                    logger.info(f"   Selector '{selector}' matched {len(found)} elements")
                    break
            except Exception:
                continue

        # Pass 2: Heuristic — find elements with both image AND price text
        if len(product_elements) < 3:
            candidates = []
            for tag in soup.find_all(["div", "li", "article", "a"], limit=500):
                if tag.find("img") and PRICE_REGEX.search(tag.get_text()):
                    candidates.append(tag)
            if len(candidates) >= 3:
                product_elements = candidates[:50]
                logger.info(f"   Heuristic found {len(product_elements)} candidates")

        # Extract data from each element
        for elem in product_elements[:30]:
            try:
                product = self._extract_single_product(
                    elem, website_name, base_url, suggested_category
                )
                if product:
                    products.append(product)
            except Exception as e:
                logger.debug(f"   Skip element: {e}")
                continue

        return products

    def _extract_single_product(self, elem, website_name: str, base_url: str,
                                 suggested_category: str = None):
        """Extract a single product's data from a DOM element."""

        # ─── Name ───
        name = None
        for sel in ['h2', 'h3', 'h4', '.name', '.title', '.product-name',
                    '.product-title', '[class*="name"]', '[class*="title"]',
                    '[data-name]', 'a[title]']:
            found = elem.select_one(sel)
            if found:
                text = found.get_text(strip=True) or found.get("title", "").strip()
                if text and 3 < len(text) < 150:
                    name = text
                    break

        if not name:
            # Fallback: use img alt text
            img = elem.find("img")
            if img:
                alt = img.get("alt", "").strip()
                if alt and 3 < len(alt) < 150:
                    name = alt

        if not name:
            return None

        # ─── Price ───
        price = None
        currency = "$"
        full_text = elem.get_text(" ", strip=True)
        price_match = PRICE_REGEX.search(full_text)
        if price_match:
            price = price_match.group(0).strip()
            for c in "£€¥$":
                if c in price:
                    currency = c
                    break
        else:
            # Try common price selectors
            for sel in ['.price', '[class*="price"]', '.amount',
                        '[data-price]', '.cost', '.money']:
                found = elem.select_one(sel)
                if found:
                    pt = found.get_text(strip=True)
                    if pt and any(c in pt for c in "$£€¥0123456789"):
                        price = pt[:30]
                        break

        if not price:
            return None

        # ─── Image URL ───
        img_url = None
        img = elem.find("img")
        if img:
            for attr in ["src", "data-src", "data-lazy-src", "data-original",
                         "data-srcset", "srcset"]:
                val = img.get(attr)
                if val:
                    # Handle srcset (take first URL)
                    if " " in val:
                        val = val.split(",")[0].strip().split(" ")[0]
                    if not val.endswith((".svg", ".gif")) and "placeholder" not in val.lower():
                        img_url = val
                        break

        if img_url:
            img_url = self._make_absolute_url(base_url, img_url)
            # Skip 1x1 tracking pixels
            if "1x1" in img_url or img_url.endswith("=") or len(img_url) < 30:
                img_url = None

        if not img_url:
            img_url = random.choice(FALLBACK_IMAGES)

        # ─── Product URL ───
        product_url = base_url
        link = elem.find("a", href=True)
        if link:
            product_url = self._make_absolute_url(base_url, link["href"])

        # ─── Category Detection ───
        category = self._detect_category(name, suggested_category, base_url)

        # ─── Color (try to extract, otherwise random) ───
        color = random.choice(COLOR_NAMES)
        for sel in ['[class*="color"]', '[data-color]', '.swatch']:
            found = elem.select_one(sel)
            if found:
                color_text = found.get("data-color") or found.get_text(strip=True)
                if color_text and 2 < len(color_text) < 30:
                    color = color_text[:30]
                    break

        return {
            "id": f"{website_name.lower().replace(' ', '-')}-{hash(name) & 0xFFFFFF:x}-{int(time.time() * 1000)}",
            "name": name[:100],
            "price": price[:30],
            "currency": currency,
            "image_url": img_url,
            "product_url": product_url,
            "category": category,
            "source_website": website_name,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "color": color,
            "description": f"{website_name} {category}",
        }

    def _detect_category(self, product_name: str, suggested: str = None,
                          context_url: str = "") -> str:
        """Detect product category from name + URL context."""
        text_to_check = f"{product_name} {context_url}".lower()

        # Check by keyword match (longest categories first to avoid false matches)
        sorted_cats = sorted(CATEGORY_KEYWORDS.items(),
                             key=lambda x: -max(len(k) for k in x[1]))
        for category, keywords in sorted_cats:
            for kw in keywords:
                if kw.lower() in text_to_check:
                    return category

        # Fall back to suggested category
        if suggested:
            for cat in CATEGORY_KEYWORDS.keys():
                if cat.lower() in suggested.lower() or suggested.lower() in cat.lower():
                    return cat

        return DEFAULT_CATEGORY

    def _find_category_links(self, soup, base_url: str):
        """Find category navigation links."""
        categories = []
        seen_urls = set()

        category_terms = [
            "shirt", "polo", "t-shirt", "pant", "jean", "short",
            "jacket", "coat", "sweater", "hoodie", "dress", "skirt",
            "blazer", "suit", "men", "women", "new",
        ]

        for link in soup.find_all("a", href=True, limit=300):
            href = link["href"]
            text = link.get_text(strip=True).lower()

            if not text or len(text) > 50:
                continue
            if href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            for term in category_terms:
                if term in text:
                    full_url = self._make_absolute_url(base_url, href)
                    if full_url and full_url not in seen_urls:
                        seen_urls.add(full_url)
                        categories.append((text.title(), full_url))
                    break

            if len(categories) >= 10:
                break

        return categories

    def _make_absolute_url(self, base_url: str, url: str) -> str:
        """Convert relative URL to absolute."""
        if not url:
            return None
        if url.startswith(("http://", "https://")):
            return url
        if url.startswith("//"):
            return "https:" + url
        return urljoin(base_url, url)

    # ─── Mock Data Fallback (only if all scraping fails) ─────────────────────

    def _generate_mock_products(self, website_name: str, website_url: str):
        """Generate realistic mock data when real scraping returns nothing."""
        name_prefixes = {
            "ZARA": ["Basic", "Premium", "Urban", "Classic", "Modern", "Essential", "Trend", "Studio"],
            "Lululemon": ["Swift", "Align", "Wunder", "Define", "Invigorate", "Fast", "Scuba", "Ready"],
            "UNIQLO": ["Airism", "Heattech", "Blocktech", "Supima", "Ultra", "Premium", "Cashmere", "UV"],
            "Next": ["Signature", "Collection", "Classic", "Modern", "Tailored", "Smart", "Pure", "Refined"],
            "Bershka": ["Street", "Raw", "Urban", "Basic", "Oversized", "Slim", "Y2K", "Destroyed"],
            "J.Crew": ["Wallace", "Barnes", "Aldridge", "Classic", "Heritage", "Merino", "Essential", "Crew"],
            "Ralph Lauren": ["Polo", "Classic", "Oxford", "Crew", "Vintage", "Heritage", "Rugby", "Custom"],
        }

        category_suffixes = {
            "Shirts": ["Oxford Shirt", "Linen Shirt", "Cotton Shirt", "Regular Fit Shirt"],
            "Polo Shirts": ["Polo Shirt", "Sport Polo", "Classic Polo", "Slim Polo"],
            "T-Shirts": ["Crew Neck Tee", "V-Neck Tee", "Graphic Tee", "Essential Tee"],
            "Pants": ["Chino Pants", "Dress Pants", "Slim Pants", "Cargo Pants"],
            "Jeans": ["Slim Jeans", "Straight Jeans", "Bootcut Jeans", "Skinny Jeans"],
            "Shorts": ["Chino Shorts", "Athletic Shorts", "Casual Shorts", "Denim Shorts"],
            "Jackets": ["Bomber Jacket", "Denim Jacket", "Leather Jacket", "Field Jacket"],
            "Coats": ["Wool Coat", "Trench Coat", "Puffer Coat", "Peacoat"],
            "Sweaters": ["Cashmere Sweater", "Crew Neck Sweater", "Turtleneck", "Cardigan"],
            "Hoodies": ["Pullover Hoodie", "Zip Hoodie", "Oversized Hoodie", "Fleece Hoodie"],
        }

        price_ranges = {
            "ZARA": (19, 120), "Lululemon": (48, 168), "UNIQLO": (14, 99),
            "Next": (18, 110), "Bershka": (12, 79), "J.Crew": (29, 298),
            "Ralph Lauren": (49, 650),
        }

        prefixes = name_prefixes.get(website_name, ["Premium", "Classic", "Modern"])
        prange = price_ranges.get(website_name, (20, 100))
        currency = "£" if website_name == "Next" else "$"
        all_categories = list(category_suffixes.keys())

        products = []
        used = set()
        for i in range(random.randint(8, 14)):
            cat = random.choice(all_categories)
            suffixes = category_suffixes[cat]
            name = f"{random.choice(prefixes)} {random.choice(suffixes)}"
            if name in used:
                continue
            used.add(name)

            products.append({
                "id": f"{website_name.lower().replace(' ', '-')}-mock-{i}-{int(time.time() * 1000)}",
                "name": name,
                "price": f"{currency}{random.randint(*prange)}.{random.randint(0, 99):02d}",
                "currency": currency,
                "image_url": random.choice(FALLBACK_IMAGES),
                "product_url": website_url,
                "category": cat,
                "source_website": website_name,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "color": random.choice(COLOR_NAMES),
                "description": f"{website_name} {cat.lower()} (mock data — real scrape returned no items)",
            })

        return products
