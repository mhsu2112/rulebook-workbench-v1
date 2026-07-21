"""Human-readable rendering of the Derived Blueprint (P2 output note:
'structured store is the source of truth, human-readable rendering derived
from it'). Pure code — no model calls; deterministic; regenerate at will.

One self-contained HTML document: scope header → per-family sections →
per-item element tables (obligations / definitions / interactions) with
citation quotes and verification marks → defect register appendix →
provenance footer (manifest hash, counts, render time).
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

CSS = """
body { font: 14px/1.55 -apple-system, Segoe UI, sans-serif; color: #1a1f2e;
       max-width: 60rem; margin: 2rem auto; padding: 0 1.2rem; }
h1 { font-size: 1.5rem; border-bottom: 2px solid #1a1f2e; padding-bottom: .4rem; }
h2 { font-size: 1.15rem; margin-top: 2.2rem; border-bottom: 1px solid #c9ced9; padding-bottom: .25rem; }
h3 { font-size: 1rem; margin-top: 1.4rem; }
.meta { color: #5a6172; font-size: .85rem; }
.scope { background: #f4f6fa; border-left: 3px solid #1a1f2e; padding: .6rem .9rem; margin: 1rem 0; }
table { border-collapse: collapse; width: 100%; margin: .5rem 0 1rem; font-size: .85rem; }
th, td { border: 1px solid #d7dbe4; padding: .35rem .5rem; text-align: left; vertical-align: top; }
th { background: #eef1f6; }
.quote { color: #444c5e; font-style: italic; font-size: .8rem; }
.v { color: #1a7f37; } .x { color: #b42318; }
.empty { color: #8a91a0; font-style: italic; }
.badge { display: inline-block; background: #eef1f6; border: 1px solid #d7dbe4;
         border-radius: 4px; padding: 0 .35rem; font-size: .75rem; margin-right: .3rem; }
.defect { border: 1px solid #e2c363; border-radius: 6px; padding: .5rem .8rem; margin: .5rem 0; }
footer { margin-top: 3rem; border-top: 1px solid #c9ced9; padding-top: .6rem;
         color: #5a6172; font-size: .8rem; }
@media print { body { max-width: none; } }
"""


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _cites(citations: list) -> str:
    out = []
    for c in citations or []:
        if isinstance(c, str):
            c = {"quote": c}
        mark = ('<span class="v">✓</span>' if c.get("verified")
                else '<span class="x">✗</span>' if "verified" in c else "")
        out.append(f'<div class="quote">{mark} “{_e(c.get("quote", ""))}”</div>')
    return "".join(out)


def render_blueprint(program_dir: str | Path, program_id: str) -> str:
    gdir = Path(program_dir) / "governed"
    bdir = gdir / "blueprint"

    ps = {}
    ps_path = gdir / "purpose_statement.json"
    if ps_path.exists():
        ps = json.loads(ps_path.read_text())
    scope = (((ps.get("synthesis") or {}).get("scope_sentence") or {}).get("text") or "")
    mode = (((ps.get("synthesis") or {}).get("recommended_mode") or {}).get("mode") or "?")

    manifest_hash, items_meta = "", []
    man_path = gdir / "manifest" / "manifest.json"
    if man_path.exists():
        man = json.loads(man_path.read_text())
        manifest_hash = man.get("content_hash", "")
        items_meta = man.get("items", [])
    fam_of = {i["item_id"]: i.get("family", "?") for i in items_meta}
    title_of = {i["item_id"]: i.get("title", "") for i in items_meta}
    loc_of = {i["item_id"]: i.get("locator", "") for i in items_meta}

    docs = {}
    for f in sorted(bdir.glob("*.json")):
        if f.name == "extraction_register.json":
            continue
        docs[f.stem] = json.loads(f.read_text())

    families: dict[str, list[str]] = {}
    for iid in docs:
        families.setdefault(fam_of.get(iid, "?"), []).append(iid)

    n_ob = sum(len(d.get("obligations", [])) for d in docs.values())
    n_df = sum(len(d.get("definitions", [])) for d in docs.values())
    summary_html = ""
    spath = gdir / "blueprint_summary.json"
    if spath.exists():
        summary_html = render_summary_html(json.loads(spath.read_text()))

    body = [f"<h1>Derived Blueprint — {_e(program_id)}</h1>",
            f'<div class="meta">Mode: {_e(mode)} · {len(docs)} sources · '
            f'{n_ob} obligations · {n_df} definitions · rendered '
            f'{datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</div>',
            f'<div class="scope"><b>Ratified scope.</b> {_e(scope)}</div>',
            summary_html,
            '<div class="meta">This rendering is DERIVED from the structured store '
            '(one extraction file per source, citation quotes machine-verified). '
            'Per the fidelity rule (P2.3) it preserves the corpus as built — '
            'contradictions, duplication and divergent definitions included; '
            'resolving them is Phase 3 work, recorded as operations, never edits here.</div>']

    for fam in sorted(families):
        body.append(f"<h2>{_e(fam)} ({len(families[fam])} sources)</h2>")
        for iid in sorted(families[fam]):
            d = docs[iid]
            body.append(f"<h3>{_e(iid)}</h3>"
                        f'<div class="meta">{_e(title_of.get(iid, ""))} · {_e(loc_of.get(iid, ""))}</div>')
            if d.get("nothing_in_scope"):
                body.append(f'<p class="empty">∅ Nothing in scope. {_e((d.get("notes") or "")[:500])}</p>')
                continue
            obs = d.get("obligations", [])
            if obs:
                rows = "".join(
                    f"<tr><td><span class='badge'>{_e(o.get('modality'))}</span>{_e(o.get('actor'))}</td>"
                    f"<td>{_e(o.get('action'))}"
                    f"{('<div class=meta>trigger: ' + _e(o.get('trigger')) + '</div>') if o.get('trigger') else ''}"
                    f"{('<div class=meta>threshold: ' + _e(o.get('threshold')) + '</div>') if o.get('threshold') else ''}"
                    f"{('<div class=meta>exceptions: ' + _e('; '.join(o.get('exceptions'))) + '</div>') if o.get('exceptions') else ''}"
                    f"{_cites(o.get('citations'))}</td></tr>"
                    for o in obs)
                body.append(f"<table><tr><th>Actor / modality</th><th>Obligation</th></tr>{rows}</table>")
            dfs = d.get("definitions", [])
            if dfs:
                rows = "".join(
                    f"<tr><td>{_e(t.get('term'))}</td><td>{_e(t.get('definition'))}"
                    f"{_cites(t.get('citations'))}</td></tr>" for t in dfs)
                body.append(f"<table><tr><th>Term</th><th>Definition (as given)</th></tr>{rows}</table>")
            ints = d.get("interactions", [])
            if ints:
                body.append('<div class="meta">Interactions: '
                            + "; ".join(_e(i if isinstance(i, str) else json.dumps(i))[:200]
                                        for i in ints[:12]) + "</div>")
            if d.get("notes"):
                body.append(f'<div class="meta">Notes: {_e(d["notes"][:600])}</div>')

    dpath = gdir / "registers" / "defects.json"
    if dpath.exists():
        defects = json.loads(dpath.read_text())
        total = sum(len(r.get("findings", [])) for r in defects.get("runs", {}).values())
        body.append(f"<h2>Defect Register appendix ({total} findings)</h2>")
        for run_id, run in sorted(defects.get("runs", {}).items()):
            body.append(f"<h3>{_e(run_id)} ({len(run.get('findings', []))})</h3>")
            for f in run.get("findings", []):
                locs = ", ".join(
                    f"{_e(l.get('item_id'))}{' <span class=v>✓</span>' if l.get('verified') else ''}"
                    for l in f.get("locations", []))
                body.append(f'<div class="defect"><span class="badge">{_e(f.get("code"))}</span>'
                            f'<b>{_e(f.get("title"))}</b>'
                            f'<div>{_e(f.get("description", ""))}</div>'
                            f'<div class="meta">↳ {locs}</div></div>')

    body.append(f"<footer>Program {_e(program_id)} · frozen manifest {_e(manifest_hash)} · "
                "structured store: governed/blueprint/ (source of truth — this document is a "
                "derived rendering and may be regenerated at any time)</footer>")
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>Derived Blueprint — {_e(program_id)}</title>"
            f"<style>{CSS}</style></head><body>{''.join(body)}</body></html>")


SUMMARY_PROMPT = """You are writing an ADVISORY executive summary for the Derived Blueprint of
program {program_id} — a reading guide for people encountering the document
cold. Produce the typed BlueprintExecutiveSummary JSON per the schema.

RATIFIED SCOPE: {scope}

HARD RULES (the fidelity rule extends to you):
- DESCRIBE the regime as built. Do NOT resolve, harmonize, or evaluate any
  conflict, duplication, or divergence — where the blueprint records tension,
  your job is to point at it, not settle it. Phase 3 settles things, under
  governance; you are a map legend.
- Every highlight and tension carries refs: item_ids from the blueprint and/or
  defect codes (e.g. "D2", "defects-cross#4") a reader can check.
- No claims beyond the blueprint and defect register below. If something is
  notable by its ABSENCE, you may say so only if a defect finding (D9 gap) or
  a ∅ item documents it.
- Respect evidentiary ceilings: enforcement-evidence and proposal items inform
  expectations; never state them as operative duties.
- Plain prose for a policy audience. No bullet-point salad in the text fields.
- The headline is AT MOST two sentences — the forest in one breath; detail
  belongs in regime_shape.

BLUEPRINT DIGEST (structured store, condensed):
{digest}

DEFECT REGISTER:
{defects}"""


def build_digest(program_dir: str | Path) -> tuple[str, str]:
    """Condensed structured store for the summary prompt: per item — title,
    family, obligation one-liners, defined terms; plus the full defect register
    titles/descriptions. Pure code."""
    gdir = Path(program_dir) / "governed"
    man_path = gdir / "manifest" / "manifest.json"
    meta = {}
    if man_path.exists():
        for i in json.loads(man_path.read_text()).get("items", []):
            meta[i["item_id"]] = i
    parts = []
    for f in sorted((gdir / "blueprint").glob("*.json")):
        if f.name == "extraction_register.json":
            continue
        d = json.loads(f.read_text())
        iid = f.stem
        m = meta.get(iid, {})
        obs = [f"[{o.get('modality')}] {o.get('actor')}: {o.get('action')}"[:220]
               for o in d.get("obligations", [])]
        dfs = [t.get("term", "") for t in d.get("definitions", [])]
        parts.append(json.dumps({
            "item_id": iid, "family": m.get("family"), "title": m.get("title"),
            "status": m.get("status"), "evidence_role": m.get("evidence_role"),
            "nothing_in_scope": d.get("nothing_in_scope", False),
            "obligations": obs, "defined_terms": dfs,
            "notes": (d.get("notes") or "")[:300] or None}))
    digest = "\n".join(parts)
    defects = "(no defect register)"
    dpath = gdir / "registers" / "defects.json"
    if dpath.exists():
        dd = json.loads(dpath.read_text())
        lines = []
        for run_id, run in sorted(dd.get("runs", {}).items()):
            for i, fd in enumerate(run.get("findings", [])):
                lines.append(f"{run_id}#{i} [{fd.get('code')}] {fd.get('title')}: "
                             f"{fd.get('description','')[:300]} "
                             f"(items: {', '.join(l.get('item_id','') for l in fd.get('locations', []))})")
        defects = "\n".join(lines)
    return digest, defects


def render_summary_html(summary: dict) -> str:
    """The advisory box injected at the top of the rendered blueprint."""
    hl = "".join(f"<li>{_e(h['point'])} <span class='meta'>[{_e(', '.join(h['refs']))}]</span></li>"
                 for h in summary.get("highlights", []))
    tn = "".join(f"<li>{_e(t['point'])} <span class='meta'>[{_e(', '.join(t['refs']))}]</span></li>"
                 for t in summary.get("tensions", []))
    shape = "".join(f"<h4>{_e(sec['heading'])}</h4><p>{_e(sec['text'])}</p>"
                    for sec in summary.get("regime_shape", []))
    return (
        "<div style='border:2px solid #8a5a00; background:#fdf8ef; border-radius:8px; "
        "padding: .9rem 1.2rem; margin: 1.2rem 0;'>"
        "<div class='meta' style='color:#8a5a00; font-weight:bold;'>ADVISORY ORIENTATION — "
        "model-drafted reading guide. Not part of the governed blueprint; never ratified; "
        "the element tables and Defect Register below are the artifact. Where this summary "
        "and a table disagree, the table wins.</div>"
        f"<h2 style='margin-top:.6rem;'>Executive summary</h2>"
        f"<p><b>{_e(summary.get('headline',''))}</b></p>"
        f"<p class='meta'>{_e(summary.get('how_to_read',''))}</p>"
        f"{shape}"
        f"<h4>Where to focus</h4><ul>{hl}</ul>"
        f"<h4>Tensions the register documents (not resolved here)</h4><ul>{tn}</ul>"
        f"<p class='meta'>Caveats: {_e(summary.get('caveats',''))}</p>"
        "</div>")


# ---------------- Target Blueprint rendering (P3 output, operation-trace form) ----------------

TARGET_SUMMARY_PROMPT = """You are writing an ADVISORY executive summary for the TARGET Blueprint of
program {program_id} — the regime AFTER its Phase-3 work (refactor cleanup and,
in redesign mode, objective-driven reshaping). Produce the typed
BlueprintExecutiveSummary JSON per the schema.

RATIFIED SCOPE: {scope}
MODE: {mode}

HARD RULES (fidelity extends to you):
- DESCRIBE the target regime as it now stands: what the finalized operations
  consolidated, clarified, retired, and — in redesign mode — changed and why.
  Point at the operation trace and crosswalk; do not invent.
- In `tensions`, record what was deliberately NOT settled: the parked/backlog
  items (refactor mode: change-class moves refused and deferred; redesign
  mode: objectives deferred) — the honest list of questions left open. Cite
  op_ids / objective ids.
- In redesign mode, every change traces to a Principal-adopted objective — say
  which objectives the reshaping served (by id).
- This is a working paper, never operative text; the element tables live in the
  Derived Blueprint, provision-level accountability in the Crosswalk.

MANDATE (redesign mode; ranked objectives):
{mandate}

DERIVED BLUEPRINT DIGEST (the baseline being transformed):
{digest}

FINALIZED OPERATION TRACE (what the Phase-3 work did):
{trace}"""


def build_target_digest(program_dir: str | Path) -> tuple[str, str, str]:
    """Returns (derived_digest, trace_summary, mandate_text). Pure code."""
    gdir = Path(program_dir) / "governed"
    derived, _ = build_digest(program_dir)
    tgt, trace = _combined_target_trace(gdir)
    lines = []
    for op in trace:
        d = op.get("disposition") or {}
        hook = (op["operation"].get("objective_hook") or {}).get("objective_id")
        lines.append(f"{op.get('op_id')} [{op.get('_pass')}] {op['operation']['op_type']} "
                     f"({d.get('effect_class')}{'/'+hook if hook else ''}): "
                     f"{op['operation'].get('proposal','')[:200]}")
    mandate = "(refactor mode — no mandate)"
    mp = gdir / "ratified_mandate.json"
    if mp.exists():
        m = json.loads(mp.read_text())
        mandate = "\n".join(f"{o['objective_id']}: {o['statement']}" for o in m["objectives"])
        mandate += "\nRANKING: " + " > ".join(m["ranking"])
    return derived[:120_000], "\n".join(lines)[:80_000], mandate


def _combined_target_trace(gdir: Path):
    tgt = json.loads((gdir / "target_blueprint.json").read_text())
    trace = []
    if tgt.get("mode") == "redesign" and (gdir / "refactored_baseline.json").exists():
        for op in json.loads((gdir / "refactored_baseline.json").read_text()).get("operation_trace", []):
            trace.append({**op, "_pass": "refactor"})
    for op in tgt.get("operation_trace", []):
        trace.append({**op, "_pass": "redesign" if tgt.get("mode") == "redesign" else "refactor"})
    return tgt, trace


def render_target_blueprint(program_dir: str | Path, program_id: str) -> str:
    gdir = Path(program_dir) / "governed"
    tgt, trace = _combined_target_trace(gdir)
    mode = tgt.get("mode", "?")
    man_path = gdir / "manifest" / "manifest.json"
    fam_of, title_of = {}, {}
    if man_path.exists():
        for i in json.loads(man_path.read_text()).get("items", []):
            fam_of[i["item_id"]] = i.get("family", "?")
            title_of[i["item_id"]] = i.get("title", "")
    ps = {}
    if (gdir / "purpose_statement.json").exists():
        ps = json.loads((gdir / "purpose_statement.json").read_text())
    scope = (((ps.get("synthesis") or {}).get("scope_sentence") or {}).get("text") or "")

    ec_color = {"codify": "#1a7f37", "clarify": "#8a5a00", "fill_gap": "#8a5a00",
                "change": "#b42318", "unresolved": "#b42318"}

    # group operations by the family of their first resolvable target
    fams: dict[str, list] = {}
    for op in trace:
        tg = op["operation"].get("targets", [])
        fam = fam_of.get(tg[0]["item_id"], "cross-family") if tg else "cross-family"
        fams.setdefault(fam, []).append(op)

    summary_html = ""
    sp = gdir / "target_blueprint_summary.json"
    if sp.exists():
        summary_html = render_summary_html(json.loads(sp.read_text()))

    ec = {}
    for op in trace:
        c = (op.get("disposition") or {}).get("effect_class", "?")
        ec[c] = ec.get(c, 0) + 1

    body = [f"<h1>Target Blueprint — {_e(program_id)}</h1>",
            f'<div class="meta">Mode: {_e(mode)} · {len(trace)} finalized operations · '
            f'effect classes: {_e(", ".join(f"{k} {v}" for k, v in sorted(ec.items())))} · '
            f'rendered {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</div>',
            f'<div class="scope"><b>Ratified scope.</b> {_e(scope)}</div>',
            summary_html,
            '<div class="meta">This is the Target Blueprint in <b>operation-trace form</b>: the '
            'Derived Blueprint (its element tables) plus the ordered, finalized operations below, '
            'each with the human disposition that approved it. A fully materialized composite — the '
            'element tables rewritten — is a later step (backlog B6). Provision-level accountability '
            '(where every legacy rule went) is in the <b>Crosswalk</b> (Align tab); the underlying '
            'element tables are in the <b>Derived Blueprint</b>.</div>']

    mp = gdir / "ratified_mandate.json"
    if mp.exists():
        m = json.loads(mp.read_text())
        objs = "".join(f"<div class=meta>{_e(o['objective_id'])}: {_e(o['statement'])}</div>"
                       for o in m["objectives"])
        body.append(f'<div class="scope" style="border-left-color:#31456e"><b>Ratified Mandate</b> '
                    f'(the authority for every change below) — ranking {_e(" > ".join(m["ranking"]))}'
                    f'{objs}</div>')

    for fam in sorted(fams):
        ops = fams[fam]
        body.append(f"<h2>{_e(fam)} — {len(ops)} operations</h2>")
        for op in ops:
            d = op.get("disposition") or {}
            cls = d.get("effect_class", "?")
            hook = (op["operation"].get("objective_hook") or {})
            tg = ", ".join(_e(t.get("item_id")) + (f"→{_e(t.get('element_ref'))}" if t.get("element_ref") else "")
                           for t in op["operation"].get("targets", []))
            body.append(
                f'<div class="op"><span class="badge">{_e(op["operation"]["op_type"])}</span>'
                f'<span class="badge" style="color:{ec_color.get(cls, "#5a6172")}">{_e(cls)}</span>'
                f'<span class="meta"> {_e(op.get("op_id"))} · {_e(op.get("_pass"))} pass'
                f'{" · hook " + _e(hook.get("objective_id")) if hook.get("objective_id") else ""}</span>'
                f'<div style="margin-top:3px">{_e(op["operation"].get("proposal", ""))}</div>'
                f'<div class="meta">targets: {tg}</div>'
                f'<div class="meta">⚖ {_e(d.get("action"))} — {_e((d.get("reviewer") or {}).get("name"))} '
                f'({_e((d.get("reviewer") or {}).get("role"))}): {_e(d.get("rationale", ""))[:300]}</div></div>')

    # deferred / parked — the honest "not decided here"
    parked = tgt.get("redesign_backlog", [])
    deferred = tgt.get("deferred_objectives", [])
    if parked or deferred:
        body.append("<h2>Deliberately not decided here</h2>")
        if parked:
            body.append(f'<div class="meta">Parked to the Redesign Backlog (change-class moves the '
                        f'refactor pass refused): {_e(", ".join(parked))}</div>')
        for d in deferred:
            body.append(f'<div class="meta">Objective {_e(d.get("objective_id"))} deferred: '
                        f'{_e(d.get("rationale", ""))}</div>')

    disc = tgt.get("disclosures", {})
    body.append(f'<footer>Ratified by {_e((tgt.get("ratified_by") or {}).get("name"))} '
                f'({_e((tgt.get("ratified_by") or {}).get("role"))}) · content hash {_e(tgt.get("content_hash"))} · '
                f'disclosures: manual effect classification={_e(disc.get("manual_effect_classification"))}, '
                f'{_e(disc.get("adjudication"))}. Derived rendering — the governed store is the source of truth.</footer>')
    extra_css = ".op{border:1px solid #d7dbe4;border-radius:8px;padding:8px 11px;margin:6px 0;font-size:.9rem;}"
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>Target Blueprint — {_e(program_id)}</title>"
            f"<style>{CSS}{extra_css}</style></head><body>{''.join(body)}</body></html>")
