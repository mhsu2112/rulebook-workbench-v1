"""Live eval harness for the purpose-elicitation skill (ADR-011; PRD M1 exit).

Runs the refactor-applicable cases from
rulebook-workbench/evals/purpose-elicitation-cases.md as model-vs-model
conversations: the intake_interview task plays the interviewer (skill
verbatim, D5) while eval_respondent plays a scripted persona; eval_judge then
scores the transcript + synthesized statement against the case's gold labels.

Requires OPENROUTER_API_KEY. Costs real money (rough order: cents/case).
Usage:  python scripts/run_evals.py [C01 C04 ...]   (default: all cases)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from workbench.config import load_registry
from workbench.server import load_dotenv
from workbench.router import ModelRouter
from workbench.server import COMPLETE_MARKER, INTERVIEW_SYSTEM, SYNTHESIS_PROMPT, ServerState

REPO = Path(__file__).resolve().parents[1]
load_dotenv(REPO)
MAX_TURNS = 16

CASES: dict[str, dict] = {
    "C01": {"gold_mode": "refactor", "persona": "You are an agency staffer. Your guidance stock is a mess: 30 years of circulars, nobody can find what applies. You want cleanup only — if asked whether this project should change what the rules require, you firmly say no, park those questions. You can name your agency's guidance as amendable. Answer questions directly and briefly."},
    "C04": {"gold_mode": "refactor", "persona": "You open with 'compliance costs are insane.' Under probing it emerges the costs come from duplicative filings and redundant processes — you do NOT want requirements changed, just deduplicated. Say so when the change-tolerance question comes."},
    "C05": {"gold_mode": "redesign", "persona": "You open with 'compliance costs are insane.' Under probing it emerges you think the thresholds themselves are substantively wrong and should change. When asked whether the project should make such calls, say yes — and if asked by what authority, say your deputy-director boss would own those calls."},
    "C06": {"gold_mode": "refactor", "persona": "You want statutory provisions cleaned up, but your client can amend nothing — it is all statute and there is no legislative appetite. Reveal this at the client/amendability question and see what the interviewer does. If offered re-scopings, entertain but do not immediately accept them."},
    "C07": {"gold_mode": "decomposition", "persona": "You genuinely want two things and present them as one project: cleaning up AML guidance AND overhauling the examination-manual drafting process. Keep them fused until the interviewer explicitly shows you it is two projects."},
    "C09": {"gold_mode": "refactor", "persona": "You are inside the authority, with delegated power to reissue guidance directly. You want your unit's circulars consolidated. Direct posture, cleanup only."},
    "C10": {"gold_mode": "refactor", "persona": "Answer 'park everything' at the change-tolerance question, but later keep proposing substantive fixes ('while we're at it, the threshold should be 250k'). See whether the interviewer surfaces the inconsistency. If confronted, choose to stay in cleanup mode."},
    "C11": {"gold_mode": ["none", "decomposition"], "persona": "Be vague and mildly contradictory. Give evasive answers ('sort of both', 'depends'), contradict an earlier answer once. Do not converge unless the interviewer pins you down with concrete options; even then stay fuzzy on half the questions."},
    "C12": {"gold_mode": "redesign", "persona": "You want liquidity rules redesigned but when asked for objectives, deflect: 'you're the expert, you write the objectives.' Only take ownership of an objective if the interviewer explicitly makes you pick or edit one yourself."},
    "C14": {"gold_mode": "refactor", "persona": "Cooperative cleanup respondent, but when told about the transcript, refuse consent for any verbatim quotes to be published. Proceed otherwise normally."},
    "C15": {"gold_mode": "refactor", "persona": "You are impatient. After two questions, say 'skip the interview, just start the census.' Push twice; if the interviewer explains what would be lost and offers a minimal path, grudgingly cooperate with short answers."},
    "C16": {"gold_mode": "redesign", "persona": "You want AML redesigned. Every 'objective' you offer is a mechanism restatement ('firms should file SARs on time', 'exams should use the manual'). Only give a real outcome if the interviewer pushes past the mechanism at least once."},
}

JUDGE_PROMPT = """You are scoring a purpose-elicitation interview against its case spec.

CASE: {case_id} — gold mode(s): {gold_mode}
Persona the respondent was playing: {persona}

Score per the schema. mode_recommended is what the INTERVIEWER concluded
(or 'decomposition' if it split the project; 'none' if it refused to
conclude / emitted only open items — for an evasive respondent, 'none' with
blocking open items is the CORRECT outcome). unauthorized_adoption is true
only if a non-Principal's objectives/rankings were recorded as adopted
rather than as hypotheses.

===== INTERVIEW TRANSCRIPT =====
{transcript}

===== SYNTHESIZED STATEMENT (may be empty) =====
{statement}
"""


def run_case(router: ModelRouter, skill: str, case_id: str, spec: dict) -> dict:
    system = INTERVIEW_SYSTEM.format(marker=COMPLETE_MARKER, skill=skill)
    interviewer_hist: list[dict] = []
    respondent_hist: list[dict] = [
        {"role": "system", "content": "Roleplay exactly this persona in an interview; stay in character; keep answers under 120 words.\n" + spec["persona"]},
        {"role": "user", "content": "The interview begins. Open by stating your request in one or two sentences."},
    ]
    opening, _ = router.call("eval_respondent", respondent_hist)
    respondent_hist.append({"role": "assistant", "content": opening})
    user_msg = opening
    for _ in range(MAX_TURNS):
        interviewer_hist.append({"role": "user", "content": user_msg})
        q, _ = router.call("intake_interview", [{"role": "system", "content": system}] + interviewer_hist)
        interviewer_hist.append({"role": "assistant", "content": q})
        if COMPLETE_MARKER in q:
            break
        respondent_hist.append({"role": "user", "content": q})
        a, _ = router.call("eval_respondent", respondent_hist)
        respondent_hist.append({"role": "assistant", "content": a})
        user_msg = a

    transcript = "\n\n".join(f"[{m['role'].upper()}]\n{m['content']}" for m in interviewer_hist)
    statement = ""
    try:
        doc, _ = router.call("purpose_synthesis", [{"role": "user", "content": SYNTHESIS_PROMPT.format(
            program_id=f"eval-{case_id.lower()}", transcript_ref="(eval)", transcript=transcript)}])
        statement = json.dumps(doc, indent=2)
    except Exception as e:  # synthesis failure is itself a scored fact
        statement = f"(synthesis failed: {e})"

    verdict, _ = router.call("eval_judge", [{"role": "user", "content": JUDGE_PROMPT.format(
        case_id=case_id, gold_mode=spec["gold_mode"], persona=spec["persona"],
        transcript=transcript, statement=statement)}])
    n_questions = sum(1 for m in interviewer_hist if m["role"] == "assistant")
    gold = spec["gold_mode"] if isinstance(spec["gold_mode"], list) else [spec["gold_mode"]]
    verdict.update({
        "case": case_id, "gold_mode": spec["gold_mode"],
        "mode_ok": verdict["mode_recommended"] in gold,
        "questions_asked": n_questions,
        "budget_ok": n_questions <= 14,
    })
    return verdict


def main() -> int:
    import os
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    wanted = args or list(CASES)
    registry = load_registry(REPO / "models.yaml")
    budget = float(os.environ.get("EVAL_BUDGET_USD", "15"))
    router = ModelRouter(registry=registry, budget_usd=budget)
    skill = ServerState(REPO).skill_text
    out_dir = REPO / "evals-out"
    out_dir.mkdir(exist_ok=True)
    # Resume by default: completed cases are skipped unless --force.
    done = {cid for cid in wanted if (out_dir / f"{cid}.json").exists()}
    if done and not force:
        print(f"resuming — skipping already-completed: {', '.join(sorted(done))}")
        wanted = [c for c in wanted if c not in done]
    results = []
    for cid in wanted:
        print(f"— running {cid} …", flush=True)
        try:
            v = run_case(router, skill, cid, CASES[cid])
        except Exception as e:  # one broken case never kills the run; budget stop ends it cleanly
            print(f"  ERROR on {cid}: {e}")
            if "budget" in str(e).lower():
                print(f"  budget ${budget:.2f} exhausted — completed cases are saved; "
                      f"rerun `make evals` (or raise EVAL_BUDGET_USD) to continue from here")
                break
            (out_dir / f"{cid}.error.txt").write_text(str(e))
            continue
        results.append(v)
        (out_dir / f"{cid}.json").write_text(json.dumps(v, indent=2))
        flag = "PASS" if (v["mode_ok"] and not v["unauthorized_adoption"]
                          and not v["agent_invented_objectives"] and v["budget_ok"]) else "FAIL"
        print(f"  {flag}  mode={v['mode_recommended']} (gold {v['gold_mode']})  "
              f"q={v['questions_asked']}  adoption_leak={v['unauthorized_adoption']}  "
              f"invented={v['agent_invented_objectives']}")

    # Summarize EVERYTHING on disk, not just this run's cases.
    all_v = [json.loads((out_dir / f"{c}.json").read_text())
             for c in CASES if (out_dir / f"{c}.json").exists()]
    passed = sum(1 for v in all_v if v["mode_ok"] and not v["unauthorized_adoption"]
                 and not v["agent_invented_objectives"] and v["budget_ok"])
    print(f"\nSuite: {passed}/{len(all_v)} pass, {len(CASES) - len(all_v)} not yet run "
          f"— details in evals-out/  (this run spent ${router.spent_usd:.4f})")
    return 0 if passed == len(all_v) and len(all_v) == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
