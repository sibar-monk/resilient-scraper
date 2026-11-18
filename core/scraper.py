"""Follow the catalog links, validate book details, and resume safely."""

import logging
import random
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from io import BytesIO

from PIL import Image

import requests
from bs4 import BeautifulSoup

if __package__:
    from .storage import (
        BOOKS_PER_PAGE, PAGE_COUNT, TARGET, load_checkpoint, publish_results, save_checkpoint,
        validate_checkpoint, write_atomic,
    )
    from .validation import START_URL, canonical_url, item_id_for, validate_book
else:
    from storage import (
        BOOKS_PER_PAGE, PAGE_COUNT, TARGET, load_checkpoint, publish_results, save_checkpoint,
        validate_checkpoint, write_atomic,
    )
    from validation import START_URL, canonical_url, item_id_for, validate_book

MAX_RETRIES = 3
RETRY_CODES = {429, 500, 502, 503, 504}
HEADERS = {
    "User-Agent": "resilient-scraper/1.0 (educational project; Books to Scrape)",
    "Accept-Language": "en-GB,en;q=0.9",
}
STARS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


class ScrapeError(Exception):
    """A request or catalog problem that can be reported to the user."""


class PauseRequests(ScrapeError):
    """Pause further requests after an access denial or a persistent rate limit."""


def retry_after_seconds(value):
    if not value:
        return 0
    if value.isascii() and value.isdecimal():
        return int(value)
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return max(0, (date - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return 0


def fetch(url, referer, logger, max_retries=MAX_RETRIES):
    """Make the first request and up to three retries for temporary failures."""
    headers = {**HEADERS, "Referer": canonical_url(START_URL, referer)}
    for attempt in range(max_retries + 1):
        time.sleep(random.uniform(1.0, 2.5))
        retry_after = 0
        try:
            request_url = canonical_url(START_URL, url)
            response = requests.get(request_url, headers=headers, timeout=(8, 20), allow_redirects=False)
            if response.status_code == 200:
                return response
            problem = f"HTTP {response.status_code}"
            if response.status_code in {401, 403}:
                raise PauseRequests(f"{problem} for {url}. The server declined access.")
            if response.status_code not in RETRY_CODES:
                raise ScrapeError(f"{problem} for {url}")
            retry_after = retry_after_seconds(response.headers.get("Retry-After"))
        except requests.exceptions.RequestException as error:
            problem = f"{type(error).__name__}: {error}"

        if attempt < max_retries:
            delay = max(2 ** attempt, retry_after)
            logger.warning("%s | %s | retry %d/%d in %.1f s plus jitter",
                           url, problem, attempt + 1, max_retries, delay)
            print(f"  Temporary request error. Retry {attempt + 1}/{max_retries} "
                  f"after {delay:.1f} seconds plus jitter.", flush=True)
            time.sleep(delay)

    if problem == "HTTP 429":
        raise PauseRequests(f"HTTP 429 for {url} after retries. "
                            f"Wait at least {max(4, retry_after):g} seconds before resuming.")
    raise ScrapeError(f"{problem} for {url}. Request retries exhausted.")


def make_soup(url, referer, logger):
    response = fetch(url, referer, logger)
    # The site's pound symbol is UTF-8. Force decoding even if HTTP omits a charset.
    response.encoding = "utf-8"
    return BeautifulSoup(response.text, "html.parser")


def catalog_links(soup, url):
    books = soup.select("article.product_pod h3 a")
    links = [canonical_url(url, book.get("href")) for book in books]
    next_link = soup.select_one("li.next a")
    next_url = canonical_url(url, next_link.get("href")) if next_link else None
    return links, next_url


def require_text(soup, selector, field):
    element = soup.select_one(selector)
    value = " ".join(element.get_text(" ", strip=True).split()) if element else ""
    if not value:
        raise ValueError(f"{field} is missing")
    return value


def parse_book(soup, url):
    title = require_text(soup, ".product_main h1", "title")
    category = require_text(soup, ".breadcrumb li:nth-last-child(2) a", "category")
    price_text = require_text(soup, ".product_main .price_color", "price_gbp")
    if not re.fullmatch(r"£[0-9]+\.[0-9]{2}", price_text):
        raise ValueError(f"price_gbp has an unexpected format: {price_text!r}")
    price = float(price_text[1:])

    details = {}
    for row in soup.select(".table.table-striped tr"):
        heading = row.select_one("th")
        value = row.select_one("td")
        if heading and value:
            details[heading.get_text(strip=True)] = " ".join(value.get_text(" ", strip=True).split())
    upc = details.get("UPC", "")

    rating_node = soup.select_one(".product_main .star-rating")
    rating_classes = rating_node.get("class", []) if rating_node else []
    ratings = [STARS[name] for name in rating_classes if name in STARS]
    if len(ratings) != 1:
        raise ValueError("rating_stars must be a single rating from 1 to 5")

    availability = details.get("Availability", "")
    stock = re.fullmatch(r"In stock \(([0-9]+) available\)", availability, re.IGNORECASE)
    if stock:
        quantity = int(stock.group(1))
        in_stock = True
    elif availability.casefold() == "out of stock":
        quantity = 0
        in_stock = False
    else:
        raise ValueError(f"stock_quantity cannot be read from {availability!r}")

    record = {
        "item_id": item_id_for(url),
        "title": title,
        "upc": upc,
        "category": category,
        "price_gbp": price,
        "rating_stars": ratings[0],
        "stock_quantity": quantity,
        "in_stock": in_stock,
        "source_url": url,
    }
    validate_book(record)
    image = soup.select_one("#product_gallery img")
    cover_url = None
    if image and image.get("src"):
        try:
            cover_url = canonical_url(url, image["src"])
        except ValueError:
            pass  # The bonus image is separate from the required book fields.
    return {"record": record, "cover_url": cover_url}


def logger_for(folder):
    folder.mkdir(parents=True, exist_ok=True)
    logger = logging.Logger("book_scraper")
    handler = logging.FileHandler(folder / "scraper.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    return logger, handler


def locate_start(start_page, logger):
    url = START_URL
    referer = START_URL
    visited = set()
    for _ in range(1, start_page):
        if url in visited:
            raise ScrapeError("The catalog's Next link repeated a page.")
        visited.add(url)
        soup = make_soup(url, referer, logger)
        _, next_url = catalog_links(soup, url)
        if not next_url:
            raise ScrapeError("The catalog ended before the chosen starting page.")
        referer, url = url, next_url
    return url, referer


def new_page(url, referer, logger):
    soup = make_soup(url, referer, logger)
    links, next_url = catalog_links(soup, url)
    if len(links) != BOOKS_PER_PAGE or len(set(links)) != BOOKS_PER_PAGE:
        raise ScrapeError(f"Expected {BOOKS_PER_PAGE} distinct book links on {url}.")
    return {"url": url, "next_url": next_url, "links": links}


def scrape_page(page, state, checkpoint, logger, page_number):
    items = state["items"]
    url = page["url"]
    pending = []

    # Reuse records saved on this page. Detect duplicates across pages.
    for book_url in page["links"]:
        saved = items.get(item_id_for(book_url))
        if saved is None:
            pending.append(book_url)
        elif saved["page_url"] != url or saved["record"]["source_url"] != book_url:
            raise ScrapeError(f"Duplicate product URL or item ID across pages: {book_url}")

    print(f"Page {page_number} of {PAGE_COUNT} | {len(items)}/{TARGET} books validated "
          f"| {len(pending)} book(s) pending", flush=True)

    # Give malformed detail pages one fresh fetch after the other books are processed.
    malformed = []
    for attempt in range(2):
        for book_url in pending:
            try:
                soup = make_soup(book_url, url, logger)
                result = parse_book(soup, book_url)
            except PauseRequests:
                raise
            except ScrapeError as error:
                logger.error("Pending book | %s | %s", book_url, error)
                print("  Request failed after retries. The book remains pending.", flush=True)
                continue
            except ValueError as error:
                logger.warning("Malformed book | %s | %s", book_url, error)
                print(f"  Book needs review: {error}", flush=True)
                if attempt == 0:
                    malformed.append(book_url)
                continue

            book_id = result["record"]["item_id"]
            if book_id in items:
                raise ScrapeError(f"Duplicate item ID for {book_url}.")
            items[book_id] = {**result, "page_url": url}
            save_checkpoint(checkpoint, state)
            if len(items) % 5 == 0:
                print(f"  Saved {len(items)}/{TARGET} validated books.", flush=True)
        pending = malformed

    if any(item_id_for(book_url) not in items for book_url in page["links"]):
        count = sum(item_id_for(book_url) not in items for book_url in page["links"])
        raise ScrapeError(f"{count} book(s) remain pending on page {page_number} of {PAGE_COUNT}.")

    state["completed_page_urls"].append(url)
    save_checkpoint(checkpoint, state)
    print(f"Page {page_number} of {PAGE_COUNT} complete | {len(items)}/{TARGET} books saved.",
          flush=True)


def cover_rank(record):
    return (-record["rating_stars"], record["price_gbp"], record["item_id"])


def valid_jpeg(source):
    """Try decoding the complete JPEG, including its image data."""
    try:
        with Image.open(source, formats=["JPEG"]) as image:
            image.load()
        return True
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return False


def download_covers(folder, items, logger):
    """Keep every valid cached cover, then try the missing top-ten images."""
    records = sorted((item["record"] for item in items.values()), key=cover_rank)[:10]
    cover_paths = {}
    pending = []

    # Check the whole cache before a network pause can stop new downloads.
    for record in records:
        book_id = record["item_id"]
        relative_path = f"media/{book_id}.jpg"
        if valid_jpeg(folder / relative_path):
            cover_paths[book_id] = relative_path
        else:
            pending.append(record)

    print(f"Cover images | {len(cover_paths)} cached | {len(pending)} to download.", flush=True)
    for record in pending:
        book_id = record["item_id"]
        cover_url = items[book_id]["cover_url"]
        relative_path = f"media/{book_id}.jpg"
        try:
            if not cover_url:
                raise ScrapeError("No cover URL on the detail page.")
            response = fetch(cover_url, record["source_url"], logger)
            if not valid_jpeg(BytesIO(response.content)):
                raise ScrapeError("Cover response could not be decoded as a JPEG.")
            write_atomic(folder / relative_path, lambda file: file.write(response.content))
        except PauseRequests as error:
            logger.warning("Cover downloads paused | %s", error)
            print(f"  Cover downloads paused. {error}", flush=True)
            break
        except (ScrapeError, OSError) as error:
            logger.warning("Cover unavailable | %s | %s", book_id, error)
            continue
        cover_paths[book_id] = relative_path
    return cover_paths


def run_scrape(folder, start_page):
    """Resume the five-page group and return the full exported dataset."""
    logger, handler = logger_for(folder)
    checkpoint = folder / "scraper_state.json"
    try:
        state = load_checkpoint(folder, start_page, logger)
        completed = state["completed_page_urls"]
        pages = state["pages"]
        items = state["items"]
        if items or pages:
            print(f"Checkpoint loaded | {len(completed)}/{PAGE_COUNT} pages complete "
                  f"| {len(items)}/{TARGET} books already saved.", flush=True)

        for offset in range(len(completed), PAGE_COUNT):
            if offset == len(pages):
                if offset:
                    previous = pages[offset - 1]
                    url, referer = previous["next_url"], previous["url"]
                else:
                    url, referer = locate_start(start_page, logger)
                if not url or url in completed:
                    raise ScrapeError("The catalog did not supply five consecutive distinct pages.")
                pages.append(new_page(url, referer, logger))
                validate_checkpoint(state, start_page)
                save_checkpoint(checkpoint, state)
            scrape_page(pages[offset], state, checkpoint, logger, offset + 1)

        if len(completed) != PAGE_COUNT or len(items) != TARGET:
            raise ScrapeError(f"Expected {TARGET} unique validated books on {PAGE_COUNT} pages.")

        print("Dataset complete. Checking the top 10 cover images.", flush=True)
        covers = download_covers(folder, items, logger)
        records = [
            {**item["record"], "cover_path": covers.get(book_id, "")}
            for book_id, item in items.items()
        ]
        results = publish_results(folder, records, state)
        print(f"CSV and JSON saved | {len(covers)}/10 cover images available.", flush=True)
        print(f"Results folder  {results}", flush=True)
        return records
    except (ScrapeError, ValueError, OSError) as error:
        logger.error("Run paused | %s", error)
        raise
    finally:
        handler.close()
