from http.server import BaseHTTPRequestHandler
import os
import sys
import json
import csv
import urllib.parse
import datetime
import io
import tempfile
import sqlite3

root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from db_helper import get_db_config, get_all_qna_from_db

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed_url.query)
        db_choice = params.get('db', ['prod'])[0].strip().lower()
        fmt = params.get('format', ['json'])[0].strip().lower()
        
        if db_choice not in ("prod", "uat"):
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "db parameter must be 'prod' or 'uat'"}).encode('utf-8'))
            return
        if fmt not in ("csv", "json", "db"):
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "format parameter must be 'csv', 'json', or 'db'"}).encode('utf-8'))
            return
            
        try:
            cfg = get_db_config()
            db_url = cfg[f"{db_choice}_url"]
            db_token = cfg[f"{db_choice}_token"]
            
            entries = get_all_qna_from_db(db_url, db_token)
            
            filename = f"bhairava_{db_choice}_db"
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if fmt == "json":
                content = json.dumps(entries, indent=2).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}_{timestamp}.json"')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                
            elif fmt == "csv":
                output = io.StringIO()
                writer = csv.writer(output, quoting=csv.QUOTE_ALL)
                writer.writerow(["num", "category", "asker", "date", "time", "question", "answer", "rephrased", "approved", "followup"])
                for d in entries:
                    writer.writerow([
                        d.get("num", ""),
                        d.get("category", ""),
                        d.get("asker", ""),
                        d.get("date", ""),
                        d.get("time", ""),
                        d.get("question", ""),
                        d.get("answer", ""),
                        d.get("rephrased", ""),
                        d.get("approved", ""),
                        d.get("followup", "")
                    ])
                content = output.getvalue().encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}_{timestamp}.csv"')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                
            elif fmt == "db":
                with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                    tmp_path = tmp.name
                    
                try:
                    conn = sqlite3.connect(tmp_path)
                    cursor = conn.cursor()
                    cursor.execute("""
                    CREATE TABLE qna (
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
                    """)
                    
                    insert_sql = """
                    INSERT INTO qna (
                        num, category, asker, date, time, question, answer, rephrased, approved, followup
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """
                    rows_to_insert = []
                    for d in entries:
                        try:
                            num_val = int(d["num"])
                        except ValueError:
                            continue
                        rows_to_insert.append((
                            num_val,
                            d.get("category", ""),
                            d.get("asker", ""),
                            d.get("date", ""),
                            d.get("time", ""),
                            d.get("question", ""),
                            d.get("answer", ""),
                            d.get("rephrased", ""),
                            d.get("approved", "true"),
                            d.get("followup", "")
                        ))
                    cursor.executemany(insert_sql, rows_to_insert)
                    conn.commit()
                    conn.close()
                    
                    with open(tmp_path, 'rb') as f:
                        content = f.read()
                        
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Disposition', f'attachment; filename="{filename}_{timestamp}.db"')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Content-Length', str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                finally:
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Failed to generate download: {str(e)}"}).encode('utf-8'))
