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

## API
- `POST /comparison` — multipart form fields:
  - `before` (file), `after` (file)
  - `threshold` (int, 0..255)
  - `ignore_json` (JSON array of `{x,y,w,h}` normalized 0..1)
  - Header **required**: `X-API-Key: <key>`
- `GET /comparison/{id}` — returns record (requires header)
- `GET /comparisons?limit=10` — recent history (requires header)

### Sample cURL
```bash
curl -H "X-API-Key: dev123" -X POST http://localhost:8000/comparison   -F "before=@sample_images/before.png"   -F "after=@sample_images/after.png"   -F "threshold=25"   -F 'ignore_json=[{"x":0.1,"y":0.1,"w":0.2,"h":0.1}]'
```

---

## Assumptions
- Development uses Conda rather than `venv` for Python environment management.
- Python 3.11 and Node.js 18+ are available.
- A valid API key is provided via the `API_KEYS` environment variable.
- Users have network access to install dependencies and retrieve packages.

---

## What I'd Improve With More Time

### Add automated backend tests for the comparison endpoint
Currently, the project lacks unit tests to verify diff logic or API responses.

**Suggested task**  
Add backend comparison tests

**Start task**

### Persist comparison records in a database instead of disk files
The API stores metadata and images on disk, which limits scalability and concurrency.

**Suggested task**  
Use SQLite for comparison history

**Start task**

### Improve frontend error handling and UX
Errors are displayed as plain text; there’s no global toast or retry mechanism.

**Suggested task**  
Enhance frontend error UI

**Start task**

---

## Challenges Faced
- Unable to execute or verify the full stack within this environment; behavior was inferred solely from code inspection.
- Ensuring the correct stylesheet import (`styles.css`) in `frontend/src/main.tsx` was necessary to avoid build failures.
- Managing API key configuration and CORS while running backend and frontend locally required careful environment setup.
