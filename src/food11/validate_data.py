import argparse
import hashlib
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image

from food11.data import CLASSES

def check_splits(dataset_dir: Path) -> bool:
    print("1. Checking split folders...")
    ok = True
    for split in ["training", "validation", "evaluation"]:
        split_dir = dataset_dir / split
        if not split_dir.is_dir():
            print(f"  FAIL: Missing split folder {split}")
            ok = False
            continue
        folders = {p.name for p in split_dir.iterdir() if p.is_dir()}
        if folders != set(CLASSES):
            print(f"  FAIL: {split} has incorrect class folders. Missing: {set(CLASSES) - folders}, Extra: {folders - set(CLASSES)}")
            ok = False
    if ok:
        print("  PASS: All splits have exactly the 11 classes.")
    return ok

def check_images_and_hashes(dataset_dir: Path):
    print("2. Checking image properties and 4. Checking for duplicates...")
    img_ok = True
    hash_ok = True
    hashes = {} # hash -> (split, class, filename)
    
    for split in ["training", "validation", "evaluation"]:
        split_dir = dataset_dir / split
        if not split_dir.is_dir():
            continue
        for cls_dir in split_dir.iterdir():
            if not cls_dir.is_dir() or cls_dir.name not in CLASSES:
                continue
            for img_path in cls_dir.glob("*.jpg"):
                # Check image
                try:
                    with Image.open(img_path) as img:
                        if img.size != (128, 128):
                            print(f"  FAIL: {img_path} is {img.size}, expected (128, 128)")
                            img_ok = False
                        if img.mode != "RGB":
                            print(f"  FAIL: {img_path} mode is {img.mode}, expected RGB")
                            img_ok = False
                except Exception as e:
                    print(f"  FAIL: {img_path} could not be opened: {e}")
                    img_ok = False
                
                # Check hash
                h = hashlib.md5(img_path.read_bytes()).hexdigest()
                if h in hashes:
                    prev_split, prev_cls, prev_name = hashes[h]
                    if prev_split != split:
                        print(f"  FAIL: Duplicate image across splits: {img_path} matches {prev_split}/{prev_cls}/{prev_name}")
                        hash_ok = False
                else:
                    hashes[h] = (split, cls_dir.name, img_path.name)
                    
    if img_ok:
        print("  PASS: All images are RGB 128x128.")
    if hash_ok:
        print("  PASS: No duplicate images across splits.")
    return img_ok, hash_ok

def check_counts_and_distribution(dataset_dir: Path, min_per_class: int, tau: float):
    print(f"3. Checking min {min_per_class} images per class...")
    print(f"5. Checking distribution variance (tau={tau})...")
    
    counts = defaultdict(lambda: defaultdict(int))
    for split in ["training", "validation", "evaluation"]:
        split_dir = dataset_dir / split
        if not split_dir.is_dir():
            continue
        for cls_dir in split_dir.iterdir():
            if cls_dir.is_dir() and cls_dir.name in CLASSES:
                counts[split][cls_dir.name] = len(list(cls_dir.glob("*.jpg")))

    count_ok = True
    for split in ["training", "validation", "evaluation"]:
        for cls in CLASSES:
            if counts[split][cls] < min_per_class:
                print(f"  FAIL: {split}/{cls} has only {counts[split][cls]} images (< {min_per_class})")
                count_ok = False
    if count_ok:
        print("  PASS: All classes meet the minimum image count.")

    dist_ok = True
    train_total = sum(counts["training"].values())
    val_total = sum(counts["validation"].values())
    
    if train_total > 0 and val_total > 0:
        for cls in CLASSES:
            train_share = counts["training"][cls] / train_total
            val_share = counts["validation"][cls] / val_total
            if abs(train_share - val_share) > tau:
                print(f"  FAIL: {cls} distribution differs by {abs(train_share - val_share):.3f} (train: {train_share:.3f}, val: {val_share:.3f})")
                dist_ok = False
    if dist_ok:
        print("  PASS: Train and validation distributions are within tau.")
    
    return count_ok, dist_ok

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("--min-per-class", type=int, default=50)
    parser.add_argument("--tau", type=float, default=0.05)
    args = parser.parse_args()

    if not args.dataset_dir.is_dir():
        print(f"Error: {args.dataset_dir} is not a directory.")
        sys.exit(1)

    print(f"Validating dataset: {args.dataset_dir}\n")
    
    splits_ok = check_splits(args.dataset_dir)
    img_ok, hash_ok = check_images_and_hashes(args.dataset_dir)
    count_ok, dist_ok = check_counts_and_distribution(args.dataset_dir, args.min_per_class, args.tau)
    
    print("\n" + "="*40)
    if all([splits_ok, img_ok, hash_ok, count_ok, dist_ok]):
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")
        sys.exit(1)

if __name__ == "__main__":
    main()