from pathlib import Path
import yaml

def load_config(path: Path):
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # normalize
    cfg["base_dir"] = str(Path(cfg["base_dir"]).expanduser())
    return cfg
