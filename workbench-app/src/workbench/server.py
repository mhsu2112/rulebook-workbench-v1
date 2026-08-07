"""FastAPI app for the workbench prototype.

M1 scope (PRD spec/40 §7/§10): P0 in software — interview chat running the
purpose-elicitation skill verbatim (D5), typed purpose synthesis, and the ⚖
ratification workflow with the append-only decision log. Plus the model
settings endpoints (the per-task toggle).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Document upload needs python-multipart; FastAPI validates Form/File routes at
# app-build time, so registering them when the package is absent crashes the
# WHOLE app on startup. Guard on it: with the package, the real upload endpoints
# load; without it, lightweight stubs return a clear 503 and the rest of the app
# runs normally.
_HAS_MULTIPART = (importlib.util.find_spec("multipart") is not None
                  or importlib.util.find_spec("python_multipart") is not None)

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import acquire, crosswalk as crosswalk_mod, discover as discover_mod, distill, manifest, package as package_mod, policy as policy_mod, presets as presets_mod, programs_admin, redesign as redesign_mod, refactor as refactor_mod, render, storage
from .config import load_registry
from .router import (
    DiversityViolationError,
    ModelRouter,
    RouterError,
    SensitiveTaskPolicyError,
    StructuredOutputError,
)

SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
COMPLETE_MARKER = "[INTERVIEW-COMPLETE]"


def load_dotenv(root: Path) -> None:
    """Load KEY=value lines from <root>/.env into the environment.

    Real environment variables win; the file only fills gaps. Keeps the app
    usable by non-developers who created .env per SETUP.md and expect
    `make app` to just work."""
    env = root / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value

INTERVIEW_SYSTEM = """You are the Rulebook Workbench's Phase 0 purpose-elicitation interviewer,
speaking with a respondent inside the workbench app. Follow the skill
instructions below exactly: transcript notice, the respondent's NAME and
capacity first (ask for the actual name — role provenance needs it), one
question per turn, options with implications, echo the draft scope
sentence early, run the kill tests in front of the respondent, and never
record objectives from a non-Principal as adopted (they are hypotheses).
When — and only when — the interview is complete through S6 and the kill
tests, end your final message with the marker {marker} on its own line.

===== SKILL (verbatim, D5) =====
{skill}
"""

SYNTHESIS_PROMPT = """Below is the verbatim transcript of a purpose-elicitation interview
conducted in the Rulebook Workbench. Produce the typed PurposeStatement JSON
object conforming exactly to the response schema. Rules: verbatim answers go
in interview.answers with stable answer IDs; every synthesized conclusion
cites basis_answer_ids; the mode recommendation cites the discriminating
answers; roles stay distinct (respondent is not principal unless the
transcript verifies authority — otherwise principal is null); open items are
typed with blocking flags (a missing principal in redesign mode is always
blocking); ratification.status is "awaiting_ratification"; status is
"awaiting_ratification". Use people's ACTUAL names where the transcript
states them — never invent placeholder names; if a name was not captured,
use "UNRECORDED" and add a non-blocking open item. Set mandate_hypotheses_ref
to the string "PENDING" if the transcript contains Mandate-seed material
(S5: objectives, tradeoffs, constraints), else null — the workbench, not
you, decides the file path.

program_id: {program_id}
transcript_ref: {transcript_ref}

===== TRANSCRIPT =====
{transcript}
"""

MANDATE_PROMPT = """From the interview transcript below, produce the typed MandateHypotheses
JSON object conforming exactly to the response schema. ADR-006 rules:
status is "hypothesis"; principal is null; every objective's adoption is
null; every objective and ranking carries attribution to its actual source
in the transcript (respondent_view unless the respondent cited an
authority document or statute); pairs the respondent declined to rank are
open_tradeoffs, not rankings; constraint claims are verified:false unless
the transcript contains a checked citation. Objectives are outcome-level:
compress mechanism language out, exactly as the interviewer's confirmed
echo did if one exists.

program_id: {program_id}

===== TRANSCRIPT =====
{transcript}
"""


DISCOVERY_PROMPT = """You are helping assemble the CORPUS for a regulatory-consolidation program:
the set of primary legal sources (statutes, regulations, and binding/authoritative agency
guidance) in scope. You are PROPOSING candidates for a human to review — you are NOT deciding
the corpus, and nothing you return enters it until a person accepts it.

FIRST identify the JURISDICTION(S) in scope from the Purpose Statement (e.g. United States, United
Kingdom, European Union, or another country) and propose sources IN THE RIGHT LEGAL SYSTEM — do not
default to US law unless the scope is US. Include cross-cutting sources a keyword search would miss.
Prefer citable primary law.

For each candidate give the most precise locator AND an official full-text URL you can:
- United States: cfr_locator "<title> CFR Part <part>" for regulations; usc_locator
  "<title> U.S.C. <section>" for statutes.
- United Kingdom: put the citation in `locator` (e.g. "UK EMIR art. 9", "FSMA 2000 s.137") and set
  `url` to the legislation.gov.uk page (e.g. https://www.legislation.gov.uk/eur/2012/648).
- European Union: put the citation in `locator` (e.g. "Regulation (EU) 2019/834 art. 9") and set
  `url` to the EUR-Lex page.
- Any other jurisdiction / agency guidance: put the citation in `locator` and set `url` to the
  issuing authority's OFFICIAL page for the document.
Always give issuer (the agency, department, or legislature), a short family label
(statute / regulation / guidance / …), and a one-line rationale for why it is in scope.

For non-US sources ALWAYS provide a `url` — that is how the source is verified and later fetched.
Do NOT invent citations or URLs: if unsure of an exact identifier, omit it and describe the document
in the title/rationale so a human can find it. Every locator/URL you give is machine-checked (US
citations against the live catalog; other URLs by resolving them), and unverifiable ones are
flagged, not hidden. Return 8–20 candidates.

Search hints from the user: {terms}

===== RATIFIED PURPOSE STATEMENT (scope) =====
{purpose}
"""


DISCOVERY_QUESTIONS_PROMPT = """A user is about to run assisted source discovery to help assemble the CORPUS
for the regulatory-consolidation program below. Before proposing sources, ask up to THREE short
clarifying questions that would most sharpen the search — e.g. which agencies are in vs. out of
scope, whether to include binding guidance and manuals or only statutes/regulations, whether to
surface proposed/pending rules as "not yet law", and time/jurisdiction boundaries. Base them on
this program's actual scope; skip anything already clear from the Purpose Statement. Return ONLY
the questions, one per line, no numbering or preamble.

===== RATIFIED PURPOSE STATEMENT (scope) =====
{purpose}
"""


class ServerState:
    def __init__(self, root: Path, transport=None, api_key: Optional[str] = None):
        self.root = root
        self.registry = load_registry(root / "models.yaml")
        self.overrides_path = root / "overrides.json"
        user_overrides = {}
        if self.overrides_path.exists():
            user_overrides = json.loads(self.overrides_path.read_text())
        self.router = ModelRouter(
            registry=self.registry, transport=transport, api_key=api_key,
            user_overrides=user_overrides,
        )
        self.skill_text = self._find_skill()

    def _find_skill(self) -> str:
        candidates = [
            self.root.parent / "rulebook-workbench" / "skills" / "purpose-elicitation" / "SKILL.md",
            self.root / "skills" / "purpose-elicitation" / "SKILL.md",
        ]
        for c in candidates:
            if c.exists():
                return c.read_text()
        raise FileNotFoundError(
            "purpose-elicitation SKILL.md not found — expected the rulebook-workbench "
            "repo beside this one (see PRD D5: the skill runs verbatim)"
        )

    def save_overrides(self) -> None:
        self.overrides_path.write_text(json.dumps(self.router.user_overrides, indent=2))

    # -------- program helpers --------

    def pdir(self, program_id: str) -> Path:
        d = self.root / "programs" / program_id
        if not d.is_dir():
            raise HTTPException(404, f"Unknown program '{program_id}'")
        return d

    def interview_path(self, program_id: str) -> Path:
        return self.pdir(program_id) / "restricted" / "interview.json"  # ADR-016: transcripts are restricted

    def history(self, program_id: str) -> list[dict]:
        p = self.interview_path(program_id)
        return json.loads(p.read_text()) if p.exists() else []


class ProgramIn(BaseModel):
    program_id: str


class MessageIn(BaseModel):
    message: str


class RatifyIn(BaseModel):
    name: str
    role: str
    rationale: str


class OverrideIn(BaseModel):
    task_id: str
    model: Optional[str] = None  # null clears the override


class SliceIn(BaseModel):
    slice_id: str


class ManifestItemIn(BaseModel):
    item_id: str
    title: str
    issuer: str
    family: str
    status: str = "live"
    locator: str
    url: Optional[str] = None
    evidence_role: Optional[str] = None
    note: Optional[str] = None


class DiscoverIn(BaseModel):
    terms: str = ""
    qa: str = ""          # optional mini-interview Q&A, folded into the prompt (spec/54 §2.2)


class RenameIn(BaseModel):
    new_id: str


class PresetIn(BaseModel):
    preset: str
    lab: Optional[str] = None


class PolicySetIn(BaseModel):
    preset: str
    lab: Optional[str] = None


class PolicyRatifyIn(BaseModel):
    name: str
    role: str = "Program Owner"
    rationale: str


class AcquireIn(BaseModel):
    limit: int = 8
    retry_errors: bool = False


class UrlOverrideIn(BaseModel):
    item_id: str
    url: str = ""


class ExcludeIn(BaseModel):
    item_id: str
    reason: str = ""
    undo: bool = False


class ProposeIn(BaseModel):
    limit: int = 4
    retry_errors: bool = False


class DispositionIn(BaseModel):
    name: str
    role: str
    action: str
    effect_class: str
    rationale: str
    modified_proposal: Optional[str] = None


class RefactorRatifyIn(BaseModel):
    name: str
    role: str
    rationale: str


class CharterIn(BaseModel):
    successor_id: str


class MandateDecision(BaseModel):
    objective_id: str
    action: str
    rationale: str
    amended_statement: Optional[str] = None


class MandateRatifyIn(BaseModel):
    name: str
    role: str
    decisions: list[MandateDecision]
    ranking: list[str]
    constraints: list[str] = []
    rationale: str


class BacklogDispositionIn(BaseModel):
    name: str
    role: str
    action: str
    rationale: str
    objective_id: Optional[str] = None


class RedesignRatifyIn(BaseModel):
    name: str
    role: str
    rationale: str
    deferred_objectives: list[dict] = []


class DefectRunIn(BaseModel):
    family: Optional[str] = None  # null -> cross-corpus pass


# ---- ledger phase maps (spec/55 §5): which tasks / decisions / transcripts
# belong to each middle-panel tab, for the contextual read-only ledger.
LEDGER_PHASE_TASKS = {
    "purpose": ["intake_interview", "purpose_synthesis", "mandate_synthesis"],
    "corpus": ["source_discovery", "discovery_questions", "second_census"],
    "blueprint": ["distill_extract", "distill_focus", "claim_verify", "defect_detect", "blueprint_summary"],
    "refactor": ["operation_propose", "effect_classify_assist"],
    "redesign": ["misalign_detect", "redesign_propose", "target_summary"],
    "target": ["target_summary"],
}
LEDGER_PHASE_TRANSCRIPTS = {
    "purpose": ["interview.json"],
    "corpus": ["discovery_interview.json"],
}


def _decision_phase(entry: dict) -> str:
    a = (entry.get("artifact") or "")
    t = entry.get("type") or ""
    if "model_policy" in a:
        return "setup"
    if "purpose_statement" in a:
        return "purpose"
    if "manifest" in a or t == "manifest_freeze":
        return "corpus"
    if "redesign" in a:
        return "redesign"
    if "refactor" in a or t == "disposition":
        return "refactor"
    return "overview"


def create_app(root: Optional[str | Path] = None, transport=None, api_key: Optional[str] = None) -> FastAPI:
    root = Path(root or os.environ.get("WORKBENCH_ROOT") or Path(__file__).resolve().parents[2])
    load_dotenv(root)
    state = ServerState(root, transport=transport, api_key=api_key)
    app = FastAPI(title="Rulebook Workbench", version="0.1 (M1)")
    app.state.wb = state  # test hook

    def _router_call(task_id: str, messages: list[dict], pid: Optional[str] = None):
        # A program's model choices are its ratified policy (spec/55 §4): inject
        # them as program-scoped overrides for this call so provenance flows from
        # the decision. Restore afterward so calls never leak across programs.
        prev_overrides = state.router.program_overrides
        if pid:
            try:
                state.router.program_overrides = policy_mod.load(state.pdir(pid), pid).get("overrides") or {}
            except Exception:  # noqa: BLE001 — a missing/bad policy just means defaults
                state.router.program_overrides = prev_overrides
        try:
            out, stamp = state.router.call(task_id, messages)
            runs = state.root / "runs"
            runs.mkdir(exist_ok=True)
            with (runs / "stamps.jsonl").open("a") as f:
                f.write(json.dumps({**stamp, "program_id": pid}) + "\n")
            return out, stamp
        except SensitiveTaskPolicyError as e:
            raise HTTPException(503, f"Privacy fail-closed (ADR-016): {e}")
        except DiversityViolationError as e:
            raise HTTPException(409, f"Model diversity rule (G5): {e}")
        except StructuredOutputError as e:
            raise HTTPException(502, f"Structured output failed validation: {e}")
        except RouterError as e:
            raise HTTPException(502, str(e))
        finally:
            state.router.program_overrides = prev_overrides

    # ---------------- programs ----------------

    @app.post("/api/programs")
    def create_program(body: ProgramIn):
        if not SLUG.match(body.program_id):
            raise HTTPException(400, "program_id must be a lowercase slug (a-z, 0-9, -, _)")
        storage.init_program(state.root, body.program_id)
        return {"program_id": body.program_id}

    @app.get("/api/programs")
    def list_programs():
        return programs_admin.list_active(state.root)

    @app.get("/api/programs/archived")
    def list_archived():
        return programs_admin.list_archived(state.root)

    @app.post("/api/programs/{pid}/archive")
    def archive_program(pid: str):
        """'Delete' = archive, never destroy (spec/54 §2.4). The append-only
        decision log is preserved; the program is restorable."""
        try:
            return programs_admin.archive(state.root, pid)
        except programs_admin.AdminError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/programs/{pid}/restore")
    def restore_program(pid: str):
        try:
            return programs_admin.restore(state.root, pid)
        except programs_admin.AdminError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/programs/{pid}/rename")
    def rename_program(pid: str, body: RenameIn):
        """Safe rename: moves the folder, repoints program_id in artifacts and
        provenance stamps (exact match), logs the change (spec/54 §2.4)."""
        try:
            return programs_admin.rename(state.root, pid, body.new_id)
        except programs_admin.AdminError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/programs/{pid}/package")
    def download_package(pid: str):
        """One organized .zip of the whole program — readable documents, the full
        governed tree, decision log + manifest (csv), and the owner's restricted
        transcripts, clearly marked (spec/54 §2.3c, §2.5)."""
        pdir = state.pdir(pid)
        renders: dict[str, str] = {}
        # Best-effort rendering — a program missing a phase simply omits that doc.
        try:
            if any((pdir / "governed" / "blueprint").glob("*.json")):
                renders["derived-blueprint.html"] = render.render_blueprint(pdir, pid)
        except Exception:  # noqa: BLE001 — package is resilient to a missing render
            pass
        try:
            if (pdir / "governed" / "target_blueprint.json").exists():
                renders["target-blueprint.html"] = render.render_target_blueprint(pdir, pid)
                renders["crosswalk.html"] = _crosswalker(pid).render()
        except Exception:  # noqa: BLE001
            pass
        data = package_mod.build(pdir, pid, renders=renders, manifest_doc=manifest.load(pdir))
        return Response(content=data, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{pid}-package.zip"'})

    # ---------------- interview (P0.1) ----------------

    @app.get("/api/programs/{pid}/interview")
    def get_interview(pid: str):
        return state.history(pid)

    @app.post("/api/programs/{pid}/interview")
    def post_interview(pid: str, body: MessageIn):
        history = state.history(pid)
        system = INTERVIEW_SYSTEM.format(marker=COMPLETE_MARKER, skill=state.skill_text)
        messages = ([{"role": "system", "content": system}]
                    + history + [{"role": "user", "content": body.message}])
        reply, stamp = _router_call("intake_interview", messages, pid=pid)
        history += [{"role": "user", "content": body.message},
                    {"role": "assistant", "content": reply}]
        p = state.interview_path(pid)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(history, indent=2))
        return {
            "reply": reply,
            "complete": COMPLETE_MARKER in reply,
            "model_served": stamp["model_served"],
            "cost_usd": stamp["cost"]["usd"],
        }

    # ---------------- synthesis (typed Purpose Statement) ----------------

    @app.post("/api/programs/{pid}/synthesize")
    def synthesize(pid: str):
        history = state.history(pid)
        if not history:
            raise HTTPException(400, "No interview transcript to synthesize from")
        # A ratified Purpose Statement is a governed artifact — re-synthesizing
        # must NOT silently overwrite it and reset it to awaiting_ratification
        # (that un-ratifies it and hides the Corpus tab and everything after).
        pp = state.pdir(pid) / "governed" / "purpose_statement.json"
        if pp.exists() and json.loads(pp.read_text()).get("status") == "ratified":
            raise HTTPException(409, "This program's Purpose Statement is already ratified. "
                "Re-synthesizing would overwrite and silently un-ratify it, so it is blocked. "
                "The ratified purpose is protected; revise it through an explicit revision, not re-synthesis.")
        transcript = "\n\n".join(f"[{m['role'].upper()}]\n{m['content']}" for m in history)
        transcript_ref = f"programs/{pid}/restricted/interview.json"
        prompt = SYNTHESIS_PROMPT.format(program_id=pid, transcript_ref=transcript_ref,
                                         transcript=transcript)
        doc, stamp = _router_call("purpose_synthesis", [{"role": "user", "content": prompt}], pid=pid)
        # Derivational normalization (kept schema-valid):
        doc["program_id"] = pid
        doc["interview"]["transcript_ref"] = transcript_ref
        doc["status"] = "awaiting_ratification"
        doc["ratification"] = {"status": "awaiting_ratification", "ratified_by": None}
        cost = stamp["cost"]["usd"]

        # Mandate-seed material present → produce the referenced artifact,
        # or null the ref. A reference to a file that doesn't exist is an
        # OR-3 violation; it never leaves this function dangling.
        if doc.get("mandate_hypotheses_ref"):
            mh_rel = f"programs/{pid}/restricted/mandate_hypotheses.json"
            try:
                mh, mh_stamp = _router_call("mandate_synthesis", [{"role": "user", "content":
                    MANDATE_PROMPT.format(program_id=pid, transcript=transcript)}], pid=pid)
                mh["program_id"] = pid
                mh["status"] = "hypothesis"
                for obj in mh.get("objectives", []):
                    obj["adoption"] = None  # ADR-006: nothing adopted at P0.1, ever
                mh["principal"] = None
                (state.pdir(pid) / "restricted" / "mandate_hypotheses.json").write_text(
                    json.dumps(mh, indent=2))
                doc["mandate_hypotheses_ref"] = mh_rel
                cost += mh_stamp["cost"]["usd"]
            except HTTPException as e:
                doc["mandate_hypotheses_ref"] = None
                doc.setdefault("open_items", []).append({
                    "item_id": f"OI-MH-{len(doc.get('open_items', [])) + 1}",
                    "description": f"Mandate-seed material exists in the transcript but hypotheses "
                                   f"extraction failed ({e.detail}); re-run synthesis or extract manually.",
                    "owner": "Program Owner", "blocking": False,
                    "resolves_via": "Re-synthesize",
                })

        out = state.pdir(pid) / "governed" / "purpose_statement.json"
        out.write_text(json.dumps(doc, indent=2))
        return {"purpose_statement": doc, "cost_usd": cost}

    @app.get("/api/programs/{pid}/purpose")
    def get_purpose(pid: str):
        p = state.pdir(pid) / "governed" / "purpose_statement.json"
        if not p.exists():
            raise HTTPException(404, "No purpose statement yet — synthesize first")
        return json.loads(p.read_text())

    # ---------------- ratification (⚖, OR-4 discipline) ----------------

    @app.post("/api/programs/{pid}/open-items/{item_id}/resolve")
    def resolve_open_item(pid: str, item_id: str, body: RatifyIn):
        """⚖ Resolve one open item — a logged human decision, not an edit."""
        if not body.name.strip() or not body.rationale.strip():
            raise HTTPException(400, "Resolving an open item requires your name and a rationale — both go to the Decision Log")
        p = state.pdir(pid) / "governed" / "purpose_statement.json"
        if not p.exists():
            raise HTTPException(404, "No purpose statement")
        doc = json.loads(p.read_text())
        if doc.get("status") == "ratified":
            raise HTTPException(409, "Already ratified — open items are frozen")
        for item in doc.get("open_items", []):
            if item.get("item_id") == item_id:
                if item.get("resolution"):
                    raise HTTPException(409, f"{item_id} already resolved")
                now = datetime.now(timezone.utc).isoformat()
                entry_id = f"DL-{len(storage.read_decisions(state.pdir(pid))) + 1:03d}"
                item["blocking"] = False
                item["resolution"] = {"by": body.name, "role": body.role, "timestamp": now,
                                      "rationale": body.rationale, "decision_log_ref": entry_id}
                storage.append_decision(state.pdir(pid), {
                    "entry_id": entry_id, "timestamp": now, "type": "disposition",
                    "artifact": "purpose_statement.json",
                    "decided_by": {"name": body.name, "role": body.role},
                    "decision": f"Resolve open item {item_id}: {item.get('description', '')[:120]}",
                    "rationale": body.rationale,
                })
                p.write_text(json.dumps(doc, indent=2))
                return doc
        raise HTTPException(404, f"Unknown open item '{item_id}'")

    @app.post("/api/programs/{pid}/ratify")
    def ratify(pid: str, body: RatifyIn):
        if body.role != "Program Owner":
            raise HTTPException(403, "Only the Program Owner may ratify a Purpose Statement")
        if not body.rationale.strip():
            raise HTTPException(400, "Ratification requires a rationale — it goes in the Decision Log")
        p = state.pdir(pid) / "governed" / "purpose_statement.json"
        if not p.exists():
            raise HTTPException(404, "No purpose statement to ratify")
        doc = json.loads(p.read_text())
        if doc.get("status") == "ratified":
            raise HTTPException(409, "Already ratified")
        blocking = [i.get("item_id", "?") for i in doc.get("open_items", []) if i.get("blocking")]
        if blocking:
            raise HTTPException(409, "Blocked by open items: " + ", ".join(blocking)
                                + " — resolve each (⚖, logged) before ratification")
        now = datetime.now(timezone.utc).isoformat()
        entry_id = f"DL-{len(storage.read_decisions(state.pdir(pid))) + 1:03d}"
        doc["status"] = "ratified"
        doc["ratification"] = {
            "status": "ratified",
            "ratified_by": {"name": body.name, "capacity": "Program Owner", "identity_verified": True},
            "timestamp": now,
            "decision_log_ref": entry_id,
            "rationale": body.rationale,
        }
        storage.append_decision(state.pdir(pid), {
            "entry_id": entry_id, "timestamp": now, "type": "ratification",
            "artifact": "purpose_statement.json",
            "artifact_version": doc.get("version", "0.1"),
            "decided_by": {"name": body.name, "role": body.role},
            "decision": f"Ratify Purpose Statement for {pid}",
            "rationale": body.rationale,
        })
        p.write_text(json.dumps(doc, indent=2))
        return doc

    # ---------------- manifest (P1: import → freeze) ----------------

    @app.get("/api/slices")
    def list_slices():
        d = state.root / "data"
        out = []
        if d.is_dir():
            for f in sorted(d.glob("*-slice.json")):
                doc = json.loads(f.read_text())
                out.append({"slice_id": doc.get("slice_id", f.stem), "items": len(doc.get("items", [])),
                            "source_note": (doc.get("source_note") or "")[:240]})
        return out

    @app.get("/api/programs/{pid}/manifest")
    def get_manifest(pid: str):
        doc = manifest.load(state.pdir(pid))
        if doc is None:
            raise HTTPException(404, "No manifest — import a corpus slice first")
        gaps_p = state.pdir(pid) / "governed" / "registers" / "gaps.json"
        gaps = json.loads(gaps_p.read_text()) if gaps_p.exists() else []
        return {**doc, "gaps": gaps}

    @app.post("/api/programs/{pid}/manifest/import")
    def import_manifest(pid: str, body: SliceIn):
        f = state.root / "data" / f"{body.slice_id}.json"
        if not f.exists():
            raise HTTPException(404, f"Unknown slice '{body.slice_id}'")
        try:
            doc = manifest.import_slice(state.pdir(pid), json.loads(f.read_text()), pid)
        except manifest.FrozenError as e:
            raise HTTPException(409, str(e))
        except manifest.ManifestError as e:
            raise HTTPException(400, str(e))
        return doc

    @app.post("/api/programs/{pid}/manifest/items")
    def add_manifest_item(pid: str, body: ManifestItemIn):
        """Build the corpus in-app: append one source to the unfrozen manifest."""
        try:
            return manifest.add_item(state.pdir(pid), body.model_dump(exclude_none=True), pid)
        except manifest.FrozenError as e:
            raise HTTPException(409, str(e))
        except manifest.ManifestError as e:
            raise HTTPException(400, str(e))

    @app.delete("/api/programs/{pid}/manifest/items/{item_id}")
    def remove_manifest_item(pid: str, item_id: str):
        try:
            return manifest.remove_item(state.pdir(pid), item_id)
        except manifest.FrozenError as e:
            raise HTTPException(409, str(e))
        except manifest.ManifestError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/programs/{pid}/discover")
    def discover_sources(pid: str, body: DiscoverIn):
        """Assisted census (spec/53): propose candidate corpus sources for review.
        Read-only against the manifest — a candidate enters the corpus only when a
        human clicks Add (the existing add_item path). Degrades, never crashes:
        catalog-only if the model is unavailable, model-only if a catalog is down."""
        pdir = state.pdir(pid)
        man = manifest.load(pdir)
        if man and man.get("frozen"):
            raise HTTPException(409, "Corpus is frozen (OR-7) — discovery adds to an unfrozen "
                                     "manifest only; new material goes to the scope-change queue")
        existing = (man or {}).get("items", [])
        terms = [t.strip() for t in re.split(r"[,\n]", body.terms) if t.strip()]

        # Model lane is best-effort: a missing key / budget stop / upstream error
        # must not deny the user the catalog lane.
        model_raw: list[dict] = []
        extra_note: Optional[str] = None
        ps_path = pdir / "governed" / "purpose_statement.json"
        purpose_text = ps_path.read_text()[:20000] if ps_path.exists() else "(no Purpose Statement on file)"
        qa_block = f"\n\n===== USER'S CLARIFYING ANSWERS (weigh these) =====\n{body.qa.strip()}" if body.qa.strip() else ""
        try:
            out, _ = _router_call("source_discovery", [{"role": "user", "content":
                DISCOVERY_PROMPT.format(terms=body.terms.strip() or "(none given)",
                                        purpose=purpose_text) + qa_block}], pid=pid)
            if isinstance(out, dict):
                model_raw = out.get("candidates") or []
        except HTTPException as e:
            extra_note = f"model expansion unavailable ({e.detail}) — showing catalog results only"

        # Persist the census reasoning (terms + Q&A) to the restricted store so it
        # travels in the owner's program package (spec/54 §2.5).
        if body.qa.strip() or terms:
            rp = pdir / "restricted" / "discovery_interview.json"
            rp.parent.mkdir(parents=True, exist_ok=True)
            hist = json.loads(rp.read_text()) if rp.exists() else []
            hist.append({"timestamp": datetime.now(timezone.utc).isoformat(),
                         "terms": body.terms, "qa": body.qa})
            rp.write_text(json.dumps(hist, indent=2))

        # Route the catalog lanes by jurisdiction inferred from the scope + terms + Q&A.
        juris = discover_mod.detect_jurisdictions(purpose_text + " " + body.terms + " " + body.qa)
        d = discover_mod.Discoverer(snapshot_date=SNAPSHOT_DATE, transport=state.router.transport)
        result = d.discover(terms=terms, model_candidates=model_raw, existing_items=existing,
                            jurisdictions=juris)
        if extra_note:
            result["notes"].append(extra_note)
        return result

    @app.post("/api/programs/{pid}/discover/questions")
    def discover_questions(pid: str):
        """Optional mini-interview: up to 3 clarifying questions to sharpen discovery
        (spec/54 §2.2). Best-effort — if the model is unavailable, returns none."""
        pdir = state.pdir(pid)
        ps_path = pdir / "governed" / "purpose_statement.json"
        purpose_text = ps_path.read_text()[:20000] if ps_path.exists() else "(no Purpose Statement on file)"
        try:
            out, _ = _router_call("discovery_questions", [{"role": "user", "content":
                DISCOVERY_QUESTIONS_PROMPT.format(purpose=purpose_text)}], pid=pid)
            qs = [ln.strip(" -•\t") for ln in str(out).splitlines() if ln.strip()][:3]
            return {"questions": qs}
        except HTTPException as e:
            return {"questions": [], "note": f"question generation unavailable ({e.detail})"}

    # ---------------- per-program model policy (spec/55 §4) ----------------

    @app.get("/api/programs/{pid}/policy")
    def get_policy(pid: str):
        return policy_mod.load(state.pdir(pid), pid)

    @app.post("/api/programs/{pid}/policy")
    def set_policy(pid: str, body: PolicySetIn):
        """Set the program's model strategy (provisional only)."""
        if body.preset not in presets_mod.PRESETS:
            raise HTTPException(400, f"Unknown preset '{body.preset}'")
        try:
            doc, notes = policy_mod.set_preset(state.pdir(pid), pid, state.registry, body.preset, body.lab)
        except policy_mod.PolicyLocked as e:
            raise HTTPException(409, str(e))
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"policy": doc, "notes": notes}

    @app.post("/api/programs/{pid}/policy/override")
    def set_policy_override(pid: str, body: OverrideIn):
        """Fine-tune one task's model (provisional only) → strategy becomes Customized."""
        try:
            return policy_mod.set_override(state.pdir(pid), pid, body.task_id, body.model)
        except policy_mod.PolicyLocked as e:
            raise HTTPException(409, str(e))

    @app.post("/api/programs/{pid}/policy/ratify")
    def ratify_policy(pid: str, body: PolicyRatifyIn):
        """⚖ Lock the model policy: it becomes a ratified decision, read-only after."""
        if body.role != "Program Owner":
            raise HTTPException(403, "Only the Program Owner may lock the model policy")
        if not body.name.strip() or not body.rationale.strip():
            raise HTTPException(400, "Locking requires your name and a rationale — both go to the Decision Log")
        try:
            doc = policy_mod.ratify(state.pdir(pid), pid, body.name.strip(), body.rationale.strip())
        except policy_mod.PolicyError as e:
            raise HTTPException(409, str(e))
        now = datetime.now(timezone.utc).isoformat()
        entry_id = f"DL-{len(storage.read_decisions(state.pdir(pid))) + 1:03d}"
        label = doc["preset"] + (f":{doc['lab']}" if doc.get("lab") else "")
        storage.append_decision(state.pdir(pid), {
            "entry_id": entry_id, "timestamp": now, "type": "ratification",
            "artifact": "model_policy.json",
            "decided_by": {"name": body.name.strip(), "role": body.role},
            "decision": f"Lock model policy for {pid}: {label} ({len(doc['overrides'])} task overrides)",
            "rationale": body.rationale.strip(),
        })
        return doc

    @app.post("/api/programs/{pid}/policy/reopen")
    def reopen_policy(pid: str, body: PolicyRatifyIn):
        """Re-open a locked policy (Program Owner + rationale, logged) — the only
        way to change models after locking (spec/55 §4)."""
        if body.role != "Program Owner":
            raise HTTPException(403, "Only the Program Owner may re-open the model policy")
        if not body.name.strip() or not body.rationale.strip():
            raise HTTPException(400, "Re-opening requires your name and a rationale — both go to the Decision Log")
        doc = policy_mod.reopen(state.pdir(pid), pid)
        now = datetime.now(timezone.utc).isoformat()
        entry_id = f"DL-{len(storage.read_decisions(state.pdir(pid))) + 1:03d}"
        storage.append_decision(state.pdir(pid), {
            "entry_id": entry_id, "timestamp": now, "type": "other",
            "artifact": "model_policy.json",
            "decided_by": {"name": body.name.strip(), "role": body.role},
            "decision": f"Re-open model policy for {pid} (was locked)",
            "rationale": body.rationale.strip(),
        })
        return doc

    @app.post("/api/programs/{pid}/manifest/freeze")
    def freeze_manifest(pid: str, body: RatifyIn):
        """⚖ Freeze the corpus (instruction set P1.7). Logged; irreversible in-place."""
        if body.role not in ("Corpus Steward", "Distillation Lead", "Program Owner"):
            raise HTTPException(403, "Freeze is a Corpus Steward / Distillation Lead / Program Owner act")
        if not body.name.strip() or not body.rationale.strip():
            raise HTTPException(400, "Freezing requires your name and a rationale — both go to the Decision Log")
        # Gate (spec/55 §4): the policy governing distillation spend must be a
        # ratified decision before the corpus is committed.
        if policy_mod.load(state.pdir(pid), pid).get("status") != "ratified":
            raise HTTPException(409, "Lock your model policy before freezing the corpus — the models that "
                                     "will run distillation must be a ratified decision first (Models tab → Lock).")
        try:
            doc = manifest.freeze(state.pdir(pid))
        except manifest.FrozenError as e:
            raise HTTPException(409, str(e))
        except manifest.ManifestError as e:
            raise HTTPException(400, str(e))
        now = datetime.now(timezone.utc).isoformat()
        entry_id = f"DL-{len(storage.read_decisions(state.pdir(pid))) + 1:03d}"
        storage.append_decision(state.pdir(pid), {
            "entry_id": entry_id, "timestamp": now, "type": "manifest_freeze",
            "artifact": "manifest/manifest.json", "artifact_version": doc["manifest_version"],
            "decided_by": {"name": body.name, "role": body.role},
            "decision": f"Freeze manifest for {pid}: {len(doc['items'])} items, {doc['content_hash']}",
            "rationale": body.rationale,
        })
        return doc

    # ---------------- corpus texts (M3.1: acquisition) ----------------

    SNAPSHOT_DATE = "2026-07-18"  # DL-002 pin; program-configurable at Scope Contract freeze

    def _frozen_manifest(pid: str) -> dict:
        doc = manifest.load(state.pdir(pid))
        if doc is None:
            raise HTTPException(404, "No manifest — import a corpus slice first")
        if not doc.get("frozen"):
            raise HTTPException(409, "Manifest is not frozen — texts are acquired only against a "
                                     "pinned corpus (freeze first)")
        return doc

    def _excluded(pid: str) -> set:
        """item_ids the Program Owner has set aside (spec/55): recorded outside the
        frozen manifest so OR-7 holds, but dropped from the required-to-work set so
        an un-acquirable source doesn't block completeness."""
        p = state.pdir(pid) / "governed" / "excluded_sources.json"
        if p.exists():
            try:
                return set((json.loads(p.read_text()).get("items") or {}).keys())
            except ValueError:
                return set()
        return set()

    @app.post("/api/programs/{pid}/corpus/exclude")
    def exclude_source(pid: str, body: ExcludeIn):
        """Set aside (or restore) a corpus source. Logged; does not touch the
        frozen manifest or its hash — the source stays on the record, marked as a
        deliberate exclusion rather than a failure."""
        doc = _frozen_manifest(pid)
        item = next((i for i in doc["items"] if i["item_id"] == body.item_id), None)
        if item is None:
            raise HTTPException(404, f"No item '{body.item_id}' in the corpus")
        p = state.pdir(pid) / "governed" / "excluded_sources.json"
        reg = json.loads(p.read_text()) if p.exists() else {"items": {}}
        reg.setdefault("items", {})
        now = datetime.now(timezone.utc).isoformat()
        if body.undo:
            reg["items"].pop(body.item_id, None)
            decision = f"Restore set-aside source '{body.item_id}' to the working corpus"
        else:
            if not body.reason.strip():
                raise HTTPException(400, "Setting a source aside requires a reason — it goes to the Decision Log")
            reg["items"][body.item_id] = {"reason": body.reason.strip(), "at": now}
            decision = f"Set aside source '{body.item_id}': {item.get('title', '')[:80]}"
        p.write_text(json.dumps(reg, indent=2))
        entry_id = f"DL-{len(storage.read_decisions(state.pdir(pid))) + 1:03d}"
        storage.append_decision(state.pdir(pid), {
            "entry_id": entry_id, "timestamp": now, "type": "disposition",
            "artifact": "corpus", "decided_by": {"name": "Program Owner", "role": "Program Owner"},
            "decision": decision, "rationale": body.reason.strip() or "restored"})
        return {"item_id": body.item_id, "excluded": not body.undo, "count": len(reg["items"])}

    @app.get("/api/programs/{pid}/corpus/status")
    def corpus_status(pid: str):
        doc = _frozen_manifest(pid)
        acq = acquire.Acquirer(state.pdir(pid), snapshot_date=SNAPSHOT_DATE,
                               manifest_hash=doc["content_hash"], transport=state.router.transport)
        reg = acq.register()
        ups = acq.uploads()
        excl = _excluded(pid)
        counts = {"fetched": 0, "error": 0, "pending": 0, "excluded": 0}
        per_item = {}
        for it in doc["items"]:
            iid = it["item_id"]
            if iid in excl:                      # set aside → not error, not required
                counts["excluded"] += 1
                per_item[iid] = {"status": "excluded", "errors": None, "text_chars": None}
                continue
            rec = reg["items"].get(iid)
            up = ups.get(iid)
            if rec:
                st, errors, chars = rec["status"], rec.get("errors"), rec.get("text_chars")
            elif up and (state.pdir(pid) / "governed" / "corpus_texts" / f"{iid}.txt").exists():
                st, errors, chars = "manual", None, up.get("chars")   # uploaded, not yet in the register
            else:
                st, errors, chars = "pending", None, None
            # 'manual'/'browser_assisted' (uploaded or hand-supplied) count as acquired.
            bucket = "fetched" if st in acquire.DONE_STATUSES else (st if st in counts else "pending")
            counts[bucket] += 1
            per_item[iid] = {"status": st, "errors": errors, "text_chars": chars,
                             "uploaded": bool(up)}
        return {"snapshot_date": SNAPSHOT_DATE, "manifest_hash": doc["content_hash"],
                "counts": counts, "items": per_item}

    @app.post("/api/programs/{pid}/corpus/acquire")
    def corpus_acquire(pid: str, body: AcquireIn):
        doc = _frozen_manifest(pid)
        acq = acquire.Acquirer(state.pdir(pid), snapshot_date=SNAPSHOT_DATE,
                               manifest_hash=doc["content_hash"], transport=state.router.transport)
        excl = _excluded(pid)
        items = [i for i in doc["items"] if i["item_id"] not in excl]  # don't re-fetch set-aside sources
        try:
            return acq.acquire(items, limit=body.limit, retry_errors=body.retry_errors)
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/programs/{pid}/corpus/url-override")
    def set_url_override(pid: str, body: UrlOverrideIn):
        """Supply/correct the source URL for one corpus item without touching the
        frozen manifest (OR-7: the datum is immutable; how we fetch it is ours).
        For sources the auto-fetcher can't map (e.g. non-US legislation)."""
        doc = _frozen_manifest(pid)
        if not any(i["item_id"] == body.item_id for i in doc["items"]):
            raise HTTPException(404, f"No item '{body.item_id}' in the corpus")
        d = state.pdir(pid) / "governed" / "corpus_texts"
        d.mkdir(parents=True, exist_ok=True)
        path = d / "url_overrides.json"
        ov = json.loads(path.read_text()) if path.exists() else {}
        url = body.url.strip()
        if url:
            ov[body.item_id] = url
        else:
            ov.pop(body.item_id, None)
        path.write_text(json.dumps(ov, indent=2))
        return {"item_id": body.item_id, "url": url or None, "overrides": len(ov)}

    MAX_UPLOAD_BYTES = 25 * 1024 * 1024   # 25 MB — a generous ceiling for a single source document
    _UPLOAD_MISSING_MSG = ("Document upload needs the 'python-multipart' package, which isn't "
                           "installed. Install it (pip install python-multipart) and restart the app.")

    if _HAS_MULTIPART:
        @app.post("/api/programs/{pid}/corpus/upload")
        async def corpus_upload(pid: str, item_id: str = Form(...), file: UploadFile = File(...)):
            """Supply the TEXT for a source already in the frozen corpus by uploading
            its document — for sources with no fetchable URL. Doesn't touch the frozen
            manifest (OR-7): only records how the datum's text was acquired."""
            doc = _frozen_manifest(pid)
            if not any(i["item_id"] == item_id for i in doc["items"]):
                raise HTTPException(404, f"No item '{item_id}' in the corpus")
            data = await file.read()
            if not data:
                raise HTTPException(400, "the uploaded file is empty")
            if len(data) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"file is {len(data) // (1024*1024)} MB — the limit is 25 MB")
            try:
                prov = acquire.store_upload(state.pdir(pid), item_id, file.filename or "upload", data)
            except acquire.UploadError as e:
                raise HTTPException(422, str(e))
            acq = acquire.Acquirer(state.pdir(pid), snapshot_date=SNAPSHOT_DATE,
                                   manifest_hash=doc["content_hash"], transport=state.router.transport)
            acq.mark_uploaded(item_id)     # reflect it in the corpus immediately, no fetch pass
            return {"item_id": item_id, "status": "manual", **prov}

        @app.post("/api/programs/{pid}/discover/upload")
        async def discover_upload(pid: str, title: str = Form(...), issuer: str = Form(...),
                                  family: str = Form(...), locator: str = Form(""),
                                  evidence_role: str = Form(""), file: UploadFile = File(...)):
            """Add a BRAND-NEW source to the (unfrozen) corpus from an uploaded
            document — for in-scope sources that aren't retrievable by URL. Creates
            the manifest item and stores its text in one step."""
            title, issuer, family = title.strip(), issuer.strip(), family.strip()
            if not (title and issuer and family):
                raise HTTPException(400, "title, issuer, and family are all required")
            data = await file.read()
            if not data:
                raise HTTPException(400, "the uploaded file is empty")
            if len(data) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"file is {len(data) // (1024*1024)} MB — the limit is 25 MB")
            existing = {i["item_id"] for i in (manifest.load(state.pdir(pid)) or {"items": []}).get("items", [])}
            base = discover_mod.slugify(title) or "uploaded-source"
            iid, n = base, 2
            while iid in existing:
                iid, n = f"{base}-{n}", n + 1
            try:
                prov = acquire.store_upload(state.pdir(pid), iid, file.filename or "upload", data)
            except acquire.UploadError as e:
                raise HTTPException(422, str(e))
            item = {
                "item_id": iid, "title": title, "issuer": issuer, "family": family,
                "status": "live", "locator": (locator.strip() or f"Uploaded document: {file.filename}"),
                "evidence_role": (evidence_role.strip() or None),
                "note": (f"Source text supplied by uploaded document '{file.filename}' "
                         f"({prov['sha256']}); no public URL."),
            }
            try:
                manifest.add_item(state.pdir(pid), {k: v for k, v in item.items() if v is not None}, pid)
            except manifest.FrozenError as e:
                raise HTTPException(409, str(e))
            except manifest.ManifestError as e:
                raise HTTPException(400, str(e))
            return {"item": item, "status": "manual", **prov}
    else:
        # python-multipart absent — register stubs so the rest of the app still
        # starts, and any upload attempt gets a clear, actionable message.
        @app.post("/api/programs/{pid}/corpus/upload")
        def corpus_upload_unavailable(pid: str):
            raise HTTPException(503, _UPLOAD_MISSING_MSG)

        @app.post("/api/programs/{pid}/discover/upload")
        def discover_upload_unavailable(pid: str):
            raise HTTPException(503, _UPLOAD_MISSING_MSG)

    # ---------------- distillation (M3.2: P2 extract → defects) ----------------

    def _distiller(pid: str) -> "distill.Distiller":
        doc = _frozen_manifest(pid)
        ps_path = state.pdir(pid) / "governed" / "purpose_statement.json"
        if not ps_path.exists():
            raise HTTPException(409, "No Purpose Statement — distillation is anchored to the ratified scope")
        ps = json.loads(ps_path.read_text())
        if ps.get("status") != "ratified":
            raise HTTPException(409, "Purpose Statement is not ratified — ratify before distilling (OR-4 discipline)")
        scope = (((ps.get("synthesis") or {}).get("scope_sentence") or {}).get("text")
                 or "").strip()
        if not scope:
            raise HTTPException(409, "Ratified Purpose Statement has no scope sentence")
        d = distill.Distiller(state.pdir(pid), program_id=pid, scope=scope,
                              manifest_hash=doc["content_hash"],
                              call_fn=lambda task, msgs: _router_call(task, msgs, pid=pid))
        excl = _excluded(pid)
        d._items = [i for i in doc["items"] if i["item_id"] not in excl]  # set-aside sources aren't required
        return d

    @app.get("/api/programs/{pid}/blueprint")
    def blueprint(pid: str):
        d = _distiller(pid)
        try:
            reg = d.reconcile(d._items)   # register = derived; files + sources = truth
        except ValueError as e:
            raise HTTPException(409, str(e))
        counts = {"extracted": 0, "error": 0, "pending": 0}
        per_item = {}
        for it in d._items:
            rec = reg["items"].get(it["item_id"])
            st = rec["status"] if rec else "pending"
            counts[st if st in counts else "pending"] += 1
            per_item[it["item_id"]] = {**(rec or {"status": "pending"}), "family": it.get("family")}
        return {"assembly": d.assemble(d._items), "counts": counts, "items": per_item,
                "defects": d.defects(), "scope": d.scope,
                "has_summary": (d.pdir / "governed" / "blueprint_summary.json").exists()}

    @app.get("/api/programs/{pid}/blueprint/extraction/{item_id}")
    def blueprint_extraction(pid: str, item_id: str):
        d = _distiller(pid)
        ex = d._extraction(item_id)
        if ex is None:
            raise HTTPException(404, f"No extraction for '{item_id}' yet")
        return ex

    @app.post("/api/programs/{pid}/blueprint/extract")
    def blueprint_extract(pid: str, body: AcquireIn):
        d = _distiller(pid)
        try:
            return d.run(d._items, limit=body.limit, retry_errors=body.retry_errors)
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.post("/api/programs/{pid}/blueprint/summarize")
    def blueprint_summarize(pid: str):
        """Generate/refresh the ADVISORY executive summary (model-drafted,
        clearly labeled, never part of the governed blueprint)."""
        d = _distiller(pid)   # gates: frozen manifest + ratified PS
        digest, defects = render.build_digest(state.pdir(pid))
        out, stamp = _router_call("blueprint_summary", [{"role": "user", "content":
            render.SUMMARY_PROMPT.format(program_id=pid, scope=d.scope,
                                         digest=digest, defects=defects)}], pid=pid)
        out["_provenance"] = {"advisory": True, "model_served": stamp["model_served"],
                              "generated_at": stamp["timestamp"],
                              "cost_usd": stamp["cost"]["usd"],
                              "note": "reading guide only — never ratified, tables win"}
        (state.pdir(pid) / "governed" / "blueprint_summary.json").write_text(
            json.dumps(out, indent=2))
        return out

    @app.get("/api/programs/{pid}/blueprint/render", response_class=HTMLResponse)
    def blueprint_render(pid: str):
        _distiller(pid)   # same gates: frozen manifest + ratified PS
        return render.render_blueprint(state.pdir(pid), pid)

    @app.post("/api/programs/{pid}/blueprint/defects")
    def blueprint_defects(pid: str, body: DefectRunIn):
        d = _distiller(pid)
        return d.detect_defects(d._items, family=body.family)

    # ---------------- refactor pass (M4: P3.1-P3.8) ----------------

    def _refactorer(pid: str) -> "refactor_mod.Refactorer":
        d = _distiller(pid)                      # inherits manifest + ratified-PS gates
        reg = d.reconcile(d._items)
        undone = [it["item_id"] for it in d._items
                  if reg["items"].get(it["item_id"], {}).get("status") != "extracted"]
        if undone:
            raise HTTPException(409, f"Phase 2 gate not passed: {len(undone)} items not extracted "
                                     f"({', '.join(undone[:5])}…) — the refactor pass works a complete "
                                     "Derived Blueprint")
        if not (state.pdir(pid) / "governed" / "registers" / "defects.json").exists():
            raise HTTPException(409, "No Defect Register — run defect detection before the refactor pass")
        ps = json.loads((state.pdir(pid) / "governed" / "purpose_statement.json").read_text())
        mode = (((ps.get("synthesis") or {}).get("recommended_mode") or {}).get("mode")
                or "refactor")

        def dl_fn(entry: dict) -> str:
            entry_id = f"DL-{len(storage.read_decisions(state.pdir(pid))) + 1:03d}"
            storage.append_decision(state.pdir(pid), {
                "entry_id": entry_id,
                "timestamp": datetime.now(timezone.utc).isoformat(), **entry})
            return entry_id

        return refactor_mod.Refactorer(
            state.pdir(pid), program_id=pid, scope=d.scope, mode=mode,
            manifest_hash=d.manifest_hash,
            call_fn=lambda task, msgs: _router_call(task, msgs, pid=pid),
            dl_fn=dl_fn)

    def _refactor_guard(fn):
        try:
            return fn()
        except refactor_mod.RefactorError as e:
            raise HTTPException(e.status, e.detail)

    @app.get("/api/programs/{pid}/refactor")
    def refactor_summary(pid: str):
        return _refactorer(pid).summary()

    @app.post("/api/programs/{pid}/refactor/propose")
    def refactor_propose(pid: str, body: ProposeIn):
        r = _refactorer(pid)
        return r.propose(limit=body.limit, retry_errors=body.retry_errors)

    @app.post("/api/programs/{pid}/refactor/operations/{op_id}/disposition")
    def refactor_disposition(pid: str, op_id: str, body: DispositionIn):
        r = _refactorer(pid)
        return _refactor_guard(lambda: r.disposition(
            op_id, name=body.name, role=body.role, action=body.action,
            effect_class=body.effect_class, rationale=body.rationale,
            modified_proposal=body.modified_proposal))

    @app.post("/api/programs/{pid}/refactor/invariants")
    def refactor_invariants(pid: str):
        return _refactorer(pid).invariants()

    @app.post("/api/programs/{pid}/refactor/ratify")
    def refactor_ratify(pid: str, body: RefactorRatifyIn):
        r = _refactorer(pid)
        return _refactor_guard(lambda: r.ratify(
            name=body.name, role=body.role, rationale=body.rationale))

    # ---------------- redesign pass (P0.9 + P3D) ----------------

    def _redesigner(pid: str) -> "redesign_mod.Redesigner":
        ps_path = state.pdir(pid) / "governed" / "purpose_statement.json"
        if not ps_path.exists():
            raise HTTPException(404, "unknown program")
        ps = json.loads(ps_path.read_text())
        if ps.get("status") != "ratified":
            raise HTTPException(409, "Purpose Statement not ratified")
        mode = (((ps.get("synthesis") or {}).get("recommended_mode") or {}).get("mode"))
        if mode != "redesign":
            raise HTTPException(409, "This is not a redesign-mode program — the redesign pass "
                                     "runs only under a redesign charter (OR-1)")
        if not (state.pdir(pid) / "governed" / "refactored_baseline.json").exists():
            raise HTTPException(409, "No certified Refactored Blueprint baseline — the redesign "
                                     "pass runs on a cleaned drawing or not at all (OR-8)")
        scope = (((ps.get("synthesis") or {}).get("scope_sentence") or {}).get("text") or "")

        def dl_fn(entry: dict) -> str:
            entry_id = f"DL-{len(storage.read_decisions(state.pdir(pid))) + 1:03d}"
            storage.append_decision(state.pdir(pid), {
                "entry_id": entry_id,
                "timestamp": datetime.now(timezone.utc).isoformat(), **entry})
            return entry_id

        return redesign_mod.Redesigner(
            state.pdir(pid), program_id=pid, scope=scope,
            call_fn=lambda task, msgs: _router_call(task, msgs, pid=pid), dl_fn=dl_fn)

    def _rd_guard(fn):
        try:
            return fn()
        except refactor_mod.RefactorError as e:
            raise HTTPException(e.status, e.detail)

    @app.post("/api/programs/{pid}/charter-successor")
    def charter_successor(pid: str, body: CharterIn):
        sid = body.successor_id.strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,60}", sid):
            raise HTTPException(400, "successor_id: lowercase letters, digits, hyphens")
        succ_dir = state.root / "programs" / sid   # not pdir(): it does not exist yet
        out = _rd_guard(lambda: redesign_mod.charter_successor(
            state.pdir(pid), succ_dir, pred_id=pid, succ_id=sid))
        for p_, note in ((pid, f"Charter redesign successor {sid} (ADR-007)"),
                         (sid, f"Chartered from {pid} against its certified Target Blueprint")):
            entry_id = f"DL-{len(storage.read_decisions(state.pdir(p_))) + 1:03d}"
            storage.append_decision(state.pdir(p_), {
                "entry_id": entry_id, "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "scope_election", "artifact": "purpose_statement.json",
                "artifact_version": "0.1", "decision": note,
                "rationale": "sequence split ratified in the predecessor Purpose Statement",
                "decided_by": {"name": "system (per ratified charter)", "role": "Program Owner"}})
        return out

    @app.get("/api/programs/{pid}/redesign")
    def redesign_summary(pid: str):
        return _redesigner(pid).summary()

    @app.post("/api/programs/{pid}/redesign/mandate/ratify")
    def redesign_mandate_ratify(pid: str, body: MandateRatifyIn):
        r = _redesigner(pid)
        return _rd_guard(lambda: r.ratify_mandate(
            name=body.name, role=body.role,
            decisions=[d.model_dump() for d in body.decisions],
            ranking=body.ranking, constraints=body.constraints, rationale=body.rationale))

    @app.post("/api/programs/{pid}/redesign/misalign")
    def redesign_misalign(pid: str):
        return _rd_guard(lambda: _redesigner(pid).detect_misalignments())

    @app.post("/api/programs/{pid}/redesign/propose")
    def redesign_propose(pid: str, body: ProposeIn):
        r = _redesigner(pid)
        return _rd_guard(lambda: r.propose(limit=body.limit, retry_errors=body.retry_errors))

    @app.post("/api/programs/{pid}/redesign/operations/{op_id}/disposition")
    def redesign_disposition(pid: str, op_id: str, body: DispositionIn):
        r = _redesigner(pid)
        return _rd_guard(lambda: r.disposition(
            op_id, name=body.name, role=body.role, action=body.action,
            effect_class=body.effect_class, rationale=body.rationale,
            modified_proposal=body.modified_proposal))

    @app.post("/api/programs/{pid}/redesign/backlog/{op_id}/disposition")
    def redesign_backlog(pid: str, op_id: str, body: BacklogDispositionIn):
        r = _redesigner(pid)
        return _rd_guard(lambda: r.backlog_disposition(
            op_id, name=body.name, role=body.role, action=body.action,
            rationale=body.rationale, objective_id=body.objective_id))

    @app.post("/api/programs/{pid}/redesign/invariants")
    def redesign_invariants(pid: str):
        return _rd_guard(lambda: _redesigner(pid).invariants())

    @app.post("/api/programs/{pid}/redesign/ratify")
    def redesign_ratify(pid: str, body: RedesignRatifyIn):
        r = _redesigner(pid)
        return _rd_guard(lambda: r.ratify(
            name=body.name, role=body.role, rationale=body.rationale,
            deferred_objectives=body.deferred_objectives))

    # ---------------- align pass (Phase 4 spine: crosswalk + audit) ----------------

    def _crosswalker(pid: str) -> "crosswalk_mod.Crosswalker":
        state.pdir(pid)  # 404 if unknown
        if not (state.pdir(pid) / "governed" / "target_blueprint.json").exists():
            raise HTTPException(409, "No ratified Target Blueprint — the Align pass runs on a "
                                     "ratified Phase-3 output (Phase 4 entry gate)")
        return crosswalk_mod.Crosswalker(state.pdir(pid), pid)

    def _overview(pid: str) -> dict:
        d = state.pdir(pid)
        g = d / "governed"
        def js(path, default=None):
            f = g / path
            return json.loads(f.read_text()) if f.exists() else default

        ps = js("purpose_statement.json", {}) or {}
        syn = ps.get("synthesis") or {}
        mode = ((syn.get("recommended_mode") or {}).get("mode")) or "?"
        scope = ((syn.get("scope_sentence") or {}).get("text")) or ""
        stages = []

        # Purpose
        stages.append({"key": "purpose", "label": "Purpose", "phase": "P0",
                       "done": ps.get("status") == "ratified",
                       "metric": (f"ratified · {mode} mode" if ps.get("status") == "ratified"
                                  else ps.get("status", "not started")),
                       "detail": scope[:160], "link": None})

        # Corpus (set-aside sources drop out of the required-to-work count)
        man = js("manifest/manifest.json")
        acq = js("corpus_texts/acquisition.json", {"items": {}}) or {"items": {}}
        _excl = _excluded(pid)
        n_items = len([i for i in man.get("items", []) if i["item_id"] not in _excl]) if man else 0
        n_fetched = sum(1 for v in acq.get("items", {}).values()
                        if v.get("status") in ("fetched", "browser_assisted", "manual"))
        stages.append({"key": "corpus", "label": "Corpus", "phase": "P1",
                       "done": bool(man) and n_fetched >= n_items and n_items > 0,
                       "metric": (f"{n_items} sources · frozen · {n_fetched} acquired" if man
                                  else "not assembled"),
                       "detail": f"manifest {man.get('content_hash','')[:22]}" if man else "",
                       "link": None})

        # Derived Blueprint
        bdir = g / "blueprint"
        n_ext = n_ob = n_df = 0
        if bdir.exists():
            for f in bdir.glob("*.json"):
                if f.name == "extraction_register.json":
                    continue
                doc = json.loads(f.read_text())
                n_ext += 1
                n_ob += len(doc.get("obligations", []))
                n_df += len(doc.get("definitions", []))
        defects = js("registers/defects.json", {"runs": {}}) or {"runs": {}}
        n_def = sum(len(r.get("findings", [])) for r in defects.get("runs", {}).values())
        stages.append({"key": "derived", "label": "Derived Blueprint", "phase": "P2 ① Distill",
                       "done": n_ext > 0 and n_ext >= n_items,
                       "metric": (f"{n_ob} obligations · {n_df} definitions · {n_def} defects"
                                  if n_ext else "not distilled"),
                       "detail": f"{n_ext}/{n_items} sources extracted",
                       "link": f"/api/programs/{pid}/blueprint/render" if n_ext else None})

        # Phase 3: refactor / redesign -> Target Blueprint
        tb = js("target_blueprint.json")
        mand = js("ratified_mandate.json")
        ec = {}
        if tb:
            trace = list(tb.get("operation_trace", []))
            base = js("refactored_baseline.json")
            if tb.get("mode") == "redesign" and base:
                trace = base.get("operation_trace", []) + trace
            for op in trace:
                cl = (op.get("disposition") or {}).get("effect_class", "?")
                ec[cl] = ec.get(cl, 0) + 1
            n_ops = len(trace)
        else:
            n_ops = 0
        p3label = "P3 ②b Redesign" if mode == "redesign" else "P3 ②a Refactor"
        p3metric = "not started"
        if tb:
            p3metric = f"{n_ops} operations finalized · " + ", ".join(f"{k} {v}" for k, v in sorted(ec.items()))
        stages.append({"key": "phase3", "label": ("Redesign" if mode == "redesign" else "Refactor"),
                       "phase": p3label, "done": bool(tb),
                       "metric": p3metric,
                       "detail": (f"Mandate: {len(mand.get('objectives', []))} objectives ranked"
                                  if mand else ""),
                       "link": None})

        # Target Blueprint
        stages.append({"key": "target", "label": "Target Blueprint", "phase": "P3 output",
                       "done": bool(tb),
                       "metric": (f"ratified · {tb.get('label','')}" if tb else "not ratified"),
                       "detail": (tb.get("content_hash", "")[:22] if tb else ""),
                       "link": f"/api/programs/{pid}/target-blueprint/render" if tb else None})

        # Align (crosswalk)
        cw_metric, cw_done, cw_detail = "runs after Target Blueprint", False, ""
        if tb:
            try:
                cw = crosswalk_mod.Crosswalker(d, pid).build()
                c = cw["counts"]
                cw_done = cw["audit"]["pass"]
                cw_metric = f"{c['subsumed']} subsumed · {c['repealed']} repealed · {c['retained']} retained"
                cw_detail = "effect-class audit " + ("PASS" if cw["audit"]["pass"] else "FAILING")
            except Exception:
                cw_metric = "unavailable"
        stages.append({"key": "align", "label": "Align — Crosswalk", "phase": "P4 ③ Align",
                       "done": cw_done, "metric": cw_metric, "detail": cw_detail,
                       "link": f"/api/programs/{pid}/crosswalk/render" if tb else None})

        # decisions + cost
        decisions = storage.read_decisions(d)
        cost = 0.0
        stamps = state.root / "runs" / "stamps.jsonl"
        if stamps.exists():
            for line in stamps.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    st = json.loads(line)
                except ValueError:
                    continue
                if st.get("program_id") == pid:
                    cost += (st.get("cost") or {}).get("usd", 0) or 0

        # A tab appears once the program is READY to work on that phase (the
        # previous gate has passed), NOT only once that phase already has
        # output. Keying on output dead-ends new programs — e.g. the Corpus tab
        # is where you BUILD the manifest, so it must not require a manifest to
        # already exist. (Fixes: new program, Purpose ratified, no Corpus tab.)
        ps_ratified = ps.get("status") == "ratified"
        manifest_frozen = bool(man) and man.get("frozen")
        phase2_complete = n_ext > 0 and n_items > 0 and n_ext >= n_items
        has_defects = (g / "registers" / "defects.json").exists()
        has_ops = (g / "registers" / "operations.json").exists()
        has_baseline = (g / "refactored_baseline.json").exists()
        tabs = {
            "corpus": ps_ratified,                                   # ready to assemble the corpus
            "derived": manifest_frozen,                              # ready to distill / view the blueprint
            "refactor": has_ops or (mode != "redesign" and phase2_complete and has_defects),
            "redesign": mode == "redesign" and (
                has_baseline or (g / "registers" / "redesign_operations.json").exists()),
            "target": bool(tb),
            "align": bool(tb),
        }
        return {"program_id": pid, "mode": mode, "scope": scope, "stages": stages,
                "tabs": tabs, "decisions": decisions, "decision_count": len(decisions),
                "cost_usd": round(cost, 2)}

    @app.get("/api/programs/{pid}/overview")
    def overview(pid: str):
        return _overview(pid)

    @app.get("/api/programs/{pid}/ledger/{phase}")
    def ledger(pid: str, phase: str):
        """The read-only record for a phase (spec/55 §5): its conversation, its
        decisions, and the models it used. 'overview' is program-wide."""
        pdir = state.pdir(pid)
        all_decisions = storage.read_decisions(pdir)

        # provenance: aggregate this program's stamps by task
        prov: dict[str, dict] = {}
        stamps = state.root / "runs" / "stamps.jsonl"
        if stamps.exists():
            for line in stamps.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    s = json.loads(line)
                except ValueError:
                    continue
                if s.get("program_id") != pid:
                    continue
                tid = s.get("task_id")
                rec = prov.setdefault(tid, {"task": tid, "model": s.get("model_served"), "calls": 0, "cost": 0.0})
                rec["model"] = s.get("model_served") or rec["model"]
                rec["calls"] += 1
                rec["cost"] += (s.get("cost") or {}).get("usd", 0.0) or 0.0

        def read_transcript(fname: str) -> list:
            p = pdir / "restricted" / fname
            if not p.exists():
                return []
            try:
                data = json.loads(p.read_text())
            except ValueError:
                return []
            out = []
            if fname == "interview.json":
                for m in data:
                    out.append({"role": m.get("role", "?"),
                                "content": (m.get("content", "") or "").replace("[INTERVIEW-COMPLETE]", "").strip(),
                                "source": "purpose interview"})
            else:  # discovery_interview.json — list of {timestamp, terms, qa}
                for m in data:
                    body = ("terms: " + (m.get("terms") or "—")) + (("\n" + m["qa"]) if m.get("qa") else "")
                    out.append({"role": "discovery", "content": body, "source": "source discovery"})
            return out

        if phase == "overview":
            conversation = read_transcript("interview.json") + read_transcript("discovery_interview.json")
            decisions = all_decisions
            models = sorted(prov.values(), key=lambda r: r["task"])
        else:
            tasks = set(LEDGER_PHASE_TASKS.get(phase, []))
            models = sorted((r for t, r in prov.items() if t in tasks), key=lambda r: r["task"])
            decisions = [d for d in all_decisions if _decision_phase(d) == phase]
            conversation = []
            for f in LEDGER_PHASE_TRANSCRIPTS.get(phase, []):
                conversation += read_transcript(f)

        for r in models:
            r["cost"] = round(r["cost"], 6)
        return {"phase": phase, "conversation": conversation,
                "decisions": decisions, "models": models}

    @app.get("/api/programs/{pid}/target-blueprint/render", response_class=HTMLResponse)
    def target_blueprint_render(pid: str):
        if not (state.pdir(pid) / "governed" / "target_blueprint.json").exists():
            raise HTTPException(409, "No ratified Target Blueprint yet — complete and ratify the "
                                     "Refactor/Redesign pass first")
        return render.render_target_blueprint(state.pdir(pid), pid)

    @app.post("/api/programs/{pid}/target-blueprint/summarize")
    def target_blueprint_summarize(pid: str):
        gdir = state.pdir(pid) / "governed"
        if not (gdir / "target_blueprint.json").exists():
            raise HTTPException(409, "No ratified Target Blueprint yet")
        ps = json.loads((gdir / "purpose_statement.json").read_text())
        scope = (((ps.get("synthesis") or {}).get("scope_sentence") or {}).get("text") or "")
        mode = (((ps.get("synthesis") or {}).get("recommended_mode") or {}).get("mode") or "?")
        digest, trace, mandate = render.build_target_digest(state.pdir(pid))
        out, stamp = _router_call("target_summary", [{"role": "user", "content":
            render.TARGET_SUMMARY_PROMPT.format(program_id=pid, scope=scope, mode=mode,
                                                mandate=mandate, digest=digest, trace=trace)}], pid=pid)
        out["_provenance"] = {"advisory": True, "model_served": stamp["model_served"],
                              "generated_at": stamp["timestamp"], "cost_usd": stamp["cost"]["usd"],
                              "note": "reading guide only — never ratified; the operation trace wins"}
        (gdir / "target_blueprint_summary.json").write_text(json.dumps(out, indent=2))
        return out

    @app.get("/api/programs/{pid}/crosswalk")
    def crosswalk_data(pid: str):
        return _crosswalker(pid).build()

    @app.get("/api/programs/{pid}/crosswalk/render", response_class=HTMLResponse)
    def crosswalk_render(pid: str):
        return _crosswalker(pid).render()

    # ---------------- model settings (the toggle) ----------------

    @app.get("/api/models")
    def models():
        tasks = {}
        for tid, t in state.registry.tasks.items():
            res = state.router.resolve(tid)
            tasks[tid] = {
                "phase": t.phase, "description": t.description,
                "default_model": t.default_model, "sensitive": t.sensitive,
                "current_model": res.model, "source": res.source,
                "must_differ_family_from": t.must_differ_family_from,
            }
        lifetime_usd, lifetime_calls = 0.0, 0
        stamps = state.root / "runs" / "stamps.jsonl"
        if stamps.exists():
            for line in stamps.read_text().splitlines():
                if line.strip():
                    lifetime_calls += 1
                    lifetime_usd += (json.loads(line).get("cost") or {}).get("usd", 0.0)
        return {"tasks": tasks, "catalog": state.registry.settings.catalog,
                "active_preset": presets_mod.detect_active(state.registry, state.router.user_overrides),
                "spent_usd": round(state.router.spent_usd, 6),
                "calls": len(state.router.run_records),
                "lifetime_usd": round(lifetime_usd, 6), "lifetime_calls": lifetime_calls}

    @app.get("/api/models/presets")
    def list_presets():
        """The preset lineup + which one is currently active (spec/54 follow-on)."""
        return {
            "presets": [
                {"id": "recommended", "label": "Recommended",
                 "blurb": "The curated defaults — strong models for the reasoning, cheap ones for the mechanical steps, independence built in."},
                {"id": "cost", "label": "Cost-optimized",
                 "blurb": "The cheapest capable model for each task."},
                {"id": "open", "label": "Open-weight-first",
                 "blurb": "Prefer the open models (Nemotron / Kimi / Qwen) wherever they're capable and policy-eligible."},
                {"id": "lab", "label": "Lab-first", "labs": [
                    {"id": "anthropic", "label": "Anthropic"},
                    {"id": "openai", "label": "OpenAI"},
                    {"id": "google", "label": "Gemini"}],
                 "blurb": "One house everywhere it's allowed; the independence checks stay on a different house by rule."},
            ],
            "active": presets_mod.detect_active(state.registry, state.router.user_overrides),
        }

    @app.post("/api/models/preset")
    def apply_preset(body: PresetIn):
        """Bulk-apply a preset: writes the per-task overrides, enforcing the
        independence and privacy rules (they can't be waived by a preset)."""
        if body.preset not in presets_mod.PRESETS:
            raise HTTPException(400, f"Unknown preset '{body.preset}'")
        try:
            assign, notes = presets_mod.resolve_preset(state.registry, body.preset, body.lab)
        except ValueError as e:
            raise HTTPException(400, str(e))
        state.router.user_overrides = dict(assign)
        state.save_overrides()
        return {"active": {"preset": body.preset, "lab": body.lab},
                "overrides": assign, "notes": notes}

    @app.post("/api/models/override")
    def override(body: OverrideIn):
        state.registry.task(body.task_id)  # 404 via KeyError -> 500? convert:
        if body.model is None:
            state.router.user_overrides.pop(body.task_id, None)
        else:
            state.router.user_overrides[body.task_id] = body.model
        state.save_overrides()
        res = state.router.resolve(body.task_id)
        return {"task_id": body.task_id, "current_model": res.model, "source": res.source}

    @app.exception_handler(KeyError)
    async def key_error(_, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    static_dir = Path(__file__).parent / "static"

    class _NoCacheStatic(StaticFiles):
        # Serve the UI with "no-cache" so the browser revalidates every load and
        # never hands back a stale index.html after an update. This is revalidate,
        # not no-store: unchanged files still return a cheap 304 via ETag, but a
        # changed file is picked up immediately — no hard-refresh needed.
        async def get_response(self, path, scope):
            resp = await super().get_response(path, scope)
            resp.headers["Cache-Control"] = "no-cache"
            return resp

    app.mount("/", _NoCacheStatic(directory=str(static_dir), html=True), name="ui")
    return app
