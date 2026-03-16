import threading
import time
import os
import csv
import webbrowser
import subprocess
import sys
try:
    import msvcrt
except ImportError:
    msvcrt = None
from collections import deque
from flask import Flask, request, jsonify
from flask_cors import CORS

from rich.live import Live
from rich.table import Table
from rich.console import Console

app = Flask(__name__)
# Enable CORS so the browser deployed on Cloudflare can hit this endpoint
CORS(app, resources={r"/*": {
    "origins": "*",
    "allow_headers": ["Content-Type", "Content-Encoding", "Accept"]
}})

# Store recent events
events = deque(maxlen=2000)
replayer_proc = None

# Runtime context
IN_DOCKER     = os.environ.get('IN_DOCKER', '').lower() in ('1', 'true', 'yes')
RECREATOR_URL = os.environ.get('RECREATOR_URL', 'http://localhost:5000')
CSV_DIR       = os.environ.get('CSV_DIR', os.path.dirname(os.path.abspath(__file__)))

# Cross-platform command input (stdin readline thread feeds this)
cmd_queue      = deque()
cmd_status     = ""    # last command result
cmd_status_time = 0.0  # timestamp when cmd_status was last set

@app.route('/track', methods=['POST', 'OPTIONS'])
def track():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    data = None
    raw_bytes = request.get_data()
    
    # Handle gzip compressed payloads
    if request.headers.get('Content-Encoding') == 'gzip' or request.headers.get('Content-Type') == 'application/gzip':
        import gzip
        try:
            raw_bytes = gzip.decompress(raw_bytes)
        except Exception as e:
            return jsonify({"status": "error", "error": "failed to decompress"}), 400

    import json
    try:
        data = json.loads(raw_bytes)
    except json.JSONDecodeError:
        # Fallback to treating it as terminal message
        text = raw_bytes.decode('utf-8', errors='replace')
        if text.strip():
            data = {
                "type": "terminal_msg",
                "data": text,
                "timestamp": int(time.time() * 1000)
            }

    if data:
        def process_event(ev):
            events.appendleft(ev)
            ev_type = ev.get('type')
            if ev_type == 'mousemove':
                f = _csv_path('mouse_events.csv')
                file_exists = os.path.isfile(f)
                with open(f, 'a', newline='', encoding='utf-8') as fh:
                    writer = csv.writer(fh)
                    if not file_exists:
                        writer.writerow(['timestamp', 'x', 'y', 'target'])
                    writer.writerow([ev.get('timestamp'), ev.get('x'), ev.get('y'), ev.get('target')])
            elif ev_type == 'keydown':
                f = _csv_path('keystrokes.csv')
                file_exists = os.path.isfile(f)
                with open(f, 'a', newline='', encoding='utf-8') as fh:
                    writer = csv.writer(fh)
                    if not file_exists:
                        writer.writerow(['timestamp', 'key', 'target'])
                    writer.writerow([ev.get('timestamp'), ev.get('key'), ev.get('target')])
            elif ev_type == 'scroll':
                f = _csv_path('scroll_events.csv')
                file_exists = os.path.isfile(f)
                with open(f, 'a', newline='', encoding='utf-8') as fh:
                    writer = csv.writer(fh)
                    if not file_exists:
                        writer.writerow(['timestamp', 'y'])
                    writer.writerow([ev.get('timestamp'), ev.get('y')])

        if isinstance(data, list):
            # Batch of events
            for ev in data:
                process_event(ev)
        else:
            process_event(data)

    return jsonify({"status": "ok"})

def _csv_path(name):
    return os.path.join(CSV_DIR, name)

def run_flask():
    import logging
    # Suppress default flask request logging to not mess up the TUI
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    # Run server on port 8000 as expected by Tailscale funnel
    app.run(host='0.0.0.0', port=8000, debug=False, use_reloader=False)

from rich.layout import Layout
from rich.panel import Panel
from rich.align import Align
from rich.rule import Rule

def _csv_row_count(name):
    """Return number of data rows in a CSV (minus header)."""
    try:
        with open(_csv_path(name), 'r') as f:
            return max(0, sum(1 for _ in f) - 1)
    except:
        return 0

def _file_kb(name):
    try:
        return f"{os.path.getsize(_csv_path(name)) / 1024:.1f} KB"
    except:
        return "—"

def _load_csv_events():
    """Read past events from disk into the live deque at startup.
    Only loads types we track (mousemove, keydown, scroll, click).
    Does NOT conflict with [c] clear (clears deque only) or [r] reset (deletes files + deque)."""
    type_map = {
        'mouse_events.csv':  'mousemove',
        'keystrokes.csv':    'keydown',
        'scroll_events.csv': 'scroll',
    }
    loaded = 0
    for fname, ev_type in type_map.items():
        path = _csv_path(fname)
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ev = {'type': ev_type}
                    try:
                        ev['timestamp'] = float(row.get('timestamp', 0))
                    except ValueError:
                        continue
                    if ev_type == 'mousemove':
                        ev.update({'x': row.get('x'), 'y': row.get('y'), 'target': row.get('target')})
                    elif ev_type == 'keydown':
                        ev.update({'key': row.get('key'), 'target': row.get('target')})
                    elif ev_type == 'scroll':
                        ev.update({'y': row.get('y')})
                    events.appendleft(ev)
                    loaded += 1
        except Exception:
            pass
    return loaded

def generate_dashboard():
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="cmdbar", size=3),
    )
    layout["body"].split_row(
        Layout(name="stats", size=38),
        Layout(name="main_events"),
        Layout(name="mouse_stream", size=34)
    )

    # ── Header ──────────────────────────────────────────────────────────────
    all_events = list(events)
    clicks    = sum(1 for e in all_events if e.get('type') == 'click')
    keys      = sum(1 for e in all_events if e.get('type') == 'keydown')
    scrolls   = sum(1 for e in all_events if e.get('type') == 'scroll')
    moves     = sum(1 for e in all_events if e.get('type') == 'mousemove')

    header_text = (
        f"[bold white]Activity Monitor[/bold white]  "
        f"[grey50]|[/grey50]  "
        f"[green]port 8000  receiving[/green]  "
        f"[grey50]|[/grey50]  "
        f"[cyan]{time.strftime('%H:%M:%S')}[/cyan]"
    )
    layout["header"].update(Panel(Align.center(header_text), border_style="grey37"))

    # ── Command bar (replaces old statusbar + cmdstatus) ─────────────────────────
    # Left: available commands. Right: replayer status.
    # Centre: feedback (auto-clears to empty placeholder after 3 s)
    if IN_DOCKER:
        replayer_right = f"Replayer: [cyan]{RECREATOR_URL}[/cyan]"
    else:
        rp_status = "running" if (replayer_proc and replayer_proc.poll() is None) else "stopped"
        rp_color  = "green" if rp_status == "running" else "grey50"
        replayer_right = f"Replayer: [{rp_color}]{rp_status}[/{rp_color}]"

    # Auto-clear feedback after 3 s; show placeholder when empty
    if cmd_status and (time.time() - cmd_status_time) > 3:
        pass  # will read as empty below (not mutating global here)
    feedback_age = time.time() - cmd_status_time
    if cmd_status and feedback_age <= 3:
        fb_color = "red" if cmd_status.startswith("!") else "green"
        centre = f"[{fb_color}]{cmd_status}[/{fb_color}]"
    else:
        centre = "[grey50]r reset · c clear · s replay · q quit[/grey50]"

    cmds_left = "[grey62]commands:[/grey62]"
    cmdbar_text = f"{cmds_left}  {centre}  [grey50]|[/grey50]  {replayer_right}"
    layout["cmdbar"].update(Panel(Align.center(cmdbar_text), border_style="grey37"))

    # ── Stats Panel ──────────────────────────────────────────────────────────
    mouse_rows  = _csv_row_count('mouse_events.csv')
    key_rows    = _csv_row_count('keystrokes.csv')
    scroll_rows = _csv_row_count('scroll_events.csv')
    mouse_kb    = _file_kb('mouse_events.csv')
    key_kb      = _file_kb('keystrokes.csv')
    scroll_kb   = _file_kb('scroll_events.csv')

    st = Table(box=None, expand=True, show_header=False, padding=(0, 1))
    st.add_column("Label", style="grey62", no_wrap=True, width=14)
    st.add_column("Value", no_wrap=True)

    # ── Live counts  ────────────────────────────────────────────────────────
    st.add_row("[bold cyan]LIVE COUNTS[/bold cyan]", "")
    st.add_row(Rule(style="cyan"), "")
    st.add_row("", "")
    st.add_row("Clicks",     f"[bold green]{clicks:>6}[/bold green]")
    st.add_row("Keystrokes", f"[bold cyan]{keys:>6}[/bold cyan]")
    st.add_row("Scrolls",    f"[bold yellow]{scrolls:>6}[/bold yellow]")
    st.add_row("Mouse pts",  f"[bold white]{moves:>6}[/bold white]")
    st.add_row("", "")

    # ── CSV on disk  ────────────────────────────────────────────────────────
    st.add_row("[bold cyan]STORED DATA[/bold cyan]", "")
    st.add_row(Rule(style="cyan"), "")
    st.add_row("", "")
    for lbl, rows, size in [
        ("mouse",  mouse_rows,  mouse_kb),
        ("keys",   key_rows,    key_kb),
        ("scroll", scroll_rows, scroll_kb),
    ]:
        st.add_row(f"[cyan]{lbl}[/cyan]", f"[white]{rows:>5}[/white] [grey50]rows[/grey50]")
        st.add_row("",              f"[grey50]{size:>8}[/grey50]")
        st.add_row("", "")

    layout["stats"].update(Panel(st, title="[bold]Stats[/bold]", border_style="cyan", padding=(0, 1)))

    # ── Main Activity Log ────────────────────────────────────────────────────
    main_table = Table(box=None, expand=True, row_styles=["", "dim"])
    main_table.add_column("Time",    style="cyan",    no_wrap=True, width=9)
    main_table.add_column("Type",    style="magenta", width=10)
    main_table.add_column("Details", style="white")

    other_events = [e for e in all_events if e.get('type') not in ('mousemove', 'scroll')]
    for ev in other_events[:30]:
        ev_type = ev.get('type', '')
        if ev_type == 'click':
            details = f"x={ev.get('x','')} y={ev.get('y','')}  [{ev.get('target','') or ev.get('element','')}]"
        elif ev_type == 'keydown':
            details = f"\"{ev.get('key','')}\"  in {ev.get('target','')}"
        elif ev_type == 'pageview':
            details = ev.get('url', '')
        else:
            details = str(ev.get('data', ''))

        ts = ev.get('timestamp', '')
        if isinstance(ts, (int, float)):
            ts = time.strftime('%H:%M:%S', time.localtime(ts / 1000))
        main_table.add_row(str(ts), ev_type.upper(), details)

    # Add scroll events to main log too (last 5 are enough)
    scroll_events = [e for e in all_events if e.get('type') == 'scroll']
    for ev in scroll_events[:5]:
        ts = ev.get('timestamp', '')
        if isinstance(ts, (int, float)):
            ts = time.strftime('%H:%M:%S', time.localtime(ts / 1000))
        main_table.add_row(str(ts), "SCROLL", f"scrollY={ev.get('y','')}px")

    layout["main_events"].update(Panel(main_table, title="Activity", border_style="grey50"))

    # ── Mouse Stream ─────────────────────────────────────────────────────────
    mouse_table = Table(box=None, expand=True, row_styles=["", "dim"])
    mouse_table.add_column("Time",   style="cyan",  no_wrap=True, width=12)
    mouse_table.add_column("x",      style="green",  width=6)
    mouse_table.add_column("y",      style="yellow", width=6)
    mouse_table.add_column("Target", style="grey70")

    mouse_events = [e for e in all_events if e.get('type') == 'mousemove']
    for ev in mouse_events[:30]:
        ts = ev.get('timestamp', '')
        if isinstance(ts, (int, float)):
            ms = int(ts % 1000)
            ts = time.strftime('%H:%M:%S', time.localtime(ts / 1000)) + f".{ms:03d}"
        mouse_table.add_row(str(ts), str(ev.get('x','')), str(ev.get('y','')), str(ev.get('target','')))

    layout["mouse_stream"].update(Panel(mouse_table, title="Mouse Stream", border_style="grey37"))

    return layout


def _stdin_reader():
    """Background thread: reads stdin lines and queues them as commands.
    Works in both local terminal and `docker attach` sessions."""
    while True:
        try:
            line = sys.stdin.readline()
            if line:
                cmd_queue.append(line.strip().lower())
        except Exception:
            break


def _run_command(cmd, replayer_proc, replayer_log):
    """Execute a command string, return (replayer_proc, signal)."""
    global cmd_status, cmd_status_time
    def _set(msg):
        global cmd_status, cmd_status_time
        cmd_status = msg
        cmd_status_time = time.time()

    if cmd in ('r', 'reset'):
        for name in ('mouse_events.csv', 'keystrokes.csv', 'scroll_events.csv'):
            p = _csv_path(name)
            if os.path.exists(p): os.remove(p)
        events.clear()
        _set("CSVs reset and view cleared")
    elif cmd in ('c', 'clear'):
        events.clear()
        _set("View cleared")
    elif cmd in ('s', 'replay', 'replayer'):
        if IN_DOCKER:
            _set(f"Open in browser: {RECREATOR_URL}")
        else:
            if replayer_proc is None or replayer_proc.poll() is not None:
                recreator_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'recreator'
                )
                if replayer_log:
                    replayer_log.seek(0); replayer_log.truncate()
                env = os.environ.copy()
                import site
                env['PYTHONPATH'] = os.pathsep.join(
                    site.getusersitepackages() if hasattr(site, 'getusersitepackages') else []
                ) + os.pathsep + env.get('PYTHONPATH', '')
                replayer_proc = subprocess.Popen(
                    [sys.executable, 'app.py'],
                    cwd=recreator_dir,
                    stdout=replayer_log,
                    stderr=replayer_log,
                    env=env
                )
                time.sleep(1.5)
                _set("Replayer started")
            webbrowser.open(RECREATOR_URL)
    elif cmd in ('q', 'quit', 'exit'):
        return replayer_proc, 'QUIT'
    elif cmd:
        _set(f"! unknown: {cmd!r}  (r c s q)")
    return replayer_proc, None


if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Pre-populate from disk so the TUI is not blank on startup
    _load_csv_events()

    # Start stdin reader thread — works locally and via docker attach
    stdin_thread = threading.Thread(target=_stdin_reader, daemon=True)
    stdin_thread.start()

    console = Console()
    time.sleep(0.5)

    replayer_proc = None
    replayer_log  = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'replayer.log'), 'w') if not IN_DOCKER else None

    with Live(generate_dashboard(), refresh_per_second=4, console=console, screen=True) as live:
        try:
            quit_requested = False
            while not quit_requested:
                time.sleep(0.1)

                # Drain command queue (from stdin thread)
                while cmd_queue:
                    cmd = cmd_queue.popleft()
                    replayer_proc, signal = _run_command(cmd, replayer_proc, replayer_log)
                    if signal == 'QUIT':
                        quit_requested = True
                        break

                # Also accept single-key presses on Windows via msvcrt (no Enter needed)
                if msvcrt and msvcrt.kbhit():
                    key = msvcrt.getch().decode('utf-8', errors='ignore').lower()
                    replayer_proc, signal = _run_command(key, replayer_proc, replayer_log)
                    if signal == 'QUIT':
                        quit_requested = True

                live.update(generate_dashboard())
        except KeyboardInterrupt:
            pass
        finally:
            if replayer_proc and replayer_proc.poll() is None:
                replayer_proc.terminate()
            if replayer_log:
                replayer_log.close()
