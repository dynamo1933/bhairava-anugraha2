"""
Utility script to merge and append entries from New-QnA-Entries.csv
into qna.csv and qna-preview.csv.
"""

import csv
import logging
import os
import shutil
from typing import List

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("append_qna")

# Paths and configuration
WORKSPACE_DIR = r"c:\Users\dynam\Desktop\Bhairva"
QNA_PATH = os.path.join(WORKSPACE_DIR, "qna.csv")
PREVIEW_PATH = os.path.join(WORKSPACE_DIR, "qna-preview.csv")
NEW_ENTRIES_PATH = os.path.join(WORKSPACE_DIR, "New-QnA-Entries.csv")

# Constants representing the bounds for append logic
QNA_APPEND_MIN = 198
QNA_APPEND_MAX = 305

PREVIEW_APPEND_MIN = 300
PREVIEW_APPEND_MAX = 305

ENCODINGS_TO_TRY = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def create_backup(file_path: str) -> None:
    """
    Create a backup copy of the target file.

    Args:
        file_path: Absolute path to the file to back up.
    """
    if not os.path.exists(file_path):
        logger.warning(f"File to backup does not exist: {file_path}")
        return

    backup_path = f"{file_path}.bak"
    try:
        shutil.copyfile(file_path, backup_path)
        logger.info(f"Successfully created backup: {backup_path}")
    except IOError as ex:
        logger.error(f"Failed to create backup for {file_path}: {ex}")
        raise


def load_csv_rows(file_path: str) -> List[List[str]]:
    """
    Load rows from a CSV file trying multiple encodings.

    Args:
        file_path: Absolute path to the CSV file.

    Returns:
        List of CSV rows.
    """
    for encoding in ENCODINGS_TO_TRY:
        try:
            with open(file_path, "r", newline="", encoding=encoding) as f:
                reader = csv.reader(f)
                return list(reader)
        except (UnicodeDecodeError, IOError):
            continue

    msg = f"Could not load or decode CSV file: {file_path}"
    logger.error(msg)
    raise IOError(msg)


def filter_new_records(
    new_rows: List[List[str]],
    min_num: int,
    max_num: int,
    num_idx: int
) -> List[List[str]]:
    """
    Filter the rows of the new CSV file based on entry ID boundaries.

    Args:
        new_rows: The full list of data rows from the new entries file (excluding header).
        min_num: The minimum ID to include (inclusive).
        max_num: The maximum ID to include (inclusive).
        num_idx: Index of the 'num' column.

    Returns:
        Filtered list of rows.
    """
    filtered = []
    for row in new_rows:
        if len(row) <= num_idx:
            continue
        try:
            val = int(row[num_idx].strip())
            if min_num <= val <= max_num:
                filtered.append(row)
        except ValueError:
            # Skip rows where entry ID is not a valid integer
            continue
    return filtered


def save_csv_rows(file_path: str, rows: List[List[str]]) -> None:
    """
    Write rows back to a CSV file in UTF-8 encoding with double quotes.

    Args:
        file_path: Absolute path to the target file.
        rows: All rows (including header) to write.
    """
    try:
        with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            writer.writerows(rows)
        logger.info(f"Successfully saved {len(rows)} rows to {file_path}")
    except IOError as ex:
        logger.error(f"Failed to write CSV file {file_path}: {ex}")
        raise


def append_to_target(
    target_path: str,
    new_rows: List[List[str]],
    min_num: int,
    max_num: int
) -> None:
    """
    Read target, filter matching new records, and write the merged dataset.

    Args:
        target_path: Path to the existing CSV file.
        new_rows: Rows from the new QnA database file (excluding header).
        min_num: The min entry ID range to append.
        max_num: The max entry ID range to append.
    """
    # Create backup before modification
    create_backup(target_path)

    # Load existing rows
    existing_rows = load_csv_rows(target_path)
    if not existing_rows:
        raise ValueError(f"Target file {target_path} is empty or invalid.")

    header = existing_rows[0]
    try:
        num_idx = header.index("num")
    except ValueError as ex:
        logger.error(f"Column 'num' not found in headers of {target_path}: {header}")
        raise ex

    # Filter records from new data matching the target's missing bounds
    records_to_append = filter_new_records(new_rows, min_num, max_num, num_idx)
    logger.info(f"Found {len(records_to_append)} records to append within range [{min_num}, {max_num}].")

    # Combine existing and new records
    merged_rows = existing_rows + records_to_append

    # Save to disk
    save_csv_rows(target_path, merged_rows)


def main() -> None:
    """
    Main entry point to perform the CSV merge operations.
    """
    logger.info("Starting Q&A CSV merge operation...")

    try:
        # Load new entries
        new_raw_rows = load_csv_rows(NEW_ENTRIES_PATH)
        if len(new_raw_rows) < 2:
            logger.error("No entries found in New-QnA-Entries.csv.")
            return

        new_header = new_raw_rows[0]
        new_data_rows = new_raw_rows[1:]
        
        # Verify header columns
        if "num" not in new_header:
            logger.error(f"No 'num' column found in {NEW_ENTRIES_PATH}")
            return

        # Perform merge into qna.csv
        logger.info(f"Updating {QNA_PATH}...")
        append_to_target(QNA_PATH, new_data_rows, QNA_APPEND_MIN, QNA_APPEND_MAX)

        # Perform merge into qna-preview.csv
        logger.info(f"Updating {PREVIEW_PATH}...")
        append_to_target(PREVIEW_PATH, new_data_rows, PREVIEW_APPEND_MIN, PREVIEW_APPEND_MAX)

        logger.info("CSV merge completed successfully.")

    except Exception as ex:
        logger.exception(f"An unexpected error occurred during execution: {ex}")
        raise


if __name__ == "__main__":
    main()
