import os, zipfile, pathlib, sys
repo_root = pathlib.Path('.')
zip_path = repo_root / 'code.zip'
with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
    # Add README.md
    readme = repo_root / 'README.md'
    if readme.is_file():
        z.write(readme, arcname='README.md')
    # Add code directory recursively with forward-slash paths
    code_dir = repo_root / 'code'
    for dirpath, _, filenames in os.walk(code_dir):
        for fname in filenames:
            file_path = pathlib.Path(dirpath) / fname
            rel_path = file_path.relative_to(repo_root).as_posix()
            z.write(file_path, arcname=rel_path)
print('ZIP created at', zip_path)
