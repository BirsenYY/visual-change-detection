# Visual Change Detection

A demo for computing visual differences between two images.

- **Backend**: FastAPI service that validates an API key, saves uploaded images, and returns a diff overlay and mask.
- **Frontend**: React + Vite app that lets users draw ignore regions and submit comparisons, with the API base configurable via `VITE_API_BASE`.

---

## Setup Instructions

### Backend (FastAPI)

#### Create and activate a Conda environment
```bash
conda create -n visualdiff python=3.11 -y
conda activate visualdiff
```

#### Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

#### Configure API keys (REQUIRED)
Set the API key(s) before starting the server:
```bash
export API_KEYS=dev123
```

#### Run the API
```bash
uvicorn app:app --reload --port 8000
```
Images and diff artifacts are stored under `backend/data/` and served at `/data/*`.

### Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev
```
Optionally, override the API base:
```bash
# macOS/Linux shell example (works in the same shell session)
export VITE_API_BASE=http://localhost:8000
# or create a .env file in ./frontend with: VITE_API_BASE=http://localhost:8000
```

---

## Usage
1. Enter your **API key** (the same value you put in `API_KEYS`).
2. Upload **Before** and **After** images.
3. (Optional) Draw rectangles on the **Before** image to **ignore** those regions.
4. Move the sensitivity slider (lower = more sensitive).
5. Click **Compare**.
6. View diff overlay and score; check **Recent comparisons**.

---

## How the visual diff works
The comparison is a fast, pixel‑level diff implemented with OpenCV. High‑level steps:

1. **Load & align**
   - Decode both images as 8‑bit BGR.
   - If sizes differ, resize the *after* image to match the *before* image using area resampling so a 1:1 pixel comparison is possible.

2. **Per‑pixel difference**
   - Compute absolute difference per channel: `absdiff = cv2.absdiff(before, after)`.
   - Collapse to a single intensity map: `gray = cv2.cvtColor(absdiff, cv2.COLOR_BGR2GRAY)`.

3. **Sensitivity / thresholding**
   - The UI slider **0–100** maps to an OpenCV threshold **0–255** (lower = more sensitive).
   - We binarize: `mask = gray >= threshold` (via `cv2.threshold(..., THRESH_BINARY)`).
   - Result: `mask` is **255** for changed pixels, **0** otherwise.

4. **Noise cleanup**
   - Apply a light morphological **open** (3×3 kernel, 1 pass) to remove single‑pixel specks.

5. **Ignore regions** (optional)
   - The frontend lets you draw rectangles on the *Before* image; these are sent as normalized `{x,y,w,h}` in **[0..1]**.
   - On the server, we scale those to pixels and set `mask[y1:y2, x1:x2] = 0` so they don’t count as changes.

6. **Difference score**
   - `difference_percent = (countNonZero(mask) / (H×W)) × 100` and rounded to 4 decimals.
   - Interprets “how much of the image changed,” after thresholding & ignores.

7. **Visualization**
   - Build a red overlay where `mask==255` and alpha‑blend onto the *after* image: `vis = addWeighted(after, 0.7, redOverlay, 0.3, 0)`.
   - The API returns both the **binary mask** and the **diff overlay**.

**Why this approach?**
- It’s **O(N)** over pixels, simple, and predictable for UI screenshots.
- The threshold knob lets you suppress tiny antialiasing/text rendering changes.

**Limitations & tips**
- Very small sub‑pixel/antialias changes can still light up at low thresholds → increase sensitivity (higher threshold) or draw ignore regions.
- Dynamic content (timestamps/cursors/ads) should be ignored using rectangles.
- For perceptual similarity (less sensitive to tiny shifts), a future upgrade could add **SSIM** or a multi‑scale/blurred comparison.

---

## API
- `POST /comparison` — multipart form fields:
  - `before` (file), `after` (file)
  - `threshold` (int, 0..255)
  - `ignore_json` (JSON array of `{x,y,w,h}` normalized 0..1)
  - Header **required**: `X-API-Key: <key>`
- `GET /comparison/{id}` — returns record (requires header)
- `GET /comparisons?limit=10` — recent history (requires header)

### Sample images (included)

This repo includes three before/after pairs under `sample_images/`:
sample_images/
pair1-before.png
pair1-after.png
pair2-before.png
pair2-after.png
pair3-before.png
pair3-after.png


### Sample cURL
```bash
curl -H "X-API-Key: dev123" -X POST http://localhost:8000/comparison   -F "before=@sample_images/pair1-before.png"   -F "after=@sample_images/pair1-after.png"   -F "threshold=25"   -F 'ignore_json=[{"x":0.1,"y":0.1,"w":0.2,"h":0.1}]'
```

---

## Assumptions
- Development uses Conda rather than `venv` for Python environment management.
- Python 3.11 and Node.js 18+ are available.
- A valid API key is provided via the `API_KEYS` environment variable.
- Users have network access to install dependencies and retrieve packages.

---

## Limitations and Recommendations

### Testing

#### Backend — automated tests for the comparison endpoint
There are currently no automated tests validating the image-diff logic or API responses.
- **Add** a `pytest` suite using FastAPI’s `TestClient`.
- **Cover** happy paths and edge cases: threshold sensitivity, ignore regions, size mismatch handling, and persistence of `metadata.json`.
- **Assert** on status codes, response schema, and that expected files are written to `/data/<id>/`.

#### Frontend — test harness and coverage
Frontend tests are not configured; running `npm test` fails because no script is defined.
- **Add** Vitest + React Testing Library.
- **Cover** form validation (missing API key/files), 401 error messaging, slider→threshold mapping, and region-selection interactions.

**Suggested task:** Establish backend and frontend test suites.

### Preview rendering inconsistency
“Before” and “After” previews can render at slightly different sizes even when source dimensions match. This stems from responsive layout constraints and `object-fit` behavior.

**Planned fix:** Normalize preview containers in `App.tsx` (shared aspect ratio, identical wrapper dimensions, consistent padding/borders) to ensure pixel-aligned comparisons.

### Persist comparison records in a database instead of disk files
The API stores metadata and images on disk, which limits scalability and concurrency.

**Suggested task**  
Use SQLite for comparison history

### Improve frontend error handling and UX
Errors are displayed as plain text; there’s no global toast or retry mechanism.

**Suggested task**  
Enhance frontend error UI

---

## Challenges Faced
- Unable to execute or verify the full stack within this environment; behavior was inferred solely from code inspection.
- Ensuring the correct stylesheet import (`styles.css`) in `frontend/src/main.tsx` was necessary to avoid build failures.
- Managing API key configuration and CORS while running backend and frontend locally required careful environment setup.
