#!/usr/bin/env python3
"""
dashboard/server.py – QA Chat Tester Dashboard
Run from project root:  python dashboard/server.py [port=8765]
"""
import http.server
import io
import json
import os
import queue
import sqlite3
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "logs.db"
CASES_PATH = ROOT / "cases.json"
HTML_PATH = Path(__file__).resolve().parent / "index.html"

# ── Global run state ──────────────────────────────────────────────────────────
import signal as _signal

_run_lock = threading.Lock()
_run_state = {
    "running": False,
    "pgid": None,       # process group id — used to kill entire tree
    "output": [],
    "returncode": None,
    "started_at": None,
}
_sse_clients: list[queue.Queue] = []
_sse_lock = threading.Lock()


def _kill_pgid(pgid: int):
    """Send SIGTERM then immediately SIGKILL to an entire process group."""
    for sig in (_signal.SIGTERM, _signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            break   # group already gone
        except Exception:
            pass


def _broadcast(line: str | None):
    with _sse_lock:
        dead = []
        for q in _sse_clients:
            try:
                q.put_nowait(line)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)


def _db():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# ── Minimal XLSX builder (stdlib only) ───────────────────────────────────────
def _build_xlsx(headers: list[str], rows: list[list]) -> bytes:
    """Return a valid .xlsx file as bytes using only zipfile + xml."""

    def _esc(v) -> str:
        if v is None:
            return ""
        return (
            str(v)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    # Shared strings table
    ss: list[str] = []
    ss_idx: dict[str, int] = {}

    def _si(val: str) -> int:
        if val not in ss_idx:
            ss_idx[val] = len(ss)
            ss.append(val)
        return ss_idx[val]

    # Build cell rows XML
    sheet_rows = []
    # header row (bold via style 1)
    hcells = "".join(
        f'<c r="{chr(65+i)}1" t="s" s="1"><v>{_si(h)}</v></c>'
        for i, h in enumerate(headers)
    )
    sheet_rows.append(f'<row r="1">{hcells}</row>')

    for ri, row in enumerate(rows, start=2):
        cells = []
        for ci, val in enumerate(row):
            col = chr(65 + ci)
            ref = f"{col}{ri}"
            if val is None or val == "":
                cells.append(f'<c r="{ref}"/>')
            else:
                # Store raw string in shared-strings table; _esc only at XML write time
                idx = _si(str(val))
                cells.append(f'<c r="{ref}" t="s"><v>{idx}</v></c>')
        sheet_rows.append(f'<row r="{ri}">{"".join(cells)}</row>')

    sheet_data = "\n".join(sheet_rows)
    # _esc applied once here when embedding into XML
    ss_items = "".join(f"<si><t xml:space=\"preserve\">{_esc(s)}</t></si>" for s in ss)

    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
            ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>"
            '<sheet name="Conversaciones" sheetId="1" r:id="rId1"/>'
            "</sheets></workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<sheetData>{sheet_data}</sheetData>"
            "</worksheet>"
        ),
        "xl/sharedStrings.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(ss)}" uniqueCount="{len(ss)}">'
            f"{ss_items}</sst>"
        ),
        "xl/styles.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<fonts><font/><font><b/></font></fonts>"
            "<fills><fill/><fill/></fills>"
            "<borders><border/></borders>"
            "<cellStyleXfs><xf/></cellStyleXfs>"
            "<cellXfs>"
            "<xf fontId=\"0\"/>"           # style 0 – normal
            "<xf fontId=\"1\"/>"           # style 1 – bold (headers)
            "</cellXfs>"
            "</styleSheet>"
        ),
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content.encode("utf-8"))
    return buf.getvalue()


# ── HTTP Handler ──────────────────────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):  # silence access log
        pass

    # ── helpers ──

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    # ── routing ──

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        routes = {
            "/":                         self._html,
            "/index.html":               self._html,
            "/api/stats":                self._stats,
            "/api/conversations":        self._list_conversations,
            "/api/analyses":             self._list_analyses,
            "/api/cases":                self._get_cases,
            "/api/run/status":           self._run_status,
            "/api/run/stream":           self._run_stream,
            "/api/export/conversations": self._export_conversations,
        }
        if path in routes:
            routes[path]()
        elif path.startswith("/api/conversations/"):
            self._get_conversation(path[len("/api/conversations/"):])
        else:
            self._send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path == "/api/db":
            self._clear_db()
        else:
            self._send_json({"error": "not found"}, 404)

    def do_PUT(self):
        path = urlparse(self.path).path
        if path == "/api/cases":
            self._put_cases()
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/run":
            self._start_run()
        elif path == "/api/run/stop":
            self._stop_run()
        else:
            self._send_json({"error": "not found"}, 404)

    # ── endpoint implementations ──

    def _html(self):
        body = HTML_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stats(self):
        conn = _db()
        s = conn.execute("SELECT COUNT(DISTINCT session_id) c FROM logs").fetchone()["c"]
        m = conn.execute("SELECT COUNT(*) c FROM logs").fetchone()["c"]
        i = conn.execute("SELECT COUNT(*) c FROM insights").fetchone()["c"]
        r = conn.execute(
            "SELECT COUNT(DISTINCT run_id) c FROM logs WHERE run_id IS NOT NULL"
        ).fetchone()["c"]
        conn.close()
        self._send_json({"sessions": s, "messages": m, "insights": i, "runs": r})

    def _list_conversations(self):
        conn = _db()
        rows = conn.execute("""
            SELECT
                l.session_id,
                l.run_id,
                l.scenario_group_id,
                l.scenario,
                l.user_id,
                COUNT(*) AS message_count,
                MIN(l.created_at) AS started_at,
                MAX(l.updated_at) AS last_message_at,
                i.complete AS insight_complete,
                i.analysis AS insight_summary,
                (SELECT campaigns FROM logs
                 WHERE session_id = l.session_id AND campaigns IS NOT NULL
                 LIMIT 1) AS campaigns
            FROM logs l
            LEFT JOIN (
                SELECT session_id, complete, SUBSTR(analysis,1,120) AS analysis
                FROM insights
                GROUP BY session_id
            ) i ON i.session_id = l.session_id
            GROUP BY l.session_id
            ORDER BY last_message_at DESC
        """).fetchall()
        conn.close()
        result = []
        for r in rows:
            row = dict(r)
            if row.get("campaigns"):
                try:
                    row["campaigns"] = json.loads(row["campaigns"])
                except Exception:
                    row["campaigns"] = []
            else:
                row["campaigns"] = []
            result.append(row)
        self._send_json(result)

    def _list_analyses(self):
        conn = _db()
        rows = conn.execute("""
            SELECT
                i.insight_id,
                i.session_id,
                i.run_id,
                i.analysis,
                i.complete,
                i.created_at,
                i.updated_at,
                (SELECT l.user_id           FROM logs l WHERE l.session_id = i.session_id LIMIT 1) AS user_id,
                (SELECT l.scenario_group_id  FROM logs l WHERE l.session_id = i.session_id LIMIT 1) AS scenario_group_id,
                (SELECT l.scenario           FROM logs l WHERE l.session_id = i.session_id LIMIT 1) AS scenario,
                (SELECT l.campaigns          FROM logs l WHERE l.session_id = i.session_id AND l.campaigns IS NOT NULL LIMIT 1) AS campaigns,
                (SELECT COUNT(*)             FROM logs l WHERE l.session_id = i.session_id) AS message_count
            FROM insights i
            ORDER BY i.created_at DESC
        """).fetchall()
        conn.close()
        result = []
        for r in rows:
            row = dict(r)
            if row.get("campaigns"):
                try:
                    row["campaigns"] = json.loads(row["campaigns"])
                except Exception:
                    row["campaigns"] = []
            else:
                row["campaigns"] = []
            result.append(row)
        self._send_json(result)

    def _get_conversation(self, session_id: str):
        conn = _db()
        msgs = conn.execute(
            "SELECT * FROM logs WHERE session_id=? ORDER BY created_at", (session_id,)
        ).fetchall()
        insight = conn.execute(
            "SELECT * FROM insights WHERE session_id=? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        conn.close()

        out = []
        for m in msgs:
            row = dict(m)
            for f in ("raw_response", "files", "images", "campaigns"):
                if row.get(f):
                    try:
                        row[f] = json.loads(row[f])
                    except Exception:
                        pass
            out.append(row)

        self._send_json({
            "messages": out,
            "insight": dict(insight) if insight else None,
        })

    def _export_conversations(self):
        conn = _db()
        rows = conn.execute("""
            SELECT
                l.session_id,
                l.run_id,
                l.user_id,
                l.scenario_group_id,
                l.scenario,
                l.message,
                l.response,
                l.campaigns,
                i.analysis,
                i.complete,
                l.created_at
            FROM logs l
            LEFT JOIN insights i ON i.run_id = l.run_id
            WHERE l.message IS NOT NULL
            ORDER BY l.run_id, l.created_at
        """).fetchall()
        conn.close()

        headers = [
            "session_id", "run_id", "user_id", "scenario_group_id", "scenario",
            "message", "response", "campaign", "analysis", "complete", "created_at",
        ]

        def _parse_campaigns(val) -> str:
            if not val:
                return ""
            try:
                camps = json.loads(val) if isinstance(val, str) else val
                if isinstance(camps, list) and camps:
                    return " | ".join(
                        c.get("campaign_name", c.get("campaign_id", str(c)))
                        for c in camps if isinstance(c, dict)
                    )
            except Exception:
                pass
            return ""

        data = []
        for r in rows:
            row = dict(r)
            data.append([
                row.get("session_id", ""),
                row.get("run_id", ""),
                row.get("user_id", ""),
                row.get("scenario_group_id", ""),
                row.get("scenario", ""),
                row.get("message", ""),
                row.get("response", ""),
                _parse_campaigns(row.get("campaigns")),
                row.get("analysis", ""),
                "SI" if row.get("complete") else "NO",
                row.get("created_at", ""),
            ])
        xlsx = _build_xlsx(headers, data)

        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Disposition", 'attachment; filename="conversaciones.xlsx"')
        self.send_header("Content-Length", str(len(xlsx)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(xlsx)

    def _clear_db(self):
        conn = _db()
        conn.execute("DELETE FROM logs")
        conn.execute("DELETE FROM insights")
        conn.commit()
        conn.close()
        self._send_json({"ok": True})

    def _get_cases(self):
        try:
            self._send_json({"content": CASES_PATH.read_text(encoding="utf-8")})
        except FileNotFoundError:
            self._send_json({"content": "[]"})

    def _put_cases(self):
        try:
            data = json.loads(self._body())
            content = data.get("content", "")
            json.loads(content)  # validate
            CASES_PATH.write_text(content, encoding="utf-8")
            self._send_json({"ok": True})
        except json.JSONDecodeError as e:
            self._send_json({"error": f"JSON inválido: {e}"}, 400)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _run_status(self):
        with _run_lock:
            # Verify the process group is still alive
            if _run_state["running"] and _run_state["pgid"]:
                try:
                    os.killpg(_run_state["pgid"], 0)
                except (ProcessLookupError, PermissionError):
                    _run_state["running"]    = False
                    _run_state["returncode"] = -1
                    _run_state["pgid"]       = None
                    _broadcast(None)

            self._send_json({
                "running":     _run_state["running"],
                "returncode":  _run_state["returncode"],
                "started_at":  _run_state["started_at"],
                "lines":       len(_run_state["output"]),
            })

    def _run_stream(self):
        q: queue.Queue = queue.Queue(maxsize=1000)
        with _sse_lock:
            _sse_clients.append(q)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # send backlog
        with _run_lock:
            backlog = list(_run_state["output"])
        for line in backlog:
            try:
                self.wfile.write(f"data: {json.dumps(line)}\n\n".encode())
                self.wfile.flush()
            except Exception:
                return

        try:
            while True:
                try:
                    line = q.get(timeout=25)
                    if line is None:
                        self.wfile.write(b"event: done\ndata: done\n\n")
                        self.wfile.flush()
                        break
                    self.wfile.write(f"data: {json.dumps(line)}\n\n".encode())
                    self.wfile.flush()
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except Exception:
            pass
        finally:
            with _sse_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)

    def _start_run(self):
        try:
            body = self._body()
            data = json.loads(body) if body else {}
        except Exception:
            data = {}

        batch_size  = int(data.get("batch_size", 20))
        max_workers = int(data.get("max_workers", 10))
        max_items   = int(data.get("max_items", 0))
        json_file   = data.get("json_file", "cases.json")

        with _run_lock:
            if _run_state["running"]:
                self._send_json({"error": "Ya hay una ejecución en curso"}, 409)
                return
            _run_state.update(
                running=True, pgid=None, output=[], returncode=None,
                started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )

        def _worker():
            cmd = [
                sys.executable,
                str(ROOT / "batch_runner.py"),
                f"json_file={json_file}",
                f"batch_size={batch_size}",
                f"max_workers={max_workers}",
                f"max_items={max_items}",
            ]
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, cwd=str(ROOT),
                    preexec_fn=os.setsid,   # own process group → killpg kills all children
                )
                pgid = os.getpgid(proc.pid)
                with _run_lock:
                    _run_state["pgid"] = pgid

                for raw in proc.stdout:
                    line = raw.rstrip()
                    with _run_lock:
                        # If we were stopped externally, drain and discard
                        if not _run_state["running"]:
                            break
                        _run_state["output"].append(line)
                    _broadcast(line)

                proc.wait()
                with _run_lock:
                    if _run_state["running"]:   # not already stopped by _stop_run
                        _run_state["running"]    = False
                        _run_state["returncode"] = proc.returncode
                        _run_state["pgid"]       = None
            except Exception as exc:
                with _run_lock:
                    _run_state["running"]    = False
                    _run_state["returncode"] = -1
                    _run_state["output"].append(f"ERROR: {exc}")
                _broadcast(f"ERROR: {exc}")
            finally:
                _broadcast(None)   # sentinel → SSE clients get "done" event

        threading.Thread(target=_worker, daemon=True).start()
        self._send_json({"ok": True})

    def _stop_run(self):
        with _run_lock:
            pgid    = _run_state.get("pgid")
            running = _run_state.get("running")

        if not running:
            self._send_json({"error": "No hay proceso activo"}, 400)
            return

        # Kill the entire process group (batch_runner + all main.py children)
        if pgid:
            _kill_pgid(pgid)

        with _run_lock:
            _run_state["running"]    = False
            _run_state["returncode"] = -1
            _run_state["pgid"]       = None

        _broadcast(None)   # notify SSE clients
        self._send_json({"ok": True})


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port_arg = next((a.split("=")[1] for a in sys.argv[1:] if a.startswith("port=")), None)
    port = int(port_arg) if port_arg else 8765

    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Dashboard corriendo en  http://localhost:{port}")
    print(f"DB:    {DB_PATH}")
    print(f"Cases: {CASES_PATH}")
    print("Ctrl+C para detener.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
