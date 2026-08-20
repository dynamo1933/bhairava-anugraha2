import os
import requests
import json
import time

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(ROOT_DIR, ".env")

def load_env():
    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        os.environ[k.strip()] = v.strip()
        except Exception:
            pass

load_env()

def get_analytics_db_config():
    load_env()
    url = os.environ.get("TURSO_ANALYSIS_DB_URL") or ""
    token = os.environ.get("TURSO_ANALYSIS_AUTH_TOKEN") or ""
    return {
        "url": url.strip(),
        "token": token.strip()
    }

def execute_turso_pipeline(url, token, requests_payload):
    """
    Executes raw SQL requests using Turso HTTP v2 pipeline endpoint.
    """
    if not url or not token:
        raise ValueError("Turso Analytics DB URL or Auth Token is missing")

    clean_url = url.rstrip('/')
    if clean_url.startswith("libsql://"):
        clean_url = clean_url.replace("libsql://", "https://")
    pipeline_endpoint = f"{clean_url}/v2/pipeline"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {"requests": requests_payload}

    res = requests.post(pipeline_endpoint, headers=headers, json=payload, timeout=12)
    if res.status_code != 200:
        raise RuntimeError(f"Turso HTTP API error {res.status_code}: {res.text}")

    data = res.json()
    results = []
    for resp in data.get("results", []):
        if resp.get("type") == "ok":
            response_obj = resp.get("response", {})
            result_obj = response_obj.get("result", {})
            results.append(result_obj)
        elif resp.get("type") == "error":
            err_msg = resp.get("error", {}).get("message", "Unknown Turso Error")
            raise RuntimeError(f"Turso statement execution error: {err_msg}")
        else:
            results.append(None)
    return results

def init_analytics_db():
    """
    Initialize guest_events table and indexes if missing.
    """
    cfg = get_analytics_db_config()
    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS guest_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_id TEXT,
            session_id TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            event_type TEXT,
            page_url TEXT,
            page_title TEXT,
            search_query TEXT,
            download_file TEXT,
            api_endpoint TEXT,
            response_time_ms REAL DEFAULT 0,
            status_code INTEGER DEFAULT 200,
            error_flag INTEGER DEFAULT 0,
            session_duration_sec REAL DEFAULT 0,
            page_duration_sec REAL DEFAULT 0,
            browser TEXT,
            os TEXT,
            device TEXT,
            ip_address TEXT,
            country TEXT,
            city TEXT,
            user_agent TEXT
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_guest_events_ts ON guest_events(timestamp);",
        "CREATE INDEX IF NOT EXISTS idx_guest_events_session ON guest_events(session_id);",
        "CREATE INDEX IF NOT EXISTS idx_guest_events_guest ON guest_events(guest_id);",
        "CREATE INDEX IF NOT EXISTS idx_guest_events_type ON guest_events(event_type);"
    ]

    requests_payload = [{"type": "execute", "stmt": {"sql": stmt}} for stmt in ddl_statements]
    try:
        execute_turso_pipeline(cfg["url"], cfg["token"], requests_payload)
        print("[+] Analytics Database initialized successfully.")
    except Exception as e:
        print(f"[-] Failed to initialize Analytics DB: {e}")

def record_guest_event(data):
    """
    Record a single visitor telemetry event into guest_events.
    """
    cfg = get_analytics_db_config()
    sql = """
    INSERT INTO guest_events (
        guest_id, session_id, event_type, page_url, page_title,
        search_query, download_file, api_endpoint, response_time_ms,
        status_code, error_flag, session_duration_sec, page_duration_sec,
        browser, os, device, ip_address, country, city, user_agent
    ) VALUES (
        ?, ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?, ?
    )
    """

    def parse_param(val, default=""):
        if val is None:
            return default
        return val

    args = [
        {"type": "text", "value": parse_param(data.get("guest_id"), "anonymous")},
        {"type": "text", "value": parse_param(data.get("session_id"), "")},
        {"type": "text", "value": parse_param(data.get("event_type"), "pageview")},
        {"type": "text", "value": parse_param(data.get("page_url"), "")},
        {"type": "text", "value": parse_param(data.get("page_title"), "")},
        {"type": "text", "value": parse_param(data.get("search_query"), "")},
        {"type": "text", "value": parse_param(data.get("download_file"), "")},
        {"type": "text", "value": parse_param(data.get("api_endpoint"), "")},
        {"type": "float", "value": float(data.get("response_time_ms") or 0)},
        {"type": "integer", "value": str(int(data.get("status_code") or 200))},
        {"type": "integer", "value": str(int(data.get("error_flag") or 0))},
        {"type": "float", "value": float(data.get("session_duration_sec") or 0)},
        {"type": "float", "value": float(data.get("page_duration_sec") or 0)},
        {"type": "text", "value": parse_param(data.get("browser"), "Unknown")},
        {"type": "text", "value": parse_param(data.get("os"), "Unknown")},
        {"type": "text", "value": parse_param(data.get("device"), "Desktop")},
        {"type": "text", "value": parse_param(data.get("ip_address"), "127.0.0.1")},
        {"type": "text", "value": parse_param(data.get("country"), "Unknown")},
        {"type": "text", "value": parse_param(data.get("city"), "Unknown")},
        {"type": "text", "value": parse_param(data.get("user_agent"), "")}
    ]

    requests_payload = [{"type": "execute", "stmt": {"sql": sql, "args": args}}]
    execute_turso_pipeline(cfg["url"], cfg["token"], requests_payload)
    return True

def get_guest_analytics_stats():
    """
    Computes and aggregates all 18 analytics metrics from Turso.
    """
    cfg = get_analytics_db_config()
    
    queries = {
        "active_users": "SELECT COUNT(DISTINCT session_id) as count FROM guest_events WHERE timestamp >= datetime('now', '-5 minutes');",
        "daily_users": "SELECT COUNT(DISTINCT guest_id) as count FROM guest_events WHERE timestamp >= datetime('now', '-24 hours');",
        "monthly_users": "SELECT COUNT(DISTINCT guest_id) as count FROM guest_events WHERE timestamp >= datetime('now', '-30 days');",
        "top_pages": "SELECT page_url, page_title, COUNT(*) as views, ROUND(AVG(page_duration_sec), 1) as avg_time FROM guest_events WHERE page_url IS NOT NULL AND page_url != '' GROUP BY page_url ORDER BY views DESC LIMIT 10;",
        "avg_session_time": "SELECT ROUND(AVG(max_dur), 1) as avg_dur FROM (SELECT session_id, MAX(session_duration_sec) as max_dur FROM guest_events GROUP BY session_id);",
        "avg_page_time": "SELECT ROUND(AVG(page_duration_sec), 1) as avg_dur FROM guest_events WHERE event_type='pageview' AND page_duration_sec > 0;",
        "browsers": "SELECT browser, COUNT(DISTINCT session_id) as count FROM guest_events WHERE browser IS NOT NULL AND browser != '' GROUP BY browser ORDER BY count DESC;",
        "os_list": "SELECT os, COUNT(DISTINCT session_id) as count FROM guest_events WHERE os IS NOT NULL AND os != '' GROUP BY os ORDER BY count DESC;",
        "devices": "SELECT device, COUNT(DISTINCT session_id) as count FROM guest_events WHERE device IS NOT NULL AND device != '' GROUP BY device ORDER BY count DESC;",
        "top_searches": "SELECT search_query, COUNT(*) as count FROM guest_events WHERE event_type='search' AND search_query IS NOT NULL AND search_query != '' GROUP BY search_query ORDER BY count DESC LIMIT 10;",
        "top_downloads": "SELECT download_file, COUNT(*) as count FROM guest_events WHERE event_type='download' AND download_file IS NOT NULL AND download_file != '' GROUP BY download_file ORDER BY count DESC LIMIT 10;",
        "error_rates": "SELECT COUNT(*) as total, SUM(CASE WHEN error_flag = 1 OR status_code >= 400 THEN 1 ELSE 0 END) as errors FROM guest_events;",
        "avg_response_time": "SELECT ROUND(AVG(response_time_ms), 1) as avg_ms FROM guest_events WHERE response_time_ms > 0;",
        "slow_apis": "SELECT api_endpoint, COUNT(*) as calls, ROUND(AVG(response_time_ms), 1) as avg_ms, ROUND(MAX(response_time_ms), 1) as max_ms FROM guest_events WHERE api_endpoint IS NOT NULL AND api_endpoint != '' GROUP BY api_endpoint ORDER BY avg_ms DESC LIMIT 10;",
        "heatmap": "SELECT strftime('%w', timestamp) as day_of_week, strftime('%H', timestamp) as hour_of_day, COUNT(*) as count FROM guest_events WHERE timestamp >= datetime('now', '-7 days') GROUP BY day_of_week, hour_of_day;",
        "countries": "SELECT country, COUNT(DISTINCT session_id) as count FROM guest_events WHERE country IS NOT NULL AND country != '' GROUP BY country ORDER BY count DESC LIMIT 10;",
        "cities": "SELECT city, country, COUNT(DISTINCT session_id) as count FROM guest_events WHERE city IS NOT NULL AND city != '' GROUP BY city ORDER BY count DESC LIMIT 10;",
        "rpm": "SELECT strftime('%H:%M', timestamp) as minute, COUNT(*) as count FROM guest_events WHERE timestamp >= datetime('now', '-60 minutes') GROUP BY minute ORDER BY minute ASC;"
    }

    keys = list(queries.keys())
    requests_payload = [{"type": "execute", "stmt": {"sql": queries[k]}} for k in keys]
    
    results = execute_turso_pipeline(cfg["url"], cfg["token"], requests_payload)

    def parse_rows(result_obj):
        if not result_obj:
            return []
        cols = [c["name"] for c in result_obj.get("cols", [])]
        rows = []
        for r in result_obj.get("rows", []):
            row_dict = {}
            for i, col in enumerate(cols):
                val_obj = r[i]
                if isinstance(val_obj, dict):
                    val = val_obj.get("value")
                else:
                    val = val_obj
                row_dict[col] = val
            rows.append(row_dict)
        return rows

    stats = {}
    for idx, key in enumerate(keys):
        stats[key] = parse_rows(results[idx])

    # Transform counters cleanly
    def get_single_val(res_rows, col_name, default=0):
        if res_rows and len(res_rows) > 0 and col_name in res_rows[0]:
            v = res_rows[0][col_name]
            if v is not None:
                try:
                    if isinstance(default, float):
                        return float(v)
                    return int(v)
                except Exception:
                    return v
            return default
        return default

    error_total = int(get_single_val(stats.get("error_rates"), "total", 0))
    error_count = int(get_single_val(stats.get("error_rates"), "errors", 0))
    error_percentage = round((float(error_count) / float(error_total) * 100.0), 2) if error_total > 0 else 0.0

    return {
        "active_users": int(get_single_val(stats.get("active_users"), "count", 0)),
        "daily_users": int(get_single_val(stats.get("daily_users"), "count", 0)),
        "monthly_users": int(get_single_val(stats.get("monthly_users"), "count", 0)),
        "most_visited_pages": stats.get("top_pages", []),
        "avg_session_time": float(get_single_val(stats.get("avg_session_time"), "avg_dur", 0.0)),
        "avg_page_time": float(get_single_val(stats.get("avg_page_time"), "avg_dur", 0.0)),
        "browser_usage": stats.get("browsers", []),
        "os_usage": stats.get("os_list", []),
        "device_usage": stats.get("devices", []),
        "top_searches": stats.get("top_searches", []),
        "top_downloads": stats.get("top_downloads", []),
        "error_rate": error_percentage,
        "total_requests": int(error_total),
        "total_errors": int(error_count),
        "avg_response_time": float(get_single_val(stats.get("avg_response_time"), "avg_ms", 0.0)),
        "slow_apis": stats.get("slow_apis", []),
        "heatmap": stats.get("heatmap", []),
        "traffic_by_country": stats.get("countries", []),
        "traffic_by_city": stats.get("cities", []),
        "requests_per_minute": stats.get("rpm", [])
    }

if __name__ == '__main__':
    print("Testing Analytics DB initialization...")
    init_analytics_db()
    print("Testing recording sample event...")
    record_guest_event({
        "guest_id": "test_guest_123",
        "session_id": "test_session_456",
        "event_type": "pageview",
        "page_url": "/index.html",
        "page_title": "Bhairava Anugraha",
        "browser": "Chrome",
        "os": "Windows",
        "device": "Desktop",
        "ip_address": "127.0.0.1",
        "country": "India",
        "city": "Bengaluru"
    })
    print("Testing stats computation...")
    s = get_guest_analytics_stats()
    print("Analytics Stats Summary:", json.dumps(s, indent=2))
