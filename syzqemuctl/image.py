import os
import shutil
import requests
import subprocess
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from . import utils
from . import __title__

@dataclass
class ImageInfo:
    """VM image information"""
    name: str
    path: Path
    created_at: float
    running: bool
    is_template: bool = False
    is_cache: bool = False
    image_ready: bool = False
    pid: Optional[int] = None

class ImageManager:
    # use create-image.sh from a specified commit
    SYZKALLER_SCRIPT_URL = "https://github.com/google/syzkaller/raw/32d786e786e2caf2ba9704bf55562e65b1a4e70c/tools/create-image.sh"
    
    def __init__(self, images_home: str):
        self.images_home = Path(images_home)
        self.template_default_dir = self.images_home / "image-template"

    def _download_create_script(self) -> None:
        """Download create-image.sh script"""
        script_path = self.images_home / "create-image.sh"
        if not script_path.exists():
            if utils.download_file(self.SYZKALLER_SCRIPT_URL, str(script_path), executable=True):
                print(f"Downloaded create-image.sh to {script_path}")

    def initialize(self, force: bool = False, blocking: bool = False, size: int = 3072) -> None:
        """Initialize image directory
        Args:
            force: Force reinitialize even if template exists
            blocking: Wait for template creation to complete
            size: Template disk size in MB (default: 3072)
        """
        self.images_home.mkdir(parents=True, exist_ok=True)
        self._download_create_script()

        if self.is_image_ready("image-template") and not force:
            print("Template image already exists, initialization complete")
            return

        # Create template directory
        self.template_default_dir.mkdir(exist_ok=True)
        shutil.copy2(
            self.images_home / "create-image.sh",
            self.template_default_dir / "create-image.sh"
        )

        # Run create-image.sh (-s size for specified image size)
        print("Starting template image creation, this may take a while...")
        cmd = f"cd {self.template_default_dir} && ./create-image.sh -s {size} && touch .image_ready"

        if blocking:
            print(f"Creating template image: {self.template_default_dir} in blocking mode")
            try:
                subprocess.run(["bash", "-c", cmd], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Failed to create template image: {e}")
                return
        else:
            print(f"Creating template image: {self.template_default_dir} in non-blocking mode")
            subprocess.Popen(
                ["screen", "-dmS", f"{__title__}-template-creation",
                    "bash", "-c", cmd],
                start_new_session=True
            )

    def _copy_core_image_files(self, source: Path, dest: Path) -> bool:
        """Copy core files needed to boot and manage a VM"""
        core_files = ["create-image.sh", "bullseye.img", "bullseye.id_rsa", "bullseye.id_rsa.pub"]
        for name in core_files:
            src = source / name
            if not src.exists():
                print(f"Failed to copy core image files: {name} not found in {source}")
                return False

        try:
            dest.mkdir(parents=True, exist_ok=True)
            for name in core_files:
                shutil.copy2(source / name, dest / name)
            return True
        except Exception as e:
            print(f"Failed to copy core image files: {e}")
            return False

    def _touch_ready(self, path: Path) -> None:
        """Create .image_ready, unlink first if exists to record fresh birth time"""
        ready_file = path / ".image_ready"
        if ready_file.exists():
            ready_file.unlink()
        ready_file.touch()

    def is_image_ready(self, name: str) -> bool:
        """Check if image is ready"""
        path = self.images_home / name
        return (path / ".image_ready").exists() or (path / ".template_ready").exists()

    def create(self, name: str, size: Optional[int] = None, force: bool = False) -> bool:
        """Create new image"""
        template_ready = self.is_image_ready("image-template")
        if size is not None:
            template_ready = template_ready or self.is_image_ready(f"image-template-{size}")
        if not template_ready:
            print(f"Template image not ready, please wait until the creation done. Or run {__title__} init if you have not.")
            return False

        if name.startswith("image-template"):
            print(f"Image name '{name}' is reserved, names starting with 'image-template' are not allowed")
            return False

        target_dir = self.images_home / name
        if target_dir.exists():
            print(f"Image {name} already exists")
            return False

        if size is None:
            # Copy from default template
            try:
                print(f"Creating image: {name}")
                if not self._copy_core_image_files(self.template_default_dir, target_dir):
                    return False
                self._touch_ready(target_dir)
                print(f"Successfully created image: {name}")
                return True
            except Exception as e:
                print(f"Failed to create image: {e}")
                return False
        elif size <= 0:
            print(f"Invalid image size: {size}MB")
            return False
        elif size > 20 * 1024:
            print(f"Image size too large: {size}MB, max 20*1024MB")
            return False
        else:
            template_size_dir = self.images_home / f"image-template-{size}"

            if force:
                # Bypass cache, create from scratch
                target_dir.mkdir(exist_ok=True)
                shutil.copy2(
                    self.images_home / "create-image.sh",
                    target_dir / "create-image.sh"
                )
                print(f"Creating image: {name} with size {size}MB from scratch (cache bypassed)")
                try:
                    subprocess.Popen(
                        ["screen", "-dmS", f"{__title__}-{name}-creation",
                            "bash", "-c", f"cd {target_dir} && ./create-image.sh -s {size} && touch .image_ready"],
                        start_new_session=True
                    )
                except Exception as e:
                    print(f"Failed to create image: {e}")
                    return False
                return True

            if self.is_image_ready(f"image-template-{size}"):
                # Copy from cache
                try:
                    print(f"Creating image: {name} from template cache (size {size}MB)")
                    if not self._copy_core_image_files(template_size_dir, target_dir):
                        return False
                    self._touch_ready(target_dir)
                    print(f"Successfully created image: {name}")
                    return True
                except Exception as e:
                    print(f"Failed to create image: {e}")
                    return False
            elif template_size_dir.exists():
                print(f"Template for size {size} is being created, please wait or use --force to create from scratch")
                return False
            else:
                # Create from scratch and cache
                target_dir.mkdir(exist_ok=True)
                shutil.copy2(
                    self.images_home / "create-image.sh",
                    target_dir / "create-image.sh"
                )

                # Try to atomically create cache directory to prevent concurrent creation
                try:
                    template_size_dir.mkdir(exist_ok=False)
                except FileExistsError:
                    print(f"Template for size {size} is being created, please wait or use --force to create from scratch")
                    return False

                print(f"Creating image: {name} with size {size}MB from scratch")
                cmd = (
                    f"cd {target_dir} && ./create-image.sh -s {size} && "
                    f"touch .image_ready && "
                    f"cp create-image.sh bullseye.img bullseye.id_rsa bullseye.id_rsa.pub {template_size_dir}/ && "
                    f"touch {template_size_dir}/.image_ready"
                )
                try:
                    subprocess.Popen(
                        ["screen", "-dmS", f"{__title__}-{name}-creation",
                            "bash", "-c", cmd],
                        start_new_session=True
                    )
                except Exception as e:
                    print(f"Failed to create image: {e}")
                    return False
                return True
                
            
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
        running = False
        try:
            pid_text = pid_file.read_text().strip()
            pid = int(pid_text)
            os.kill(pid, 0)
            running = True
        except (ValueError, ProcessLookupError, OSError):
            running = False

        # Check if it's template and its status
        is_template = name == "image-template" or name.startswith("image-template-")
        is_cache = name.startswith("image-template-")
        image_ready = (path / ".image_ready").exists()

        return ImageInfo(
            name=name,
            path=path,
            created_at=path.stat().st_ctime,
            running=running,
            is_template=is_template,
            is_cache=is_cache,
            image_ready=image_ready,
            pid=pid
        )

    def list_images(self) -> List[ImageInfo]:
        """List all images, including template and cache templates"""
        if not self.images_home.exists():
            return []

        images = []
        for path in self.images_home.iterdir():
            if path.is_dir() and not path.name.startswith("."):
                if info := self.get_image_info(path.name):
                    images.append(info)

        # Sort: main template first, then cache templates by name, then user images by creation time
        return sorted(images, key=lambda x: (
            0 if x.name == "image-template" else (1 if x.is_cache else 2),
            x.name if x.is_template else x.created_at
        ))
