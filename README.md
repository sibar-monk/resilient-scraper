# resilient-scraper

Collect 100 unique books from five consecutive catalog pages at [Books to Scrape](https://books.toscrape.com/), an intentionally scrapeable practice site. The terminal menu runs the scrape and lets you explore the saved results. The project uses Python, Requests, Beautiful Soup, and Pillow for JPEG checks.

## Set up in VS Code

Open the **`core/`** folder in VS Code. Open **Terminal → New Terminal** and check that `main.py` is in the current folder. Run the commands below with **Python 3.12**.

| Action | Windows PowerShell | macOS or Linux |
| --- | --- | --- |
| Create a virtual environment | `py -3.12 -m venv project_venv` | `python3.12 -m venv project_venv` |
| Install the project dependencies | `.\project_venv\Scripts\python.exe -m pip install -r requirements.txt` | `./project_venv/bin/python -m pip install -r requirements.txt` |
| Open the menu | `.\project_venv\Scripts\python.exe main.py` | `./project_venv/bin/python main.py` |

These commands use the virtual environment directly. In an already activated virtual environment, run `python main.py` from the folder containing `main.py`. The requirements file retains your supplied version pins and adds Pillow for cover checks. The application uses Requests, Beautiful Soup, and Pillow; its other modules come with Python. Flask and dotenv remain among the supplied pins but are not used. No web server, database, account, or API key is needed.

## Collect and explore the books

1. Open the menu. The heading shows **Catalog pages 1 to 5**. To select another group, choose **5** and enter its first page. For example, starting at **2** selects pages **2 to 6**.
2. Choose **1** to start or resume. An uninterrupted run commonly takes several minutes because requests are spaced out. Follow the count shown on screen.
3. When the run finishes, choose **2** to browse the saved books or **6** to open the filter menu directly. Set any filters in the order you like, then choose **0** in the filter menu to show matching books. In the book list, use **F** to edit filters, **S** to sort, **N/P** to move between screens, or enter a row number to see its full record. Choose **C** to clear filters or **B** to go back.
4. Choose **3** for the summary or **7** for **Exports and covers**. **4** is a shortcut to the ranked covers. Choose **8** to browse the supplied sample offline. Choose **9** to see progress or start the selected range fresh. Choose **0** to exit.

To start or resume directly, use the following command in an activated virtual environment. The same arguments select the same checkpoint.

```text
python main.py --scrape --start-page 2
```

## Preview or open results from the terminal

At the main menu choose **7. Exports and covers**. The menu uses the range shown at the top of the screen.

| Menu choice | How to use it |
| --- | --- |
| **1. Preview CSV** | Read the header and up to 10 CSV rows at a time, in saved item ID order. |
| **2. Preview JSON** | Read one complete, indented JSON record at a time, including its numeric and boolean values. |
| **3. Open CSV file** or **4. Open JSON file** | Open the complete file in the default application configured on your computer. |
| **5. View and open top 10 covers** | See the ranked books and local paths. Enter a rank from **1–10** to open that JPEG, or press **F** to open the media folder. |

In a CSV or JSON preview, press **N** for next, **P** for previous, **O** to open the full file, or **B** to go back. The cover list also uses **B** to go back. The program prints the absolute path when you try to open a file or folder. VS Code and other desktop terminals use the system opener on Windows, macOS, and Linux. If the computer has no desktop session or default application for the file, use the printed path. CSV and JSON previews work inside the terminal in either case.

## Recover from an interruption

1. Start a scrape and wait until at least one progress line shows books saved. Press **Ctrl+C** in that terminal.
2. Run the same command again. If using the menu, select the same starting page and choose **1**.
3. Look for **Checkpoint loaded** and the count of already saved books. The scraper continues with the missing books on the unfinished page. After all five pages finish, a repeated run reuses the saved books and checks for any missing cover images.

The checkpoint stores identified catalog pages, product links, completed page URLs, and validated records keyed by item ID. After each successful book, the scraper keeps the previous committed checkpoint as `scraper_state.backup.json` and replaces the main file. It validates the page sequence and saved records when loading either file. If a book remains invalid after a fresh detail fetch, the run leaves its page unfinished and logs the field and URL in `scraper.log`. If a page cannot supply 20 distinct book links or a product repeats across pages, the selected group pauses and explains the reason. Choose a different starting page for a separate five-page group when needed.

If the main checkpoint is missing or invalid, the scraper tries the backup. It preserves any damaged main file as `scraper_state.damaged-*.json`, restores a valid backup, and reports how many books it recovered. The backup may be one save behind. If neither file is usable, the scraper pauses and leaves both files in place. Option **9** shows progress and offers a deliberate reset. Typing **RESET** starts the same range from zero and leaves its previous published results accessible until a new set is ready.

## How the scraper works

- **Dynamic pagination.** The scraper starts at the site homepage, finds `li.next a` in the HTML, and resolves the link against the current page URL. An alternate starting page is reached by following the same links. Exactly five consecutive pages contribute to a finished dataset.
- **Master and detail.** A catalog page supplies book links. Each detail page supplies the full title, UPC, category, price, rating, and exact stock count. The scraper normalizes the absolute HTTPS product URL and takes the first 16 hexadecimal characters of its SHA-256 hash. Repeated URLs get the same ID.
- **Request pacing and recovery.** Requests carry a project User-Agent, an Accept-Language header, and a Referer for the page that led to the URL. Each attempt has a 1.0 to 2.5 second random delay and a connection/read timeout. A temporary request failure gets up to three retries with base waits of 1, 2, and 4 seconds, plus the random delay. For rate limits and retryable server responses, a longer `Retry-After` value takes precedence. Repeated HTTP 429 responses pause further requests.
- **Validation and exports.** The source fields are checked before checkpointing. The final exports require 100 unique validated records. Both use ascending item ID order. The CSV uses UTF-8 with a BOM, quotes every cell, and shows prices to two decimal places. The writer prefixes formula-like title, UPC, or category text with a tab inside the quoted cell, including common full-width prefixes. This is an [Excel-oriented mitigation](https://community.owasp.org/attacks/CSV_Injection). Spreadsheet import behavior varies. Use the indented JSON when you need original text and native number and boolean types.
- **Cover ranking.** Stars sort highest first. Ties go to the cheaper book, then the ascending item ID. The top 10 covers use filenames like `media/<item_id>.jpg`. Paths are relative to the folder containing the CSV and JSON. Pillow decodes each JPEG before accepting it. The scraper checks all ten cached images first, then requests only missing or invalid ones. If requests pause, all usable cached and newly downloaded covers keep their links in both exports. Resume the same range to retry the remaining images. An empty path means no cover is available for that row; books outside the top ten also have empty paths.

**Exactly 100 from 5 consecutive pages means exactly 100 valid books from 5 consecutive pages.** If one required record remains invalid, the selected five-page group stays unfinished. The program cannot truthfully turn 99 valid books into 100 without recovering that book. It never invents values, duplicates a record, or silently adds a sixth page. Resume after the source or parser issue is resolved, or select a different complete group of five consecutive pages. Cover failures are separate: they may reduce the image count, while the 100 validated book records still export.


## How exports stay together

The scraper writes CSV, JSON, available covers, and `run_summary.json` to one new results folder. When the files are ready, it atomically replaces `current_results.json` with the name of that folder. The terminal uses this pointer to open one consistent set. If writing a file fails, the previous set remains current. Identical results reuse the current folder. Older folders remain available, so previously opened files are kept.

The program prints the published folder after success. Share the two exports from that folder together with its `media/` directory to preserve the cover paths. The run summary lists each catalog URL and its validated book count.

## Find the files

All paths in this table are relative to the folder containing `main.py`.

| Path | Purpose |
| --- | --- |
| `main.py` | Terminal entry point and menu |
| `__init__.py` | Identifies the folder as a Python package when the files are placed in `core/` |
| `scraper.py` | Requests, pagination, detail parsing, checks, and cover downloads |
| `storage.py` | Checkpoint files and CSV and JSON writing |
| `terminal.py` | Offline browsing, filters, sorting, details, and summary |
| `exports.py` | Terminal export previews and opening CSV, JSON, JPEGs, or the media folder |
| `validation.py` | Canonical URLs, stable IDs, and record validation shared by parsing and storage |
| `requirements.txt` | Required Dependencies |
| `tests/` | Offline checks for resume, exports, validation, retries, and covers |
| `output/pages-01-05/scraper_state.json` | Checkpoint for the default group | 
| `output/pages-01-05/scraper_state.backup.json` | Previous committed checkpoint |
| `output/pages-01-05/current_results.json` | Name of the current published results folder |
| `output/pages-01-05/results/run-*/` | Matching CSV, JSON, available media, and run summary |
| `output/pages-01-05/media/` | Reusable cover cache |
| `output/pages-01-05/scraper.log` | Request and validation messages |
| `screenshots/` | Evidence from the terminal run and dataset previews |
| `sample_run/` | CSV, JSON, run summary, and ten cover images from the verified live run of pages 2 to 6 |

sample_run/ and output result from running the project and page numbers are according to the run considered. Here, stated examples are the runs from Verification manchine.

Each starting page uses its own output folder. Run one scrape at a time for a given range.

A completed rerun reuses the saved book snapshot for that range. Separate, overlapping ranges may contain the same book, with the same ID in each range.

Choose **8** to browse the supplied results offline, including the exports and covers. Use a fresh extraction for your own checkpoint demonstration.

## Run offline tests

From the folder containing `main.py`, with the project environment activated, run:

```text
python -m unittest discover -s tests -v
```

Á folder named 'sample-run' is placed for offline tests to show results. Outputs belong to the verification machine runs. You can create your own sample_run folder by copying the appropriate final output files into that folder.

On Windows PowerShell you can use `.\project_venv\Scripts\python.exe` in place of `python`. On macOS and Linux use `./project_venv/bin/python`. The ten tests use local files and simulated responses to check checkpoint recovery, duplicate prevention, retry delays, coordinated publishing, CSV formatting, and JPEG repair. The cover regression test pauses at different ranks, checks that CSV and JSON retain all usable cached links, and confirms that a resume downloads only the missing images. It does not deliberately trigger rate limits on the website.

## Project requirements and verification

The first column quotes the assignment. Use the last column to see each requirement in the code, the included evidence, or a fresh run.

| Project requirement | Project design | Code and evidence to review |
| --- | --- | --- |
| **1.** “Scrape Books to Scrape (http://books.toscrape.com/) using dynamic DOM pagination (following the "next" button link) — hardcoding page URLs (e.g., page-1.html) is prohibited.” | Start at the site's HTTPS home page and resolve each catalog page's Next link. An alternate starting page follows the same Next links. | In [scraper.py](scraper.py), see `catalog_links`, `locate_start`, and `run_scrape`. Compare adjacent `pages` entries in `scraper_state.json`. |
| **2.** “Implement Two-Stage (Master-Detail) scraping: navigate into each book's individual product page to extract metadata not available on the main catalog listing.” | Catalog pages provide product links. Detail pages provide the full title and product metadata. | In [scraper.py](scraper.py), see `new_page`, `scrape_page`, and `parse_book`. Open any saved `source_url` and compare its UPC and stock count with the export. |
| **3.** “Collect exactly 100 unique product records across 5 consecutive catalog pages.” | Require 20 distinct links on each of five consecutive pages and 100 unique validated records before export. | See `new_page` and `run_scrape` in [scraper.py](scraper.py) and `write_exports` in [storage.py](storage.py). Check the chosen range and **100 validated** in [the console summary](screenshots/03-terminal-summary.png). |
| **4.** “Extract and sanitize: item_id (deterministic SHA-256 short hash of the product URL), full title, upc code, category, price_gbp (cleaned float), rating_stars (integer 1 to 5), stock_quantity (exact integer parsed from "In stock (X available)"), in_stock (boolean), and canonical source_url.” | Clean text and URLs, validate required values, convert prices, ratings, and stock counts to numbers, and use the first 16 hexadecimal characters of the URL hash. | See [validation.py](validation.py) for `canonical_url`, `item_id_for`, and `validate_book`. See `parse_book` in [scraper.py](scraper.py). Open **7 → 2** for a full record, or inspect [sample JSON](sample_run/books.json). |
| **5.** “Include realistic HTTP headers (User-Agent, Accept-Language, Referer) and randomized jitter sleep (1.0 to 2.5 seconds) between requests.” | Identify the course scraper, set the language preference and referring URL, and wait a random 1.0–2.5 seconds before each request attempt. | In [scraper.py](scraper.py), see `HEADERS` and `fetch`. |
| **6.** “Implement exponential backoff retry logic (max_retries=3) handling RequestException, timeouts, rate limits (429), and gateway errors (500, 502, 503, 504).” | Use up to three retries after the first attempt. Wait 1, 2, and 4 seconds plus jitter, with a longer server-supplied Retry-After taking precedence. | See `MAX_RETRIES`, `RETRY_CODES`, `retry_after_seconds`, and `fetch` in [scraper.py](scraper.py). Run `test_backoff_and_retry_after` in [the offline tests](tests/test_scraper.py) for a timeout, 429, 503, and success sequence. |
| **7.** “Maintain a local checkpoint file (scraper_state.json) tracking completed page URLs and scraped item_ids so interrupted runs resume automatically from the last unfinished page.” | Each range has one checkpoint. Save a validated book after each successful detail page and mark a catalog page complete after all its books are saved. | See `scrape_page` and `run_scrape` in [scraper.py](scraper.py), and `load_checkpoint` and `write_atomic` in [storage.py](storage.py). Follow the restart walkthrough and look for **Checkpoint loaded**. |
| **8.** “Validate each scraped record against the required schema and log any malformed items without crashing the script.” | Validate required fields before saving. Log the failed field and book URL, try malformed detail pages again, and report persistent omissions as unfinished work. | See `parse_book` and `scrape_page` in [scraper.py](scraper.py) and `validate_book` in [validation.py](validation.py). When a failure occurs, find its entry in the selected range's `scraper.log`. |
| **9.** “Save the validated records to both CSV and JSON files, and generate a console summary showing total records, average book price, category breakdown, and the cheapest/most expensive books.” | Save both exports in ascending item ID order. Show all requested statistics in the terminal summary. | See `write_exports` and `publish_results` in [storage.py](storage.py) and `show_summary` in [terminal.py](terminal.py). Choose **3** for the summary and **7** for [terminal export access](screenshots/07-terminal-exports.png). |
| **10.** “Prevent duplicate product records across multiple or resumed runs using the deterministic item_id hash.” | Key saved records by item ID, reuse previously validated records, and check uniqueness before export. | See `item_id_for` in [validation.py](validation.py) and `scrape_page` in [scraper.py](scraper.py). Restart the same range and check that it reuses the saved count and the finished files have 100 distinct IDs. |
| **Bonus.** “Automatically download the book cover image (.jpg) for the top 10 highest-rated books into a local media folder and link the local file path in your CSV output.” | Rank by rating descending, price ascending, then item ID ascending. Save each cover as `media/<item_id>.jpg` and put the relative path in `cover_path`. | See `cover_rank` and `download_covers` in [scraper.py](scraper.py). Choose **7 → 5**, enter a rank, and match the JPEG name to the `cover_path` in [sample CSV](sample_run/books.csv). |

> “Scrape only websites that permit automated access, respect rate limits with jitter delays, and never hardcode pagination URLs.”

The scraper targets only Books to Scrape. `canonical_url` checks the host, and `fetch` paces requests and pauses on persistent rate limits and access denials. See [validation.py](validation.py) and [scraper.py](scraper.py).

