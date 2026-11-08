from pathlib import Path

from PIL import Image

CLASSES = [
    "Bread", "Dairy product", "Dessert", "Egg", "Fried food", "Meat",
    "Noodles-Pasta", "Rice", "Seafood", "Soup", "Vegetable-Fruit"
]

# Mapping from the Kaggle folder names (0-10) to the human-readable classes
# 0: Bread, 1: Dairy, 2: Dessert, 3: Egg, 4: Fried, 5: Meat,
# 6: Noodles, 7: Rice, 8: Seafood, 9: Soup, 10: Vegetable-Fruit
CLASS_MAP = {str(i): cls for i, cls in enumerate(CLASSES)}

def category_from_filename(filename: str) -> str:
    """'3_120.jpg' -> 'Egg'"""
    prefix = Path(filename).stem.split("_")[0]
    return CLASS_MAP.get(prefix, "Unknown")

def resize_image(img: Image.Image, size: int = 128) -> Image.Image:
    """Returns an RGB image of size x size."""
    return img.convert("RGB").resize((size, size))

if __name__ == "__main__":
    # The copy logic from Lab 1 could go here, but we already did it via bash.
    pass