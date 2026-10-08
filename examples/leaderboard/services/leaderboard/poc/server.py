#!/usr/bin/env python3
"""Leaderboard proof-of-concept (stdlib only) — compares two ranking backends.

  memory : ordered in-memory index with O(log n) rank lookup (proxy for Redis sorted sets, Option A)
  sqlite : indexed table, rank via COUNT(*) and OFFSET (naive PostgreSQL-only ranking, Option B v1)
  sqlite-keyset : keyset seeks + score-bucket counts (fair PostgreSQL-only ranking, Option B v2)

Endpoints
  GET  /boards/global/top?n=100
  GET  /boards/global/around/<player_id>?k=10
  POST /events   {"event_id", "player_id", "score_delta", "completed_at"}   (idempotent on event_id)
  GET  /health

Logs are JSON lines (level, msg, …) written to stdout and --log-file, ready for `devkit logs`.
"""
from __future__ import annotations

import argparse
import bisect
import json
import random
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

MAX_DELTA = 5_000  # assumption A2


class MemoryBoard:
    """Sorted list of keys (-score, reached_at, player). Rank = index + 1."""

    def __init__(self):
        self.keys: list[tuple[int, float, str]] = []
        self.by_player: dict[str, tuple[int, float, str]] = {}
        self.lock = threading.Lock()

    def load(self, rows):
        self.keys = sorted((-s, t, p) for p, s, t in rows)
        self.by_player = {k[2]: k for k in self.keys}

    def apply(self, player, delta, ts):
        with self.lock:
            old = self.by_player.get(player)
            score = delta
            if old:
                i = bisect.bisect_left(self.keys, old)
                del self.keys[i]
                score = -old[0] + delta
            new = (-score, ts, player)
            bisect.insort(self.keys, new)
            self.by_player[player] = new
            return score

    def top(self, n):
        with self.lock:
            return [(i + 1, k[2], -k[0]) for i, k in enumerate(self.keys[:n])]

    def around(self, player, k):
        with self.lock:
            key = self.by_player.get(player)
            if key is None:
                return None
            i = bisect.bisect_left(self.keys, key)
            lo = max(0, i - k)
            return [(j + 1, x[2], -x[0]) for j, x in enumerate(self.keys[lo:i + k + 1], start=lo)]


class SqliteBoard:
    def __init__(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.execute("CREATE TABLE scores(player TEXT PRIMARY KEY, score INTEGER, reached_at REAL)")
        self.db.execute("CREATE INDEX ix_rank ON scores(score DESC, reached_at ASC)")
        self.lock = threading.Lock()

    def load(self, rows):
        self.db.executemany("INSERT INTO scores VALUES (?,?,?)", rows)
        self.db.commit()

    def apply(self, player, delta, ts):
        with self.lock:
            self.db.execute("INSERT INTO scores VALUES (?,?,?) ON CONFLICT(player) DO UPDATE "
                            "SET score = score + excluded.score, reached_at = excluded.reached_at", (player, delta, ts))
            self.db.commit()
            return self.db.execute("SELECT score FROM scores WHERE player=?", (player,)).fetchone()[0]

    def top(self, n):
        with self.lock:
            rows = self.db.execute("SELECT player, score FROM scores ORDER BY score DESC, reached_at ASC LIMIT ?", (n,))
            return [(i + 1, p, s) for i, (p, s) in enumerate(rows)]

    def around(self, player, k):
        with self.lock:
            me = self.db.execute("SELECT score, reached_at FROM scores WHERE player=?", (player,)).fetchone()
            if not me:
                return None
            rank = self.db.execute("SELECT COUNT(*) FROM scores WHERE score > ? OR (score = ? AND reached_at < ?)",
                                   (me[0], me[0], me[1])).fetchone()[0] + 1
            lo = max(0, rank - 1 - k)
            rows = self.db.execute("SELECT player, score FROM scores ORDER BY score DESC, reached_at ASC "
                                   "LIMIT ? OFFSET ?", (2 * k + 1, lo))
            return [(lo + i + 1, p, s) for i, (p, s) in enumerate(rows)]


class KeysetBoard(SqliteBoard):
    """Fair Option B (challenger review): keyset seeks for neighbours + score-bucket counts for the rank number."""

    def __init__(self):
        super().__init__()
        self.db.execute("CREATE TABLE buckets(score INTEGER PRIMARY KEY, n INTEGER)")

    def load(self, rows):
        super().load(rows)
        self.db.execute("INSERT INTO buckets SELECT score, COUNT(*) FROM scores GROUP BY score")
        self.db.commit()

    def apply(self, player, delta, ts):
        with self.lock:
            old = self.db.execute("SELECT score FROM scores WHERE player=?", (player,)).fetchone()
            if old:
                self.db.execute("UPDATE buckets SET n = n - 1 WHERE score = ?", (old[0],))
            self.db.execute("INSERT INTO scores VALUES (?,?,?) ON CONFLICT(player) DO UPDATE "
                            "SET score = score + excluded.score, reached_at = excluded.reached_at", (player, delta, ts))
            new = self.db.execute("SELECT score FROM scores WHERE player=?", (player,)).fetchone()[0]
            self.db.execute("INSERT INTO buckets VALUES (?, 1) ON CONFLICT(score) DO UPDATE SET n = n + 1", (new,))
            self.db.commit()
            return new

    def around(self, player, k):
        with self.lock:
            me = self.db.execute("SELECT score, reached_at FROM scores WHERE player=?", (player,)).fetchone()
            if not me:
                return None
            s, t = me
            ahead = self.db.execute("SELECT COALESCE(SUM(n), 0) FROM buckets WHERE score > ?", (s,)).fetchone()[0]
            ahead += self.db.execute("SELECT COUNT(*) FROM scores WHERE score = ? AND reached_at < ?", (s, t)).fetchone()[0]
            rank = ahead + 1
            # Index-friendly keyset seeks: split the OR so each branch is a range on ix_rank (an OR forces a scan).
            above = self.db.execute(
                "SELECT player, score FROM (SELECT player, score, reached_at FROM scores WHERE score = ? AND reached_at < ? "
                "ORDER BY reached_at DESC LIMIT ?) UNION ALL SELECT player, score FROM (SELECT player, score, reached_at "
                "FROM scores WHERE score > ? ORDER BY score ASC, reached_at DESC LIMIT ?)", (s, t, k, s, k)).fetchall()[:k][::-1]
            below = self.db.execute(
                "SELECT player, score FROM (SELECT player, score, reached_at FROM scores WHERE score = ? AND reached_at > ? "
                "ORDER BY reached_at ASC LIMIT ?) UNION ALL SELECT player, score FROM (SELECT player, score, reached_at "
                "FROM scores WHERE score < ? ORDER BY score DESC, reached_at ASC LIMIT ?)", (s, t, k, s, k)).fetchall()[:k]
            rows = above + [(player, s)] + below
            first = rank - len(above)
            return [(first + i, p, sc) for i, (p, sc) in enumerate(rows)]


def make_handler(board, applied: set, log):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

        def do_GET(self):
            url = urlparse(self.path)
            q = parse_qs(url.query)
            t0 = time.perf_counter()
            try:
                if url.path == "/health":
                    return self._send(200, {"ok": True})
                if url.path == "/boards/global/top":
                    rows = board.top(int(q.get("n", ["100"])[0]))
                elif url.path.startswith("/boards/global/around/"):
                    rows = board.around(url.path.rsplit("/", 1)[1], int(q.get("k", ["10"])[0]))
                    if rows is None:
                        return self._send(404, {"error": "unranked"})
                else:
                    return self._send(404, {"error": "not found"})
                ms = (time.perf_counter() - t0) * 1000
                if ms > 50:
                    log("WARN", "slow read", path=url.path, duration_ms=round(ms, 1))
                self._send(200, {"entries": [{"rank": r, "player": p, "score": s} for r, p, s in rows]})
            except Exception as e:  # noqa: BLE001 — PoC: surface everything in the log
                log("ERROR", "read failed", path=url.path, error=repr(e))
                self._send(500, {"error": "internal"})

        def do_POST(self):
            if self.path != "/events":
                return self._send(404, {"error": "not found"})
            try:
                ev = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                if ev["event_id"] in applied:
                    log("INFO", "duplicate event ignored", event_id=ev["event_id"])
                    return self._send(200, {"applied": False, "reason": "duplicate"})
                if not 0 <= ev["score_delta"] <= MAX_DELTA:
                    log("WARN", "implausible score rejected", player=ev["player_id"], delta=ev["score_delta"])
                    return self._send(422, {"applied": False, "reason": "implausible"})
                score = board.apply(ev["player_id"], ev["score_delta"], time.time())
                applied.add(ev["event_id"])
                self._send(200, {"applied": True, "score": score})
            except (KeyError, ValueError) as e:
                log("ERROR", "bad event", error=repr(e))
                self._send(400, {"error": "bad event"})

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["memory", "sqlite", "sqlite-keyset"], default="memory")
    ap.add_argument("--players", type=int, default=200_000)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--log-file")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    logf = open(a.log_file, "a", encoding="utf-8") if a.log_file else None

    def log(level, msg, **fields):
        line = json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "level": level, "msg": msg,
                           "backend": a.backend, **fields})
        print(line, flush=True)
        if logf:
            logf.write(line + "\n")
            logf.flush()

    rnd = random.Random(a.seed)
    rows = [(f"p{i}", rnd.randint(0, 50_000), rnd.random() * 1e6) for i in range(a.players)]
    board = {"memory": MemoryBoard, "sqlite": SqliteBoard, "sqlite-keyset": KeysetBoard}[a.backend]()
    t0 = time.perf_counter()
    board.load(rows)
    log("INFO", "board loaded", players=a.players, load_s=round(time.perf_counter() - t0, 2))
    server = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(board, set(), log))
    log("INFO", "listening", port=a.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
