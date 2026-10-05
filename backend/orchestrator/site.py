"""Read the product's start page as plain text, so a manual with only a URL still gives the main agent something to read.

A single HTTP GET (not a browser session): redirects are followed only inside allowed_domains, the body is capped,
and failures are recorded rather than raised. Script-rendered pages yield little text; that is reported, not hidden.
"""

import html
import re
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 2_000_000
MAX_TEXT = 6000
REDIRECTS = 5


def page_text(markup):
    title = re.search(r"<title[^>]*>(.*?)</title>", markup, flags=re.S | re.I)
    description = re.search(r"<meta[^>]+name=[\"']description[\"'][^>]*content=[\"']([^\"']*)", markup, flags=re.I)
    body = re.sub(r"<(script|style|noscript|svg|template)\b.*?</\1>", " ", markup, flags=re.S | re.I)
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    body = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"\s+", " ", html.unescape(body)).strip()
    return {"title": html.unescape(title[1]).strip() if title else "", "description": html.unescape(description[1]).strip() if description else "",
            "text": text[:MAX_TEXT], "truncated": len(text) > MAX_TEXT}


async def read_site(url, allowed_domains, transport=None):
    """{"status": "ok"|"failed", "url", "title", "description", "text", "truncated"} or {"status": "failed", "reason"}."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False, transport=transport,
                                     headers={"User-Agent": "muchhuman-phase1/1.0"}) as client:
            for _ in range(REDIRECTS + 1):
                if urlsplit(url).hostname not in allowed_domains:
                    return {"status": "failed", "url": url, "reason": "跳转到了 allowed_domains 之外，未读取"}
                async with client.stream("GET", url) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    if response.status_code >= 400:
                        return {"status": "failed", "url": url, "reason": f"HTTP {response.status_code}"}
                    if "html" not in response.headers.get("content-type", "html"):
                        return {"status": "failed", "url": url, "reason": "首页不是 HTML"}
                    content = b""
                    async for chunk in response.aiter_bytes():
                        content += chunk
                        if len(content) > MAX_BYTES:
                            break
                    markup = content[:MAX_BYTES].decode(response.encoding or "utf-8", errors="replace")
                    result = {"status": "ok", "url": url, **page_text(markup)}
                    if len(result["text"]) < 200:
                        result["note"] = "首页几乎没有静态文字（可能由脚本渲染），AI 能读到的产品信息很少"
                    return result
            return {"status": "failed", "url": url, "reason": "跳转次数过多"}
    except httpx.HTTPError as error:
        return {"status": "failed", "url": url, "reason": type(error).__name__}
