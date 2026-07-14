import os
import csv
import json
import requests
import sys

# Load .env file manually if it exists in the root folder
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(ROOT_DIR, ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ[k.strip()] = v.strip()

TURSO_DB_URL = os.environ.get("TURSO_DB_URL")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")
CSV_PATH = os.path.join(ROOT_DIR, "qna.csv")

def is_turso_configured():
    return bool(TURSO_DB_URL and TURSO_AUTH_TOKEN)

def execute_turso_statements(statements):
    """
    Executes a list of statement dicts in a single pipeline.
    """
    url = f"{TURSO_DB_URL.rstrip('/')}/v2/pipeline"
    headers = {
        "Authorization": f"Bearer {TURSO_AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "requests": statements + [{"type": "close"}]
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise Exception(f"Turso API Error {response.status_code}: {response.text}")
        
    res_data = response.json()
    results = res_data.get("results", [])
    
    for idx, r in enumerate(results[:-1]):
        if r.get("type") == "error":
            raise Exception(f"SQL Error at statement {idx}: {r.get('error', {}).get('message')}")
            
    return results

def get_all_qna():
    """
    Retrieves all Q&A entries.
    Falls back to CSV if Turso is not configured.
    """
    if is_turso_configured():
        # Query Turso database
        sql = "SELECT num, category, asker, date, time, question, answer, rephrased, approved, followup FROM qna ORDER BY num;"
        stmt = {
            "type": "execute",
            "stmt": {
                "sql": sql
            }
        }
        try:
            results = execute_turso_statements([stmt])
            execute_result = results[0]["response"]["result"]
            cols = [c["name"] for c in execute_result["cols"]]
            rows = execute_result["rows"]
            
            entries = []
            for row in rows:
                entry = {}
                for idx, col_name in enumerate(cols):
                    cell = row[idx]
                    val = cell.get("value") if cell.get("type") != "null" else ""
                    # Ensure num is returned as a string to match CSV behavior
                    if col_name == "num" and val is not None:
                        val = str(val)
                    entry[col_name] = val
                entries.append(entry)
            return entries
        except Exception as e:
            # Log error and fallback to CSV
            print(f"[-] Turso error in get_all_qna: {e}. Falling back to local CSV.", file=sys.stderr)
    
    # CSV Fallback
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"qna.csv not found at {CSV_PATH}")
        
    rows = []
    for encoding in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            with open(CSV_PATH, 'r', newline='', encoding=encoding) as f:
                reader = csv.reader(f)
                rows = list(reader)
            if rows:
                break
        except Exception:
            continue
    else:
        raise Exception("Could not decode qna.csv")
        
    if len(rows) < 1:
        return []
        
    header = [h.strip().lower() for h in rows[0]]
    entries = []
    for row in rows[1:]:
        if not row:
            continue
        entry = {}
        for idx, col_name in enumerate(header):
            if idx < len(row):
                entry[col_name] = row[idx]
            else:
                entry[col_name] = ""
        entries.append(entry)
    return entries

def update_qna_entry(num, rephrased_text=None, approved_val=None, category_val=None, question_val=None, answer_val=None, followup_val=None):
    """
    Updates a single Q&A entry by num.
    Falls back to CSV if Turso is not configured.
    """
    if is_turso_configured():
        sets = []
        args = []
        
        if rephrased_text is not None:
            sets.append("rephrased = ?")
            args.append({"type": "text", "value": rephrased_text.strip()})
        if approved_val is not None:
            sets.append("approved = ?")
            args.append({"type": "text", "value": str(approved_val).strip().lower()})
        if category_val is not None:
            sets.append("category = ?")
            args.append({"type": "text", "value": category_val.strip()})
        if question_val is not None:
            sets.append("question = ?")
            args.append({"type": "text", "value": question_val.strip()})
        if answer_val is not None:
            sets.append("answer = ?")
            args.append({"type": "text", "value": answer_val.strip()})
        if followup_val is not None:
            sets.append("followup = ?")
            args.append({"type": "text", "value": str(followup_val).strip()})
            
        if not sets:
            return True
            
        sql = f"UPDATE qna SET {', '.join(sets)} WHERE num = ?;"
        args.append({"type": "integer", "value": str(num)})
        
        stmt = {
            "type": "execute",
            "stmt": {
                "sql": sql,
                "args": args
            }
        }
        try:
            execute_turso_statements([stmt])
            return True
        except Exception as e:
            print(f"[-] Turso error in update_qna_entry: {e}. Falling back to CSV.", file=sys.stderr)
            
    # CSV Fallback
    if not os.path.exists(CSV_PATH):
        return False
        
    rows = []
    for encoding in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            with open(CSV_PATH, 'r', newline='', encoding=encoding) as f:
                reader = csv.reader(f)
                rows = list(reader)
            if rows:
                break
        except Exception:
            continue
    else:
        return False
        
    if not rows:
        return False
        
    header = [h.strip().lower() for h in rows[0]]
    try:
        num_idx = header.index("num")
    except ValueError:
        return False
        
    rephrased_idx = header.index("rephrased") if "rephrased" in header else -1
    approved_idx = header.index("approved") if "approved" in header else -1
    category_idx = header.index("category") if "category" in header else -1
    question_idx = header.index("question") if "question" in header else -1
    answer_idx = header.index("answer") if "answer" in header else -1
    followup_idx = header.index("followup") if "followup" in header else -1
    
    updated = False
    for row in rows[1:]:
        if len(row) > num_idx and row[num_idx].strip() == str(num):
            if rephrased_text is not None and rephrased_idx != -1:
                while len(row) <= rephrased_idx:
                    row.append("")
                row[rephrased_idx] = rephrased_text.strip()
            
            if approved_val is not None and approved_idx != -1:
                while len(row) <= approved_idx:
                    row.append("")
                row[approved_idx] = str(approved_val).strip().lower()
                
            if category_val is not None and category_idx != -1:
                while len(row) <= category_idx:
                    row.append("")
                row[category_idx] = category_val.strip()
                
            if question_val is not None and question_idx != -1:
                while len(row) <= question_idx:
                    row.append("")
                row[question_idx] = question_val.strip()
                
            if answer_val is not None and answer_idx != -1:
                while len(row) <= answer_idx:
                    row.append("")
                row[answer_idx] = answer_val.strip()
                
            if followup_val is not None and followup_idx != -1:
                while len(row) <= followup_idx:
                    row.append("")
                row[followup_idx] = str(followup_val).strip()
                
            updated = True
            break
            
    if not updated:
        return False
        
    try:
        with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            writer.writerows(rows)
        return True
    except Exception:
        return False
