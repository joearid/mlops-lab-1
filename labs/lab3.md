# Lab 3: Containerizing the Model with Docker

**Student:** joearid  
**Repository:** [https://github.com/joearid/mlops-lab-1](https://github.com/joearid/mlops-lab-1)  
**MLflow Tracking Server:** `http://127.0.0.1:5000`  
**Registered Model:** `food11`, version 1, alias `@champion`  
**Docker Image:** `food11-api:latest`, 1.67 GB, multi-stage build

---

## Question 1: What version number was your model given? What is the difference between a run's logged model artifact and a registered model?

**Version:** `1`, created on 09/21/2026 at 05:14:32 PM, with the alias `champion`.

### Evidence: Registration Output

```text
$ uv run python -c "
import mlflow
mlflow.set_tracking_uri('http://127.0.0.1:5000')
result = mlflow.register_model(
    'runs:/78fc718cad8d4f7ca3992302d891484e/model',
    'food11'
)
print('Version:', result.version)
print('Name:', result.name)
"

Successfully registered model 'food11'.
Created version '1' of model 'food11'.
Version: 1
Name: food11
```

### Evidence: MLflow UI

The MLflow Model Registry shows:

|Field|Value|
|---|---|
|Model name|`food11`|
|Version|**1**|
|Registered at|09/21/2026, 05:14:32 PM|
|Created by|joearid|
|Alias|`@champion`|

### Difference Between a Logged Model Artifact and a Registered Model

||Logged model artifact|Registered model|
|---|---|---|
|Scope|Belongs to a single run|Named entity with its own lifecycle|
|Identity|`runs:/<run-id>/model` or an internal model ID|Stable name plus version|
|Versioning|No registry version history|Explicit versions such as 1, 2, 3, ...|
|Metadata|Run-level metadata|Description, tags, aliases, and lineage|
|Purpose|Experiment tracking|Model delivery and deployment|

A logged model is a snapshot produced by an individual experiment run. A registered model is a managed deployment artifact with its own lifecycle and version history.

In this case, the run produced the model, and that model was subsequently registered as `food11` version 1. The `champion` alias then provides a stable reference to the version currently selected for serving.

---

# Question 2: What aliases replaced the old built-in stages? Why version a model separately from the run, and why is an alias more flexible than a fixed stage name?

MLflow replaced the older built-in model stages such as `None`, `Staging`, `Production`, and `Archived` with **model aliases**.

Aliases are free-form names such as:

```text
champion
challenger
latest
baseline
canary
shadow
```

### Evidence: Alias Assignment

```text
$ uv run python -c "
import mlflow
mlflow.set_tracking_uri('http://127.0.0.1:5000')
client = mlflow.MlflowClient()
client.set_registered_model_alias('food11', 'champion', 1)
mv = client.get_model_version_by_alias('food11', 'champion')
print('champion -> version', mv.version, '| run_id:', mv.run_id)
"

champion -> version 1 | run_id: 78fc718cad8d4f7ca3992302d891484e
```

The MLflow UI also shows the `@champion` badge next to version 1.

### Why Version the Model Separately from the Run?

The run and the registered model serve different purposes.

The **run** records where and how the model was produced. It contains information such as parameters, metrics, artifacts, and experiment metadata.

The **registered model** represents the model that is available for delivery or deployment.

This separation provides several benefits:

1. A new training run can produce a new model without changing the deployment interface.
    
2. Multiple model versions can coexist in the registry.
    
3. A deployment can refer to an alias rather than a specific version.
    
4. The same model artifact can be associated with different deployment workflows.
    
5. Runs remain historical records, while aliases provide mutable deployment pointers.
    

### Why Are Aliases More Flexible Than Fixed Stages?

Fixed stages provide a predefined set of states. Aliases instead allow teams to define names appropriate to their own workflow.

For example:

```text
champion -> version 2
challenger -> version 3
canary -> version 4
```

The version numbers remain immutable, while the aliases can be repointed.

For example:

```python
client.set_registered_model_alias("food11", "champion", 2)
```

changes which version is referenced by `champion` without modifying the version numbers themselves.

This separates the model registry mechanism from the deployment policy chosen by a team.

---

# Question 3: Why load the model through an MLflow model URI instead of pointing directly to the `.pth` file on disk? What would you have to change to serve a newer model version?

The serving application uses:

```python
MODEL_URI = "models:/food11@champion"
```

rather than a hardcoded `.pth` file.

### Why Use an MLflow Model URI?

**1. Decoupling**

The application does not need to know which file contains the model or which training run produced it. It asks MLflow for the model currently associated with the `champion` alias.

**2. Model updates without rebuilding the image**

If version 2 becomes the new champion, the application can continue using:

```text
models:/food11@champion
```

without changing the source code or rebuilding the Docker image.

**3. Model metadata**

An MLflow model contains information about its environment and model format, including files such as `MLmodel`, environment specifications, and dependency information.

A raw `.pth` file does not provide the same model-management information.

**4. Lineage**

The registered model can be traced back to its source run, parameters, metrics, artifacts, and other experiment information.

**5. Portability**

The model URI abstracts the artifact location. The underlying artifact can be stored using different storage backends rather than requiring the application to know a particular filesystem path.

### Evidence: `serve.py`

```python
MLFLOW_TRACKING_URI = os.environ.get(
    "MLFLOW_TRACKING_URI",
    "http://127.0.0.1:5000"
)

MODEL_URI = "models:/food11@champion"
```

### Evidence: Server Startup

```text
INFO: Started server process [15274]
INFO: Waiting for application startup.
Loading model from models:/food11@champion
(tracking uri: http://127.0.0.1:5000)
Model loaded successfully.
INFO: Application startup complete.
```

### How Would a Newer Model Version Be Served?

No source-code change is required.

The process is:

1. Register the new model as a new version.
    
2. Assign the `champion` alias to that version.
    
3. Restart the serving container.
    

For example:

```text
champion -> version 2
```

The application continues to request:

```text
models:/food11@champion
```

and MLflow resolves that URI to version 2.

---

# Question 4: Why copy `pyproject.toml` and `uv.lock` and run `uv sync` before copying the rest of the source code? What happens to the build cache when you only change a line in `serve.py`?

Docker builds are composed of layers. Docker can reuse a layer when the instruction and its inputs have not changed.

Therefore, dependency files should be copied before source code that changes frequently.

The Dockerfile uses:

```dockerfile
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
```

The dependency installation depends on `pyproject.toml` and `uv.lock`, but not on the application source.

If `serve.py` changes, the dependency layer remains cached.

### Dockerfile

```dockerfile
# Stage 1: builder
FROM python:3.10-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Stage 2: runtime
FROM python:3.10-slim

COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/
```

### Evidence: Cached Layers

```text
Step 4/15 : COPY pyproject.toml uv.lock ./
 ---> Using cache

Step 5/15 : ENV UV_PROJECT_ENVIRONMENT=/app/.venv ...
 ---> Using cache

Step 6/15 : RUN uv sync --frozen --no-dev --no-install-project
 ---> Using cache
```

When only `serve.py` changes:

- The base image remains cached.
    
- The `uv` binary remains cached.
    
- `pyproject.toml` and `uv.lock` remain cached.
    
- The `uv sync` layer remains cached.
    
- `COPY src/ ./src/` is rebuilt.
    
- Subsequent layers are rebuilt as necessary.
    

The approximately 1.5 GB virtual environment therefore does not have to be recreated after every source-code change.

This significantly reduces rebuild time.

---

# Question 5: What is the size difference between a naive single-stage image and your multi-stage image? Use `docker history` to identify the largest layers.

The two images were measured on the same machine using the same `.dockerignore`.

|Image|Disk usage|
|---|--:|
|`food11-api:latest`|**1.67 GB**|
|`food11-api-naive:latest`|**2.55 GB**|
|Difference|**~880 MB**|

The naive image is approximately 52% larger.

### Evidence: `docker images`

```text
IMAGE                    ID             DISK USAGE
food11-api-naive:latest  49eeb0ea127b   2.55GB
food11-api:latest        acde5c7e2305   1.67GB
```

### Multi-Stage Image

The largest layers reported by `docker history` were:

|Layer|Size|Description|
|---|--:|---|
|Virtual environment|**1.55 GB**|PyTorch, SciPy, pandas, NumPy, MLflow, etc.|
|`python:3.10-slim` base|~123 MB|Debian root filesystem and Python|
|`COPY src/`|**18.6 kB**|Application source|
|Other metadata layers|~9 kB|Environment, user, command, etc.|
|**Total**|**~1.67 GB**||

Approximately 93% of the final image consists of Python dependencies.

### Naive Single-Stage Image

|Layer|Size|Description|
|---|--:|---|
|`RUN uv sync --frozen --no-dev`|1.39 GB|Python dependencies|
|`COPY . .`|938 kB|Project files|
|`COPY --from=uv`|56.1 MB|`uv` binary|
|`apt-get install ...`|2.18 MB|Build tools|
|`python:3.10` base layers|~1.10 GB|Full Python base image|
|**Total**|**~2.55 GB**||

### Source of the Difference

The main difference is the runtime base image.

The naive image uses:

```text
python:3.10
```

while the multi-stage image uses:

```text
python:3.10-slim
```

The measured base-image difference is approximately 978 MB.

The `apt-get` layer itself contributes only about 2.18 MB.

The important advantage of the multi-stage design is that build-time requirements do not have to remain in the final runtime image. A project requiring compilation could use a larger builder image while retaining a small runtime image.

---

# Question 6: What happens to build speed and image size if you forget the `.dockerignore`? Which excluded folders would actually break the build if sent to the Docker daemon?

The repository contains several large directories that should not be included in the Docker build context.

|Folder|Size|Consequence|
|---|--:|---|
|`data/`|**1.3 GB**|Large unnecessary upload and potentially embeds training data|
|`mlruns/`|**129 MB**|Sends local MLflow artifacts and metadata|
|`.venv/`|**1.5 GB**|Sends the host virtual environment|
|`.git/`|2.5 MB|Sends Git history unnecessarily|
|`__pycache__/`|Small|Sends machine-specific bytecode|

### Evidence: Host Directory Sizes

```text
1.3G    data/
129M    mlruns/
1.5G    .venv/
2.5M    .git/
```

With the `.dockerignore` file, the build context was:

```text
Sending build context to Docker daemon  952.3kB
```

Without the `.dockerignore`, the build context would be approximately 3 GB.

This represents roughly a 3000-fold increase compared with the measured 952.3 kB context.

Every build would therefore have to transfer a much larger amount of data to the Docker daemon.

### Which Directories Cause Problems?

The `.venv/` directory is particularly problematic because it represents the host Python environment. The container should create its own environment using the container's Python version and the project's lock file.

Including `data/` would not necessarily cause a build failure, but it would unnecessarily add approximately 1.3 GB of training data to the build context and potentially to the image.

Including `mlruns/` would similarly add unnecessary local MLflow artifacts and could cause confusion between local artifacts and the configured tracking server.

Including `.git/` would not normally break the build, but it would unnecessarily expose repository history inside the build context.

The conclusion about these folders causing functional problems is based on the project configuration rather than a build performed without `.dockerignore`. The measured build-context size, however, was directly observed.

---

# Question 7: Why can't the container simply use `127.0.0.1:5000` to reach the MLflow server on the host? What does `host.docker.internal` resolve to?

Normally, `127.0.0.1` inside a container refers to the container itself.

A container has its own network namespace and its own loopback interface. Therefore:

```text
127.0.0.1:5000
```

inside the container does not normally refer to:

```text
127.0.0.1:5000
```

on the host.

### Linux Setup Used in This Lab

The container was run using:

```text
--network host
```

With host networking, the container shares the host's network namespace. Therefore, in this particular setup:

```text
127.0.0.1:5000
```

inside the container refers to the host's MLflow server.

This approach is simple but provides less network isolation.

### `host.docker.internal`

On Docker Desktop for macOS and Windows, Docker provides:

```text
host.docker.internal
```

This hostname resolves to an address that allows a container to communicate with the host.

On Linux, the equivalent can be provided with:

```text
--add-host=host.docker.internal:host-gateway
```

The exact address behind `host.docker.internal` depends on the Docker environment. It is a Docker-provided hostname rather than a normal public Internet hostname.

### Important Additional Issue: MLflow Artifact Storage

The container initially failed even though it could reach the MLflow tracking server.

Without the volume mount:

```text
$ docker run --rm --network host \
  -e MLFLOW_TRACKING_URI=http://127.0.0.1:5000 \
  food11-api:latest

INFO: Loading model from models:/food11@champion
ERROR: mlflow.exceptions.MlflowException: No such artifact: ''
```

The model was registered using a local filesystem artifact store.

The MLflow model version points to:

```text
models:/m-6cf1bd65420443638191b6970b181615
```

and the corresponding artifact exists on disk at:

```text
mlruns/1/models/m-6cf1bd65420443638191b6970b181615/artifacts
```

The MLflow server stores this as an absolute host filesystem path:

```text
file:///home/lo/...
```

Therefore, the container needs access to that path.

The working command was:

```text
$ docker run --rm --network host \
  -v /home/lo/Desktop/vscode/semestre1uni/mlruns:/home/lo/Desktop/vscode/semestre1uni/mlruns \
  -e MLFLOW_TRACKING_URI=http://127.0.0.1:5000 \
  food11-api:latest
```

This produced:

```text
INFO: Loading model from models:/food11@champion
Model loaded successfully.
INFO: Application startup complete.
Uvicorn running on http://0.0.0.0:8000
```

### Production Solution

A production deployment should use remote artifact storage such as:

```text
S3
GCS
Azure Blob Storage
```

The container could then download the model artifact from the remote store rather than depending on a host filesystem mount.

---

# Question 8: Stop the container and start a new one from the same image. Does the model still load correctly without rebuilding? What does this tell you about what is baked into the image versus fetched at runtime?

Yes. The model loaded correctly after stopping the original container and starting a new container from the same image. No image rebuild was required.

### Original Container

```text
$ docker ps

CONTAINER ID   IMAGE               COMMAND                  STATUS
c625583e3fbf   food11-api:latest   "uvicorn src.food11…"   Up
```

The container was stopped:

```text
$ docker stop $(docker ps -q --filter ancestor=food11-api:latest)
c625583e3fbf
```

No containers remained running.

A new container was then started from the same image:

```text
$ docker run --rm --network host \
  -v /home/lo/Desktop/vscode/semestre1uni/mlruns:/home/lo/Desktop/vscode/semestre1uni/mlruns \
  -e MLFLOW_TRACKING_URI=http://127.0.0.1:5000 \
  food11-api:latest
```

The application successfully loaded the model:

```text
INFO: Started server process [1]
INFO: Waiting for application startup.
Loading model from models:/food11@champion
Model loaded successfully.
INFO: Application startup complete.
Uvicorn running on http://0.0.0.0:8000
```

### Prediction Comparison

The prediction before and after restarting the container was identical:

```json
{
  "predicted_class": "Bread",
  "confidence": 0.8322247266769409
}
```

The complete probability distribution was also identical to the displayed precision.

This demonstrates that the trained weights were not baked into the Docker image. Instead, the image contains the application and its dependencies, while the model is retrieved from MLflow when the container starts.

### Baked Into the Image vs. Fetched at Runtime

|Baked into the image|Fetched at runtime|
|---|---|
|Python 3.10 runtime|Registered model weights|
|Debian system libraries|MLflow model artifacts|
|Python dependencies|Model metadata|
|PyTorch|Any external model artifacts|
|FastAPI and Uvicorn||
|Application source code||

The image is therefore immutable with respect to the application code and environment, while the model can be changed independently through the MLflow registry.

The tradeoff is that the container is not completely self-contained. It requires access to MLflow and its artifact store when it starts.

---

# Question 9: The Dockerfile and image are versioned differently. One lives in Git, while the other does not yet. What is still missing before another machine, such as a CI runner or Kubernetes cluster, could reliably pull and run the exact image you built?

### Current State

The repository contains the Docker build recipe:

```text
Dockerfile
.dockerignore
src/food11/serve.py
pyproject.toml
uv.lock
```

The Docker image currently exists only in the local Docker daemon:

```text
food11-api:latest
```

### Evidence: Versioned Dockerfile

```text
$ git ls-files | grep -E "(Dockerfile|dockerignore|serve\.py)"

.dockerignore
Dockerfile
src/food11/serve.py
```

These files were committed in:

```text
1035b80 Containerize model serving with Docker
```

The serving code was subsequently committed in:

```text
d2dc705
```

### Evidence: Local-Only Image

```text
$ docker images food11-api:latest

IMAGE               ID             DISK USAGE
food11-api:latest   acde5c7e2305   1.67GB
```

There is no registry prefix such as:

```text
docker.io/...
ghcr.io/...
```

Therefore, another machine cannot pull this image from the Internet.

## What Is Still Missing?

### 1. Push the Image to a Container Registry

The image needs to be published to a registry such as:

```text
Docker Hub
GitHub Container Registry
Amazon ECR
Google Artifact Registry
Azure Container Registry
```

### 2. Use an Immutable Image Identifier

`latest` is a mutable tag. For reproducible deployments, the image should also have a version-specific identifier, for example:

```text
food11-api:1.0.0
food11-api:git-1035b80
```

The strongest immutable identifier is the image digest:

```text
sha256:...
```

### 3. Configure Registry Authentication

If the registry is private, CI and Kubernetes need appropriate credentials, pull secrets, or cloud IAM permissions.

### 4. Add a CI Pipeline

A CI pipeline can connect the Git commit to the container image:

```text
git push
    |
    v
CI build
    |
    v
docker build
    |
    v
tag with Git SHA
    |
    v
docker push
```

For example:

```text
$REGISTRY/food11-api:$GIT_SHA
```

### 5. Move MLflow Artifacts to Remote Storage

The current MLflow configuration depends on local filesystem artifacts.

A portable deployment should use:

```text
S3
GCS
Azure Blob Storage
```

This removes the requirement to mount the host's `mlruns` directory into the container.

### 6. Use a Real MLflow Server URL

Instead of:

```text
http://127.0.0.1:5000
```

the deployed container should use a network-accessible MLflow endpoint such as:

```text
https://mlflow.example.internal
```

Authentication and TLS should be configured appropriately.

### 7. Add a Deployment Configuration

A Kubernetes deployment would normally include resources such as:

```text
Deployment
Service
Ingress
```

or an equivalent Helm chart.

The deployment configuration should specify the exact container image and provide the MLflow tracking URI and required secrets.

### 8. Pin Base Images

The Dockerfile currently uses floating tags such as:

```dockerfile
FROM python:3.10-slim
```

and:

```dockerfile
FROM ghcr.io/astral-sh/uv:latest
```

For stronger reproducibility, these can be pinned to image digests.

---

# Implementation Note: `pyfunc` vs. `pytorch` Model Loading

The lab instructions suggest:

```python
mlflow.pyfunc.load_model("models:/food11@champion")
```

However, the implementation uses:

```python
mlflow.pytorch.load_model("models:/food11@champion")
```

This difference resulted from how the model was logged in Lab 2.

The model was logged using:

```python
mlflow.pytorch.log_model(
    model,
    serialization_format="pickle"
)
```

without an input signature.

Attempts to use the `pyfunc` interface produced errors related to input handling and model serialization, including:

```text
Prediction failed: setting an array element with a sequence.
```

and:

```text
mlflow.exceptions.MlflowException:
If serialization_format is set to 'pt2',
then input_example is required.
```

Another error was:

```text
Unsupported signature type for the selected serialization format.
If the serialization_format argument is set to 'pt2',
the input signature must be specified using TensorSpec.
```

Therefore, the implementation uses the PyTorch flavor directly while still loading the model through the MLflow Registry URI:

```text
models:/food11@champion
```

This preserves the important architectural property of registry-based model loading. The serving application does not depend on a hardcoded `.pth` file.

### Production Fix

A production version could re-log the model with an explicit signature and input example:

```python
mlflow.pytorch.log_model(
    model,
    name="model",
    signature=inferred_signature,
    input_example=example
)
```

The resulting model could then be registered as a new version and assigned to the `champion` alias.

This would allow the serving application to use the `pyfunc` interface specified by the lab.

---

# Summary of Lab 3 Deliverables

## GitHub

The repository contains:

- `Dockerfile`, implementing a multi-stage build
    
- `.dockerignore`, excluding unnecessary and large directories
    
- `src/food11/serve.py`, implementing FastAPI serving and MLflow registry loading
    
- `pyproject.toml` and `uv.lock`, including the serving dependencies
    

Relevant commits include:

```text
1035b80  Containerize model serving with Docker
d2dc705  Serving implementation
```

## MLflow Model Registry

The registered model is:

```text
Name:       food11
Version:    1
Alias:      champion
Run ID:     78fc718cad8d4f7ca3992302d891484e
Run name:   casual-hen-500
Registered: 09/21/2026 05:14:32 PM
```

## Docker

The final image is:

```text
food11-api:latest
```

with a measured size of:

```text
1.67 GB
```

The multi-stage build keeps build-time tooling out of the final runtime image.

Approximately 93% of the image consists of Python dependencies, while the application source itself is only about 18.6 kB.

## End-to-End Verification

The implementation was verified through the following tests:

1. The FastAPI application successfully served predictions locally.
    
2. The Dockerized application produced the same prediction as the local application.
    
3. The container was stopped and recreated from the same image without rebuilding.
    
4. The model was successfully reloaded from MLflow at container startup.
    
5. The prediction remained identical after the restart.
    
6. Running the container without access to the local MLflow artifact path failed.
    
7. Mounting the MLflow artifact directory allowed the container to load the model successfully.
    
8. The multi-stage image was measured at **1.67 GB** compared with **2.55 GB** for the naive single-stage image.
    
9. The multi-stage approach therefore reduced the image size by approximately **880 MB**, or **52%**.
    
10. The `.dockerignore` reduced the Docker build context to approximately **952.3 kB**, compared with approximately **3 GB** of files that would otherwise be sent to the Docker daemon.
    
11. The remaining portability requirements are a container registry, immutable image identification, remote MLflow artifact storage, a network-accessible MLflow server, deployment configuration, and appropriate credentials.