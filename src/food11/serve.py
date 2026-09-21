"""FastAPI serving app for the Food-11 model.

Loads the registered model `food11@champion` from the MLflow Model Registry
and exposes /health and /predict endpoints.

Run locally:
    uv run uvicorn src.food11.serve:app --host 0.0.0.0 --port 8000
"""

import io
import os

import mlflow.pytorch
import numpy as np
import torch
from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000")
MODEL_URI = "models:/food11@champion"

# Class order must match ImageFolder's alphabetical sort of folders
# 0 -> "0" -> Bread, 1 -> "1" -> Dairy product, 2 -> "10" -> Vegetable-Fruit, ...
CLASSES = [
    "Bread",            # folder "0"
    "Dairy product",    # folder "1"
    "Vegetable-Fruit",  # folder "10"
    "Dessert",          # folder "2"
    "Egg",              # folder "3"
    "Fried food",       # folder "4"
    "Meat",             # folder "5"
    "Noodles-Pasta",    # folder "6"
    "Rice",             # folder "7"
    "Seafood",          # folder "8"
    "Soup",             # folder "9"
]

IMG_SIZE = 128
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


# ---------------------------------------------------------------------------
# App + model loading at startup
# ---------------------------------------------------------------------------
app = FastAPI(title="Food-11 API", version="1.0")

_model = None


def _load_model():
    """Load the champion model once at startup."""
    global _model
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    print(f"Loading model from {MODEL_URI} (tracking uri: {MLFLOW_TRACKING_URI})")
    _model = mlflow.pytorch.load_model(MODEL_URI, map_location="cpu")
    _model.eval()
    print("Model loaded successfully.")


@app.on_event("startup")
def startup_event():
    _load_model()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


def _preprocess(image_bytes: bytes) -> torch.Tensor:
    """Turn raw bytes into a normalized NCHW float32 tensor (batch size 1)."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = img.resize((IMG_SIZE, IMG_SIZE))
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = (arr - IMAGENET_MEAN) / IMAGENET_STD
    arr = np.transpose(arr, (2, 0, 1))  # HWC -> CHW
    return torch.from_numpy(arr[np.newaxis, ...]).float()  # (1, 3, 128, 128)


@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet.")

    try:
        contents = await file.read()
        x = _preprocess(contents)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {e}")

    try:
        with torch.no_grad():
            logits = _model(x)
        logits = logits.numpy().reshape(-1)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")

    if logits.shape[0] != len(CLASSES):
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected output shape: {logits.shape}",
        )

    # Softmax for confidence
    exp = np.exp(logits - logits.max())
    probs = exp / exp.sum()

    idx = int(np.argmax(probs))
    return {
        "predicted_class": CLASSES[idx],
        "confidence": float(probs[idx]),
        "all_probabilities": {c: float(p) for c, p in zip(CLASSES, probs)},
    }
