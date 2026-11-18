"""Start the interactive menu or run the scraper directly."""

import argparse
import sys
from pathlib import Path

if __package__:
    from .exports import browse_covers, exports_menu
    from .scraper import ScrapeError, run_scrape
    from .storage import current_results, group_name, range_lock, read_json, reset_checkpoint, validate_checkpoint
    from .terminal import browse_books, range_label, saved_books, show_summary
else:
    from exports import browse_covers, exports_menu
    from scraper import ScrapeError, run_scrape
    from storage import current_results, group_name, range_lock, read_json, reset_checkpoint, validate_checkpoint
    from terminal import browse_books, range_label, saved_books, show_summary

ROOT = Path(__file__).resolve().parent


def scrape_range(folder, start, *, fresh=False):
    print(f"\nSCRAPE  |  {range_label(start)}", flush=True)
    try:
        with range_lock(folder):
            if fresh:
                reset_checkpoint(folder, start)
            books = run_scrape(folder, start)
    except (ScrapeError, ValueError, OSError) as error:
        print(f"\nRun paused. {error}")
        print(f"Details  {folder / 'scraper.log'}")
        print("Choose the same page range to resume from saved progress.")
        return 1
    show_summary(books, start)
    return 0


def show_results(action, folder, start, label):
    try:
        if action == "4":
            browse_covers(folder)
        elif action == "7":
            exports_menu(folder, label)
        else:
            books = saved_books(folder)
            if books:
                if action == "3":
                    show_summary(books, start)
                else:
                    browse_books(books, start_with_filters=(action == "6"))
    except (ValueError, OSError) as error:
        print(f"Could not open the saved results. {error}")


def sample_menu():
    folder = ROOT / "sample_run"
    while True:
        print("\nSUPPLIED SAMPLE  |  Catalog pages 1 to 5\n"
              "2. Browse books\n3. View summary\n4. View covers\n"
              "6. Filter and sort books\n7. Exports and covers\n0. Back")
        action = input("Choose an option: ").strip()
        if action == "0":
            return
        if action in {"2", "3", "4", "6", "7"}:
            show_results(action, folder, 1, "Supplied sample | Catalog pages 1 to 5")
        else:
            print("Choose a number from the menu.")


def checkpoint_menu(folder, start):
    path = folder / "scraper_state.json"
    backup = folder / "scraper_state.backup.json"
    print(f"\nCHECKPOINT  |  {range_label(start)}")
    try:
        state = read_json(path)
        validate_checkpoint(state, start)
        print(f"Saved {len(state['items'])}/100 books | "
              f"{len(state['completed_page_urls'])}/5 pages complete.")
    except FileNotFoundError:
        print("No main checkpoint found.")
    except (ValueError, OSError) as error:
        print(f"Cannot read the main checkpoint. {error}")
    if backup.is_file():
        print("A backup exists. Start or resume to check it if the main file cannot be used.")
    print(f"Checkpoint path  {path}")
    print("Starting fresh resets progress for this range. Published files stay available.")
    if input("Type RESET to start a fresh scrape, or press Enter to go back: ").strip() == "RESET":
        scrape_range(folder, start, fresh=True)


def menu(start):
    while True:
        folder = ROOT / "output" / group_name(start)
        print(f"\nresilient-scraper  |  {range_label(start)}\n"
              "1. Start or resume scrape\n"
              "2. Browse books\n"
              "3. View summary\n"
              "4. View and open top 10 covers\n"
              "5. Change starting catalog page\n"
              "6. Filter and sort books\n"
              "7. Exports and covers\n"
              "8. Browse supplied sample offline\n"
              "9. Checkpoint status or start fresh\n"
              "0. Exit")
        action = input("Choose an option: ").strip()
        if action == "0":
            return
        if action == "1":
            scrape_range(folder, start)
        elif action == "5":
            value = input(f"Starting catalog page [{start}]: ").strip()
            if value:
                try:
                    start = positive_page(value)
                except argparse.ArgumentTypeError as error:
                    print(error)
        elif action == "8":
            sample_menu()
        elif action == "9":
            checkpoint_menu(folder, start)
        elif action in {"2", "3", "4", "6", "7"}:
            try:
                results = current_results(folder)
                show_results(action, results, start, range_label(start))
            except (ValueError, OSError) as error:
                print(f"Could not locate the published results. {error}")
        else:
            print("Choose a number from the menu.")


def positive_page(value):
    try:
        number = int(value)
        if number >= 1:
            return number
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Enter a whole page number of 1 or higher.")


def main():
    parser = argparse.ArgumentParser(description="resilient-scraper collects and explores 100 books from five catalog pages.")
    parser.add_argument("--start-page", type=positive_page, default=1,
                        help="first catalog page in the group (default: 1)")
    parser.add_argument("--scrape", action="store_true",
                        help="start or resume without opening the menu")
    args = parser.parse_args()

    # Preserve titles with international characters in redirected terminal output.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        if args.scrape:
            return scrape_range(ROOT / "output" / group_name(args.start_page), args.start_page)
        menu(args.start_page)
        return 0
    except KeyboardInterrupt:
        print("\nStopped. Open the same page range to continue from any saved checkpoint.")
        return 130
    except EOFError:
        print("\nInput ended. Run the command again to reopen the menu.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
