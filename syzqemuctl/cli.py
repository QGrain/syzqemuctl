import click
from rich.console import Console
from rich.table import Table
from datetime import datetime

from ._version import __title__, __version__, __author__, __email__
from .config import global_conf
from .image import ImageManager
from .vm import VM

console = Console()

def format_size(size: int) -> str:
    """Format file size"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"

@click.group()
@click.version_option(version=__version__, message=f"{__title__} {__version__}\nAuthor: {__author__} <{__email__}>")
def cli():
    """QEMU virtual machine management tool"""
    try:
        # Try to load config
        if not global_conf.load():
            if click.get_current_context().invoked_subcommand != "init":
                console.print(f"[red]Error: Please run '{__title__} init' first[/red]")
                exit(1)
    except Exception as e:
        console.print(f"[red]Error: Failed to load config - {e}[/red]")
        if click.get_current_context().invoked_subcommand != "init":
            exit(1)

@cli.command()
@click.option("--images-home", required=True, help="Images home directory")
def init(images_home: str):
    """Initialize configuration"""
    if global_conf.is_initialized():
        console.print(f"[yellow]Warning: {__title__} is already initialized[/yellow]")
        if not click.confirm("Reinitialize?"):
            return
            
    # Initialize config
    global_conf.initialize(images_home)
    console.print(f"[green]Config file created: {global_conf.config_file}[/green]")
    
    # Initialize image manager
    manager = ImageManager(global_conf.images_home)
    manager.initialize()
    console.print("[green]Starting template image creation, this may take a while...[/green]")
    console.print(f"Use '{__title__} status image-template' to check progress")

@cli.command()
@click.argument("name")
def create(name: str):
    """Create new image"""
    manager = ImageManager(global_conf.images_home)
    manager.create(name)

@cli.command()
@click.argument("name")
def delete(name: str):
    """Delete image"""
    manager = ImageManager(global_conf.images_home)
    manager.delete(name)

@cli.command()
@click.argument("name")
def status(name: str):
    """Query image status"""
    manager = ImageManager(global_conf.images_home)
    if info := manager.get_image_info(name):
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Property")
        table.add_column("Value")
        
        table.add_row("Name", info.name)
        table.add_row("Path", str(info.path))
        
        # Handle template status
        if info.is_template:
            created_time = datetime.fromtimestamp(info.created_at).strftime("%Y-%m-%d %H:%M:%S")
            if info.template_ready:
                table.add_row("Created At", created_time)
                table.add_row("Template Status", "[green]Ready[/green]")
            else:
                table.add_row("Created At", f"{created_time} [yellow]Creating...[/yellow]")
                table.add_row("Template Status", "[yellow]Initializing[/yellow]")
        else:
            table.add_row("Created At", 
                         datetime.fromtimestamp(info.created_at).strftime("%Y-%m-%d %H:%M:%S"))
            
        # Show running status
        if info.running:
            vm = VM(str(info.path))
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
            
        console.print(table)
    else:
        console.print(f"[red]Error: Image {name} not found[/red]")

@cli.command()
def list():
    """List all images"""
    manager = ImageManager(global_conf.images_home)
    images = manager.list_images()
    
    # Print global config info
    console.print(f"\n[bold cyan]Global Configuration[/bold cyan]")
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
        if not template.template_ready:
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
    
    # Show template status first
    template = next((img for img in images if img.is_template), None)
    if template:
        created_time = datetime.fromtimestamp(template.created_at).strftime("%Y-%m-%d %H:%M:%S")
        if not template.template_ready:
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
def run(name: str, kernel: str, port: int, mem: str, smp: int):
    """Run virtual machine"""
    # Check if image exists
    manager = ImageManager(global_conf.images_home)
    if not (info := manager.get_image_info(name)):
        console.print(f"[red]Error: Image {name} not found[/red]")
        return
        
    # Check if already running
    if info.running:
        console.print(f"[red]Error: Image {name} is already running[/red]")
        return
        
    # Create VM instance and start
    vm = VM(str(info.path))  
    if vm.start(kernel, port, mem, smp):
        console.print("[green]Starting VM... SSH will be available soon[/green]")
        console.print(f"Use '{__title__} status {name}' or check console for status")
    else:
        console.print("[red]Failed to start VM[/red]")

@cli.command()
@click.argument("name")
def stop(name: str):
    """Stop virtual machine"""
    manager = ImageManager(global_conf.images_home)
    if not (info := manager.get_image_info(name)):
        console.print(f"[red]Error: Image {name} not found[/red]")
        return
        
    if not info.running:
        console.print(f"[yellow]Warning: Image {name} is not running[/yellow]")
        return
        
    vm = VM(str(info.path))
    if vm.stop():
        console.print("[green]VM stopped[/green]")
    else:
        console.print("[red]Failed to stop VM[/red]")

@cli.command()
@click.argument("src")
@click.argument("dst")
def cp(src: str, dst: str):
    """Copy files between host and VM"""
    # Parse paths
    def parse_path(path: str):
        if ":" in path:
            image_name, remote_path = path.split(":", 1)
            return image_name, remote_path
        return None, path
        
    src_image, src_path = parse_path(src)
    dst_image, dst_path = parse_path(dst)
    
    if src_image and dst_image:
        console.print("[red]Error: Direct copy between VMs not supported[/red]")
        return
        
    if not (src_image or dst_image):
        console.print("[red]Error: Must specify a VM path[/red]")
        return
        
    # Get image info
    image_name = src_image or dst_image
    manager = ImageManager(global_conf.images_home)
    if not (info := manager.get_image_info(image_name)):
        console.print(f"[red]Error: Image {image_name} not found[/red]")
        return
        
    if not info.running:
        console.print(f"[red]Error: Image {image_name} is not running[/red]")
        return
        
    # Handle file transfer
    vm = VM(str(info.path))
    if not vm.is_ready():
        console.print(f"[yellow]Error: Image {image_name} is starting, please wait[/yellow]")
        return
        
    with vm:
        try:
            if src_image:
                vm.copy_from_vm(src_path, dst_path)
                console.print(f"[green]Copied from VM: {dst_path}[/green]")
            else:
                vm.copy_to_vm(src_path, dst_path)
                console.print(f"[green]Copied to VM: {dst_path}[/green]")
        except Exception as e:
            console.print(f"[red]Failed to copy file: {e}[/red]")

@cli.command()
@click.argument("name")
@click.argument("command")
def exec(name: str, command: str):
    """Execute command in VM"""
    manager = ImageManager(global_conf.images_home)
    if not (info := manager.get_image_info(name)):
        console.print(f"[red]Error: Image {name} not found[/red]")
        return
        
    if not info.running:
        console.print(f"[red]Error: Image {name} is not running[/red]")
        return
        
    # Execute command
    vm = VM(str(info.path))
        
    with vm:
        try:
            stdout, stderr = vm.execute(command)
            if stdout:
                console.print("[bold]STDOUT:[/bold]")
                console.print(stdout)
            if stderr:
                console.print("[bold red]STDERR:[/bold red]")
                console.print(stderr)
        except Exception as e:
            console.print(f"[red]Failed to execute command: {e}[/red]")

if __name__ == "__main__":
    cli() 