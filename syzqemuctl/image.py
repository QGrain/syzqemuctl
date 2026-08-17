import shutil
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
    
    def __init__(self, images_home: str, verbose: bool = False):
        self.images_home = Path(images_home).expanduser().resolve()
        self.template_default_dir = self.images_home / "image-template"
        self.verbose = verbose

    def _image_path(self, name: str) -> Optional[Path]:
        """Resolve a single image name without allowing path traversal"""
        if not name or Path(name).name != name:
            return None
        candidate = self.images_home / name
        if candidate.is_symlink():
            return None
        path = candidate.resolve()
        return path if path.parent == self.images_home else None

    def _download_create_script(self) -> bool:
        """Download create-image.sh script"""
        script_path = self.images_home / "create-image.sh"
        if script_path.exists():
            return True
        if utils.download_file(
            self.SYZKALLER_SCRIPT_URL,
            str(script_path),
            executable=True,
        ):
            utils.log_info(f"Downloaded create-image.sh to {script_path}", self.verbose)
            return True
        return False

    def initialize(self, force: bool = False, blocking: bool = False, size: int = 3072) -> bool:
        """Initialize image directory
        Args:
            force: Force reinitialize even if template exists
            blocking: Wait for template creation to complete
            size: Template disk size in MB (default: 3072)
        """
        if size <= 0:
            print(f"Invalid image size: {size}MB")
            return False

        self.images_home.mkdir(parents=True, exist_ok=True)
        if not self._download_create_script():
            return False

        if self.template_default_dir.is_symlink():
            print("Template image directory must not be a symbolic link")
            return False

        if self.is_image_ready("image-template") and not force:
            utils.log_info("Template image already exists, initialization complete", self.verbose)
            return True

        # Create template directory
        self.template_default_dir.mkdir(exist_ok=True)
        shutil.copy2(
            self.images_home / "create-image.sh",
            self.template_default_dir / "create-image.sh"
        )

        # Run create-image.sh (-s size for specified image size)
        utils.log_info("Starting template image creation, this may take a while...", self.verbose)
        if blocking:
            utils.log_info(f"Creating template image: {self.template_default_dir} in blocking mode", self.verbose)
            try:
                subprocess.run(
                    ["./create-image.sh", "-s", str(size)],
                    cwd=str(self.template_default_dir),
                    check=True,
                )
                self._touch_ready(self.template_default_dir)
                return True
            except subprocess.CalledProcessError as e:
                print(f"Failed to create template image: {e}")
                return False
        else:
            utils.log_info(f"Creating template image: {self.template_default_dir} in non-blocking mode", self.verbose)
            try:
                subprocess.Popen(
                    ["screen", "-dmS", utils.make_screen_name(
                        self.template_default_dir, "creation"
                    ), "bash", "-c",
                        'cd "$1" && ./create-image.sh -s "$2" && touch .image_ready',
                        __title__, str(self.template_default_dir), str(size)],
                    start_new_session=True
                )
                return True
            except OSError as e:
                print(f"Failed to start template image creation: {e}")
                return False

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
        path = self._image_path(name)
        if path is None:
            return False
        return (path / ".image_ready").exists() or (path / ".template_ready").exists()

    def create(self, name: str, size: Optional[int] = None, force: bool = False) -> bool:
        """Create new image"""
        target_dir = self._image_path(name)
        if target_dir is None:
            print(f"Invalid image name: {name}")
            return False

        template_ready = self.is_image_ready("image-template")
        if size is not None:
            template_ready = template_ready or self.is_image_ready(f"image-template-{size}")
        if not template_ready:
            print(f"Template image not ready, please wait until the creation done. Or run {__title__} init if you have not.")
            return False

        if name.startswith("image-template"):
            print(f"Image name '{name}' is reserved, names starting with 'image-template' are not allowed")
            return False

        if target_dir.exists():
            print(f"Image {name} already exists")
            return False

        if size is None:
            # Copy from default template
            try:
                utils.log_info(f"Creating image: {name}", self.verbose)
                if not self._copy_core_image_files(self.template_default_dir, target_dir):
                    return False
                self._touch_ready(target_dir)
                utils.log_info(f"Successfully created image: {name}", self.verbose)
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
            template_size_dir = self._image_path(f"image-template-{size}")
            if template_size_dir is None:
                print("Template cache directory must not be a symbolic link")
                return False

            if force:
                # Bypass cache, create from scratch
                target_dir.mkdir(exist_ok=True)
                shutil.copy2(
                    self.images_home / "create-image.sh",
                    target_dir / "create-image.sh"
                )
                utils.log_info(f"Creating image: {name} with size {size}MB from scratch (cache bypassed)", self.verbose)
                try:
                    subprocess.Popen(
                        ["screen", "-dmS", utils.make_screen_name(
                            target_dir, "creation"
                        ),
                            "bash", "-c",
                            'cd "$1" && ./create-image.sh -s "$2" && touch .image_ready',
                            __title__, str(target_dir), str(size)],
                        start_new_session=True
                    )
                except Exception as e:
                    print(f"Failed to create image: {e}")
                    return False
                return True

            if self.is_image_ready(f"image-template-{size}"):
                # Copy from cache
                try:
                    utils.log_info(f"Creating image: {name} from template cache (size {size}MB)", self.verbose)
                    if not self._copy_core_image_files(template_size_dir, target_dir):
                        return False
                    self._touch_ready(target_dir)
                    utils.log_info(f"Successfully created image: {name}", self.verbose)
                    return True
                except Exception as e:
                    print(f"Failed to create image: {e}")
                    return False
            elif template_size_dir.exists():
                utils.log_info(f"Template for size {size} is being created, please wait or use --force to create from scratch", self.verbose)
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
                    utils.log_info(f"Template for size {size} is being created, please wait or use --force to create from scratch", self.verbose)
                    return False

                utils.log_info(f"Creating image: {name} with size {size}MB from scratch", self.verbose)
                try:
                    subprocess.Popen(
                        ["screen", "-dmS", utils.make_screen_name(
                            target_dir, "creation"
                        ),
                            "bash", "-c",
                            'cd "$1" && ./create-image.sh -s "$2" && '
                            'touch .image_ready && '
                            'cp create-image.sh bullseye.img bullseye.id_rsa '
                            'bullseye.id_rsa.pub "$3"/ && '
                            'touch "$3"/.image_ready',
                            __title__, str(target_dir), str(size),
                            str(template_size_dir)],
                        start_new_session=True
                    )
                except Exception as e:
                    print(f"Failed to create image: {e}")
                    return False
                return True
                
            
    def delete(self, name: str) -> bool:
        """Delete image"""
        target_dir = self._image_path(name)
        if target_dir is None:
            print(f"Invalid image name: {name}")
            return False
        if not target_dir.exists():
            print(f"Image {name} does not exist")
            return False

        from .vm import VM
        with utils.image_operation_lock(target_dir):
            vm = VM(str(target_dir))
            runtime_screens = vm._screen_session_ids()
            if runtime_screens is None:
                print(f"Unable to verify runtime state for image {name}")
                return False
            if vm.is_running() or runtime_screens:
                print(f"Image {name} is running; stop it before deleting")
                return False

            creation_screen = utils.make_screen_name(target_dir, "creation")
            legacy_creation_screen = (
                f"{__title__}-template-creation"
                if name == "image-template"
                else f"{__title__}-{name}-creation"
            )
            creation_states = [utils.check_screen_exists(creation_screen)]
            if legacy_creation_screen != creation_screen:
                creation_states.append(
                    utils.check_screen_exists(legacy_creation_screen)
                )
            if any(state is None for state in creation_states):
                print(f"Unable to verify creation state for image {name}")
                return False
            if any(creation_states):
                print(f"Image {name} is still being created")
                return False

            try:
                shutil.rmtree(target_dir)
                utils.log_info(f"Successfully deleted image: {name}", self.verbose)
                return True
            except Exception as e:
                print(f"Failed to delete image: {e}")
                return False
            
    def get_image_info(self, name: str) -> Optional[ImageInfo]:
        """Get image information"""
        path = self._image_path(name)
        if path is None or not path.exists():
            return None

        # Check running status
        from .vm import VM

        vm = VM(str(path))
        pid_file = path / "vm.pid"
        try:
            pid = int(pid_file.read_text().strip())
        except (ValueError, OSError):
            pid = None
        running = vm.is_running()
        if pid is not None and not vm._qemu_pids_for_image([pid]):
            pid = None

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
