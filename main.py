"""fftext — tiny local-LLM text helper.

Subcommands (with single-letter aliases):

  fftext summarize <input>            (alias: s)
  fftext explain   <input>            (alias: e, eli5)
  fftext check     <input>            (alias: c)
  fftext translate [--lang "..."] <input>   (alias: t)

<input> is one of:
  - a path to an existing file -> read as UTF-8
  - a URL (http:// or https://) -> fetched, parsed via readability-lxml,
    HTML tags stripped, visible newlines preserved
  - "-" (a dash), or omitted entirely while stdin is piped -> read stdin
  - any other string -> treated literally

Legacy demo modes (no subcommand):
  python main.py                  # demo prompt
  python main.py "your prompt"    # one-shot
  python main.py -i               # interactive

Flags (anywhere):
  -v / --verbose                  # show timing info
  -d / --debug                    # dump raw LLM output (check only)
"""

import re
import sys
from pathlib import Path

import requests

from llm import load_model, demo_oneshot, demo_interactive
from summarize import task_summarize
from explain import task_explain
from check import task_check
from translate import task_translate


# --- input handling ---------------------------------------------------------

# Generic desktop UA so sites don't auto-block as obvious bot. Same UA the
# search backends use; consistency is fine since the operator is the user.
_FETCH_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_FETCH_HEADERS = {"User-Agent": _FETCH_UA, "Accept-Language": "en-US,en;q=0.9"}
_FETCH_TIMEOUT = 15  # seconds — generous since this is one-shot per run

_URL_RE = re.compile(r"^https?://", re.I)


def _looks_like_path(s: str) -> bool:
    """Cheap pre-check before stat(). A path component over 255 bytes raises
    ENAMETOOLONG on Linux, and newlines never appear in real paths."""
    if "\n" in s or "\x00" in s:
        return False
    # Check each component against the 255-byte filesystem limit.
    for part in s.replace("\\", "/").split("/"):
        if len(part.encode("utf-8", errors="replace")) > 255:
            return False
    return True


def _fetch_url(url: str) -> tuple[str, str]:
    """Fetch a URL, extract the main article with readability-lxml, and
    return (plain_text, source_label).

    readability-lxml gives us the article body as cleaned HTML; we then
    strip tags to plain text but preserve block boundaries as '\\n' so
    paragraphs don't collapse into one wall of words. Falls back to the
    raw page if readability can't isolate an article (common on docs
    pages, indexes, and very short posts).
    """
    # Import locally so users who never hit a URL don't pay the import cost
    # or need readability installed.
    try:
        from readability import Document
    except ImportError:
        print("fftext: URL input requires readability-lxml. "
              "Install with: pip install readability-lxml lxml",
              file=sys.stderr)
        sys.exit(2)

    try:
        from lxml import html as lxml_html
    except ImportError:
        print("fftext: URL input requires lxml. "
              "Install with: pip install lxml",
              file=sys.stderr)
        sys.exit(2)

    try:
        r = requests.get(url, headers=_FETCH_HEADERS, timeout=_FETCH_TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"fftext: failed to fetch {url}: {e}", file=sys.stderr)
        sys.exit(1)

    # readability handles encoding detection internally; pass it the raw
    # response text and a title to anchor against. The library wraps the
    # article body in <html><body>...</body></html>.
    doc = Document(r.text)
    article_html = doc.summary(html_partial=True) or r.text
    title = (doc.short_title() or "").strip()

    # Parse the article HTML and convert to plain text. We replace block-
    # level elements with explicit newlines BEFORE text-extraction so
    # paragraph and list breaks survive. Without this, lxml's text_content()
    # would smash everything into a single space-separated blob.
    try:
        tree = lxml_html.fromstring(article_html)
    except (ValueError, lxml_html.etree.ParserError):
        # Some pages produce HTML lxml can't parse — fall back to the raw
        # response text after a light tag-strip.
        return _strip_html_fallback(r.text), url

    # Drop scripts/styles outright — they're never article content.
    for el in tree.xpath("//script | //style | //noscript"):
        el.getparent().remove(el)

    # Append a newline after each block-level element so .text_content()
    # produces something readable instead of one giant line.
    _BLOCK_TAGS = {
        "p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
        "blockquote", "pre", "hr", "section", "article", "header", "footer",
        "ul", "ol", "table",
    }
    for el in tree.iter():
        if el.tag in _BLOCK_TAGS:
            # Use tail because that's where text BETWEEN siblings lives.
            el.tail = (el.tail or "") + "\n"

    text = tree.text_content()
    # Collapse runs of horizontal whitespace within lines but keep newlines.
    # Then collapse 3+ blank lines down to 2 — keeps paragraph breaks
    # visible without bloating the input character budget.
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    label = f"{title} <{url}>" if title else url
    return text, label


def _strip_html_fallback(html_text: str) -> str:
    """Crude tag-strip for when lxml can't parse the page. Preserves
    newlines on block-level tag boundaries before stripping everything
    else. Used only when the structured path fails."""
    # Insert newlines at block-level boundaries.
    html_text = re.sub(
        r"</?(p|br|div|li|tr|h[1-6]|blockquote|pre|hr|section|article|"
        r"header|footer|ul|ol|table)[^>]*>",
        "\n", html_text, flags=re.I,
    )
    # Drop script/style blocks entirely.
    html_text = re.sub(r"<script[^>]*>.*?</script>", "",
                       html_text, flags=re.S | re.I)
    html_text = re.sub(r"<style[^>]*>.*?</style>", "",
                       html_text, flags=re.S | re.I)
    # Remove remaining tags.
    text = re.sub(r"<[^>]+>", "", html_text)
    # Whitespace cleanup.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def resolve_input(arg: str) -> tuple[str, str]:
    """Return (text, source_label).

    Resolution order:
      1. "-" (dash) -> read stdin.
      2. http:// or https:// prefix -> fetch + readability parse.
      3. Existing file path -> read as UTF-8.
      4. Anything else -> literal string.
    """
    # 1. Explicit stdin sentinel.
    if arg == "-":
        return sys.stdin.buffer.read().decode("utf-8", errors="replace"), "<stdin>"

    # 2. URL.
    if _URL_RE.match(arg):
        return _fetch_url(arg)

    # 3. File path.
    if _looks_like_path(arg):
        try:
            p = Path(arg)
            if p.is_file():
                return p.read_text(encoding="utf-8", errors="replace"), str(p)
        except OSError:
            # Any stat-level failure -> fall through and treat as a string.
            pass

    # 4. Literal string.
    return arg, "<string>"


# --- CLI --------------------------------------------------------------------

USAGE = """\
fftext - tiny local-LLM text helper

  fftext summarize <file|url|string>          (alias: s)
  fftext explain   <file|url|string>          (alias: e, eli5)
  fftext check     <file|url|string>          (alias: c)
  fftext translate [--lang "<target>"] <file|url|string>   (alias: t)

Input is a file, URL, literal string, or "-"/omitted to read stdin.

Examples:
  fftext s notes.txt
  fftext e https://example.com/post
  cat notes.txt | fftext s                     # read piped stdin (or pass "-")
  fftext t hello.txt                          # defaults to English
  fftext t --lang "Castilian Spanish" hello.txt
  fftext t --lang "casual Japanese" "How are you today?"

Legacy demo modes:
  python main.py                  # demo prompt
  python main.py "your prompt"    # one-shot
  python main.py -i               # interactive

Flags (anywhere):
  -v / --verbose                  # show timing info
  -d / --debug                    # dump raw LLM output (check only)
"""

# Subcommand canonicalization. Aliases collapse to canonical names.
_ALIASES = {
    "s": "summarize", "summarize": "summarize",
    "e": "explain", "eli5": "explain", "explain": "explain",
    "c": "check", "check": "check",
    "t": "translate", "translate": "translate",
}


def _extract_lang_flag(args: list[str]) -> tuple[str, list[str]]:
    """Pull --lang/--language from args. Supports both '--lang X' and
    '--lang=X'. Returns (lang_value, args_without_lang). Empty string
    if not present — task_translate defaults to English in that case."""
    out: list[str] = []
    lang = ""
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--lang", "--language", "-l"):
            if i + 1 >= len(args):
                print(f"fftext: {a} needs a value", file=sys.stderr)
                sys.exit(2)
            lang = args[i + 1]
            i += 2
            continue
        if a.startswith("--lang="):
            lang = a.split("=", 1)[1]
            i += 1
            continue
        if a.startswith("--language="):
            lang = a.split("=", 1)[1]
            i += 1
            continue
        out.append(a)
        i += 1
    return lang, out


def main() -> None:
    args = sys.argv[1:]

    # Global boolean flags come out first so they can appear anywhere.
    verbose = False
    for flag in ("-v", "--verbose"):
        while flag in args:
            verbose = True
            args.remove(flag)

    debug = False
    for flag in ("-d", "--debug"):
        while flag in args:
            debug = True
            args.remove(flag)

    if args and args[0] in ("-h", "--help"):
        print(USAGE)
        return

    # fftext subcommands (canonical + aliases).
    if args and args[0] in _ALIASES:
        cmd = _ALIASES[args[0]]
        rest = args[1:]

        # Translate has its own flag (--lang), pull it out before
        # input-joining so it doesn't end up concatenated into the text.
        lang = ""
        if cmd == "translate":
            lang, rest = _extract_lang_flag(rest)

        if not rest:
            # No arg: treat piped stdin as the input. On a TTY there's
            # nothing piped and a read would hang, so that's a usage error.
            if not sys.stdin.isatty():
                rest = ["-"]
            else:
                print(f"fftext: '{cmd}' needs a filepath, URL, string, "
                      f"or '-' for stdin\n\n{USAGE}", file=sys.stderr)
                sys.exit(2)

        # Join trailing args so unquoted multi-word strings still work,
        # but ONLY if the first arg doesn't look like a file or URL —
        # otherwise we'd corrupt the path/URL with appended junk.
        first = rest[0]
        if len(rest) == 1 or _URL_RE.match(first) or _looks_like_path(first):
            arg = first
        else:
            arg = " ".join(rest)

        text, source = resolve_input(arg)
        llm = load_model()

        if cmd == "summarize":
            task_summarize(llm, text, source, verbose)
        elif cmd == "explain":
            task_explain(llm, text, source, verbose)
        elif cmd == "check":
            task_check(llm, text, source, verbose, debug=debug)
        elif cmd == "translate":
            task_translate(llm, text, source, lang, verbose)
        return

    # Legacy paths
    llm = load_model()
    if args and args[0] in ("-i", "--interactive"):
        demo_interactive(llm, verbose)
        return

    prompt = " ".join(args) if args else "In one sentence, what is llama.cpp?"
    demo_oneshot(llm, prompt, verbose)


if __name__ == "__main__":
    main()
