from http.server import BaseHTTPRequestHandler
import os
import sys
import json
import csv

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

        # If we are explicitly in Vercel environment, don't attempt to write to disk
        # as it will fail or be lost immediately. Instead, return a helpful error.
        if os.environ.get("VERCEL"):
            self.send_response(403)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "Vercel's serverless environment has a read-only filesystem. "
                         "To save changes permanently, please run the server locally (python server.py), "
                         "save your changes there, and push the updated CSV files to GitHub."
            }).encode('utf-8'))
            return

        # Otherwise, attempt to update local files
        success_qna = self.update_csv("qna.csv", num, rephrased_text, approved_val, category_val, question_val, answer_val, followup_val)

        if success_qna:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "message": "Updated successfully on disk"}).encode('utf-8'))
        else:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "Failed to update qna.csv file on disk"
            }).encode('utf-8'))

    def update_csv(self, filename, num, rephrased_text=None, approved_val=None, category_val=None, question_val=None, answer_val=None, followup_val=None):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        file_path = os.path.join(root_dir, filename)
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
        category_idx = header.index("category") if "category" in header else -1
        question_idx = header.index("question") if "question" in header else -1
        answer_idx = header.index("answer") if "answer" in header else -1
        followup_idx = header.index("followup") if "followup" in header else -1

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
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                writer.writerows(rows)
            return True
        except Exception:
            return False
