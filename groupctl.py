import argparse
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()
GROUP_DIR = ROOT / ".group"
LOCAL_DIR = GROUP_DIR / "local"
EVENTS_DIR = GROUP_DIR / "events"
MEMBERS_DIR = GROUP_DIR / "members"
FINAL_DIR = GROUP_DIR / "final"
PROTOCOL_VERSION = "0.1"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compact_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_git(args: list[str], check: bool = True) -> str:
    """執行 Git 指令（整合版：加入 Windows utf-8 容錯與 errors='replace'）"""
    try:
        res = subprocess.run(
            ["git"] + args,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"  # 吸收你的版本優點：避免 Windows 編碼錯誤導致崩潰
        )
        if check and res.returncode != 0:
            err_msg = res.stderr.strip() if res.stderr else "unknown error"
            raise RuntimeError(f"git {' '.join(args)} failed: {err_msg}")
        return res.stdout.strip() if res.stdout else ""
    except Exception as e:
        if check:
            raise RuntimeError(f"git {' '.join(args)} execution error: {e}")
        return ""


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_group_cfg() -> dict:
    cfg_path = GROUP_DIR / "group.json"
    if not cfg_path.exists():
        sys.exit("Error: .group/group.json not found. Run 'python groupctl.py init' first.")
    return read_json(cfg_path)


def load_me() -> dict:
    me_path = LOCAL_DIR / "me.json"
    if not me_path.exists():
        sys.exit("Error: .group/local/me.json not found. Run 'python groupctl.py register' first.")
    return read_json(me_path)


def load_local_state() -> dict:
    state_path = LOCAL_DIR / "state.json"
    if state_path.exists():
        return read_json(state_path)
    return {"seen_events": []}


def save_local_state(state: dict) -> None:
    write_json(LOCAL_DIR / "state.json", state)


def all_events() -> list[dict]:
    if not EVENTS_DIR.exists():
        return []
    events = []
    for p in sorted(EVENTS_DIR.glob("E-*.json")):
        try:
            events.append(read_json(p))
        except Exception:
            pass
    return events


def next_change_id() -> str:
    max_num = 0
    for ev in all_events():
        cid = ev.get("change_id", "")
        if isinstance(cid, str) and cid.startswith("C-"):
            try:
                max_num = max(max_num, int(cid.split("-", 1)[1]))
            except ValueError:
                pass
    return f"C-{max_num + 1}"


def write_event(event_type: str, payload: dict, related_events: list[str] | None = None) -> Path:
    cfg = load_group_cfg()
    me = load_me()
    suffix = uuid.uuid4().hex[:4]
    event_id = f"E-{compact_utc()}-{me['person_id']}-{suffix}"
    event = {
        "protocol_version": PROTOCOL_VERSION,
        "event_id": event_id,
        "event_type": event_type,
        "group_id": cfg["group_id"],
        "person_id": me["person_id"],
        "created_at": now_utc(),
        "related_events": related_events or [],
    }
    event.update(payload)
    out_path = EVENTS_DIR / f"{event_id}.json"
    write_json(out_path, event)
    state = load_local_state()
    if event_id not in state["seen_events"]:
        state["seen_events"].append(event_id)
        save_local_state(state)
    return out_path


def cmd_init(args: argparse.Namespace) -> None:
    for d in [GROUP_DIR / "assignment", MEMBERS_DIR, EVENTS_DIR, FINAL_DIR, LOCAL_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    write_json(GROUP_DIR / "group.json", {
        "protocol_version": PROTOCOL_VERSION,
        "group_id": args.group_id,
        "canonical_branch": args.branch,
        "assignment_file": ".group/assignment/assignment.md",
    })
    print(f"✅ 已初始化群組 {args.group_id} (canonical_branch={args.branch})")


def cmd_register(args: argparse.Namespace) -> None:
    load_group_cfg()
    joined = datetime.now().astimezone().isoformat(timespec="seconds")
    member_doc = {
        "protocol_version": PROTOCOL_VERSION,
        "person_id": args.person_id,
        "display_name": args.name,
        "joined_at": joined,
    }
    write_json(MEMBERS_DIR / f"{args.person_id}.json", member_doc)
    write_json(LOCAL_DIR / "me.json", {
        "person_id": args.person_id,
        "display_name": args.name,
    })
    print(f"✅ 成功註冊成員: {args.person_id} ({args.name})")


def cmd_branch(args: argparse.Namespace) -> None:
    me = load_me()
    branch_name = f"people/{me['person_id']}/{args.topic}"
    existing = run_git(["branch", "--list", branch_name], check=False)
    if existing:
        run_git(["checkout", branch_name])
    else:
        run_git(["checkout", "-b", branch_name])
    print(f"🌿 已切換至個人分支: {branch_name}")


def cmd_status(args: argparse.Namespace) -> None:
    cfg = load_group_cfg()
    me = load_me() if (LOCAL_DIR / "me.json").exists() else {"person_id": "(unregistered)", "display_name": ""}
    if args.fetch:
        run_git(["fetch", "--all", "--prune"], check=False)

    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], check=False) or "(no commits)"
    head = run_git(["rev-parse", "--short", "HEAD"], check=False) or "(none)"
    dirty = run_git(["status", "--short"], check=False)
    canonical = cfg["canonical_branch"]
    can_ref = f"origin/{canonical}" if run_git(["rev-parse", "--verify", f"origin/{canonical}"], check=False) else canonical
    can_commit = run_git(["rev-parse", "--short", can_ref], check=False) or "(none)"
    ahead_behind = run_git(["rev-list", "--left-right", "--count", f"{can_ref}...HEAD"], check=False)

    state = load_local_state()
    seen = set(state.get("seen_events", []))
    events = all_events()
    unseen = [e for e in events if e["event_id"] not in seen]
    blockers = [e for e in events if e["event_type"] == "blocker"]
    tests = [e for e in events if e["event_type"] == "test_result"]

    print(f"📊 Group: {cfg['group_id']} | Person: {me['person_id']} ({me['display_name']})")
    print(f"📌 Current Branch: {branch} @ {head}")
    print(f"🔗 Canonical ({can_ref}): {can_commit} | Behind/Ahead: {ahead_behind or 'N/A'}")
    print(f"📝 Uncommitted Changes: {'Yes' if dirty else 'No'}")
    if dirty:
        print(dirty)
    print(f"🔔 Unprocessed Events: {len(unseen)}")
    for e in unseen:
        print(f"  - [{e['event_id']}] {e['event_type']} by {e['person_id']}: {e.get('summary', e.get('text', ''))}")
    if tests:
        lt = tests[-1]
        print(f"🧪 Latest Test: {lt['automated_result']} @ {lt.get('commit')} ({lt.get('summary', '')})")
    if blockers:
        print(f"⚠️ Recorded Blockers: {len(blockers)} (latest: {blockers[-1].get('summary')})")


def cmd_sync(args: argparse.Namespace) -> None:
    load_group_cfg()
    run_git(["fetch", "--all", "--prune"], check=False)
    state = load_local_state()
    seen = set(state.get("seen_events", []))
    events = all_events()
    unseen = [e for e in events if e["event_id"] not in seen]

    print(f"🔄 發現 {len(unseen)} 個新事件:")
    for e in unseen:
        print(json.dumps(e, ensure_ascii=False, indent=2))
        if not args.peek:
            seen.add(e["event_id"])
    if not args.peek:
        state["seen_events"] = sorted(seen)
        save_local_state(state)
        print("✅ 已將新事件標記為已讀 (.group/local/state.json)")


def cmd_pub(args: argparse.Namespace) -> None:
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    commit = run_git(["rev-parse", "--short", "HEAD"])
    cid = args.change_id or next_change_id()
    ev_path = write_event("change_published", {
        "change_id": cid,
        "branch": branch,
        "commit": commit,
        "summary": args.summary,
        "files_changed": args.files or [],
        "interface_changes": args.interfaces or [],
        "tests_run": args.tests or [],
        "known_issues": args.issues or [],
        "proposed_for_integration": True,
    })
    print(f"📤 已發布變更 {cid} -> {ev_path.relative_to(ROOT)}")


def cmd_rev(args: argparse.Namespace) -> None:
    ev_path = write_event("review", {
        "change_id": args.change_id,
        "verdict": args.verdict,
        "summary": args.summary,
        "issues": args.issues or [],
        "tests_run": args.tests or [],
    }, related_events=args.related or [])
    print(f"🔍 已發布對 {args.change_id} 的審查結果 ({args.verdict}) -> {ev_path.relative_to(ROOT)}")


def cmd_test(args: argparse.Namespace) -> None:
    commit = run_git(["rev-parse", "--short", "HEAD"])
    result_status = args.result
    if args.cmd:
        proc = subprocess.run(args.cmd, shell=True, cwd=ROOT)
        result_status = "pass" if proc.returncode == 0 else "fail"
    ev_path = write_event("test_result", {
        "scope": args.scope,
        "commit": commit,
        "commands": [args.cmd] if args.cmd else [],
        "automated_result": result_status,
        "passed": args.passed,
        "failed": args.failed,
        "skipped": args.skipped,
        "human_checks_required": args.human_checks or [],
        "summary": args.summary,
    })
    print(f"🧪 已發布測試結果 ({result_status} @ {commit}) -> {ev_path.relative_to(ROOT)}")


def cmd_int(args: argparse.Namespace) -> None:
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    merge_commit = args.merge_commit or run_git(["rev-parse", "--short", "HEAD"])
    ev_path = write_event("integration_result", {
        "change_id": args.change_id,
        "target_branch": branch,
        "result": args.result,
        "merge_commit": merge_commit,
        "conflicts": args.conflicts or [],
        "conflict_resolution_summary": args.resolution or "",
        "verification": {
            "build": args.build,
            "tests": args.tests,
            "semantic_review": args.semantic,
        },
        "summary": args.summary,
    }, related_events=args.related or [])
    print(f"🔀 已發布整合結果對於 {args.change_id} ({args.result}) -> {ev_path.relative_to(ROOT)}")


def cmd_blocker(args: argparse.Namespace) -> None:
    ev_path = write_event("blocker", {
        "summary": args.summary,
        "blocking_change_id": args.change_id or "",
        "requested_action": args.action,
    })
    print(f"⚠️ 已回報阻礙 -> {ev_path.relative_to(ROOT)}")


def cmd_final_candidate(args: argparse.Namespace) -> None:
    cfg = load_group_cfg()
    commit = run_git(["rev-parse", "HEAD"])
    members = [read_json(p)["display_name"] for p in sorted(MEMBERS_DIR.glob("*.json")) if p.name != "me.json"]
    md = (
        f"# Group Final Report (Candidate)\n\n"
        f"## Assignment\n{cfg['assignment_file']}\n\n"
        f"## Result\n{args.summary}\n\n"
        f"## Canonical Commit\n{commit}\n\n"
        f"## Important Changes\n{args.changes}\n\n"
        f"## Validation\n{args.validation}\n\n"
        f"## Known Limitations\n{args.limitations or 'None'}\n\n"
        f"## Contributors\n{', '.join(members)}\n"
    )
    cand_path = FINAL_DIR / "candidate.md"
    cand_path.write_text(md, encoding="utf-8")
    ev_path = write_event("final_candidate", {
        "canonical_branch": cfg["canonical_branch"],
        "canonical_commit": commit,
        "candidate_report_path": ".group/final/candidate.md",
        "known_issues": [args.limitations] if args.limitations else [],
        "summary": args.summary,
    })
    print(f"🏁 已產生最終候選報告與事件 -> {ev_path.relative_to(ROOT)}")


def cmd_final_confirm(args: argparse.Namespace) -> None:
    cfg = load_group_cfg()
    me = load_me()
    commit = run_git(["rev-parse", "HEAD"])
    cand_path = FINAL_DIR / "candidate.md"
    report_path = FINAL_DIR / "final_report.md"
    if cand_path.exists():
        text = cand_path.read_text(encoding="utf-8").replace("# Group Final Report (Candidate)", "# Group Final Report")
        report_path.write_text(text, encoding="utf-8")
    else:
        sys.exit("Error: 請先執行 'python groupctl.py final-candidate'。")

    status = "completed_with_known_limitations" if args.limitations else "completed"
    final_doc = {
        "protocol_version": PROTOCOL_VERSION,
        "group_id": cfg["group_id"],
        "canonical_branch": cfg["canonical_branch"],
        "canonical_commit": commit,
        "report_file": ".group/final/final_report.md",
        "initiated_by": me["person_id"],
        "created_at": now_utc(),
        "status": status,
        "known_limitations": [args.limitations] if args.limitations else [],
    }
    write_json(FINAL_DIR / "final.json", final_doc)
    ev_path = write_event("final_result", {
        "canonical_branch": cfg["canonical_branch"],
        "canonical_commit": commit,
        "final_report_path": ".group/final/final_report.md",
        "known_limitations": final_doc["known_limitations"],
        "initiated_by": me["person_id"],
        "summary": "Group finalization completed.",
    })
    print(f"🎉 專案最終確認完成 -> {ev_path.relative_to(ROOT)}")


def main() -> None:
    p = argparse.ArgumentParser(prog="groupctl", description="Group Collaboration Tool v0.1 (Unified)")
    sub = p.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--group-id", required=True)
    p_init.add_argument("--branch", default="main")
    p_init.set_defaults(func=cmd_init)

    p_reg = sub.add_parser("register")
    p_reg.add_argument("--person-id", required=True)
    p_reg.add_argument("--name", required=True)
    p_reg.set_defaults(func=cmd_register)

    p_br = sub.add_parser("branch")
    p_br.add_argument("--topic", required=True)
    p_br.set_defaults(func=cmd_branch)

    p_st = sub.add_parser("status")
    p_st.add_argument("--fetch", action="store_true")
    p_st.set_defaults(func=cmd_status)

    p_sy = sub.add_parser("sync")
    p_sy.add_argument("--peek", action="store_true")
    p_sy.set_defaults(func=cmd_sync)

    p_pub = sub.add_parser("pub")
    p_pub.add_argument("--change-id", default=None)
    p_pub.add_argument("--summary", required=True)
    p_pub.add_argument("--files", nargs="*")
    p_pub.add_argument("--interfaces", nargs="*")
    p_pub.add_argument("--tests", nargs="*")
    p_pub.add_argument("--issues", nargs="*")
    p_pub.set_defaults(func=cmd_pub)

    p_rev = sub.add_parser("rev")
    p_rev.add_argument("--change-id", required=True)
    p_rev.add_argument("--verdict", required=True, choices=["accept", "accept_with_changes", "reject", "needs_more_evidence"])
    p_rev.add_argument("--summary", required=True)
    p_rev.add_argument("--issues", nargs="*")
    p_rev.add_argument("--tests", nargs="*")
    p_rev.add_argument("--related", nargs="*")
    p_rev.set_defaults(func=cmd_rev)

    p_tst = sub.add_parser("test")
    p_tst.add_argument("--scope", default="current_branch")
    p_tst.add_argument("--cmd", default="")
    p_tst.add_argument("--result", default="pass", choices=["pass", "fail", "partial", "not_available"])
    p_tst.add_argument("--passed", type=int, default=0)
    p_tst.add_argument("--failed", type=int, default=0)
    p_tst.add_argument("--skipped", type=int, default=0)
    p_tst.add_argument("--human-checks", nargs="*")
    p_tst.add_argument("--summary", required=True)
    p_tst.set_defaults(func=cmd_test)

    p_int = sub.add_parser("int")
    p_int.add_argument("--change-id", required=True)
    p_int.add_argument("--result", required=True, choices=["success", "failed", "needs_human"])
    p_int.add_argument("--merge-commit", default="")
    p_int.add_argument("--conflicts", nargs="*")
    p_int.add_argument("--resolution", default="")
    p_int.add_argument("--build", default="pass")
    p_int.add_argument("--tests", default="pass")
    p_int.add_argument("--semantic", default="pass")
    p_int.add_argument("--summary", required=True)
    p_int.add_argument("--related", nargs="*")
    p_int.set_defaults(func=cmd_int)

    p_blk = sub.add_parser("blocker")
    p_blk.add_argument("--summary", required=True)
    p_blk.add_argument("--change-id", default="")
    p_blk.add_argument("--action", required=True)
    p_blk.set_defaults(func=cmd_blocker)

    p_fc = sub.add_parser("final-candidate")
    p_fc.add_argument("--summary", required=True)
    p_fc.add_argument("--changes", required=True)
    p_fc.add_argument("--validation", required=True)
    p_fc.add_argument("--limitations", default="")
    p_fc.set_defaults(func=cmd_final_candidate)

    p_fn = sub.add_parser("final-confirm")
    p_fn.add_argument("--limitations", default="")
    p_fn.set_defaults(func=cmd_final_confirm)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()