"""Page classifier: recognition from a live-shaped frame, and the prototypes the app ships."""

import json
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from frame_normalize import normalize_frame
from image_ops import preprocess_for_ocr
from tools.reference_screens import reference_screens

TEMPLATES = Path(__file__).resolve().parent.parent / "src" / "edge-agent" / "assets" / "templates" / "bper"
SCREENS = [f"screen {n}" for n in range(1, 10)]
# The screenshots the page prototypes were built from, kept only in the practice archive.
REFERENCES = reference_screens()

MONITOR = {"left": 0, "top": 0, "width": 1920, "height": 1080}
DESKTOP = (32, 34, 38)


def _live_frame(template: Path, scale: float = 1.0) -> Image.Image:
    """What the capture loop really sees: the app window inside a full monitor.

    The reference templates are window screenshots; `mss` grabs the whole
    screen. This rebuilds that framing so the test exercises the live path
    instead of feeding the classifier its own prototype back.
    """
    win = Image.open(template).convert("RGB")
    if scale != 1.0:
        win = win.resize(
            (int(win.width * scale), int(win.height * scale)), Image.Resampling.LANCZOS
        )
    frame = Image.new("RGB", (MONITOR["width"], MONITOR["height"]), DESKTOP)
    frame.paste(win, ((MONITOR["width"] - win.width) // 2, (MONITOR["height"] - win.height) // 2))
    return frame


def _as_worker_sees_it(frame: Image.Image) -> Image.Image:
    """The worker's own order: normalize the framing, then preprocess for OCR."""
    normalized, _strategy = normalize_frame(frame, MONITOR, window_rect_provider=lambda: None)
    return preprocess_for_ocr(
        normalized,
        scale=None,
        unsharp_amount=0.8,
        unsharp_radius=1.2,
        unsharp_threshold=2,
        contrast_stretch=True,
    )


@pytest.fixture(scope="module")
def classifier():
    pytest.importorskip("torch", reason="DINOv2 page classifier needs torch")
    from page_classifier import (
        BPERPagePrototypeClassifier,
        DEFAULT_CROP_ROI,
        DEFAULT_SIMILARITY_THRESHOLD,
    )

    return BPERPagePrototypeClassifier(
        templates_dir=TEMPLATES,
        crop_roi=DEFAULT_CROP_ROI,
        similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD,
        device="cpu",
    )


@pytest.mark.slow
@pytest.mark.parametrize("screen", SCREENS)
def test_recognizes_each_page_from_a_full_monitor_frame(classifier, screen):
    label, score = classifier.classify(_as_worker_sees_it(_live_frame(REFERENCES[screen])))

    assert label == screen, f"got {label!r} at score {score:.3f}"


@pytest.mark.slow
@pytest.mark.parametrize("scale", [0.8, 1.4])
def test_recognition_survives_a_differently_sized_window(classifier, scale):
    # The operator's browser will not be 848x679. Recognition must not depend on
    # the window matching the template's pixel size.
    misread = [
        screen
        for screen in SCREENS
        if classifier.classify(
            _as_worker_sees_it(_live_frame(REFERENCES[screen], scale=scale))
        )[0]
        != screen
    ]

    assert misread == []


@pytest.mark.slow
def test_rejects_a_frame_that_is_not_a_bper_page(classifier):
    # A blank desktop must not be labelled as a page: a false positive burns the
    # page slot for the whole job and the operator cannot capture it again.
    label, _ = classifier.classify(Image.new("RGB", (1920, 1080), DESKTOP))

    assert label is None


def test_the_app_ships_prototypes_not_screenshots():
    """The app knows its pages a priori: it carries their prototypes, not the images to compute them from."""
    images = [p.name for p in TEMPLATES.rglob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}]

    assert images == []


def test_shipped_prototypes_are_ready_without_any_image(tmp_path):
    from page_classifier import cache_is_valid

    shutil.copyfile(TEMPLATES / "bper_page_prototypes.json", tmp_path / "bper_page_prototypes.json")

    assert cache_is_valid(tmp_path) is True


def _stale_prototypes(tmp_path):
    from page_classifier import embedding_geometry

    (tmp_path / "bper_page_prototypes.json").write_text(
        json.dumps({"geometry": embedding_geometry() + " stale", "prototypes": {"screen 1": {"embedding": [1.0], "count": 1}}}),
        encoding="utf-8",
    )
    return tmp_path


def test_prototypes_of_another_embedding_geometry_are_not_ready(tmp_path):
    """Prototypes and queries have to be embedded the same way, or every score is meaningless."""
    from page_classifier import cache_is_valid

    assert cache_is_valid(_stale_prototypes(tmp_path)) is False


def test_classifier_refuses_prototypes_of_another_embedding_geometry(tmp_path):
    pytest.importorskip("torch", reason="DINOv2 page classifier needs torch")
    from page_classifier import BPERPagePrototypeClassifier

    with pytest.raises(RuntimeError, match="build_prototypes"):
        BPERPagePrototypeClassifier(templates_dir=_stale_prototypes(tmp_path), device="cpu")


# ------------------------------------------------- reject classes and margin

REJECT_PREFIX = "SCARTO"


def _prototype_dir(tmp_path, pages, rejects):
    """A templates dir in the subdirectory layout: one folder per class."""
    root = tmp_path / "bper"
    for name, images in {**pages, **rejects}.items():
        folder = root / name
        folder.mkdir(parents=True)
        for i, img in enumerate(images):
            img.save(folder / f"{i}.png")
    return root


def _page_like(seed: int) -> Image.Image:
    """A synthetic page: white sheet, coloured header band, text-like rows."""
    img = Image.new("RGB", (848, 679), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 848, 60], fill=(10, 60 + seed * 30, 120))
    for row in range(12):
        d.rectangle([40, 100 + row * 40, 700 + seed * 20, 120 + row * 40],
                    fill=(200 - seed * 20, 200, 210))
    return img


def _not_a_page() -> Image.Image:
    img = Image.new("RGB", (848, 679), (30, 30, 34))
    ImageDraw.Draw(img).ellipse([300, 200, 550, 450], fill=(200, 80, 40))
    return img


@pytest.fixture(scope="module")
def rejecting_classifier(tmp_path_factory):
    """A classifier trained on two pages plus one reject class.

    Reject classes are ordinary prototype folders whose name starts with the
    reject prefix. That keeps the prototype-building code unchanged: what makes
    them special is only how classify() reports a win by one of them.
    """
    pytest.importorskip("torch", reason="DINOv2 page classifier needs torch")
    from page_classifier import BPERPagePrototypeClassifier

    root = _prototype_dir(
        tmp_path_factory.mktemp("protos"),
        pages={"pagina a": [_page_like(0), _page_like(0)],
               "pagina b": [_page_like(2), _page_like(2)]},
        rejects={f"{REJECT_PREFIX}-fuori-processo": [_not_a_page(), _not_a_page()]},
    )
    from page_classifier import _scan_dataset_images

    return BPERPagePrototypeClassifier(templates_dir=root, crop_roi=None, similarity_threshold=0.0,
                                       device="cpu", build_from=_scan_dataset_images(root))


@pytest.mark.slow
def test_a_reject_prototype_wins_instead_of_a_page(rejecting_classifier):
    """Without a reject class the classifier must pick a page, whatever it sees.

    Measured on real frames: 100% of negatives were assigned to a page, by
    construction rather than by error. A false positive consumes that page's slot
    for the whole job, so having somewhere to put a non-page is not a refinement.
    """
    label, _score = rejecting_classifier.classify(_not_a_page())

    assert label is None, f"un negativo e' stato etichettato {label!r}"


@pytest.mark.slow
def test_a_page_still_wins_when_reject_prototypes_exist(rejecting_classifier):
    label, _score = rejecting_classifier.classify(_page_like(0))

    assert label == "pagina a"


@pytest.mark.slow
def test_classify_reports_the_margin_over_the_runner_up(rejecting_classifier):
    """The margin is what the LLM fallback is gated on, so it must be reported.

    Accuracy alone cannot drive a hybrid decision: what matters is whether a given
    answer is separable from the next best one. classify_detailed() exposes that
    without changing the (label, score) contract five call sites already use.
    """
    result = rejecting_classifier.classify_detailed(_page_like(0))

    assert result.label == "pagina a"
    assert result.margin > 0.0
    assert result.runner_up != result.label


@pytest.mark.slow
def test_a_rejected_frame_is_reported_as_rejected_not_as_unknown(rejecting_classifier):
    """A frame that lost to a reject prototype is not the same as one below
    threshold: the first was actively recognised as a non-page, the second was
    simply not recognised. The caller needs to tell them apart to decide whether
    asking the LLM is worth a call."""
    result = rejecting_classifier.classify_detailed(_not_a_page())

    assert result.label is None
    assert result.rejected_by is not None
    assert result.rejected_by.startswith(REJECT_PREFIX)


def test_cache_is_stale_when_reject_classes_appear(tmp_path):
    """Adding a reject class changes what the classifier is, not just its data.

    The dataset hash covers the images, and adding a folder does change it, but the
    scoring behaviour changes too: the same query that previously had to pick a page
    can now be rejected. A cache built before reject classes existed must not be
    served against a configuration that has them, and the geometry string is where
    that is declared.
    """
    from page_classifier import embedding_geometry

    without = embedding_geometry(reject_classes=0)
    with_three = embedding_geometry(reject_classes=3)

    assert without != with_three


@pytest.mark.slow
def test_reject_classes_do_not_cost_page_recognition(classifier):
    """Adding reject prototypes must not disturb the pages.

    Measured while wiring this: reject classes alone leave reference recognition at
    9/9, while adding real crops to the *page* classes dropped it to 1/9. That is
    why the shipped prototypes carry reject classes and keep the nine references as
    the page prototypes. This test is the guard on the half that works.
    """
    misread = [
        screen
        for screen in SCREENS
        if classifier.classify(Image.open(REFERENCES[screen]))[0] != screen
    ]

    assert misread == []


@pytest.mark.slow
def test_a_blank_desktop_is_rejected_by_a_named_class(classifier):
    """Before reject classes existed the only possible answer was a page or a
    below-threshold None. Naming which reject class won tells the caller the frame
    was recognised as a non-page rather than simply not recognised."""
    result = classifier.classify_detailed(Image.new("RGB", (1920, 1080), DESKTOP))

    assert result.label is None
    assert result.rejected_by is not None
