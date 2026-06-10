# fftext

> **Summarize, explain, fact-check, or translate any text, URL, or file. No GPU. No cloud. One command.**

![Python](https://img.shields.io/badge/python-3.9+-blue) ![License](https://img.shields.io/badge/license-Apache--2.0-green) ![Platforms](https://img.shields.io/badge/platforms-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey)

```bash
fftext s https://en.wikipedia.org/wiki/Llama.cpp
```

Three bullet points, streamed to your terminal, generated on your CPU. No API key. No round-trip to anyone's server.

[![Watch the demo](https://img.youtube.com/vi/KnBKJRb43S0/maxresdefault.jpg)](https://www.youtube.com/watch?v=KnBKJRb43S0)

📺 **[Watch the demo on YouTube](https://www.youtube.com/watch?v=KnBKJRb43S0)**

---

## Why fftext

- ⚡ **Fast on CPU.** Powered by a quantized 0.8B Qwen3.5 (Q4_K_M GGUF, ~500 MB) running through `llama.cpp`. Streams tokens as they're generated so you see the answer build, not a spinner. No CUDA. No Metal-only tricks. Plain old cores.
- 🌐 **Files, URLs, or raw strings.** Point it at a `.txt`, paste an article URL, or just type the text inline. URLs get fetched, run through `readability-lxml` for main-content extraction, and stripped to clean prose before the model sees them.
- 📴 **Offline after first run.** The model downloads once to your Hugging Face cache and stays there. Your text never leaves your machine (except for `check`, which needs the web — see below).
- 🪶 **Lean deps.** `llama-cpp-python`, `requests`, `beautifulsoup4`, `readability-lxml`, `lxml`. That's it. No PyTorch, no LangChain, no cloud SDKs.
- 🧠 **Four tasks, four prompts, one binary.** Summarize, explain like I'm five, fact-check against the live web, or translate into any language or register you can describe. Each task is a separate, focused prompt — not one mega-prompt trying to do everything.
- 🗣 **Translate into anything you can describe.** `--lang "formal German"`, `--lang "casual Japanese"`, `--lang "Brazilian Portuguese"` — whatever string you pass goes straight into the prompt. You drive the register and dialect.
- 🔍 **Fact-check with citations.** `fftext check` extracts claims, ranks them, web-searches each one (Mojeek and Startpage, rotated), and labels them SUPPORTED, REFUTED, CONFLICTING, or INSUFFICIENT — with a source URL per claim. CPU-only, no API key, no Google.

---

## Quickstart

```bash
# Install
pip install .

# Try the four tasks
fftext s notes.txt                                       # summarize a file
fftext e https://en.wikipedia.org/wiki/Photosynthesis    # ELI5 a URL
fftext c "The Eiffel Tower was built in 1822."           # fact-check a string
fftext t --lang "French" "How are you today?"            # translate
```

First run downloads ~500 MB of model weights. Every run after is offline (except `check`, which searches the web).

---

## The four tasks

| Subcommand     | Alias(es) | What it does                                                         |
|----------------|-----------|----------------------------------------------------------------------|
| `summarize`    | `s`       | Three short bullet points. Concrete and specific, no preamble.        |
| `explain`     | `e`, `eli5` | Plain-language explanation, 4–6 sentences, like to a curious kid.   |
| `check`        | `c`       | Extract claims → web-search each → label SUPPORTED / REFUTED / CONFLICTING / INSUFFICIENT. |
| `translate`    | `t`       | Translate into any language/register you describe via `--lang`.       |

Every task accepts the same three input shapes — file, URL, or raw string — resolved in that order.

---

## Usage

```bash
# Summarize anything
fftext s notes.txt
fftext s https://example.com/post
fftext s "Paste a long block of text right here on the command line."
cat notes.txt | fftext s                               # read from stdin
echo "clouds can weight more than a ton" | fftext c -  # "-" is stdin too, for any subcommand

# Explain it like I'm ten
fftext e paper.pdf.txt
fftext eli5 https://en.wikipedia.org/wiki/Quantum_entanglement

# Fact-check
fftext c article.txt
fftext c "The Roman Empire fell in 476 AD."
fftext c --debug article.txt          # show ranking, queries, snippets, raw verdicts

# Translate
fftext t hello.txt                                            # defaults to English
fftext t --lang "formal German" hello.txt
fftext t --lang "casual Japanese" "How are you today?"
fftext t --lang "polite Brazilian Portuguese" letter.txt
fftext t -l "Egyptian Arabic" "Where is the train station?"
```

---

## Input handling

`<input>` for any subcommand is resolved in this order:

1. **`-` (a dash), or omitted entirely while stdin is piped** → read from stdin as UTF-8 (errors replaced). This lets fftext work as a Unix filter: `cat notes.txt | fftext s`. A bare `-` always reads stdin; omitting the argument reads stdin only when it's piped — on an interactive terminal an omitted argument prints usage instead of blocking on a read that would never return.
2. **Starts with `http://` or `https://`** → fetched with `requests`, parsed with `readability-lxml` to isolate the main article body, then stripped to plain text with paragraph breaks preserved. Falls back to a light tag-strip if readability can't find an article (common on docs pages and indexes).
3. **Looks like an existing file path** → read as UTF-8 (errors replaced).
4. **Anything else** → treated literally as a string.

Long inputs are head-and-tail clipped to ~10,000 characters (~2,500 tokens) so prompt + generation + chat template fit comfortably in the 4,096-token context. You'll see a `[note: input clipped...]` line on stderr when that happens. The clip keeps the start and end of the document, which preserves intros and conclusions — what summaries and explanations care about most.

---

## Output

Streamed to stdout as it's generated. Notes and timing info go to stderr, so you can pipe just the answer:

```bash
fftext s long-doc.txt > summary.txt
fftext t --lang French letter.txt | tee letter.fr.txt
```

### Summarize

```
- The author argues that small local models are now good enough for routine text tasks.
- Speed gains come from quantization and streaming, not better hardware.
- The main remaining gap is multilingual quality below 7B parameters.
```

### Explain

```
A neural network is like a giant calculator that learns by example. You show it lots
of pictures of cats and dogs, and it slowly figures out which patterns mean "cat" and
which mean "dog." Each time it gets one wrong, it nudges its internal numbers a tiny
bit so it'll do better next time. After millions of nudges, it gets pretty good.
```

### Check

One line per claim, with a verdict label and the top supporting URL:

```
SUPPORTED     The Eiffel Tower was completed in 1889.  [https://en.wikipedia.org/wiki/Eiffel_Tower]
REFUTED       It was built by Thomas Edison.  [https://www.britannica.com/biography/Gustave-Eiffel]
INSUFFICIENT  It is currently the tallest structure in Paris.  [-]
```

Run with `-v` for timings and `--debug` to see ranked claims, generated search queries, raw snippets, and the model's reasoning before each verdict.

### Translate

The translation, and nothing else. No "Here's the translation:" preamble, no original text echoed back, no transliteration unless the target language genuinely calls for it. Paragraph breaks and markdown formatting are preserved.

---

## Flags

| Flag                   | Description                                                                |
|------------------------|----------------------------------------------------------------------------|
| `-v`, `--verbose`      | Print timing info to stderr (token rate, per-stage timings on `check`).    |
| `-d`, `--debug`        | `check` only. Dump claims, queries, snippets, verdicts, and dropped reasons. |
| `-l`, `--lang`         | `translate` only. Target language description. Default: English.            |
| `-h`, `--help`         | Show usage and exit.                                                       |

Flags can appear anywhere on the command line. The subcommand has to come first.

---

## How it works

### `summarize` / `explain` / `translate`

One LLM call, streamed. The whole trick is keeping the system prompt short — a 0.8B model gets confused by long instructions and burns tokens echoing them back. Each task has its own tight system prompt (3–4 lines) and a sane `max_tokens` cap so the model doesn't ramble. Sampling is `temperature=0.3, top_p=0.9, repeat_penalty=1.1` — faithful, not creative.

### `check` — the interesting one

Per run:

1. **Extract claims.** LLM emits a JSON array of factual statements (names, numbers, dates, roles, events). Robust parser tolerates trailing commas, smart quotes, missing brackets, and falls through to a numbered-list scrape if the JSON is hopeless. Deduped against normalized lowercase + whitespace.
2. **Rank.** LLM picks the top three most fact-checkable claims out of up to twelve. Each surviving claim costs ~4 more LLM calls, so ranking 9→3 saves ~24 calls.
3. **Rewrite as keyword queries.** One LLM call per claim turns `"James Talarico is a Presbyterian seminarian."` into `"James Talarico" Presbyterian seminarian`. Real search engines weight rare tokens; sending whole sentences with stopwords tanks recall. Heuristic stopword-strip fallback if the rewrite looks suspicious.
4. **Search.** Mojeek and Startpage, rotated by claim index, with fallback to the other on empty. Jittered sleeps and a generic desktop UA. Sanitized queries to avoid tripping WAFs on `$`, backticks, pipes, etc. Eight-thread pool, ~8s timeout per request.
5. **Summarize evidence.** LLM compresses each snippet into one sentence about the claim. Irrelevant snippets are dropped here, not at the judge stage.
6. **Synthesize.** LLM lays out what supports, what contradicts, and what's missing — short and structured.
7. **Evaluate.** Deterministic shortcuts handle the obvious cases (no support → REFUTED; nothing either way → INSUFFICIENT). Genuinely mixed evidence goes to one more LLM call with `<think>` reasoning enabled, picking one of four labels.

Per-claim total: about four LLM calls and one search round-trip. The ranker keeps the bill from exploding on long inputs.

---

## Performance notes

- **Threads.** Detected from `os.cpu_count()` and halved — `os.cpu_count()` returns logical cores, and oversubscribing hyperthreads runs slower than just using the physical ones. Override with `QWEN_THREADS=N` if you know your physical core count and want to skip the heuristic.
- **Context.** Fixed at 4,096 tokens. Per-token generation cost scales with *filled* context, not the cap, so the cap itself is nearly free — what costs you is filling it via bigger inputs. The 10,000-character clip keeps that under control.
- **Streaming.** Matters more on CPU than on GPU. Total latency is what it is, but perceived latency drops a lot when the first token arrives in under a second.
- **C-level log silencing.** `llama.cpp` prints warnings via C `printf` that bypass Python's `verbose=False`. fftext installs a null log callback to kill the `n_ctx_seq < n_ctx_train` nag and friends. Trade-off: real C-level errors get swallowed too, but Python-level exceptions still propagate fine.

---

## Model & cache

The default model is `unsloth/Qwen3.5-0.8B-GGUF` (`Qwen3.5-0.8B-Q4_K_M.gguf`, ~500 MB), downloaded on first run via `huggingface-hub` to your standard HF cache:

- **macOS / Linux** — `~/.cache/huggingface/hub/`
- **Windows** — `%USERPROFILE%\.cache\huggingface\hub\`

To use a different GGUF model, edit `load_model()` in `llm.py` and swap the `repo_id` / `filename`. Anything `llama.cpp` ≥ the bundled version can load (Qwen, Llama, Mistral, Gemma, Phi, etc.) should work, but the prompt templates and stop sequences are tuned for the Qwen3.5 chat format — your mileage on other families will vary.

---

## Legacy demo modes

Before fftext had subcommands it was a small wrapper around `llama-cpp-python` for testing. Those modes still work:

```bash
python main.py                            # canned demo prompt
python main.py "your prompt here"         # one-shot
python main.py -i                         # interactive chat (Ctrl-C to quit)
```

Mostly useful for sanity-checking the model load and sampling parameters when you change something.

---

## Notes & limits

- **0.8B is small.** It's good enough for the four tasks above, and it's fast enough to actually be useful on a laptop. But it's not GPT-4. Long, complex documents get clipped, and the model occasionally hallucinates on edge-case claims. `check` exists precisely because the model can't be trusted as a one-shot oracle — let it propose, let the web dispose.
- **`check` depends on scraping.** Mojeek and Startpage rotate, with jittered sleeps and a desktop UA, but if both go down or both start serving captchas you'll see empty results and `INSUFFICIENT` verdicts. Run with `--debug` to confirm whether you're being blocked vs. just hitting a thin topic.
- **Translation works best between major languages.** A 0.8B model handles English ↔ French, Spanish, German, Italian, Portuguese, and Chinese well; smaller languages and complex register requests degrade more.
- **URL parsing is best-effort.** `readability-lxml` is strong on articles, weaker on docs pages, listings, and SPAs. The fallback tag-strip catches the rest. If you get garbage out of a particular URL, save the page as text first and pass the file.

---

## License

Apache-2.0 for this project. The Qwen3.5 model is distributed under its own license — see the [model card](https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF). Powered by [llama.cpp](https://github.com/ggerganov/llama.cpp) via [llama-cpp-python](https://github.com/abetlen/llama-cpp-python), with URL parsing courtesy of [readability-lxml](https://github.com/buriy/python-readability).
