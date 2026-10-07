#!/usr/bin/env python3
"""Offline, stdlib-only persistence helper. Connectors are operated by the skills."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

VERSION = 1
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
ID_RE = re.compile(r"[UW][A-Z0-9]{2,63}\Z")
MODES = {"off", "observe", "dry-run", "on"}
STATUSES = {"complete", "partial", "missing", "unsupported"}
ADAPTER = "notion-plain-v1"


class Invalid(ValueError):
    pass


class Unsupported(Invalid):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def digest(value):
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def instant(value):
    require(isinstance(value, str), "timestamp must be an ISO string")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Invalid("invalid timestamp") from exc
    require(result.tzinfo is not None and result.utcoffset() is not None,
            "timestamp needs an explicit UTC offset")
    return result.astimezone(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def clock(value=None):
    return instant(value) if value else datetime.now(timezone.utc)


def zone(name):
    # The default needs no platform IANA database (which is absent on some Windows installs).
    return timezone(timedelta(hours=9), "Asia/Tokyo") if name == "Asia/Tokyo" else ZoneInfo(name)


def member_id(value):
    require(isinstance(value, str) and bool(ID_RE.fullmatch(value)), "invalid Slack user ID")
    return value


def period(value, monthly=False):
    require(isinstance(value, str), "period must be a string")
    try:
        result = date.fromisoformat(value + "-01" if monthly else value)
    except ValueError as exc:
        raise Invalid("invalid calendar period") from exc
    require(value == result.strftime("%Y-%m" if monthly else "%Y-%m-%d"),
            "invalid calendar period")
    return value


def web_url(value, notion=False):
    require(isinstance(value, str), "source URL is required")
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    require(parsed.scheme == "https" and host and not parsed.username and not parsed.password,
            "source URL must be HTTPS without credentials")
    if notion:
        require(host in {"notion.so", "www.notion.so", "notion.site", "app.notion.com"}
                or host.endswith(".notion.site"), "unsupported Notion URL")
    return value


def read_input(path):
    target = Path(path)
    require(target.name != ".env" and not target.name.startswith(".env."),
            "secret files are not accepted")
    try:
        result = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Invalid("unable to read JSON input") from exc
    require(isinstance(result, dict), "JSON input must be an object")
    return result


class Repository:
    def __init__(self, workspace):
        self.workspace = Path(workspace).expanduser().resolve()
        require(self.workspace.is_dir(), "workspace must be an existing directory")
        require(not self.workspace.is_relative_to(PLUGIN_ROOT),
                "use the user workspace, not the plugin package or cache")
        parts = self.workspace.parts
        require(not any(parts[i:i + 3] in ((".codex", "plugins", "cache"),
                                           (".claude", "plugins", "cache"))
                        for i in range(len(parts))), "plugin cache cannot store user data")
        self.root = self.workspace / ".people-manager"
        require(not self.root.is_symlink(), "data root cannot be a symlink")

    def safe(self, relative):
        rel = Path(relative)
        require(not rel.is_absolute() and ".." not in rel.parts, "unsafe relative path")
        target = self.root / rel
        current = self.root
        require(not current.is_symlink(), "data root cannot be a symlink")
        for part in rel.parts:
            current = current / part
            require(not current.is_symlink(), "symlinks in data paths are forbidden")
        require(target.resolve().is_relative_to(self.root.resolve()), "data path escapes root")
        return target

    def exists(self, relative):
        return self.safe(relative).exists()

    def read(self, relative):
        try:
            return self.safe(relative).read_text(encoding="utf-8")
        except OSError as exc:
            raise Invalid("required local file is missing or unreadable") from exc

    def json(self, relative):
        try:
            result = json.loads(self.read(relative))
        except ValueError as exc:
            raise Invalid("invalid local JSON") from exc
        require(isinstance(result, dict), "local JSON must be an object")
        return result

    def save(self, relative, content):
        target = self.safe(relative)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.safe(relative)
        fd, temporary = tempfile.mkstemp(prefix=".atomic-", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            self.safe(relative)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def save_json(self, relative, value):
        self.save(relative, encoded(value))

    @contextmanager
    def lock(self, create=False):
        if create:
            self.root.mkdir(mode=0o700, exist_ok=True)
        require(self.root.is_dir(), "run setup first")
        target = self.safe(".lock")
        try:
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise Invalid("workspace is locked; inspect the existing lock before retrying") from exc
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(str(os.getpid()) + "\n")
            yield
        finally:
            self.safe(".lock").unlink()

    def load(self):
        config = self.json("config.json")
        validate_config(config)
        state = self.json("state.json")
        require(state.get("version") == VERSION and isinstance(state.get("members"), dict)
                and isinstance(state.get("mirrors"), dict), "unsupported or invalid state")
        return config, state


def validate_config(config):
    require(config.get("version") == VERSION, "unsupported config version")
    require(config.get("mode") in MODES, "invalid mode")
    try:
        zone(config.get("timezone", ""))
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise Invalid("unknown timezone") from exc
    web_url(config.get("notion_url"), notion=True)
    members = config.get("members")
    require(isinstance(members, list) and members, "members must be a non-empty list")
    ids = []
    for member in members:
        require(isinstance(member, dict), "invalid member object")
        identity = member_id(member.get("slack_user_id"))
        require(member.get("id") == identity, "member ID must equal the Slack user ID")
        ids.append(identity)
        require(isinstance(member.get("display_name"), str), "display_name must be a string")
        require(isinstance(member.get("active"), bool), "active must be boolean")
        require(isinstance(member.get("meeting_roots", []), list), "meeting_roots must be a list")
        if member.get("notion_user_id") is not None:
            require(isinstance(member["notion_user_id"], str) and member["notion_user_id"],
                    "invalid Notion user ID")
        if member.get("member_page_url"):
            web_url(member["member_page_url"], notion=True)
    require(len(ids) == len(set(ids)), "duplicate member identity")
    targets = config.get("notion_targets")
    require(isinstance(targets, dict), "notion_targets must be an object")
    for target in targets.values():
        require(isinstance(target, dict) and target.get("status") in {"ready", "missing"},
                "invalid Notion discovery target")
        if target["status"] == "ready":
            require(target.get("unique") is True and target.get("source_id")
                    and isinstance(target.get("properties"), dict),
                    "ready Notion target needs unique discovery and mapped properties")
    notify = config.get("notification")
    require(isinstance(notify, dict) and notify.get("mode") in {"off", "on"},
            "invalid notification setting")
    operator = notify.get("operator_slack_user_id")
    if operator:
        member_id(operator)
        require(operator not in ids, "operator notification destination cannot be a managed member")
    if notify["mode"] == "on":
        require(operator and notify.get("destination_slack_user_id") == operator,
                "notification must target the explicit operator only")
    return config


def setup(repo, slack_user_id, notion_url, options=None):
    identity = member_id(slack_user_id)
    web_url(notion_url, notion=True)
    options = options or {}
    with repo.lock(create=True):
        if repo.exists("config.json"):
            config, state = repo.load()
            require(config["notion_url"] == notion_url, "Notion URL change requires configure")
        else:
            config = {"version": VERSION, "timezone": "Asia/Tokyo", "mode": "off",
                      "notion_url": notion_url, "members": [],
                      "notion_targets": {"activity": {"status": "missing"}},
                      "notification": {"mode": "off"}}
            state = {"version": VERSION, "members": {}, "mirrors": {}}
        for field in ("timezone", "mode", "notion_targets", "notification"):
            if field in options:
                config[field] = options[field]
        member = next((m for m in config["members"] if m["id"] == identity), None)
        if member is None:
            member = {"id": identity, "slack_user_id": identity,
                      "display_name": identity, "active": True, "meeting_roots": []}
            config["members"].append(member)
        for field in ("display_name", "active", "notion_user_id", "member_page_url", "meeting_roots"):
            if field in options:
                member[field] = options[field]
        validate_config(config)
        hold_changed_bindings(config, state)
        state["members"].setdefault(identity, {"cursor": None, "days": {}, "seen": [],
                                                   "documents": {}, "meetings": {}})
        repo.save(f"members/{identity}/goals.md", repo.read(f"members/{identity}/goals.md")
                  if repo.exists(f"members/{identity}/goals.md") else "# Goals\n\n")
        # The user workspace's ignore file does not depend on the plugin package's ignore file.
        repo.save(".gitignore", "*\n!.gitignore\n")
        repo.save_json("config.json", config)
        repo.save_json("state.json", state)
    return {"status": "configured", "member_id": identity, "root": str(repo.root),
            "mode": config["mode"], "notion_discovery": config["notion_targets"]}


def configure(repo, config):
    validate_config(config)
    with repo.lock():
        previous, state = repo.load()
        previous_ids = {m["id"] for m in previous["members"]}
        require(previous_ids == {m["id"] for m in config["members"]},
                "configure preserves registered identities; use setup to add members")
        hold_changed_bindings(config, state)
        repo.save_json("config.json", config)
        repo.save_json("state.json", state)
    return {"status": "configured", "mode": config["mode"]}


def person(config, state, identity):
    member_id(identity)
    member = next((m for m in config["members"] if m["id"] == identity), None)
    require(member is not None and identity in state["members"], "unknown member")
    value = state["members"][identity]
    require(isinstance(value, dict) and all(isinstance(value.get(k), dict)
                for k in ("days", "documents", "meetings"))
            and isinstance(value.get("seen"), list), "invalid member state")
    return member, value


def window(config, state, identity, now=None):
    member, current = person(config, state, identity)
    cutoff = clock(now).replace(second=0, microsecond=0)
    cursor = instant(current["cursor"]) if current.get("cursor") else None
    require(cursor is None or cursor <= cutoff, "cursor is in the future")
    if current["days"]:
        latest = max(instant(day.get("cutoff")) for day in current["days"].values())
        require(cursor == latest, "cursor disagrees with the latest committed cutoff")
    start = cursor or cutoff - timedelta(days=3)
    limit = cutoff - timedelta(days=7)
    clamped = start < limit
    start = max(start, limit)
    today = cutoff.astimezone(zone(config["timezone"])).date().isoformat()
    reason = ("off" if config["mode"] == "off" else "inactive" if not member["active"]
              else "already-written" if today in current["days"]
              else "cadence" if cursor and cutoff - cursor < timedelta(hours=48) else None)
    return {"status": "ready" if reason is None else reason, "member_id": identity,
            "date": today, "start": iso(start), "cutoff": iso(cutoff),
            "backlog_truncated": clamped, "mode": config["mode"]}


def fact_key(fact):
    return digest(json.dumps([fact["source"], fact["source_id"],
                              iso(instant(fact["happened_at"]))], separators=(",", ":")))


def validate_capture(config, state, capture, now=None):
    require(capture.get("version") == VERSION, "unsupported capture version")
    member, current = person(config, state, capture.get("member_id"))
    start, cutoff = instant(capture.get("start")), instant(capture.get("cutoff"))
    require(cutoff <= clock(now), "capture cutoff is in the future")
    expected = window(config, state, member["id"], iso(cutoff))
    if capture.get("date") in current["days"]:
        return {"status": "already-written", "window": expected,
                "missing_sources": [], "facts": [], "duplicates": 0}
    require(start < cutoff, "empty or inverted capture range")
    require(start == instant(expected["start"]) and cutoff == instant(expected["cutoff"]),
            "capture must match the current planned window")
    require(capture.get("date") == expected["date"], "capture calendar date mismatch")
    sources = capture.get("sources")
    require(isinstance(sources, dict), "sources must be an object")
    missing = []
    for name in ("slack", "notion"):
        source = sources.get(name, {"status": "missing"})
        require(isinstance(source, dict) and source.get("status") in STATUSES,
                "invalid source status")
        if source["status"] != "complete":
            missing.append(name)
            continue
        if not (source.get("pagination_complete") is True
                and isinstance(source.get("evidence"), list) and source["evidence"]
                and all(isinstance(e, str) and e for e in source["evidence"])
                and isinstance(source.get("scope"), list) and source["scope"]
                and all(isinstance(s, str) and s for s in source["scope"])
                and source.get("retrieval") == "exhaustive"
                and source.get("start") and source.get("end")):
            missing.append(name)
            continue
        if instant(source["start"]) > start or instant(source["end"]) < cutoff:
            missing.append(name)
        if name == "notion" and (source.get("attribution_complete") is not True
                                  or not member.get("notion_user_id")):
            missing.append(name)
    facts = capture.get("facts")
    require(isinstance(facts, list), "facts must be a list")
    cleaned, keys, duplicate_count, skipped = [], set(current["seen"]), 0, []
    generated_page_ids = {m.get("page_id") for m in state["mirrors"].values() if m.get("page_id")}
    for fact in facts:
        require(isinstance(fact, dict) and fact.get("source") in {"slack", "notion"},
                "invalid fact source")
        require(isinstance(fact.get("source_id"), str) and fact["source_id"], "fact needs source ID")
        web_url(fact.get("url"))
        happened = instant(fact.get("happened_at"))
        require(start <= happened < cutoff, "fact is outside the half-open window")
        require(isinstance(fact.get("text"), str) and fact["text"].strip(), "fact needs text")
        require(fact.get("private") is False and fact.get("generated") is False,
                "private or generated content is excluded")
        require(fact["source_id"] not in generated_page_ids
                and "people-manager:" not in fact["text"], "generated mirror is excluded")
        if fact["source"] == "slack":
            require(fact.get("author_id") == member["slack_user_id"],
                    "Slack fact must be authored by the member")
            visibility = fact.get("visibility")
            require(visibility not in {"dm", "group_dm"}
                    and fact.get("is_im") is not True and fact.get("is_mpim") is not True,
                    "DM and group DM content is excluded")
            if visibility == "private_channel":
                membership = fact.get("membership", {})
                valid = (isinstance(membership, dict) and fact.get("channel_id")
                         and membership.get("channel_id") == fact["channel_id"]
                         and capture.get("operator_slack_user_id")
                         and membership.get("operator_id") == capture["operator_slack_user_id"]
                         and membership.get("confirmed") is True
                         and isinstance(membership.get("evidence"), str) and membership["evidence"]
                         and membership.get("checked_at"))
                if valid:
                    member_id(capture["operator_slack_user_id"])
                    operator = config["notification"].get("operator_slack_user_id")
                    valid = (operator == capture["operator_slack_user_id"] and
                             cutoff <= instant(membership["checked_at"]) <= clock(now))
                if not valid:
                    skipped.append({"source_id": fact["source_id"], "reason": "membership-unconfirmed"})
                    missing.append("slack")
                    continue
            elif visibility != "public":
                skipped.append({"source_id": fact["source_id"], "reason": "channel-type-unknown"})
                missing.append("slack")
                continue
        else:
            require(member.get("notion_user_id")
                    and fact.get("notion_user_id") == member["notion_user_id"],
                    "Notion fact attribution is unknown or mismatched")
        key = fact_key(fact)
        if key in keys:
            duplicate_count += 1
            continue
        keys.add(key)
        item = copy.deepcopy(fact)
        activity_date = (period(fact["activity_date"]) if "activity_date" in fact else
                         happened.astimezone(zone(config["timezone"])).date().isoformat())
        item.update({"happened_at": iso(happened), "key": key,
                     "activity_date": activity_date})
        cleaned.append(item)
    return {"status": "missing" if missing else expected["status"], "window": expected,
            "missing_sources": sorted(set(missing)), "facts": cleaned, "duplicates": duplicate_count,
            "skipped": skipped}


def preview(mode, result):
    if mode == "off":
        return {"status": "off"}
    if mode == "observe":
        return {"status": "observe", "facts_count": len(result.get("facts", [])),
                "missing_sources": result.get("missing_sources", [])}
    return {"status": "dry-run", "planned_status": result.get("status"),
            "facts_count": len(result.get("facts", [])), "window": result.get("window"),
            "missing_sources": result.get("missing_sources", [])}


def activity_markdown(identity, capture, checked):
    lines = [f"\n## {capture['date']}\n", f"<!-- people-manager:activity:{identity}:{capture['date']} -->\n",
             f"Window: [{capture['start']}, {capture['cutoff']})\n\n"]
    if checked["window"]["backlog_truncated"]:
        lines.append("Coverage note: older backlog excluded by the seven-day window.\n\n")
    if not checked["facts"]:
        lines.append("No activity found in the fully covered sources.\n")
    for item in checked["facts"]:
        text = item["text"].replace("\n", " ").replace("\r", " ")
        lines.append(f"- {item['activity_date']} | {item['happened_at']} | {text}\n"
                     f"  Source: {item['source']}:{item['source_id']} {item['url']}\n"
                     f"  <!-- fact:{item['key']} -->\n")
    return "".join(lines)


def mirror_key(kind, identity, when):
    return f"people-manager:{kind}:{identity}:{when}"


def canonical_mirror(body):
    """Parse only the visible ID plus one plain literal code block; fail closed."""
    require(isinstance(body, str), "mirror body must be a string")
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    index = 0
    while index < len(lines) and lines[index] == "":
        index += 1
    require(index < len(lines), "unsupported mirror markup")
    matched = re.fullmatch(r"Management ID: (people-manager:(?:activity|monthly):[UW][A-Z0-9]+:\d{4}-\d{2}(?:-\d{2})?)", lines[index])
    require(matched is not None, "visible Management ID is missing or changed")
    key = matched.group(1)
    index += 1
    while index < len(lines) and lines[index] == "":
        index += 1
    require(index < len(lines) and lines[index] in {"```", "```text", "```plain text", "```plaintext"},
            "unsupported literal code fence")
    index += 1
    payload = []
    while index < len(lines) and lines[index] != "```":
        require(not re.match(r"\s*(?:```|~~~)", lines[index]), "nested or unknown code fence")
        payload.append(lines[index])
        index += 1
    require(index < len(lines), "literal code block is not closed")
    index += 1
    require(all(line == "" for line in lines[index:]), "extra mirror content or unknown markup")
    return {"adapter": ADAPTER, "key": key, "payload_lines": payload}


def mirror_body(key, body):
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    if any(re.match(r"\s*(?:```|~~~)", line) for line in normalized.split("\n")):
        raise Unsupported("literal mirror cannot wrap an existing fence; unsupported")
    sent = "\n".join([f"Management ID: {key}", "", "```text", *normalized.split("\n"), "```", ""])
    canonical_mirror(sent)
    return sent


def add_pending(state, kind, identity, when, body_hash, path):
    key = mirror_key(kind, identity, when)
    state["mirrors"][key] = {"status": "pending", "failures": 0, "kind": kind,
                             "member_id": identity, "period": when,
                             "body_sha256": body_hash, "path": path}


def commit_activity(repo, capture, now=None):
    config, state = repo.load()
    if config["mode"] == "off":
        return {"status": "off"}
    checked = validate_capture(config, state, capture, now)
    if config["mode"] != "on":
        return preview(config["mode"], checked)
    if checked["status"] != "ready":
        return {"status": checked["status"], "missing_sources": checked["missing_sources"]}
    with repo.lock():
        config, state = repo.load()
        checked = validate_capture(config, state, capture, now)
        if config["mode"] != "on":
            return preview(config["mode"], checked)
        if checked["status"] != "ready":
            return {"status": checked["status"], "missing_sources": checked["missing_sources"]}
        identity, today = capture["member_id"], capture["date"]
        current = state["members"][identity]
        activity_records(repo, current, identity)
        path = f"members/{identity}/activity/{today[:7]}.md"
        section = activity_markdown(identity, capture, checked)
        previous = repo.read(path) if repo.exists(path) else f"# Activity {today[:7]}\n"
        marker = f"<!-- {mirror_key('activity', identity, today)} -->"
        if marker in previous:
            return {"status": "already-written"}
        # The immutable sidecar allows month selection by activity_date, across collection months.
        sidecar = f"members/{identity}/activity/records/{today}.json"
        require(not repo.exists(sidecar), "existing activity record needs manual reconciliation")
        repo.save(path, previous + section)
        record_value = {"version": VERSION, "member_id": identity, "date": today,
                        "start": capture["start"], "cutoff": capture["cutoff"],
                        "sources": capture["sources"], "facts": checked["facts"],
                        "body_sha256": digest(section)}
        repo.save_json(sidecar, record_value)
        current["days"][today] = {"path": path, "record_path": sidecar,
                                   "record_sha256": digest(encoded(record_value)),
                                   "body_sha256": digest(section), "body": section,
                                   "cutoff": checked["window"]["cutoff"]}
        current["seen"].extend(f["key"] for f in checked["facts"])
        current["cursor"] = checked["window"]["cutoff"]
        add_pending(state, "activity", identity, today, digest(section), path)
        repo.save_json("state.json", state)
    return {"status": "committed", "path": path, "body_sha256": digest(section),
            "facts_count": len(checked["facts"]), "cursor": current["cursor"],
            "mirror_key": mirror_key("activity", identity, today)}


def import_meeting(repo, value):
    config, state = repo.load()
    if config["mode"] == "off":
        return {"status": "off"}
    person(config, state, value.get("member_id"))
    require(isinstance(value.get("meeting_id"), str) and value["meeting_id"], "meeting_id is required")
    period(value.get("date"))
    require(bool(value.get("source_url")) != bool(value.get("source_file")),
            "meeting needs exactly one explicit URL or local transcript source")
    if value.get("source_url"):
        web_url(value["source_url"])
    if value.get("source_file"):
        require(isinstance(value["source_file"], str) and value["source_file"], "invalid transcript path")
        source = Path(value["source_file"]).expanduser().resolve()
        require(source.is_relative_to(repo.workspace) and source.is_file(),
                "local transcript source must be an existing workspace file")
        require(source.name != ".env" and not source.name.startswith(".env."), "secret file is excluded")
    participants, transcript = value.get("participants"), value.get("transcript")
    require(isinstance(participants, list) and participants
            and all(isinstance(p, str) and p for p in participants), "participants are required")
    require(isinstance(transcript, list) and transcript, "raw transcript is required; summary alone is insufficient")
    unknown = False
    for utterance in transcript:
        require(isinstance(utterance, dict) and isinstance(utterance.get("text"), str)
                and utterance["text"].strip(), "invalid transcript utterance")
        speaker = utterance.get("speaker")
        require(speaker is None or isinstance(speaker, str), "invalid speaker")
        if not speaker or speaker not in participants:
            unknown = True
    stored = {k: value[k] for k in ("member_id", "meeting_id", "date", "participants", "transcript",
                                    "source_url", "source_file", "summary") if k in value}
    stored.update({"private": True, "speaker_status": "unconfirmed" if unknown else "confirmed",
                   "summary_is_evidence": False})
    if config["mode"] != "on":
        return {"status": config["mode"], "speaker_status": stored["speaker_status"]}
    identity, mid = value["member_id"], digest(value["meeting_id"])[:32]
    path = f"members/{identity}/meetings/{mid}.json"
    with repo.lock():
        config, state = repo.load()
        if config["mode"] != "on":
            return {"status": config["mode"]}
        if repo.exists(path):
            return {"status": "already-written", "path": path}
        repo.save_json(path, stored)
        state["members"][identity]["meetings"][mid] = {"path": path, "date": value["date"],
                                                       "sha256": digest(encoded(stored)),
                                                       "speaker_status": stored["speaker_status"]}
        repo.save_json("state.json", state)
    return {"status": "imported", "path": path, "speaker_status": stored["speaker_status"], "private": True}


def activity_records(repo, current, identity):
    """Reject interrupted multi-file commits; never silently recover or duplicate them."""
    folder = f"members/{identity}/activity"
    directory = repo.safe(folder)
    for path in directory.glob("*.md"):
        raw = repo.read(f"{folder}/{path.name}")
        for found_id, collected in re.findall(r"<!-- people-manager:activity:([UW][A-Z0-9]+):(\d{4}-\d{2}-\d{2}) -->", raw):
            require(found_id == identity and collected in current["days"],
                    "incomplete local activity commit; manual reconciliation is required")
    record_folder = repo.safe(f"{folder}/records")
    known_records = {day["record_path"] for day in current["days"].values()}
    for path in record_folder.glob("*.json"):
        require(f"{folder}/records/{path.name}" in known_records,
                "orphan activity evidence; manual reconciliation is required")
    records = []
    for collected, day in current["days"].items():
        original = repo.read(day["path"])
        body = day["body"]
        require(digest(body) == day["body_sha256"] and body in original
                and original.count(f"<!-- {mirror_key('activity', identity, collected)} -->") == 1,
                "local activity section changed; monthly report held")
        raw_record = repo.read(day["record_path"])
        require(digest(raw_record) == day.get("record_sha256"),
                "local activity evidence changed; monthly report held")
        record = repo.json(day["record_path"])
        require(record.get("member_id") == identity and record.get("date") == collected
                and record.get("body_sha256") == day["body_sha256"]
                and instant(record.get("cutoff")) == instant(day.get("cutoff")),
                "activity record identity mismatch")
        records.append(record)
        for item in record["facts"]:
            require(item.get("key") == fact_key(item) and item.get("private") is False
                    and item.get("generated") is False, "invalid activity fact evidence")
            period(item.get("activity_date"))
    keys = [fact["key"] for record in records for fact in record["facts"]]
    require(len(keys) == len(set(keys)) and set(keys) == set(current["seen"]),
            "activity deduplication state disagrees with committed evidence")
    if records:
        require(instant(current.get("cursor")) == max(instant(record["cutoff"]) for record in records),
                "cursor disagrees with committed evidence")
    return records


def monthly_evidence(repo, current, identity, when):
    eligible = set()
    for record in activity_records(repo, current, identity):
        for item in record["facts"]:
            activity_date = item["activity_date"]
            if activity_date.startswith(when):
                eligible.add(item["key"])
    return eligible


def commit_document(repo, value):
    config, state = repo.load()
    if config["mode"] == "off":
        return {"status": "off"}
    identity = value.get("member_id")
    person(config, state, identity)
    kind = value.get("kind")
    require(kind in {"prep", "monthly"}, "invalid document kind")
    when = period(value.get("period"), monthly=kind == "monthly")
    body = value.get("body")
    require(isinstance(body, str) and body.strip(), "document body is required")
    if kind == "monthly":
        require(not any(re.match(r"\s*(?:```|~~~)", line) for line in body.splitlines())
                and re.search(r"</?table(?:\s|>)", body, re.IGNORECASE) is None,
                "monthly body supports headings, paragraphs, and lists; fences/tables are unsupported")
        require(not value.get("private_meeting_ids"), "private meetings cannot enter monthly reports")
        evidence = value.get("evidence_fact_keys")
        require(isinstance(evidence, list), "monthly requires activity evidence keys")
        eligible = monthly_evidence(repo, state["members"][identity], identity, when)
        require(all(isinstance(k, str) and k in eligible for k in evidence),
                "monthly evidence must be public activity in the requested activity month")
        marker = f"<!-- {mirror_key(kind, identity, when)} -->"
        if marker not in body:
            body = body.rstrip() + "\n\n" + marker + "\n"
        require(body.count(marker) == 1, "monthly document has duplicate identity markers")
    key = f"{kind}:{when}"
    path = f"members/{identity}/{kind}/{when}.md"
    if config["mode"] != "on":
        return {"status": config["mode"], "path": path, "body_sha256": digest(body)}
    with repo.lock():
        config, state = repo.load()
        if config["mode"] != "on":
            return {"status": config["mode"]}
        current = state["members"][identity]
        if key in current["documents"] or repo.exists(path):
            return {"status": "already-written", "path": path}
        if kind == "monthly":
            eligible = monthly_evidence(repo, current, identity, when)
            require(all(k in eligible for k in evidence), "monthly activity evidence changed while saving")
        repo.save(path, body)
        current["documents"][key] = {"path": path, "body_sha256": digest(body)}
        if kind == "monthly":
            add_pending(state, kind, identity, when, digest(body), path)
        repo.save_json("state.json", state)
    return {"status": "committed", "path": path, "body_sha256": digest(body),
            "mirror_key": mirror_key(kind, identity, when) if kind == "monthly" else None}


def expected_mirror(repo, config, state, value):
    identity = value.get("member_id")
    member, current = person(config, state, identity)
    kind = value.get("kind")
    require(kind in {"activity", "monthly"}, "invalid mirror kind")
    when = period(value.get("period"), monthly=kind == "monthly")
    key = mirror_key(kind, identity, when)
    require(key in state["mirrors"], "mirror requires a committed local original")
    record = state["mirrors"][key]
    target = config["notion_targets"].get("activity", {"status": "missing"})
    require(target.get("status") == "ready" and member.get("member_page_url"),
            "mirror target or member relation is missing")
    if kind == "activity":
        day = current["days"].get(when)
        require(day is not None, "missing original activity section")
        body = day["body"]
        require(body in repo.read(day["path"]) and digest(body) == record["body_sha256"],
                "local original changed; mirror held")
    else:
        body = repo.read(record["path"])
        require(digest(body) == record["body_sha256"], "local original changed; mirror held")
    sent = mirror_body(key, body)
    expected = mirror_binding(config, record)
    expected.update({"adapter": ADAPTER, "body": sent, "sent_body_sha256": digest(sent),
                     "canonical_sent_sha256": digest(encoded(canonical_mirror(sent)))})
    return key, record, expected


def mirror_binding(config, record):
    identity, when, kind = record["member_id"], record["period"], record["kind"]
    member = next(m for m in config["members"] if m["id"] == identity)
    target = config["notion_targets"].get("activity", {"status": "missing"})
    key = mirror_key(kind, identity, when)
    props = dict(target.get("properties", {}))
    props.update({"member_id": identity, "period": when, "kind": kind, "key": key})
    return {"source_id": target.get("source_id") if target.get("status") == "ready" else None,
            "relation": member.get("member_page_url"), "key": key, "properties": props,
            "local_body_sha256": record["body_sha256"]}


def hold_changed_bindings(config, state):
    for record in state["mirrors"].values():
        if record.get("binding") is not None and record["binding"] != mirror_binding(config, record):
            record.update(status="held", reason="binding-changed")


def matches_expected(page, expected, page_id=None, require_fetch=False):
    if not (isinstance(page, dict) and isinstance(page.get("page_id"), str)
            and page["page_id"] and (page_id is None or page["page_id"] == page_id)
            and all(page.get(k) == expected[k] for k in ("source_id", "relation", "key", "properties"))
            and isinstance(page.get("body"), str) and digest(page["body"]) == page.get("body_sha256")):
        return False
    try:
        if digest(encoded(canonical_mirror(page["body"]))) != expected["canonical_sent_sha256"]:
            return False
        if require_fetch:
            fetch = page.get("fetch", {})
            if not (isinstance(fetch, dict) and fetch.get("status") == "complete"
                    and fetch.get("pagination_complete") is True and fetch.get("independent") is True
                    and fetch.get("method") == "connector-fetch" and fetch.get("fetched_at")
                    and fetch.get("truncated", False) is False
                    and fetch.get("unknown_block_count", 0) == 0
                    and isinstance(fetch.get("unknown_block_ids", []), list)
                    and not fetch.get("unknown_block_ids", [])
                    and isinstance(fetch.get("evidence"), list) and fetch["evidence"]
                    and all(isinstance(e, str) and e for e in fetch["evidence"])
                    and instant(fetch["fetched_at"]) <= clock()):
                return False
    except Invalid:
        return False
    return True


def confirm_mirror(record, expected, page):
    record.update(status="confirmed", page_id=page["page_id"], adapter=ADAPTER,
                  sent_body_sha256=expected["sent_body_sha256"], fetched_body_sha256=digest(page["body"]),
                  canonical_sent_sha256=expected["canonical_sent_sha256"],
                  canonical_fetched_sha256=digest(encoded(canonical_mirror(page["body"]))),
                  fetched_at=page["fetch"]["fetched_at"], fetch_evidence=copy.deepcopy(page["fetch"]))
    record.pop("reason", None)


def record_mirror(repo, value):
    config, state = repo.load()
    if config["mode"] == "off":
        return {"status": "off"}
    try:
        key, record, expected = expected_mirror(repo, config, state, value)
    except Unsupported:
        if config["mode"] != "on":
            return {"status": config["mode"], "reason": "unsupported-adapter"}
        key = mirror_key(value["kind"], value["member_id"], value["period"])
        with repo.lock():
            config, state = repo.load()
            if config["mode"] != "on":
                return {"status": config["mode"], "reason": "unsupported-adapter"}
            state["mirrors"][key].update(status="held", reason="unsupported-adapter")
            repo.save_json("state.json", state)
        return {"status": "held", "key": key, "can_create": False, "reason": "unsupported-adapter"}
    outcome = value.get("outcome")
    require(outcome in {"inspect", "unknown", "failed", "created", "reconcile"}, "invalid mirror outcome")
    if config["mode"] != "on":
        return {"status": config["mode"], "key": key, "expected": expected}
    with repo.lock():
        config, state = repo.load()
        if config["mode"] != "on":
            return {"status": config["mode"]}
        key, record, expected = expected_mirror(repo, config, state, value)
        binding = mirror_binding(config, record)
        if record.get("binding") is not None and record["binding"] != binding:
            record.update(status="held", reason="binding-changed")
            repo.save_json("state.json", state)
        if record["status"] == "confirmed" and not value.get("search") and not value.get("readback"):
            return {"status": "confirmed", "key": key, "page_id": record["page_id"], "can_create": False}
        if record["status"] in {"held", "hold"}:
            return {"status": "held", "key": key, "can_create": False}
        search = value.get("search", {})
        complete = (isinstance(search, dict) and search.get("status") == "complete"
                    and search.get("pagination_complete") is True and search.get("key") == key
                    and search.get("source_id") == expected["source_id"]
                    and isinstance(search.get("evidence"), list) and bool(search["evidence"])
                    and isinstance(search.get("matches"), list))
        matches = search.get("matches", []) if complete else []
        claimed_now = False
        was_confirmed = record["status"] == "confirmed"
        if was_confirmed and complete and not matches:
            record.update(status="held", reason="confirmed-page-missing")
        elif was_confirmed and matches and matches[0].get("page_id") != record["page_id"]:
            record.update(status="held", reason="confirmed-page-identity-changed")
        elif len(matches) > 1 or (matches and not matches_expected(matches[0], expected)):
            record.update(status="held", reason="duplicate-or-mismatch")
        elif was_confirmed and value.get("readback") and not matches_expected(value["readback"], expected, record["page_id"], require_fetch=True):
            record.update(status="held", reason="readback-mismatch")
        elif was_confirmed and not complete:
            record["reason"] = "search-incomplete"
        elif outcome == "unknown":
            record.update(status="unknown", reason="create-result-unknown")
        elif outcome == "failed":
            record["failures"] += 1
            # A failure report cannot erase an uncertain or in-flight create claim.
            record.update(status="held" if record["failures"] >= 3 else record["status"], reason="mirror-failed")
        elif outcome == "created":
            # inspect records a durable create claim before the connector's one create attempt.
            require(record["status"] == "creating", "create was not claimed; inspect complete search first")
            readback = value.get("readback")
            if (isinstance(value.get("page_id"), str) and value["page_id"]
                    and matches_expected(readback, expected, value["page_id"], require_fetch=True)):
                confirm_mirror(record, expected, readback)
            else:
                record.update(status="held", reason="readback-mismatch")
        elif complete and matches:
            readback = value.get("readback")
            if matches_expected(readback, expected, matches[0]["page_id"], require_fetch=True):
                confirm_mirror(record, expected, readback)
            else:
                record.update(status="held", reason="readback-mismatch")
        elif complete and not matches:
            if outcome == "reconcile":
                record.update(status="pending")
                record.pop("reason", None)
            elif record["status"] == "pending":
                record.update(status="creating")
                record.update(adapter=ADAPTER, sent_body_sha256=expected["sent_body_sha256"],
                              canonical_sent_sha256=expected["canonical_sent_sha256"])
                record.pop("reason", None)
                claimed_now = True
            # creating/unknown never permits a second create until complete reconciliation.
        elif outcome in {"inspect", "reconcile"}:
            record["reason"] = "search-incomplete"
        if claimed_now or record["status"] in {"confirmed", "unknown"}:
            record.setdefault("binding", copy.deepcopy(binding))
        repo.save_json("state.json", state)
    return {"status": record["status"], "key": key, "expected": expected,
            "can_create": claimed_now,
            "page_id": record.get("page_id"), "reason": record.get("reason")}


def status(repo):
    config, state = repo.load()
    return {"status": "configured", "mode": config["mode"], "timezone": config["timezone"],
            "members": [{"id": member["id"], "display_name": member["display_name"],
                         "active": member["active"], "cursor": state["members"][member["id"]].get("cursor"),
                         "activity_sections": len(state["members"][member["id"]]["days"])}
                        for member in config["members"]],
            "notion_targets": config["notion_targets"],
            "notification": config["notification"],
            "mirrors": [{"key": key, "status": "held" if item.get("binding") is not None
                         and item["binding"] != mirror_binding(config, item) else item["status"],
                         "failures": item["failures"], "page_id": item.get("page_id"),
                         "reason": item.get("reason")}
                        for key, item in state["mirrors"].items()]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".", help="user working directory; never the plugin cache")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "setup"):
        command = commands.add_parser(name)
        command.add_argument("--slack-user-id", required=True)
        command.add_argument("--notion-url", required=True)
        command.add_argument("--input", help="optional setup/discovery JSON fragment")
    command = commands.add_parser("configure")
    command.add_argument("--input", required=True, help="complete updated config JSON")
    commands.add_parser("validate-config")
    commands.add_parser("status")
    command = commands.add_parser("window")
    command.add_argument("--member", required=True)
    command.add_argument("--now")
    for name in ("validate-capture", "commit-activity", "import-meeting", "commit-document", "record-mirror"):
        command = commands.add_parser(name)
        command.add_argument("--input", required=True)
        if name in {"validate-capture", "commit-activity"}:
            command.add_argument("--now")
    args = parser.parse_args(argv)
    try:
        repo = Repository(args.workspace)
        name = args.command
        if name in {"init", "setup"}:
            result = setup(repo, args.slack_user_id, args.notion_url,
                           read_input(args.input) if args.input else None)
        elif name == "configure":
            result = configure(repo, read_input(args.input))
        elif name == "status":
            result = status(repo)
        elif name == "validate-config":
            repo.load()
            result = {"status": "valid"}
        elif name == "window":
            config, state = repo.load()
            result = window(config, state, args.member, args.now)
        elif name == "validate-capture":
            config, state = repo.load()
            checked = validate_capture(config, state, read_input(args.input), args.now)
            result = {k: v for k, v in checked.items() if k != "facts"}
            result["facts_count"] = len(checked["facts"])
        else:
            operation = {"commit-activity": commit_activity, "import-meeting": import_meeting,
                         "commit-document": commit_document, "record-mirror": record_mirror}[name]
            value = read_input(args.input)
            result = operation(repo, value, args.now) if name == "commit-activity" else operation(repo, value)
        print(encoded(result), end="")
        return 0
    except (Invalid, OSError, KeyError, TypeError) as exc:
        message = str(exc) if isinstance(exc, Invalid) else "local operation failed; inspect files without sharing secrets"
        print(encoded({"status": "error", "error": message}), end="")
        return 2


if __name__ == "__main__":
    sys.exit(main())
