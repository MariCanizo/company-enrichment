import logging
from typing import List, Optional, Tuple

from .config import MOCK_SEARCH, TAVILY_API_KEY
from .models import CompanyInput

logger = logging.getLogger(__name__)

# Known domains for mock / seed runs (replace with search API in production)
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

    if MOCK_SEARCH or not TAVILY_API_KEY:
        url = _SEED_DOMAINS.get(name_key)
        snippets = [
            f"Mock search hit for {company.company_name}",
            f"Official site candidate: {url}" if url else "No seed domain",
        ]
        return url, snippets

    return _tavily_search(company.company_name)


def _tavily_search(company_name: str) -> Tuple[Optional[str], List[str]]:
    try:
        from tavily import TavilyClient  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Install tavily-python or set MOCK_SEARCH=true") from exc

    client = TavilyClient(api_key=TAVILY_API_KEY)
    query = f"{company_name} official website investor relations contact"
    response = client.search(query=query, max_results=5)
    results = response.get("results", [])
    snippets = [r.get("content", "")[:500] for r in results if r.get("content")]
    main_url = results[0]["url"] if results else None
    return main_url, snippets


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
