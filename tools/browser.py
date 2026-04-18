"""
Browser automation tools using Playwright.
A single browser instance is shared across tool calls.
"""
import threading

_lock = threading.Lock()
_playwright = None
_browser = None
_page = None


def _ensure_browser(headless=False):
    global _playwright, _browser, _page
    with _lock:
        if _page is None or _page.is_closed():
            from playwright.sync_api import sync_playwright
            _playwright = sync_playwright().start()
            _browser = _playwright.chromium.launch(headless=headless)
            context = _browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            _page = context.new_page()
    return _page


def _launch_browser(p):
    headless = p.get("headless", False)
    page = _ensure_browser(headless=headless)
    return f"Browser launched ({'headless' if headless else 'visible'}) — ready."


def _navigate(p):
    url = p["url"]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    page = _ensure_browser()
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    return f"Navigated to: {page.url}  |  Title: {page.title()}"


def _click_element(p):
    selector = p["selector"]
    page = _ensure_browser()
    page.click(selector, timeout=10000)
    return f"Clicked: {selector}"


def _type_in_element(p):
    selector = p["selector"]
    text = p["text"]
    clear_first = p.get("clear_first", True)
    page = _ensure_browser()
    if clear_first:
        page.fill(selector, text)
    else:
        page.type(selector, text)
    return f"Typed into {selector}: {text[:60]}"


def _get_element_text(p):
    selector = p["selector"]
    page = _ensure_browser()
    elements = page.query_selector_all(selector)
    if not elements:
        return f"No elements found for: {selector}"
    texts = [el.inner_text().strip() for el in elements[:20] if el.inner_text().strip()]
    return "\n".join(texts) if texts else "(no text content)"


def _get_page_content(p):
    max_chars = p.get("max_chars", 6000)
    mode = p.get("mode", "text")
    page = _ensure_browser()
    if mode == "html":
        content = page.content()
    else:
        content = page.inner_text("body") if page.query_selector("body") else ""
    if len(content) > max_chars:
        content = content[:max_chars] + f"\n...(truncated, {len(content)} total chars)"
    return f"URL: {page.url}\nTitle: {page.title()}\n\n{content}"


def _find_elements(p):
    selector = p["selector"]
    page = _ensure_browser()
    elements = page.query_selector_all(selector)
    if not elements:
        return f"No elements found for: {selector}"
    results = []
    for i, el in enumerate(elements[:30]):
        tag = el.evaluate("el => el.tagName.toLowerCase()")
        text = el.inner_text().strip()[:80]
        attrs = el.evaluate("el => el.outerHTML")[:150]
        results.append(f"[{i}] <{tag}> text='{text}'  html={attrs}")
    return "\n".join(results)


def _screenshot_browser(p):
    import tempfile
    from pathlib import Path
    path = p.get("save_path", str(Path(tempfile.gettempdir()) / "jarvis_browser.png"))
    full_page = p.get("full_page", False)
    page = _ensure_browser()
    page.screenshot(path=path, full_page=full_page)
    return f"Browser screenshot saved: {path}"


def _execute_javascript(p):
    code = p["code"]
    page = _ensure_browser()
    result = page.evaluate(code)
    return str(result) if result is not None else "(null)"


def _go_back(p):
    page = _ensure_browser()
    page.go_back()
    return f"Went back to: {page.url}"


def _go_forward(p):
    page = _ensure_browser()
    page.go_forward()
    return f"Went forward to: {page.url}"


def _close_browser(p):
    global _playwright, _browser, _page
    with _lock:
        try:
            if _browser:
                _browser.close()
            if _playwright:
                _playwright.stop()
        except Exception:
            pass
        _playwright = _browser = _page = None
    return "Browser closed."


def _get_current_url(p):
    global _page
    if _page is None or _page.is_closed():
        return "No browser open."
    return f"Current URL: {_page.url}\nTitle: {_page.title()}"


def _wait_for_element(p):
    selector = p["selector"]
    timeout = p.get("timeout", 10000)
    state = p.get("state", "visible")
    page = _ensure_browser()
    page.wait_for_selector(selector, timeout=timeout, state=state)
    return f"Element '{selector}' is now {state}"


def _select_option(p):
    selector = p["selector"]
    value = p["value"]
    page = _ensure_browser()
    page.select_option(selector, value=value)
    return f"Selected '{value}' in {selector}"


def _press_key_browser(p):
    key = p["key"]
    selector = p.get("selector")
    page = _ensure_browser()
    if selector:
        page.press(selector, key)
    else:
        page.keyboard.press(key)
    return f"Pressed key: {key}"


def _scroll_page(p):
    direction = p.get("direction", "down")
    amount = p.get("amount", 500)
    page = _ensure_browser()
    if direction == "down":
        page.evaluate(f"window.scrollBy(0, {amount})")
    elif direction == "up":
        page.evaluate(f"window.scrollBy(0, -{amount})")
    elif direction == "top":
        page.evaluate("window.scrollTo(0, 0)")
    elif direction == "bottom":
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    return f"Scrolled {direction}"


TOOLS = [
    (
        {
            "name": "browser_launch",
            "description": "Launch a browser window. Call this before other browser tools if browser isn't open.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "headless": {"type": "boolean", "description": "Run headless (no window). Default false."}
                },
            },
        },
        _launch_browser,
    ),
    (
        {
            "name": "browser_navigate",
            "description": "Navigate the browser to a URL",
            "input_schema": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "URL to navigate to"}},
                "required": ["url"],
            },
        },
        _navigate,
    ),
    (
        {
            "name": "browser_click",
            "description": "Click an element in the browser using a CSS selector or text",
            "input_schema": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector, e.g. 'button#submit', 'text=Sign in'"}
                },
                "required": ["selector"],
            },
        },
        _click_element,
    ),
    (
        {
            "name": "browser_type",
            "description": "Type text into an input field in the browser",
            "input_schema": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector for the input field"},
                    "text": {"type": "string"},
                    "clear_first": {"type": "boolean", "description": "Clear existing text first (default true)"},
                },
                "required": ["selector", "text"],
            },
        },
        _type_in_element,
    ),
    (
        {
            "name": "browser_get_text",
            "description": "Get text content of element(s) matching a selector",
            "input_schema": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector"}
                },
                "required": ["selector"],
            },
        },
        _get_element_text,
    ),
    (
        {
            "name": "browser_get_page_content",
            "description": "Get the visible text content (or HTML) of the current page",
            "input_schema": {
                "type": "object",
                "properties": {
                    "max_chars": {"type": "integer", "description": "Max characters to return (default 6000)"},
                    "mode": {"type": "string", "enum": ["text", "html"], "description": "Return visible text or raw HTML"},
                },
            },
        },
        _get_page_content,
    ),
    (
        {
            "name": "browser_find_elements",
            "description": "Find elements matching a CSS selector and return their details",
            "input_schema": {
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"],
            },
        },
        _find_elements,
    ),
    (
        {
            "name": "browser_screenshot",
            "description": "Take a screenshot of the browser",
            "input_schema": {
                "type": "object",
                "properties": {
                    "save_path": {"type": "string"},
                    "full_page": {"type": "boolean", "description": "Capture full scrollable page"},
                },
            },
        },
        _screenshot_browser,
    ),
    (
        {
            "name": "browser_execute_js",
            "description": "Execute JavaScript in the browser and return the result",
            "input_schema": {
                "type": "object",
                "properties": {"code": {"type": "string", "description": "JavaScript expression or code block"}},
                "required": ["code"],
            },
        },
        _execute_javascript,
    ),
    (
        {
            "name": "browser_back",
            "description": "Navigate browser back",
            "input_schema": {"type": "object", "properties": {}},
        },
        _go_back,
    ),
    (
        {
            "name": "browser_forward",
            "description": "Navigate browser forward",
            "input_schema": {"type": "object", "properties": {}},
        },
        _go_forward,
    ),
    (
        {
            "name": "browser_current_url",
            "description": "Get the current browser URL and page title",
            "input_schema": {"type": "object", "properties": {}},
        },
        _get_current_url,
    ),
    (
        {
            "name": "browser_wait_for",
            "description": "Wait for an element to appear",
            "input_schema": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "timeout": {"type": "integer", "description": "Timeout in ms (default 10000)"},
                    "state": {"type": "string", "enum": ["visible", "hidden", "attached", "detached"]},
                },
                "required": ["selector"],
            },
        },
        _wait_for_element,
    ),
    (
        {
            "name": "browser_select",
            "description": "Select an option from a <select> dropdown",
            "input_schema": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "value": {"type": "string", "description": "Option value or label"},
                },
                "required": ["selector", "value"],
            },
        },
        _select_option,
    ),
    (
        {
            "name": "browser_press_key",
            "description": "Press a key in the browser (e.g. 'Enter', 'Escape', 'Tab')",
            "input_schema": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "selector": {"type": "string", "description": "Focus element first (optional)"},
                },
                "required": ["key"],
            },
        },
        _press_key_browser,
    ),
    (
        {
            "name": "browser_scroll",
            "description": "Scroll the browser page",
            "input_schema": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down", "top", "bottom"]},
                    "amount": {"type": "integer", "description": "Pixels to scroll (for up/down)"},
                },
            },
        },
        _scroll_page,
    ),
    (
        {
            "name": "browser_close",
            "description": "Close the browser",
            "input_schema": {"type": "object", "properties": {}},
        },
        _close_browser,
    ),
]
