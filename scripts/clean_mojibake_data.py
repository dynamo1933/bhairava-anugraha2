import os
import sys
import shutil
import csv
import re

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Ensure workspace root is in sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from db_helper import (
    clean_mojibake_text,
    get_db_config,
    execute_turso_statements,
    is_turso_configured,
    get_all_qna,
    CSV_PATH
)

ALL_COLS = ("num", "category", "asker", "date", "time", "tags", "question", "answer", "rephrased", "approved", "followup", "links")

def backup_csv():
    bak_path = os.path.join(ROOT_DIR, "qna.csv.bak_mojibake")
    if os.path.exists(CSV_PATH):
        shutil.copyfile(CSV_PATH, bak_path)
        print(f"[+] Backed up qna.csv to {bak_path}")

def clean_csv():
    backup_csv()
    rows = []
    encodings = ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1')
    for enc in encodings:
        try:
            with open(CSV_PATH, 'r', newline='', encoding=enc) as f:
                reader = csv.reader(f)
                rows = list(reader)
            if rows:
                print(f"[+] Loaded {len(rows)} rows from qna.csv using {enc}")
                break
        except Exception:
            continue
    else:
        raise Exception("Failed to read qna.csv")

    header = [h.strip().lower() for h in rows[0]]
    cleaned_rows = [rows[0]]
    changes_count = 0

    for row in rows[1:]:
        if not row or not any(row):
            continue
        cleaned_row = []
        row_changed = False
        for cell in row:
            cleaned_val = clean_mojibake_text(cell)
            if cleaned_val != cell:
                row_changed = True
            cleaned_row.append(cleaned_val)
        if row_changed:
            changes_count += 1
        cleaned_rows.append(cleaned_row)

    with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(cleaned_rows)
    print(f"[+] Wrote cleaned data to qna.csv. Rows with modifications: {changes_count}/{len(rows)-1}")

def sync_database(active_db="prod"):
    if not is_turso_configured(active_db=active_db):
        print(f"[-] Turso database '{active_db}' is not configured. Skipping.")
        return

    print(f"[+] Fetching entries from Turso '{active_db}' database...")
    entries = get_all_qna(active_db=active_db)
    print(f"[+] Found {len(entries)} entries in Turso '{active_db}'. Cleaning...")

    statements = []
    updated_entries = 0

    for e in entries:
        num = e.get("num")
        if not num:
            continue

        sets = []
        args = []
        entry_changed = False

        for col in ALL_COLS:
            if col == "num":
                continue
            original_val = e.get(col, "") or ""
            cleaned_val = clean_mojibake_text(original_val)
            if cleaned_val != original_val:
                entry_changed = True
            sets.append(f"{col} = ?")
            args.append({"type": "text", "value": cleaned_val})

        if entry_changed:
            updated_entries += 1
            sql = f"UPDATE qna SET {', '.join(sets)} WHERE num = ?;"
            args.append({"type": "integer", "value": str(num)})
            statements.append({
                "type": "execute",
                "stmt": {
                    "sql": sql,
                    "args": args
                }
            })

    print(f"[+] {updated_entries} entries require update in Turso '{active_db}'.")
    if not statements:
        print(f"[+] Turso '{active_db}' is already completely clean!")
        return

    # Execute in batches of 40 statements
    BATCH_SIZE = 40
    for i in range(0, len(statements), BATCH_SIZE):
        batch = statements[i:i + BATCH_SIZE]
        print(f"    Sending batch {i//BATCH_SIZE + 1}/{(len(statements) + BATCH_SIZE - 1)//BATCH_SIZE} ({len(batch)} entries)...")
        execute_turso_statements(batch, active_db=active_db)

    print(f"[✓] Turso '{active_db}' successfully updated with clean data!")

def verify_all():
    print("\n--- Final Verification ---")
    # 1. Check CSV
    with open(CSV_PATH, 'r', encoding='utf-8', errors='replace') as f:
        csv_text = f.read()
    csv_bad = re.findall(r'(\ufffd|â€|â€™|â€œ|â†’|â€¦|_x00|Ä_)', csv_text)
    print(f"CSV remaining corrupted patterns: {len(csv_bad)}")

    # 2. Check Turso Prod
    for db_name in ("prod", "uat"):
        if is_turso_configured(active_db=db_name):
            entries = get_all_qna(active_db=db_name)
            bad_in_db = 0
            for e in entries:
                text = " ".join(str(e.get(c, "")) for c in ALL_COLS)
                if re.search(r'(\ufffd|â€|â€™|â€œ|â†’|â€¦|_x00|Ä_)', text):
                    bad_in_db += 1
            print(f"Turso '{db_name}' entries with bad patterns: {bad_in_db}/{len(entries)}")

if __name__ == "__main__":
    clean_csv()
    sync_database("prod")
    sync_database("uat")
    verify_all()
