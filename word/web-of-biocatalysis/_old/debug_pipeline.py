#!/usr/bin/env python3
"""
Debug version to see what's really happening
"""

import sys
from pathlib import Path
import pandas as pd

# Add the parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

def debug_files():
    """Debug function to check all files and paths"""
    
    print("🔍 DEBUG: Checking file locations and contents...")
    
    # Check current directory
    current_dir = Path.cwd()
    print(f"Current directory: {current_dir}")
    
    # Check for config file
    config_paths = [
        current_dir / "config.yaml",
        current_dir.parent / "config.yaml",
        current_dir / "pipeline" / "config.yaml"
    ]
    
    print("\n📁 Config file search:")
    for path in config_paths:
        exists = "✅" if path.exists() else "❌"
        print(f"  {exists} {path}")
        if path.exists():
            print(f"      Found config at: {path}")
            try:
                with open(path, 'r') as f:
                    content = f.read()
                    print(f"      Config content preview: {content[:200]}...")
                    if 'base_dir' in content:
                        lines = content.split('\n')
                        for line in lines:
                            if 'base_dir' in line:
                                print(f"      Base dir setting: {line.strip()}")
            except Exception as e:
                print(f"      Error reading config: {e}")
    
    # Check seed files
    print("\n📊 Seed files:")
    
    # Curated seeds
    curated_path = current_dir / "curated" / "curated_seeds.csv"
    print(f"Curated seeds: {curated_path}")
    if curated_path.exists():
        df = pd.read_csv(curated_path)
        print(f"  ✅ Found {len(df)} curated papers")
        print(f"  Columns: {list(df.columns)}")
        print(f"  Sample data:\n{df.head()}")
    else:
        print(f"  ❌ Not found")
    
    # Auto seeds  
    auto_path = current_dir / "core_output" / "combined_pillar_assignments.csv"
    print(f"\nAuto seeds: {auto_path}")
    if auto_path.exists():
        df = pd.read_csv(auto_path)
        print(f"  ✅ Found {len(df)} auto papers")
        print(f"  Columns: {list(df.columns)}")
        print(f"  DOIs: {list(df['doi'])}")
    else:
        print(f"  ❌ Not found")
    
    # Check library directory
    print("\n📚 Library directory:")
    library_paths = [
        current_dir / "library",
        current_dir.parent / "library",
        current_dir / "data" / "library"
    ]
    
    for lib_path in library_paths:
        print(f"Checking: {lib_path}")
        if lib_path.exists():
            files = list(lib_path.iterdir())
            print(f"  ✅ Found library with {len(files)} items")
            if files:
                print(f"  Contents: {[f.name for f in files[:5]]}")
        else:
            print(f"  ❌ Not found")
    
    # Check if we can import the modules
    print("\n🔧 Module imports:")
    try:
        from pipeline.config import load_config
        print("  ✅ pipeline.config imported")
    except Exception as e:
        print(f"  ❌ pipeline.config failed: {e}")
        
    try:
        from pipeline.storage import Store
        print("  ✅ pipeline.storage imported")
    except Exception as e:
        print(f"  ❌ pipeline.storage failed: {e}")
    
    # Try to create a Store object
    print("\n🗃️  Storage test:")
    try:
        # Try to load config first
        config_path = None
        for path in config_paths:
            if path.exists():
                config_path = path
                break
        
        if config_path:
            from pipeline.config import load_config
            cfg = load_config(config_path)
            print(f"  ✅ Config loaded from {config_path}")
            print(f"  Base dir in config: {cfg.get('base_dir', 'NOT FOUND')}")
            
            from pipeline.storage import Store
            store = Store(Path(cfg["base_dir"]))
            print(f"  ✅ Store created: {store.base}")
            
            # Check if base directory exists
            if store.base.exists():
                print(f"  ✅ Store base directory exists")
                print(f"  Contents: {list(store.base.iterdir())}")
            else:
                print(f"  ❌ Store base directory doesn't exist: {store.base}")
                
        else:
            print("  ❌ No config file found")
            
    except Exception as e:
        print(f"  ❌ Storage test failed: {e}")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    debug_files()
