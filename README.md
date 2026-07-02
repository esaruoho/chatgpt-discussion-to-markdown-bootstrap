# chatgpt-discussion-to-markdown-bootstrap

**Download a FULL ChatGPT conversation as clean markdown, from a share URL. One file. Zero
dependencies. Zero tokens. Zero round-trips.**

Give it a ChatGPT *share* link; get a `conversation.md`. No more "open the page → scroll to the top
→ scroll to the bottom → select all → copy → paste into another chat." The whole conversation is
already embedded in the shared page — this just decodes it. No API key, no login, no LLM.

```bash
python3 chatgpt-bootstrap.py https://chatgpt.com/share/<uuid>            # print markdown
python3 chatgpt-bootstrap.py https://chatgpt.com/share/<uuid>  chat.md   # write chat.md
python3 chatgpt-bootstrap.py --bootstrap                                # print the whole story
```

Python 3.8+ stdlib only. Save it, run it, share it.

## The two share shapes

In ChatGPT, **Share → Create link** turns the conversation into a public snapshot. Two URL shapes,
different behaviour:

| URL shape | What it contains |
|---|---|
| `https://chatgpt.com/share/<uuid>` | the **FULL** conversation — every user / assistant / tool turn |
| `https://chatgpt.com/s/t_…` | a shared **post** snapshot — often only a **slice** (e.g. just the final assistant turn) |

The tool reports the true message count and flags a `/s/` slice honestly. **For the full thread,
share via `/share/<uuid>`.**

## How it works (the one non-obvious bit)

Today's `chatgpt.com` is a **react-router** app. The shared page ships the conversation as a
**turbo-stream**: a flat, index-deduplicated JSON array handed to
`window.__reactRouterContext.streamController.enqueue("[…]")`. Objects are encoded as
`{"_<i>": <j>}` (key = `arr[i]`, value = `arr[j]`); negative integers are null sentinels; references
are shared (deduplicated).

1. **Pull** every `streamController.enqueue("…")` payload; unescape it to a JSON array.
2. **Resolve** the array back into a tree — follow the `{"_i": j}` index references, **memoising on
   index** (shared refs → resolve once; no infinite loops).
3. **Walk** the tree for every node with `author.role` + `content.parts` → that's a message.
4. **Dedup + order.** A turbo-stream references each turn **twice** (a `mapping` node *and* a linear
   chain), as two distinct objects with identical content — so dedup by `(role, text)` and order by
   `create_time`. *(This is the single most common bug when parsing these pages: every message comes
   out doubled. That's why the dedup step is not optional.)*
5. **Fallback.** Older shares embedded a Next.js `<script id="__NEXT_DATA__">` blob instead; the same
   message walker handles it. As of mid-2026, live `/share/` pages use turbo-stream.

Deterministic, free, no model involved.

### Verified on real shares

Tested on real public `/share/<uuid>` links of 8, 26, and 66 turns — full threads, clean alternating
User/ChatGPT pairs, real timestamps, tool turns included. The `/s/` post format carries only the
shared slice, and is labelled as such.

## Limits & honesty

- **`/s/` posts are partial by design** → flagged, not faked. Prefer `/share/<uuid>` for the whole thread.
- **Private / expired links** raise a clear error. Nothing is fabricated.
- **Images / non-text parts** render as a `[content_type]` placeholder.
- If ChatGPT changes its page format, the fix lives in this one file: only the embed-reader (the
  turbo-stream decoder) would change; the message-walk is the stable core.

## Wire it into your own tools

`parse(html, url)` returns `{title, model, messages:[{role, text, create_time, model}], slice}`, and
`to_markdown(convo)` renders it. So you can drop this into a CLI, a chatbot command, or an
email-agent that turns an inbound ChatGPT link into a stored, analysable `conversation.md` — no
manual copy-paste, no tokens spent on extraction.

## The pattern: a "bootstrap"

This is a single, self-contained, self-explaining file that carries a whole idea in a form another
bot or human can run **and** understand from the file alone — idea transfer, not just code transfer.
`python3 chatgpt-bootstrap.py --bootstrap` prints the whole story; the rest of the file *is* the
story, executable.

## Rebuild-from-scratch checklist (for porting)

1. `GET` the share URL with a browser `User-Agent`, follow redirects.
2. Regex out every `streamController.enqueue("(.*?)")` payload; `json.loads(json.loads('"'+p+'"'))`.
3. Resolve `{"_i": j}` index refs → tree, memoising on index, negatives → `None`.
4. Walk for `author.role` + `content.parts`; dedup by `(role, text)`; sort by `create_time`.
5. Fallback: `<script id="__NEXT_DATA__">…</script>` → same walk.
6. Render markdown: title, source, per-turn `## 🧑 User` / `## 🤖 ChatGPT` + text.

## License

MIT — share and improve freely. No warranty, be nice.
