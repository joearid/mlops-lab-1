# Lab 5 - CI/CD with GitHub Actions

**Student:** joearid
**Repository:** [https://github.com/joearid/mlops-lab-1](https://github.com/joearid/mlops-lab-1)
**GitHub Actions Workflow:** [.github/workflows/ci.yml](https://github.com/joearid/mlops-lab-1/blob/main/.github/workflows/ci.yml)
**Published Image:** `ghcr.io/joearid/mlops-lab-1`

---

## Question 1: Why is it a bad idea for a unit test to load the real model from your MLflow server?

A unit test must be fast, deterministic, and isolated. Loading the real model from MLflow violates all three:

1. **Network & Infrastructure Dependency:** The test requires a running MLflow server. If the server is down, unreachable, or slow, the test fails, even if the code is perfectly correct.
2. **State Dependency:** The test requires the `champion` alias to exist and the artifact to be in the registry. On a fresh CI runner (which is a blank slate), there is no model in the registry, causing the test to fail with `RESOURCE_DOES_NOT_EXIST`.
3. **Speed:** Downloading a multi-megabyte `.pkl` file and initializing PyTorch takes seconds. Unit tests should run in milliseconds so developers get instant feedback.
4. **Non-Determinism:** If the model in the registry is updated (e.g., `champion` moves to v2), the predictions change, and the test might suddenly fail without any code changes.
5. **Resource Ceiling (GPU & RAM):** The real model may be hundreds of megabytes and require CUDA. A GitHub-hosted runner has no GPU and roughly 7 GB of RAM. Loading the champion can OOM or fall back to CPU-only execution that is 10–100× slower. The test then fails not because your code is wrong, but because the machine is too small for the artifact.

---

## Question 2: What exactly does `test_predict_returns_valid_json` prove, and what does it *not* prove?

**What it proves:**
It proves the **API contract**. It verifies that the FastAPI route correctly parses the uploaded image (multipart form data), passes it to the model, takes the model's output, decodes it using the `CLASSES` array, and returns the correct JSON keys (`category`, `confidence`).

**Evidence : Fake Model used in the test:**
```python
class FakeModel:
    def __call__(self, x):
        # Return a tensor heavily favoring class 0 (Bread)
        return torch.tensor([[10.0] + [0.0] * 10])
```

**What it does not prove:**
It does not prove that the real model is accurate. Because the `FakeModel` always returns `Bread` regardless of the image, the test would pass even if the real PyTorch weights were corrupted, random, or completely untrained. It isolates the web API logic from the machine learning logic.

**Evidence : Test passing locally:**
```text
$ uv run pytest -q
.....                                                                    [100%]
5 passed, 4 warnings in 2.29s
```

---

## Question 3: Which check caught the duplicate, and why is it more dangerous than a corrupted image?

The **MD5 hash check** caught the duplicate. By hashing the file contents (`hashlib.md5(path.read_bytes()).hexdigest()`), the script detected that two different filenames in different splits shared the exact same image data.

**Evidence : `validate_data.py` failure on duplicates:**
```text
$ uv run python -m src.food11.validate_data data/food11_processed_mini --min-per-class 30
...
2. Checking image properties and 4. Checking for duplicates...
  FAIL: Duplicate image across splits: data/food11_processed_mini/validation/Dairy product/1_123.jpg matches training/Dairy product/1_185.jpg
  FAIL: Duplicate image across splits: data/food11_processed_mini/evaluation/Fried food/4_123.jpg matches training/Fried food/4_167.jpg
...
```

**Why it's more dangerous:**
A corrupted image causes an immediate, loud failure. The training script crashes with a PIL `UnidentifiedImageError`, and the developer fixes it.
A train/test duplicate causes **silent data leakage**. The model memorizes the image during training and simply "recognizes" it during evaluation. The test accuracy is artificially inflated. You deploy the model, and it fails catastrophically in the real world because it never learned to generalize.

---

## Question 4: Where in your workflow should `validate_data.py` run?

Since the CI runner cannot see the DVC data (it would need DagsHub credentials and downloading 1.3GB is too slow), the validation should run in two places:

1. **Locally, as a pre-commit / pre-push hook:** Before running `dvc add data`, we run `validate_data.py`. If it fails, we never commit the bad pointer file.
2. **In a dedicated "Data CI" pipeline:** If the GitHub runner authenticates with DagsHub and runs `dvc pull`, `validate_data.py` can run in CI before the model training step. This ensures PRs that modify DVC pointers don't break the data contract.

---

## Question 5: What happens to `smoke` if a unit test fails? What without `needs`?

In GitHub Actions, every job declared within a workflow file is, by default, an autonomous island, a sovereign entity scheduled onto a runner independently, with no knowledge of its siblings' fates. if any job listed in `needs` fails, is skipped, or is cancelled, the dependent job is skipped, not failed, not retried, skipped, marked in the UI with a grey dash and the annotation "Skipped."

**With `needs: test`:**
If `test` fails (e.g., `ruff` finds an error or `pytest` fails), the workflow stops immediately. The `smoke` job is skipped. You do not waste time and compute building a Docker image for broken code.

**Evidence : GitHub Actions failure (15s):**
When `ruff` found an import error in `validate_data.py`, the `test` job failed in 15 seconds, and the `smoke` job never ran.

**Without `needs`:**
`smoke` and `test` would run in parallel. You would wait 5 minutes for the Docker image to build, only to find out the unit tests failed and you have to fix the code and start over.

---

## Question 6: How long did the run take? Which step got faster the second time?

The first successful run took ~6 minutes. The second run took ~1 minute.

**Why it got faster:**
1. **`test` job:** Because we used `astral-sh/setup-uv@v5` with `enable-cache: true`, the second run reused the cached `.venv` (saving the 2–3 minute PyTorch download).
2. **`smoke` job:** Docker's layer caching reused the `RUN uv sync --frozen --no-dev` layer, meaning it didn't re-download PyTorch and dependencies.

---

## Question 7: Why tag with the commit SHA rather than `latest`?

`latest` is a **mutable pointer**. If Machine A pulls `latest` at 10:00 AM and Machine B pulls `latest` at 11:00 AM, they might run completely different code if a new push happened in between. 

Tagging with the **git commit SHA** (e.g., `ghcr.io/joearid/mlops-lab-1:f2c7d0a`) creates an **immutable reference**. You know exactly which code is running, making rollbacks and audits possible.

**Evidence : CI pushing with SHA:**
```yaml
tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
```
**Evidence : Pulling the exact image from GHCR:**
```text
$ docker manifest inspect ghcr.io/joearid/mlops-lab-1:$(git rev-parse HEAD)
{
   "schemaVersion": 2,
   "mediaType": "application/vnd.docker.distribution.manifest.list.v2+json",
   "manifests": [
      {
         "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
         "size": 1603,
         "digest": "sha256:...",
         "platform": {
            "architecture": "amd64",
            "os": "linux"
         }
      },
...
```

---

## Question 8: Why does the `push` job declare `permissions:` explicitly?

`GITHUB_TOKEN` is a short-lived token created automatically for every run. By default, it has read-only access for security. 

To push to `ghcr.io`, the token needs `packages: write`. If we didn't explicitly declare this, the push would fail with a 403 Forbidden error. Declaring it explicitly ensures **least privilege**, the `test` and `smoke` jobs have read-only access, and only `push` can modify packages. If a compromised step runs in `test`, it cannot overwrite your published images.

a malicious dependency (a typo-squatted `pip install`) running in `test` with a broad `GITHUB_TOKEN` could push a poisoned image to `ghcr.io` under your namespace, and that image would then be pulled by production. That is the worst-case scenario the `permissions:` block prevents.


## Question 9: What does the pull request page show? Could you still merge?

If a unit test fails on a PR, the PR page shows a red ❌ next to the failing check. The "Merge pull request" button is greyed out and disabled with a message like *"Merging is blocked: 1 required status check is failing."*

This changes team dynamics: no one can accidentally merge broken code into `main`, regardless of their local machine setup.

*(Note: I configured the `ci.yml` to run `on: [push, pull_request]` so this workflow will run on any PR targeting `main`).*

---
## Question 10: What did the gate decide, and with which numbers? What does `2 * se` represent?

**Test Run 1 — Deliberately bad model (lr=1e-5, epochs=2):**
- Candidate v2 Accuracy: 0.2091
- Champion v1 Accuracy: 0.7515
- Standard Error (n=330): 0.0238
- Threshold (Champion + 2*SE): 0.7991
- Decision: **Rejected** (0.2091 < 0.7991). `challenger` alias set on v2.
**Test Run 2 — Improved model (lr=1e-4, epochs=2):**
- Candidate v3 Accuracy: 0.7636
- Champion v1 Accuracy: 0.7515
- Standard Error (n=330): 0.0238
- Threshold (Champion + 2*SE): 0.7991
- Decision: **Rejected** (0.7636 < 0.7991). `challenger` alias set on v3.

**What `2 * SE` represents:**
The threshold `champion + 2 * SE` is a pragmatic 95% one-sided confidence bound. Under the null hypothesis that the two models have equal accuracy, the candidate's observed advantage is unlikely to exceed two standard errors by chance alone. The gate therefore rejects candidates whose advantage is indistinguishable from noise on a 330-image test set. At an accuracy of ~0.75, `2*SE` is approximately **4.76 accuracy points**. 
In our case, even though v3 was slightly better (0.7636 vs 0.7515, a gain of 1.21 points), the improvement was not large enough to prove it wasn't just a lucky roll of the dice. The gate correctly protected the `champion` production model from being overwritten by a noisy, statistically insignificant update.


---

## Question 11: Name two ways to make `promote.py` run automatically after training.

1. **DagsHub Hosted MLflow + GitHub Actions:** DagsHub offers a hosted MLflow server per repository. You can configure a GitHub Action to train the model, log to DagsHub, and then automatically run `promote.py` using DagsHub credentials injected as GitHub Secrets.
2. **Inline in the training workflow (simplest):** If training runs in GitHub Actions, the promotion gate can be the final step of the same job:
```yaml
- name: Train and log to MLflow
  run: python src/food11/train.py --epochs 10
- name: Promote if the gate passes
  run: python src/food11/promote.py --version ${{ steps.register.outputs.version }}
  env:
    MLFLOW_TRACKING_URI: ${{ secrets.MLFLOW_TRACKING_URI }}
```

No webhook, no dispatch, no separate reachability problem, the same runner that trained the model can immediately query the registry and move the alias.

---

## Question 12: Draw the pipeline.

```text
[Developer Laptop]
  git push
      │
      ▼
[GitHub]
  Trigger: on: [push, pull_request]
      │
      ├──▶ Job: test (Automatic)
      │     ├── Checkout code
      │     ├── Setup uv (cached)
      │     ├── ruff check (Lint)
      │     └── pytest (Unit + API tests)
      │
      ├──▶ Job: smoke (Automatic, needs test)
      │     ├── docker build
      │     └── Run container with SKIP_MODEL=1, curl /health
      │
      └──▶ Job: push (Automatic, needs smoke, only on main)
            ├── Login to ghcr.io
            └── docker buildx push (tag: ${{ github.sha }})

[MLflow Server]
      │
      ▼
  Human runs: promote.py --version N  (Manual step)
      ├── Fetch candidate accuracy
      ├── Fetch champion accuracy
      ├── Calculate SE
      └── Move 'champion' alias (if gate passes)

[Deployment Environment]
  Pulls image: ghcr.io/joearid/mlops-lab-1:<commit-sha>
  Fetches model: models:/food11@champion (fetched at container startup)
```

**Code vs. Model Decisions:**
*   **Code:** Decided by the `git push`. The image is immutably tagged with the `git commit SHA`.
*   **Model:** Decided by the MLflow alias `champion` (mutable pointer). Swappable at runtime without rebuilding the image.

---

## Implementation Notes & Troubleshooting

### 1. GitHub Token `workflow` Scope
When trying to push the initial `.github/workflows/ci.yml` file, the push was rejected:
```text
! [remote rejected] main -> main (refusing to allow a Personal Access Token to create or update workflow `.github/workflows/ci.yml` without `workflow` scope)
```
**Fix:** Generated a new Personal Access Token (Classic) on GitHub with both the `repo` and `workflow` scopes.

### 2. `validate_data.py` and Dataset Resizing
Our initial `food11_processed_mini` was created by simply copying the 512x512 raw images. The `validate_data.py` script caught this immediately (`FAIL: ... is (512, 512), expected (128, 128)`).
**Fix:** Updated `make_mini.py` to actually resize images to 128x128 using PIL and convert them to RGB.

### 3. Duplicate Hash Check
After resizing, `validate_data.py` caught duplicates in the Kaggle dataset (e.g., `1_123.jpg` and `1_185.jpg` had identical content).
**Fix:** Updated `make_mini.py` to deduplicate using `hashlib.md5` before saving.

### 4. Ruff Import Sorting
The first CI run failed in 15 seconds because `ruff` found unsorted imports in `validate_data.py`.
**Fix:** Ran `uv run ruff check --fix src tests` locally, committed, and pushed. The second CI run passed.

---

## Summary of Lab 5 Deliverables

**GitHub (`origin/main`):**
- `.github/workflows/ci.yml`-> the CI pipeline (test, smoke, push)
- `tests/test_data.py` & `tests/test_api.py` -> Unit and API tests
- `src/food11/data.py` -> Pure functions for data processing
- `src/food11/validate_data.py` -> Data contract validation script
- `src/food11/promote.py` -> Statistical promotion gate
- `src/food11/make_mini.py` -> Dataset creation and deduplication script

**Verified end-to-end:**
- CI pipeline passed (green checkmark on GitHub Actions).
- `ruff` and `pytest` ran successfully.
- Docker image built and `/health` returned 200.
- Image pushed to `ghcr.io/joearid/mlops-lab-1:<sha>`.
- `promote.py` accurately rejected a candidate model that did not exceed the `2*SE` threshold.
