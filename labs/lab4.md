# Lab 4 - Orchestrating the app with Docker Compose

**Student:** joearid
**Repository:** [https://github.com/joearid/mlops-lab-1](https://github.com/joearid/mlops-lab-1)
**Tracking server (inside Compose):** `http://mlflow:5000`
**Frontend:** `http://127.0.0.1:8501`
**MLflow UI:** `http://127.0.0.1:5000`



## Question 1: What happens to `/mlflow-data` if you never mount a volume?

**Test performed:** Built the `mlflow` image, ran it standalone **without** a volume on port 5001, created a `test-ephemeral` experiment, destroyed the container, and restarted a new container from the same image.

### Evidence: Standalone container data loss

**First run (fresh container):**
```text
$ mlflow.create_experiment('test-ephemeral')
created test-ephemeral

Experiments visible:
  - test-ephemeral (id=1)
  - Default (id=0)
```

**After `docker rm -f mlflow-test` + `docker run` from the same image:**
```text
Experiments visible:
  - Default (id=0)
```

### Deep Dive: OverlayFS and Copy-on-Write (CoW)
A Docker container's filesystem is not a single disk. It is a union mount (using the Linux `overlay2` storage driver) consisting of read-only image layers (`lowerdir`) and a single ephemeral writable layer (`upperdir`). When MLflow writes its SQLite database (`mlflow.db`) and artifacts (`mlruns/`) to `/mlflow-data`, the Linux kernel uses **Copy-on-Write (CoW)** to copy those files into the `upperdir`. 

When the container is removed via `docker rm`, the Docker daemon deletes the `upperdir` on the host (`/var/lib/docker/overlay2/<id>/diff`). The image layers remain intact, but all state is lost. The new container boots with a fresh, empty `upperdir`, forcing MLflow to initialize an empty database.



## Question 2: Why a named volume instead of a bind mount?

While a bind mount would technically persist the data, a named volume is preferred for several architectural reasons:

### Deep Dive: VFS, DAC, and UID Mapping
*   **The Bind Mount Problem:** A bind mount (`./mlflow-data:/mlflow-data`) uses the Linux `mount --bind` syscall. It maps a host directory directly into the container. Linux permissions are based on numeric UIDs (Discretionary Access Control). In our setup, the `mlflow` container ran as `root` (UID 0) and owned the volume, but the training script ran as `appuser` (UID 1000). Writing to a root-owned bind mount as UID 1000 triggered a kernel `EACCES` (Permission Denied).
*   **The Named Volume Solution:** Named volumes live in `/var/lib/docker/volumes/`. Docker manages the permissions and seeds the directory from the image's metadata. Furthermore, named volumes are portable across host operating systems (Linux, Mac, Windows), whereas bind mounts depend on host-specific file paths. Finally, MLflow stores absolute file paths in its database; a bind mount ties these paths to a specific host directory, which breaks if the folder is renamed.

---

## Question 3: Why does `http://mlflow:5000` resolve now?

In Lab 3, the inference container used `host.docker.internal` or `--network host` to reach the host's MLflow server. In Lab 4, Docker Compose automatically creates a private, user-defined bridge network (`semestre1uni_default`).

### Evidence: Service name resolution in Compose

```text
Loading model from models:/food11@champion (tracking uri: http://mlflow:5000)
Model loaded successfully.
```

### Deep Dive: Network Namespaces and Embedded DNS
Every container operates in its own Linux network namespace, with its own loopback (`lo`) and ethernet (`eth0`) interfaces. They are connected to a virtual bridge on the host via `veth` pairs. 
Unlike the legacy `docker0` bridge, user-defined bridges include an **embedded DNS resolver** running at `127.0.0.11` inside every container. When `serve.py` attempts to resolve `mlflow`, the kernel queries `127.0.0.11`. The Docker daemon intercepts this UDP query and returns the internal IP of the `mlflow` container (e.g., `172.19.0.2`), allowing direct container-to-container HTTP traffic without exposing ports to the host.



## Question 4: Why does the frontend read `INFERENCE_URL` from an environment variable?

Hardcoding `http://inference:8000` would make the frontend image entirely dependent on Docker Compose. If you ran the frontend standalone (`docker run frontend:latest`), there is no Compose network and the `inference` DNS entry does not exist.

### Deep Dive: `execve` and The Twelve-Factor App
When Docker starts a container, it calls `execve()` in the kernel, passing an environment array (`envp`). Python reads this from `/proc/self/environ` into `os.environ`. By using `os.environ.get("INFERENCE_URL", "http://127.0.0.1:8000")`, the application adheres to Factor III of the *Twelve-Factor App*: **Store config in the environment**. 
This keeps the immutable image portable across environments (Compose uses `http://inference:8000`, local dev falls back to `127.0.0.1:8000`, and Kubernetes could inject a cluster URL).



## Question 5: Why doesn't `inference` publish a port? How does the frontend reach it?

A published port binds a container to the host machine. The `inference` service is only called by the `frontend` service on the internal network.

### Evidence: `docker compose ps` showing internal vs published ports

```text
NAME                       SERVICE     PORTS
semestre1uni-frontend-1    frontend    0.0.0.0:8501->8501/tcp
semestre1uni-inference-1   inference   8000/tcp
semestre1uni-mlflow-1      mlflow      0.0.0.0:5000->5000/tcp
```
Notice `inference` has `8000/tcp` (no `->`), meaning it is exposed to the Docker network but not published to the host.

### Deep Dive: `iptables` and Attack Surface
Declaring `ports: - "8501:8501"` causes the Docker daemon to inject `iptables` rules on the host (specifically `DNAT` rules in the `nat` table), routing external host traffic to the container. `inference` has no published port, meaning no `iptables` rules are created. It is entirely unreachable from outside the bridge network. This minimizes the attack surface, only the human-facing UIs (MLflow and Streamlit) are exposed to the host browser.



## Question 6: What happens if `depends_on` starts `inference` before `mlflow` is ready?

`depends_on` only guarantees start order (the `mlflow` container process is created before the `inference` container). It does **not** wait for the application inside to accept connections.

### Evidence: Startup failure due to unready MLflow

When the `inference` container started while MLflow was still initializing its database, it crashed:
```text
ConnectionRefusedError: [Errno 111] Connection refused
...
mlflow.exceptions.MlflowException: API request to http://127.0.0.1:5000/api/2.0/mlflow/experiments/get-by-name failed
```

### Deep Dive: TCP Handshake Race Condition
When `inference` starts, it immediately sends a TCP `SYN` packet to `mlflow:5000`. If MLflow's Uvicorn process hasn't reached the `socket() -> bind() -> listen()` sequence yet, the Linux kernel on the bridge sees a packet for a closed port and replies with a TCP `RST` (Reset) packet. Python's `requests` library translates this to `ConnectionRefusedError`. 
To fix this in production, you must use a `healthcheck` in the `mlflow` service and declare `depends_on: mlflow: condition: service_healthy`, or implement retry logic in `serve.py`.



## Question 7: Which services have a published port listed?

- **mlflow**: publishes `5000` (for the UI).
- **frontend**: publishes `8501` (for the Streamlit UI).
- **inference**: does not publish a port (`8000/tcp` internal only).

This exactly matches the `docker-compose.yml` configuration, where only `mlflow` and `frontend` have a `ports:` block.



## Question 8: Does the prediction come from the new model version or the old one? 

Before a restart, `serve.py` holds the old model in memory (loaded once at startup). The prediction comes from the old version. To pick up the new version without rebuilding the image, run:

```bash
docker compose restart inference
```

### Evidence: Registering v2 and moving the alias

```text
$ (python snippet registering v2 and moving alias)
New version: 2
champion -> 2
```
After `docker compose restart inference`, the logs show:
```text
Loading model from models:/food11@champion (tracking uri: http://mlflow:5000)
Model loaded successfully.
```
The inference service now serves version 2.



## Question 9: Why does `restart` alone work? What is baked into the image versus fetched?

**Baked into the image:** Python runtime, system libraries, PyTorch, MLflow, FastAPI, and the application code (`serve.py`).
**Fetched at runtime:** The `.pkl` model weights and metadata from the MLflow Registry.

### Deep Dive: Immutable Infrastructure vs. Dynamic State
Docker images are immutable. `docker compose restart` sends a `SIGTERM` to the container, destroying it and creating a new one from the exact same read-only image layers. During the new container's startup, `serve.py` queries the MLflow REST API (`/api/2.0/mlflow/registered-models/alias`). Because the alias was moved to v2, MLflow returns the v2 artifact URI, and the container downloads the new `.pkl` via HTTP into RAM. 
A rebuild (`docker compose build`) is only needed if code or dependencies change. 



## Question 10: Persistence across `down`/`up` vs `down -v`/`up`

### Evidence: `down` / `up` (volume kept)
```text
$ docker compose down
$ docker compose up -d
$ docker compose exec mlflow python -c "..." 
champion -> 2
```
The database and artifacts survived because `docker compose down` only removes containers and networks. The named volume (`semestre1uni_mlflow-data`) remains in Docker's internal graph database.

### Evidence: `down -v` / `up` (volume wiped)
```text
$ docker compose down -v
  Volume semestre1uni_mlflow-data     Removed
$ docker compose up -d
$ docker compose exec mlflow python -c "..." 
NOT FOUND: RestException
```
### Deep Dive: Graph Database and Filesystem Deletion
Docker stores volume metadata in an internal database (BoltDB). `down -v` tells the daemon to delete the volume object from this database, and explicitly calls `os.RemoveAll()` on the host directory (`/var/lib/docker/volumes/<name>/_data`). The SQLite database (`mlflow.db`) and all model artifacts are permanently destroyed at the filesystem level. The next `up` creates a fresh, empty volume.



## Question 11: What would have to change for three replicas or surviving a machine failure?

Docker Compose is a single-node orchestrator. It cannot provide:
1. **High Availability:** Compose lacks a scheduler and consensus algorithm (like Raft). If the host dies, the stack dies.
2. **Load Balancing:** Scaling to 3 replicas with `--scale inference=3` fails because publishing a host port (`8000:8000`) causes a kernel `EADDRINUSE` (Address already in use) when binding to the same port three times. You would need an Nginx/Traefik reverse proxy to load balance traffic.
3. **Rolling Updates:** Compose stops and recreates containers sequentially, causing downtime. Kubernetes provides zero-downtime rolling updates via readiness probes.
4. **Stateful HA for MLflow:** SQLite relies on file-level locks (`fcntl`) and cannot be safely shared across multiple nodes. Production MLflow requires a multi-writer backend (Postgres/MySQL) and object storage (S3/GCS).



## Implementation Notes & Troubleshooting

During the execution of this lab, several MLflow 3.x and Docker networking nuances were encountered and resolved:

### 1. MLflow 3.x Security Middleware (DNS Rebinding)
**Error:** `403 Invalid Host header`
MLflow 3.x added a FastAPI middleware that checks the HTTP `Host` header to prevent DNS rebinding attacks. When `inference` connected to `http://mlflow:5000`, the host header was rejected. 
**Fix:** Added `--allowed-hosts "mlflow:5000,localhost:5000,127.0.0.1:5000"` to the `mlflow server` command in the Dockerfile.

### 2. MLflow Artifact Serving (HTTP Proxying)
**Error:** `MlflowException: No such artifact: ''` or `PermissionError: [Errno 13] Permission denied`
By default, MLflow returns local file paths (`file:///mlflow-data/...`) to clients, which fails if the client doesn't have the volume mounted. 
**Fix:** Added `--serve-artifacts` and `--artifacts-destination /mlflow-data/mlruns`. This forces the MLflow server to act as an HTTP reverse proxy for artifacts. The inference container now downloads the model via `mlflow-artifacts:/...` HTTP streaming, mimicking production S3/GCS behavior.

### 3. Training Permissions
**Error:** `PermissionError: [Errno 13] Permission denied: '/mlflow-data'`
The MLflow volume is owned by `root` (UID 0), but the `train` service's Dockerfile drops privileges to `appuser` (UID 1000). 
**Fix:** We ran the training service with `--user root` to bypass the DAC restrictions and write to the root-owned volume.

### 4. Training URI Patching
The original `train.py` hardcoded `mlflow.set_tracking_uri("http://127.0.0.1:5000")`. 
**Fix:** Patched to `os.environ.get("MLFLOW_TRACKING_URI", ...)` so it dynamically connects to `http://mlflow:5000` via Compose's embedded DNS.


