"""Run from the project folder with python -m unittest discover -s tests -v."""

import csv
import io
import logging
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bs4 import BeautifulSoup

import scraper
import storage
from validation import validate_book

SAMPLE = Path(__file__).resolve().parents[1] / "sample_run"


class ScraperTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.records = storage.read_json(SAMPLE / "books.json")
        for record in self.records:
            record["cover_path"] = ""

    def test_invalid_record_and_duplicate_id_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "rating_stars"):
            validate_book({**self.records[0], "rating_stars": 99})
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            storage.validate_dataset(self.records[:-1] + [self.records[0]])

    def test_interruption_and_backup_resume(self):
        pages = [scraper.START_URL] + [
            scraper.START_URL + f"catalogue/example-{letter}.html" for letter in "abcdef"
        ]
        products = [
            [scraper.START_URL + f"catalogue/book-{page}-{i}/index.html" for i in range(20)]
            for page in range(len(pages))
        ]
        requested = []

        def fake_html(url, referer, logger):
            requested.append(url)
            if url in pages:
                index = pages.index(url)
                html = "".join(
                    f'<article class="product_pod"><h3><a href="{link}">Book</a></h3></article>'
                    for link in products[index]
                )
                if index + 1 < len(pages):
                    html += f'<li class="next"><a href="{pages[index + 1]}">Next</a></li>'
            else:
                html = """
                <ul class="breadcrumb"><li>Home</li><li><a>Fiction</a></li><li>Book</li></ul>
                <div class="product_main"><h1>Full Book Title</h1>
                  <p class="price_color">£15.00</p><p class="star-rating Four"></p></div>
                <table class="table table-striped">
                  <tr><th>UPC</th><td>abc123</td></tr>
                  <tr><th>Availability</th><td>In stock (12 available)</td></tr>
                </table>
                """
            return BeautifulSoup(html, "html.parser")

        def interrupt(url, referer, logger):
            if url == products[2][5]:
                raise KeyboardInterrupt
            return fake_html(url, referer, logger)

        path = self.folder / "scraper_state.json"
        with redirect_stdout(io.StringIO()):
            with patch.object(scraper, "make_soup", side_effect=interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    scraper.run_scrape(self.folder, 2)
            self.assertEqual(len(storage.read_json(path)["items"]), 25)
            # Corrupt a nested field while keeping the JSON readable.
            state = storage.read_json(path)
            next(iter(state["items"].values()))["record"]["rating_stars"] = 99
            storage.write_json(path, state)
            requested.clear()
            with patch.object(scraper, "make_soup", side_effect=fake_html):
                scraper.run_scrape(self.folder, 2)
                self.assertEqual(
                    set(requested).intersection(products[1] + products[2]),
                    set(products[2][4:]),
                )
                self.assertEqual(storage.read_json(path)["completed_page_urls"], pages[1:6])
                active = storage.current_results(self.folder)
                self.assertEqual(len(storage.read_json(active / "books.json")), 100)
                requested.clear()
                scraper.run_scrape(self.folder, 2)
                self.assertEqual(requested, [])
                self.assertEqual(storage.current_results(self.folder), active)
            self.assertEqual(len(list(self.folder.glob("scraper_state.damaged-*.json"))), 1)

    def test_unusable_checkpoint_is_preserved(self):
        path = self.folder / "scraper_state.json"
        path.write_text("{broken", encoding="utf-8")
        storage.write_json(self.folder / "scraper_state.backup.json", {"pages": [None]})
        with self.assertRaisesRegex(ValueError, "Backup unavailable or invalid"):
            storage.load_checkpoint(self.folder, 1)
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken")

    def test_reset_retains_published_results(self):
        state = storage.empty_state(1)
        storage.save_checkpoint(self.folder / "scraper_state.json", state)
        active = storage.publish_results(self.folder, self.records, state)
        storage.reset_checkpoint(self.folder, 1)
        self.assertEqual(storage.load_checkpoint(self.folder, 1), state)
        self.assertEqual(storage.current_results(self.folder), active)

    def test_failed_csv_keeps_previous_matching_pair(self):
        state = storage.empty_state(1)
        previous = storage.publish_results(self.folder, self.records, state)
        old_json = (previous / "books.json").read_bytes()
        old_csv = (previous / "books.csv").read_bytes()
        self.records[0]["title"] = "Updated Title"
        write_atomic = storage.write_atomic

        def fail_csv(path, *args, **kwargs):
            if path.suffix == ".csv":
                raise PermissionError("Simulated CSV write error")
            return write_atomic(path, *args, **kwargs)

        with patch.object(storage, "write_atomic", side_effect=fail_csv):
            with self.assertRaises(PermissionError):
                storage.publish_results(self.folder, self.records, state)
        self.assertEqual(storage.current_results(self.folder), previous)
        self.assertEqual((previous / "books.json").read_bytes(), old_json)
        self.assertEqual((previous / "books.csv").read_bytes(), old_csv)
        active = storage.publish_results(self.folder, self.records, state)
        self.assertEqual(storage.current_results(self.folder), active)
        self.assertNotEqual(active, previous)
        self.assertEqual(storage.read_json(active / "books.json")[0]["title"], "Updated Title")

    def test_csv_prefix_is_added_without_changing_json(self):
        example = "＝1+1"
        self.records[0]["title"] = example
        storage.write_exports(self.folder, self.records)
        with (self.folder / "books.csv").open(encoding="utf-8-sig", newline="") as file:
            self.assertEqual(next(csv.DictReader(file))["title"], "\t" + example)
        self.assertEqual(storage.read_json(self.folder / "books.json")[0]["title"], example)

    def test_invalid_cached_jpeg_is_downloaded_again(self):
        sample = next((SAMPLE / "media").glob("*.jpg"))
        record = self.records[0]
        book_id = record["item_id"]
        target = self.folder / "media" / f"{book_id}.jpg"
        target.parent.mkdir()
        target.write_bytes(sample.read_bytes()[:100])
        items = {book_id: {"record": record, "cover_url": scraper.START_URL + "media/test.jpg"}}
        logger = logging.Logger("test")
        with patch.object(scraper, "fetch", return_value=SimpleNamespace(content=sample.read_bytes())) as fetch:
            self.assertEqual(scraper.download_covers(self.folder, items, logger)[book_id], f"media/{book_id}.jpg")
            self.assertEqual(scraper.download_covers(self.folder, items, logger)[book_id], f"media/{book_id}.jpg")
            fetch.assert_called_once()
        self.assertTrue(scraper.valid_jpeg(target))

    def test_backoff_and_retry_after(self):
        responses = [
            scraper.requests.exceptions.Timeout("simulated"),
            SimpleNamespace(status_code=429, headers={"Retry-After": "7"}),
            SimpleNamespace(status_code=503, headers={}),
            SimpleNamespace(status_code=200, headers={}),
        ]
        with (
            patch.object(scraper.requests, "get", side_effect=responses) as get,
            patch.object(scraper.random, "uniform", return_value=1.5),
            patch.object(scraper.time, "sleep") as sleep,
            redirect_stdout(io.StringIO()),
        ):
            logger = logging.Logger("test")
            logger.addHandler(logging.NullHandler())
            scraper.fetch(scraper.START_URL, scraper.START_URL, logger)
        self.assertEqual(get.call_count, 4)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1.5, 1, 1.5, 7, 1.5, 4, 1.5])

    def test_cover_pause_keeps_cached_links_and_resume_repairs_only_missing(self):
        ranked = sorted(self.records, key=scraper.cover_rank)[:10]
        items = {
            book["item_id"]: {
                "record": book,
                "cover_url": scraper.START_URL + f"media/{book['item_id']}.jpg",
            }
            for book in self.records
        }
        logger = logging.Logger("cover-test")
        logger.addHandler(logging.NullHandler())
        # Pause at the first, middle, or last rank; also leave a later request pending.
        cases = [((0,), 429), ((4,), 403), ((9,), 401), ((0, 4), 429)]
        for missing, status in cases:
            with self.subTest(missing_ranks=missing, status=status):
                folder = self.folder / f"case-{status}-{missing[0]}-{len(missing)}"
                shutil.copytree(SAMPLE / "media", folder / "media")
                missing_ids = {ranked[index]["item_id"] for index in missing}
                for book_id in missing_ids:
                    (folder / "media" / f"{book_id}.jpg").write_bytes(b"broken JPEG")
                expected = {book["item_id"] for book in ranked} - missing_ids

                with redirect_stdout(io.StringIO()), patch.object(
                    scraper, "fetch", side_effect=scraper.PauseRequests(f"Simulated HTTP {status}")
                ) as fetch:
                    paths = scraper.download_covers(folder, items, logger)
                self.assertEqual(set(paths), expected)
                fetch.assert_called_once()  # No more HTTP requests after the pause.

                records = [{**book, "cover_path": paths.get(book["item_id"], "")}
                           for book in self.records]
                active = storage.publish_results(folder, records, storage.empty_state(1))
                saved = storage.read_json(active / "books.json")
                self.assertEqual({book["item_id"] for book in saved if book["cover_path"]}, expected)
                with (active / "books.csv").open(encoding="utf-8-sig", newline="") as file:
                    csv_books = list(csv.DictReader(file))
                self.assertEqual({book["item_id"] for book in csv_books if book["cover_path"]}, expected)
                self.assertTrue(all(scraper.valid_jpeg(active / paths[book_id]) for book_id in expected))

                def repaired_cover(url, referer, log):
                    return SimpleNamespace(content=(SAMPLE / "media" / url.rsplit("/", 1)[1]).read_bytes())

                with redirect_stdout(io.StringIO()), patch.object(
                    scraper, "fetch", side_effect=repaired_cover
                ) as fetch:
                    repaired = scraper.download_covers(folder, items, logger)
                self.assertEqual(len(repaired), 10)
                self.assertEqual(fetch.call_count, len(missing))
                self.assertTrue(all(scraper.valid_jpeg(folder / path) for path in repaired.values()))

    def test_bad_cover_response_leaves_no_image_or_link(self):
        record = self.records[0]
        book_id = record["item_id"]
        items = {book_id: {"record": record, "cover_url": scraper.START_URL + "media/test.jpg"}}
        logger = logging.Logger("cover-test")
        logger.addHandler(logging.NullHandler())
        with redirect_stdout(io.StringIO()), patch.object(
            scraper, "fetch", return_value=SimpleNamespace(content=b"<html>Try later</html>")
        ):
            self.assertEqual(scraper.download_covers(self.folder, items, logger), {})
        self.assertFalse((self.folder / "media" / f"{book_id}.jpg").exists())


if __name__ == "__main__":
    unittest.main()
