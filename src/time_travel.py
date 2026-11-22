"""Read a pinned snapshot manifest, the local analogue of Iceberg time travel."""
import json, argparse, pathlib
ap=argparse.ArgumentParser(); ap.add_argument("--snapshot",default="latest"); a=ap.parse_args()
print(json.loads(pathlib.Path("data/curated/snapshot.json").read_text()))
