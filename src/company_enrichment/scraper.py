import logging
import re
from typing import Dict, Iterable, Optional

import httpx

from bs4 import BeautifulSoup

from .config import MOCK_SEARCH, USER_AGENT
from .models import CompanyInput, ScrapeBundle
from .search import candidate_paths, discover_main_url

logger = logging.getLogger(__name__)

_SOCIAL_PATTERNS = {
    "linkedin_url": re.compile(r"https?://(?:[\w-]+\.)?linkedin\.com/company/[\w%-./]+", re.I),
    "facebook_url": re.compile(r"https?://(?:[\w-]+\.)?facebook\.com/[\w%-./]+", re.I),
    "twitter_url": re.compile(
        r"https?://(?:[\w-]+\.)?(?:twitter|x)\.com/[\w%-./]+", re.I
    ),
    "instagram_url": re.compile(r"https?://(?:[\w-]+\.)?instagram\.com/[\w%-./]+", re.I),
    "youtube_url": re.compile(
        r"https?://(?:[\w-]+\.)?youtube\.com/(?:channel|c|user|@)[\w%-./]+", re.I
    ),
}


async def build_scrape_bundle(
    company: CompanyInput,
    client: Optional[httpx.AsyncClient] = None,
) -> ScrapeBundle:
    main_url, snippets = discover_main_url(company)
    bundle = ScrapeBundle(
        cpyId=company.cpyId,
        company_name=company.company_name,
        main_url=main_url,
        search_snippets=snippets,
    )

    if not main_url:
        logger.warning("No main_url for %s", company.company_name)
        return bundle

    if MOCK_SEARCH:
        bundle.pages[main_url] = (
            f"Mock scraped homepage text for {company.company_name}. "
            f"Visit {main_url} for official information."
        )
        bundle.candidate_logo_url = f"{main_url.rstrip('/')}/favicon.ico"
        return bundle

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )

    try:
        for url in candidate_paths(main_url):
            try:
                resp = await client.get(url)
                if resp.status_code >= 400:
                    continue
                text = _html_to_text(resp.text)
                if len(text) > 200:
                    bundle.pages[url] = text[:12000]
            except httpx.HTTPError as exc:
                logger.debug("Fetch failed %s: %s", url, exc)

        if bundle.pages:
            first_html = next(iter(bundle.pages.values()))
            bundle.candidate_logo_url = _guess_og_image(first_html, main_url)
    finally:
        if owns_client:
            await client.aclose()

    return bundle


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def _guess_og_image(page_text: str, base_url: str) -> Optional[str]:
    # In production parse actual HTML for og:image; mock uses favicon path pattern
    return f"{base_url.rstrip('/')}/favicon.ico"


def extract_social_links(text_blobs: Iterable[str]) -> Dict[str, Optional[str]]:
    joined = "\n".join(text_blobs)
    out: Dict[str, Optional[str]] = {}
    for field, pattern in _SOCIAL_PATTERNS.items():
        match = pattern.search(joined)
        out[field] = match.group(0) if match else None
    return out
