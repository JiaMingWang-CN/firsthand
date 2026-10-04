"""SQLite exchange between the browser orchestrator and the OASIS process."""

import json
from pathlib import Path
import sqlite3
from contextlib import contextmanager

from core.experience import ExperienceMemory, load_experience


class SimulationStore:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self, draft, schedule):
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE personas(persona_id TEXT PRIMARY KEY, persona_json TEXT NOT NULL, browse_slice INTEGER NOT NULL);
                CREATE TABLE experiences(persona_id TEXT PRIMARY KEY, slice_index INTEGER NOT NULL, directory TEXT NOT NULL, memory_json TEXT NOT NULL);
                CREATE TABLE reads(read_id INTEGER PRIMARY KEY, persona_id TEXT NOT NULL, slice_index INTEGER NOT NULL,
                    post_id INTEGER NOT NULL, before_experience INTEGER NOT NULL, post_json TEXT NOT NULL);
                CREATE TABLE disclosures(disclosure_id INTEGER PRIMARY KEY, persona_id TEXT NOT NULL, slice_index INTEGER NOT NULL,
                    shared_json TEXT NOT NULL, withheld_json TEXT NOT NULL, public_body TEXT NOT NULL);
                CREATE TABLE actions(action_id INTEGER PRIMARY KEY, persona_id TEXT NOT NULL, slice_index INTEGER NOT NULL,
                    experienced INTEGER NOT NULL, action TEXT NOT NULL, allowed_json TEXT NOT NULL, public_body TEXT NOT NULL,
                    target_post_id INTEGER, result_json TEXT NOT NULL);
                CREATE TABLE surveys(persona_id TEXT PRIMARY KEY, answer_json TEXT NOT NULL, flags_json TEXT NOT NULL);
                CREATE TABLE activity(persona_id TEXT NOT NULL, slice_index INTEGER NOT NULL, local_hour INTEGER NOT NULL,
                    probability REAL NOT NULL, draw REAL NOT NULL, active INTEGER NOT NULL, PRIMARY KEY(persona_id,slice_index));
                CREATE TABLE commands(command_id INTEGER PRIMARY KEY, kind TEXT NOT NULL, slice_index INTEGER NOT NULL,
                    logical_time TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued', result_json TEXT);
            """)
            slots = {row["persona_id"]: row["slice_index"] for row in schedule}
            db.executemany("INSERT INTO personas VALUES(?,?,?)", [(p.persona_id, p.model_dump_json(), slots[p.persona_id]) for p in draft.personas])

    def set_metadata(self, key, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO metadata VALUES(?,?)", (key, json.dumps(value, ensure_ascii=False)))

    def metadata(self, key):
        with self.connect() as db:
            row = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def publish_experience(self, persona_id, tick, directory):
        memory = load_experience(directory)
        result = json.loads((Path(directory) / "result.json").read_text(encoding="utf-8"))
        if memory.persona_id != persona_id or not result["passed"] or memory.assessment is None:
            raise ValueError("Only verified experience may enable social expression")
        with self.connect() as db:
            db.execute("INSERT INTO experiences VALUES(?,?,?,?)", (persona_id, tick, str(Path(directory).resolve()), memory.model_dump_json()))

    def experience(self, persona_id):
        with self.connect() as db:
            row = db.execute("SELECT memory_json FROM experiences WHERE persona_id=?", (persona_id,)).fetchone()
        return ExperienceMemory.model_validate_json(row[0]) if row else None

    def record_reads(self, pid, tick, posts, experienced):
        with self.connect() as db:
            db.executemany("INSERT INTO reads(persona_id,slice_index,post_id,before_experience,post_json) VALUES(?,?,?,?,?)",
                [(pid, tick, post["post_id"], int(not experienced), json.dumps(post, ensure_ascii=False)) for post in posts])

    def read_posts(self, pid):
        with self.connect() as db:
            rows = db.execute("SELECT post_json FROM reads WHERE persona_id=? ORDER BY read_id", (pid,)).fetchall()
        return {post["post_id"]: post for post in (json.loads(row[0]) for row in rows)}

    def expectations(self, pid):
        with self.connect() as db:
            rows = db.execute("SELECT post_id,post_json FROM reads WHERE persona_id=? AND before_experience=1 ORDER BY read_id", (pid,)).fetchall()
        seen = {}
        for row in rows:
            post = json.loads(row["post_json"])
            seen[row["post_id"]] = f"体验前我看到帖子 #{row['post_id']} 说：{post['content']}。这是他人表达，尚非我的亲身体验。"
        return list(seen.values())[-10:]

    def record_disclosure(self, pid, tick, plan, body):
        with self.connect() as db:
            db.execute("INSERT INTO disclosures(persona_id,slice_index,shared_json,withheld_json,public_body) VALUES(?,?,?,?,?)",
                (pid, tick, json.dumps(plan.shared), json.dumps([item.model_dump() for item in plan.withheld], ensure_ascii=False), body))

    def record_action(self, pid, tick, experienced, action, allowed, body, target, result):
        with self.connect() as db:
            db.execute("INSERT INTO actions(persona_id,slice_index,experienced,action,allowed_json,public_body,target_post_id,result_json) VALUES(?,?,?,?,?,?,?,?)",
                (pid, tick, int(experienced), action, json.dumps(sorted(allowed)), body, target, json.dumps(result, ensure_ascii=False)))

    def survey(self, pid, answer, flags):
        with self.connect() as db:
            db.execute("INSERT INTO surveys VALUES(?,?,?)", (pid, answer.model_dump_json(), json.dumps(flags)))

    def enqueue(self, kind, tick, logical_time):
        with self.connect() as db:
            cursor = db.execute("INSERT INTO commands(kind,slice_index,logical_time) VALUES(?,?,?)", (kind, tick, logical_time))
            return cursor.lastrowid

    def next_command(self):
        with self.connect() as db:
            row = db.execute("SELECT * FROM commands WHERE state='queued' ORDER BY command_id LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE commands SET state='running' WHERE command_id=?", (row["command_id"],))
        return dict(row) if row else None

    def command_result(self, command_id):
        with self.connect() as db:
            row = db.execute("SELECT state,result_json FROM commands WHERE command_id=?", (command_id,)).fetchone()
        return dict(row)

    def complete_command(self, command_id, result, failed=False):
        with self.connect() as db:
            db.execute("UPDATE commands SET state=?,result_json=? WHERE command_id=?",
                       ("failed" if failed else "done", json.dumps(result, ensure_ascii=False), command_id))
