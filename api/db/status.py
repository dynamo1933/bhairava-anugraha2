from http.server import BaseHTTPRequestHandler
import os
import sys
import json

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
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
