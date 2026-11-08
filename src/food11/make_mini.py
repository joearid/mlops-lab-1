import hashlib
import shutil
from pathlib import Path

from PIL import Image

src = Path("data/food11_raw")
dst = Path("data/food11_processed_mini")
splits = {"training": 100, "validation": 30, "evaluation": 30}

classes = [
    "Bread", "Dairy product", "Dessert", "Egg", "Fried food", "Meat",
    "Noodles-Pasta", "Rice", "Seafood", "Soup", "Vegetable-Fruit"
]
class_map = {str(i): cls for i, cls in enumerate(classes)}

if dst.exists():
    shutil.rmtree(dst)

seen_hashes = set()

print("Creating properly resized mini dataset (deduplicated)...")
for split, n in splits.items():
    for cls_dir in sorted((src / split).iterdir()):
        if not cls_dir.is_dir():
            continue
        
        new_folder_name = class_map.get(cls_dir.name, cls_dir.name)
        out_dir = dst / split / new_folder_name
        out_dir.mkdir(parents=True, exist_ok=True)
        
        count = 0
        for img_path in sorted(cls_dir.glob("*.jpg")):
            if count >= n:
                break
            try:
                # Check for duplicates before processing
                file_hash = hashlib.md5(img_path.read_bytes()).hexdigest()
                if file_hash in seen_hashes:
                    continue
                
                with Image.open(img_path) as img:
                    img_resized = img.convert("RGB").resize((128, 128))
                    img_resized.save(out_dir / img_path.name)
                
                seen_hashes.add(file_hash)
                count += 1
            except Exception as e:
                print(f"Failed to process {img_path}: {e}")
    print(f"Created {split}")