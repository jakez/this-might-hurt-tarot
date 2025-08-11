#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This Might Hurt Tarot – scraper (fixed: title-anchored parsing).
Outputs CSV columns:
  suit_arcana, card, subtitle, description, image_url, page_url
Optionally downloads images to ./images/
"""

import re
import time
import csv
import os
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from bs4 import BeautifulSoup as _BS_for_noscript  # reuse the parser

NUMERIC_RANK = {"Two":"2","Three":"3","Four":"4","Five":"5","Six":"6",
                "Seven":"7","Eight":"8","Nine":"9","Ten":"10"}

# --- helpers ---------------------------------------------------------------

def _extract_img_url_from(el: Tag) -> list[str]:
    """Return all plausible image URLs found under element `el`."""
    urls = []

    # <a href="...">
    for a in el.find_all("a", href=True):
        urls.append(a["href"])

    # <img ...> with multiple ways images can appear
    for img in el.find_all("img"):
        for attr in ("data-src", "data-image", "src"):
            if img.has_attr(attr) and img.get(attr):
                urls.append(img[attr])
        if img.has_attr("srcset"):
            parts = [p.strip().split(" ")[0] for p in img["srcset"].split(",") if p.strip()]
            urls.extend(parts)

    # inline CSS background-image
    for node in el.find_all(True):
        style = node.get("style", "") or ""
        m = re.search(r"background-image\s*:\s*url\(['\"]?([^)'\"]+)['\"]?\)", style, re.I)
        if m:
            urls.append(m.group(1))

    # <noscript><img src=...></noscript>
    for ns in el.find_all("noscript"):
        try:
            ns_soup = _BS_for_noscript(ns.decode_contents(), "lxml")
            for img in ns_soup.find_all("img"):
                for attr in ("src", "data-src", "data-image"):
                    if img.get(attr):
                        urls.append(img[attr])
        except Exception:
            pass

    # normalize & filter
    cleaned = []
    for u in urls:
        if not u:
            continue
        base_u = u.split("?")[0]
        low = base_u.lower()
        if any(bad in low for bad in ("logo", "header", "favicon", "sprite")):
            continue
        if (low.endswith((".jpg",".jpeg",".png",".webp",".gif")) or "/images/" in low):
            cleaned.append(urljoin(BASE, base_u))
    return cleaned



def card_filename_tokens(title_text: str, suit_arcana: str) -> list[str]:
    """Return substrings likely present in the CDN filename."""
    title = title_text.strip()
    toks = []
    if suit_arcana == "Major Arcana":
        base = re.sub(r"^The\s+", "", title, flags=re.I)
        toks += [base.replace(" ", ""), title.replace(" ", "")]
    else:
        m = re.match(r"^(Ace|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Page|Knight|Queen|King)\s+of\s+(\w+)", title, re.I)
        if m:
            rank = m.group(1).title()
            suit  = m.group(2).title()
            toks.append(f"{rank}Of{suit}")
            if rank in NUMERIC_RANK:
                toks.append(f"{NUMERIC_RANK[rank]}of{suit}")
    return [t.lower() for t in toks]


BASE = "https://www.thismighthurttarot.com"
PAGES = {
    "Major Arcana": "/majorarcana",
    "Wands": "/wands",
    "Cups": "/cups",
    "Swords": "/swords",
    "Pentacles": "/pentacles",
}

DOWNLOAD_IMAGES = True
IMG_DIR = "images"
DELAY_SEC = 1.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TMH-Scraper/1.1; +https://example.org)"
}

def get_soup(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")

def text_clean(s: str) -> str:
    return re.sub(r"\s+\n", "\n", re.sub(r"[ \t]+", " ", s)).strip()

def is_image_href(href: str | None) -> bool:
    if not href:
        return False
    href = href.split("?")[0]
    return any(href.lower().endswith(ext) for ext in (".jpg",".jpeg",".png",".webp",".gif")) or "/images/" in href

def nearest_card_image_url(title_el: Tag, title_text: str, suit_arcana: str) -> str | None:
    """
    Inside the smallest ancestor section/article/main that contains the title:
    - collect *all* plausible image URLs with their DOM order
    - prefer the closest candidate BEFORE the title; fallback to closest AFTER
    - score by filename tokens (AceOfWands, 2ofWands, etc.)
    """
    # boundary container
    boundary = (title_el.find_parent(["section", "article", "main"]) or title_el.parent)

    # flatten nodes in document order
    nodes = [n for n in boundary.descendants if isinstance(n, Tag)]

    # index of the title element in that order
    try:
        title_idx = nodes.index(title_el)
    except ValueError:
        title_idx = len(nodes) // 2  # shouldn’t happen

    # harvest candidates with their first-seen index
    candidates = []  # [(index, url)]
    seen = set()
    for idx, n in enumerate(nodes):
        for url in _extract_img_url_from(n):
            if url not in seen:
                seen.add(url)
                candidates.append((idx, url))

    if not candidates:
        return None

    # build filename tokens for scoring
    tokens = card_filename_tokens(title_text, suit_arcana)

    def score(idx_url):
        idx, u = idx_url
        ul = u.lower()
        sc = 0
        for t in tokens:
            if t in ul:
                sc += 20
        if any(s in ul for s in ("_forweb", "forweb", "/images/")):
            sc += 2
        if ul.endswith((".jpg",".jpeg",".png",".webp",".gif")):
            sc += 1
        # prefer before-title; closer gets a bonus
        distance = abs(idx - title_idx)
        before_bonus = 10 if idx < title_idx else 0
        return (before_bonus, -distance, sc)

    # choose best by (before?, nearest, token score)
    best = sorted(candidates, key=score, reverse=True)[0]
    return best[1]

# Title patterns
MAJORS = r"(The Fool|The Magician|The High Priestess|The Empress|The Emperor|The Hierophant|The Lovers|The Chariot|Strength|The Hermit|The Wheel of Fortune|Justice|The Hanged Man|Death|Temperance|The Devil|The Tower|The Star|The Moon|The Sun|Judgement|The World)"
RANKS = r"(Ace|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Page|Knight|Queen|King)"

def title_regex_for(suit_arcana: str) -> re.Pattern:
    if suit_arcana == "Major Arcana":
        return re.compile(rf"^{MAJORS}$", re.I)
    else:
        return re.compile(rf"^{RANKS}\s+of\s+{re.escape(suit_arcana)}$", re.I)

def looks_like_subtitle(txt: str, title_pat: re.Pattern) -> bool:
    if not txt: return False
    if title_pat.search(txt): return False
    return 3 <= len(txt) <= 60 and txt[0].isupper()

def collect_paragraphs(start_node: Tag, stop_pat: re.Pattern) -> list[str]:
    """Collect <p> text after start_node until the next title-like text."""
    desc = []
    cur = start_node
    while True:
        cur = cur.find_next()
        if cur is None:
            break
        # Stop if we hit the next card title
        if isinstance(cur, Tag):
            txt = cur.get_text(strip=True, separator=" ")
            if txt and stop_pat.search(txt):
                break
            if cur.name == "p":
                t = cur.get_text(separator=" ", strip=True)
                if t:
                    desc.append(t)
    return desc

def download_image(url: str, out_dir: str, filename_hint: str):
    os.makedirs(out_dir, exist_ok=True)
    base = re.sub(r"[^a-zA-Z0-9_-]+", "_", filename_hint).strip("_")
    ext = os.path.splitext(url.split("?")[0])[1]
    if len(ext) > 6 or not ext:
        ext = ".jpg"
    path = os.path.join(out_dir, f"{base}{ext}")
    try:
        with requests.get(url, headers=HEADERS, timeout=60, stream=True) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
    except Exception as e:
        print(f"[warn] failed downloading {url}: {e}")

def parse_card_page(suit_arcana: str, url_path: str):
    url = urljoin(BASE, url_path)
    soup = get_soup(url)

    # Flexible container (Squarespace varies)
    content = soup.select_one("main, article, .sqs-layout, #content, #page, body")
    if content is None:
        content = soup

    title_pat = title_regex_for(suit_arcana)

    # Find elements whose visible text is a title (often wrapped in <a>)
    title_nodes = []
    for el in content.find_all(['a','h1','h2','h3','h4','strong','div']):  # narrow tag set to reduce double matches
      txt = el.get_text(separator=" ", strip=True)
      if not txt:
          continue
      if not title_pat.fullmatch(txt):
          continue
      # skip if a descendant ALSO matches (we only want the deepest match once)
      child_match = False
      for child in el.find_all(True):
          ctxt = child.get_text(separator=" ", strip=True)
          if ctxt and title_pat.fullmatch(ctxt):
              child_match = True
              break
      if child_match:
          continue
      title_nodes.append(el)

    results = []
    for i, title_el in enumerate(title_nodes):
        title_text = re.sub(r"\s+", " ", title_el.get_text(" ", strip=True))
        # try to grab a short subtitle right after the title node
        subtitle = ""
        next_text_el = title_el.find_next(string=lambda s: isinstance(s, NavigableString) and s.strip())
        if next_text_el:
            cand = next_text_el.strip()
            if looks_like_subtitle(cand, title_pat):
                subtitle = cand

        # find description paragraphs until the next title
        desc_parts = collect_paragraphs(title_el, title_pat)
        description = text_clean("\n\n".join(desc_parts))

        # image url = nearest previous image-like link before the title
        img_url = nearest_card_image_url(title_el, title_text, suit_arcana) or ""

        results.append({
            "suit_arcana": suit_arcana,
            "card": title_text,
            "subtitle": subtitle,
            "description": description,
            "image_url": img_url,
            "page_url": url,
        })

    # basic sanity: warn if page unexpectedly empty
    if not results:
        print(f"[warn] No cards parsed on {url} – site structure may have changed.")

    time.sleep(DELAY_SEC)
    return results

def main():
    rows = []
    for suit, path in PAGES.items():
        print(f"Scraping {suit} … {path}")
        try:
            rows.extend(parse_card_page(suit, path))
        except Exception as e:
            print(f"[error] {suit}: {e}")

    print(f"Collected {len(rows)} cards.")

    # Order for nicer CSV
    order_key = {"Major Arcana": 0, "Wands": 1, "Cups": 2, "Swords": 3, "Pentacles": 4}
    num_map = {"Ace":1,"Two":2,"Three":3,"Four":4,"Five":5,"Six":6,"Seven":7,"Eight":8,"Nine":9,"Ten":10,"Page":11,"Knight":12,"Queen":13,"King":14}
    def sort_key(r):
        s = r["suit_arcana"]
        n = r["card"]
        if s == "Major Arcana":
            # keep page order by discovery
            return (order_key[s], 0)
        m = re.match(r"^(Ace|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Page|Knight|Queen|King)", n)
        return (order_key[s], num_map.get(m.group(1), 99) if m else 99)

    rows.sort(key=sort_key)

    # Write CSV
    out_csv = "this_might_hurt_tarot.csv"
    fieldnames = ["suit_arcana", "card", "subtitle", "description", "image_url", "page_url"]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"Wrote {out_csv}")

    # Download images
    if DOWNLOAD_IMAGES:
        os.makedirs(IMG_DIR, exist_ok=True)
        for r in rows:
            if r["image_url"]:
                download_image(r["image_url"], IMG_DIR, f'{r["suit_arcana"]}_{r["card"]}')
        print(f"Images saved to ./{IMG_DIR}/")

if __name__ == "__main__":
    main()
