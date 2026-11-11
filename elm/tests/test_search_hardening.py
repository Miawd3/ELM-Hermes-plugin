"""Offline retrieval determinism, admission, and scope regression contracts."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
from elm_memory import cli

MOMENT = "2026-11-07T12:00:00+00:00"


def keys(rows):
    return [r["section_key"] for r in rows]


class SearchHardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="elm-search-hardening-")
        self.base = Path(self.temp.name)
        self.root = self.base / "store"
        self.root.mkdir()
        self.con = cli.connect(self.root)

    def tearDown(self):
        self.con.close()
        self.temp.cleanup()

    def write(self, path, body="amber cobalt", *, status="active", tags="allow", heading="Evidence"):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"Title: Record\nStatus: {status}\nTags: {tags}\nLast updated: 2026-11-06\n\n# {heading}\n\n{body}\n")
        return p

    def sync(self):
        self.assertEqual([], cli.sync(self.con, self.root)["errors"])

    def args(self, query="amber cobalt", *extra):
        return cli.build_parser().parse_args([
            "context", "--root", str(self.root), "--project", "sample",
            "--no-sync", "--no-trace", "--json", "--budget", "700", *extra, "--", query,
        ])

    def context(self, args=None):
        out = io.StringIO()
        with redirect_stdout(out):
            cli.command_context(args or self.args(), self.con, self.root)
        return json.loads(out.getvalue())

    def test_equal_bm25_ties_ignore_reversed_insertion_and_rebuild(self):
        paths = [f"20_projects/sample/{name}.md" for name in ("z", "b", "A", "a", "é")]
        files = [self.write(path) for path in reversed(paths)]
        orders = []
        packets = []
        for reverse in (False, True, False):
            with self.con:
                self.con.execute("DELETE FROM sections_fts")
                self.con.execute("DELETE FROM documents")
            with patch.object(cli, "iter_markdown", return_value=iter(sorted(files, reverse=reverse))):
                self.sync()
            args = self.args("amber cobalt", "--limit", "3")
            rows = cli.search_sections(self.con, args.task, args, limit=100, broad=False)
            self.assertEqual(1, len({r["score"] for r in rows}))
            self.assertEqual(sorted(keys(rows)), keys(rows))
            orders.append(keys(rows))
            packets.append(self.context(args)["packet"])
        self.assertTrue(all(order == orders[0] for order in orders))
        self.assertTrue(all(packet == packets[0] for packet in packets))

    def test_fresh_stores_with_opposite_file_creation_and_scan_order(self):
        results = []
        for i, reverse in enumerate((False, True)):
            root = self.base / f"fresh-{i}"
            root.mkdir()
            files = []
            for name in sorted(("a", "c", "b"), reverse=reverse):
                p = root / f"20_projects/sample/{name}.md"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("Title: Record\nStatus: active\n\n# Evidence\n\namber cobalt\n")
                files.append(p)
            con = cli.connect(root)
            try:
                with patch.object(cli, "iter_markdown", return_value=iter(files)):
                    self.assertEqual([], cli.sync(con, root)["errors"])
                args = self.args()
                out = io.StringIO()
                with redirect_stdout(out):
                    cli.command_context(args, con, root)
                packet = json.loads(out.getvalue())
                results.append((keys(cli.search_sections(con, args.task, args)), packet["packet"]))
            finally:
                con.close()
        self.assertEqual(results[0], results[1])

    def test_markdown_traversal_has_casefold_then_exact_path_order(self):
        names = ("z.md", "A.md", "a.md", "b.md", ".elm/ignore.md")
        for path in names:
            self.write(path)
        # Exercise real traversal ordering over enumerated path spellings without
        # requiring the underlying filesystem to store two case-distinct files.
        # The separate fresh-store test covers actual filesystem enumeration.
        with patch.object(type(self.root), "rglob", return_value=iter(self.root / name for name in names)):
            actual = [p.relative_to(self.root).as_posix() for p in cli.iter_markdown(self.root)]
        self.assertEqual(["A.md", "a.md", "b.md", "z.md"], actual)

    def test_nonempty_strict_lane_no_longer_suppresses_broad_evidence(self):
        self.write("20_projects/sample/strict.md", "amber cobalt irrelevant boilerplate")
        self.write("20_projects/sample/evidence.md", "amber verified answer is seventy three")
        self.sync()
        args = self.args("amber cobalt", "--budget", "1600")
        strict = cli.search_sections(self.con, args.task, args, broad=False)
        self.assertEqual(1, len(strict))
        result = self.context(args)
        self.assertIn("verified answer is seventy three", result["packet"])
        self.assertEqual(2, result["retrieval"]["candidate_count"])
        self.assertFalse(result["fallback_used"])

    def test_fusion_exact_rank_ties_and_cap(self):
        strict = [{"section_key": key, "text": "exact"} for key in ("b", "a", "d")]
        broad = [{"section_key": key, "text": "exact"} for key in ("a", "b", "c")]
        self.assertEqual(["b", "a"], keys(cli.fuse_search_lanes(strict, broad, 2)))
        self.assertEqual(["b", "a", "d", "c"], keys(cli.fuse_search_lanes(strict, broad, 4)))
        self.assertEqual([], cli.fuse_search_lanes([], [], 3))
        self.assertEqual(keys(strict), keys(cli.fuse_search_lanes(strict, [], 3)))

    def test_capped_lanes_are_uncapped_prefix_and_union_stays_bounded(self):
        for i in range(35):
            self.write(f"20_projects/sample/{i:02}.md", "amber cobalt" if i % 3 else "amber answer")
        self.sync()
        args = self.args("amber cobalt", "--limit", "7")
        for broad in (False, True):
            all_rows = cli.search_sections(self.con, args.task, args, broad=broad, limit=100)
            capped = cli.search_sections(self.con, args.task, args, broad=broad)
            self.assertEqual(keys(all_rows[:7]), keys(capped))
        result = self.context(args)
        self.assertEqual(7, result["retrieval"]["strict_count"])
        self.assertEqual(7, result["retrieval"]["broad_count"])
        self.assertEqual(7, result["retrieval"]["candidate_count"])

    def test_filters_preserved_in_each_lane_and_final_packet(self):
        self.write("20_projects/sample/allowed/good.md", "amber good evidence")
        self.write("20_projects/other/allowed/project.md", "amber projectsecret")
        self.write("10_shared/shared.md", "amber sharedsecret")
        self.write("20_projects/sample/allowed/99_archive/arch.md", "amber archivesecret")
        self.write("20_projects/sample/allowed/tag.md", "amber tagsecret", tags="deny")
        self.write("20_projects/sample/allowed/status.md", "amber statussecret", status="draft")
        self.write("20_projects/sample/elsewhere/path.md", "amber pathsecret")
        self.sync()
        args = self.args("amber cobalt", "--namespace", "project", "--tag", "allow",
                         "--status", "active", "--path-prefix", "20_projects/sample/allowed")
        for broad in (False, True):
            rows = cli.search_sections(self.con, args.task, args, broad=broad)
            self.assertTrue(all(r["path"].endswith("good.md") for r in rows))
        result = self.context(args)
        self.assertIn("good evidence", result["packet"])
        self.assertNotIn("secret", result["packet"])
        self.assertTrue(result["fallback_used"])

    def add_claim(self, path, status="accepted", valid_from="2020-01-01", valid_to=None):
        doc = self.con.execute("SELECT id FROM documents WHERE path=?", (path,)).fetchone()[0]
        row = dict(claim_id=f"claim_{doc}", document_id=doc, path=path, project="sample", subject="s",
                   predicate=f"p{doc}", object="o", status=status, authority="user_ratified",
                   valid_from=valid_from, valid_to=valid_to, recorded_at="2020-01-01", transitioned_at="2020-01-01",
                   proposal_id=f"proposal_{doc}", evidence_ids_json="[]", source_refs_json="[]",
                   sensitivity="normal", actor="test", content_hash="test")
        with self.con:
            self.con.execute(f"INSERT INTO claims ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", list(row.values()))

    def test_governance_time_history_and_supplements_fail_closed(self):
        paths = []
        for name in ("current", "future", "expired", "disputed"):
            path = f"20_projects/sample/{name}/active_context.md"
            self.write(path, f"amber {name} evidence", heading="Current focus")
            paths.append(path)
        self.sync()
        self.add_claim(paths[0])
        self.add_claim(paths[1], valid_from="9999-01-01")
        self.add_claim(paths[2], valid_to="2020-01-02")
        self.add_claim(paths[3], status="disputed")
        args = self.args("amber cobalt", "--budget", "1600")
        with patch.object(cli, "now_iso", return_value=MOMENT):
            result = self.context(args)
        self.assertIn("current evidence", result["packet"])
        for label in ("future", "expired", "disputed"):
            self.assertNotIn(f"{label} evidence", result["packet"])
        args.include_history = True
        rows, _ = cli.search_context_candidates(self.root, args.task, args, policy_moment=MOMENT)
        self.assertEqual(set(paths), {r["path"] for r in rows})

    def test_readonly_concurrent_connections_and_frozen_policy_time(self):
        self.write("20_projects/sample/good.md")
        self.sync()
        args = self.args()
        seen = []
        barrier = threading.Barrier(2)
        original = cli.search_sections
        def checked(con, query, args, **kwargs):
            self.assertEqual(1, con.execute("PRAGMA query_only").fetchone()[0])
            with self.assertRaises(sqlite3.OperationalError):
                con.execute("CREATE TABLE forbidden(x)")
            seen.append((threading.get_ident(), id(con), kwargs["policy_moment"]))
            barrier.wait(timeout=5)
            return original(con, query, args, **kwargs)
        before = hashlib.sha256(cli.db_path(self.root).read_bytes()).hexdigest()
        with patch.object(cli, "search_sections", side_effect=checked):
            rows, info = cli.search_context_candidates(self.root, args.task, args, policy_moment=MOMENT)
        self.assertEqual(2, len({s[0] for s in seen}))
        self.assertEqual(2, len({s[1] for s in seen}))
        self.assertEqual({MOMENT}, {s[2] for s in seen})
        self.assertEqual(before, hashlib.sha256(cli.db_path(self.root).read_bytes()).hexdigest())
        self.assertEqual(1, len(rows))

    def test_single_term_does_not_run_identical_lane_twice(self):
        self.write("20_projects/sample/good.md")
        self.sync()
        result = self.context(self.args("amber"))
        self.assertEqual(1, result["retrieval"]["lane_count"])
        self.assertFalse(result["fallback_used"])

    def test_lane_failure_refuses_partial_results(self):
        self.write("20_projects/sample/good.md")
        self.sync()
        original = cli.search_sections
        def fail_broad(*a, **kw):
            if kw.get("broad"):
                raise cli.ReadOnlyIndexError("synthetic lane failure")
            return original(*a, **kw)
        with patch.object(cli, "search_sections", side_effect=fail_broad):
            with self.assertRaisesRegex(cli.ReadOnlyIndexError, "lane failure"):
                self.context()

    def test_concurrent_index_commit_refuses_mixed_context(self):
        self.write("20_projects/sample/good.md")
        self.sync()
        original = cli.search_context_candidates
        def mutate(*a, **kw):
            rows = original(*a, **kw)
            other = cli.connect(self.root)
            try:
                with other:
                    other.execute("UPDATE documents SET status='draft'")
            finally:
                other.close()
            return rows
        with patch.object(cli, "search_context_candidates", side_effect=mutate):
            with self.assertRaisesRegex(cli.ReadOnlyIndexError, "Index changed"):
                self.context()

    def test_uncommitted_parent_connection_is_refused(self):
        self.con.execute("INSERT INTO elm_meta(key,value) VALUES('test','value')")
        with self.assertRaisesRegex(cli.ReadOnlyIndexError, "committed index"):
            self.context()
        self.con.rollback()

    def test_index_replacement_refuses_context(self):
        self.write("20_projects/sample/good.md")
        self.sync()
        with patch.object(cli, "_index_file_identity", side_effect=[(1, 2), (1, 3)]):
            with self.assertRaisesRegex(cli.ReadOnlyIndexError, "replaced"):
                self.context()

    def test_supplemental_equal_rank_ties_are_stable(self):
        paths = [f"20_projects/sample/{i}/active_context.md" for i in range(6)]
        files = [self.write(path, "current evidence", heading="Current focus") for path in paths]
        snapshots = []
        for reverse in (False, True):
            with self.con:
                self.con.execute("DELETE FROM sections_fts")
                self.con.execute("DELETE FROM documents")
            with patch.object(cli, "iter_markdown", return_value=iter(sorted(files, reverse=reverse))):
                self.sync()
            rows = cli._context_supplemental_sections(self.con, self.args(), "sample")
            self.assertEqual(4, len(rows))
            self.assertEqual(sorted(keys(rows)), keys(rows))
            snapshots.append(keys(rows))
        self.assertEqual(snapshots[0], snapshots[1])

    def test_ordinary_text_budget_remains_estimated_not_actual_tokenizer(self):
        body = "漢字仮名交じり文" * 40
        self.write("20_projects/sample/good.md", "amber " + body)
        self.sync()
        result = self.context(self.args("amber", "--budget", "700"))
        self.assertLessEqual(result["estimated_tokens"], 700)
        self.assertEqual((len(result["packet"]) + 3) // 4, result["estimated_tokens"])
        self.assertIn(body, result["packet"])

    def test_search_command_remains_strict_unless_broad_requested(self):
        self.write("20_projects/sample/good.md", "amber evidence")
        self.sync()
        for extra, count in (([], 0), (["--broad"], 1)):
            args = cli.build_parser().parse_args(["search", "--root", str(self.root), "--project", "sample",
                                                  "--no-sync", "--json", *extra, "amber cobalt"])
            out = io.StringIO()
            with redirect_stdout(out):
                cli.command_search(args, self.con, self.root)
            self.assertEqual(count, json.loads(out.getvalue())["count"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
