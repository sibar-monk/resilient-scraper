"""Preview saved exports and open them using the system file associations."""

import csv
import json
import os
import subprocess
import sys

if __package__:
    from .terminal import ask_choice, saved_books, show_covers
else:
    from terminal import ask_choice, saved_books, show_covers


def export_available(path):
    if path.is_file():
        return True
    print(f"File unavailable. Start or resume this range to generate it.\nPath  {path}")
    return False


def open_path(path):
    """Keep the path visible even when there is no graphical opener."""
    print(f"Path  {path}")
    if not path.exists():
        print("This file or folder is unavailable.")
        return
    try:
        if sys.platform == "win32":
            os.startfile(str(path))
        else:
            if sys.platform == "darwin":
                command = "open"
            elif os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
                command = "xdg-open"
            else:
                print("No desktop session detected. Use the path above.")
                return

            launcher = subprocess.Popen(
                [command, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if launcher.wait(timeout=1) != 0:
                print("The system could not open this path. Use the path above.")
    except subprocess.TimeoutExpired:
        return  # Let the opener finish while the terminal menu remains available.
    except OSError:
        print("The system could not open this path. Use the path above.")


def preview_export(path):
    if not export_available(path):
        return

    is_csv = path.suffix == ".csv"
    if is_csv:
        with path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file)
            header = next(reader, [])
            records = list(reader)
        writer = csv.writer(sys.stdout, lineterminator="\n")
    else:
        records = saved_books(path.parent)

    if not records:
        print("The export has no records to preview.")
        return

    page_size = 10 if is_csv else 1
    offset = 0
    while True:
        end = min(offset + page_size, len(records))
        position = f"{offset + 1} to {end}" if is_csv else str(end)
        print(f"\n{path.name}  |  Showing {position} of {len(records)}")
        print(f"Path  {path}\n")
        if is_csv:
            writer.writerow(header)
            writer.writerows(records[offset:end])
        else:
            print(json.dumps(records[offset], ensure_ascii=False, indent=2))

        action = input("\nN next | P previous | O open file | B back: ").strip().lower()
        if action == "b":
            return
        if action == "o":
            open_path(path)
        elif action == "n" and end < len(records):
            offset += page_size
        elif action == "p" and offset > 0:
            offset -= page_size
        else:
            print("That option is unavailable on this screen.")


def browse_covers(folder):
    books = saved_books(folder)
    if not books:
        return
    paths = show_covers(books, folder)
    while True:
        action = input("\nEnter a rank to open a cover | F open image folder | B back: ").strip().lower()
        if action == "b":
            return
        if action == "f":
            open_path(folder / "media")
        elif action in paths:
            open_path(paths[action])
        elif action in {str(rank) for rank in range(1, 11)}:
            print("This cover is unavailable. Run the same range again to retry its download.")
        else:
            print("Choose a cover rank from 1 to 10, F, or B.")


def exports_menu(folder, label):
    csv_path = folder / "books.csv"
    json_path = folder / "books.json"
    actions = {
        "1": (preview_export, csv_path),
        "2": (preview_export, json_path),
        "3": (open_path, csv_path),
        "4": (open_path, json_path),
        "5": (browse_covers, folder),
    }
    while True:
        print(f"\nEXPORTS AND COVERS  |  {label}\nResults folder  {folder}")
        print("1. Preview CSV\n2. Preview JSON\n3. Open CSV file\n"
              "4. Open JSON file\n5. View and open top 10 covers\n0. Back to main menu")
        choice = ask_choice("Choose an export option: ", {"0", *actions})
        if choice == "0":
            return
        action, path = actions[choice]
        try:
            if choice not in {"3", "4"} or export_available(path):
                action(path)
        except (ValueError, OSError, csv.Error) as error:
            print(f"Could not read the selected output. {error}")
