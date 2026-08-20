import os
import csv
import json
import requests
import sys

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(ROOT_DIR, ".env")

def load_env():
    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        os.environ[k.strip()] = v.strip()
        except Exception:
            pass

load_env()

import tempfile

DB_CONFIG_PATH = os.path.join(ROOT_DIR, ".db_config.json")
TMP_DB_CONFIG_PATH = os.path.join(tempfile.gettempdir(), ".db_config.json")
CSV_PATH = os.path.join(ROOT_DIR, "qna.csv")

def get_db_config(active_db_override=None):
    load_env()
    prod_url = os.environ.get("TURSO_DB_URL") or ""
    prod_token = os.environ.get("TURSO_AUTH_TOKEN") or ""
    
    uat_url = os.environ.get("TURSO_UAT_DB_URL") or ""
    uat_token = os.environ.get("TURSO_UAT_AUTH_TOKEN") or ""
    
    config = {
        "active_db": "prod",
        "prod_url": prod_url,
        "prod_token": prod_token,
        "uat_url": uat_url,
        "uat_token": uat_token
    }
    
    for path in (TMP_DB_CONFIG_PATH, DB_CONFIG_PATH):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    config["active_db"] = saved.get("active_db", "prod")
                    if saved.get("prod_url") and not os.environ.get("TURSO_DB_URL"): config["prod_url"] = saved["prod_url"]
                    if saved.get("uat_url") and not os.environ.get("TURSO_UAT_DB_URL"): config["uat_url"] = saved["uat_url"]
                break
            except Exception:
                pass
            
    if active_db_override in ("prod", "uat"):
        config["active_db"] = active_db_override

    # Clean urls starting with libsql:// to https://
    for key in ("prod_url", "uat_url"):
        if config[key] and config[key].startswith("libsql://"):
            config[key] = config[key].replace("libsql://", "https://", 1)
            
    return config

def save_db_config(config):
    clean_cfg = {
        "active_db": config.get("active_db", "prod")
    }
    for path in (DB_CONFIG_PATH, TMP_DB_CONFIG_PATH):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(clean_cfg, f, indent=2)
            break
        except Exception as e:
            print(f"Warning: Could not save db config to {path}: {e}", file=sys.stderr)

def get_active_credentials(active_db=None):
    cfg = get_db_config(active_db_override=active_db)
    if cfg["active_db"] == "uat":
        return cfg["uat_url"], cfg["uat_token"]
    return cfg["prod_url"], cfg["prod_token"]

def is_turso_configured(active_db=None):
    url, token = get_active_credentials(active_db=active_db)
    return bool(url and token)

def execute_turso_statements(statements, db_url=None, auth_token=None, active_db=None):
    """
    Executes a list of statement dicts in a single pipeline.
    """
    if db_url is None or auth_token is None:
        db_url, auth_token = get_active_credentials(active_db=active_db)
        
    if not db_url or not auth_token:
        raise Exception("Turso database credentials not configured.")
        
    url = f"{db_url.rstrip('/')}/v2/pipeline"
    headers = {
        "Authorization": f"Bearer {auth_token}",
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

def get_all_qna(active_db=None):
    """
    Retrieves all Q&A entries.
    Falls back to CSV if Turso is not configured.
    """
    if is_turso_configured(active_db=active_db):
        # Query Turso database
        sql = "SELECT num, category, asker, date, time, question, answer, rephrased, approved, followup FROM qna ORDER BY num;"
        stmt = {
            "type": "execute",
            "stmt": {
                "sql": sql
            }
        }
        try:
            results = execute_turso_statements([stmt], active_db=active_db)
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

def update_qna_entry(num, rephrased_text=None, approved_val=None, category_val=None, question_val=None, answer_val=None, followup_val=None, active_db=None):
    """
    Updates a single Q&A entry by num.
    Falls back to CSV if Turso is not configured.
    """
    if is_turso_configured(active_db=active_db):
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
            execute_turso_statements([stmt], active_db=active_db)
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

def add_qna_entry(entry_data, active_db=None):
    """
    Inserts a new Q&A entry into Turso (or local CSV fallback).
    """
    import datetime
    num = str(entry_data.get('num', '')).strip()
    if not num:
        existing = get_all_qna(active_db=active_db)
        nums = [int(e['num']) for e in existing if str(e.get('num', '')).isdigit()]
        num = str(max(nums) + 1 if nums else 1)
        
    category = str(entry_data.get('category', '')).strip() or "Mantra & Japa"
    asker = str(entry_data.get('asker', '')).strip() or "UAT Contributor"
    now = datetime.datetime.now()
    date_str = str(entry_data.get('date', '')).strip() or now.strftime("%d.%m.%Y")
    time_str = str(entry_data.get('time', '')).strip() or now.strftime("%H:%M")
    question = str(entry_data.get('question', '')).strip()
    answer = str(entry_data.get('answer', '')).strip()
    rephrased = str(entry_data.get('rephrased', '')).strip()
    approved = str(entry_data.get('approved', 'false')).strip().lower()
    followup = str(entry_data.get('followup', '')).strip()
    
    if is_turso_configured(active_db=active_db):
        insert_sql = """
        INSERT OR REPLACE INTO qna (num, category, asker, date, time, question, answer, rephrased, approved, followup)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        args = [
            {"type": "integer", "value": num},
            {"type": "text", "value": category},
            {"type": "text", "value": asker},
            {"type": "text", "value": date_str},
            {"type": "text", "value": time_str},
            {"type": "text", "value": question},
            {"type": "text", "value": answer},
            {"type": "text", "value": rephrased},
            {"type": "text", "value": approved},
            {"type": "text", "value": followup}
        ]
        
        stmt = {
            "type": "execute",
            "stmt": {
                "sql": insert_sql,
                "args": args
            }
        }
        execute_turso_statements([stmt], active_db=active_db)
        return {"success": True, "num": num}

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
            
    if not rows:
        return {"success": False, "error": "CSV empty"}
        
    new_row = [num, category, asker, date_str, time_str, question, answer, rephrased, approved, followup]
    rows.append(new_row)
    
    with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerows(rows)
        
    return {"success": True, "num": num}

def get_all_qna_from_db(db_url, auth_token):
    sql = "SELECT num, category, asker, date, time, question, answer, rephrased, approved, followup FROM qna ORDER BY num;"
    stmt = {
        "type": "execute",
        "stmt": {
            "sql": sql
        }
    }
    results = execute_turso_statements([stmt], db_url=db_url, auth_token=auth_token)
    execute_result = results[0]["response"]["result"]
    cols = [c["name"] for c in execute_result["cols"]]
    rows = execute_result["rows"]
    
    entries = []
    for row in rows:
        entry = {}
        for idx, col_name in enumerate(cols):
            cell = row[idx]
            val = cell.get("value") if cell.get("type") != "null" else ""
            if col_name == "num" and val is not None:
                val = str(val)
            entry[col_name] = val
        entries.append(entry)
    return entries

def sync_databases(source_db_name, target_db_name, mode="overwrite"):
    cfg = get_db_config()
    
    src_url = cfg[f"{source_db_name}_url"]
    src_token = cfg[f"{source_db_name}_token"]
    
    tgt_url = cfg[f"{target_db_name}_url"]
    tgt_token = cfg[f"{target_db_name}_token"]
    
    if not src_url or not src_token:
        raise Exception(f"Source database ({source_db_name}) credentials are not configured.")
    if not tgt_url or not tgt_token:
        raise Exception(f"Target database ({target_db_name}) credentials are not configured.")
        
    # Get all from source
    entries = get_all_qna_from_db(src_url, src_token)
    
    # Ensure target table exists
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
    execute_turso_statements([{"type": "execute", "stmt": {"sql": create_table_sql}}], db_url=tgt_url, auth_token=tgt_token)
    
    insert_sql = """
    INSERT OR REPLACE INTO qna (
        num, category, asker, date, time, question, answer, rephrased, approved, followup
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """
    statements = []

    if mode == "append" and target_db_name == "uat":
        # Append mode: preserve existing UAT data
        existing_tgt = get_all_qna_from_db(tgt_url, tgt_token)
        existing_nums = set(int(e["num"]) for e in existing_tgt if str(e.get("num", "")).isdigit())
        max_num = max(existing_nums) if existing_nums else 0

        for d in entries:
            try:
                num_val = int(d["num"])
            except ValueError:
                continue

            if num_val in existing_nums:
                max_num += 1
                target_num = max_num
            else:
                target_num = num_val

            args = [
                {"type": "integer", "value": str(target_num)},
                {"type": "text", "value": d.get("category", "")},
                {"type": "text", "value": d.get("asker", "")},
                {"type": "text", "value": d.get("date", "")},
                {"type": "text", "value": d.get("time", "")},
                {"type": "text", "value": d.get("question", "")},
                {"type": "text", "value": d.get("answer", "")},
                {"type": "text", "value": d.get("rephrased", "")},
                {"type": "text", "value": d.get("approved", "")},
                {"type": "text", "value": d.get("followup", "")}
            ]
            statements.append({
                "type": "execute",
                "stmt": {
                    "sql": insert_sql,
                    "args": args
                }
            })
    else:
        # Overwrite mode: Clear target table
        execute_turso_statements([{"type": "execute", "stmt": {"sql": "DELETE FROM qna;"}}], db_url=tgt_url, auth_token=tgt_token)

        for d in entries:
            try:
                num_val = int(d["num"])
            except ValueError:
                continue

            args = [
                {"type": "integer", "value": str(num_val)},
                {"type": "text", "value": d.get("category", "")},
                {"type": "text", "value": d.get("asker", "")},
                {"type": "text", "value": d.get("date", "")},
                {"type": "text", "value": d.get("time", "")},
                {"type": "text", "value": d.get("question", "")},
                {"type": "text", "value": d.get("answer", "")},
                {"type": "text", "value": d.get("rephrased", "")},
                {"type": "text", "value": d.get("approved", "")},
                {"type": "text", "value": d.get("followup", "")}
            ]
            statements.append({
                "type": "execute",
                "stmt": {
                    "sql": insert_sql,
                    "args": args
                }
            })
            
    # Execute batch inserts
    batch_size = 50
    for i in range(0, len(statements), batch_size):
        batch = statements[i:i + batch_size]
        execute_turso_statements(batch, db_url=tgt_url, auth_token=tgt_token)
        
    return len(statements)
