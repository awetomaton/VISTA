#!/usr/bin/env python3
"""
Fix GIF loop counts to make them loop infinitely.

Usage:
    python fix_gif_loops.py
"""

from pathlib import Path

from PIL import Image


def fix_gif_loop(gif_path):
    """
    Set GIF to loop infinitely (loop count = 0).

    Parameters
    ----------
    gif_path : Path
        Path to the GIF file
    """
    try:
        # Open the GIF
        img = Image.open(gif_path)

        # Check if it's an animated GIF
        if not getattr(img, "is_animated", False):
            print(f"  Skipping {gif_path.name} (not animated)")
            return

        # Extract all frames
        frames = []
        durations = []

        try:
            while True:
                frames.append(img.copy())
                durations.append(img.info.get("duration", 100))
                img.seek(img.tell() + 1)
        except EOFError:
            pass  # End of frames

        # Save with infinite loop (loop=0)
        frames[0].save(
            gif_path,
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=0,  # 0 = infinite loop
            optimize=False,
        )

        print(f"  ✓ Fixed {gif_path.name}")

    except Exception as e:
        print(f"  ✗ Error processing {gif_path.name}: {e}")


def main():
    """Find and fix all GIF files in the _static directory."""
    # Get the script directory
    script_dir = Path(__file__).parent
    static_dir = script_dir / "source" / "_static"

    if not static_dir.exists():
        print(f"Error: Directory not found: {static_dir}")
        return

    # Find all GIF files
    gif_files = list(static_dir.glob("**/*.gif"))

    if not gif_files:
        print("No GIF files found in _static directory")
        return

    print(f"Found {len(gif_files)} GIF file(s)")
    print("Processing...\n")

    for gif_path in gif_files:
        fix_gif_loop(gif_path)

    print(f"\nDone! Processed {len(gif_files)} file(s)")


if __name__ == "__main__":
    main()
