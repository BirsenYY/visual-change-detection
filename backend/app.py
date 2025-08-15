import io
import os
import uuid
import time
from typing import Dict, Any

import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

app = FastAPI(title="Visual Diff API")

# Allow local dev origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))
os.makedirs(DATA_ROOT, exist_ok=True)

# Mount static file server so diff/before/after images can be loaded by the frontend
app.mount("/data", StaticFiles(directory=DATA_ROOT), name="data")

# Simple in-memory store for metadata (swap to Redis/DB in production)
STORE: Dict[str, Dict[str, Any]] = {}


def _read_image(file: UploadFile) -> np.ndarray:
    content = file.file.read()
    arr = np.frombuffer(content, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail=f"Could not decode image: {file.filename}")
    return img


def _ensure_same_size(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if a.shape[:2] != b.shape[:2]:
        # Resize b to a's size to allow comparison (alternatively, reject with 400)
        b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
    return a, b


def _compute_diff(before: np.ndarray, after: np.ndarray, threshold: int) -> tuple[np.ndarray, float, np.ndarray]:
    # Absolute pixel difference (per channel), then grayscale to get a single map
    absdiff = cv2.absdiff(before, after)
    gray = cv2.cvtColor(absdiff, cv2.COLOR_BGR2GRAY)

    # Threshold (0..255); lower = more sensitive
    _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

    # Optional: de-noise tiny specks
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    changed_pixels = int(cv2.countNonZero(mask))
    total_pixels = mask.shape[0] * mask.shape[1]
    diff_pct = (changed_pixels / total_pixels) * 100.0

    # Create visualization by overlaying red where changes detected
    highlight = after.copy()
    red_layer = np.zeros_like(after)
    red_layer[:, :] = (0, 0, 255)  # BGR red

    mask_3c = cv2.merge([mask, mask, mask])
    overlay = np.where(mask_3c > 0, red_layer, np.zeros_like(red_layer))
    vis = cv2.addWeighted(highlight, 0.7, overlay, 0.3, 0)

    return mask, float(diff_pct), vis


@app.post("/comparison")
async def create_comparison(
    before: UploadFile = File(...),
    after: UploadFile = File(...),
    # Slider from UI maps 0..100 to 0..255; but accept raw here for flexibility
    threshold: int = Form(25),
):
    if not (0 <= threshold <= 255):
        raise HTTPException(status_code=400, detail="threshold must be in [0, 255]")

    img_before = _read_image(before)
    img_after = _read_image(after)
    img_before, img_after = _ensure_same_size(img_before, img_after)

    mask, diff_pct, vis = _compute_diff(img_before, img_after, threshold)

    comp_id = str(uuid.uuid4())
    out_dir = os.path.join(DATA_ROOT, comp_id)
    os.makedirs(out_dir, exist_ok=True)

    # Save inputs & outputs (PNG)
    before_path = os.path.join(out_dir, "before.png")
    after_path = os.path.join(out_dir, "after.png")
    diff_path = os.path.join(out_dir, "diff.png")
    mask_path = os.path.join(out_dir, "mask.png")

    cv2.imwrite(before_path, img_before)
    cv2.imwrite(after_path, img_after)
    cv2.imwrite(diff_path, vis)
    cv2.imwrite(mask_path, mask)

    record = {
        "id": comp_id,
        "threshold": threshold,
        "difference_percent": round(diff_pct, 4),
        "created_at": int(time.time()),
        "assets": {
            "before_url": f"/data/{comp_id}/before.png",
            "after_url": f"/data/{comp_id}/after.png",
            "diff_url": f"/data/{comp_id}/diff.png",
            "mask_url": f"/data/{comp_id}/mask.png",
        },
    }

    STORE[comp_id] = record
    return JSONResponse(record)


@app.get("/comparison/{comp_id}")
async def get_comparison(comp_id: str):
    rec = STORE.get(comp_id)
    if not rec:
        # Try reconstructing from disk if API restarted but files exist
        out_dir = os.path.join(DATA_ROOT, comp_id)
        before_path = os.path.join(out_dir, "before.png")
        after_path = os.path.join(out_dir, "after.png")
        diff_path = os.path.join(out_dir, "diff.png")
        mask_path = os.path.join(out_dir, "mask.png")
        if all(os.path.exists(p) for p in [before_path, after_path, diff_path, mask_path]):
            rec = {
                "id": comp_id,
                "threshold": None,
                "difference_percent": None,
                "created_at": None,
                "assets": {
                    "before_url": f"/data/{comp_id}/before.png",
                    "after_url": f"/data/{comp_id}/after.png",
                    "diff_url": f"/data/{comp_id}/diff.png",
                    "mask_url": f"/data/{comp_id}/mask.png",
                },
            }
        else:
            raise HTTPException(status_code=404, detail="comparison not found")
    return JSONResponse(rec)