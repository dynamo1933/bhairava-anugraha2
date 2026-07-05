import http.server
import socketserver
import json
import csv
import os
import urllib.parse
from rephrase_agent import rephrase_question

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
        else:
            self.send_error(404, "API Endpoint Not Found")

    def handle_get_qna(self):
        csv_path = os.path.join(DIRECTORY, "qna.csv")
        if not os.path.exists(csv_path):
            self.send_json_error(404, "qna.csv file not found")
            return

        rows = []
        for encoding in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
            try:
                with open(csv_path, 'r', newline='', encoding=encoding) as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                if rows:
                    break
            except Exception:
                continue
        else:
            self.send_json_error(500, "Could not decode qna.csv")
            return

        if len(rows) < 1:
            self.send_json_error(500, "qna.csv is empty")
            return

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

        self.send_json_response(entries)

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
        except Exception:
            self.send_json_error(400, "Invalid JSON body")
            return

        if not num:
            self.send_json_error(400, "num is required")
            return

        if rephrased_text is None and approved_val is None:
            self.send_json_error(400, "Either rephrased or approved parameter is required")
            return

        success_qna = self.update_csv("qna.csv", num, rephrased_text, approved_val)

        if success_qna:
            self.send_json_response({"success": True, "message": "Updated successfully on disk"})
        else:
            self.send_json_error(500, "Failed to update qna.csv file on disk")

    def update_csv(self, filename, num, rephrased_text=None, approved_val=None):
        file_path = os.path.join(DIRECTORY, filename)
        if not os.path.exists(file_path):
            return False

        rows = []
        for encoding in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
            try:
                with open(file_path, 'r', newline='', encoding=encoding) as f:
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

        updated = False
        for row in rows[1:]:
            if len(row) > num_idx and row[num_idx].strip() == num:
                if rephrased_text is not None and rephrased_idx != -1:
                    while len(row) <= rephrased_idx:
                        row.append("")
                    row[rephrased_idx] = rephrased_text.strip()
                
                if approved_val is not None and approved_idx != -1:
                    while len(row) <= approved_idx:
                        row.append("")
                    row[approved_idx] = str(approved_val).strip().lower()
                
                updated = True
                break

        if not updated:
            return False

        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                writer.writerows(rows)
            return True
        except Exception:
            return False

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
    Ensure 'approved' column exists in qna.csv.
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
        if "approved" not in header_lower:
            header.append("approved")
            for r in rows[1:]:
                while len(r) < len(header) - 1:
                    r.append("")
                r.append("true")
            
            try:
                with open(path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                    writer.writerows(rows)
                print(f"[+] Migrated {name} to include 'approved' column.")
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

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), QnAAPIHandler) as httpd:
        print(f"[+] Server started at http://localhost:{PORT}")
        print(f"[+] Serving admin dashboard at http://localhost:{PORT}/rephrase.html")
        print("[*] Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[-] Server stopped.")
