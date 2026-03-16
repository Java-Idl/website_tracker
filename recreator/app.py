import os
import csv
import urllib.request
import urllib.error
from flask import Flask, render_template, jsonify

app = Flask(__name__)

TARGET_URL = "https://projectbpeer.pages.dev/"
# Allow overriding via env var so Docker volumes work
CLIENT_DIR = os.environ.get(
    'CSV_DIR',
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'client')
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/proxy')
def proxy():
    try:
        req = urllib.request.Request(
            TARGET_URL,
            headers={
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/122.0.0.0 Safari/537.36'
                ),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            }
        )
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode('utf-8', errors='replace')
        # Inject <base> tag so styles/images load from the real site
        base_tag = f'<base href="{TARGET_URL}">'
        if '<head>' in html:
            html = html.replace('<head>', f'<head>{base_tag}')
        else:
            html = f'{base_tag}{html}'
        # Strip tracker script in all its forms
        for pat in ['<script src="tracker.js"></script>',
                    '<script src="tracker.min.js"></script>',
                    '<script src="/tracker.js"></script>']:
            html = html.replace(pat, '<!-- tracker removed -->')
        return html
    except Exception as e:
        return f"Error proxying site: {str(e)}", 500

@app.route('/api/events')
def get_events():
    events = []
    
    # Read mouse events
    mouse_csv = os.path.join(CLIENT_DIR, 'mouse_events.csv')
    if os.path.exists(mouse_csv):
        print(f"Reading mouse events from {mouse_csv}")
        with open(mouse_csv, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or row[0] == 'timestamp': continue # Skip header if present
                try:
                    events.append({
                        'type': 'mousemove',
                        'timestamp': float(row[0]),
                        'x': float(row[1]),
                        'y': float(row[2]),
                        'target': row[3] if len(row) > 3 else ''
                    })
                except (ValueError, IndexError):
                    continue

    # Read keystrokes
    key_csv = os.path.join(CLIENT_DIR, 'keystrokes.csv')
    if os.path.exists(key_csv):
        print(f"Reading keystrokes from {key_csv}")
        with open(key_csv, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or row[0] == 'timestamp': continue # Skip header
                try:
                    events.append({
                        'type': 'keydown',
                        'timestamp': float(row[0]),
                        'key': row[1],
                        'target': row[2] if len(row) > 2 else ''
                    })
                except (ValueError, IndexError):
                    continue

    # Read scroll events
    scroll_csv = os.path.join(CLIENT_DIR, 'scroll_events.csv')
    if os.path.exists(scroll_csv):
        print(f"Reading scroll from {scroll_csv}")
        with open(scroll_csv, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or row[0] == 'timestamp': continue
                try:
                    events.append({
                        'type': 'scroll',
                        'timestamp': float(row[0]),
                        'y': float(row[1])
                    })
                except (ValueError, IndexError):
                    continue

    # Sort sequentially by timestamp across all files
    events.sort(key=lambda x: x['timestamp'])
    print(f"Fetched {len(events)} total events.")
    
    return jsonify({"events": events})

if __name__ == '__main__':
    print("Starting session recreator on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
