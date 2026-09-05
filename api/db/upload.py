from http.server import BaseHTTPRequestHandler
import os
import sys
import json
import csv
import io
import base64
import tempfile
import sqlite3

root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from db_helper import get_db_config, execute_turso_statements, ensure_schema_columns, get_all_qna_from_db

COLUMN_ALIASES = {
    "number": "num",
    "num": "num",
    "no": "num",
    "no.": "num",
    "id": "num",
    "entry": "num",
    "s.no": "num",
    "sr no": "num",
    "sr. no.": "num",
    "category": "category",
    "cat": "category",
    "folio": "category",
    "sadhaka (asker)": "asker",
    "sadhaka": "asker",
    "asker": "asker",
    "seeker": "asker",
    "author": "asker",
    "date": "date",
    "time": "time",
    "tags": "tags",
    "tag": "tags",
    "keywords": "tags",
    "question": "question",
    "original question": "question",
    "query": "question",
    "answer": "answer",
    "response": "answer",
    "rephrased question": "rephrased",
    "rephrased": "rephrased",
    "rephrase": "rephrased",
    "approved": "approved",
    "published": "approved",
    "follow up number": "followup",
    "follow up": "followup",
    "followup number": "followup",
    "followup": "followup",
    "follow-up number": "followup",
    "follow-up": "followup",
    "links": "links",
    "link": "links",
    "references": "links",
}

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            db_choice = data.get('db', '').strip().lower()
            filename = data.get('filename', '').strip()
            file_content = data.get('content', '')
        except Exception:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON body"}).encode('utf-8'))
            return
            
        if db_choice not in ("prod", "uat"):
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "db parameter must be 'prod' or 'uat'"}).encode('utf-8'))
            return
        if not filename or not file_content:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "filename and content parameters are required"}).encode('utf-8'))
            return
            
        try:
            entries = []
            ext = os.path.splitext(filename.lower())[1]
            ALL_COLS = ("num", "category", "asker", "date", "time", "tags", "question", "answer", "rephrased", "approved", "followup", "links")
            
            if ext == ".json":
                raw_entries = json.loads(file_content)
                if not isinstance(raw_entries, list):
                    raise Exception("JSON file must contain a list of objects.")
                for idx, entry in enumerate(raw_entries):
                    normalized = {COLUMN_ALIASES.get(str(k).strip().lower(), str(k).strip().lower()): v for k, v in entry.items()}
                    if "num" not in normalized or "question" not in normalized:
                        raise Exception(f"Item at index {idx} must contain at least 'num' and 'question'.")
                    entry_dict = {}
                    for col in ALL_COLS:
                        entry_dict[col] = str(normalized.get(col, "")).strip() if normalized.get(col) is not None else ""
                    entries.append(entry_dict)
                        
            elif ext == ".csv":
                f = io.StringIO(file_content)
                reader = csv.reader(f)
                rows = list(reader)
                if not rows:
                    raise Exception("CSV file is empty.")
                header = [COLUMN_ALIASES.get(h.strip().lower(), h.strip().lower()) for h in rows[0]]
                if "num" not in header or "question" not in header:
                    raise Exception("CSV must contain at least 'num' and 'question' columns.")
                col_map = {col: header.index(col) for col in header}
                
                for row in rows[1:]:
                    if not row or not any(row):
                        continue
                    entry = {}
                    for col_name in ALL_COLS:
                        if col_name in col_map and col_map[col_name] < len(row):
                            entry[col_name] = row[col_map[col_name]].strip()
                        else:
                            entry[col_name] = ""
                    entries.append(entry)
                    
            elif ext == ".db":
                db_bytes = base64.b64decode(file_content)
                with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                    tmp.write(db_bytes)
                    tmp_path = tmp.name
                    
                try:
                    conn = sqlite3.connect(tmp_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM qna;")
                    rows = cursor.fetchall()
                    cols = [COLUMN_ALIASES.get(c[0].strip().lower(), c[0].strip().lower()) for c in cursor.description]
                    conn.close()
                    
                    for row in rows:
                        entry = {}
                        for col_name in ALL_COLS:
                            if col_name in cols:
                                idx = cols.index(col_name)
                                entry[col_name] = str(row[idx]) if row[idx] is not None else ""
                            else:
                                entry[col_name] = ""
                        entries.append(entry)
                finally:
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass
            elif ext in (".xlsx", ".xls"):
                import openpyxl
                import datetime
                
                def format_excel_cell(val, col_name):
                    if val is None:
                        return ""
                    if col_name in ("num", "followup"):
                        if isinstance(val, (int, float)):
                            try:
                                f = float(val)
                                if f.is_integer():
                                    return str(int(f))
                            except Exception:
                                pass
                        s = str(val).strip()
                        parts = [p.strip() for p in s.split(",") if p.strip()]
                        cleaned = []
                        for p in parts:
                            try:
                                f = float(p)
                                if f.is_integer():
                                    cleaned.append(str(int(f)))
                                else:
                                    cleaned.append(p)
                            except Exception:
                                cleaned.append(p)
                        return ", ".join(cleaned) if cleaned else s
                    elif col_name == "time":
                        if isinstance(val, (datetime.time, datetime.datetime)):
                            return val.strftime("%H:%M")
                        return str(val).strip()
                    elif col_name == "date":
                        if isinstance(val, datetime.datetime):
                            return val.strftime("%d.%m.%Y")
                        return str(val).strip()
                    elif col_name == "approved":
                        if isinstance(val, bool):
                            return "true" if val else "false"
                        s = str(val).strip().lower()
                        return "true" if s in ("true", "1", "yes") else ("false" if s in ("false", "0", "no") else s)
                    return str(val).strip()
                
                file_bytes = base64.b64decode(file_content)
                wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
                ws = wb.active
                rows = list(ws.iter_rows(values_only=True))
                if not rows:
                    raise Exception("Excel file is empty.")
                header = [COLUMN_ALIASES.get(str(h).strip().lower(), str(h).strip().lower()) if h is not None else "" for h in rows[0]]
                if "num" not in header or "question" not in header:
                    raise Exception("Excel file must contain at least 'num' and 'question' columns in header.")
                col_map = {col: header.index(col) for col in header if col}
                
                for row in rows[1:]:
                    if not row or not any(c is not None and str(c).strip() for c in row):
                        continue
                    entry = {}
                    for col_name in ALL_COLS:
                        if col_name in col_map and col_map[col_name] < len(row):
                            val = row[col_map[col_name]]
                            entry[col_name] = format_excel_cell(val, col_name)
                        else:
                            entry[col_name] = ""
                    if not entry.get("num") and not entry.get("question"):
                        continue
                    entries.append(entry)
            else:
                raise Exception("Unsupported file format. Must be .json, .csv, .db, or .xlsx")
                
            cfg = get_db_config()
            db_url = cfg[f"{db_choice}_url"]
            db_token = cfg[f"{db_choice}_token"]
            
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS qna (
                num INTEGER PRIMARY KEY,
                category TEXT,
                asker TEXT,
                date TEXT,
                time TEXT,
                tags TEXT,
                question TEXT,
                answer TEXT,
                rephrased TEXT,
                approved TEXT,
                followup TEXT,
                links TEXT
            );
            """
            execute_turso_statements([{"type": "execute", "stmt": {"sql": create_table_sql}}], db_url=db_url, auth_token=db_token)
            ensure_schema_columns(db_url=db_url, auth_token=db_token)
            
            insert_sql = """
            INSERT OR REPLACE INTO qna (
                num, category, asker, date, time, tags, question, answer, rephrased, approved, followup, links
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """
            statements = []

            mode = data.get("mode", "overwrite").strip().lower()
            if mode == "append" and db_choice == "uat":
                # Append mode: preserve existing UAT entries
                existing_tgt = get_all_qna_from_db(db_url, db_token)
                existing_nums = set(int(e["num"]) for e in existing_tgt if str(e.get("num", "")).isdigit())
                max_num = max(existing_nums) if existing_nums else 0

                for d in entries:
                    try:
                        num_val = int(float(str(d["num"]).strip()))
                    except (ValueError, TypeError):
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
                        {"type": "text", "value": d.get("tags", "")},
                        {"type": "text", "value": d.get("question", "")},
                        {"type": "text", "value": d.get("answer", "")},
                        {"type": "text", "value": d.get("rephrased", "")},
                        {"type": "text", "value": d.get("approved", "")},
                        {"type": "text", "value": d.get("followup", "")},
                        {"type": "text", "value": d.get("links", "")}
                    ]
                    statements.append({
                        "type": "execute",
                        "stmt": {
                            "sql": insert_sql,
                            "args": args
                        }
                    })
            else:
                # Overwrite mode: Clear database table first
                execute_turso_statements([{"type": "execute", "stmt": {"sql": "DELETE FROM qna;"}}], db_url=db_url, auth_token=db_token)

                for d in entries:
                    try:
                        num_val = int(float(str(d["num"]).strip()))
                    except (ValueError, TypeError):
                        continue
                    args = [
                        {"type": "integer", "value": str(num_val)},
                        {"type": "text", "value": d.get("category", "")},
                        {"type": "text", "value": d.get("asker", "")},
                        {"type": "text", "value": d.get("date", "")},
                        {"type": "text", "value": d.get("time", "")},
                        {"type": "text", "value": d.get("tags", "")},
                        {"type": "text", "value": d.get("question", "")},
                        {"type": "text", "value": d.get("answer", "")},
                        {"type": "text", "value": d.get("rephrased", "")},
                        {"type": "text", "value": d.get("approved", "")},
                        {"type": "text", "value": d.get("followup", "")},
                        {"type": "text", "value": d.get("links", "")}
                    ]
                    statements.append({
                        "type": "execute",
                        "stmt": {
                            "sql": insert_sql,
                            "args": args
                        }
                    })
                
            batch_size = 50
            for i in range(0, len(statements), batch_size):
                batch = statements[i:i+batch_size]
                execute_turso_statements(batch, db_url=db_url, auth_token=db_token)
                
            action_desc = "appended" if (mode == "append" and db_choice == "uat") else "uploaded and restored"
            res_payload = {"success": True, "message": f"Successfully {action_desc} {len(statements)} entries to {db_choice.upper()} database."}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(res_payload).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Upload error: {str(e)}"}).encode('utf-8'))
