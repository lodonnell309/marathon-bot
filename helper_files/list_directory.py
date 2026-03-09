"""
Prints the project directory tree. Skips .git, .venv, __pycache__ by default.
Run from repo root: python helper_files/list_directory.py
"""
import os


def list_directory_structure(
    base_path: str = ".",
    exclude_dirs: frozenset = frozenset({".git", ".venv", "venv", "__pycache__"}),
):
    for root, dirs, files in os.walk(base_path):
        for d in exclude_dirs:
            if d in dirs:
                dirs.remove(d)
        level = root.replace(base_path, "").count(os.sep)
        indent = " " * 4 * level
        print(f"{indent}{os.path.basename(root) or '.'}/")
        subindent = " " * 4 * (level + 1)
        for f in files:
            print(f"{subindent}{f}")


if __name__ == "__main__":
    list_directory_structure()
