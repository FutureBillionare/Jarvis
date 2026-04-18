"""
Tool: notebooklm_tool
Description: Automate Google NotebookLM via browser — open notebooks, add sources, ask questions.
Uses the existing HUBERT Playwright browser instance.
"""


def _page():
    from tools.browser import _ensure_browser
    return _ensure_browser(headless=False)


def run_open_notebooklm(params):
    page = _page()
    page.goto("https://notebooklm.google.com", wait_until="domcontentloaded", timeout=20000)
    return f"NotebookLM opened. Title: {page.title()}"


def run_list_notebooks(params):
    page = _page()
    if "notebooklm" not in page.url:
        page.goto("https://notebooklm.google.com", wait_until="domcontentloaded", timeout=20000)
    try:
        page.wait_for_selector("[data-testid='notebook-card'], .notebook-title", timeout=8000)
        elements = page.query_selector_all("[data-testid='notebook-card'], .notebook-title")
        names = [el.inner_text().strip() for el in elements if el.inner_text().strip()]
        return "Notebooks:\n" + "\n".join(f"  • {n}" for n in names) if names else "No notebooks found (may need to sign in)."
    except Exception:
        return "Could not find notebooks — check that you are signed in to Google."


def run_open_notebook(params):
    title = params["title"]
    page  = _page()
    if "notebooklm" not in page.url:
        page.goto("https://notebooklm.google.com", wait_until="domcontentloaded", timeout=20000)
    try:
        page.click(f"text={title}", timeout=6000)
        page.wait_for_load_state("domcontentloaded")
        return f"Opened notebook: {title}"
    except Exception:
        return f"Could not find notebook titled '{title}'. Use notebooklm_list_notebooks to see available ones."


def run_add_source_url(params):
    url  = params["url"]
    page = _page()
    try:
        # Look for the "Add source" button
        add_btn = page.query_selector("button:has-text('Add source'), button:has-text('Add')")
        if add_btn:
            add_btn.click()
            page.wait_for_timeout(1000)
        # Look for URL input
        url_input = page.query_selector("input[placeholder*='url' i], input[placeholder*='link' i], input[type='url']")
        if url_input:
            url_input.fill(url)
            page.keyboard.press("Enter")
            page.wait_for_timeout(2000)
            return f"Source URL added: {url}"
        return "Could not find URL input. Notebook may need to be opened first."
    except Exception as e:
        return f"Error adding source: {e}"


def run_ask_notebook(params):
    question = params["question"]
    page     = _page()
    try:
        chat_input = page.query_selector(
            "textarea[placeholder*='Ask' i], textarea[placeholder*='question' i], [contenteditable='true']"
        )
        if not chat_input:
            return "Could not find chat input. Open a notebook first."
        chat_input.fill(question)
        page.keyboard.press("Enter")
        page.wait_for_timeout(4000)
        # Try to grab the last assistant response
        responses = page.query_selector_all("[data-testid='message'], .response-text, .chat-message")
        if responses:
            last = responses[-1].inner_text().strip()
            return last[:2000]
        return "Question sent. Check the NotebookLM window for the response."
    except Exception as e:
        return f"Error asking question: {e}"


TOOLS = [
    ({"name": "notebooklm_open",
      "description": "Open Google NotebookLM in the browser.",
      "input_schema": {"type": "object", "properties": {}}}, run_open_notebooklm),

    ({"name": "notebooklm_list_notebooks",
      "description": "List available notebooks in NotebookLM.",
      "input_schema": {"type": "object", "properties": {}}}, run_list_notebooks),

    ({"name": "notebooklm_open_notebook",
      "description": "Open a specific notebook by title.",
      "input_schema": {"type": "object", "properties": {
          "title": {"type": "string", "description": "Notebook title"}
      }, "required": ["title"]}}, run_open_notebook),

    ({"name": "notebooklm_add_source",
      "description": "Add a URL as a source to the currently open NotebookLM notebook.",
      "input_schema": {"type": "object", "properties": {
          "url": {"type": "string", "description": "URL to add as a source"}
      }, "required": ["url"]}}, run_add_source_url),

    ({"name": "notebooklm_ask",
      "description": "Ask a question in the currently open NotebookLM notebook.",
      "input_schema": {"type": "object", "properties": {
          "question": {"type": "string"}
      }, "required": ["question"]}}, run_ask_notebook),
]
