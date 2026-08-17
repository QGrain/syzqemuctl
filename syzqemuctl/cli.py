import os
import subprocess
import click
from rich.console import Console
from rich.table import Table
from datetime import datetime
from typing import Optional

from ._version import __title__, __version__, __author__, __email__
from .config import global_conf
from .image import ImageManager
from .vm import VM
from . import utils

console = Console()

def print_version(ctx, param, value):
    """Custom version info print function"""
    if not value or ctx.resilient_parsing:
        return
    
    version_info = f"[default][bold]{__title__} {__version__}\nAuthor: {__author__} <{__email__}>[/bold][/default]"
    
    # Check for latest version
    latest_version, error = utils.check_latest_version()
    if latest_version and utils.needs_update(__version__, latest_version):
        version_info += f"\n\n[yellow]Find new version: {latest_version}[/yellow]"
        version_info += "\n[yellow]Please run the following command to update:[/yellow]"
        version_info += "\n[green]pip install --upgrade syzqemuctl[/green]"
    elif error:
        version_info += f"\n\n[dim]Failed to check update: {error}[/dim]"
    
    console.print(version_info)
    ctx.exit()

@click.group()
@click.option('--version', is_flag=True, callback=print_version, expose_value=False, is_eager=True,
              help='print version info')
def cli():
    """QEMU virtual machine management tool"""
    try:
        global_conf.load()
    except Exception as e:
        console.print(f"[red]Error: Failed to load config - {e}[/red]")


def require_config() -> str:
    """Return images_home or fail without interfering with subcommand help"""
    if not global_conf.images_home:
        raise click.ClickException(f"Please run '{__title__} init' first")
    return global_conf.images_home

@cli.command()
@click.option("--images-home", required=True, help="Images home directory")
@click.option("--force", is_flag=True, help="Force reinitialize")
@click.option("--wait", is_flag=True, help="Wait until template creation completes")
@click.option("--size", type=click.IntRange(min=1), default=3072, help="Template disk size in MB (default: 3072)")
def init(images_home: str, force: bool = False, wait: bool = False, size: int = 3072):
    """Initialize configuration"""
    if global_conf.is_initialized() and not force:
        console.print(f"[yellow]Warning: {__title__} is already initialized[/yellow]")
        console.print(f"[yellow]Current cache dir: {global_conf.DEFAULT_CACHE_DIR}[/yellow]")
        console.print(f"[yellow]Current config file: {global_conf.config_file}[/yellow]")
        console.print(f"[yellow]Current images home: {global_conf.images_home}[/yellow]")
        if not click.confirm("Reinitialize?"):
            console.print("[green]Everything kept[/green]")
            return
        force = True

    if utils.check_command_injection(images_home):
        raise click.ClickException(
            "Invalid image home: contains dangerous characters"
        )
    # Initialize config
    global_conf.initialize(images_home, force=force, verbose=True)
    console.print(f"[green]Default cache dir: {global_conf.DEFAULT_CACHE_DIR}[/green]")
    console.print(f"[green]Config file created: {global_conf.config_file}[/green]")

    # Initialize image manager
    manager = ImageManager(global_conf.images_home, verbose=True)
    if not manager.initialize(force=force, blocking=wait, size=size):
        raise click.ClickException("Failed to initialize template image")
    console.print("[green]Starting template image creation, this may take a while...[/green]")
    console.print(f"Use '{__title__} status image-template' to check progress")

@cli.command()
@click.argument("name")
@click.option("--size", type=int, help="Disk size in MB. If unspecified, copies from default template. If specified and cache exists, copies from cache; otherwise creates from scratch.")
@click.option("--force", is_flag=True, help="Force creation from scratch, bypassing cache")
def create(name: str, size: Optional[int], force: bool):
    """Create new image"""
    images_home = require_config()
    if utils.check_command_injection(name):
        raise click.ClickException(
            "Invalid image name: contains dangerous characters"
        )
    manager = ImageManager(images_home, verbose=True)
    if manager.create(name, size, force=force):
        console.print(f"[green]Successfully created image: {name}[/green]")
    else:
        raise click.ClickException(f"Failed to create image: {name}")

@cli.command()
@click.argument("name")
def delete(name: str):
    """Delete image"""
    images_home = require_config()
    if utils.check_command_injection(name):
        raise click.ClickException(
            "Invalid image name: contains dangerous characters"
        )
    manager = ImageManager(images_home, verbose=True)
    if not manager.delete(name):
        raise click.ClickException(f"Failed to delete image: {name}")

@cli.command()
@click.argument("name")
def status(name: str):
    """Query image status"""
    images_home = require_config()
    if utils.check_command_injection(name):
        raise click.ClickException(
            "Invalid image name: contains dangerous characters"
        )
    manager = ImageManager(images_home, verbose=True)
    if info := manager.get_image_info(name):
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Property")
        table.add_column("Value")

        table.add_row("Name", info.name)
        table.add_row("Path", str(info.path))

        # Handle template status
        if info.is_template:
            created_time = datetime.fromtimestamp(info.created_at).strftime("%Y-%m-%d %H:%M:%S")
            if info.image_ready:
                table.add_row("Created At", created_time)
                table.add_row("Template Status", "[green]Ready[/green]")
            else:
                table.add_row("Created At", f"{created_time} [yellow]Creating...[/yellow]")
                table.add_row("Template Status", "[yellow]Initializing[/yellow]")
        else:
            table.add_row("Created At",
                         datetime.fromtimestamp(info.created_at).strftime("%Y-%m-%d %H:%M:%S"))

        # Show running status
        creation_screen = utils.make_screen_name(info.path, "creation")
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
        if any(creation_states):
            table.add_row("Status", "[yellow]Creating[/yellow]")
        elif any(state is None for state in creation_states):
            table.add_row("Status", "[yellow]Unknown[/yellow]")
        elif info.running:
            vm = VM(str(info.path), verbose=True)
            if vm.is_ready():
                table.add_row("Status", "[green]Running[/green]")
            else:
                table.add_row("Status", "[yellow]Starting[/yellow]")

            if vm_conf := vm.get_last_vm_config():
                table.add_row("Kernel", vm_conf.kernel)
                table.add_row("SSH Port", str(vm_conf.port))
                table.add_row("Memory", vm_conf.memory)
                table.add_row("CPU Cores", str(vm_conf.smp))
            table.add_row("PID", str(info.pid))
            table.add_row("Console", f"screen -r {vm.screen_name}")
        else:
            table.add_row("Status", "[yellow]Not Running[/yellow]")

        # Show image ready status for non-templates
        if not info.is_template:
            if info.image_ready:
                table.add_row("Image Ready", "[green]Yes[/green]")
            else:
                table.add_row("Image Ready", "[yellow]Creating...[/yellow]")

        console.print(table)
    else:
        raise click.ClickException(f"Image {name} not found")

@cli.command()
def list():
    """List all images"""
    images_home = require_config()
    manager = ImageManager(images_home, verbose=True)
    images = manager.list_images()
    
    # Print global config info
    console.print("\n[bold cyan]Global Configuration[/bold cyan]")
    console.print(f"Images Home: {global_conf.images_home}")
    console.print()
    
    if not images:
        console.print("[yellow]Error: No images found, template not created[/yellow]")
        console.print("Possible reasons:")
        console.print("1. IMAGES_HOME directory doesn't exist or permission denied")
        console.print("2. Initialization failed")
        console.print(f"Try running '{__title__} init --images-home DIR' again\n")
        return
        
    # Check if only template exists
    if len(images) == 1 and images[0].is_template:
        template = images[0]
        if not template.image_ready:
            console.print("[yellow]Template image is being created...[/yellow]")
            console.print(f"Use '{__title__} status image-template' to check progress\n")
        else:
            console.print("[green]Template image is ready![/green]")
            console.print("No other images available")
            console.print(f"Run '{__title__} create IMAGE_NAME' to create new image\n")
        return
        
    # Create table for all images
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Name")
    table.add_column("Created At")
    table.add_column("Status")
    table.add_column("PID")
    
    # Show template and cache templates first
    templates = [img for img in images if img.is_template]
    for template in templates:
        created_time = datetime.fromtimestamp(template.created_at).strftime("%Y-%m-%d %H:%M:%S")
        if template.is_cache:
            if not template.image_ready:
                created_time = f"{created_time} [yellow]Creating...[/yellow]"
                status = "[yellow]Cache (Creating)[/yellow]"
            else:
                status = "[dim]Cache (Ready)[/dim]"
            table.add_row(
                template.name,
                created_time,
                status,
                str(template.pid) if template.pid else "-"
            )
        else:
            if not template.image_ready:
                created_time = f"{created_time} [yellow]Creating...[/yellow]"
                status = "[yellow]Initializing[/yellow]"
            else:
                status = "[green]Ready[/green]" if template.running else "[yellow]Not Running[/yellow]"
            table.add_row(
                "image-template",
                created_time,
                status,
                str(template.pid) if template.pid else "-"
            )

    # Show other images
    for img in [img for img in images if not img.is_template]:
        status = "[green]Running[/green]" if img.running else "[yellow]Not Running[/yellow]"
        table.add_row(
            img.name,
            datetime.fromtimestamp(img.created_at).strftime("%Y-%m-%d %H:%M:%S"),
            status,
            str(img.pid) if img.pid else "-"
        )
        
    console.print(table)
    console.print()

@cli.command()
@click.argument("name")
@click.option("--kernel", help="Kernel path")
@click.option("--port", type=int, help="SSH port")
@click.option("--mem", help="Memory size")
@click.option("--smp", type=int, help="CPU cores")
@click.option("--snapshot", is_flag=True, help="Run with snapshot mode (changes discarded on shutdown)")
@click.option(
    "--kernel-args",
    help="Replace the complete guest kernel command line",
)
@click.option(
    "--extra-kernel-args",
    help="Append arguments to the saved or default guest kernel command line",
)
def run(
    name: str,
    kernel: Optional[str],
    port: Optional[int],
    mem: Optional[str],
    smp: Optional[int],
    snapshot: bool,
    kernel_args: Optional[str],
    extra_kernel_args: Optional[str],
):
    """Run virtual machine"""
    images_home = require_config()
    if utils.check_command_injection(name) or utils.check_command_injection(kernel) or utils.check_command_injection(mem):
        raise click.ClickException("Invalid input: contains dangerous characters")
    # Check if image exists
    manager = ImageManager(images_home, verbose=True)
    if not (info := manager.get_image_info(name)):
        raise click.ClickException(f"Image {name} not found")
        
    # Check if image is ready
    if not info.image_ready:
        raise click.ClickException(f"Image {name} is not ready yet")

    # Create VM instance and start
    vm = VM(str(info.path), verbose=True)
    if vm.start(
        kernel=kernel,
        port=port,
        mem=mem,
        smp=smp,
        snapshot=snapshot,
        kernel_args=kernel_args,
        extra_kernel_args=extra_kernel_args,
    ):
        console.print("[green]Starting VM... SSH will be available soon[/green]")
        console.print(f"Use '{__title__} status {name}' or check console for status")
    else:
        raise click.ClickException("Failed to start VM")

@cli.command()
@click.argument("name")
@click.option("--wait", is_flag=True, help="Wait until runtime cleanup completes")
@click.option("--force", is_flag=True, help="Clean stale runtime and orphan QEMU processes")
@click.option(
    "--timeout",
    type=click.IntRange(min=1),
    default=20,
    show_default=True,
    help="Maximum seconds to wait when --wait is used",
)
def stop(name: str, wait: bool, force: bool, timeout: int):
    """Stop virtual machine"""
    images_home = require_config()
    if utils.check_command_injection(name):
        raise click.ClickException("Invalid image name: contains dangerous characters")
    manager = ImageManager(images_home, verbose=True)
    if not (info := manager.get_image_info(name)):
        raise click.ClickException(f"Image {name} not found")
        
    if not info.running and not force:
        console.print(f"[yellow]Warning: Image {name} is not running[/yellow]")
        return
        
    vm = VM(str(info.path), verbose=True)
    if vm.stop(wait=wait, timeout=timeout, force=force):
        console.print("[green]VM stopped[/green]")
    else:
        raise click.ClickException("Failed to stop VM")

@cli.command()
@click.argument("name")
def restart(name: str):
    """Restart virtual machine with last configuration"""
    images_home = require_config()
    if utils.check_command_injection(name):
        raise click.ClickException(
            "Invalid image name: contains dangerous characters"
        )
    manager = ImageManager(images_home, verbose=True)
    if not (info := manager.get_image_info(name)):
        raise click.ClickException(f"Image {name} not found")
    
    if not info.image_ready:
        raise click.ClickException(f"Image {name} is not ready yet")

    if not info.running:
        raise click.ClickException(f"Image {name} is not running")

    # Stop VM
    vm = VM(str(info.path), verbose=True)
    if not vm.stop():
        raise click.ClickException("Failed to stop VM")
    console.print("[green]VM stopped[/green]")
    
    # Restart VM with the previous configuration
    if vm.start():
        console.print("[yellow]Restarting VM with last boot configuration (no snapshot by default), this may take some time[/yellow]")
        console.print(f"Use '{__title__} status {name}' or check console for status")
    else:
        raise click.ClickException("Failed to restart VM")

@cli.command()
@click.argument("src")
@click.argument("dst")
@click.option(
    "--timeout",
    type=click.IntRange(min=1),
    default=None,
    help="Maximum seconds for the file transfer",
)
def cp(src: str, dst: str, timeout: Optional[int]):
    """Copy files between host and VM"""
    images_home = require_config()
    if utils.check_command_injection(src) or utils.check_command_injection(dst):
        raise click.ClickException("Invalid input: contains dangerous characters")
    # Parse paths
    def parse_path(path: str):
        if ":" in path:
            image_name, remote_path = path.split(":", 1)
            return image_name, remote_path
        return None, path
        
    src_image, src_path = parse_path(src)
    dst_image, dst_path = parse_path(dst)
    
    if src_image and dst_image:
        raise click.ClickException("Direct copy between VMs not supported")
        
    if not (src_image or dst_image):
        raise click.ClickException("Must specify a VM path")
        
    # Get image info
    image_name = src_image or dst_image
    manager = ImageManager(images_home, verbose=True)
    if not (info := manager.get_image_info(image_name)):
        raise click.ClickException(f"Image {image_name} not found")
        
    if not info.image_ready:
        raise click.ClickException(f"Image {image_name} is not ready yet")

    if not info.running:
        raise click.ClickException(f"Image {image_name} is not running")

    # Handle file transfer
    vm = VM(str(info.path), verbose=True)
    try:
        with vm:
            if src_image:
                dst_dir = os.path.dirname(dst_path)
                if dst_dir:
                    os.makedirs(dst_dir, exist_ok=True)
                vm.copy_from_vm(src_path, dst_path, timeout=timeout)
                console.print(f"[green]Copied from VM: {src} to {dst}[/green]")
            else:
                if not os.path.exists(src_path):
                    raise FileNotFoundError(f"Source path {src_path} does not exist")
                vm.copy_to_vm(src_path, dst_path, timeout=timeout)
                console.print(f"[green]Copied to VM: {src} to {dst}[/green]")
    except Exception as e:
        raise click.ClickException(f"Failed to copy file: {e}") from e

@cli.command()
@click.argument("name")
@click.argument("command")
@click.option(
    "--timeout",
    type=click.IntRange(min=1),
    default=None,
    help="Maximum seconds for command execution",
)
def exec(name: str, command: str, timeout: Optional[int]):
    """Execute command in VM"""
    images_home = require_config()
    if utils.check_command_injection(name):
        raise click.ClickException("Invalid image name: contains dangerous characters")
    manager = ImageManager(images_home, verbose=True)
    if not (info := manager.get_image_info(name)):
        raise click.ClickException(f"Image {name} not found")
        
    if not info.image_ready:
        raise click.ClickException(f"Image {name} is not ready yet")

    if not info.running:
        raise click.ClickException(f"Image {name} is not running")

    # Execute command
    vm = VM(str(info.path), verbose=True)

    try:
        with vm:
            stdout, stderr = vm.execute(
                command,
                timeout=timeout,
                check=True,
            )
            if stdout:
                console.print("[bold]STDOUT:[/bold]")
                console.print(stdout)
            if stderr:
                console.print("[bold red]STDERR:[/bold red]")
                console.print(stderr)
    except subprocess.CalledProcessError as e:
        if e.output:
            console.print("[bold]STDOUT:[/bold]")
            console.print(e.output)
        if e.stderr:
            console.print("[bold red]STDERR:[/bold red]")
            console.print(e.stderr)
        raise click.ClickException(
            f"Remote command exited with status {e.returncode}"
        ) from e
    except Exception as e:
        raise click.ClickException(f"Failed to execute command: {e}") from e

if __name__ == "__main__":
    cli()
