#!/usr/bin/env python3
"""
Migrate Q&A entries from local qna.csv to Turso LibSQL online database.
"""

import csv
import os
import requests
import sys

# Configuration
DB_URL = "https://daqna-dynamo1933.aws-ap-south-1.turso.io/v2/pipeline"
AUTH_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODM3NDY3NDMsImlkIjoiMDE5ZjRmOTctMWUwMS03OGI0LTgxYjUtZDM0YzQyMTMxZTY0Iiwia2lkIjoiU3FmUWRuTTltd05Obm9FdTNCbEF3MWctUmk4ZnpVd2dZM2dYZzhlUjVUZyIsInJpZCI6IjA1MzgzMTZhLTE3OGItNDY4YS04NzlmLTRjZjQ3YTEyMjg0NiJ9._HCWILmpd_dvzt9AFXibb8T4lJIN2zZDmjDaD9q4VYH9f_ZnsmwfGCP1dS0v-33hBsd8hCcvQ7E_b34ArjtdBg"

DIRECTORY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(DIRECTORY, "qna.csv")

def execute_statements(statements):
    """
    Executes a list of statement dicts (with 'sql' and optional 'args') in a single pipeline.
    Each statement should be formatted for the /v2/pipeline endpoint:
    {
        "type": "execute",
        "stmt": {
            "sql": "...",
            "args": [...]
        }
    }
    """
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "requests": statements + [{"type": "close"}]
    }
    
    response = requests.post(DB_URL, headers=headers, json=payload)
    if response.status_code != 200:
        print(f"[-] HTTP Error {response.status_code}: {response.text}")
        response.raise_for_status()
        
    res_data = response.json()
    results = res_data.get("results", [])
    
    for idx, r in enumerate(results[:-1]):  # Skip the close operation result
        if r.get("type") == "error":
            print(f"[-] SQL Error at statement {idx}: {r.get('error', {}).get('message')}")
            sys.exit(1)
            
    return results

def main():
    print("[*] Starting Turso database migration...")
    print(f"[*] Reading local CSV from: {CSV_PATH}")
    
    if not os.path.exists(CSV_PATH):
        print(f"[-] Error: {CSV_PATH} not found.")
        sys.exit(1)
        
    rows = []
    for encoding in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            with open(CSV_PATH, 'r', newline='', encoding=encoding) as f:
                reader = csv.reader(f)
                rows = list(reader)
            if rows:
                break
        except Exception as e:
            print(f"[*] Failed with encoding {encoding}: {e}")
            continue
            
    if not rows:
        print("[-] Error: Could not read or decode CSV file.")
        sys.exit(1)
        
    header = [h.strip().lower() for h in rows[0]]
    data_rows = rows[1:]
    print(f"[+] Loaded {len(data_rows)} entries from CSV.")
    
    # Check that required columns exist
    required_cols = {"num", "category", "asker", "date", "time", "question", "answer", "rephrased", "approved", "followup"}
    header_set = set(header)
    missing = required_cols - header_set
    if missing:
        print(f"[-] Error: Missing columns in CSV: {missing}")
        sys.exit(1)
        
    # Map header names to their indices
    col_map = {col: header.index(col) for col in required_cols}
    
    # Step 1: Create the QnA table if it doesn't exist
    print("[*] Ensuring the 'qna' table exists in the database...")
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS qna (
        num INTEGER PRIMARY KEY,
        category TEXT,
        asker TEXT,
        date TEXT,
        time TEXT,
        question TEXT,
        answer TEXT,
        rephrased TEXT,
        approved TEXT,
        followup TEXT
    );
    """
    create_stmt = {
        "type": "execute",
        "stmt": {
            "sql": create_table_sql
        }
    }
    execute_statements([create_stmt])
    print("[+] Table 'qna' is ready.")
    
    # Step 2: Prepare insert statements
    insert_sql = """
    INSERT OR REPLACE INTO qna (
        num, category, asker, date, time, question, answer, rephrased, approved, followup
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """
    
    statements = []
    for row in data_rows:
        if not row or not any(row):
            continue
            
        # Extract and normalize values
        try:
            num_val = int(row[col_map["num"]].strip())
        except ValueError:
            print(f"[-] Warning: Skipping invalid row with non-integer num: {row}")
            continue
            
        category_val = row[col_map["category"]].strip()
        asker_val = row[col_map["asker"]].strip()
        date_val = row[col_map["date"]].strip()
        time_val = row[col_map["time"]].strip()
        question_val = row[col_map["question"]].strip()
        answer_val = row[col_map["answer"]].strip()
        rephrased_val = row[col_map["rephrased"]].strip()
        approved_val = row[col_map["approved"]].strip()
        followup_val = row[col_map["followup"]].strip()
        
        args = [
            {"type": "integer", "value": str(num_val)},
            {"type": "text", "value": category_val},
            {"type": "text", "value": asker_val},
            {"type": "text", "value": date_val},
            {"type": "text", "value": time_val},
            {"type": "text", "value": question_val},
            {"type": "text", "value": answer_val},
            {"type": "text", "value": rephrased_val},
            {"type": "text", "value": approved_val},
            {"type": "text", "value": followup_val}
        ]
        
        statements.append({
            "type": "execute",
            "stmt": {
                "sql": insert_sql,
                "args": args
            }
        })
        
    print(f"[*] Uploading {len(statements)} entries to database in batches...")
    
    # Execute in batches to prevent payload sizing or timeout issues
    batch_size = 50
    inserted_count = 0
    
    for i in range(0, len(statements), batch_size):
        batch = statements[i:i + batch_size]
        execute_statements(batch)
        inserted_count += len(batch)
        print(f"   [+] Uploaded {inserted_count}/{len(statements)} entries...")
        
    print("\n[+] Migration completed successfully!")
    print(f"[+] Total entries inserted/updated: {inserted_count}")

if __name__ == "__main__":
    main()
