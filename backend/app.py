import io
import os
import uuid
import time
import json
from typing import Dict, Any, List, Optional
from collections import deque

import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Depends, Query
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

# In‑memory store + recent history (persist images + metadata.json to disk)
STORE: Dict[str, Dict[str, Any]] = {}
HISTORY = deque(maxlen=50)

# --- Mandatory API key auth ---
_raw_keys = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]
API_KEYS = set(_raw_keys)
if not API_KEYS:
    # Enforce that a key must be configured
    raise RuntimeError(
        "API_KEYS must be set (comma-separated). Example: export API_KEYS=dev123"
    )

def require_api_key(x_api_key: Optional[str] = Header(default=None)):
    if not x_api_key or x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def _read_image(file: UploadFile) -> np.ndarray:
    content = file.file.read()
    arr = np.frombuffer(content, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail=f"Could not decode image: {file.filename}")
    return img


def _ensure_same_size(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if a.shape[:2] != b.shape[:2]:
        b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
    return a, b


def _apply_ignore_rects(mask: np.ndarray, rects: List[dict]):
    if not rects:
        return
    h, w = mask.shape[:2]
    for r in rects:
        # rects are normalized [0..1]: {x, y, w, h}
        x1 = max(0, min(w - 1, int(round(r.get('x', 0) * w))))
        y1 = max(0, min(h - 1, int(round(r.get('y', 0) * h))))
        x2 = max(0, min(w, int(round((r.get('x', 0) + r.get('w', 0)) * w))))
        y2 = max(0, min(h, int(round((r.get('y', 0) + r.get('h', 0)) * h))))
        if y2 > y1 and x2 > x1:
            mask[y1:y2, x1:x2] = 0  # ignore: force no-change in that region


def _compute_diff(before: np.ndarray, after: np.ndarray, threshold: int, ignore_rects: Optional[List[dict]] = None) -> tuple[np.ndarray, float, np.ndarray]:
    absdiff = cv2.absdiff(before, after)
    gray = cv2.cvtColor(absdiff, cv2.COLOR_BGR2GRAY)

    # Threshold (0..255); lower = more sensitive
    _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

    # De-noise tiny specks
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    # Apply ignore regions (set changes to 0 inside rectangles)
    _apply_ignore_rects(mask, ignore_rects or [])

    changed_pixels = int(cv2.countNonZero(mask))
    total_pixels = mask.shape[0] * mask.shape[1]
    diff_pct = (changed_pixels / total_pixels) * 100.0

    # Visualization overlay (red)
    highlight = after.copy()
    red_layer = np.zeros_like(after)
    red_layer[:, :] = (0, 0, 255)  # BGR red
    mask_3c = cv2.merge([mask, mask, mask])
    overlay = np.where(mask_3c > 0, red_layer, np.zeros_like(red_layer))
    vis = cv2.addWeighted(highlight, 0.7, overlay, 0.3, 0)

    return mask, float(diff_pct), vis


def _save_record(comp_id: str, record: Dict[str, Any]):
    out_dir = os.path.join(DATA_ROOT, comp_id)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def _load_record(comp_id: str) -> Optional[Dict[str, Any]]:
    out_dir = os.path.join(DATA_ROOT, comp_id)
    meta_path = os.path.join(out_dir, "metadata.json")
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    # Fallback to reconstruct minimal if images exist
    before_path = os.path.join(out_dir, "before.png")
    after_path = os.path.join(out_dir, "after.png")
    diff_path = os.path.join(out_dir, "diff.png")
    mask_path = os.path.join(out_dir, "mask.png")
    if all(os.path.exists(p) for p in [before_path, after_path, diff_path, mask_path]):
        return {
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
    return None


@app.post("/comparison")
async def create_comparison(
    before: UploadFile = File(...),
    after: UploadFile = File(...),
    threshold: int = Form(25),
    ignore_json: Optional[str] = Form(None),  # JSON string: [{x,y,w,h} ...] all normalized 0..1
    _auth: None = Depends(require_api_key),
):
    if not (0 <= threshold <= 255):
        raise HTTPException(status_code=400, detail="threshold must be in [0, 255]")

    try:
        ignore_rects = json.loads(ignore_json) if ignore_json else []
        if not isinstance(ignore_rects, list):
            raise ValueError
    except Exception:
        raise HTTPException(status_code=400, detail="ignore_json must be a JSON array of {x,y,w,h}")

    img_before = _read_image(before)
    img_after = _read_image(after)
    img_before, img_after = _ensure_same_size(img_before, img_after)

    mask, diff_pct, vis = _compute_diff(img_before, img_after, threshold, ignore_rects)

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
        "ignore_rects": ignore_rects,
        "assets": {
            "before_url": f"/data/{comp_id}/before.png",
            "after_url": f"/data/{comp_id}/after.png",
            "diff_url": f"/data/{comp_id}/diff.png",
            "mask_url": f"/data/{comp_id}/mask.png",
        },
    }

    STORE[comp_id] = record
    HISTORY.append(comp_id)
    _save_record(comp_id, record)
    return JSONResponse(record)


@app.get("/comparison/{comp_id}")
async def get_comparison(comp_id: str, _auth: None = Depends(require_api_key)):
    rec = STORE.get(comp_id)
    if not rec:
        rec = _load_record(comp_id)
        if not rec:
            raise HTTPException(status_code=404, detail="comparison not found")
        STORE[comp_id] = rec
    return JSONResponse(rec)


@app.get("/comparisons")
async def list_comparisons(limit: int = Query(10, ge=1, le=50), _auth: None = Depends(require_api_key)):
    # newest first
    ids = list(HISTORY)[-limit:][::-1]
    items = []
    for cid in ids:
        items.append(STORE.get(cid) or _load_record(cid))
    items = [i for i in items if i]
    return {"items": items, "count": len(items)}