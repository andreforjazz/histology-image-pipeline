"""Report installed pipeline dependencies without printing machine paths or credentials."""
import importlib
import importlib.metadata
import sys

MODULES = {'numpy': 'numpy', 'PIL': 'Pillow', 'tifffile': 'tifffile',
           'imagecodecs': 'imagecodecs', 'cv2': 'opencv-python', 'scipy': 'scipy',
           'openslide': 'openslide-python', 'h5py': 'h5py', 'matplotlib': 'matplotlib'}
OPTIONAL = {'slideio': 'slideio', 'pylibCZIrw': 'pylibCZIrw',
            'matlab.engine': 'matlabengine', 'wsidicom': 'wsidicom', 'isyntax': 'pyisyntax'}


def main():
    print(f'Python {sys.version.split()[0]}')
    missing = []
    for optional, packages in ((False, MODULES), (True, OPTIONAL)):
        for module, package in packages.items():
            try:
                importlib.import_module(module)
                print(f'OK {package} {importlib.metadata.version(package)}')
            except (ImportError, OSError, importlib.metadata.PackageNotFoundError):
                print(f'{"OPTIONAL" if optional else "MISSING"} {package}')
                if not optional:
                    missing.append(package)
    return bool(missing)


if __name__ == '__main__':
    raise SystemExit(main())
