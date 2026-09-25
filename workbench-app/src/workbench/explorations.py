"""Explorations (release 2) — branches that run a program forward from one
changed interview answer without touching the official record.

Design note: "Explorations — design note (release 2)", agreed 25 Sep 2026; ADR-019.

* A branch lives INSIDE its program: programs/<pid>/explorations/<xid>/ with
  the same governed/restricted layout, plus branch.json. The server addresses
  it as "<pid>~x-<xid>"; "~" can never occur in a program id, so every
  existing endpoint works inside a branch unchanged.
* A branch copies only what the changed answer does not affect.
* Its decisions go to its own log, numbered EX-<XID>-###; its ratifications
  are typed exploration_ratification; its documents carry a banner.
* It never reaches the program's packages (they only walk governed/ and
  restricted/), and it joins the official record only through promotion,
  which creates a NEW official program (the ADR-007 pattern).
"""
from __future__ import annotations

import json
import shutil
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SEP = "~x-"
BANNER = "EXPLORATION — not part of the official record"

# Which interview stage restarts where. S5 (objectives, priorities) only feeds
# the Mandate, so a redesign program keeps its corpus, blueprint and Refactor
# work; every other stage can move the scope, so the Purpose Statement is
# re-drafted and the corpus is offered back as an unfrozen draft.
RESTART = {"S1": "purpose", "S2": "purpose", "S3": "purpose", "S4": "purpose", "S5": "mandate", "S6": "purpose"}

# Model tasks each restart re-runs (for the cost preview).
TASKS_PURPOSE = ["purpose_synthesis", "mandate_synthesis"]
TASKS_DISTILL = ["distill_extract", "distill_focus", "defect_detect", "blueprint_summary"]
TASKS_REFACTOR = ["operation_propose", "effect_classify_assist"]
TASKS_REDESIGN = ["misalign_detect", "redesign_propose", "target_summary"]


class ExplorationError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text()) if p.exists() else default
    except ValueError:
        return default


# ---------------------------------------------------------------- addressing

def split_id(program_id: str) -> tuple[str, Optional[str]]:
    if SEP in program_id:
        parent, xid = program_id.split(SEP, 1)
        return parent, xid
    return program_id, None


def branch_dir(root: Path, parent_id: str, xid: str) -> Path:
    return Path(root) / "programs" / parent_id / "explorations" / xid


def is_branch(program_dir: str | Path) -> bool:
    p = Path(program_dir)
    return p.parent.name == "explorations" and (p / "branch.json").exists()


def info(program_dir: str | Path) -> Optional[dict]:
    p = Path(program_dir)
    return _load(p / "branch.json") if is_branch(p) else None


def label(xid: str) -> str:
    return "Exploration " + xid.upper()


def entry_prefix(program_dir: str | Path) -> str:
    b = info(program_dir)
    return f"EX-{b['branch_id'].upper()}" if b else "DL"


# ---------------------------------------------------------------- helpers

def _answers(ps: dict) -> list[dict]:
    return ((ps or {}).get("interview") or {}).get("answers") or []


def _find_answer(ps: dict, answer_id: str) -> dict:
    for a in _answers(ps):
        if a.get("answer_id") == answer_id:
            return a
    raise ExplorationError(404, f"No recorded answer '{answer_id}' in the Purpose Statement")


def _next_xid(parent_dir: Path) -> str:
    base = parent_dir / "explorations"
    taken = {p.name for p in base.iterdir()} if base.is_dir() else set()
    letters = string.ascii_lowercase
    for n in range(1, 4):
        for i in range(len(letters) ** n):
            s, k = "", i
            for _ in range(n):
                s = letters[k % 26] + s
                k //= 26
            if s not in taken:
                return s
    raise ExplorationError(409, "Too many explorations on this program")


def _log(parent_dir: Path, event: dict) -> None:
    base = parent_dir / "explorations"
    base.mkdir(parents=True, exist_ok=True)
    with (base / "explorations.log.jsonl").open("a") as f:
        f.write(json.dumps({"timestamp": _now(), **event}, sort_keys=True) + "\n")


def _mode(ps: dict) -> str:
    return (((ps or {}).get("synthesis") or {}).get("recommended_mode") or {}).get("mode") or ""


def restart_for(parent_dir: Path, ps: dict, stage: str) -> str:
    r = RESTART.get(stage, "purpose")
    if r == "mandate" and not (_mode(ps) == "redesign"):
        r = "purpose"          # a refactor program has no Mandate: S5 moves the Purpose itself
    return r


def _last_dl(program_dir: Path) -> Optional[str]:
    log = Path(program_dir) / "governed" / "decisions.log.jsonl"
    if not log.exists():
        return None
    last = None
    for line in log.read_text().splitlines():
        if line.strip():
            try:
                last = json.loads(line).get("entry_id") or last
            except ValueError:
                pass
    return last


def _spend(stamps: list[dict], program_id: str, tasks: Optional[list[str]] = None) -> float:
    total = 0.0
    for s in stamps:
        if s.get("program_id") != program_id:
            continue
        t = s.get("task_id") or s.get("task")
        if tasks is None or t in tasks:
            total += (s.get("cost") or {}).get("usd", 0.0) or 0.0
    return round(total, 2)


# ---------------------------------------------------------------- impact preview

def impact(parent_dir: Path, parent_id: str, answer_id: str, stamps: list[dict],
           reuse_blueprint: bool = False) -> dict:
    """What changing one answer re-runs, what it reuses, and what it may cost,
    from what the same steps cost this program the first time (re-runs included,
    so the estimate is an upper bound)."""
    g = parent_dir / "governed"
    ps = _load(g / "purpose_statement.json")
    if not ps:
        raise ExplorationError(409, "This program has no Purpose Statement yet, so there is no answer to change")
    a = _find_answer(ps, answer_id)
    stage = a.get("stage") or ""
    restart = restart_for(parent_dir, ps, stage)
    has = lambda rel: (g / rel).exists()
    if restart == "mandate":
        reused = ["Source corpus (frozen)", "Derived Blueprint", "Defect Register"]
        if has("registers/operations.json"):
            reused.append("Refactor decisions so far")
        if has("refactored_baseline.json"):
            reused.append("Refactored baseline")
        reruns = ["Purpose Statement (re-drafted, then ratified inside the exploration)", "Mandate", "Redesign",
                  "Target blueprint", "Align"]
        tasks = TASKS_PURPOSE + TASKS_REDESIGN
        changes = "Objectives and their priority order, which feed the Mandate."
    else:
        reused = ["Source corpus as a starting draft (unfrozen, texts kept)"]
        reruns = ["Purpose Statement (re-drafted, then ratified inside the exploration)", "Source corpus (re-frozen)"]
        tasks = list(TASKS_PURPOSE)
        if reuse_blueprint:
            reused.append("Derived Blueprint and defects, as-is (may miss what the new scope brings in)")
        else:
            reruns.append("Distill (extraction and defect detection)")
            tasks += TASKS_DISTILL
        reruns += ["Refactor"] + (["Redesign"] if _mode(ps) == "redesign" else []) + ["Target blueprint", "Align"]
        tasks += TASKS_REFACTOR + TASKS_REDESIGN
        changes = ("Scope boundaries: which regimes are in or out." if stage == "S6"
                   else "Potentially the mode, the scope sentence and the decision served.")
    est = _spend(stamps, parent_id, tasks)
    return {"answer": a, "stage": stage, "restart": restart, "changes": changes, "reused": reused,
            "reruns": reruns, "estimate_usd": est,
            "estimate_basis": ("What these steps have cost this program so far, re-runs included. "
                               "Steps it has not reached yet are not counted.")}


# ---------------------------------------------------------------- create

def create(root: Path, parent_dir: Path, parent_id: str, *, name: str, answer_id: str, new_answer: str,
           created_by: dict, reuse_blueprint: bool = False) -> dict:
    if SEP in parent_id:
        raise ExplorationError(400, "Explorations branch from an official program, not from another exploration")
    new_answer = (new_answer or "").strip()
    if not new_answer:
        raise ExplorationError(400, "Give the other answer the exploration should use")
    g = parent_dir / "governed"
    ps = _load(g / "purpose_statement.json")
    if not ps:
        raise ExplorationError(409, "This program has no Purpose Statement yet, so there is no answer to change")
    a = _find_answer(ps, answer_id)
    if new_answer == (a.get("verbatim") or "").strip():
        raise ExplorationError(400, "That is the same as the recorded answer")
    stage = a.get("stage") or ""
    restart = restart_for(parent_dir, ps, stage)

    xid = _next_xid(parent_dir)
    bdir = branch_dir(root, parent_id, xid)
    bg, br = bdir / "governed", bdir / "restricted"
    bg.mkdir(parents=True)
    br.mkdir(parents=True)

    # transcript + the changed answer, as a marked turn the synthesizer reads
    history = _load(parent_dir / "restricted" / "interview.json", []) or []
    if not isinstance(history, list):
        history = []
    history = list(history) + [{"role": "user", "content": (
        f"[EXPLORATION {xid.upper()}] For this exploration, my answer to “{a.get('question', '')}” "
        f"({answer_id}) is: {new_answer}\n\nThis replaces my earlier answer: “{a.get('verbatim', '')}”. "
        "Carry the consequences of this change through everything else I said.")}]
    (br / "interview.json").write_text(json.dumps(history, indent=2))

    # same pinned models as the parent, so differences come from the answer alone
    if (g / "model_policy.json").exists():
        pol = json.loads((g / "model_policy.json").read_text())
        pol["program_id"] = f"{parent_id}{SEP}{xid}"
        (bg / "model_policy.json").write_text(json.dumps(pol, indent=2))

    def cp(rel: str):
        src, dst = g / rel, bg / rel
        if src.is_dir():
            shutil.copytree(src, dst)
        elif src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)

    if restart == "mandate":
        for rel in ("manifest", "corpus_texts", "excluded_sources.json", "blueprint", "blueprint_summary.json",
                    "registers", "refactored_baseline.json"):
            cp(rel)
    else:
        cp("manifest")
        cp("corpus_texts")
        cp("excluded_sources.json")
        man = bg / "manifest" / "manifest.json"
        if man.exists():                     # back to an unfrozen draft: the new scope may change it
            m = json.loads(man.read_text())
            m.update({"frozen": False, "frozen_at": None, "content_hash": None,
                      "program_id": f"{parent_id}{SEP}{xid}"})
            man.write_text(json.dumps(m, indent=2))
            (bg / "manifest" / "manifest.sha256").unlink(missing_ok=True)
        if reuse_blueprint:
            cp("blueprint")
            cp("blueprint_summary.json")
            if (g / "registers" / "defects.json").exists():
                (bg / "registers").mkdir(exist_ok=True)
                shutil.copy(g / "registers" / "defects.json", bg / "registers" / "defects.json")

    doc = {"branch_id": xid, "label": label(xid), "name": (name or "").strip() or f"{answer_id}: another answer",
           "parent": parent_id, "based_on": _last_dl(parent_dir),
           "changed": {"answer_id": answer_id, "stage": stage, "question": a.get("question", ""),
                       "old": a.get("verbatim", ""), "new": new_answer},
           "restart": restart, "reuse_blueprint": bool(reuse_blueprint),
           "created_by": created_by, "created_at": _now(), "status": "active"}
    (bdir / "branch.json").write_text(json.dumps(doc, indent=2))
    _log(parent_dir, {"event": "created", "branch_id": xid, "by": created_by, "answer_id": answer_id})
    return {**doc, "program_id": f"{parent_id}{SEP}{xid}"}


def after_freeze(program_dir: Path, new_hash: str) -> None:
    """When a branch re-freezes its corpus: carry the captured texts over to the new
    corpus identity, and drop a reused blueprint if the corpus actually changed (the
    distiller refuses to mix extractions from two different corpora)."""
    p = Path(program_dir)
    if not is_branch(p):
        return
    g = p / "governed"
    acq = g / "corpus_texts" / "acquisition.json"
    if acq.exists():
        reg = _load(acq, {}) or {}
        if reg.get("manifest_hash") != new_hash:
            items = {i["item_id"] for i in (_load(g / "manifest" / "manifest.json", {}) or {}).get("items", [])}
            reg["manifest_hash"] = new_hash
            reg["items"] = {k: v for k, v in (reg.get("items") or {}).items() if k in items}
            acq.write_text(json.dumps(reg, indent=2))
    ext = g / "blueprint" / "extraction_register.json"
    if ext.exists() and (_load(ext, {}) or {}).get("manifest_hash") != new_hash:
        shutil.rmtree(g / "blueprint", ignore_errors=True)
        (g / "blueprint_summary.json").unlink(missing_ok=True)
        (g / "registers" / "defects.json").unlink(missing_ok=True)


# ---------------------------------------------------------------- read

def _metrics(program_dir: Path) -> dict:
    g = Path(program_dir) / "governed"
    ps = _load(g / "purpose_statement.json") or {}
    man = _load(g / "manifest" / "manifest.json") or {}
    excl = set(((_load(g / "excluded_sources.json") or {}).get("items") or {}).keys())
    obl = dfn = 0
    bdir = g / "blueprint"
    if bdir.is_dir():
        for f in bdir.glob("*.json"):
            if f.name == "extraction_register.json":
                continue
            d = _load(f, {}) or {}
            obl += len(d.get("obligations") or [])
            dfn += len(d.get("definitions") or [])
    runs = ((_load(g / "registers" / "defects.json") or {}).get("runs") or {})
    ops = ((_load(g / "registers" / "operations.json") or {}).get("operations") or {})
    status = {}
    for op in ops.values():
        status[op.get("status")] = status.get(op.get("status"), 0) + 1
    tb = _load(g / "target_blueprint.json")
    return {
        "mode": _mode(ps) or None,
        "purpose_status": ps.get("status"),
        "scope": (((ps.get("synthesis") or {}).get("scope_sentence") or {}).get("text")),
        "sources_in_use": (len([i for i in man.get("items", []) if i["item_id"] not in excl]) if man else None),
        "corpus_frozen": bool(man.get("frozen")) if man else None,
        "obligations": obl if bdir.is_dir() else None,
        "definitions": dfn if bdir.is_dir() else None,
        "defects": sum(len(r.get("findings") or []) for r in runs.values()) if runs else None,
        "proposals_finalized": status.get("finalized") if ops else None,
        "proposals_parked": status.get("parked") if ops else None,
        "target_blueprint": bool(tb),
        "target_operations": len((tb or {}).get("operation_trace") or []) if tb else None,
    }


def listing(root: Path, parent_dir: Path, parent_id: str, stamps: list[dict], include_archived: bool = False) -> list[dict]:
    base = parent_dir / "explorations"
    out = []
    if not base.is_dir():
        return out
    current = _last_dl(parent_dir)
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        b = _load(d / "branch.json")
        if not b or (b.get("status") != "active" and not include_archived):
            continue
        pid = f"{parent_id}{SEP}{b['branch_id']}"
        out.append({**b, "program_id": pid, "spend_usd": _spend(stamps, pid),
                    "decisions": len([l for l in ((d / "governed" / "decisions.log.jsonl").read_text().splitlines()
                                                  if (d / "governed" / "decisions.log.jsonl").exists() else []) if l.strip()]),
                    "official_now_at": current, "stale": bool(current) and current != b.get("based_on"),
                    "metrics": _metrics(d)})
    return out


def compare(parent_dir: Path, bdir: Path) -> dict:
    return {"official": _metrics(parent_dir), "branch": _metrics(bdir), "branch_info": _load(bdir / "branch.json")}


# ---------------------------------------------------------------- archive / promote

def archive(parent_dir: Path, xid: str, by: dict) -> dict:
    bdir = parent_dir / "explorations" / xid
    b = _load(bdir / "branch.json")
    if not b:
        raise ExplorationError(404, f"No exploration '{xid}'")
    b["status"] = "archived"
    b["archived_at"], b["archived_by"] = _now(), by
    (bdir / "branch.json").write_text(json.dumps(b, indent=2))
    _log(parent_dir, {"event": "archived", "branch_id": xid, "by": by})
    return b


def promote(root: Path, parent_dir: Path, parent_id: str, xid: str, new_id: str, *, by: dict,
            rationale: str, append_decision, next_entry_id) -> dict:
    """Copy the branch into a NEW official program. Provisional ratifications are
    reset; the branch's log is kept beside the new program's (empty) official log as
    evidence; one decision is written in each program's official log."""
    bdir = parent_dir / "explorations" / xid
    b = _load(bdir / "branch.json")
    if not b:
        raise ExplorationError(404, f"No exploration '{xid}'")
    if b.get("status") == "promoted":
        raise ExplorationError(409, f"{label(xid)} was already promoted to {b.get('promoted_to')}")
    if not (rationale or "").strip():
        raise ExplorationError(400, "Give a rationale for promoting this exploration")
    ndir = Path(root) / "programs" / new_id
    if ndir.exists():
        raise ExplorationError(409, f"A program called {new_id} already exists")
    shutil.copytree(bdir, ndir, ignore=shutil.ignore_patterns("branch.json"))
    g = ndir / "governed"
    # the branch's own log becomes history; the new program's official log starts fresh
    log = g / "decisions.log.jsonl"
    if log.exists():
        log.rename(g / "exploration_history.jsonl")
    (g / "promoted_from.json").write_text(json.dumps({**b, "promoted_at": _now(), "promoted_by": by,
                                                       "rationale": rationale}, indent=2))
    # reset provisional ratifications: the Program Owner re-ratifies officially
    ps_p = g / "purpose_statement.json"
    if ps_p.exists():
        ps = json.loads(ps_p.read_text())
        ps["program_id"] = new_id
        ps["status"] = "awaiting_ratification"
        ps["ratification"] = {"status": "awaiting_ratification"}
        ps_p.write_text(json.dumps(ps, indent=2))
    for rel in ("refactored_baseline.json", "ratified_mandate.json", "target_blueprint.json",
                "target_blueprint.html", "crosswalk.html", "registers/invariants.json"):
        (g / rel).unlink(missing_ok=True)
    pol_p = g / "model_policy.json"
    if pol_p.exists():
        pol = json.loads(pol_p.read_text())
        pol["program_id"] = new_id
        pol_p.write_text(json.dumps(pol, indent=2))
    man_p = g / "manifest" / "manifest.json"
    if man_p.exists():
        m = json.loads(man_p.read_text())
        m["program_id"] = new_id
        man_p.write_text(json.dumps(m, indent=2))
    now = _now()
    append_decision(ndir, {
        "entry_id": next_entry_id(ndir), "timestamp": now, "type": "other", "artifact": "promoted_from.json",
        "decided_by": by, "decision": f"Program created by promoting {label(xid)} of {parent_id} "
                                      f"(changed answer {b['changed']['answer_id']}). Steps must be re-ratified.",
        "rationale": rationale})
    append_decision(parent_dir, {
        "entry_id": next_entry_id(parent_dir), "timestamp": now, "type": "other", "artifact": f"explorations/{xid}",
        "decided_by": by, "decision": f"{label(xid)} promoted to a new official program, {new_id}. "
                                      "This program is unchanged.",
        "rationale": rationale})
    b.update({"status": "promoted", "promoted_to": new_id, "promoted_at": now, "promoted_by": by})
    (bdir / "branch.json").write_text(json.dumps(b, indent=2))
    _log(parent_dir, {"event": "promoted", "branch_id": xid, "by": by, "to": new_id})
    return {"program_id": new_id, "promoted_from": f"{parent_id}{SEP}{xid}"}
