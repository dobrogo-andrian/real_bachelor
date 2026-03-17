import os
import re


def get_next_filename(base_filename, folder, ext=".csv"):
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)

    files = os.listdir(folder)
    matching_files = [f for f in files if f.startswith(base_filename) and f.endswith(ext)]

    max_number = 0
    for file in matching_files:
        try:
            number = int(file.replace(base_filename, "").replace(ext, "").strip("_"))
            if number > max_number:
                max_number = number
        except ValueError:
            continue

    next_number = max_number + 1
    return os.path.join(folder, f"{base_filename}_{next_number}{ext}")


def extract_sort_key(filename):
    name_part = os.path.splitext(filename)[0]
    match = re.match(r"(.*?)(\d+)?$", name_part)
    if match:
        prefix = match.group(1)
        number = int(match.group(2)) if match.group(2) else -1
        return (prefix.lower(), number)
    return (name_part.lower(), -1)
