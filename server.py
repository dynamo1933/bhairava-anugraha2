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

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == '/api/qna':
            self.handle_get_qna()
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
            rephrased_text = data.get('rephrased', '').strip()
        except Exception:
            self.send_json_error(400, "Invalid JSON body")
            return

        if not num:
            self.send_json_error(400, "num is required")
            return

        success_qna = self.update_csv("qna.csv", num, rephrased_text)
        success_preview = self.update_csv("qna-preview.csv", num, rephrased_text)

        if success_qna and success_preview:
            self.send_json_response({"success": True, "message": "Updated successfully on disk"})
        else:
            self.send_json_error(500, f"Failed to update files. qna.csv success: {success_qna}, qna-preview.csv success: {success_preview}")

    def update_csv(self, filename, num, rephrased_text):
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
            rephrased_idx = header.index("rephrased")
        except ValueError:
            return False

        updated = False
        for row in rows[1:]:
            if len(row) > num_idx and row[num_idx].strip() == num:
                while len(row) <= rephrased_idx:
                    row.append("")
                row[rephrased_idx] = rephrased_text
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

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), QnAAPIHandler) as httpd:
        print(f"[+] Server started at http://localhost:{PORT}")
        print(f"[+] Serving admin dashboard at http://localhost:{PORT}/rephrase.html")
        print("[*] Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[-] Server stopped.")
