"""Keep checkpoint writes safe and produce the CSV and JSON datasets."""

import csv
import filecmp
import json
import os
import re
import shutil
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile, mkdtemp

if __package__:
    from .validation import item_id_for, require_site_url, validate_book
else:
    from validation import item_id_for, require_site_url, validate_book

PAGE_COUNT = 5
BOOKS_PER_PAGE = 20
TARGET = PAGE_COUNT * BOOKS_PER_PAGE
FIELDS = (
    "item_id", "title", "upc", "category", "price_gbp", "rating_stars",
    "stock_quantity", "in_stock", "source_url", "cover_path",
)


def group_name(start_page):
    return f"pages-{start_page:02d}-{start_page + PAGE_COUNT - 1:02d}"


def read_json(path):
    with path.open(encoding="utf-8") as file:
        return json.load(file)


@contextmanager
def range_lock(folder):
    """Allow one scraper to write each page range at a time."""
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "scraper.lock").open("a+b") as lock:
        try:
            if os.name == "nt":
                import msvcrt

                if lock.tell() == 0:
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise OSError("Could not lock this page range. Check for another active scrape.") from error
        yield


def write_atomic(path, write, *, encoding=None):
    """Write beside the destination, then replace it after closing the file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if encoding is None else "w"
    options = {} if encoding is None else {"encoding": encoding, "newline": ""}
    file = NamedTemporaryFile(mode=mode, dir=path.parent, delete=False, **options)
    temporary = Path(file.name)
    try:
        with file:
            write(file)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path, data):
    def write(file):
        json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")

    write_atomic(path, write, encoding="utf-8")


def empty_state(start_page):
    return {
        "version": 1, "start_page": start_page, "pages": [],
        "completed_page_urls": [], "items": {},
    }


def validate_checkpoint(state, start_page):
    if (
        not isinstance(state, dict)
        or state.get("version") != 1
        or state.get("start_page") != start_page
        or not isinstance(state.get("pages"), list)
        or not isinstance(state.get("completed_page_urls"), list)
        or not isinstance(state.get("items"), dict)
    ):
        raise ValueError("Checkpoint format does not match this page range")

    pages = state["pages"]
    completed = state["completed_page_urls"]
    if not len(completed) <= len(pages) <= min(PAGE_COUNT, len(completed) + 1):
        raise ValueError("Checkpoint has an unexpected number of pages")

    page_urls = []
    products = {}
    expected_next = None
    for page in pages:
        if not isinstance(page, dict) or "next_url" not in page:
            raise ValueError("Checkpoint has a malformed catalog page")
        url = require_site_url(page.get("url"))
        if url in page_urls or (page_urls and url != expected_next):
            raise ValueError("Checkpoint catalog pages do not follow their Next links")
        page_urls.append(url)
        expected_next = page["next_url"]
        if expected_next is not None:
            require_site_url(expected_next)
        links = page.get("links")
        if not isinstance(links, list) or len(links) != BOOKS_PER_PAGE:
            raise ValueError("Checkpoint page must contain 20 product links")
        for link in links:
            book_id = item_id_for(require_site_url(link))
            if book_id in products:
                raise ValueError("Checkpoint contains duplicate product links or IDs")
            products[book_id] = (url, link)

    if completed != page_urls[:len(completed)]:
        raise ValueError("Checkpoint completed pages do not match the catalog sequence")
    items = state["items"]
    for book_id, item in items.items():
        if not isinstance(item, dict) or "cover_url" not in item:
            raise ValueError(f"Saved book {book_id} has an invalid checkpoint entry")
        book = item.get("record")
        try:
            validate_book(book)
            if book["item_id"] != book_id or products.get(book_id) != (
                item.get("page_url"), book["source_url"]
            ):
                raise ValueError("Book ID or catalog page does not match its saved link")
            if item.get("cover_url") is not None:
                require_site_url(item["cover_url"])
        except ValueError as error:
            raise ValueError(f"Saved book {book_id}. {error}") from error
    for book_id, (page_url, _) in products.items():
        if page_url in completed and book_id not in items:
            raise ValueError(f"Completed page is missing saved book {book_id}")


def load_checkpoint(folder, start_page, logger=None):
    path = folder / "scraper_state.json"
    backup = folder / "scraper_state.backup.json"
    if not path.exists() and not backup.exists():
        return empty_state(start_page)

    try:
        state = read_json(path)
        validate_checkpoint(state, start_page)
        return state
    except (FileNotFoundError, ValueError) as primary_error:
        try:
            state = read_json(backup)
            validate_checkpoint(state, start_page)
        except (OSError, ValueError) as backup_error:
            raise ValueError(
                f"Cannot resume from {path}. {primary_error}. "
                f"Backup unavailable or invalid. {backup_error}"
            ) from backup_error

        if path.exists():
            # Give every preserved copy a unique name and keep the backup intact.
            with NamedTemporaryFile(dir=folder, prefix="scraper_state.damaged-", suffix=".json",
                                    delete=False) as copy:
                damaged = Path(copy.name)
            try:
                write_atomic(damaged, lambda file: file.write(path.read_bytes()))
            except OSError:
                damaged.unlink(missing_ok=True)
                raise
            print(f"Preserved damaged checkpoint at {damaged}", flush=True)
        write_json(path, state)
        message = f"Recovered checkpoint backup with {len(state['items'])} saved books."
        if logger is not None:
            logger.warning("%s Main checkpoint error: %s", message, primary_error)
        print(message, flush=True)
        return state


def save_checkpoint(path, state):
    """Keep the previous committed state before replacing the main checkpoint."""
    backup = path.with_name("scraper_state.backup.json")
    if path.exists():
        write_atomic(backup, lambda file: file.write(path.read_bytes()))
    else:
        write_json(backup, empty_state(state["start_page"]))
    write_json(path, state)


def reset_checkpoint(folder, start_page):
    """Start this range at zero while leaving its published results available."""
    state = empty_state(start_page)
    write_json(folder / "scraper_state.backup.json", state)
    write_json(folder / "scraper_state.json", state)


def validate_dataset(records):
    if not isinstance(records, list) or len(records) != TARGET:
        raise ValueError(f"The dataset must contain exactly {TARGET} books")
    ids = set()
    for number, record in enumerate(records, 1):
        try:
            validate_book(record)
            if "cover_path" not in record:
                raise ValueError("cover_path is missing")
            if record["item_id"] in ids:
                raise ValueError("Duplicate item_id")
            ids.add(record["item_id"])
        except ValueError as error:
            raise ValueError(f"Book record {number}. {error}") from error


def spreadsheet_text(value):
    """Add an Excel-oriented text prefix to formula-like strings."""
    normalized = unicodedata.normalize("NFKC", value).lstrip()
    if normalized.startswith(("=", "+", "-", "@")):
        return "\t" + value
    return value


def write_exports(folder, records):
    validate_dataset(records)
    records = sorted(records, key=lambda record: record["item_id"])

    def write_csv(file):
        writer = csv.DictWriter(file, fieldnames=FIELDS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for record in records:
            row = {field: record[field] for field in FIELDS}
            for field in ("title", "category", "upc"):
                row[field] = spreadsheet_text(row[field])
            row["price_gbp"] = f'{record["price_gbp"]:.2f}'
            row["in_stock"] = str(record["in_stock"]).lower()
            writer.writerow(row)

    write_json(folder / "books.json", records)
    write_atomic(folder / "books.csv", write_csv, encoding="utf-8-sig")


def current_results(folder):
    """Resolve one published folder for both exports and its matching media."""
    pointer = folder / "current_results.json"
    if not pointer.is_file():
        return folder  # Bundled sample and results from the earlier version.
    name = read_json(pointer)
    if not isinstance(name, str) or not re.fullmatch(r"run-[a-zA-Z0-9_-]+", name):
        raise ValueError(f"Invalid results pointer at {pointer}")
    result = folder / "results" / name
    if not all((result / name).is_file() for name in ("books.csv", "books.json")):
        raise ValueError(f"Published results are incomplete at {result}")
    return result


def publish_results(folder, records, state):
    """Finish a new set before atomically switching the current results pointer."""
    results = folder / "results"
    results.mkdir(parents=True, exist_ok=True)
    staged = Path(mkdtemp(prefix="run-", dir=results))
    try:
        write_exports(staged, records)
        for record in records:
            relative = record["cover_path"]
            if relative:
                destination = staged / relative
                destination.parent.mkdir(exist_ok=True)
                shutil.copyfile(folder / relative, destination)
        write_json(staged / "run_summary.json", {
            "start_page": state["start_page"],
            "total_books": len(records),
            "covers_available": sum(bool(book["cover_path"]) for book in records),
            "catalog_pages": [
                {"url": page["url"], "validated_books": len(page["links"])}
                for page in state["pages"]
            ],
        })
        try:
            previous = current_results(folder)
        except (OSError, ValueError):
            previous = None  # A new valid set can replace an invalid pointer.
        files = [file.relative_to(staged) for file in staged.rglob("*") if file.is_file()]
        if previous is not None and all(
            (previous / name).is_file()
            and filecmp.cmp(staged / name, previous / name, shallow=False)
            for name in files
        ):
            shutil.rmtree(staged)
            return previous
    except (Exception, KeyboardInterrupt):
        shutil.rmtree(staged, ignore_errors=True)
        raise
    # Keep the staged set if interrupted while switching the pointer.
    write_json(folder / "current_results.json", staged.name)
    return staged
