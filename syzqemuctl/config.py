import os
import json
from pathlib import Path
from typing import Optional, Dict

from . import __title__

class GlobalConfig:
    """Global configuration management"""
    DEFAULT_CONFIG_DIR = os.path.expanduser(f"~/.config/{__title__}")
    DEFAULT_CONFIG_FILE = "settings.json"
    DEFAULT_CACHE_DIR = os.path.expanduser(f"~/.cache/{__title__}")
    
    def __init__(self):
        self.config_dir = Path(self.DEFAULT_CONFIG_DIR)
        self.config_file = self.config_dir / self.DEFAULT_CONFIG_FILE
        self._settings: Dict = {}
        os.makedirs(self.DEFAULT_CONFIG_DIR, exist_ok=True)
        os.makedirs(self.DEFAULT_CACHE_DIR, exist_ok=True)
        
    def initialize(self, images_home: str, **kwargs) -> None:
        """Initialize configuration"""
        
        self._settings = {
            "images_home": str(Path(images_home).absolute()),
            **kwargs
        }
        
        with self.config_file.open("w") as f:
            json.dump(self._settings, f, indent=2)
            
    def load(self) -> bool:
        """Load configuration file"""
        try:
            if not self.config_file.exists():
                return False
                
            with self.config_file.open() as f:
                self._settings = json.load(f)
            return True
        except Exception as e:
            print(f"Failed to load config: {e}")
            return False
            
    @property
    def images_home(self) -> Optional[str]:
        """Get images home directory path"""
        return self._settings.get("images_home")
        
    def is_initialized(self) -> bool:
        """Check if initialized"""
        return self.config_file.exists()

# Global configuration instance
global_conf = GlobalConfig() 