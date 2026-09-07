import http.server
import socketserver
import json
import csv
import os
import urllib.parse
import secrets

VALID_TOKENS = set()
from rephrase_agent import rephrase_question
from db_helper import (
    get_all_qna, 
    update_qna_entry, 
    get_db_config, 
    save_db_config, 
    execute_turso_statements, 
    get_all_qna_from_db,
    sync_databases,
    ensure_schema_columns
)

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

    def is_authenticated(self, query_params=None):
        auth_header = self.headers.get('Authorization')
        if auth_header:
            parts = auth_header.split(' ')
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                token = parts[1]
                if token in VALID_TOKENS:
                    return True
        
        if query_params:
            parsed_query = urllib.parse.parse_qs(query_params)
            token = parsed_query.get('token', [None])[0]
            if token and token in VALID_TOKENS:
                return True
                
        return False

    def send_unauthorized(self):
        self.send_json_error(401, "Unauthorized: Invalid or missing token")

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        
        # Security blacklist check for files ending with sensitive extensions
        normalized_path = urllib.parse.unquote(parsed_url.path)
        path_parts = [p for p in normalized_path.replace('\\', '/').split('/') if p]
        
        is_sensitive = False
        for part in path_parts:
            if part.startswith('.') or part == '..':
                is_sensitive = True
                break
        
        if not is_sensitive:
            _, ext = os.path.splitext(normalized_path.lower())
            if ext in ('.py', '.env', '.json', '.bak', '.txt', '.md'):
                is_sensitive = True
                
        if is_sensitive:
            self.send_error(403, "Access Forbidden")
            return

        if parsed_url.path == '/api/qna':
            self.handle_get_qna()
        elif parsed_url.path == '/api/db/status':
            if not self.is_authenticated():
                self.send_unauthorized()
                return
            self.handle_get_db_status()
        elif parsed_url.path == '/api/db/download':
            if not self.is_authenticated(query_params=parsed_url.query):
                self.send_unauthorized()
                return
            self.handle_get_db_download(parsed_url.query)
        elif parsed_url.path == '/api/analytics/stats':
            if not self.is_authenticated():
                self.send_unauthorized()
                return
            self.handle_get_analytics_stats()
        elif parsed_url.path in ('/rephrase', '/rephrase/'):
            self.send_response(301)
            self.send_header('Location', '/rephrase.html')
            self.end_headers()
        else:
            super().do_GET()

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == '/api/login':
            self.handle_post_login()
            return
        elif parsed_url.path == '/api/analytics/collect':
            self.handle_post_analytics_collect()
            return
            
        # All other POST endpoints must be authenticated
        if not self.is_authenticated():
            self.send_unauthorized()
            return

        if parsed_url.path == '/api/rephrase':
            self.handle_post_rephrase()
        elif parsed_url.path == '/api/save':
            self.handle_post_save()
        elif parsed_url.path == '/api/add':
            self.handle_post_add()
        elif parsed_url.path == '/api/db/switch':
            self.handle_post_db_switch()
        elif parsed_url.path == '/api/db/sync':
            self.handle_post_db_sync()
        elif parsed_url.path == '/api/db/upload':
            self.handle_post_db_upload()
        else:
            self.send_error(404, "API Endpoint Not Found")

    def handle_post_login(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            username = data.get('username', '').strip()
            password = data.get('password', '')
        except Exception:
            self.send_json_error(400, "Invalid JSON body")
            return
            
        expected_username = os.environ.get('ADMIN_USERNAME', 'admin')
        expected_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
        
        if username == expected_username and password == expected_password:
            token = secrets.token_hex(16)
            VALID_TOKENS.add(token)
            self.send_json_response({"success": True, "token": token})
        else:
            self.send_json_error(401, "Invalid username or password")

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
            active_db = self.headers.get('x-active-db') or self.headers.get('X-Active-DB')
            entries = get_all_qna(active_db=active_db)
            self.send_json_response(entries)
        except Exception as e:
            self.send_json_error(500, str(e))

    def handle_get_db_status(self):
        try:
            active_db = self.headers.get('x-active-db') or self.headers.get('X-Active-DB')
            cfg = get_db_config(active_db_override=active_db)
            
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

    def handle_post_add(self):
        active_db = self.headers.get('x-active-db') or self.headers.get('X-Active-DB')
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
        except Exception:
            self.send_json_error(400, "Invalid JSON body")
            return
            
        if not data.get('question', '').strip():
            self.send_json_error(400, "Question text is required")
            return
            
        try:
            res = add_qna_entry(data, active_db=active_db)
            self.send_json_response({"success": True, "message": "Entry created successfully", "num": res.get("num")})
        except Exception as e:
            self.send_json_error(500, f"Failed to add entry: {str(e)}")

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
            cfg = get_db_config(active_db_override=target_db)
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
            mode = data.get('mode', 'overwrite').strip().lower()
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
            count = sync_databases(source, target, mode=mode)
            action_word = "appended" if mode == "append" else "synced"
            self.send_json_response({"success": True, "message": f"Successfully {action_word} {count} entries from {source.upper()} to {target.upper()}."})
        except Exception as e:
            self.send_json_error(500, f"Sync error: {str(e)}")

    def handle_get_db_download(self, query):
        params = urllib.parse.parse_qs(query)
        db_choice = params.get('db', ['prod'])[0].strip().lower()
        fmt = params.get('format', ['json'])[0].strip().lower()
        
        if db_choice not in ("prod", "uat"):
            self.send_json_error(400, "db parameter must be 'prod' or 'uat'")
            return
        if fmt not in ("csv", "json", "db", "xlsx", "excel"):
            self.send_json_error(400, "format parameter must be 'csv', 'json', 'db', or 'xlsx'")
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
                headers = ["num", "category", "asker", "date", "time", "tags", "question", "answer", "rephrased", "approved", "followup", "links"]
                writer.writerow(headers)
                for d in entries:
                    writer.writerow([d.get(col, "") for col in headers])
                content = output.getvalue().encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}_{timestamp}.csv"')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                
            elif fmt in ("xlsx", "excel"):
                import io
                import openpyxl
                
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "QnA"
                headers = ["num", "category", "asker", "date", "time", "tags", "question", "answer", "rephrased", "approved", "followup", "links"]
                ws.append(headers)
                for d in entries:
                    ws.append([d.get(col, "") for col in headers])
                output = io.BytesIO()
                wb.save(output)
                content = output.getvalue()
                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}_{timestamp}.xlsx"')
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
                        tags TEXT,
                        question TEXT,
                        answer TEXT,
                        rephrased TEXT,
                        approved TEXT,
                        followup TEXT,
                        links TEXT
                    );
                    """)
                    
                    insert_sql = """
                    INSERT INTO qna (
                        num, category, asker, date, time, tags, question, answer, rephrased, approved, followup, links
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                            d.get("tags", ""),
                            d.get("question", ""),
                            d.get("answer", ""),
                            d.get("rephrased", ""),
                            d.get("approved", ""),
                            d.get("followup", ""),
                            d.get("links", "")
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
                import io
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
                        os.remove(tmp_path)
            elif ext in (".xlsx", ".xls"):
                import base64
                import io
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
            
            mode = data.get('mode', 'overwrite').strip().lower()
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

            if mode == 'append' and db_choice == 'uat':
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
                
            print(f"[DEBUG UPLOAD] ext={ext}, len(entries)={len(entries)}, len(statements)={len(statements)}", flush=True)
            batch_size = 50
            for i in range(0, len(statements), batch_size):
                batch = statements[i:i + batch_size]
                execute_turso_statements(batch, db_url=db_url, auth_token=db_token)
                
            action_desc = "appended" if (mode == "append" and db_choice == "uat") else "uploaded and restored"
            self.send_json_response({"success": True, "message": f"Successfully {action_desc} {len(statements)} entries to {db_choice.upper()} database."})
            
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
            tags_val = data.get('tags')
            links_val = data.get('links')
        except Exception:
            self.send_json_error(400, "Invalid JSON body")
            return
 
        if not num:
            self.send_json_error(400, "num is required")
            return
 
        if (rephrased_text is None and approved_val is None and category_val is None and 
            question_val is None and answer_val is None and followup_val is None and
            tags_val is None and links_val is None):
            self.send_json_error(400, "At least one parameter to update is required")
            return
 
        success = update_qna_entry(
            num,
            rephrased_text=rephrased_text,
            approved_val=approved_val,
            category_val=category_val,
            question_val=question_val,
            answer_val=answer_val,
            followup_val=followup_val,
            tags_val=tags_val,
            links_val=links_val
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
        if "tags" not in header_lower:
            header.append("tags")
            for r in rows[1:]:
                while len(r) < len(header) - 1:
                    r.append("")
                r.append("")
            changed = True
            print(f"[+] Migrated {name} to include 'tags' column.")

        header_lower = [h.strip().lower() for h in header]
        if "links" not in header_lower:
            header.append("links")
            for r in rows[1:]:
                while len(r) < len(header) - 1:
                    r.append("")
                r.append("")
            changed = True
            print(f"[+] Migrated {name} to include 'links' column.")

        if changed:
            try:
                with open(path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                    writer.writerows(rows)
            except Exception as e:
                print(f"[-] Failed to migrate {name}: {e}")

if __name__ == '__main__':
    os.chdir(DIRECTORY)
    
    env_path = os.path.join(DIRECTORY, ".env")
    if os.path.exists(env_path):
        print("[*] Found .env file, loading environment variables...")
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip()

    migrate_csvs()

    try:
        ensure_schema_columns(active_db="prod")
        ensure_schema_columns(active_db="uat")
    except Exception as e:
        print(f"[-] Schema ensure warning: {e}")

    try:
        init_analytics_db()
    except Exception as e:
        print(f"[-] Analytics DB Init Warning: {e}")

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("", PORT), QnAAPIHandler) as httpd:
        print(f"[+] Server started at http://localhost:{PORT}")
        print(f"[+] Serving admin dashboard at http://localhost:{PORT}/rephrase.html")
        print("[*] Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[-] Server stopped.")
