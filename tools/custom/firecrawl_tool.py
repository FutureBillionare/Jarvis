"""
Tool: firecrawl_tool
Description: Web scraping and crawling via Firecrawl — scrape pages, crawl sites, extract structured data.
Requires: FIRECRAWL_API_KEY environment variable.
"""
import os, json


def _client():
    from firecrawl import FirecrawlApp
    key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not key:
        raise RuntimeError("Set the FIRECRAWL_API_KEY environment variable.")
    return FirecrawlApp(api_key=key)


def run_scrape(params):
    url     = params["url"]
    formats = params.get("formats", ["markdown"])
    app     = _client()
    result  = app.scrape_url(url, formats=formats)
    if "markdown" in formats:
        content = result.get("markdown", result.get("content", str(result)))
    else:
        content = json.dumps(result, indent=2, default=str)
    max_chars = params.get("max_chars", 5000)
    if len(content) > max_chars:
        content = content[:max_chars] + f"\n…(truncated, {len(content)} total chars)"
    return content


def run_crawl(params):
    url        = params["url"]
    max_pages  = params.get("max_pages", 5)
    app        = _client()
    result     = app.crawl_url(
        url,
        params={"crawlerOptions": {"maxDepth": params.get("max_depth", 2),
                                    "limit": max_pages}},
        poll_interval=3,
    )
    pages = result.get("data", [])
    if not pages:
        return f"No pages crawled from {url}."
    lines = [f"Crawled {len(pages)} pages from {url}:\n"]
    for i, page in enumerate(pages):
        lines.append(f"[{i+1}] {page.get('url', '?')}")
        content = page.get("markdown", page.get("content", ""))[:300]
        lines.append(f"    {content.replace(chr(10), ' ')[:200]}\n")
    return "\n".join(lines)


def run_extract(params):
    url    = params["url"]
    schema = params.get("schema", {})
    prompt = params.get("prompt", "Extract all relevant structured information from this page.")
    app    = _client()
    result = app.scrape_url(
        url,
        formats=["extract"],
        actions=[],
        extract={"prompt": prompt, "schema": schema} if schema else {"prompt": prompt},
    )
    extracted = result.get("extract", result)
    return json.dumps(extracted, indent=2, default=str)


def run_map_site(params):
    url    = params["url"]
    app    = _client()
    result = app.map_url(url)
    links  = result.get("links", [])
    if not links:
        return f"No links found at {url}."
    return f"Found {len(links)} links at {url}:\n" + "\n".join(f"  {l}" for l in links[:50])


TOOLS = [
    ({"name": "firecrawl_scrape",
      "description": "Scrape a webpage and return its content as clean markdown.",
      "input_schema": {"type": "object", "properties": {
          "url":       {"type": "string"},
          "formats":   {"type": "array", "items": {"type": "string"},
                        "description": "['markdown'] or ['html'] — default markdown"},
          "max_chars": {"type": "integer", "description": "Max characters to return"},
      }, "required": ["url"]}}, run_scrape),

    ({"name": "firecrawl_crawl",
      "description": "Crawl a website and return content from multiple pages.",
      "input_schema": {"type": "object", "properties": {
          "url":       {"type": "string"},
          "max_pages": {"type": "integer", "description": "Max pages to crawl, default 5"},
          "max_depth": {"type": "integer", "description": "Crawl depth, default 2"},
      }, "required": ["url"]}}, run_crawl),

    ({"name": "firecrawl_extract",
      "description": "Extract structured data from a webpage using AI and an optional schema.",
      "input_schema": {"type": "object", "properties": {
          "url":    {"type": "string"},
          "prompt": {"type": "string", "description": "What to extract"},
          "schema": {"type": "object", "description": "JSON Schema for the extracted data"},
      }, "required": ["url"]}}, run_extract),

    ({"name": "firecrawl_map_site",
      "description": "Map all links/URLs on a website.",
      "input_schema": {"type": "object", "properties": {
          "url": {"type": "string"}
      }, "required": ["url"]}}, run_map_site),
]
