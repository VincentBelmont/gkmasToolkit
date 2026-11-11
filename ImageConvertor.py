"""Resizes PNG textures exported from Unity and saves them as lossless WebP.

This is a standalone helper: it does not read .unity3d bundles. Point it at the
folder where your Unity extractor (AssetStudio, AssetRipper, ...) wrote the
textures.

Usage:
    python ImageConvertor.py <input-dir> [-o OUTPUT] [--size 1820x1024]
                             [--format webp|png] [--flat]
"""

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("ImageConvertor needs Pillow: pip install -r requirements-optional.txt")
    raise SystemExit(2)
from rich.console import Console

# The game's textures are 2048x1024 with extra padding around the content.
DEFAULT_SIZE = (1820, 1024)

console = Console()


def parseSize(text):
    """Parses 'WIDTHxHEIGHT' into a (width, height) tuple."""
    try:
        width, height = (int(part) for part in text.lower().split("x"))
    except Exception:
        raise argparse.ArgumentTypeError("expected WIDTHxHEIGHT, for example 1820x1024")
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("width and height must be positive")
    return width, height


def destinationFor(path, inputRoot, outputRoot, formatName, flat, used):
    """Builds the output path, mirroring subdirectories unless --flat was given."""
    subdirectory = Path() if flat else path.relative_to(inputRoot).parent
    candidate = outputRoot / subdirectory / f"{path.stem}.{formatName}"
    suffix = 1
    while candidate in used:
        candidate = outputRoot / subdirectory / f"{path.stem}-{suffix}.{formatName}"
        suffix += 1
    used.add(candidate)
    return candidate


def convertFile(path, destination, targetSize, formatName):
    """Resizes (or reuses, when already the right size) and writes one image."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(path) as image:
        converted = image if image.size == targetSize else image.resize(
            targetSize, resample=Image.LANCZOS, reducing_gap=3
        )
        if converted.mode not in ("RGB", "RGBA"):
            converted = converted.convert("RGBA")
        if formatName == "webp":
            converted.save(destination, format="webp", lossless=True, method=6)
        else:
            converted.save(destination, format="png")
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Resize extracted PNG textures and export them as lossless WebP or PNG."
    )
    parser.add_argument("input", type=Path, help="directory containing the exported PNGs")
    parser.add_argument("-o", "--output", type=Path,
                        help="output directory (default: <input>/Converted)")
    parser.add_argument("--size", type=parseSize, default=DEFAULT_SIZE, metavar="WxH",
                        help="target size in pixels, default 1820x1024")
    parser.add_argument("--format", choices=("webp", "png"), default="webp",
                        help="output format, default webp")
    parser.add_argument("--flat", action="store_true",
                        help="write every output into one directory instead of mirroring subdirectories")
    args = parser.parse_args(argv)

    inputRoot = args.input.resolve()
    if not inputRoot.is_dir():
        console.print(f"[bold red]>>> [Error][/bold red] Input folder '{inputRoot}' does not exist.")
        return 2

    outputRoot = (args.output or inputRoot / "Converted").resolve()
    files = sorted(inputRoot.rglob("*.png"))
    if not files:
        console.print(f"[bold yellow]>>> [Warn][/bold yellow] No PNG files found under '{inputRoot}'.")
        return 0

    total = len(files)
    converted = 0
    failures = []
    used = set()

    for index, path in enumerate(files, start=1):
        try:
            destination = destinationFor(path, inputRoot, outputRoot, args.format, args.flat, used)
            convertFile(path, destination, args.size, args.format)
            converted += 1
            console.print(f"[bold green]>>> [Succeed][/bold green] ({index}/{total}) '{path.name}' -> {destination}")
        except Exception as error:
            failures.append(path)
            console.print(f"[bold red]>>> [Failed][/bold red] ({index}/{total}) '{path.name}': {type(error).__name__}: {error}")

    console.print(
        f"[bold]>>> [Summary][/bold] {converted}/{total} converted, {len(failures)} failed, "
        f"output -> {outputRoot}"
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
