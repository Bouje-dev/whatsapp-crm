"""
Flow helpers: URL scraper for AI Agent product context.
"""
import logging
import re

logger = logging.getLogger(__name__)


def scrape_product_data(url):
    """
    Fetch a URL and extract text suitable as product context (title, description, price-like patterns).
    Uses requests + BeautifulSoup if available, else falls back to requests only.
    Returns a string with product-relevant text, or empty string on failure.
    """
    if not url or not url.strip().startswith(("http://", "https://")):
        return ""
    url = url.strip()
    try:
        import requests
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (compatible; FlowBot/1.0)"})
        r.raise_for_status()
        html = r.text
    except Exception as e:
        logger.warning("scrape_product_data fetch failed: %s", e)
        return ""

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
    except ImportError:
        # Fallback: strip tags with regex
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Keep first ~80 lines and join; limit total length
    out = "\n".join(lines[:80])[:8000]
    return out


# Price/currency patterns (e.g. 99.99, $50, 50 MAD, 100 SAR)
PRICE_RE = re.compile(
    r"(?:\$|€|£|MAD|USD|EUR|SAR|AED|EGP)\s*[\d,.]+\s*|[\d,.]+\s*(?:\$|€|£|MAD|USD|EUR|SAR|AED|EGP)|[\d,]+\s*\.?\d*\s*(?:MAD|USD|EUR|SAR|AED|EGP)|[\d,.]+\s*(?:DH|MAD)",
    re.MULTILINE | re.IGNORECASE,
)


def _extract_structured(text):
    """
    Heuristic extraction of product_name, prices, market from scraped text.
    Returns dict: product_name, prices (str), market, additional (str).
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    product_name = ""
    prices_lines = []
    market = ""
    rest = []

    for i, line in enumerate(lines):
        if not line:
            continue
        if not product_name and len(line) > 2 and len(line) < 200:
            product_name = line
            continue
        if PRICE_RE.search(line) or re.search(r"\d{1,6}[,.]\d{2}", line):
            prices_lines.append(line)
            continue
        if re.search(r"\b(market|marketplace|store|shop|category|brand)\b", line, re.IGNORECASE) and len(line) < 300:
            if not market:
                market = line
            else:
                rest.append(line)
            continue
        rest.append(line)

    prices = "\n".join(prices_lines[:20]).strip() if prices_lines else ""
    additional = "\n".join(rest[:60]).strip()[:4000] if rest else ""

    return {
        "product_name": product_name[:500] if product_name else "",
        "prices": prices[:1500] if prices else "",
        "market": market[:500] if market else "",
        "additional": additional,
    }


def scrape_and_extract_product(url):
    """
    Scrape URL and return both full text and structured fields.
    Returns dict: product_context, product_name, prices, market, additional.
    """
    raw = scrape_product_data(url)
    if not raw:
        return {"product_context": "", "product_name": "", "prices": "", "market": "", "additional": ""}
    structured = _extract_structured(raw)
    return {
        "product_context": raw,
        "product_name": structured["product_name"],
        "prices": structured["prices"],
        "market": structured["market"],
        "additional": structured["additional"],
    }
