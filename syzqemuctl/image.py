import os
import shutil
import requests
import subprocess
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class ImageInfo:
    """VM image information"""
    name: str
    path: Path
    created_at: float
    running: bool
    is_template: bool = False
    template_ready: bool = False
    pid: Optional[int] = None

class ImageManager:
    # use create-image.sh from a specified commit
    SYZKALLER_SCRIPT_URL = "https://github.com/google/syzkaller/raw/32d786e786e2caf2ba9704bf55562e65b1a4e70c/tools/create-image.sh"
    
    def __init__(self, images_home: str):
        self.images_home = Path(images_home)
        self.template_dir = self.images_home / "image-template"
        
    def _download_create_script(self) -> None:
        """Download create-image.sh script"""
        script_path = self.images_home / "create-image.sh"
        if not script_path.exists():
            # Check proxy settings
            proxies = {}
            if os.environ.get("http_proxy"):
                proxies["http"] = os.environ["http_proxy"]
            if os.environ.get("https_proxy"):
                proxies["https"] = os.environ["https_proxy"]
                
            response = requests.get(self.SYZKALLER_SCRIPT_URL, proxies=proxies)
            response.raise_for_status()
            script_path.write_text(response.text)
            script_path.chmod(0o755)
            print(f"Downloaded create-image.sh to {script_path}")
            
    def initialize(self, force: bool = False) -> None:
        """Initialize image directory"""
        self.images_home.mkdir(parents=True, exist_ok=True)
        self._download_create_script()
        
        if self.is_template_ready() and not force:
            print("Template image already exists, initialization complete")
            return
        
        # Create template directory
        self.template_dir.mkdir(exist_ok=True)
        shutil.copy2(
            self.images_home / "create-image.sh",
            self.template_dir / "create-image.sh"
        )
        
        # Run create-image.sh in background
        print("Starting template image creation, this may take a while...")
        subprocess.Popen(
            ["screen", "-dmS", "template-creation", 
                "bash", "-c", f"cd {self.template_dir} && ./create-image.sh && touch .template_ready"],
            start_new_session=True
        )
            
    def is_template_ready(self) -> bool:
        """Check if template is ready"""
        return (self.template_dir / ".template_ready").exists()
        
    def create(self, name: str) -> bool:
        """Create new image"""
        if not self.is_template_ready():
            print("Template image not ready, please wait...")
            return False
            
        target_dir = self.images_home / name
        if target_dir.exists():
            print(f"Image {name} already exists")
            return False
            
        try:
            print(f"Creating image: {name}")
            subprocess.run(["cp", "-r", str(self.template_dir), str(target_dir)], check=True)
            print(f"Successfully created image: {name}")
            return True
        except Exception as e:
            print(f"Failed to create image: {e}")
            return False
            
    def delete(self, name: str) -> bool:
        """Delete image"""
        target_dir = self.images_home / name
        if not target_dir.exists():
            print(f"Image {name} does not exist")
            return False
            
        try:
            shutil.rmtree(target_dir)
            print(f"Successfully deleted image: {name}")
            return True
        except Exception as e:
            print(f"Failed to delete image: {e}")
            return False
            
    def get_image_info(self, name: str) -> Optional[ImageInfo]:
        """Get image information"""
        path = self.images_home / name
        if not path.exists():
            return None
            
        # Check running status
        pid_file = path / "vm.pid"
        pid = None
        try:
            pid = int(pid_file.read_text().strip())
            running = pid_file.exists() and os.kill(int(pid_file.read_text().strip()), 0) is None
        except (ValueError, ProcessLookupError, OSError):
            running = False
                
        # Check if it's template and its status
        is_template = name == "image-template"
        template_ready = is_template and (path / ".template_ready").exists()
                
        return ImageInfo(
            name=name,
            path=path,
            created_at=path.stat().st_ctime,
            running=running,
            is_template=is_template,
            template_ready=template_ready,
            pid=pid
        )
        
    def list_images(self) -> List[ImageInfo]:
        """List all images, including template"""
        images = []
        template_info = None
        
        # Check if directory exists
        if not self.images_home.exists():
            return []
            
        # Check template image first
        if (template_dir := self.images_home / "image-template").exists():
            if template_info := self.get_image_info("image-template"):
                images.append(template_info)
                
        # Check other images
        for path in self.images_home.iterdir():
            if path.is_dir() and path.name != "image-template":
                if info := self.get_image_info(path.name):
                    images.append(info)
                    
        return sorted(images, key=lambda x: (not x.is_template, x.created_at))