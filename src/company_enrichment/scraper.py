import json
import logging
import re
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple
from urllib.parse import urljoin

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

_PHONE_RE = re.compile(
    r"(?:\+?\d[\d().\-\s]{7,}\d)",
    re.I,
)

_URL_FIELD_KEYWORDS = {
    "career_url": ("career", "careers", "jobs", "join us", "work with us"),
    "faq_url": ("faq", "faqs", "frequently asked", "help center", "support"),
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
        bundle.candidate_logo_urls = [bundle.candidate_logo_url]
        bundle.field_sources["main_url"] = "mock seed domain"
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
                fields, logo_urls, image_urls = extract_facts_from_html(
                    resp.text,
                    page_url=str(resp.url),
                    main_url=main_url,
                )
                _merge_extracted_fields(bundle, fields, str(resp.url))
                _extend_unique(bundle.candidate_logo_urls, logo_urls)
                _extend_unique(bundle.candidate_image_urls, image_urls)
                if bundle.candidate_logo_urls and not bundle.candidate_logo_url:
                    bundle.candidate_logo_url = bundle.candidate_logo_urls[0]
                if bundle.candidate_image_urls and not bundle.candidate_image_url:
                    bundle.candidate_image_url = bundle.candidate_image_urls[0]

                text = _html_to_text(resp.text)
                if len(text) > 200:
                    bundle.pages[url] = text[:12000]
            except httpx.HTTPError as exc:
                logger.debug("Fetch failed %s: %s", url, exc)
    finally:
        if owns_client:
            await client.aclose()

    return bundle


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def extract_facts_from_html(
    html: str,
    page_url: str,
    main_url: str,
) -> Tuple[Dict[str, str], List[str], List[str]]:
    """Extract deterministic facts before asking the LLM to fill gaps."""
    soup = BeautifulSoup(html, "html.parser")
    fields: Dict[str, str] = {}
    logo_urls: List[str] = []
    image_urls: List[str] = []

    for node in _iter_jsonld_nodes(soup):
        _merge_dict(fields, _fields_from_jsonld(node, page_url))
        _extend_unique(logo_urls, _urls_from_value(node.get("logo"), page_url))
        _extend_unique(image_urls, _urls_from_value(node.get("image"), page_url))

    _merge_dict(fields, _fields_from_links(soup, page_url))
    _merge_dict(fields, _fields_from_text(_html_to_text(html)))

    _extend_unique(logo_urls, _logo_urls(soup, page_url, main_url))
    _extend_unique(image_urls, _company_image_urls(soup, page_url))

    return fields, logo_urls, image_urls


def _merge_extracted_fields(bundle: ScrapeBundle, fields: Dict[str, str], source: str) -> None:
    for field, value in fields.items():
        if value and not bundle.extracted_fields.get(field):
            bundle.extracted_fields[field] = value
            bundle.field_sources[field] = source


def _merge_dict(target: Dict[str, str], incoming: Dict[str, str]) -> None:
    for key, value in incoming.items():
        if value and not target.get(key):
            target[key] = value


def _extend_unique(target: List[str], incoming: Iterable[Optional[str]]) -> None:
    for value in incoming:
        if value and value not in target:
            target.append(value)


def _iter_jsonld_nodes(soup: BeautifulSoup) -> Iterator[Dict[str, Any]]:
    scripts = soup.find_all("script", type=lambda value: value and "ld+json" in value)
    for script in scripts:
        raw = script.string or script.get_text("", strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        yield from _walk_jsonld(payload)


def _walk_jsonld(payload: Any) -> Iterator[Dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            yield from _walk_jsonld(item)
    elif isinstance(payload, dict):
        yield payload
        graph = payload.get("@graph")
        if graph:
            yield from _walk_jsonld(graph)


def _fields_from_jsonld(node: Dict[str, Any], page_url: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    node_type = node.get("@type")
    types = node_type if isinstance(node_type, list) else [node_type]
    normalized_types = {str(t).lower() for t in types if t}
    is_company = bool(
        normalized_types
        & {
            "organization",
            "corporation",
            "localbusiness",
            "store",
            "financialservice",
        }
    )

    if not is_company:
        return fields

    _set_if_present(fields, "main_url", _absolute_url(_first_url(node.get("url")), page_url))
    _set_if_present(fields, "phone", _clean_phone(_first_string(node.get("telephone"))))
    _set_if_present(fields, "slogan", _first_string(node.get("slogan")))
    _set_if_present(fields, "mission", _first_string(node.get("mission")))

    same_as = node.get("sameAs")
    if same_as:
        for url in _urls_from_value(same_as, page_url):
            for field, pattern in _SOCIAL_PATTERNS.items():
                if pattern.search(url) and field not in fields:
                    fields[field] = url

    contact_point = node.get("contactPoint")
    if isinstance(contact_point, list):
        for item in contact_point:
            if isinstance(item, dict):
                _set_if_present(fields, "phone", _clean_phone(_first_string(item.get("telephone"))))
    elif isinstance(contact_point, dict):
        _set_if_present(fields, "phone", _clean_phone(_first_string(contact_point.get("telephone"))))

    address = node.get("address")
    if isinstance(address, list):
        address = next((item for item in address if isinstance(item, dict)), None)
    if isinstance(address, dict):
        _set_if_present(fields, "address_line_1", _first_string(address.get("streetAddress")))
        city_parts = [
            _first_string(address.get("addressLocality")),
            _first_string(address.get("addressRegion")),
            _first_string(address.get("postalCode")),
        ]
        _set_if_present(fields, "address_line_2", ", ".join(part for part in city_parts if part))
        country = address.get("addressCountry")
        if isinstance(country, dict):
            country = country.get("name")
        _set_if_present(fields, "country", _first_string(country))

    return fields


def _fields_from_links(soup: BeautifulSoup, page_url: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for link in soup.find_all("a", href=True):
        href = str(link.get("href", "")).strip()
        if href.startswith(("mailto:", "javascript:", "#")):
            continue

        if href.startswith("tel:") and "phone" not in fields:
            fields["phone"] = _clean_phone(href.replace("tel:", "", 1))
            continue

        absolute = _absolute_url(href, page_url)
        if not absolute:
            continue

        haystack = " ".join(
            [
                link.get_text(" ", strip=True),
                href,
                str(link.get("title", "")),
                str(link.get("aria-label", "")),
            ]
        ).lower()

        for field, keywords in _URL_FIELD_KEYWORDS.items():
            if field not in fields and any(keyword in haystack for keyword in keywords):
                fields[field] = absolute

        for field, pattern in _SOCIAL_PATTERNS.items():
            if field not in fields and pattern.search(absolute):
                fields[field] = absolute

    return fields


def _fields_from_text(text: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    phone_match = _PHONE_RE.search(text)
    if phone_match:
        fields["phone"] = _clean_phone(phone_match.group(0))

    mission_match = re.search(
        r"\b(?:our\s+)?mission\s+(?:is|:)\s+(.{20,500}?)(?:\n|$)",
        text,
        re.I,
    )
    if mission_match:
        fields["mission"] = mission_match.group(1).strip(" .")

    return fields


def _logo_urls(soup: BeautifulSoup, page_url: str, main_url: str) -> List[str]:
    candidates: List[str] = []
    for image in soup.find_all("img"):
        haystack = " ".join(
            [
                str(image.get("alt", "")),
                str(image.get("class", "")),
                str(image.get("id", "")),
                str(image.get("src", "")),
            ]
        ).lower()
        if "logo" in haystack:
            candidate = _absolute_url(_first_string(image.get("src")), page_url)
            if candidate:
                candidates.append(candidate)

    for rel_name in ("icon", "shortcut icon", "apple-touch-icon", "mask-icon"):
        links = soup.find_all("link", rel=lambda rel: rel and rel_name in " ".join(rel).lower())
        for link in links:
            candidate = _absolute_url(_first_string(link.get("href")), page_url)
            if candidate:
                candidates.append(candidate)

    candidates.append(f"{main_url.rstrip('/')}/favicon.ico")
    unique: List[str] = []
    _extend_unique(unique, candidates)
    return unique


def _company_image_urls(soup: BeautifulSoup, page_url: str) -> List[str]:
    candidates: List[str] = []
    for attr_name, attr_value in (
        ("property", "og:image"),
        ("name", "twitter:image"),
        ("name", "thumbnail"),
    ):
        tag = soup.find("meta", attrs={attr_name: attr_value})
        if tag:
            candidate = _absolute_url(_first_string(tag.get("content")), page_url)
            if candidate:
                candidates.append(candidate)

    for image in soup.find_all("img"):
        haystack = " ".join(
            [
                str(image.get("alt", "")),
                str(image.get("class", "")),
                str(image.get("id", "")),
                str(image.get("src", "")),
            ]
        ).lower()
        if "logo" in haystack:
            continue
        if any(word in haystack for word in ("hero", "company", "about", "building", "campus")):
            candidate = _absolute_url(_first_string(image.get("src")), page_url)
            if candidate:
                candidates.append(candidate)

    unique: List[str] = []
    _extend_unique(unique, candidates)
    return unique


def _set_if_present(fields: Dict[str, str], key: str, value: Optional[str]) -> None:
    if value and key not in fields:
        fields[key] = value.strip()


def _first_string(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        for item in value:
            found = _first_string(item)
            if found:
                return found
    if isinstance(value, dict):
        for key in ("url", "@id", "content", "name"):
            found = _first_string(value.get(key))
            if found:
                return found
    return None


def _first_url(value: Any) -> Optional[str]:
    return _first_string(value)


def _urls_from_value(value: Any, page_url: str) -> Iterator[str]:
    if isinstance(value, list):
        for item in value:
            yield from _urls_from_value(item, page_url)
    else:
        absolute = _absolute_url(_first_url(value), page_url)
        if absolute:
            yield absolute


def _absolute_url(value: Optional[str], page_url: str) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    if value.startswith(("data:", "mailto:", "tel:", "javascript:")):
        return None
    return urljoin(page_url, value).split("#", 1)[0]


def _clean_phone(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    cleaned = cleaned.replace("(0)", "")
    return cleaned[:32] if cleaned else None


def extract_social_links(text_blobs: Iterable[str]) -> Dict[str, Optional[str]]:
    joined = "\n".join(text_blobs)
    out: Dict[str, Optional[str]] = {}
    for field, pattern in _SOCIAL_PATTERNS.items():
        match = pattern.search(joined)
        out[field] = match.group(0) if match else None
    return out
