from http.server import BaseHTTPRequestHandler
import os
import sys
import json

root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from db_helper import get_db_config, save_db_config

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
            target_db = data.get('db', '').strip().lower()
        except Exception:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON body"}).encode('utf-8'))
            return
            
        if target_db not in ("prod", "uat"):
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "db parameter must be 'prod' or 'uat'"}).encode('utf-8'))
            return
            
        try:
            cfg = get_db_config()
            cfg["active_db"] = target_db
            save_db_config(cfg)
            res_payload = {"success": True, "active_db": target_db, "message": f"Successfully switched database to {target_db}"}
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
            self.wfile.write(json.dumps({"error": f"Failed to switch database: {str(e)}"}).encode('utf-8'))
