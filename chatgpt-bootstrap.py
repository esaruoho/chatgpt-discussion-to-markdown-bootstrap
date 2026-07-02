#!/usr/bin/env python3
"""Convey Bootstrap — chatgpt-to-markdown. Download a FULL ChatGPT conversation as clean
markdown, from a share URL. ONE self-contained file: the tool AND its own bootstrap story.

This is a *convey bootstrap*: a single, whitelabeled, zero-dependency artifact that carries a
whole idea — runnable AND self-explaining — so it can be handed to another bot or human and adopted
immediately. `python3 chatgpt-bootstrap.py --bootstrap` prints the full story; the rest of this
file IS the story, executable.

Zero dependencies (Python 3.8+ stdlib only). Zero tokens. Zero round-trips. It does NOT call any
LLM — the whole conversation is already embedded in the shared page; this just decodes it.

    python3 chatgpt-bootstrap.py https://chatgpt.com/share/<uuid>          # -> prints markdown
    python3 chatgpt-bootstrap.py https://chatgpt.com/share/<uuid> out.md   # -> writes out.md
    python3 chatgpt-bootstrap.py https://chatgpt.com/s/t_...               # a shared post (may be a slice)
    python3 chatgpt-bootstrap.py --bootstrap                               # -> print the full bootstrap doc

Why this exists: to stop the manual labour of opening a ChatGPT share link, scrolling to the top,
scrolling to the bottom, selecting everything, and pasting it into another chat. Give it the URL;
get conversation.md.

Handles both share shapes ChatGPT emits today:
  • /share/<uuid>  — the FULL conversation (every user/assistant/tool turn)
  • /s/t_…         — a shared "post" snapshot, which often carries only a SLICE (e.g. the final
                     assistant turn). We report the true message count; we never pretend a slice
                     is the whole thread.

How it works (the one non-obvious bit): current chatgpt.com is a react-router app. The page ships
the conversation as a "turbo-stream" — a flat, index-deduplicated JSON array fed to
`window.__reactRouterContext.streamController.enqueue("[…]")`. Objects in it are encoded as
`{"_<i>": <j>}` meaning key = arr[i], value = arr[j]; negative integers are null sentinels. We
resolve that array back into a tree (memoising on index, since references are shared), then walk it
for every node that has `author.role` + `content.parts`. A turbo-stream references each turn TWICE
(a `mapping` node and a linear chain), so we dedup by (role, text). Older pages used a Next.js
`__NEXT_DATA__` blob instead; that path is kept as a fallback.

Share and improve freely. MIT-spirit: no warranty, be nice.
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone

# The full bootstrap story, embedded so ONE file conveys the whole idea. `--bootstrap` prints this.
# Whitelabeled: nothing here depends on any private infra — it runs anywhere Python does.
BOOTSTRAP = r"""
# Convey Bootstrap — chatgpt-to-markdown

**Zero dependencies. Zero tokens. Zero round-trips.** Give it a ChatGPT *share* link; get a clean
`conversation.md`. No more "open the page -> scroll to the top -> scroll to the bottom -> select all
-> copy -> paste into another chat." The whole conversation is already embedded in the shared page;
this just decodes it. No API key, no login, no LLM.

## What this IS (the pattern)
A *convey bootstrap* = a single, whitelabeled, zero-dependency file that carries a whole idea in a
form another bot or human can run AND understand from the file alone. Idea transfer, not just code
transfer. This one instantiates the pattern for "download a ChatGPT conversation as markdown."

## Use it
    python3 chatgpt-bootstrap.py https://chatgpt.com/share/<uuid>          # print markdown
    python3 chatgpt-bootstrap.py https://chatgpt.com/share/<uuid> out.md   # write out.md
    python3 chatgpt-bootstrap.py --bootstrap                               # print this doc

## Two share shapes
  * https://chatgpt.com/share/<uuid>   the FULL conversation (every user/assistant/tool turn)
  * https://chatgpt.com/s/t_...        a shared "post" snapshot, often only a SLICE (e.g. the last
                                       assistant turn). Reported honestly; never dressed up as whole.

## How it works
Today's chatgpt.com is a react-router app. The shared page ships the conversation as a
*turbo-stream*: a flat, index-deduplicated JSON array handed to
`window.__reactRouterContext.streamController.enqueue("[...]")`. Objects are encoded as
`{"_<i>": <j>}` (key = arr[i], value = arr[j]); negative ints are null sentinels; refs are shared.
  1. Pull every `streamController.enqueue("...")` payload; unescape to a JSON array.
  2. Resolve `{"_i": j}` index refs back into a tree, memoising on index (no infinite loops).
  3. Walk for every node with author.role + content.parts -> that's a message.
  4. Dedup by (role, text) — a turbo-stream references each turn TWICE (a mapping node AND a linear
     chain), so without this every message comes out doubled. Order by create_time.
  5. Fallback: an older Next.js `<script id="__NEXT_DATA__">` blob -> same walk.

## Limits & honesty
  * /s/ posts are partial by design -> flagged, not faked. Prefer /share/<uuid> for the whole thread.
  * Private/expired links raise a clear error. Nothing is fabricated.
  * Images/non-text parts render as a [content_type] placeholder.
  * If ChatGPT changes its page format, the fix lives in this one file: only the embed-reader (the
    turbo-stream decoder) would change; the message-walk is the stable core.

## Rebuild-from-scratch checklist (for a friend or a bot porting this)
  1. GET the share URL with a browser User-Agent; follow redirects.
  2. Regex out streamController.enqueue("(.*?)"); json.loads(json.loads('"'+p+'"')).
  3. Resolve {"_i": j} refs -> tree, memoise on index, negatives -> None.
  4. Walk for author.role + content.parts; dedup by (role, text); sort by create_time.
  5. Fallback: <script id="__NEXT_DATA__">...</script> -> same walk.
  6. Render markdown: title, source, per-turn "## User" / "## ChatGPT" + text.

Share and improve freely. MIT-spirit: no warranty, be nice.
""".strip()

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
ROLE_LABEL = {"user": "🧑 User", "assistant": "🤖 ChatGPT", "system": "⚙️ System", "tool": "🔧 Tool"}


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _decode_turbo_stream(html):
    for raw in re.findall(r'streamController\.enqueue\("((?:[^"\\]|\\.)*)"\)', html):
        try:
            arr = json.loads(json.loads('"' + raw + '"'))
        except Exception:
            continue
        if not isinstance(arr, list) or not arr:
            continue
        memo = {}

        def resolve(i):
            if isinstance(i, int) and i < 0:
                return None
            if not isinstance(i, int):
                return i
            if i in memo:
                return memo[i]
            memo[i] = None
            v = arr[i]
            if isinstance(v, dict):
                out = {}
                for k, val in v.items():
                    key = arr[int(k[1:])] if isinstance(k, str) and k.startswith("_") else k
                    out[key] = resolve(val)
            elif isinstance(v, list):
                out = [resolve(x) for x in v]
            else:
                out = v
            memo[i] = out
            return out

        tree = resolve(0)
        if tree is not None:
            yield tree


def _decode_next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if m:
        try:
            yield json.loads(m.group(1))
        except Exception:
            pass


def _part_text(parts):
    out = []
    for p in parts or []:
        if isinstance(p, str):
            out.append(p)
        elif isinstance(p, dict):
            t = p.get("text") or p.get("content_type") or ""
            if t:
                out.append(f"[{t}]" if t == p.get("content_type") else t)
    return "\n".join(out).strip()


def _collect_messages(tree):
    found, order = {}, []

    def walk(o):
        if isinstance(o, dict):
            au, ct = o.get("author"), o.get("content")
            if isinstance(au, dict) and "role" in au and isinstance(ct, dict):
                text = _part_text(ct.get("parts"))
                if text:
                    role = au.get("role") or "assistant"
                    key = (role, re.sub(r"\s+", " ", text).strip())
                    if key not in found:
                        found[key] = {"role": role, "text": text,
                                      "create_time": o.get("create_time"),
                                      "model": (o.get("metadata") or {}).get("resolved_model_slug")
                                               or o.get("model_slug")}
                        order.append(key)
                    else:
                        cur = found[key]
                        if cur.get("create_time") is None:
                            cur["create_time"] = o.get("create_time")
                        if not cur.get("model"):
                            cur["model"] = (o.get("metadata") or {}).get("resolved_model_slug")
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(tree)
    msgs = [found[k] for k in order]
    msgs.sort(key=lambda m: (m.get("create_time") is None, m.get("create_time") or 0))
    return msgs


def _find_title(tree):
    hit = {"t": ""}

    def walk(o, d=0):
        if hit["t"] or d > 12:
            return
        if isinstance(o, dict):
            for k in ("title", "text", "og_title"):
                v = o.get(k)
                if isinstance(v, str) and v.strip() and v.strip().lower() != "check out this chat":
                    hit["t"] = v.strip(); return
            for v in o.values():
                walk(v, d + 1)
        elif isinstance(o, list):
            for v in o:
                walk(v, d + 1)

    walk(tree)
    return hit["t"]


def parse(html, url=""):
    best, title = [], ""
    for decoder in (_decode_turbo_stream, _decode_next_data):
        for tree in decoder(html):
            msgs = _collect_messages(tree)
            if len(msgs) > len(best):
                best, title = msgs, _find_title(tree) or title
        if best:
            break
    if not best:
        raise ValueError("no conversation found (link may be private, expired, or an unknown format)")
    model = next((m["model"] for m in best if m.get("role") == "assistant" and m.get("model")), None)
    return {"url": url, "title": title or "ChatGPT conversation", "model": model,
            "messages": best, "slice": bool(url and "/s/" in url)}


def to_markdown(convo):
    def ts(t):
        if not isinstance(t, (int, float)):
            return ""
        try:
            return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            return ""
    lines = [f"# {convo['title']}", ""]
    if convo.get("url"):
        lines.append(f"- **Source:** {convo['url']}")
    if convo.get("model"):
        lines.append(f"- **Model:** {convo['model']}")
    lines.append(f"- **Messages:** {len(convo['messages'])}"
                 + ("  _(shared slice — a /s/ post may not be the full thread)_"
                    if convo.get("slice") and len(convo["messages"]) <= 2 else ""))
    lines += [f"- **Hoovered:** {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    for m in convo["messages"]:
        head = f"## {ROLE_LABEL.get(m['role'], m['role'])}"
        if m["role"] == "assistant" and m.get("model"):
            head += f"  ·  `{m['model']}`"
        stamp = ts(m.get("create_time"))
        if stamp:
            head += f"  ·  _{stamp}_"
        lines += [head, "", m["text"], ""]
    return "\n".join(lines).rstrip() + "\n"


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] in ("--bootstrap", "--about", "bootstrap"):
        print(BOOTSTRAP)
        return 0
    url = argv[0]
    out = argv[1] if len(argv) > 1 else None
    convo = parse(fetch(url), url)
    md = to_markdown(convo)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(md)
        note = " (shared slice — may be partial)" if convo["slice"] and len(convo["messages"]) <= 2 else ""
        print(f"wrote {out}  —  {len(convo['messages'])} message(s){note}", file=sys.stderr)
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
