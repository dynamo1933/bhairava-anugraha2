import http.server
import socketserver
import json
import csv
import os
import urllib.parse
from rephrase_agent import rephrase_question
from db_helper import get_all_qna, update_qna_entry

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
        try:
            entries = get_all_qna()
            self.send_json_response(entries)
        except Exception as e:
            self.send_json_error(500, str(e))

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
            followup_val = data.get('followup')  # comma-separated string of nums or empty
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

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), QnAAPIHandler) as httpd:
        print(f"[+] Server started at http://localhost:{PORT}")
        print(f"[+] Serving admin dashboard at http://localhost:{PORT}/rephrase.html")
        print("[*] Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[-] Server stopped.")
