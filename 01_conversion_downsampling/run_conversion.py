"""Explicit command-line entry point for the preserved conversion scripts."""
import argparse
import importlib
import math
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description='Convert and downsample whole-slide images.')
    p.add_argument('--format', choices=['vsi', 'czi', 'other'], required=True)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--folder', required=True, help='Output subfolder, such as 2x or 20x')
    p.add_argument('--mpp', type=float, required=True, help='Micrometres/pixel; 0 retains native resolution')
    p.add_argument('--plain-tif', action='store_true', help='Write plain TIFF for low-resolution CODA input')
    p.add_argument('--fast-pyramid', action='store_true')
    args = p.parse_args()
    if not args.input.exists():
        p.error('Input does not exist.')
    if not math.isfinite(args.mpp) or args.mpp < 0:
        p.error('mpp must be finite and >= 0.')
    if Path(args.folder).name != args.folder or args.folder in ('.', '..'):
        p.error('folder must be a single directory name.')
    if args.format != 'other' and not args.input.is_dir():
        p.error('The dedicated VSI/CZI converters require an input directory.')
    destination = args.output.resolve() / args.folder
    source_folder = args.input.resolve() if args.input.is_dir() else args.input.resolve().parent
    if destination == source_folder:
        p.error('Output directory must differ from the input directory.')
    extensions = {'.vsi'} if args.format == 'vsi' else {'.czi'} if args.format == 'czi' else {
        '.vsi', '.czi', '.ndpi', '.ndp', '.svs', '.scn', '.mrxs', '.dcm', '.qptiff',
        '.tif', '.tiff', '.isyntax', '.i2syntax'}
    candidates = [args.input] if args.input.is_file() else list(args.input.iterdir())
    if not any(f.is_file() and f.suffix.lower() in extensions for f in candidates):
        p.error('No supported input images found.')
    modules = {'vsi': ('vsi2ometif', 'VSI2tif'), 'czi': ('CZI2OMEtif', 'CZI2tif'),
               'other': ('WSI2OMEtif_All_file_types', 'WSI2tif')}
    name, function = modules[args.format]
    convert = getattr(importlib.import_module(name), function)
    convert(str(args.input.resolve()), [args.folder], [args.mpp],
            [int(not args.plain_tif)], int(not args.fast_pyramid),
            outpth=str(args.output.resolve()))


if __name__ == '__main__':
    main()
