"""The visual reviewer: composition and legibility findings from the rendered views.

Doc, section 2: the visual reviewer "inspects rendered views against the brief and returns
evidence tied to a view, object, or image region", and it must never change the scene or make the
final approval decision alone. Section 6 adds: "Critique is vague or not tied to a view/object:
ask for evidence and a specific region/object."

Two reviewer backends ship here:

``MeasuredReviewer``          real image measurements (silhouette separation, framing, exposure,
                              clipping) with no model at all. This is what makes the workflow
                              useful before any vision model is wired in, and it satisfies the
                              requirement that findings be located and reproducible.
``payload reviewer``          findings supplied from outside -- a vision model, or the agent host
                              looking at the renders. They are schema-checked and **rejected
                              unless they name a view and an object or region**, which is how
                              "make it better" cannot become a broad scene edit.

Neither backend may claim an aesthetic judgement it did not measure: findings carry
``measured`` and ``source`` so the final report can separate what was measured from what was
judged.
"""
from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from .contracts import SceneContract, ViewSpec
from .models import Finding, Severity, ViewRender, VisualReview

ANALYSIS_SIZE = (256, 256)

# Background separation. The backdrop is modelled by a border-seeded flood fill with a *local*
# similarity test, so a gradient or vignette backdrop is followed instead of being mistaken for
# the subject. Global thresholds alone classified most of a real studio render as "subject".
LOCAL_DELTA = 12     # max per-channel step between neighbouring background pixels
GLOBAL_DELTA = 54    # how far a pixel may sit from the border-median colour and still be backdrop
MIN_BACKGROUND_SHARE = 0.02
MAX_BACKGROUND_SHARE = 0.995

# Thresholds. Deliberately explicit and conservative; a threshold change here moves what the
# workflow will call a failure, so it belongs in review, not in a magic number.
MIN_SUBJECT_COVERAGE = 0.06
MAX_SUBJECT_COVERAGE = 0.97
MIN_SILHOUETTE_CONTRAST = 0.055
MAX_HIGHLIGHT_CLIP = 0.035
MAX_SHADOW_CLIP = 0.30
MIN_MEAN_LUMA = 0.035
EDGE_TOUCH_TOLERANCE = 0.004


class ReviewerError(RuntimeError):
    """Raised when a review cannot be produced from the available evidence."""


def _load_pillow():
    """Import Pillow lazily so the deterministic half of the workflow needs no image library."""
    try:
        from PIL import Image
    except Exception as error:  # pragma: no cover - depends on the host environment
        raise ReviewerError(
            "image measurements need Pillow (pip install pillow): %s" % error
        ) from None
    return Image


@dataclass
class ViewMeasurement:
    """Everything measurable about one render, in normalized (0-1) units."""

    view: str
    path: str
    width: int
    height: int
    coverage: float
    subject_box: Optional[List[float]]
    edge_touch: Dict[str, float]
    silhouette_contrast: float
    mean_luma: float
    highlight_clip: float
    shadow_clip: float
    background: List[int]
    has_alpha: bool
    reliable: bool = True
    method: str = "alpha"
    method_note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "view": self.view, "path": self.path, "width": self.width, "height": self.height,
            "coverage": round(self.coverage, 5), "subject_box": self.subject_box,
            "edge_touch": {k: round(v, 5) for k, v in self.edge_touch.items()},
            "silhouette_contrast": round(self.silhouette_contrast, 5),
            "mean_luma": round(self.mean_luma, 5),
            "highlight_clip": round(self.highlight_clip, 5),
            "shadow_clip": round(self.shadow_clip, 5),
            "background": list(self.background), "has_alpha": self.has_alpha,
            "reliable": self.reliable, "method": self.method,
            "method_note": self.method_note,
        }


def _median_channel(values: List[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _flood_background(pixels: Sequence[Sequence[int]], columns: int, rows: int) -> Any:
    """Separate subject from backdrop by growing the backdrop from the frame border.

    Returns ``(subject_mask, background_colour, reliable, note)``. Growth is local -- a pixel
    joins the backdrop when it is close to its neighbour *and* broadly close to the border median
    -- so a smooth gradient backdrop is followed correctly and a subject of similar overall tone
    is not swallowed. When the fill cannot separate the two (it covers essentially everything, or
    essentially nothing), it says so instead of returning numbers that mean nothing.
    """
    border: List[int] = []
    for x in range(columns):
        border.append(x)
        border.append((rows - 1) * columns + x)
    for y in range(rows):
        border.append(y * columns)
        border.append(y * columns + columns - 1)

    medians = [_median_channel([int(pixels[index][channel]) for index in border])
               for channel in range(3)]

    is_background = bytearray(columns * rows)
    queue: deque = deque()
    for index in border:
        pixel = pixels[index]
        if max(abs(int(pixel[channel]) - medians[channel]) for channel in range(3)) <= GLOBAL_DELTA:
            is_background[index] = 1
            queue.append(index)

    while queue:
        index = queue.popleft()
        x = index % columns
        y = index // columns
        base = pixels[index]
        for neighbour_x, neighbour_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if neighbour_x < 0 or neighbour_x >= columns or neighbour_y < 0 or neighbour_y >= rows:
                continue
            neighbour = neighbour_y * columns + neighbour_x
            if is_background[neighbour]:
                continue
            pixel = pixels[neighbour]
            if max(abs(int(pixel[channel]) - int(base[channel])) for channel in range(3)) > LOCAL_DELTA:
                continue
            if max(abs(int(pixel[channel]) - medians[channel]) for channel in range(3)) > GLOBAL_DELTA:
                continue
            is_background[neighbour] = 1
            queue.append(neighbour)

    share = sum(is_background) / float(columns * rows)
    subject = [not flag for flag in is_background]
    if share < MIN_BACKGROUND_SHARE:
        return subject, medians, False, ("no background region could be found from the frame "
                                        "border, so framing measurements are not reported")
    if share > MAX_BACKGROUND_SHARE:
        return subject, medians, False, ("the backdrop and the subject could not be separated "
                                        "(the fill covered the whole frame), so framing "
                                        "measurements are not reported")
    return subject, medians, True, ""


def render_metadata(path: str) -> Dict[str, Any]:
    """Read the provenance a renderer wrote into the image itself.

    Blender writes ``Camera``, ``Scene``, ``File`` and the render time as PNG text chunks, so an
    existing render can be checked against the view it claims to be: a supplied image that was
    made with a different camera is not evidence about the declared view. Returns an empty dict
    when the file carries no such metadata, which is reported as unknown rather than assumed.
    """
    if not path or not os.path.exists(path):
        return {}
    try:
        Image = _load_pillow()
        with Image.open(path) as handle:
            info = dict(handle.info or {})
            size = list(handle.size)
    except Exception:
        return {}
    keys = ("Camera", "Scene", "File", "RenderTime", "Frame")
    metadata = {key.lower(): info[key] for key in keys if key in info}
    metadata["resolution"] = size
    metadata["has_metadata"] = bool(metadata)
    return metadata


def _luma(pixel: Sequence[int]) -> float:
    return (0.2126 * pixel[0] + 0.7152 * pixel[1] + 0.0722 * pixel[2]) / 255.0


def measure_view(view: ViewRender) -> ViewMeasurement:
    """Measure one rendered view.

    The subject is separated from the background either by alpha (transparent film) or by
    distance from the corner background colour. Both paths are honest about what they can see;
    nothing here infers hidden geometry.
    """
    if not view.path or not os.path.exists(view.path):
        raise ReviewerError("view %r has no readable render at %r" % (view.name, view.path))
    Image = _load_pillow()
    with Image.open(view.path) as handle:
        image = handle.convert("RGBA")
    width, height = image.size
    small = image.resize(ANALYSIS_SIZE, Image.BILINEAR)
    columns, rows = small.size
    # Index through the pixel access object rather than Image.getdata(), which Pillow 12 deprecates
    # and Pillow 14 removes.
    accessor = small.load()
    pixels = [accessor[x, y] for y in range(rows) for x in range(columns)]

    has_alpha = any(pixel[3] < 250 for pixel in pixels)
    reliable = True
    method = "alpha"
    method_note = ""
    if has_alpha:
        # A transparent film gives an exact subject mask; nothing is estimated.
        mask: List[bool] = [pixel[3] > 40 for pixel in pixels]
        subject_rgb = [pixel[:3] for pixel, flag in zip(pixels, mask) if flag]
        background = [_median_channel([int(pixel[channel]) for pixel in subject_rgb])
                      for channel in range(3)] if subject_rgb else [0, 0, 0]
    else:
        mask, background, reliable, method_note = _flood_background(pixels, columns, rows)
        method = "border-flood-fill"
    subject_count = sum(1 for flag in mask if flag)
    coverage = subject_count / float(columns * rows)

    if subject_count:
        xs = [index % columns for index, flag in enumerate(mask) if flag]
        ys = [index // columns for index, flag in enumerate(mask) if flag]
        box = [min(xs) / columns, min(ys) / rows,
               (max(xs) - min(xs) + 1) / columns, (max(ys) - min(ys) + 1) / rows]
    else:
        box = None

    edge_touch = {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}
    if subject_count:
        for index, flag in enumerate(mask):
            if not flag:
                continue
            x, y = index % columns, index // columns
            if x == 0:
                edge_touch["left"] += 1
            if x == columns - 1:
                edge_touch["right"] += 1
            if y == 0:
                edge_touch["top"] += 1
            if y == rows - 1:
                edge_touch["bottom"] += 1
        edge_touch = {key: value / float(subject_count) for key, value in edge_touch.items()}

    subject_luma = [_luma(pixel) for pixel, flag in zip(pixels, mask) if flag]
    background_luma = [_luma(pixel) for pixel, flag in zip(pixels, mask) if not flag]
    silhouette = 0.0
    if subject_luma and background_luma:
        silhouette = abs(sum(subject_luma) / len(subject_luma)
                         - sum(background_luma) / len(background_luma))

    luminances = [_luma(pixel) for pixel in pixels]
    mean_luma = sum(luminances) / len(luminances) if luminances else 0.0
    highlight_clip = sum(1 for value in luminances if value > 0.985) / float(len(luminances))
    shadow_clip = sum(1 for value in luminances if value < 0.015) / float(len(luminances))

    return ViewMeasurement(
        view=view.name,
        path=view.path,
        width=width,
        height=height,
        coverage=coverage,
        subject_box=box,
        edge_touch=edge_touch,
        silhouette_contrast=silhouette,
        mean_luma=mean_luma,
        highlight_clip=highlight_clip,
        shadow_clip=shadow_clip,
        background=background,
        has_alpha=has_alpha,
        reliable=reliable,
        method=method,
        method_note=method_note,
    )


def _finding_from_measurement(measurement: ViewMeasurement, spec: Optional[ViewSpec]) -> List[Finding]:
    findings: List[Finding] = []
    box = measurement.subject_box

    def add(criterion: str, severity: str, evidence: str, fix: str, confidence: float) -> None:
        findings.append(Finding(
            criterion=criterion, result="fail", severity=severity, view=measurement.view,
            affected_object=None, evidence=evidence, suggested_fix=fix, confidence=confidence,
            region=box, measured=True, source="measured_reviewer",
        ))

    # Framing findings need a trustworthy subject/background split. When the split is not
    # measurable, the image is reported as unmeasured for framing -- never as a pass, and never
    # with a fabricated coverage figure -- while the whole-frame measurements below still run.
    mask_ok = measurement.reliable
    if not mask_ok:
        findings.append(Finding(
            criterion="framing could not be measured", result="warn",
            severity=Severity.LOW.value, view=measurement.view, affected_object=None,
            evidence=measurement.method_note or "the subject/background split is not measurable",
            suggested_fix="render this view with a transparent film or a backdrop that differs "
                          "from the subject in tone, so framing can be reviewed objectively",
            confidence=0.5, region=None, measured=False, source="measured_reviewer"))

    if mask_ok and (measurement.coverage <= 0.0 or box is None):
        add("subject present in frame", Severity.HIGH.value,
            "no subject pixels were separated from the background; the view is empty or the "
            "subject is the same colour as the background",
            "check the camera is aimed at the scene and the subject is lit against a distinct "
            "background", 0.7)
        return findings

    # Framing: a silhouette that leaves the frame cannot be read as a silhouette.
    worst_edge = max(measurement.edge_touch.items(), key=lambda item: item[1]) if mask_ok \
        else ("none", 0.0)
    if mask_ok and worst_edge[1] > EDGE_TOUCH_TOLERANCE:
        severity = Severity.HIGH.value if worst_edge[1] > 0.03 else Severity.MEDIUM.value
        add("subject fully inside the frame", severity,
            "%.1f%% of subject pixels touch the %s frame edge, so the silhouette is cut off"
            % (worst_edge[1] * 100.0, worst_edge[0]),
            "pull the camera back or reframe so the whole subject sits inside the frame",
            min(0.95, 0.5 + worst_edge[1] * 10))

    if mask_ok and measurement.coverage < MIN_SUBJECT_COVERAGE:
        add("subject reads at a legible size", Severity.MEDIUM.value,
            "subject covers %.1f%% of the frame" % (measurement.coverage * 100.0),
            "tighten the framing; aim for 40-85%% coverage so form and materials are legible",
            0.75)
    elif mask_ok and measurement.coverage > MAX_SUBJECT_COVERAGE:
        add("subject reads at a legible size", Severity.LOW.value,
            "subject covers %.1f%% of the frame, leaving no context around it"
            % (measurement.coverage * 100.0),
            "widen slightly so the subject has room to breathe against the background", 0.6)

    if mask_ok and measurement.silhouette_contrast < MIN_SILHOUETTE_CONTRAST:
        add("silhouette separates from the background", Severity.MEDIUM.value,
            "subject/background luminance difference is %.3f" % measurement.silhouette_contrast,
            "raise the separation: stronger key light, a rim light, or a darker/lighter backdrop",
            0.7)

    if measurement.mean_luma < MIN_MEAN_LUMA:
        add("exposure", Severity.HIGH.value,
            "the frame is almost black (mean luminance %.3f)" % measurement.mean_luma,
            "raise light energy or exposure", 0.8)
    if measurement.highlight_clip > MAX_HIGHLIGHT_CLIP:
        add("highlights not blown out", Severity.MEDIUM.value,
            "%.1f%% of the frame is clipped to white" % (measurement.highlight_clip * 100.0),
            "lower the key light or lift the exposure down so material response stays readable",
            min(0.95, 0.5 + measurement.highlight_clip * 8))
    if measurement.shadow_clip > MAX_SHADOW_CLIP:
        add("shadows not crushed", Severity.LOW.value,
            "%.1f%% of the frame is clipped to black" % (measurement.shadow_clip * 100.0),
            "add fill light so dark materials keep their detail", 0.6)

    if mask_ok and spec and spec.framing and measurement.coverage < MIN_SUBJECT_COVERAGE * 3:
        findings.append(Finding(
            criterion="view framing intent", result="warn", severity=Severity.LOW.value,
            view=measurement.view, evidence="declared intent: %s" % spec.framing,
            suggested_fix="compare against the declared framing intent", confidence=0.4,
            region=box, measured=False, source="contract",
        ))
    return findings


class MeasuredReviewer:
    """Review backend that only reports what it can measure."""

    name = "measured_reviewer"

    def review(self, views: List[ViewRender], contract: SceneContract,
               measurements: Optional[Dict[str, ViewMeasurement]] = None) -> VisualReview:
        review = VisualReview(reviewer=self.name)
        notes: List[str] = []
        for view in views:
            if not view.rendered or not view.path or not os.path.exists(view.path):
                notes.append("view %r was not rendered; no visual claim is made about it" % view.name)
                continue
            try:
                measurement = measure_view(view)
            except ReviewerError as error:
                notes.append("view %r could not be measured: %s" % (view.name, error))
                continue
            view.stats = measurement.to_dict()
            review.views_reviewed.append(view.name)
            review.findings.extend(_finding_from_measurement(
                measurement, contract.view(view.name)))
        review.notes = "; ".join(notes)
        return review


def findings_from_payload(payload: Any, allowed_views: Sequence[str]) -> List[Finding]:
    """Validate externally supplied findings (a vision model, or the agent host's own review).

    A finding is rejected -- not silently repaired -- when it names an unknown view or carries
    neither an object nor a region, because the doc's failure mode for vague critique is to ask
    for evidence rather than to translate it into a broad edit.
    """
    items = payload
    if isinstance(payload, dict):
        items = payload.get("findings", [])
    if not isinstance(items, list):
        raise ReviewerError("findings payload must be a list or {'findings': [...]}")
    allowed = set(allowed_views)
    findings: List[Finding] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ReviewerError("finding %d is not an object" % index)
        view = item.get("view")
        if view not in allowed:
            raise ReviewerError("finding %d names view %r, not one of %s"
                                % (index, view, sorted(allowed)))
        finding = Finding(
            criterion=str(item.get("criterion") or "unspecified"),
            result=str(item.get("result") or "warn"),
            severity=str(item.get("severity") or Severity.MEDIUM.value),
            view=view,
            affected_object=item.get("affected_object"),
            evidence=str(item.get("evidence") or ""),
            suggested_fix=item.get("suggested_fix"),
            confidence=float(item["confidence"]) if item.get("confidence") is not None else None,
            region=[float(v) for v in item["region"]] if item.get("region") else None,
            measured=False,
            source=str(item.get("source") or "external_reviewer"),
        )
        if not finding.is_located():
            raise ReviewerError(
                "finding %d (%s) names no affected_object and no region; the workflow will not "
                "turn an unlocated critique into a scene edit" % (index, finding.criterion))
        findings.append(finding)
    return findings


def load_findings(path: str, allowed_views: Sequence[str]) -> List[Finding]:
    with open(path, "r", encoding="utf-8") as handle:
        return findings_from_payload(json.load(handle), allowed_views)


def merge_reviews(primary: VisualReview, extra: VisualReview) -> VisualReview:
    """Combine two reviewers without letting either hide the other's findings."""
    merged = VisualReview(
        views_reviewed=sorted(set(primary.views_reviewed) | set(extra.views_reviewed)),
        findings=list(primary.findings) + list(extra.findings),
        reviewer="%s+%s" % (primary.reviewer, extra.reviewer),
        notes="; ".join(note for note in (primary.notes, extra.notes) if note),
    )
    return merged
