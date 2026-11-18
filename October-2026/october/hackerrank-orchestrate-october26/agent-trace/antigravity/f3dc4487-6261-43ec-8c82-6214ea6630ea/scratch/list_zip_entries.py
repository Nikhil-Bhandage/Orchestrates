import zipfile, sys
zip_path = 'code.zip'
with zipfile.ZipFile(zip_path, 'r') as z:
    for name in z.namelist():
        print(name)
