"""
Batch extractor for 13ft. Reads URLs/PMIDs (one per line) from a file,
fetches each via the Googlebot-UA technique, and saves both a
self-contained MHTML snapshot (all images/CSS bundled) and a rendered PDF.
"""
import os
import re
import sys
import time
import base64
import hashlib
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

GOOGLEBOT_UA = (
    "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.6533.119 "
    "Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)


def resolve_input(entry: str) -> str:
    entry = entry.strip()
    if not entry:
        return ""
    if entry.isdigit():
        return f"https://pubmed.ncbi.nlm.nih.gov/{entry}/"
    if not entry.startswith("http"):
        return "https://" + entry
    return entry


def safe_name(url: str) -> str:
    parsed = urlparse(url)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", parsed.path).strip("_") or "index"
    host = parsed.netloc.replace(":", "_")
    digest = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{host}__{slug}__{digest}"


def navigate(page, url: str):
    """Load the page. Try networkidle first (waits for all requests to settle);
    fall back to load/domcontentloaded if the site never idles."""
    for wait_state in ("networkidle", "load", "domcontentloaded"):
        try:
            page.goto(url, wait_until=wait_state, timeout=180000)
            return wait_state
        except Exception:
            continue
    raise RuntimeError("all navigation strategies failed")


_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
         "gif": "image/gif", "svg": "image/svg+xml", "webp": "image/webp"}


def save_inlined_html(context, page, out_path: Path) -> tuple[bool, int, str]:
    """Single-file HTML with all <img> srcs replaced by base64 data URIs.
    Opens in any browser from disk — no MHTML viewer needed."""
    try:
        html = page.content()
        srcs = page.eval_on_selector_all(
            "img",
            "els => els.map(e => ({src: e.currentSrc || e.src, srcset: e.srcset}))"
        )
        seen = {}
        for item in srcs:
            src = item["src"]
            if not src or src.startswith("data:") or src in seen:
                continue
            try:
                resp = context.request.get(src, timeout=30000)
                if not resp.ok:
                    continue
                ext = src.rsplit(".", 1)[-1].split("?")[0].lower()
                mime = _MIME.get(ext, resp.headers.get("content-type", "image/jpeg").split(";")[0])
                data = base64.b64encode(resp.body()).decode("ascii")
                seen[src] = f"data:{mime};base64,{data}"
            except Exception:
                continue
        for original, data_uri in seen.items():
            html = html.replace(original, data_uri)
        # Strip srcset so browsers don't try to re-fetch from network
        html = re.sub(r'\s+srcset="[^"]*"', "", html)
        out_path.write_text(html, encoding="utf-8")
        return True, out_path.stat().st_size, f"{len(seen)} imgs inlined"
    except Exception as e:
        return False, 0, str(e)


def save_pdf(page, out_path: Path) -> tuple[bool, int, str]:
    try:
        page.pdf(
            path=str(out_path),
            format="Letter",
            print_background=True,
            margin={"top": "0.5in", "bottom": "0.5in", "left": "0.5in", "right": "0.5in"},
        )
        return True, out_path.stat().st_size, ""
    except Exception as e:
        return False, 0, str(e)


def main(input_file: str, output_dir: str):
    out = Path(output_dir)
    (out / "html").mkdir(parents=True, exist_ok=True)
    (out / "pdf").mkdir(parents=True, exist_ok=True)

    urls = [resolve_input(l) for l in Path(input_file).read_text().splitlines()]
    urls = [u for u in urls if u]

    report = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=GOOGLEBOT_UA)
        page = context.new_page()

        for i, url in enumerate(urls, 1):
            name = safe_name(url)
            html_path = out / "html" / f"{name}.html"
            pdf_path = out / "pdf" / f"{name}.pdf"

            print(f"[{i}/{len(urls)}] {url}")
            t0 = time.time()
            try:
                wait_state = navigate(page, url)
            except Exception as e:
                print(f"   NAV FAIL: {e}")
                report.append({"url": url, "name": name, "nav": "FAIL",
                               "html_bytes": 0, "pdf_bytes": 0,
                               "html_sec": 0, "pdf_sec": 0})
                continue
            t_nav = time.time() - t0

            t0 = time.time()
            ok_h, size_h, err_h = save_inlined_html(context, page, html_path)
            t_html = time.time() - t0

            t0 = time.time()
            ok_p, size_p, err_p = save_pdf(page, pdf_path)
            t_pdf = time.time() - t0

            print(f"   nav={wait_state} {t_nav:.1f}s")
            print(f"   HTML: {'OK' if ok_h else 'FAIL'} {size_h:>9}B {t_html:.1f}s {err_h}")
            print(f"   PDF : {'OK' if ok_p else 'FAIL'} {size_p:>9}B {t_pdf:.1f}s {err_p}")
            report.append({
                "url": url, "name": name, "nav": wait_state,
                "html_ok": ok_h, "html_bytes": size_h, "html_sec": round(t_html, 1),
                "pdf_ok": ok_p, "pdf_bytes": size_p, "pdf_sec": round(t_pdf, 1),
            })

        browser.close()

    summary = out / "summary.txt"
    with summary.open("w", encoding="utf-8") as f:
        f.write(f"{'URL':<70} {'nav':<18} {'HTML':>10} {'PDF':>10} {'Hs':>5} {'Ps':>5}\n")
        for r in report:
            f.write(
                f"{r['url'][:70]:<70} {str(r.get('nav','?')):<18} "
                f"{r.get('html_bytes',0):>10} {r.get('pdf_bytes',0):>10} "
                f"{r.get('html_sec',0):>5} {r.get('pdf_sec',0):>5}\n"
            )
    print(f"\nSummary written to {summary}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python batch_extract.py <input.txt> <output_dir>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
