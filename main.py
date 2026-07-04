"""
Link Preview API
-----------------
Given a URL, returns clean, normalized metadata: title, description,
image, favicon, site name, and canonical URL. Falls back gracefully
across Open Graph, Twitter Cards, and plain HTML tags.

Run locally:
    uvicorn main:app --reload --port 8000

Example:
    GET /preview?url=https://www.bbc.co.uk
"""

import re
import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

app = FastAPI(
    title="Link Preview API",
    description="Extracts title, description, image, favicon, and site name from any URL.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; LinkPreviewBot/1.0; "
        "+https://github.com/)"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

MAX_BYTES = 2_000_000  # don't download more than ~2MB of HTML
TIMEOUT = 8.0

# Very small in-memory cache to avoid hammering the same URL repeatedly.
# Fine for a demo / low-traffic API; swap for Redis if you scale this up.
_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL_SECONDS = 60 * 30  # 30 minutes


class PreviewResponse(BaseModel):
    url: str
    final_url: str
    title: str | None = None
    description: str | None = None
    image: str | None = None
    favicon: str | None = None
    site_name: str | None = None


def _meta(soup: BeautifulSoup, *, prop: str | None = None, name: str | None = None) -> str | None:
    tag = None
    if prop:
        tag = soup.find("meta", attrs={"property": prop})
    if tag is None and name:
        tag = soup.find("meta", attrs={"name": name})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None


def _extract_favicon(soup: BeautifulSoup, base_url: str) -> str | None:
    for rel in ("icon", "shortcut icon", "apple-touch-icon"):
        link = soup.find("link", rel=lambda v: v and rel in v.lower())
        if link and link.get("href"):
            return urljoin(base_url, link["href"])
    # default fallback
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/favicon.ico"


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


async def _fetch_html(url: str) -> tuple[str, str]:
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=TIMEOUT, headers=HEADERS
    ) as client:
        try:
            async with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Target URL returned status {resp.status_code}",
                    )
                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type and "xml" not in content_type:
                    raise HTTPException(
                        status_code=422,
                        detail=f"URL does not point to an HTML page (content-type: {content_type})",
                    )
                chunks = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > MAX_BYTES:
                        break
                html_bytes = b"".join(chunks)
                final_url = str(resp.url)
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Timed out fetching the target URL")
        except httpx.RequestError as e:
            raise HTTPException(status_code=422, detail=f"Could not fetch URL: {e}")

    encoding = resp.encoding or "utf-8"
    try:
        html = html_bytes.decode(encoding, errors="replace")
    except LookupError:
        html = html_bytes.decode("utf-8", errors="replace")
    return html, final_url


@app.get("/", tags=["meta"])
async def root():
    return {
        "service": "Link Preview API",
        "usage": "/preview?url=https://example.com",
        "docs": "/docs",
    }


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}


@app.get("/preview", response_model=PreviewResponse, tags=["preview"])
async def preview(url: HttpUrl = Query(..., description="The URL to generate a preview for")):
    url_str = str(url)

    cached = _cache.get(url_str)
    if cached and (time.time() - cached[0]) < CACHE_TTL_SECONDS:
        return cached[1]

    html, final_url = await _fetch_html(url_str)
    soup = BeautifulSoup(html, "lxml")

    title = (
        _meta(soup, prop="og:title")
        or _meta(soup, name="twitter:title")
        or (soup.title.string if soup.title else None)
    )
    description = (
        _meta(soup, prop="og:description")
        or _meta(soup, name="twitter:description")
        or _meta(soup, name="description")
    )
    image = _meta(soup, prop="og:image") or _meta(soup, name="twitter:image")
    if image:
        image = urljoin(final_url, image)
    site_name = _meta(soup, prop="og:site_name") or urlparse(final_url).netloc
    favicon = _extract_favicon(soup, final_url)

    result = PreviewResponse(
        url=url_str,
        final_url=final_url,
        title=_clean(title),
        description=_clean(description),
        image=image,
        favicon=favicon,
        site_name=_clean(site_name),
    ).model_dump()

    _cache[url_str] = (time.time(), result)
    return result
