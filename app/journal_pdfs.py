"""
Walk journal repositories, extract best-available URL from each article
markdown, and render a PDF next to the markdown (in a parallel pdfs/ tree).
Resumable — skips articles whose PDF already exists.
"""
import re
import sys
import time
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

GOOGLEBOT_UA = (
    "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.6533.119 "
    "Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)

URL_PRIORITY = ("PMC", "DOI", "Article URL", "PubMed")


def extract_url(md_path: Path) -> tuple[str, str]:
    """Return (field_name, url) for the best available source URL."""
    text = md_path.read_text(encoding="utf-8", errors="ignore")[:2000]
    found = {}
    for line in text.splitlines():
        m = re.match(r"-\s*([A-Za-z ]+):\s*(https?://\S+)", line)
        if m:
            found[m.group(1).strip()] = m.group(2).strip()
    for key in URL_PRIORITY:
        if key in found:
            return key, found[key]
    return "", ""


def navigate(page, url: str) -> str:
    for wait_state in ("networkidle", "load", "domcontentloaded"):
        try:
            page.goto(url, wait_until=wait_state, timeout=60000)
            return wait_state
        except Exception:
            continue
    raise RuntimeError("nav failed")


def process(repo: Path, articles_rel: str, limit: int | None, dry_run: bool):
    articles_root = repo / articles_rel
    pdfs_root = repo / "pdfs"

    tasks = []
    for md in sorted(articles_root.rglob("*.md")):
        rel = md.relative_to(articles_root)
        pdf_path = pdfs_root / rel.with_suffix(".pdf")
        if pdf_path.exists():
            continue
        field, url = extract_url(md)
        if not url:
            continue
        tasks.append((md, pdf_path, field, url))
        if limit and len(tasks) >= limit:
            break

    print(f"\n{repo.name}: {len(tasks)} articles to process")
    if dry_run or not tasks:
        for md, pdf_path, field, url in tasks[:5]:
            print(f"  [{field}] {url}  ->  {pdf_path.relative_to(repo)}")
        return 0, 0

    ok = fail = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=GOOGLEBOT_UA)
        page = context.new_page()

        for i, (md, pdf_path, field, url) in enumerate(tasks, 1):
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            t0 = time.time()
            try:
                nav = navigate(page, url)
                page.pdf(
                    path=str(pdf_path),
                    format="Letter",
                    print_background=True,
                    margin={"top": "0.5in", "bottom": "0.5in", "left": "0.5in", "right": "0.5in"},
                )
                dt = time.time() - t0
                size = pdf_path.stat().st_size
                print(f"  [{i}/{len(tasks)}] OK {field:<5} {size:>8}B {dt:.1f}s {url}")
                ok += 1
            except Exception as e:
                dt = time.time() - t0
                print(f"  [{i}/{len(tasks)}] FAIL {field:<5} {dt:.1f}s {url}  {str(e)[:80]}")
                fail += 1
                if pdf_path.exists():
                    pdf_path.unlink()

        browser.close()
    return ok, fail


REPOS = [
    (Path("D:/PubMed/AnnFamMed"), "articles"),
    (Path("D:/PubMed/JABFM"),     "articles"),
    (Path("D:/PubMed/JABFP"),     "articles"),
    (Path("D:/PubMed/AAFP"),      "data/articles"),
]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="max articles per repo (for pilot)")
    ap.add_argument("--dry-run", action="store_true", help="list only, no download")
    ap.add_argument("--repo", choices=["AnnFamMed", "JABFM", "JABFP", "AAFP", "all"], default="all")
    args = ap.parse_args()

    total_ok = total_fail = 0
    for repo, rel in REPOS:
        if args.repo != "all" and repo.name != args.repo:
            continue
        ok, fail = process(repo, rel, args.limit, args.dry_run)
        total_ok += ok
        total_fail += fail
    print(f"\nTotal OK={total_ok} FAIL={total_fail}")
