# Demonstration evidence

These are actual VS Code integrated  terminal captures of this version of `resilient-scraper`, taken on 18 November 2026. The live run collected 5 consecutive pages.

| File | What it shows |
| --- | --- |
| [01-terminal-interrupted.png](01-terminal-interrupted.png) | Ctrl+C stops a real live scrape after one complete pages and 20 saved books. |
| [02-terminal-resumed.png](02-terminal-resumed.png) | Restarting loads 20 saved books and resumes the second catalog page. |
| [03-terminal-summary.png](03-terminal-summary.png) | A completed rerun shows 100 validated books, ten cached JPEGs, GBP statistics, and all 29 category counts. |
| [04-books-csv.png](04-books-csv.png) | The terminal reads and previews the first ten rows of the generated CSV. Long CSV fields wrap at the terminal width. |
| [05-books-json.png](05-books-json.png) | The first lines of the sample JSON copied from the completed live results. |
| [06-terminal-browser.png](06-terminal-browser.png) | All five-star books filtered and then sorted by ascending price. |
| [07-terminal-exports.png](07-terminal-exports.png) | The current menu and the published export folder. |
| [08-terminal-json.png](08-terminal-json.png) | The application's JSON preview shows a complete typed record. |
| [09-terminal-covers.png](09-terminal-covers.png) | The ranked top ten and the paths used to open their JPEGs. Rank 1 was also opened successfully in the desktop image viewer. |
| [10-offline-tests.png](10-offline-tests.png) | Ten tests passing, including simulated checkpoint damage and paused cover downloads. The tests do not send HTTP requests. |
| [11-open-image-cover.png](11-open-image-cover.png) | Ten tests passing, including simulated checkpoint damage and paused cover downloads. The tests do not send HTTP requests. |

The paths in these screenshots belong to the verification machine. Your paths will differ.
