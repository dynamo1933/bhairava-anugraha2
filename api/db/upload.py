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

from db_helper import get_db_config, execute_turso_statements

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
            
            if ext == ".json":
                entries = json.loads(file_content)
                if not isinstance(entries, list):
                    raise Exception("JSON file must contain a list of objects.")
                for idx, entry in enumerate(entries):
                    if "num" not in entry or "question" not in entry:
                        raise Exception(f"Item at index {idx} must contain at least 'num' and 'question'.")
                    for col in ("num", "category", "asker", "date", "time", "question", "answer", "rephrased", "approved", "followup"):
                        entry[col] = str(entry.get(col, "")).strip()
                        
            elif ext == ".csv":
                f = io.StringIO(file_content)
                reader = csv.reader(f)
                rows = list(reader)
                if not rows:
                    raise Exception("CSV file is empty.")
                header = [h.strip().lower() for h in rows[0]]
                if "num" not in header or "question" not in header:
                    raise Exception("CSV must contain at least 'num' and 'question' columns.")
                col_map = {col: header.index(col) for col in header}
                
                for row in rows[1:]:
                    if not row or not any(row):
                        continue
                    entry = {}
                    for col_name in ("num", "category", "asker", "date", "time", "question", "answer", "rephrased", "approved", "followup"):
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
                    cursor.execute("SELECT num, category, asker, date, time, question, answer, rephrased, approved, followup FROM qna;")
                    rows = cursor.fetchall()
                    cols = [c[0] for c in cursor.description]
                    conn.close()
                    
                    for row in rows:
                        entry = {}
                        for idx, col_name in enumerate(cols):
                            entry[col_name] = str(row[idx]) if row[idx] is not None else ""
                        entries.append(entry)
                finally:
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass
            else:
                raise Exception("Unsupported file format. Must be .json, .csv, or .db")
                
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
                question TEXT,
                answer TEXT,
                rephrased TEXT,
                approved TEXT,
                followup TEXT
            );
            """
            execute_turso_statements([{"type": "execute", "stmt": {"sql": create_table_sql}}], db_url=db_url, auth_token=db_token)
            execute_turso_statements([{"type": "execute", "stmt": {"sql": "DELETE FROM qna;"}}], db_url=db_url, auth_token=db_token)
            
            insert_sql = """
            INSERT OR REPLACE INTO qna (
                num, category, asker, date, time, question, answer, rephrased, approved, followup
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """
            statements = []
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
                
            batch_size = 50
            for i in range(0, len(statements), batch_size):
                batch = statements[i:i+batch_size]
                execute_turso_statements(batch, db_url=db_url, auth_token=db_token)
                
            res_payload = {"success": True, "message": f"Successfully uploaded and restored {len(entries)} entries to {db_choice.upper()} database."}
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
