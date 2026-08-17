import threading
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from syzqemuctl.image import ImageManager
from syzqemuctl import utils


class ImageSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.images_home = Path(self.tempdir.name) / "images home"
        self.images_home.mkdir()
        self.manager = ImageManager(str(self.images_home))

    def test_delete_rejects_path_traversal(self):
        with patch("syzqemuctl.image.shutil.rmtree") as rmtree:
            result = self.manager.delete("../outside")

        self.assertFalse(result)
        rmtree.assert_not_called()

    def test_delete_rejects_symbolic_link(self):
        image_path = self.images_home / "image"
        image_path.mkdir()
        (self.images_home / "alias").symlink_to(image_path, target_is_directory=True)

        with patch("syzqemuctl.image.shutil.rmtree") as rmtree:
            result = self.manager.delete("alias")

        self.assertFalse(result)
        rmtree.assert_not_called()

    def test_delete_refuses_running_image(self):
        image_path = self.images_home / "image"
        image_path.mkdir()

        with patch("syzqemuctl.vm.VM.is_running", return_value=True), patch(
            "syzqemuctl.image.shutil.rmtree"
        ) as rmtree:
            result = self.manager.delete("image")

        self.assertFalse(result)
        rmtree.assert_not_called()

    def test_delete_stopped_image(self):
        image_path = self.images_home / "image"
        image_path.mkdir()

        with patch("syzqemuctl.vm.VM.is_running", return_value=False), patch(
            "syzqemuctl.vm.VM._screen_session_ids", return_value=[]
        ), patch(
            "syzqemuctl.image.utils.check_screen_exists", return_value=False
        ):
            result = self.manager.delete("image")

        self.assertTrue(result)
        self.assertFalse(image_path.exists())

    def test_delete_refuses_image_with_runtime_screen(self):
        image_path = self.images_home / "image"
        image_path.mkdir()

        with patch("syzqemuctl.vm.VM.is_running", return_value=False), patch(
            "syzqemuctl.vm.VM._screen_session_ids",
            return_value=["123.syzqemuctl-image"],
        ), patch("syzqemuctl.image.shutil.rmtree") as rmtree:
            result = self.manager.delete("image")

        self.assertFalse(result)
        rmtree.assert_not_called()

    def test_delete_refuses_when_runtime_screen_state_is_unknown(self):
        image_path = self.images_home / "image"
        image_path.mkdir()

        with patch(
            "syzqemuctl.vm.VM._screen_session_ids", return_value=None
        ), patch("syzqemuctl.image.shutil.rmtree") as rmtree:
            result = self.manager.delete("image")

        self.assertFalse(result)
        rmtree.assert_not_called()

    def test_blocking_initialize_uses_argv_and_cwd(self):
        (self.images_home / "create-image.sh").write_text("#!/bin/sh\n")

        with patch.object(
            self.manager, "_download_create_script"
        ), patch("syzqemuctl.image.subprocess.run") as run:
            self.manager.initialize(blocking=True, size=4096)

        run.assert_called_once_with(
            ["./create-image.sh", "-s", "4096"],
            cwd=str(self.manager.template_default_dir),
            check=True,
        )
        self.assertTrue(
            (self.manager.template_default_dir / ".image_ready").exists()
        )

    def test_background_initialize_passes_path_as_shell_argument(self):
        (self.images_home / "create-image.sh").write_text("#!/bin/sh\n")

        with patch.object(
            self.manager, "_download_create_script"
        ), patch("syzqemuctl.image.subprocess.Popen") as popen:
            self.manager.initialize(blocking=False, size=4096)

        command = popen.call_args.args[0]
        self.assertNotIn(str(self.manager.template_default_dir), command[5])
        self.assertIn(str(self.manager.template_default_dir), command)

    def test_image_operation_lock_serializes_threads(self):
        image_path = self.images_home / "image"
        image_path.mkdir()
        first_entered = threading.Event()
        release_first = threading.Event()
        second_started = threading.Event()
        second_entered = threading.Event()

        def hold_first():
            with utils.image_operation_lock(image_path):
                first_entered.set()
                release_first.wait(1)

        def enter_second():
            second_started.set()
            with utils.image_operation_lock(image_path):
                second_entered.set()

        first = threading.Thread(target=hold_first)
        second = threading.Thread(target=enter_second)
        first.start()
        self.assertTrue(first_entered.wait(1))
        second.start()
        self.assertTrue(second_started.wait(1))
        time.sleep(0.02)
        self.assertFalse(second_entered.is_set())

        release_first.set()
        first.join(1)
        second.join(1)
        self.assertTrue(second_entered.is_set())


if __name__ == "__main__":
    unittest.main()
