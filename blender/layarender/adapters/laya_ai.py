"""The Laya adapter: the workflow's only path to a Laya decision.

Doc, section 3: "create a small adapter boundary first. Keep Laya-specific calls behind an
interface such as ``evaluate_scene_state(state, questions)``... Then the workflow can map to the
capabilities that are actually available without pretending that illustrative names are real
APIs."

This module was written against Laya's real interface, verified from its source:

* Questions are ``{id: {"type": "choice"|"noul"|"score", "instructions": ..., "criteria": {...}}}``
  (``laya/common.render_options``, ``laya/structured``).
* An answering call returns ``{"answers": {qid: {...}}}`` where a ``choice`` answer carries
  ``choice``, ``probabilities``, ``confidence`` and ``answer_confidence``; a ``noul`` answer
  carries ``noul`` (P(true)); a ``score`` answer carries ``score`` (``laya/agent.py``).
* ``min_confidence`` is a real argument and a gated answer comes back flagged
  ``low_confidence`` (``laya/structured._project``).
* The CLI answers a question file: ``laya "<state>" --questions FILE --predict --json``
  (``laya/cli.py``).
* The MCP server exposes ``laya_decide`` / ``laya_predict`` / ``laya_shortlist``
  (Laya README, MCP section).

Three runners ship, all behind one interface:

``InProcessLayaRunner``  ``laya.load(...)`` + ``agent.predict``. Needs torch and weights.
``CliLayaRunner``        the ``laya`` CLI as a subprocess. Needs the CLI and weights.
``McpLayaRunner``        calls a Laya MCP tool through a transport.

Every failure mode the doc names is handled the same way: **fail closed**. A timeout, a missing
checkpoint, a malformed answer or a confidence below the threshold never produces a route that
could write to the scene. It produces ``HUMAN_REVIEW`` with ``source == "unavailable"`` and the
reason recorded, and the workflow then refuses to apply the gated write.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..models import Decision, DecisionSource, Route

DEFAULT_MIN_CONFIDENCE = 0.60
DEFAULT_TIMEOUT_S = 60.0
DEFAULT_MODEL_ID = "convaiinnovations/laya"

# Model caveats verified from Laya's own documentation, recorded on every decision so a report
# never overstates what the decision means:
#   * "The base checkpoints are near chance on typed-decisions zero-shot."
#   * "Avoid boolean-word labels in choice questions... Use semantic labels or opaque labels."
#   * "These narrow cancellation examples are not evidence that every negated state fails."
MODEL_CAVEATS = [
    "laya base checkpoints are near chance on typed-decisions zero-shot; gate on confidence "
    "and calibrate against your own evaluation set",
    "choice labels are rendered verbatim; this adapter uses semantic, non-boolean labels",
    "confidence AUROC is ~0.77 on the reported set, so a low-confidence answer is treated as "
    "missing evidence, not as a weak preference",
]


class LayaUnavailable(RuntimeError):
    """No Laya runner could be built (missing package, weights, CLI or MCP tool)."""


class LayaMalformed(RuntimeError):
    """Laya answered, but the answer cannot be read as the question that was asked."""


@dataclass
class LayaAnswer:
    """A normalized answer to one question."""

    question: str
    label: Optional[str] = None
    probability: Optional[float] = None
    confidence: Optional[float] = None
    answer_confidence: Optional[float] = None
    kind: str = "choice"
    low_confidence: bool = False
    native: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question, "label": self.label, "probability": self.probability,
            "confidence": self.confidence, "answer_confidence": self.answer_confidence,
            "kind": self.kind, "low_confidence": self.low_confidence, "native": self.native,
        }


def _version_of(module: Any) -> str:
    for attribute in ("__version__", "VERSION"):
        value = getattr(module, attribute, None)
        if isinstance(value, str):
            return value
    return "unknown"


def _is_local_checkpoint(path: str) -> bool:
    """True when `path` is a directory that holds a complete Laya checkpoint.

    `rl_agent_config.json` is the marker ``laya.agent.Agent`` itself requires, so the same test
    that decides whether a path can be loaded is used here rather than a looser one that would
    accept a half-downloaded directory.
    """
    return (os.path.isdir(path)
            and os.path.isfile(os.path.join(path, "rl_agent_config.json"))
            and os.path.isfile(os.path.join(path, "model.safetensors")))


def resolve_local_checkpoint(model_id: str) -> Optional[str]:
    """Prefer an already-downloaded checkpoint over a Hub fetch of the same weights.

    ``LAYA_MODEL_DIR`` (or the conventional ``~/laya_models``) is checked first, but only when the
    caller did not ask for a specific path or repository of their own. 803 MB of weights on a slow
    link is the difference between a workflow that runs and one that does not, and re-downloading
    a checkpoint that is already on disk adds no reproducibility that the recorded path does not.
    The resolved path is put in ``detail`` so every decision log says which weights answered.
    """
    if model_id != DEFAULT_MODEL_ID:
        return model_id
    for candidate in (os.environ.get("LAYA_MODEL_DIR"),
                      os.path.expanduser("~/laya_models")):
        if candidate and _is_local_checkpoint(candidate):
            # Normalised because the expanded path mixes separators on Windows
            # (``C:\Users\me/laya_models``), and this string is written into every decision log.
            return os.path.normpath(candidate)
    return model_id


class LayaRunner:
    """The runner interface: answer a question set about a state."""

    name = "runner"
    detail: Dict[str, Any] = {}

    def available(self) -> bool:
        return False

    def answer(self, state_text: str, questions: Dict[str, Dict[str, Any]],
               min_confidence: float, timeout: float) -> Dict[str, Any]:
        raise LayaUnavailable("%s is not usable" % self.name)

    def version(self) -> Dict[str, Any]:
        return {"runner": self.name, **self.detail}


@dataclass
class InProcessLayaRunner(LayaRunner):
    """Answer in this process through ``laya.load`` + ``agent.predict``.

    The import and the checkpoint load are both lazy and both fallible, so the runner reports
    why it is unusable instead of raising at workflow start.
    """

    model_id: str = DEFAULT_MODEL_ID
    device: Optional[str] = None
    subfolder: Optional[str] = None
    name: str = "laya-in-process"
    _agent: Any = None
    _error: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def _load(self) -> Any:
        if self._agent is not None:
            return self._agent
        if self._error is not None:
            raise LayaUnavailable(self._error)
        try:
            import laya  # type: ignore
        except Exception as error:
            self._error = ("the laya package is not importable in this interpreter: %s" % error)
            raise LayaUnavailable(self._error) from None
        resolved = resolve_local_checkpoint(self.model_id)
        try:
            kwargs: Dict[str, Any] = {"model_id_or_path": resolved}
            if self.device:
                kwargs["device"] = self.device
            if self.subfolder:
                kwargs["subfolder"] = self.subfolder
            self._agent = laya.load(**kwargs) if hasattr(laya, "load") else laya.Agent(**kwargs)
        except Exception as error:
            self._error = "laya could not load %r: %s" % (resolved, error)
            raise LayaUnavailable(self._error) from None
        self.detail = {"model_id": resolved, "laya_version": _version_of(laya),
                       "requested_model_id": self.model_id,
                       "device": self.device or "auto", "subfolder": self.subfolder,
                       "from": "local_dir" if resolved != self.model_id else "hub"}
        return self._agent

    def available(self) -> bool:
        try:
            self._load()
            return True
        except LayaUnavailable:
            return False

    def answer(self, state_text: str, questions: Dict[str, Dict[str, Any]],
               min_confidence: float, timeout: float) -> Dict[str, Any]:
        agent = self._load()
        started = time.time()
        try:
            result = agent.predict(state_text, questions, min_confidence=min_confidence)
        except TypeError as error:
            if "min_confidence" not in str(error):
                raise LayaMalformed("laya.predict failed: %s" % error) from None
            # Older/newer signature without the gate: gate in this adapter instead, which is
            # deterministic and does not depend on the checkpoint's flags.
            result = agent.predict(state_text, questions)
        self.detail["last_latency_ms"] = round((time.time() - started) * 1000, 2)
        return {"result": result, "latency_ms": self.detail["last_latency_ms"]}


@dataclass
class CliLayaRunner(LayaRunner):
    """Answer through the ``laya`` CLI as a subprocess.

    Deliberately isolated: the control plane does not need torch, a checkpoint does not need to
    be resident between rounds, and a hung process is bounded by ``timeout`` instead of hanging
    the workflow. The CLI is invoked exactly as its own help documents:
    ``laya "<state>" --questions FILE --predict --json``.
    """

    executable: Any = "laya"
    name: str = "laya-cli"
    detail: Dict[str, Any] = field(default_factory=dict)
    _probe: Optional[bool] = None

    def _command_prefix(self) -> List[str]:
        """The command as a list, so ``["python", "-m", "laya.cli"]`` works as well as ``"laya"``."""
        if isinstance(self.executable, (list, tuple)):
            return [str(part) for part in self.executable]
        return [str(self.executable)]

    def _cwd(self) -> Optional[str]:
        """Run from a checkout that has the package on the path when one is configured."""
        return self.detail.get("cwd")

    def available(self) -> bool:
        if self._probe is not None:
            return self._probe
        try:
            completed = subprocess.run(self._command_prefix() + ["--help"], capture_output=True,
                                       text=True, timeout=30, cwd=self._cwd())
            self._probe = completed.returncode == 0
            if self._probe:
                self.detail.setdefault("executable", " ".join(self._command_prefix()))
        except Exception as error:
            self.detail["probe_error"] = str(error)
            self._probe = False
        return self._probe

    def answer(self, state_text: str, questions: Dict[str, Dict[str, Any]],
               min_confidence: float, timeout: float) -> Dict[str, Any]:
        if not self.available():
            raise LayaUnavailable("the laya CLI is not runnable as %r (%s)"
                                  % (self.executable, self.detail.get("probe_error", "")))
        handle, path = tempfile.mkstemp(prefix="layarender-questions-", suffix=".json")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(questions, stream)
        command = self._command_prefix() + [state_text, "--questions", path, "--predict", "--json",
                                           "--min-confidence", str(min_confidence)]
        started = time.time()
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                                       cwd=self._cwd())
        except subprocess.TimeoutExpired:
            raise LayaUnavailable("the laya CLI exceeded %.1fs" % timeout) from None
        except Exception as error:
            raise LayaUnavailable("the laya CLI could not be run: %s" % error) from None
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        latency = round((time.time() - started) * 1000, 2)
        if completed.returncode != 0:
            raise LayaUnavailable("the laya CLI exited %d: %s"
                                  % (completed.returncode,
                                     (completed.stderr or completed.stdout or "").strip()[:400]))
        stdout = (completed.stdout or "").strip()
        if not stdout:
            raise LayaMalformed("the laya CLI printed nothing")
        line = stdout.splitlines()[-1] if not stdout.startswith("{") else stdout
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            raise LayaMalformed("the laya CLI output is not JSON: %s" % stdout[:200]) from None
        return {"result": payload, "latency_ms": latency}


@dataclass
class McpLayaRunner(LayaRunner):
    """Answer through a Laya MCP tool over a transport (``laya_decide`` / ``laya_predict``).

    This is the doc's "connect Laya alongside Render MCP Designer" deployment: the same host that
    holds the scene tools holds the decision tool, and this adapter only has to speak the tool's
    argument shape.
    """

    transport: Any = None
    tool: str = "laya_predict"
    model: Optional[str] = None
    name: str = "laya-mcp"
    detail: Dict[str, Any] = field(default_factory=dict)

    def available(self) -> bool:
        return self.transport is not None

    def answer(self, state_text: str, questions: Dict[str, Dict[str, Any]],
               min_confidence: float, timeout: float) -> Dict[str, Any]:
        if self.transport is None:
            raise LayaUnavailable("no MCP transport was provided for the Laya tool")
        arguments: Dict[str, Any] = {"state": state_text, "questions": questions,
                                     "min_confidence": min_confidence}
        if self.model:
            arguments["model"] = self.model
        started = time.time()
        try:
            payload = self.transport.call(self.tool, arguments, read_only=True)
        except Exception as error:
            raise LayaUnavailable("the %s call failed: %s" % (self.tool, error)) from None
        latency = round((time.time() - started) * 1000, 2)
        if isinstance(payload, dict) and "answers" in payload:
            return {"result": payload, "latency_ms": latency}
        if isinstance(payload, dict) and "result" in payload:
            return {"result": payload["result"], "latency_ms": latency}
        raise LayaMalformed("the %s tool returned an unexpected payload: %r"
                            % (self.tool, str(payload)[:200]))


# ---- the workflow's own question vocabulary --------------------------------------------
# Labels are semantic (never true/false/yes/no, which Laya's README warns the checkpoints can
# follow instead of the option text) and stable, so a decision log stays readable.
ROUTE_LABELS: Dict[str, str] = {
    Route.REVISE.value: "revise_candidate",
    Route.BRANCH.value: "branch_composition",
    Route.ACCEPT.value: "accept_candidate",
    Route.HUMAN_REVIEW.value: "ask_a_person",
}
LABEL_TO_ROUTE: Dict[str, str] = {label: route for route, label in ROUTE_LABELS.items()}

ROUTE_DESCRIPTIONS: Dict[str, str] = {
    Route.REVISE.value:
        "fix the single highest-priority failing criterion on the named object or view and "
        "render again",
    Route.BRANCH.value:
        "stop editing this candidate and build a different composition or modelling direction",
    Route.ACCEPT.value:
        "the evidence is sufficient and the scene can be handed to a person as finished",
    Route.HUMAN_REVIEW.value:
        "the evidence is missing, conflicting, or too high-impact to decide automatically",
}


def normalise_route(value: str) -> Optional[str]:
    """Accept either a route key (``revise``) or a question label (``revise_candidate``).

    Callers reach for both spellings, because a decision log is written in labels while the
    deterministic layer speaks in keys. Accepting only one of them invites a question with no
    criteria, which Laya rejects with a message about the model rather than the caller, so the
    mapping is resolved here once.
    """
    if value in ROUTE_LABELS:
        return value
    if value in LABEL_TO_ROUTE:
        return LABEL_TO_ROUTE[value]
    return None


def _priority_criteria(priority_options: Any) -> Dict[str, str]:
    """Normalise the priority options to ``{id: description}``.

    Both spellings are accepted because both are natural at the call site: a plain list for
    options whose own text is the description, and a mapping when the workflow needs a short,
    stable id to act on (a failing criterion is a sentence, not an identifier).
    """
    if isinstance(priority_options, dict):
        return {str(key): str(value) for key, value in priority_options.items()}
    return {str(option): str(option).replace("_", " ") for option in (priority_options or [])}


def route_question(allowed_routes: List[str], priority_options: Any) -> Dict[str, Dict[str, Any]]:
    """Build the question set sent to Laya: one narrow route question, one priority question.

    The route question is restricted to the routes the deterministic layer already considers
    legal, so Laya is choosing between real options rather than being asked to invent one. The
    priority question is skipped when there is nothing to prioritise, which keeps the request
    small and matches the doc's "ask one narrow question at a time".

    Every criterion is mandatory: a choice question with no criteria is rejected outright by the
    model, and a route the workflow cannot name is better reported to the caller than sent as a
    question the model is free to answer with something the workflow cannot act on.
    """
    keys: List[str] = []
    unknown: List[str] = []
    for route in allowed_routes:
        key = normalise_route(route)
        if key is None:
            unknown.append(route)
        elif key not in keys:
            keys.append(key)
    if unknown:
        raise ValueError("unknown route(s) %s; expected any of %s"
                         % (sorted(unknown), sorted(ROUTE_LABELS)))
    if not keys:
        raise ValueError("route_question needs at least one allowed route to offer")
    criteria = {ROUTE_LABELS[key]: ROUTE_DESCRIPTIONS[key] for key in keys}
    questions: Dict[str, Dict[str, Any]] = {
        "route": {
            "type": "choice",
            "instructions": ("Given the scene state and the structured review evidence, which "
                             "single next step is best for this 3D scene?"),
            "criteria": criteria,
        }
    }
    criteria_for_priority = _priority_criteria(priority_options)
    if criteria_for_priority:
        questions["priority"] = {
            "type": "choice",
            "instructions": ("Which single failing criterion should be addressed first? Prefer "
                             "the one with the highest severity and the clearest located fix."),
            "criteria": criteria_for_priority,
        }
    return questions


@dataclass
class LayaAdapter:
    """``evaluate_scene_state`` / ``choose_next_step`` over whichever Laya runner is usable.

    The adapter owns three things and nothing else: building the narrow question, reading the
    answer, and refusing to produce a route when the answer cannot be trusted. It never decides
    what is legal -- that comes in as ``allowed_routes`` from the deterministic layer -- and it
    never writes to the scene.
    """

    runner: Optional[LayaRunner] = None
    min_confidence: float = DEFAULT_MIN_CONFIDENCE
    timeout: float = DEFAULT_TIMEOUT_S
    max_state_chars: int = 6000
    fallback_runners: List[LayaRunner] = field(default_factory=list)
    calls: List[Dict[str, Any]] = field(default_factory=list)

    def active_runner(self) -> Optional[LayaRunner]:
        candidates: List[LayaRunner] = []
        if self.runner is not None:
            candidates.append(self.runner)
        candidates.extend(self.fallback_runners)
        for candidate in candidates:
            try:
                if candidate.available():
                    return candidate
            except Exception:
                continue
        return None

    def describe(self) -> Dict[str, Any]:
        runner = self.active_runner()
        return {
            "available": runner is not None,
            "runner": runner.name if runner else None,
            "min_confidence": self.min_confidence,
            "timeout_s": self.timeout,
            "version": runner.version() if runner else {},
            "caveats": list(MODEL_CAVEATS),
        }

    # ---- the narrow question -----------------------------------------------------------
    def evaluate_scene_state(self, state: Any, questions: Optional[Dict[str, Dict[str, Any]]] = None,
                             allowed_routes: Optional[List[str]] = None,
                             priority_options: Any = None) -> Dict[str, Any]:
        """Ask Laya for a routing decision about ``state``.

        Returns a dict with ``answers`` (normalized), ``route`` (or ``None`` when the answer is
        unusable) and ``reason``. It raises only when the caller asked for something impossible;
        an unusable model is a normal, recorded outcome, not an exception.
        """
        routes = list(allowed_routes or [Route.REVISE.value, Route.BRANCH.value,
                                        Route.HUMAN_REVIEW.value])
        if questions is None:
            try:
                questions = route_question(routes, priority_options)
            except ValueError as error:
                # An unanswerable question is a workflow defect, but it must not take the whole
                # loop down with it: the doc's rule is that a decision the workflow cannot trust
                # fails closed to a person, so the run records why and continues.
                reason = "the route question could not be built: %s" % error
                self.calls.append({"ok": False, "reason": reason})
                return {"answers": {}, "route": None, "reason": reason, "runner": None,
                        "latency_ms": None}
        state_text = _state_text(state, self.max_state_chars)
        runner = self.active_runner()
        if runner is None:
            reason = "no Laya runner is available: %s" % _why_unavailable(self.runner,
                                                                         self.fallback_runners)
            self.calls.append({"ok": False, "reason": reason, "state_chars": len(state_text)})
            return {"answers": {}, "route": None, "reason": reason, "runner": None,
                    "latency_ms": None}
        try:
            outcome = runner.answer(state_text, questions, self.min_confidence, self.timeout)
        except LayaUnavailable as error:
            reason = "Laya is unavailable: %s" % error
            self.calls.append({"ok": False, "reason": reason, "runner": runner.name})
            return {"answers": {}, "route": None, "reason": reason, "runner": runner.name,
                    "latency_ms": None}
        except LayaMalformed as error:
            reason = "Laya returned something unreadable: %s" % error
            self.calls.append({"ok": False, "reason": reason, "runner": runner.name})
            return {"answers": {}, "route": None, "reason": reason, "runner": runner.name,
                    "latency_ms": None}
        except Exception as error:
            reason = "Laya failed: %s: %s" % (type(error).__name__, error)
            self.calls.append({"ok": False, "reason": reason, "runner": runner.name})
            return {"answers": {}, "route": None, "reason": reason, "runner": runner.name,
                    "latency_ms": None}
        answers, malformed = _project_answers(outcome.get("result"), self.min_confidence)
        self.calls.append({"ok": not malformed, "reason": malformed, "runner": runner.name,
                           "latency_ms": outcome.get("latency_ms")})
        route = None
        reason = malformed or ""
        if not malformed and "route" in answers:
            label = answers["route"].label
            route = LABEL_TO_ROUTE.get(label or "")
            if route is None:
                reason = ("Laya chose label %r, which is not one of the legal routes %s"
                          % (label, routes))
        return {"answers": answers, "route": route, "reason": reason, "runner": runner.name,
                "latency_ms": outcome.get("latency_ms"),
                "allowed_routes": routes, "questions": _recordable_questions(questions)}

    # ---- the routing decision ----------------------------------------------------------
    def choose_next_step(self, state: Any, allowed_routes: List[str],
                         priority_options: Any = None,
                         hard_failures: Optional[List[str]] = None,
                         fallback_reason: str = "") -> Decision:
        """Route the next pass, failing closed whenever Laya cannot answer safely.

        The deterministic layer passes ``allowed_routes``; this method can only choose among
        them. Four outcomes are possible:

        * Laya answered inside the allowed set -> ``source == "laya"``.
        * Laya answered ``accept_candidate`` while ``accept`` was not allowed -> a recorded
          guardrail override, never a silent acceptance.
        * Laya answered below the confidence threshold, or with an unusable label ->
          ``human_review`` with ``source == "unavailable"``.
        * No runner at all -> ``human_review`` with ``source == "unavailable"`` and the reason.
        """
        if not allowed_routes:
            return Decision(route=Route.HUMAN_REVIEW.value, source=DecisionSource.POLICY.value,
                            reason=fallback_reason or "no route is legal from the current state",
                            confidence=0.0)
        outcome = self.evaluate_scene_state(state, allowed_routes=allowed_routes,
                                            priority_options=priority_options)
        guardrails: List[str] = []
        answers = outcome.get("answers") or {}
        route = outcome.get("route")
        confidence = _confidence_of(answers.get("route"))
        priority = answers.get("priority").label if answers.get("priority") else None
        native = {
            "runner": outcome.get("runner"),
            "answers": {name: answer.to_dict() for name, answer in answers.items()},
            "questions": outcome.get("questions"),
            "allowed_routes": allowed_routes,
            "min_confidence": self.min_confidence,
            "caveats": list(MODEL_CAVEATS),
        }

        route_answer = answers.get("route")
        if route_answer is not None and route_answer.low_confidence:
            reason = ("Laya's route answer is below the confidence threshold (%.2f < %.2f), so the "
                      "workflow treats the evidence as insufficient and asks a person"
                      % (_confidence_value(route_answer), self.min_confidence))
            return Decision(route=Route.HUMAN_REVIEW.value, confidence=confidence,
                            source=DecisionSource.UNAVAILABLE.value, reason=reason,
                            priority_criterion=priority, guardrails=guardrails, native=native,
                            latency_ms=outcome.get("latency_ms"))

        if route is None:
            reason = outcome.get("reason") or "Laya produced no usable route"
            if hard_failures:
                reason = "%s; mandatory checks failing: %s" % (reason, ", ".join(hard_failures))
            return Decision(route=Route.HUMAN_REVIEW.value, confidence=confidence,
                            source=DecisionSource.UNAVAILABLE.value, reason=reason,
                            priority_criterion=priority, guardrails=guardrails, native=native,
                            latency_ms=outcome.get("latency_ms"))

        if route not in allowed_routes:
            guardrails.append("Laya chose %r, which the deterministic layer does not allow here"
                              % route)
            replacement = (Route.REVISE.value if Route.REVISE.value in allowed_routes
                           else Route.HUMAN_REVIEW.value)
            route = replacement
            guardrails.append("overridden to %r" % replacement)

        reason = "Laya routed %s" % route
        if hard_failures:
            reason = "%s with mandatory checks failing: %s" % (reason, ", ".join(hard_failures))
        return Decision(route=route, confidence=confidence, source=DecisionSource.LAYA.value,
                        reason=reason, priority_criterion=priority, guardrails=guardrails,
                        native=native, latency_ms=outcome.get("latency_ms"))


def _recordable_questions(questions: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """The questions as they will be logged, criteria included.

    Recording only the question ids made a recorded decision unauditable: the priority answer is
    a slug, and without the criteria beside it a reader cannot tell which criterion the model
    actually named. The criteria are a few hundred bytes; the questions are the point.
    """
    recorded: Dict[str, Dict[str, Any]] = {}
    for qid, question in (questions or {}).items():
        recorded[str(qid)] = {
            "type": question.get("type"),
            "instructions": question.get("instructions", ""),
            "criteria": dict(question.get("criteria") or {}),
        }
    return recorded


def _state_text(state: Any, limit: int) -> str:
    """Serialize the state compactly.

    Laya reads the state as text (``laya/common.serialize_state`` json-encodes a dict), and the
    doc asks for a focused evidence pack rather than a project dump, so the text is truncated at a
    character budget with an explicit marker instead of being silently cut.
    """
    if isinstance(state, str):
        text = state
    else:
        text = json.dumps(state, ensure_ascii=False, sort_keys=True, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + "... [%d characters truncated]" % (len(text) - limit)


def _why_unavailable(primary: Optional[LayaRunner], fallbacks: List[LayaRunner]) -> str:
    reasons: List[str] = []
    for runner in ([primary] if primary else []) + list(fallbacks):
        detail = runner.detail.get("probe_error") or runner.detail.get("load_error") or ""
        reasons.append("%s%s" % (runner.name, ": %s" % detail if detail else ""))
    return "; ".join(reasons) or "no runner was configured"


def _confidence_value(answer: LayaAnswer) -> float:
    """The number to gate on.

    ``answer_confidence`` is Laya's calibrated confidence across every question type, and
    ``confidence`` means something different per type (max probability for ``noul``, normalized
    entropy for ``choice``). The gated quantity is the calibrated one when it is present.
    """
    for value in (answer.answer_confidence, answer.confidence, answer.probability):
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def _confidence_of(answer: Optional[LayaAnswer]) -> Optional[float]:
    if answer is None:
        return None
    return round(_confidence_value(answer), 4)


def _project_answers(result: Any, min_confidence: float) -> Any:
    """Read Laya's answer map into :class:`LayaAnswer` objects.

    Returns ``(answers, malformed_reason)``. A shape this adapter does not recognise is a
    malformed answer, never a silent default: the doc's failure mode for malformed output is to
    fail closed, so the caller turns this into ``human_review``.
    """
    if not isinstance(result, dict):
        return {}, "Laya did not return a result object (got %s)" % type(result).__name__
    raw = result.get("answers")
    if raw is None:
        raw = result.get("choices")
    if not isinstance(raw, dict) or not raw:
        return {}, "Laya returned no answers"
    answers: Dict[str, LayaAnswer] = {}
    for qid, entry in raw.items():
        if not isinstance(entry, dict):
            return {}, "answer for %r is not an object" % qid
        kind = str(entry.get("type") or "choice")
        probability: Optional[float] = None
        label: Optional[str] = None
        if kind == "choice":
            label = entry.get("choice")
            probabilities = entry.get("probabilities") or {}
            numbers = [float(v) for v in probabilities.values() if isinstance(v, (int, float))]
            probability = max(numbers) if numbers else None
        elif kind == "noul":
            value = entry.get("noul")
            if isinstance(value, (int, float)):
                probability = float(value)
                label = "true" if probability >= 0.5 else "false"
        elif kind == "score":
            score = entry.get("score")
            label = str(score) if score is not None else None
            probability = entry.get("confidence")
        else:
            return {}, "answer for %r has an unknown type %r" % (qid, kind)
        if label is None:
            return {}, "answer for %r carries no label" % qid
        confidence = entry.get("confidence")
        answer_confidence = entry.get("answer_confidence")
        calibrated = answer_confidence if isinstance(answer_confidence, (int, float)) else confidence
        low = bool(entry.get("low_confidence")) or (
            isinstance(calibrated, (int, float)) and float(calibrated) < min_confidence)
        answers[qid] = LayaAnswer(
            question=qid, label=str(label), probability=probability,
            confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
            answer_confidence=float(answer_confidence)
            if isinstance(answer_confidence, (int, float)) else None,
            kind=kind, low_confidence=low, native=dict(entry),
        )
    return answers, None


def build_laya_adapter(mode: str = "auto", model_id: str = DEFAULT_MODEL_ID,
                       device: Optional[str] = None, subfolder: Optional[str] = None,
                       executable: str = "laya", cwd: Optional[str] = None,
                       transport: Any = None, tool: str = "laya_predict",
                       min_confidence: float = DEFAULT_MIN_CONFIDENCE,
                       timeout: float = DEFAULT_TIMEOUT_S) -> LayaAdapter:
    """Build an adapter for a deployment choice, without pretending the choice is free.

    ``mode`` selects the deployment the doc's table describes:

    ``in-process``  Laya as a library in this interpreter (needs torch + weights); a local
                    checkpoint directory is used when one is already on disk.
    ``cli``         Laya as a private process (needs the ``laya`` CLI + weights).
    ``mcp``         Laya alongside the scene tools on the MCP host (needs a transport).
    ``auto``        try in-process, then the CLI, then MCP; report which one was used.
    ``none``        no model at all: every route comes back ``human_review``, which is the
                    correct behaviour for a read-only shadow run.
    """
    cli = CliLayaRunner(executable=executable, detail={"cwd": cwd} if cwd else {})
    inproc = InProcessLayaRunner(model_id=model_id, device=device, subfolder=subfolder)
    mcp = McpLayaRunner(transport=transport, tool=tool)
    if mode == "in-process":
        return LayaAdapter(runner=inproc, min_confidence=min_confidence, timeout=timeout)
    if mode == "cli":
        return LayaAdapter(runner=cli, min_confidence=min_confidence, timeout=timeout)
    if mode == "mcp":
        return LayaAdapter(runner=mcp, min_confidence=min_confidence, timeout=timeout)
    if mode == "none":
        return LayaAdapter(runner=None, min_confidence=min_confidence, timeout=timeout)
    return LayaAdapter(runner=inproc, fallback_runners=[cli, mcp], min_confidence=min_confidence,
                       timeout=timeout)
