import http.server
import socketserver
import json
import csv
import os
import urllib.parse
from rephrase_agent import rephrase_question
from db_helper import (
    get_all_qna, 
    update_qna_entry, 
    get_db_config, 
    save_db_config, 
    sync_databases, 
    get_all_qna_from_db, 
    execute_turso_statements
)
from analytics_db_helper import (
    init_analytics_db,
    record_guest_event,
    get_guest_analytics_stats
)

PORT = 8080
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

class QnAAPIHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == '/api/qna':
            self.handle_get_qna()
        elif parsed_url.path == '/api/db/status':
            self.handle_get_db_status()
        elif parsed_url.path == '/api/db/download':
            self.handle_get_db_download(parsed_url.query)
        elif parsed_url.path == '/api/analytics/stats':
            self.handle_get_analytics_stats()
        elif parsed_url.path in ('/rephrase', '/rephrase/'):
            self.send_response(301)
            self.send_header('Location', '/rephrase.html')
            self.end_headers()
        else:
            super().do_GET()

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == '/api/rephrase':
            self.handle_post_rephrase()
        elif parsed_url.path == '/api/save':
            self.handle_post_save()
        elif parsed_url.path == '/api/db/switch':
            self.handle_post_db_switch()
        elif parsed_url.path == '/api/db/sync':
            self.handle_post_db_sync()
        elif parsed_url.path == '/api/db/upload':
            self.handle_post_db_upload()
        elif parsed_url.path == '/api/analytics/collect':
            self.handle_post_analytics_collect()
        else:
            self.send_error(404, "API Endpoint Not Found")

    def handle_get_analytics_stats(self):
        try:
            stats = get_guest_analytics_stats()
            self.send_json_response(stats)
        except Exception as e:
            self.send_json_error(500, str(e))

    def handle_post_analytics_collect(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body) if body else {}
            
            # Attach Client IP and User-Agent if not sent
            client_ip = self.headers.get('X-Forwarded-For', self.client_address[0])
            user_agent = self.headers.get('User-Agent', '')
            
            if not data.get('ip_address'):
                data['ip_address'] = client_ip
            if not data.get('user_agent'):
                data['user_agent'] = user_agent
                
            record_guest_event(data)
            self.send_json_response({"success": True})
        except Exception as e:
            self.send_json_error(500, str(e))

    def handle_get_qna(self):
        try:
            entries = get_all_qna()
            self.send_json_response(entries)
        except Exception as e:
            self.send_json_error(500, str(e))

    def handle_get_db_status(self):
        try:
            cfg = get_db_config()
            
            prod_status = "Connected"
            prod_count = 0
            try:
                prod_entries = get_all_qna_from_db(cfg["prod_url"], cfg["prod_token"])
                prod_count = len(prod_entries)
            except Exception as e:
                prod_status = f"Disconnected: {str(e)}"
                
            uat_status = "Connected"
            uat_count = 0
            try:
                uat_entries = get_all_qna_from_db(cfg["uat_url"], cfg["uat_token"])
                uat_count = len(uat_entries)
            except Exception as e:
                uat_status = f"Disconnected: {str(e)}"
                
            response_data = {
                "active_db": cfg["active_db"],
                "prod_url": cfg["prod_url"],
                "prod_status": prod_status,
                "prod_count": prod_count,
                "uat_url": cfg["uat_url"],
                "uat_status": uat_status,
                "uat_count": uat_count
            }
            self.send_json_response(response_data)
        except Exception as e:
            self.send_json_error(500, str(e))

    def handle_post_db_switch(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            target_db = data.get('db', '').strip().lower()
        except Exception:
            self.send_json_error(400, "Invalid JSON body")
            return
            
        if target_db not in ("prod", "uat"):
            self.send_json_error(400, "db parameter must be 'prod' or 'uat'")
            return
            
        try:
            cfg = get_db_config()
            cfg["active_db"] = target_db
            save_db_config(cfg)
            self.send_json_response({"success": True, "active_db": target_db, "message": f"Successfully switched database to {target_db}"})
        except Exception as e:
            self.send_json_error(500, f"Failed to switch database: {str(e)}")

    def handle_post_db_sync(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            source = data.get('source', '').strip().lower()
            target = data.get('target', '').strip().lower()
        except Exception:
            self.send_json_error(400, "Invalid JSON body")
            return
            
        if source not in ("prod", "uat") or target not in ("prod", "uat"):
            self.send_json_error(400, "source and target parameters must be 'prod' or 'uat'")
            return
            
        if source == target:
            self.send_json_error(400, "Source and target databases must be different")
            return
            
        try:
            count = sync_databases(source, target)
            self.send_json_response({"success": True, "message": f"Successfully synced {count} entries from {source} to {target}."})
        except Exception as e:
            self.send_json_error(500, f"Sync error: {str(e)}")

    def handle_get_db_download(self, query):
        params = urllib.parse.parse_qs(query)
        db_choice = params.get('db', ['prod'])[0].strip().lower()
        fmt = params.get('format', ['json'])[0].strip().lower()
        
        if db_choice not in ("prod", "uat"):
            self.send_json_error(400, "db parameter must be 'prod' or 'uat'")
            return
        if fmt not in ("csv", "json", "db"):
            self.send_json_error(400, "format parameter must be 'csv', 'json', or 'db'")
            return
            
        try:
            cfg = get_db_config()
            db_url = cfg[f"{db_choice}_url"]
            db_token = cfg[f"{db_choice}_token"]
            
            entries = get_all_qna_from_db(db_url, db_token)
            
            filename = f"bhairava_{db_choice}_db"
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if fmt == "json":
                content = json.dumps(entries, indent=2).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}_{timestamp}.json"')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                
            elif fmt == "csv":
                import io
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
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                
            elif fmt == "db":
                import tempfile
                import sqlite3
                
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
                            d.get("approved", ""),
                            d.get("followup", "")
                        ))
                        
                    cursor.executemany(insert_sql, rows_to_insert)
                    conn.commit()
                    conn.close()
                    
                    with open(tmp_path, "rb") as f:
                        db_content = f.read()
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                        
                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.sqlite3')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}_{timestamp}.db"')
                self.send_header('Content-Length', str(len(db_content)))
                self.end_headers()
                self.wfile.write(db_content)
                
        except Exception as e:
            self.send_json_error(500, f"Download error: {str(e)}")

    def handle_post_db_upload(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            db_choice = data.get('db', '').strip().lower()
            filename = data.get('filename', '').strip()
            file_content = data.get('content', '')
        except Exception:
            self.send_json_error(400, "Invalid JSON body")
            return
            
        if db_choice not in ("prod", "uat"):
            self.send_json_error(400, "db parameter must be 'prod' or 'uat'")
            return
        if not filename or not file_content:
            self.send_json_error(400, "filename and content parameters are required")
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
                import io
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
                import base64
                import tempfile
                import sqlite3
                
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
                        os.remove(tmp_path)
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
                batch = statements[i:i + batch_size]
                execute_turso_statements(batch, db_url=db_url, auth_token=db_token)
                
            self.send_json_response({"success": True, "message": f"Successfully uploaded and restored {len(entries)} entries to {db_choice} db."})
            
        except Exception as e:
            self.send_json_error(500, f"Upload error: {str(e)}")

    def handle_post_rephrase(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            question = data.get('question', '').strip()
        except Exception:
            self.send_json_error(400, "Invalid JSON body")
            return
 
        if not question:
            self.send_json_error(400, "Question parameter is required")
            return
 
        try:
            rephrased = rephrase_question(question)
            self.send_json_response({"rephrased": rephrased})
        except Exception as e:
            self.send_json_error(500, f"Error from agent: {str(e)}")
 
    def handle_post_save(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            num = str(data.get('num', '')).strip()
            rephrased_text = data.get('rephrased')
            approved_val = data.get('approved')
            category_val = data.get('category')
            question_val = data.get('question')
            answer_val = data.get('answer')
            followup_val = data.get('followup')
        except Exception:
            self.send_json_error(400, "Invalid JSON body")
            return
 
        if not num:
            self.send_json_error(400, "num is required")
            return
 
        if rephrased_text is None and approved_val is None and category_val is None and question_val is None and answer_val is None and followup_val is None:
            self.send_json_error(400, "At least one parameter to update is required")
            return
 
        success = update_qna_entry(
            num,
            rephrased_text=rephrased_text,
            approved_val=approved_val,
            category_val=category_val,
            question_val=question_val,
            answer_val=answer_val,
            followup_val=followup_val
        )
 
        if success:
            self.send_json_response({"success": True, "message": "Updated successfully"})
        else:
            self.send_json_error(500, "Failed to update entry")

    def send_json_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def send_json_error(self, status, message):
        self.send_json_response({"error": message}, status)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def migrate_csvs():
    """
    Ensure 'approved' and 'followup' columns exist in qna.csv.
    """
    for name in ("qna.csv",):
        path = os.path.join(DIRECTORY, name)
        if not os.path.exists(path):
            continue
        
        rows = []
        for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
            try:
                with open(path, 'r', newline='', encoding=enc) as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                if rows:
                    break
            except Exception:
                continue
        
        if not rows:
            continue
            
        header = rows[0]
        header_lower = [h.strip().lower() for h in header]
        changed = False

        if "approved" not in header_lower:
            header.append("approved")
            for r in rows[1:]:
                while len(r) < len(header) - 1:
                    r.append("")
                r.append("true")
            changed = True
            print(f"[+] Migrated {name} to include 'approved' column.")

        # Re-read header_lower after possible append
        header_lower = [h.strip().lower() for h in header]
        if "followup" not in header_lower:
            header.append("followup")
            for r in rows[1:]:
                while len(r) < len(header) - 1:
                    r.append("")
                r.append("")
            changed = True
            print(f"[+] Migrated {name} to include 'followup' column.")

        if changed:
            try:
                with open(path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                    writer.writerows(rows)
            except Exception as e:
                print(f"[-] Failed to migrate {name}: {e}")

if __name__ == '__main__':
    os.chdir(DIRECTORY)
    migrate_csvs()
    
    env_path = os.path.join(DIRECTORY, ".env")
    if os.path.exists(env_path):
        print("[*] Found .env file, loading environment variables...")
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip()

    try:
        init_analytics_db()
    except Exception as e:
        print(f"[-] Analytics DB Init Warning: {e}")

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), QnAAPIHandler) as httpd:
        print(f"[+] Server started at http://localhost:{PORT}")
        print(f"[+] Serving admin dashboard at http://localhost:{PORT}/rephrase.html")
        print("[*] Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[-] Server stopped.")
