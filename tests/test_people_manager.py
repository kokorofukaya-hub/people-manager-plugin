"""Contract tests use fictional identities and isolated temporary user workspaces."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("people_manager", ROOT / "scripts/people_manager.py")
pm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pm)
NOW = "2026-10-02T03:00:00Z"


class HelperTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.repo = pm.Repository(self.workspace)
        self.options = {"mode": "on", "notion_user_id": "notion-test-user",
                        "member_page_url": "https://www.notion.so/member-test",
                        "notion_targets": {"activity": {"status": "ready", "unique": True,
                                                          "source_id": "test-source", "properties": {"type": "activity"}}},
                        "notification": {"mode": "off", "operator_slack_user_id": "UOPERATOR"}}
        pm.setup(self.repo, "UTEST01", "https://app.notion.com/p/test-space", self.options)

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self):
        return {str(p.relative_to(self.workspace)): p.read_bytes()
                for p in self.workspace.rglob("*") if p.is_file()}

    def config_mode(self, mode):
        config = self.repo.json("config.json")
        config["mode"] = mode
        pm.configure(self.repo, config)

    def capture(self, now=NOW, facts=True):
        config, state = self.repo.load()
        window = pm.window(config, state, "UTEST01", now)
        result = {"version": 1, "member_id": "UTEST01", "date": window["date"],
                  "start": window["start"], "cutoff": window["cutoff"], "sources": {}, "facts": []}
        for source in ("slack", "notion"):
            result["sources"][source] = {"status": "complete", "start": window["start"],
                                         "end": window["cutoff"], "pagination_complete": True,
                                         "evidence": ["fictional tool response pagination exhausted"],
                                         "scope": ["test-scope"], "retrieval": "exhaustive",
                                         "attribution_complete": True}
        if facts:
            result["facts"].append({"source": "slack", "source_id": "test-message-1",
                                     "url": "https://example.slack.com/archives/CFAKE/p123",
                                     "happened_at": "2026-09-30T03:01:00Z", "text": "Finished the sample exercise",
                                     "author_id": "UTEST01", "visibility": "public", "private": False,
                                     "generated": False})
        return result

    def commit(self):
        return pm.commit_activity(self.repo, self.capture(), NOW)

    def mirror_input(self, outcome="inspect", matches=None):
        config, state = self.repo.load()
        value = {"member_id": "UTEST01", "kind": "activity", "period": "2026-10-02", "outcome": outcome}
        key, record, expected = pm.expected_mirror(self.repo, config, state, value)
        value["search"] = {"status": "complete", "pagination_complete": True, "key": key,
                            "source_id": expected["source_id"], "evidence": ["all pages inspected"],
                            "matches": matches or []}
        return value

    def page(self):
        config, state = self.repo.load()
        value = self.mirror_input()
        _, _, expected = pm.expected_mirror(self.repo, config, state, value)
        return dict(expected, page_id="test-page-1", body_sha256=pm.digest(expected["body"]), fetch=self.fetch_proof())

    def fetch_proof(self):
        return {"status": "complete", "pagination_complete": True, "independent": True,
                "method": "connector-fetch", "fetched_at": pm.iso(pm.clock()),
                "truncated": False, "unknown_block_count": 0, "unknown_block_ids": [],
                "evidence": ["fictional independent connector fetch response"]}

    def test_two_input_setup_defaults_and_url_hosts(self):
        with tempfile.TemporaryDirectory() as other:
            repo = pm.Repository(other)
            result = pm.setup(repo, "UNEW01", "https://app.notion.com/p/test-page")
            self.assertEqual(result["mode"], "off")
            self.assertEqual(repo.json("config.json")["notification"]["mode"], "off")
            self.assertTrue(repo.exists("members/UNEW01/goals.md"))
            self.assertTrue(repo.exists(".gitignore"))
        for url in ("https://www.notion.so/space", "https://notion.so/space", "https://sample.notion.site/space"):
            self.assertEqual(pm.web_url(url, notion=True), url)

    def test_identity_survives_display_name_change_and_setup_preserves_state(self):
        self.commit()
        before = self.repo.read("state.json")
        pm.setup(self.repo, "UTEST01", "https://app.notion.com/p/test-space", {"display_name": "Renamed"})
        self.assertEqual(before, self.repo.read("state.json"))
        self.assertEqual(self.repo.json("config.json")["members"][0]["id"], "UTEST01")

    def test_configure_discovery_identity_and_notification_validation(self):
        config = self.repo.json("config.json")
        config["members"][0]["display_name"] = "Changed"
        self.assertEqual(pm.configure(self.repo, config)["status"], "configured")
        bad = copy.deepcopy(config)
        bad["members"][0]["id"] = "UOTHER"
        with self.assertRaises(pm.Invalid):
            pm.configure(self.repo, bad)
        for notification in ({"mode": "on", "operator_slack_user_id": "UTEST01", "destination_slack_user_id": "UTEST01"},
                             {"mode": "on", "operator_slack_user_id": "UOPERATOR", "destination_slack_user_id": "UOTHER"}):
            bad = copy.deepcopy(config)
            bad["notification"] = notification
            with self.assertRaises(pm.Invalid):
                pm.validate_config(bad)

    def test_ambiguous_notion_target_not_ready(self):
        config = self.repo.json("config.json")
        config["notion_targets"]["activity"]["unique"] = False
        with self.assertRaises(pm.Invalid):
            pm.validate_config(config)

    def test_window_first_three_days_and_cutoff_minute_rounding(self):
        config, state = self.repo.load()
        window = pm.window(config, state, "UTEST01", "2026-10-02T03:00:59Z")
        self.assertEqual(window["start"], "2026-09-29T03:00:00Z")
        self.assertEqual(window["cutoff"], NOW)

    def test_cursor_future_rejected_and_backlog_clamped(self):
        config, state = self.repo.load()
        state["members"]["UTEST01"]["cursor"] = "2026-10-03T03:00:00Z"
        with self.assertRaises(pm.Invalid):
            pm.window(config, state, "UTEST01", NOW)
        state["members"]["UTEST01"]["cursor"] = "2026-09-01T03:00:00Z"
        window = pm.window(config, state, "UTEST01", NOW)
        self.assertEqual(window["start"], "2026-09-25T03:00:00Z")
        self.assertTrue(window["backlog_truncated"])

    def test_committed_cursor_rollback_or_null_is_anomaly(self):
        self.commit()
        config, state = self.repo.load()
        for cursor in ("2026-09-01T03:00:00Z", None):
            state["members"]["UTEST01"]["cursor"] = cursor
            with self.assertRaises(pm.Invalid):
                pm.window(config, state, "UTEST01", "2026-10-03T03:00:00Z")

    def test_48_hour_gate_and_same_day_section(self):
        self.commit()
        config, state = self.repo.load()
        self.assertEqual(pm.window(config, state, "UTEST01", "2026-10-03T03:00:00Z")["status"], "cadence")
        self.assertEqual(pm.window(config, state, "UTEST01", "2026-10-04T03:00:00Z")["status"], "ready")
        before = self.snapshot()
        original = self.capture(facts=False)
        original["start"] = "2026-09-29T03:00:00Z"
        self.assertEqual(pm.commit_activity(self.repo, original, NOW)["status"], "already-written")
        self.assertEqual(before, self.snapshot())

    def test_missing_and_partial_sources_do_not_advance_or_save(self):
        for status in ("missing", "partial", "unsupported"):
            capture = self.capture()
            capture["sources"]["notion"]["status"] = status
            before = self.snapshot()
            result = pm.commit_activity(self.repo, capture, NOW)
            self.assertEqual(result["status"], "missing")
            self.assertEqual(result["missing_sources"], ["notion"])
            self.assertEqual(before, self.snapshot())
            self.assertIsNone(self.repo.json("state.json")["members"]["UTEST01"]["cursor"])

    def test_search_pagination_scope_and_attribution_not_complete(self):
        for key, value in (("retrieval", "search"), ("pagination_complete", False), ("evidence", []),
                           ("scope", []), ("attribution_complete", False), ("start", "2026-09-30T03:00:00Z")):
            capture = self.capture()
            capture["sources"]["notion"][key] = value
            self.assertEqual(pm.commit_activity(self.repo, capture, NOW)["status"], "missing")

    def test_zero_activity_only_after_full_coverage(self):
        result = pm.commit_activity(self.repo, self.capture(facts=False), NOW)
        self.assertEqual(result["facts_count"], 0)
        self.assertEqual(result["cursor"], NOW)
        self.assertIn("fully covered", self.repo.read(result["path"]))

    def test_fact_duplicate_and_month_boundary(self):
        capture = self.capture()
        capture["facts"].append(copy.deepcopy(capture["facts"][0]))
        result = pm.commit_activity(self.repo, capture, NOW)
        self.assertEqual(result["facts_count"], 1)
        current = self.repo.json("state.json")["members"]["UTEST01"]
        record = self.repo.json(current["days"]["2026-10-02"]["record_path"])
        self.assertEqual(record["facts"][0]["activity_date"], "2026-09-30")
        key = record["facts"][0]["key"]
        draft = {"member_id": "UTEST01", "kind": "monthly", "period": "2026-09", "body": "September public activity",
                 "evidence_fact_keys": [key]}
        self.assertEqual(pm.commit_document(self.repo, draft)["status"], "committed")
        draft["period"] = "2026-10"
        with self.assertRaises(pm.Invalid):
            pm.commit_document(self.repo, draft)

    def test_half_open_fact_range(self):
        for instant in ("2026-09-29T02:59:59Z", NOW):
            capture = self.capture()
            capture["facts"][0]["happened_at"] = instant
            with self.assertRaises(pm.Invalid):
                pm.commit_activity(self.repo, capture, NOW)

    def test_explicit_activity_date_and_source_identity_duplicate(self):
        capture = self.capture()
        capture["facts"][0]["activity_date"] = "2026-09-01"
        duplicate = copy.deepcopy(capture["facts"][0])
        duplicate["url"] += "?canonical=1"
        capture["facts"].append(duplicate)
        result = pm.commit_activity(self.repo, capture, NOW)
        self.assertEqual(result["facts_count"], 1)
        current = self.repo.json("state.json")["members"]["UTEST01"]
        record = self.repo.json(current["days"]["2026-10-02"]["record_path"])
        self.assertEqual(record["facts"][0]["activity_date"], "2026-09-01")

    def test_invalid_explicit_activity_date_rejected(self):
        capture = self.capture()
        capture["facts"][0]["activity_date"] = "2026-09-31"
        with self.assertRaises(pm.Invalid):
            pm.commit_activity(self.repo, capture, NOW)

    def test_collection_can_finish_after_planned_cutoff(self):
        self.assertEqual(pm.commit_activity(self.repo, self.capture(), "2026-10-02T03:05:00Z")["status"], "committed")

    def test_capture_future_cutoff_rejected(self):
        with self.assertRaises(pm.Invalid):
            pm.commit_activity(self.repo, self.capture(), "2026-10-02T02:59:00Z")

    def test_privacy_author_generated_and_dm_cannot_be_relabelled(self):
        for key, value in (("private", True), ("generated", True), ("author_id", "UOTHER"),
                           ("visibility", "dm"), ("visibility", "group_dm"), ("is_im", True), ("is_mpim", True)):
            capture = self.capture()
            capture["facts"][0][key] = value
            before = self.snapshot()
            with self.assertRaises(pm.Invalid):
                pm.commit_activity(self.repo, capture, NOW)
            self.assertEqual(before, self.snapshot())

    def test_unknown_notion_attribution_rejected(self):
        capture = self.capture()
        fact = capture["facts"][0]
        fact.update(source="notion", notion_user_id="unknown")
        with self.assertRaises(pm.Invalid):
            pm.commit_activity(self.repo, capture, NOW)

    def test_private_channel_requires_current_operator_membership(self):
        capture = self.capture()
        capture["operator_slack_user_id"] = "UOPERATOR"
        fact = capture["facts"][0]
        fact.update(visibility="private_channel", channel_id="CPRIVATE")
        self.assertEqual(pm.commit_activity(self.repo, capture, NOW)["status"], "missing")
        fact["membership"] = {"operator_id": "UOPERATOR", "channel_id": "CPRIVATE", "confirmed": True,
                              "checked_at": NOW, "evidence": "members response includes UOPERATOR"}
        self.assertEqual(pm.commit_activity(self.repo, capture, NOW)["status"], "committed")

    def test_unknown_channel_type_is_missing_not_zero(self):
        capture = self.capture()
        capture["facts"][0]["visibility"] = "unknown"
        config, state = self.repo.load()
        checked = pm.validate_capture(config, state, capture, NOW)
        self.assertEqual(checked["status"], "missing")
        self.assertEqual(checked["skipped"][0]["reason"], "channel-type-unknown")

    def test_modes_never_update_data(self):
        for mode in ("off", "observe", "dry-run"):
            self.config_mode(mode)
            capture = self.capture()
            before = self.snapshot()
            self.assertEqual(pm.commit_activity(self.repo, capture, NOW)["status"], mode)
            self.assertEqual(before, self.snapshot())

    def test_lock_and_atomic_failure_do_not_advance_cursor(self):
        with self.repo.lock():
            with self.assertRaises(pm.Invalid):
                self.commit()
        original_save = self.repo.save
        def fail_local(path, content):
            if path.endswith("2026-10.md"):
                raise OSError("simulated disk error")
            original_save(path, content)
        with patch.object(self.repo, "save", side_effect=fail_local):
            with self.assertRaises(OSError):
                self.commit()
        self.assertIsNone(self.repo.json("state.json")["members"]["UTEST01"]["cursor"])
        self.assertFalse(self.repo.exists(".lock"))

    def test_path_traversal_symlink_root_and_nested_escape(self):
        for path in ("../outside", "/tmp/outside"):
            with self.assertRaises(pm.Invalid):
                self.repo.save(path, "blocked")
        with self.assertRaises(pm.Invalid):
            pm.member_id("../../escape")
        with tempfile.TemporaryDirectory() as outside:
            (self.repo.root / "escape").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(pm.Invalid):
                self.repo.save("escape/test.md", "blocked")
            self.assertFalse((Path(outside) / "test.md").exists())
            with tempfile.TemporaryDirectory() as rootlink:
                (Path(rootlink) / ".people-manager").symlink_to(outside, target_is_directory=True)
                with self.assertRaises(pm.Invalid):
                    pm.Repository(rootlink)

    def test_interrupted_sidecar_or_state_commit_cannot_duplicate_on_next_day(self):
        for failed_target in ("sidecar", "state"):
            with tempfile.TemporaryDirectory() as workspace:
                repo = pm.Repository(workspace)
                pm.setup(repo, "UTEST01", "https://app.notion.com/p/test-space", self.options)
                original_save = repo.save_json
                def fail_stage(path, value):
                    if (failed_target == "sidecar" and "/records/" in path
                            or failed_target == "state" and path == "state.json"):
                        raise OSError("simulated transaction interruption")
                    original_save(path, value)
                with patch.object(repo, "save_json", side_effect=fail_stage):
                    with self.assertRaises(OSError):
                        pm.commit_activity(repo, self.capture(), NOW)
                self.assertIsNone(repo.json("state.json")["members"]["UTEST01"]["cursor"])
                config, state = repo.load()
                next_window = pm.window(config, state, "UTEST01", "2026-10-03T03:00:00Z")
                capture = self.capture()
                capture.update(date=next_window["date"], start=next_window["start"], cutoff=next_window["cutoff"])
                for source in capture["sources"].values():
                    source.update(start=next_window["start"], end=next_window["cutoff"])
                with self.assertRaises(pm.Invalid):
                    pm.commit_activity(repo, capture, "2026-10-03T03:00:00Z")
                self.assertEqual(repo.read("members/UTEST01/activity/2026-10.md").count("test-message-1"), 1)

    def test_plugin_package_and_cache_are_not_workspaces(self):
        with self.assertRaises(pm.Invalid):
            pm.Repository(ROOT)
        path = self.workspace / ".codex/plugins/cache/sample"
        path.mkdir(parents=True)
        with self.assertRaises(pm.Invalid):
            pm.Repository(path)

    def test_meeting_raw_transcript_private_cache_unknown_speaker(self):
        meeting = {"member_id": "UTEST01", "meeting_id": "../../meeting", "date": "2026-10-02",
                   "source_url": "https://example.com/meeting/test", "participants": ["UTEST01"],
                   "transcript": [{"speaker": None, "text": "Unattributed text"}], "summary": "Unverified summary"}
        result = pm.import_meeting(self.repo, meeting)
        self.assertEqual(result["speaker_status"], "unconfirmed")
        stored = self.repo.json(result["path"])
        self.assertTrue(stored["private"])
        self.assertFalse(stored["summary_is_evidence"])
        self.assertEqual(pm.import_meeting(self.repo, meeting)["status"], "already-written")
        meeting["meeting_id"] = "summary-only"
        meeting.pop("transcript")
        with self.assertRaises(pm.Invalid):
            pm.import_meeting(self.repo, meeting)

    def test_private_meeting_cannot_be_monthly_evidence(self):
        draft = {"member_id": "UTEST01", "kind": "monthly", "period": "2026-09", "body": "Private quote",
                 "evidence_fact_keys": [], "private_meeting_ids": ["private-id"]}
        with self.assertRaises(pm.Invalid):
            pm.commit_document(self.repo, draft)
        draft.pop("private_meeting_ids")
        draft["evidence_fact_keys"] = ["meeting-key"]
        with self.assertRaises(pm.Invalid):
            pm.commit_document(self.repo, draft)

    def test_monthly_holds_changed_markdown_or_sidecar(self):
        self.commit()
        current = self.repo.json("state.json")["members"]["UTEST01"]
        day = current["days"]["2026-10-02"]
        record = self.repo.json(day["record_path"])
        key = record["facts"][0]["key"]
        draft = {"member_id": "UTEST01", "kind": "monthly", "period": "2026-09", "body": "Sample report",
                 "evidence_fact_keys": [key]}
        original = self.repo.read(day["path"])
        self.repo.save(day["path"], original.replace("Finished the sample exercise", "Exercise incomplete: human correction"))
        with self.assertRaises(pm.Invalid):
            pm.commit_document(self.repo, draft)
        self.repo.save(day["path"], original)
        record["facts"][0]["activity_date"] = "2026-08-01"
        self.repo.save_json(day["record_path"], record)
        draft["period"] = "2026-08"
        with self.assertRaises(pm.Invalid):
            pm.commit_document(self.repo, draft)

    def test_monthly_mirror_uses_committed_fixed_key_and_body_hash(self):
        self.commit()
        result = pm.commit_document(self.repo, {"member_id": "UTEST01", "kind": "monthly", "period": "2026-09",
                                                "body": "No additional claims", "evidence_fact_keys": []})
        body = self.repo.read(result["path"])
        self.assertIn("<!-- people-manager:monthly:UTEST01:2026-09 -->", body)
        value = {"member_id": "UTEST01", "kind": "monthly", "period": "2026-09", "outcome": "inspect"}
        config, state = self.repo.load()
        key, _, expected = pm.expected_mirror(self.repo, config, state, value)
        self.assertEqual(expected["local_body_sha256"], pm.digest(body))
        value["search"] = {"status": "complete", "pagination_complete": True, "key": key,
                            "source_id": expected["source_id"], "evidence": ["complete search"], "matches": []}
        self.assertTrue(pm.record_mirror(self.repo, value)["can_create"])
        value.update(outcome="created", page_id="test-monthly-page",
                     readback=dict(expected, page_id="test-monthly-page", body_sha256=pm.digest(expected["body"]),
                                   fetch=self.fetch_proof()))
        self.assertEqual(pm.record_mirror(self.repo, value)["status"], "confirmed")

    def test_prep_create_only_without_mirror(self):
        draft = {"member_id": "UTEST01", "kind": "prep", "period": "2026-10-02", "body": "Private prep"}
        result = pm.commit_document(self.repo, draft)
        self.assertIsNone(result["mirror_key"])
        draft["body"] = "Changed"
        self.assertEqual(pm.commit_document(self.repo, draft)["status"], "already-written")
        self.assertEqual(self.repo.read(result["path"]), "Private prep")

    def test_mirror_create_claim_exact_readback_and_no_duplicate_create(self):
        self.commit()
        claim = pm.record_mirror(self.repo, self.mirror_input())
        self.assertTrue(claim["can_create"])
        self.assertFalse(pm.record_mirror(self.repo, self.mirror_input())["can_create"])
        value = self.mirror_input("created")
        value.update(page_id="test-page-1", readback=self.page())
        self.assertEqual(pm.record_mirror(self.repo, value)["status"], "confirmed")
        historical = self.mirror_input()
        historical.pop("search")
        self.assertEqual(pm.record_mirror(self.repo, historical)["status"], "confirmed")

    def test_unknown_create_cannot_retry_until_complete_reconciliation(self):
        self.commit()
        pm.record_mirror(self.repo, self.mirror_input())
        self.assertEqual(pm.record_mirror(self.repo, self.mirror_input("unknown"))["status"], "unknown")
        self.assertFalse(pm.record_mirror(self.repo, self.mirror_input())["can_create"])
        value = self.mirror_input("reconcile")
        value["search"]["pagination_complete"] = False
        self.assertEqual(pm.record_mirror(self.repo, value)["status"], "unknown")
        self.assertEqual(pm.record_mirror(self.repo, self.mirror_input("reconcile"))["status"], "pending")
        self.assertTrue(pm.record_mirror(self.repo, self.mirror_input())["can_create"])

    def test_failure_report_does_not_erase_unknown_or_creating_claim(self):
        self.commit()
        pm.record_mirror(self.repo, self.mirror_input())
        self.assertEqual(pm.record_mirror(self.repo, self.mirror_input("failed"))["status"], "creating")
        self.assertFalse(pm.record_mirror(self.repo, self.mirror_input())["can_create"])
        pm.record_mirror(self.repo, self.mirror_input("unknown"))
        self.assertEqual(pm.record_mirror(self.repo, self.mirror_input("failed"))["status"], "unknown")
        self.assertFalse(pm.record_mirror(self.repo, self.mirror_input())["can_create"])

    def test_mirror_duplicate_and_readback_mismatch_hold(self):
        self.commit()
        page = self.page()
        self.assertEqual(pm.record_mirror(self.repo, self.mirror_input(matches=[page, copy.deepcopy(page)]))["status"], "held")
        self.assertFalse(pm.record_mirror(self.repo, self.mirror_input())["can_create"])

    def test_created_readback_props_and_body_mismatch_hold(self):
        self.commit()
        pm.record_mirror(self.repo, self.mirror_input())
        value = self.mirror_input("created")
        value.update(page_id="test-page-1", readback=self.page())
        value["readback"]["body"] += " altered"
        self.assertEqual(pm.record_mirror(self.repo, value)["status"], "held")

    def test_mirror_failure_three_times_held_without_cursor_rollback(self):
        self.commit()
        for count in range(3):
            result = pm.record_mirror(self.repo, self.mirror_input("failed"))
            self.assertEqual(result["status"], "held" if count == 2 else "pending")
        self.assertEqual(self.repo.json("state.json")["members"]["UTEST01"]["cursor"], NOW)

    def test_search_existing_single_match_requires_readback(self):
        self.commit()
        page = self.page()
        value = self.mirror_input(matches=[page])
        value["readback"] = page
        self.assertEqual(pm.record_mirror(self.repo, value)["status"], "confirmed")

    def test_adapter_roundtrip_keeps_raw_hashes_separate(self):
        self.commit()
        claim = pm.record_mirror(self.repo, self.mirror_input())
        page = self.page()
        page["body"] = page["body"].replace("\n\n```text\n", "\n```plain text\n", 1).replace("\n", "\r\n")
        page["body_sha256"] = pm.digest(page["body"])
        value = self.mirror_input("created")
        value.update(page_id=page["page_id"], readback=page)
        self.assertEqual(pm.record_mirror(self.repo, value)["status"], "confirmed")
        record = self.repo.json("state.json")["mirrors"][claim["key"]]
        self.assertNotEqual(record["sent_body_sha256"], record["fetched_body_sha256"])
        self.assertEqual(record["canonical_sent_sha256"], record["canonical_fetched_sha256"])
        self.assertEqual(record["adapter"], "notion-plain-v1")
        self.assertTrue(record["fetch_evidence"]["independent"])

    def test_adapter_echo_is_not_independent_fetch(self):
        self.commit()
        pm.record_mirror(self.repo, self.mirror_input())
        page = self.page()
        page["fetch"].update(independent=False, method="local-echo")
        value = self.mirror_input("created")
        value.update(page_id=page["page_id"], readback=page)
        self.assertEqual(pm.record_mirror(self.repo, value)["status"], "held")

    def test_adapter_raw_fetch_incomplete_flags_override_complete_label(self):
        self.commit()
        config, state = self.repo.load()
        _, _, expected = pm.expected_mirror(self.repo, config, state, self.mirror_input())
        for name, value in (("truncated", True), ("unknown_block_count", 1), ("unknown_block_ids", ["unsupported-block"]),
                            ("status", "partial"), ("pagination_complete", False)):
            page = self.page()
            page["fetch"][name] = value
            self.assertFalse(pm.matches_expected(page, expected, require_fetch=True))
        pm.record_mirror(self.repo, self.mirror_input())
        page = self.page()
        page["fetch"]["truncated"] = True
        value = self.mirror_input("created")
        value.update(page_id=page["page_id"], readback=page)
        self.assertEqual(pm.record_mirror(self.repo, value)["status"], "held")

    def test_adapter_unknown_markup_and_human_addition_rejected(self):
        key = "people-manager:monthly:UTEST01:2026-09"
        body = pm.mirror_body(key, "# Report\n\nline  with spaces\n")
        parsed = pm.canonical_mirror(body)
        for invalid in (body + "Human correction\n", "<empty-block/>\n" + body,
                        body.replace("```text", "```python"), body.replace("Management ID:", "Management ID\\:")):
            with self.assertRaises(pm.Invalid):
                pm.canonical_mirror(invalid)
        for changed in (body.replace("line  with spaces", "line with spaces"), body.replace("# Report\n\n", "# Report\n")):
            self.assertNotEqual(pm.canonical_mirror(changed), parsed)
        for label in ("", "text", "plain text", "plaintext"):
            self.assertEqual(pm.canonical_mirror(body.replace("```text", "```" + label)), parsed)

    def test_adapter_visible_key_and_source_echo_hash_validated(self):
        self.commit()
        pm.record_mirror(self.repo, self.mirror_input())
        page = self.page()
        page["body"] = page["body"].replace("Management ID: people-manager:activity:UTEST01:2026-10-02",
                                              "Management ID: people-manager:activity:UTEST01:2026-10-01", 1)
        page["body_sha256"] = pm.digest(page["body"])
        value = self.mirror_input("created")
        value.update(page_id=page["page_id"], readback=page)
        self.assertEqual(pm.record_mirror(self.repo, value)["status"], "held")

    def test_adapter_refuses_existing_payload_fences(self):
        with self.assertRaises(pm.Unsupported):
            pm.mirror_body("people-manager:monthly:UTEST01:2026-09", "# Report\n```python\nx=1\n```\n")
        for body in ("# Report\n```text\nraw\n```", "# Report\n<table><tr></tr></table>"):
            with self.assertRaises(pm.Invalid):
                pm.commit_document(self.repo, {"member_id": "UTEST01", "kind": "monthly", "period": "2026-09",
                                                "body": body, "evidence_fact_keys": []})

    def test_configure_binding_change_holds_confirmed_and_keeps_original_page(self):
        self.commit()
        page = self.page()
        value = self.mirror_input(matches=[page])
        value["readback"] = page
        result = pm.record_mirror(self.repo, value)
        self.assertEqual(result["status"], "confirmed")
        config = self.repo.json("config.json")
        config["notion_targets"]["activity"]["source_id"] = "different-source"
        config["members"][0]["member_page_url"] = "https://www.notion.so/different-member"
        pm.configure(self.repo, config)
        stored = self.repo.json("state.json")["mirrors"][result["key"]]
        self.assertEqual(stored["status"], "held")
        self.assertEqual(stored["page_id"], "test-page-1")
        self.assertEqual(stored["binding"]["source_id"], "test-source")
        self.assertEqual(pm.status(self.repo)["mirrors"][0]["status"], "held")
        self.assertEqual(pm.record_mirror(self.repo, self.mirror_input())["status"], "held")

    def test_setup_binding_change_holds_unknown_without_recreate(self):
        self.commit()
        claim = pm.record_mirror(self.repo, self.mirror_input())
        pm.record_mirror(self.repo, self.mirror_input("unknown"))
        pm.setup(self.repo, "UTEST01", "https://app.notion.com/p/test-space",
                 {"notion_targets": {"activity": {"status": "ready", "unique": True,
                                                   "source_id": "new-source", "properties": {"type": "activity"}}}})
        record = self.repo.json("state.json")["mirrors"][claim["key"]]
        self.assertEqual(record["status"], "held")
        self.assertEqual(record["reason"], "binding-changed")
        self.assertFalse(pm.record_mirror(self.repo, self.mirror_input())["can_create"])

    def test_confirmed_latest_independent_readback_is_checked(self):
        self.commit()
        page = self.page()
        value = self.mirror_input(matches=[page])
        value["readback"] = page
        confirmed = pm.record_mirror(self.repo, value)
        self.assertEqual(confirmed["status"], "confirmed")
        page["body"] += "Human correction\n"
        page["body_sha256"] = pm.digest(page["body"])
        value = self.mirror_input(matches=[page])
        value["readback"] = page
        self.assertEqual(pm.record_mirror(self.repo, value)["status"], "held")
        self.assertEqual(self.repo.json("state.json")["mirrors"][confirmed["key"]]["page_id"], page["page_id"])

    def test_confirmed_complete_search_missing_page_is_held(self):
        self.commit()
        page = self.page()
        value = self.mirror_input(matches=[page])
        value["readback"] = page
        self.assertEqual(pm.record_mirror(self.repo, value)["status"], "confirmed")
        self.assertEqual(pm.record_mirror(self.repo, self.mirror_input())["status"], "held")

    def test_generated_mirror_is_not_collected(self):
        self.commit()
        page = self.page()
        value = self.mirror_input(matches=[page])
        value["readback"] = page
        pm.record_mirror(self.repo, value)
        capture = self.capture("2026-10-04T03:00:00Z", facts=False)
        capture["facts"] = [{"source": "notion", "source_id": "test-page-1", "url": "https://www.notion.so/test-page-1",
                              "happened_at": "2026-10-03T03:00:00Z", "text": "Generated mirror",
                              "notion_user_id": "notion-test-user", "private": False, "generated": False}]
        with self.assertRaises(pm.Invalid):
            pm.commit_activity(self.repo, capture, "2026-10-04T03:00:00Z")

    def test_cli_json_input_and_status_are_offline(self):
        payload = self.workspace / "capture.json"
        payload.write_text(json.dumps(self.capture()), encoding="utf-8")
        process = subprocess.run([sys.executable, str(ROOT / "scripts/people_manager.py"), "--workspace", str(self.workspace),
                                  "commit-activity", "--input", str(payload), "--now", NOW], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(json.loads(process.stdout)["status"], "committed")


class ManifestTest(unittest.TestCase):
    def test_portable_and_host_manifests(self):
        manifest = json.loads((ROOT / "plugin.json").read_text())
        self.assertEqual(manifest["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        allowed = {"$schema", "name", "version", "description", "author", "homepage", "repository", "license", "keywords", "extensions"}
        self.assertLessEqual(set(manifest), allowed)
        self.assertRegex(manifest["name"], r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
        self.assertEqual(manifest["version"], "0.1.0")
        for field in ("$schema", "name", "version", "description", "repository"):
            self.assertIsInstance(manifest[field], str)
        self.assertTrue(all(isinstance(word, str) for word in manifest["keywords"]))
        claude = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        self.assertEqual(claude["name"], manifest["name"])
        codex_marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
        claude_marketplace = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(codex_marketplace["name"], "people-manager-plugins")
        self.assertEqual(codex_marketplace["plugins"][0]["source"], {"source": "local", "path": "./"})
        self.assertEqual(claude_marketplace["plugins"][0]["source"], "./")
        self.assertEqual(codex_marketplace["plugins"][0]["name"], claude["name"])
        self.assertEqual(claude_marketplace["plugins"][0]["name"], claude["name"])
        self.assertTrue((ROOT / "scripts/people_manager.py").is_file())


if __name__ == "__main__":
    unittest.main()
