import csv
import shutil
import os

def add_rephrased_column(file_path):
    if not os.path.exists(file_path):
        print(f"[-] File not found: {file_path}")
        return
    
    # Read existing content
    rows = []
    used_encoding = 'utf-8-sig'
    # Try different encodings
    for encoding in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            with open(file_path, 'r', newline='', encoding=encoding) as f:
                reader = csv.reader(f)
                rows = list(reader)
            if rows:
                print(f"[+] Loaded {file_path} using encoding: {encoding}")
                used_encoding = encoding
                break
        except Exception:
            continue
    else:
        print(f"[-] Could not decode {file_path}")
        return

    if not rows:
        print(f"[-] Empty file: {file_path}")
        return

    header = rows[0]
    header_lower = [h.strip().lower() for h in header]
    if "rephrased" in header_lower:
        print(f"[!] 'rephrased' column already exists in {file_path}")
        return

    # Add column name "rephrased"
    header.append("rephrased")
    
    # Add empty value for each row
    for row in rows[1:]:
        while len(row) < len(header) - 1:
            row.append("")
        row.append("")

    # Backup original
    shutil.copyfile(file_path, file_path + ".bak")
    print(f"[+] Backup created at {file_path}.bak")
    
    # Write back using utf-8-sig to preserve any byte-order-mark if present, or standard utf-8
    # We write as utf-8 as used in fix_grammar.py
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerows(rows)
    print(f"[+] Added 'rephrased' column to {file_path}")

if __name__ == '__main__':
    workspace_dir = r"c:\Users\dynam\Desktop\Bhairva"
    add_rephrased_column(os.path.join(workspace_dir, "qna.csv"))
    add_rephrased_column(os.path.join(workspace_dir, "qna-preview.csv"))
    print("[+] Migration completed.")
