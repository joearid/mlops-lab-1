# Lab 1: Git / DVC and Data Preparation

**Student:** joearid
**Repo:** https://github.com/joearid/mlops-lab-1
**DVC remote:** https://dagshub.com/joearid/mlops-lab-1.dvc

---

## Question 1: Observe the files created by `uv init`. What do they contain?

`uv init` created a minimal Python project skeleton:

| File | Purpose |
|---|---|
| `pyproject.toml` | Project metadata and dependencies. Contains `[project]` (name, version, Python version, dependency list), `[project.scripts]`, and `[build-system]` (uses `uv_build` as backend). |
| `.python-version` | Pins the Python version uv uses for this project (for example `3.10`). |
| `README.md` | Placeholder readme. |
| `src/semestre1uni/__init__.py` | Empty package file. Makes `src/semestre1uni` an importable Python package. |
| `.gitignore` | Default Python ignores (`__pycache__`, `.venv`, `*.egg-info`, `dist/`, etc.). |

---

## Question 2: What did `dvc init` create? What are they used for? Which ones should be pushed to git?

`dvc init` created:

| File / folder | Purpose |
|---|---|
| `.dvc/` | DVC's internal directory. Contains `config` (remote definitions and default remote), `.gitignore` (ignores DVC temp files inside `.dvc/`), and `tmp/` (local scratch space). |
| `.dvcignore` | Lists paths DVC should ignore when scanning the workspace (like `.gitignore` but for DVC). |

Should be pushed to git:

- `.dvc/config` - non-secret config (remote URL, default remote). Only if it contains no credentials.
- `.dvc/.gitignore` - auto-generated, keeps DVC temp files out of git.
- `.dvcignore`

Should not be pushed:

- `.dvc/tmp/` - local scratch.
- `.dvc/cache/` - local cache (content-addressed copies of tracked data).
- Any `.dvc/config.local` file - meant for local-only settings.
- Any credentials (passwords/tokens) - must live only in `~/.config/dvc/config`.

---

## Question 3: Where are the credentials stored? What are the options other than `--global`? Should the credentials be pushed to GitHub?

**Storage locations:**

| Flag       | Location                           | Scope                                  |
| ---------- | ---------------------------------- | -------------------------------------- |
| `--global` | `~/.config/dvc/config` (Linux/Mac) | All projects for the current user      |
| `--system` | `/etc/dvc/config` (Linux)          | All users on the machine (needs admin) |
| `--local`  | `.dvc/config.local`                | Current project only, never committed  |
| (no flag)  | `.dvc/config`                      | Current project, committed to git      |

Should credentials be pushed to GitHub? No.

We hit this exact issue in practice. When we ran:

```bash
dvc remote add --global origin https://dagshub.com/joearid/mlops-lab-1.dvc
dvc remote modify origin --global auth basic
dvc remote modify origin --global user joearid
dvc remote modify origin --global password <token>
```

The credentials originally ended up in `.dvc/config` (project-level, committed to git). We fixed this by:

1. `dvc remote modify origin --unset password` - remove from project config
2. `dvc remote modify origin --unset user` - remove from project config
3. `dvc remote modify --global origin user joearid` - store in `~/.config/dvc/config`
4. `dvc remote modify --global origin password <token>` - store in `~/.config/dvc/config`

Result:

- `.dvc/config` on GitHub contains only: `url`, `auth = basic`
- `~/.config/dvc/config` (not committed) contains: `url`, `auth`, `user`, `password`

Additionally, since the token was briefly exposed in git, the token was rotated on DAGsHub.

---

## Question 4: Look at the `.gitignore` file. Explain what happened.

After running `dvc add data`, DVC automatically appended:

```
/data
```

to `.gitignore`. This means git now ignores the entire `data/` folder.

Instead of git tracking the raw image files (thousands of files totaling over a GB), DVC tracks them and only the tiny pointer file `data.dvc` is committed to git. This keeps the git repo lightweight (git is bad at large binaries), while DVC handles content-addressed storage of the heavy data.

---

## Question 5: Do you see a `.dvc` file? What does it contain?

Yes. `data.dvc` at the repo root. Contents:

```yaml
outs:
- md5: 1f2be610c54d1f5e151051a72898d7f6.dir
  size: 1339489037
  nfiles: 18403
  hash: md5
  path: data
```

| Field | Meaning |
|---|---|
| `md5` | MD5 hash of the directory manifest (`.dir` file). Any change to any file inside the folder changes this hash, so DVC knows when the data changes. |
| `size` | Total size in bytes (about 1.34 GB) |
| `nfiles` | Number of files tracked (18,403) |
| `hash` | Hash algorithm used (md5) |
| `path` | Path to the tracked data folder |

This file is tiny (about 110 bytes) but fully describes the dataset state. Anyone with this pointer plus remote access can reconstruct the exact data.

---

## Question 6: GitHub web UI vs DAGsHub web UI. Where is what?

GitHub (`github.com/joearid/mlops-lab-1`):

- Code (`src/`, `pyproject.toml`, `uv.lock`, `.dvcignore`)
- `.dvc/config` (non-secret)
- `data.dvc` - the pointerto the data
- `.gitignore` (contains `/data`)
- not the actual images

**DAGsHub** (`dagshub.com/joearid/mlops-lab-1`):

- The actual data - `data/food11_raw/{training,evaluation,validation}` with all 16,643+ images
- The DVC pointer `data.dvc` is also visible there (mirror of GitHub)

So: code and pointer on GitHub, actual data on DAGsHub, and `data.dvc` is the bridge between them.

---

## Question 7: Fresh clone. Do you see the data folder? What DVC command gets it?

After cloning the repo into a fresh temp folder:

```bash
git clone https://github.com/joearid/mlops-lab-1.git
cd mlops-lab-1
ls data/          # error: no such file
```

- You do not see the `data/` folder with images.
- You do see `data.dvc` (the pointer) and `.gitignore`.

To fetch the actual data:

```bash
dvc pull
```

`dvc pull`:

1. Reads `data.dvc` and gets the directory hash `1f2be610...`
2. Contacts the DAGsHub remote (`https://dagshub.com/joearid/mlops-lab-1.dvc`)
3. Downloads every missing content-addressed file into the local DVC cache
4. Checks out the files into `data/`, verifying integrity via hashes

(Technically `dvc pull` = `dvc fetch` + `dvc checkout`.)

---

## Question 8: After checking out an older commit, do you still see `food11_processed` and `food11_processed_mini`?

No. Git and DVC must be moved together to time-travel correctly.

```bash
# 1. See which commits touched data.dvc
git log --oneline -- data.dvc
```

Example history for this repo:

```
6b987d2 Update data pointer to include mini dataset
f71fdd4 Reorganize raw Food-11 data into class folders
d46bf85 Track data folder with dvc
```

To check out an old data state:

```bash
# 2. Move the pointer (git) back
git checkout <old-commit-hash>
# 3. Move the actual data files (DVC) to match
dvc checkout
```

After both commands, the `food11_processed_mini/` folder disappears That old commit's `data.dvc` had a different hash and did not reference the mini dataset. DVC replaces the workspace content with what the old pointer described.

Why both commands? Git handles the `data.dvc` pointer (tiny text), DVC handles the actual data files. If you only run `git checkout`, the pointer changes but the files on disk do not, so DVC reports the workspace as out of sync. `dvc checkout` reconciles the files to match the pointer.

To return to the current state:

```bash
git checkout main
dvc checkout
```