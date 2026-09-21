# Lab 2: Model Training and Experiment Tracking with MLflow

**Student:** joearid
**Repo:** https://github.com/joearid/mlops-lab-1
**MLflow tracking server:** http://127.0.0.1:5000
**Experiment:** food11 (id 1)

## Question 1: What changed in `pyproject.toml` and `uv.lock`?

**`pyproject.toml`** gained:

- 4 new dependencies: `mlflow>=3.16.0`, `scikit-learn>=1.7.2`, `torch>=2.14.0`, `torchvision>=0.29.0`
- A `[[tool.uv.index]]` block named `pytorch-cpu` (URL `https://download.pytorch.org/whl/cpu`, `explicit = true`)
- A `[tool.uv.sources]` block telling uv to resolve `torch` and `torchvision` from that CPU-only index

**`uv.lock`** grew dramatically: from a small file to about 4,100 lines / 915 KB, pinning about 101 packages with exact versions and SHA256 hashes. `torch` alone pulls in about 30 transitive deps and `mlflow` pulls in about 40.

Verified CPU-only build:

```python
>>> import torch
>>> torch.__version__
'2.14.0+cpu'
>>> torch.cuda.is_available()
False
```

## Question 2: What are `--backend-store-uri` and `--default-artifact-root`? Metadata vs artifacts?

**`--backend-store-uri sqlite:///mlflow.db`**
Stores **metadata**: experiments, runs, params, metrics, tags, timestamps, and paths to artifacts. Uses SQLite. Production uses Postgres/MySQL.

**`--default-artifact-root ./mlruns`**
Stores artifacts: actual files produced by runs, such as logged models, plots, CSVs, checkpoints. Filesystem here, S3/GCS in production.

| | Metadata | Artifacts |
|---|---|---|
| Content | Runs, params, metrics, tags | Model files, images, plots |
| Size | Small, structured | Large, unstructured |
| Storage | SQL database | Filesystem / object storage |
| Purpose | Fast queries for the UI | Deliverables to download |

**Why split?** Query millions of runs cheaply (SQL rows) while keeping multi-GB artifacts on cheap blob storage. Fetching artifacts is on-demand; querying metadata is instant.

## Question 3: Why shouldn't `mlflow.db` and `mlruns/` be tracked by git or dvc?

Not in git:

- Local run outputs, regenerated every training run
- Contain machine-specific paths and run IDs
- Binary SQLite file plus hundreds of model artifacts cause huge repo bloat and no meaningful diffs
- Change constantly, producing noisy commit history

Not in dvc:

- DVC versions datasets and large model artifacts you want to snapshot and share
- MLflow is already the source of truth for its own metadata and artifacts
- Adding `mlruns/` to DVC would duplicate tracking and the two systems would drift
- MLflow runs are meant to be queried live via the tracking server, not frozen as snapshots

Rule of thumb: git = code, DVC = data/models, MLflow = experiment tracking.

## Question 4: What happens the first time you call `set_experiment("food11")`?

MLflow auto-creates the experiment:

```
2026/09/18 15:41:00 INFO mlflow.tracking.fluent: Experiment with name 'food11' does not exist. Creating a new experiment.
```

The experiment immediately appears in the UI (Experiment ID: 1). This makes scripts idempotent. Subsequent calls return the existing experiment.


## Question 5: `log_param` vs `log_metric`. Why does `log_metric` take `step`?

| | `mlflow.log_param` | `mlflow.log_metric` |
|---|---|---|
| What | Fixed value set before training | Value produced during/after training |
| Examples | lr, batch_size, epochs | train_loss, val_loss, val_accuracy |
| Changes during run? | No | Yes |
| Takes `step`? | No | Yes |
| UI display | Key-value table | Line chart vs step |

Why `step`? A metric like `val_accuracy` is logged every epoch, producing a sequence `[0.10, 0.71, ...]`. `step` (usually epoch) orders those points on the x-axis. A param has one value per run, so no step is needed.


## Question 6: Where does the model artifact live on disk?

The server was started with `--default-artifact-root ./mlruns` (relative to repo root). For any run (experiment 1, run id `0388f4a289bc40a2ba20e46ad99cf4f2`):

```
./mlruns/1/0388f4a289bc40a2ba20e46ad99cf4f2/artifacts/model/
```

Contents:

- `MLmodel` - MLflow model metadata (flavor, signature, env)
- `model.pkl` - the pickled PyTorch state dict
- `python_env.yaml` - Python version plus pip/uv requirements
- `requirements.txt` - exported dependency list
- `conda.yaml` - conda environment spec

Verify:

```bash
ls -la mlruns/1/0388f4a289bc40a2ba20e46ad99cf4f2/artifacts/model/
```

The metadata DB stores only the path to this folder, not the model bytes.


## Question 7: Which learning rate gave the best `val_accuracy`? Is higher always better?

Real results from 3 runs on the mini dataset:

| Run | lr | batch | val_acc (ep2) | test_acc | Notes |
|---|---|---|---|---|---|
| `nervous-eel-343` | 0.01 | 32 | 0.1030 | 0.1091 | Diverged |
| `caring-ant-108` (1 epoch) | 0.001 | 32 | 0.4364 | 0.3909 | Intermediate |
| `casual-hen-500` | 0.0001 | 32 | **0.7091** | **0.7515** | Best |

**Which is best?** `lr = 0.0001` gave the highest val_accuracy (0.7091) and test accuracy (0.7515).

**Is higher always better? No. This run proves it clearly.**

- `lr = 0.01` (too high): training **diverged**. val_loss exploded (26.95 after epoch 1), val_accuracy stayed near random (1/11 is about 0.09). The optimizer overshot the loss surface on every step.
- `lr = 0.0001` (small): slow but **stable convergence**. train_loss dropped steadily (1.77 to 0.60), val_acc rose (0.67 to 0.71).
- `lr = 0.001` (medium): worked but not as well within the limited epochs.

There is no monotonic "higher = better" rule. There is a sweet spot, and outside it (too high or too low) accuracy suffers.

## Question 8: Parallel coordinates plot. What pattern?

Plotting the three runs on axes `lr`, `batch_size`, `val_accuracy`:

- The line converging to **val_accuracy about 0.71** passes through **lr = 0.0001**.
- The line at **val_accuracy about 0.10** (random) passes through **lr = 0.01**.
- The middle line at **about 0.44** passes through **lr = 0.001**.
- `batch_size` was constant at 32, so it does not show variation here.

**Pattern:** accuracy vs lr is **non-monotonic**. It peaks at a moderate-to-small lr and collapses at high lr. The plot visually isolates the "too-high" lr region.

(A fully rigorous parallel-coordinates study would also vary `batch_size`; we kept it fixed at 32 to isolate the lr effect.)

## Question 9: Sort runs by `val_accuracy`. Which is best? Note its run ID.

**Best run:**

| Field | Value |
|---|---|
| Name | `casual-hen-500` |
| Experiment | `food11` (id 1) |
| **Run ID** | **`78fc718cad8d4f7ca3992302d891484e`** |
| Params | `lr=0.0001`, `batch_size=32`, `epochs=2`, `model=resnet18`, `optimizer=adam`, `dataset=mini` |
| `val_accuracy` (ep2) | **0.7091** |
| `test_accuracy` | **0.7515** |

This run ID will be used in Lab 3 for model registration.


## Summary of deliverables

**GitHub (`origin/main`):**

- `src/food11/train.py` - training script
- `pyproject.toml`, `uv.lock` - dependencies (CPU-only torch)
- `.gitignore` - ignores `data/`, `mlflow.db`, `mlruns/`
- `data.dvc` - DVC pointer covering raw and mini datasets
- `.dvc/config` - non-secret remote config

**DAGsHub:**

- DVC remote with the Food-11 datasets

**Local MLflow:**

- Tracking server at `http://127.0.0.1:5000`
- Experiment `food11` with 3 runs:
  - `nervous-eel-343` (lr=0.01) - val_acc=0.1030
  - `caring-ant-108` (lr=0.001, 1 epoch) - val_acc=0.4364
  - `casual-hen-500` (lr=0.0001) - val_acc=0.7091 (best)
- Metadata: `mlflow.db`
- Artifacts: `mlruns/`