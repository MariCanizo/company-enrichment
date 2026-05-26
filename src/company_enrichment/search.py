import logging
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from .config import MOCK_SEARCH, TAVILY_API_KEY
from .models import CompanyInput

logger = logging.getLogger(__name__)

# Known official domains for deterministic smoke runs.
_SEED_DOMAINS: dict[str, str] = {
    "danaher corporation": "https://www.danaher.com",
    "ford motor company": "https://www.ford.com",
    "merck & co.": "https://www.merck.com",
    "netflix": "https://www.netflix.com",
    "kraft heinz company": "https://www.kraftheinzcompany.com",
}


def discover_main_url(company: CompanyInput) -> Tuple[Optional[str], List[str]]:
    """
    Return (main_url, search_snippets).
    Production: Tavily/Serper/Bing. Mock: seeded domains.
    """
    name_key = company.company_name.strip().lower()

    seed_url = _SEED_DOMAINS.get(name_key)
    if MOCK_SEARCH or not TAVILY_API_KEY:
        snippets = [
            f"Mock search hit for {company.company_name}",
            f"Official site candidate: {seed_url}" if seed_url else "No seed domain",
        ]
        return seed_url, snippets

    main_url, snippets = _tavily_search(company.company_name, seed_url)
    return main_url, snippets


def _tavily_search(
    company_name: str,
    official_seed_url: Optional[str] = None,
) -> Tuple[Optional[str], List[str]]:
    try:
        from tavily import TavilyClient  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Install tavily-python or set MOCK_SEARCH=true") from exc

    client = TavilyClient(api_key=TAVILY_API_KEY)
    query = f"{company_name} official website investor relations contact"
    response = client.search(query=query, max_results=5)
    results = response.get("results", [])
    snippets = [r.get("content", "")[:500] for r in results if r.get("content")]
    urls = [r.get("url") for r in results if r.get("url")]
    main_url = _choose_main_url(urls, official_seed_url)
    return main_url, snippets


def _choose_main_url(
    urls: List[str],
    official_seed_url: Optional[str] = None,
) -> Optional[str]:
    if official_seed_url:
        seed_domain = _hostname(official_seed_url)
        for url in urls:
            if _hostname(url).endswith(seed_domain):
                return official_seed_url
        return official_seed_url

    for url in urls:
        lowered = url.lower()
        if lowered.endswith(".pdf"):
            continue
        if any(domain in lowered for domain in ("alphaspread.com", "q4cdn.com")):
            continue
        return _site_root(url)

    return _site_root(urls[0]) if urls else None


def _hostname(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _site_root(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    return f"{parsed.scheme}://{parsed.netloc}"


def candidate_paths(main_url: str) -> List[str]:
    base = main_url.rstrip("/")
    return [
        base,
        f"{base}/contact",
        f"{base}/contact-us",
        f"{base}/about",
        f"{base}/careers",
        f"{base}/jobs",
        f"{base}/privacy",
        f"{base}/investors",
    ]
