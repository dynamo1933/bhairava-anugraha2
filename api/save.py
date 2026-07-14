from http.server import BaseHTTPRequestHandler
import os
import sys
import json

# Add parent directory to sys.path so we can import db_helper
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from db_helper import update_qna_entry, is_turso_configured

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
            num = str(data.get('num', '')).strip()
            rephrased_text = data.get('rephrased')
            approved_val = data.get('approved')
            category_val = data.get('category')
            question_val = data.get('question')
            answer_val = data.get('answer')
            followup_val = data.get('followup')  # comma-separated string of nums or empty
        except Exception:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON body"}).encode('utf-8'))
            return

        if not num:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "num is required"}).encode('utf-8'))
            return

        if rephrased_text is None and approved_val is None and category_val is None and question_val is None and answer_val is None and followup_val is None:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "At least one parameter to update is required"}).encode('utf-8'))
            return

        # If we are explicitly in Vercel environment but Turso is not configured, don't attempt to write to disk
        if os.environ.get("VERCEL") and not is_turso_configured():
            self.send_response(403)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "Vercel's serverless environment has a read-only filesystem. "
                         "To save changes permanently, please configure the Turso database environment variables "
                         "(TURSO_DB_URL and TURSO_AUTH_TOKEN) in Vercel."
            }).encode('utf-8'))
            return

        # Attempt to update the entry (using db_helper which handles either Turso or local CSV)
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
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "message": "Updated successfully"}).encode('utf-8'))
        else:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "Failed to update entry"
            }).encode('utf-8'))
