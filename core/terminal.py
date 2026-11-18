"""Show the summary and let users explore the saved books offline."""

import math
import shutil
import textwrap
from collections import Counter
from pathlib import Path
from statistics import mean

if __package__:
    from .scraper import cover_rank
    from .storage import PAGE_COUNT, read_json, validate_dataset
else:
    from scraper import cover_rank
    from storage import PAGE_COUNT, read_json, validate_dataset

DATA_LABELS = {
    "item_id": "Item ID",
    "title": "Title",
    "upc": "UPC",
    "category": "Category",
    "price_gbp": "Price",
    "rating_stars": "Stars",
    "stock_quantity": "Stock quantity",
    "in_stock": "Availability",
    "source_url": "Source URL",
    "cover_path": "Local cover",
}
SORTS = {
    "1": ("Item ID ascending", "item_id", False),
    "2": ("Title A to Z", "title", False),
    "3": ("Category A to Z", "category", False),
    "4": ("Price low to high", "price_gbp", False),
    "5": ("Price high to low", "price_gbp", True),
    "6": ("Rating high to low", "rating_stars", True),
    "7": ("Stock high to low", "stock_quantity", True),
}
ROWS_PER_SCREEN = 10
EMPTY_FILTERS = ("", "", None, None, "", "")


def range_label(start):
    return f"Catalog pages {start} to {start + PAGE_COUNT - 1}"


def saved_books(folder):
    path = folder / "books.json"
    if not path.is_file():
        print("\nStart or resume this range to create its dataset.")
        return []
    books = read_json(path)
    validate_dataset(books)
    return books


def show_summary(books, start):
    cheapest = min(books, key=lambda book: book["price_gbp"])
    dearest = max(books, key=lambda book: book["price_gbp"])
    categories = Counter(book["category"] for book in books)
    price = mean(book["price_gbp"] for book in books)

    print(f"\nSCRAPE SUMMARY  |  {range_label(start)}")
    print(f"Total books       {len(books)} validated\n\nPrices in GBP")
    print(f"  Average         {price:.2f}")
    print(f'  Cheapest        {cheapest["price_gbp"]:.2f}  {cheapest["title"]}')
    print(f'  Most expensive  {dearest["price_gbp"]:.2f}  {dearest["title"]}')
    print(f"\nCategory breakdown  |  {len(categories)} categories\n  Books  Category")
    for category, count in sorted(categories.items(), key=lambda pair: (-pair[1], pair[0])):
        print(f"  {count:>5}  {category}")


def show_covers(books, folder):
    media = folder / "media"
    paths = {}
    print("\nTOP 10 COVERS  |  Starts high to low, then price and item ID low to high")
    print(f"Image folder  {media}")
    for rank, book in enumerate(sorted(books, key=cover_rank)[:10], start=1):
        relative = Path(book["cover_path"])
        path = folder / relative
        if (relative.parent == Path("media") and path.suffix == ".jpg"
                and path.is_file() and path.resolve().is_relative_to(media.resolve())):
            paths[str(rank)] = path
        print(f'{rank:>2}. {book["title"]}  |  {book["rating_stars"]}/5  '
              f'|  GBP {book["price_gbp"]:.2f}')
        print(f'    {paths.get(str(rank), "Image unavailable")}')
    return paths


def ask_price(prompt, minimum=0):
    while True:
        value = input(prompt).strip()
        if not value:
            return None
        try:
            price = float(value)
            if math.isfinite(price) and price >= minimum:
                return price
        except ValueError:
            pass
        print(f"Enter a number at least {minimum:g}, or leave the field blank.")


def ask_choice(prompt, choices):
    while True:
        answer = input(prompt).strip()
        if answer in choices:
            return answer
        print("Choose one of the listed options.")


def ask_category(books):
    categories = sorted({book["category"] for book in books}, key=str.casefold)
    for number, category in enumerate(categories, start=1):
        print(f"  {number:>2}. {category}")
    choices = {str(n): name for n, name in enumerate(categories, start=1)}
    selected = ask_choice("Category number (Enter for any): ", {"", *choices})
    return choices.get(selected, "")


def configure_filters(books, filters):
    values = list(filters)
    while True:
        print(f"\nFILTERS  |  {filter_label(values)}")
        print("1. Title search\n2. Category\n3. Price range\n"
              "4. Rating\n5. Availability\n6. Clear all filters\n0. Show matching books")
        action = ask_choice("Choose a filter: ", set("0123456"))
        if action == "0":
            return tuple(values)
        if action == "1":
            values[0] = input("Title contains (Enter for any): ").strip()
        elif action == "2":
            values[1] = ask_category(books)
        elif action == "3":
            values[2] = ask_price("Minimum GBP (Enter for any): ")
            values[3] = ask_price("Maximum GBP (Enter for any): ", values[2] or 0)
        elif action == "4":
            values[4] = ask_choice("Exact rating, 1 to 5 (Enter for any): ",
                                   {"", "1", "2", "3", "4", "5"})
        elif action == "5":
            values[5] = ask_choice("1 in stock, 2 out of stock (Enter for any): ",
                                   {"", "1", "2"})
        else:
            values = list(EMPTY_FILTERS)


def filtered_books(books, filters):
    query, category, minimum, maximum, rating, stock = filters
    return [
        book for book in books
        if query.casefold() in book["title"].casefold()
        and (not category or book["category"] == category)
        and (minimum is None or book["price_gbp"] >= minimum)
        and (maximum is None or book["price_gbp"] <= maximum)
        and (not rating or book["rating_stars"] == int(rating))
        and (not stock or book["in_stock"] == (stock == "1"))
    ]


def filter_label(filters):
    query, category, minimum, maximum, rating, stock = filters
    labels = []
    if query:
        labels.append(f'title contains "{query}"')
    if category:
        labels.append(category)
    if minimum is not None:
        labels.append(f"from GBP {minimum:.2f}")
    if maximum is not None:
        labels.append(f"up to GBP {maximum:.2f}")
    if rating:
        labels.append(f"{rating}/5 stars")
    if stock:
        labels.append("in stock" if stock == "1" else "out of stock")
    return ", ".join(labels) or "All books"


def sorted_books(books, sort):
    _, field, reverse = SORTS[sort]
    books = sorted(books, key=lambda book: book["item_id"])
    if field == "item_id":
        return books
    if field in {"title", "category"}:
        return sorted(books, key=lambda book: book[field].casefold(), reverse=reverse)
    return sorted(books, key=lambda book: book[field], reverse=reverse)


def show_table(rows):
    width = shutil.get_terminal_size(fallback=(80, 24)).columns
    if width < 65:
        for index, book in enumerate(rows, start=1):
            title = textwrap.shorten(book["title"], max(20, width - 4), placeholder="...")
            print(f'{index:>2}. {title}')
            print(f'    {book["category"]} | {book["price_gbp"]:.2f} GBP | '
                  f'{book["rating_stars"]}/5 | Stock {book["stock_quantity"]}')
        return

    title_width = min(48, width - 45)
    print(f'{"No.":>3}  {"Title":<{title_width}}  {"Category":<15}  {"GBP":>7}  '
          f'{"Stars":>5}  {"Stock":>5}')
    for index, book in enumerate(rows, start=1):
        title = textwrap.shorten(book["title"], title_width, placeholder="...")
        category = textwrap.shorten(book["category"], 15, placeholder="...")
        stars = f'{book["rating_stars"]}/5'
        print(f'{index:>3}  {title:<{title_width}}  {category:<15}  '
              f'{book["price_gbp"]:>7.2f}  {stars:>5}  {book["stock_quantity"]:>5}')


def show_book(book):
    print("\nBOOK DETAILS")
    details = dict(book)
    details["price_gbp"] = f'GBP {book["price_gbp"]:.2f}'
    details["rating_stars"] = f'{book["rating_stars"]}/5'
    details["in_stock"] = "In stock" if book["in_stock"] else "Out of stock"
    details["cover_path"] = book["cover_path"] or "None in the top 10 downloads"
    for key, label in DATA_LABELS.items():
        print(f"{label:<15} {details[key]}")


def browse_books(books, start_with_filters=False):
    filters = EMPTY_FILTERS
    if start_with_filters:
        filters = configure_filters(books, filters)
    sort = "1"
    offset = 0

    while True:
        results = sorted_books(filtered_books(books, filters), sort)
        rows = results[offset:offset + ROWS_PER_SCREEN]
        print(f"\nBROWSE BOOKS  |  {len(results)} matches  |  {SORTS[sort][0]}")
        print(f"Filters  {filter_label(filters)}")
        if rows:
            print(f"Showing {offset + 1} to {offset + len(rows)} of {len(results)}\n")
            show_table(rows)
        else:
            print("No books match. Change or clear the filters.")

        action = input("\nRow number for details | N next | P previous | F filters\n"
                       "S sort | C clear filters | B back: ").strip().lower()
        if action == "b":
            return
        if action == "n" and offset + ROWS_PER_SCREEN < len(results):
            offset += ROWS_PER_SCREEN
        elif action == "p" and offset > 0:
            offset -= ROWS_PER_SCREEN
        elif action == "f":
            filters = configure_filters(books, filters)
            offset = 0
        elif action == "s":
            for key, (label, _, _) in SORTS.items():
                print(f"  {key}. {label}")
            sort = ask_choice("Sort option: ", SORTS)
            offset = 0
        elif action == "c":
            filters = EMPTY_FILTERS
            offset = 0
        elif action in {str(row) for row in range(1, len(rows) + 1)}:
            show_book(rows[int(action) - 1])
            input("\nPress Enter to return to the list. ")
        else:
            print("That option is unavailable on this screen.")
