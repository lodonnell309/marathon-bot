import os

def list_directory_structure(
    base_path='.',
    exclude_folder='zz_marathon-coach',
    shallow_folders={'.venv', '__pycache__'}
):
    for root, dirs, files in os.walk(base_path):
        # Skip the excluded folder
        if exclude_folder in dirs:
            dirs.remove(exclude_folder)

        # Compute indentation level
        level = root.replace(base_path, '').count(os.sep)
        indent = ' ' * 4 * level
        print(f"{indent}{os.path.basename(root) or '.'}/")

        # Shallow print then skip designated shallow folders
        for shallow in shallow_folders:
            if shallow in dirs:
                print(f"{' ' * 4 * (level + 1)}{shallow}/")
                dirs.remove(shallow)

        # Print files in this folder
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            print(f"{subindent}{f}")

# Run it
list_directory_structure()
