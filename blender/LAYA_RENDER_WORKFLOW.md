# Laya AI + Render MCP Designer — what was implemented

This is the implementation of `Laya_Render_MCP_3D_Design_Workflow.docx` against this repository
(Blender artifacts plus the render sheet in `mcp-demo/`). It follows the briefing's own
architecture rather than inventing one: a creative model proposes, validators and a visual
reviewer assess the *editable scene and its renders*, Laya routes the next step from structured
evidence, and the Render MCP Designer makes only approved changes.

Everything below was verified against the artifacts in this repository and the real interfaces of
both systems. Where a claim could not be verified, the code says `not_run` instead of `pass`.

## Verified interfaces (the brief's "stage 0 — inspect")

| System | What was verified | How |
|---|---|---|
| Laya | question contract `{type: choice/noul/score, instructions, criteria}`; answer contract (`choice`, `probabilities`, `confidence`, `answer_confidence`, `low_confidence`); `min_confidence` gating; CLI `laya "<state>" --questions FILE --predict --json` | read from a local Laya checkout (`laya/agent.py`, `laya/common.py`, `laya/structured.py`, `laya/cli.py`, README) |
| Laya runtime | **installed and answering here**: `torch 2.14.1+cpu`, `transformers 5.19.0`, `safetensors 0.8.0`, `huggingface_hub 1.33.0`, `laya 0.3.28` (editable install of the local checkout); checkpoint at `~/laya_models` (`model.safetensors`, 842,609,210 bytes, plus the required `rl_agent_config.json`) | `import torch, transformers, laya` succeed; a cold in-process load of the checkpoint takes ~32 s on CPU and then answers |
| Render MCP Designer | live tool surface: `get_scene_info`, `get_object_info`, `get_viewport_screenshot`, `describe_node_type` (read); `execute_blender_code` (the single write primitive); `export_scene` (delivery) | queried the connected Blender MCP server |
| Scene artifact | `jet-kite.glb`: 43 mesh objects, 9 materials, 7450 triangles, extents `[2.415, 0.706, 3.412] m`, revision `a49e86e4…` | parsed the GLB's JSON chunk |
| Canonical cameras | `Cam_Hero`, `Cam_Belly`, `Cam_Bay`, `Cam_Cockpit`, scene `JetKite`, 1200×800 | PNG text chunks of the existing renders in `mcp-demo/` |

## The layer map

```
layarender/
  contracts.py    brief -> mandatory, machine-checkable requirements
  scene.py        reads the editable scene (.glb/.gltf) with no Blender; SceneContext for cameras/lights
  views.py        canonical views + the render fingerprint that makes comparisons meaningful
  policy.py       operation allowlist, write scope, typed targets, approval gates
  preflight.py    rejects out-of-scope / out-of-unit / unsupported / unverifiable plans pre-execution
  validators.py   deterministic checks; "not run" is never reported as "pass"
  reviewer.py     located visual findings, measured from renders; rejects unlocated critique
  adapters/
    transport.py    MCP plumbing (recording, JSONL replay, real stdio client)
    render_mcp.py   the only module that can write to the scene
    laya_ai.py      the only module that can produce a routing decision (fails closed)
  control.py      the bounded loop: assess, propose, gate, apply, render, review, route, stop
  calibrate.py    measures whether Laya's route answer can be trusted before it is gated on
  report.py       delivery report separating what ran from what was judged
  cli.py          inspect | contract | validate | review | plan | run | calibrate | report
```

## How each requirement in the brief is met

| Brief | Implementation |
|---|---|
| Separate proposing, deciding, building, reviewing | `Planner` / `LayaAdapter` / `RenderMcpAdapter` / `MeasuredReviewer` are four objects with no shared state |
| The editable scene is the source of truth | `run_scene_checks` validates `jet-kite.glb` itself (objects, dimensions, materials, triangle budget, export validity), independently of any image |
| Specify spatial requirements | `contracts/jet-kite.json` pins units, axis convention, fuselage length 2.30–2.50 m, wing span 0.85–1.00 m, polygon budget, write scope |
| Ground generation in real project context | the evidence pack is built from the measured scene summary, the contract, prior findings and check outcomes — never a project dump |
| Review structure *and* pixels | tests are split: 19 deterministic checks vs. located findings from measured renders |
| Critique becomes small, located edits | `PolicyPlanner` maps one located finding to one operation on one target; a criterion it cannot fix yields no plan, and the loop escalates instead of guessing |
| Bound iteration, preserve versions | `max_revision_rounds` from the contract; `RunState` records every round, decision, view, check, finding and score |
| Review both structure and pixels; never infer from one image | `check_export` re-reads the delivery file; a pretty render never satisfies a structural requirement |
| Laya routes from structured evidence | `LayaAdapter.choose_next_step(state, allowed_routes, …)` with the question built per state |
| MCP writes are scoped, validated, bounded, approval-gated | `preflight_plan` + `OperationPolicy.gate` + `RenderMcpAdapter.apply_patch` (which refuses anything not preflighted) |
| Fail closed on Laya timeout / malformed output | `LayaUnavailable` / `LayaMalformed` → `human_review` with `source=unavailable`; the gated write is never applied |
| The workflow can stop, branch or escalate — never loop forever | four recorded endings: `accepted`, `needs_human_review`, `budget_exhausted`, `blocked`; `accept` requires *both* Laya's route and every mandatory check passing |
| Final report distinguishes ran from not-run | `final_report()` returns `checks_ran`, `checks_not_run`, `checks_failed`, `measured_findings`, `judged_findings`, `limitations` |

## Evidence from this repository

**Deterministic checks — all 19 pass on the shipped scene** (real, offline, no model):

```
python -m layarender validate --contract contracts/jet-kite.json --scene jet-kite.glb \
  --view hero=mcp-demo/jetkite_hero.png --view belly=mcp-demo/jetkite_belly.png \
  --view bay=mcp-demo/jetkite_bay.png
```

**Visual review — measured findings on the real render sheet:**

```
python -m layarender review --contract contracts/jet-kite.json \
  --image hero=mcp-demo/jetkite_hero.png --image bay=mcp-demo/jetkite_bay.png
```

The reviewer separates subject from backdrop with a border-seeded flood fill (a local similarity
test, so a gradient backdrop is followed rather than mistaken for the subject). On the hero view
it recovers the jet's actual silhouette; when a view cannot be separated it reports
*"framing could not be measured"* instead of inventing a coverage number.

**Control loop — fail-closed, on the real scene:**

```
python -m layarender run --contract contracts/jet-kite.json --scene jet-kite.glb \
  --scene-context contracts/jet-kite.scene-context.json --laya in-process \
  --existing-view hero=mcp-demo/jetkite_hero.png --existing-view belly=mcp-demo/jetkite_belly.png \
  --existing-view bay=mcp-demo/jetkite_bay.png --existing-view cockpit=mcp-demo/jetkite_cockpit.png
```

Observed on a live run (**Laya is the decision maker, not a stub**): round 0 assesses the scene
(19 checks pass, 4 measured + 2 judged findings); the model answers the route question
`accept_candidate` at confidence 0.415 and, asked separately which failing criterion to fix first,
`subject_fully_inside_the_frame` at confidence 0.724; the gate holds because 0.415 is below the
0.60 threshold, so round 1 asks again (`revise_candidate`, 0.373) and the run ends
`needs_human_review`. **Nothing was written to the scene.**

That run is the whole design in one example: the model's route answer was wrong (it asked to
accept a scene whose hero silhouette fails to separate from the backdrop), its confidences were
correctly low, and the workflow refused to follow it — while recording the one answer it *was*
confident about so a person knows where to start. The report says so explicitly:

```
next action (what the evidence points at):
  highest-priority criterion : subject_fully_inside_the_frame
  described as               : subject fully inside the frame on belly
  the model's confidence here: 0.724
  views with failing findings: bay, belly, cockpit, hero
  the model's route answer   : accept_candidate (from laya-in-process, confidence 0.415)
```

The suite `python tests/test_layarender.py` holds these properties with 44 checks (including the
fail-closed paths, preflight rejections, stale-reference detection, located-findings enforcement,
loop termination, and the calibration probe's ability to detect a positional answer), and
`python tests/test_laya_adapter_live.py` adds 10 checks that run against the **real** runtime —
they assert Laya's answer sums to one, that the decision is attributed to `laya`, that the gate
really blocks, and that the question shape is accepted by the model. Those live checks report
`skip` (never `pass`) when the runtime is absent.

## Is the route answer trustworthy? The calibration probe

`python -m layarender calibrate` answers the brief's stage 4 directly, and only needs the model to
be reachable. It measures three things and refuses to average them into a single score:

* **determinism** — the same state and question are asked repeatedly; a model that changes its
  answer run to run cannot be gated on at all;
* **position invariance** — the same options are offered in every ordering. A model that reads the
  options keeps its label (the slot it sits in moves); a model that follows position keeps its
  slot. This is the failure a confidence threshold can never catch, because a positional answer
  reports high confidence;
* **a threshold table** — how confident the answer actually is at each gate, so the 0.60 default
  can be set from measurement instead of taste.

On this project the verdict is **NOT TRUSTWORTHY**, and the reason is honest rather than a bug:
the route answer is *stable* (it does not move with option order) but reports **0.37–0.42**,
below the 0.60 gate. Laya is not answering the route question badly — it is telling the truth
about how unsure it is, and the gate is doing its job by failing closed.

## Deployment choice, and what it costs

The brief's table offers three ways to expose Laya. This implementation takes **"connect Laya
alongside the Render MCP Designer… behind an adapter boundary"**, because it needs no new service
and keeps both native schemas separate. `build_laya_adapter(mode=…)` selects the transport:

| mode | what it needs | state today |
|---|---|---|
| `in-process` | `torch`, `transformers`, a checkpoint | **working** — loads `~/laya_models` and answers (this is the mode the live run above used) |
| `cli` | the `laya` CLI plus the same runtime | working — the same runtime, invoked as a subprocess |
| `mcp` | a transport to `laya_predict` / `laya_decide` | adapter ready; no such server is connected here |
| `auto` | tries in-process → CLI → MCP | reports which runner answered |
| `none` | nothing; every route returns `human_review` | this is what a shadow run uses |

The checkpoint is resolved without configuration: `--laya-model` defaults to
`convaiinnovations/laya`, and the adapter prefers a *complete local directory* (one that holds both
`model.safetensors` and `rl_agent_config.json`, in `$LAYA_MODEL_DIR` or `~/laya_models`) over the
network. Anything less and it reports `hub` rather than silently loading a half-checkpoint.

## Honest limits

* **Laya answers, but its route answer does not clear the gate.** Live runs end
  `needs_human_review` because the model reports 0.37–0.42 against the 0.60 threshold. This is the
  gate working, not a wiring failure: the model is genuinely unsure which of the four routes is
  right, and the workflow treats an unsure answer as missing evidence rather than a weak
  preference.
* **Laya's first choice on this project is wrong.** Asked whether to accept the scene, it answered
  `accept_candidate` — while the measured review shows the hero silhouette failing to separate
  from the background (contrast 0.027) and three views clipping the subject. The adapter records
  the disagreement as an explicit guardrail (`the model asked to accept, but measured findings fail
  on bay, belly, cockpit, hero`) instead of silently following it.
* **The checkpoint ships temperatures Laya itself refuses to trust.** On every load Laya warns that
  the checkpoint's temperatures are out of range and substitutes a fallback, so its
  `answer_confidence` values arrive flagged *uncalibrated*. The adapter surfaces that caveat on
  every decision rather than hiding it. Treat the *ranking* of the priority answers as the signal,
  not the absolute numbers.
* **The reliable signal is the priority answer, not the route.** Laya is unsure which route to take
  but highly confident *which* criterion to fix (0.72–1.00 across the failing criteria). That is
  why the report prints the priority criterion, the model's confidence in it, and the views with
  failing findings — the actionable output of an otherwise failed-closed run.
* **Only cameras are in the scene context, and only because renders name them.** The scene's
  lights are absent from both the export and the renders, so light-targeted operations come back
  as *needs a person*. Once `get_scene_info` is captured for the JetKite scene, record the light
  names in `contracts/jet-kite.scene-context.json` and lighting fixes become automatic.
* **Writes are always shadow-mode by default.** `--apply` is required to leave shadow mode, and
  approval-flagged operations additionally need `--approve`.
* **The visual reviewer measures structure and composition, not taste.** Lighting mood, brand fit
  and material intent remain a human or vision-model judgement; those findings are labelled
  `judged`, never `measured`.
