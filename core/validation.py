"""Validate the same book fields wherever records enter the program."""

import hashlib
import math
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

START_URL = "https://books.toscrape.com/"
SITE_HOST = "books.toscrape.com"


def canonical_url(base, link):
    """Resolve a link and normalize it to this practice site's HTTPS URL."""
    if not isinstance(link, str) or not link.strip():
        raise ValueError("Missing link URL")
    parts = urlsplit(urljoin(base, link.strip()))
    if parts.hostname != SITE_HOST or parts.scheme not in {"http", "https"}:
        raise ValueError("Link is outside Books to Scrape")
    if parts.username or parts.password or parts.port not in {None, 80, 443}:
        raise ValueError("Unexpected URL credentials or port")
    return urlunsplit(("https", SITE_HOST, parts.path or "/", "", ""))


def item_id_for(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def require_site_url(url):
    if canonical_url(START_URL, url) != url:
        raise ValueError("Expected a canonical Books to Scrape URL")
    return url


def validate_book(book):
    """Raise a field-specific error if a parsed or saved book is invalid."""
    if not isinstance(book, dict):
        raise ValueError("Book must be a JSON object")
    for field in ("title", "upc", "category"):
        value = book.get(field)
        if not isinstance(value, str) or not value.strip() or not value.isprintable():
            raise ValueError(f"{field} must contain printable text")
    if not re.fullmatch(r"[a-zA-Z0-9]+", book["upc"]):
        raise ValueError("upc must contain only letters and digits")

    price = book.get("price_gbp")
    if type(price) is not float or not math.isfinite(price) or price < 0:
        raise ValueError("price_gbp must be a finite, nonnegative float")
    stars = book.get("rating_stars")
    if type(stars) is not int or not 1 <= stars <= 5:
        raise ValueError("rating_stars must be an integer from 1 to 5")
    quantity = book.get("stock_quantity")
    if type(quantity) is not int or quantity < 0:
        raise ValueError("stock_quantity must be a nonnegative integer")
    if type(book.get("in_stock")) is not bool or book["in_stock"] != (quantity > 0):
        raise ValueError("in_stock must match stock_quantity")

    try:
        url = require_site_url(book.get("source_url"))
    except ValueError as error:
        raise ValueError(f"source_url is invalid. {error}") from error
    book_id = item_id_for(url)
    if book.get("item_id") != book_id:
        raise ValueError("item_id does not match the source_url hash")
    if "cover_path" in book and book["cover_path"] not in ("", f"media/{book_id}.jpg"):
        raise ValueError("cover_path must be empty or match the book's JPEG filename")
