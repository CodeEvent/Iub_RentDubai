# Independent chip-photo-vs-selfie face comparison -- lightweight,
# in-process, no new self-hosted service. Explicitly a separate check
# from Idswyft's own card-photo-vs-selfie face match: the chip's DG2
# photo is read straight off a cryptographically-signed government
# document, so a second, independent match against it is real extra
# signal for the Notary reviewer, not a duplicate of what Idswyft
# already does.
#
# Chose OpenCV's own YuNet (detection) + SFace (recognition) models
# over deploying a full separate face-recognition service (CompreFace
# was considered) because this sandbox is already running two other
# Docker stacks with real memory pressure (confirmed via `docker stats`
# before building this -- swap was already ~70% used) -- these are
# small (~39MB total), CPU-only, and run in-process, no new container.
# Verified for real before wiring this up: detected a real face in a
# test photo, self-match scored ~1.0 cosine similarity, and a quality-
# degraded same-person copy scored ~0.975 -- both comfortably above
# SFace's own published same-person threshold (~0.363 at their tested
# FAR), confirming the pipeline (not just the theory) works.
from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image

logger = logging.getLogger("paperless.rentshield")

_MODELS_DIR = Path(__file__).resolve().parent / "models"
_DETECTOR_PATH = _MODELS_DIR / "face_detection_yunet.onnx"
_RECOGNIZER_PATH = _MODELS_DIR / "face_recognition_sface.onnx"
# Deliberately github.com/.../raw/..., NOT raw.githubusercontent.com --
# these model files are Git LFS objects in opencv_zoo. raw.githubusercontent.com
# serves the literal git blob (the ~130-byte LFS pointer text, not the
# actual model), which silently corrupted the very first real download
# attempt (cv2 failed with "Failed to parse ONNX model"). github.com's
# own /raw/ redirect resolves through to the real LFS-hosted binary --
# confirmed directly (232589 real bytes, correct ONNX magic header)
# before relying on it here.
_DETECTOR_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
_RECOGNIZER_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"

# SFace's own published recommendation for "same person" at their
# tested false-accept rate -- used only as a display label; the actual
# decision is always the Notary reviewer's, never an automatic gate.
SAME_PERSON_THRESHOLD = 0.363

_detector = None
_recognizer = None


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    dest.write_bytes(response.content)


def _ensure_models() -> None:
    if not _DETECTOR_PATH.exists():
        logger.info("face_match: downloading face detection model (one-time)")
        _download(_DETECTOR_URL, _DETECTOR_PATH)
    if not _RECOGNIZER_PATH.exists():
        logger.info("face_match: downloading face recognition model (one-time)")
        _download(_RECOGNIZER_URL, _RECOGNIZER_PATH)


def _get_models():
    global _detector, _recognizer
    if _detector is None or _recognizer is None:
        _ensure_models()
        _detector = cv2.FaceDetectorYN_create(str(_DETECTOR_PATH), "", (320, 320))
        _recognizer = cv2.FaceRecognizerSF_create(str(_RECOGNIZER_PATH), "")
    return _detector, _recognizer


def _decode_bgr(image_bytes: bytes) -> np.ndarray:
    # Via Pillow first, not cv2.imdecode directly -- this project's
    # images can arrive in formats OpenCV's own decoder doesn't handle
    # (JPEG2000 chip photos, though normalize_image_for_idswyft usually
    # converts those before this is ever called; still cheap insurance).
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    rgb = np.array(image)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


class NoFaceDetectedError(Exception):
    pass


def _extract_feature(detector, recognizer, image_bytes: bytes) -> np.ndarray:
    bgr = _decode_bgr(image_bytes)
    height, width = bgr.shape[:2]
    detector.setInputSize((width, height))
    _, faces = detector.detect(bgr)
    if faces is None or len(faces) == 0:
        raise NoFaceDetectedError("No face detected in image")
    aligned = recognizer.alignCrop(bgr, faces[0])
    return recognizer.feature(aligned)


def compare_faces(image_bytes_a: bytes, image_bytes_b: bytes) -> float:
    """Returns a cosine similarity score (roughly -1 to 1, in practice
    usually 0 to 1) between the largest detected face in each image.
    Raises NoFaceDetectedError if either image has no detectable face --
    callers should treat that as "couldn't compare", not a failure of
    the verification itself (see views.py's usage)."""
    detector, recognizer = _get_models()
    feature_a = _extract_feature(detector, recognizer, image_bytes_a)
    feature_b = _extract_feature(detector, recognizer, image_bytes_b)
    return float(recognizer.match(feature_a, feature_b, cv2.FaceRecognizerSF_FR_COSINE))
