"""Edit the settings below and run this script to export several resolutions at once."""
import argparse
import importlib
import math
import sys
from pathlib import Path

# ---------------- EDIT THESE SETTINGS, THEN RUN THIS SCRIPT ----------------
pth0 = r'D:\data\raw'                # Input folder (or one file for 'other')
outpth = None                       # None saves subfolders under the input folder
file_format = 'vsi'                 # 'vsi', 'czi', or 'other'
folder_names = ['2x', '10x', '20x', '40x']
pixel_resolutions = [5, 1, 0.5, 0.25]  # Micrometres/pixel; 0 keeps native resolution
save_ome = [0, 1, 1, 1]             # Per folder: 0 = plain TIFF, 1 = OME-TIFF
load_native_resolution = 1          # 1 = native decoding; 0 = allow source pyramid
# Lists correspond by position. Each source is loaded once at the finest needed
# resolution, then all requested outputs are generated from that loaded image.
# --------------------------------------------------------------------------


def run_conversion(input_path, output_path, image_format, folders, resolutions,
                   ome_flags, native=1):
    """Validate all outputs first, then call the selected reader once per batch."""
    source = Path(input_path).resolve()
    if not source.exists():
        raise ValueError(f'Input does not exist: {source}')
    if image_format not in ('vsi', 'czi', 'other'):
        raise ValueError("file_format must be 'vsi', 'czi', or 'other'.")
    if image_format != 'other' and not source.is_dir():
        raise ValueError('The dedicated VSI/CZI converters require an input directory.')
    if not folders or not (len(folders) == len(resolutions) == len(ome_flags)):
        raise ValueError('folder_names, pixel_resolutions and save_ome must have equal nonzero lengths.')
    if not all(math.isfinite(mpp) and mpp >= 0 for mpp in resolutions):
        raise ValueError('All resolutions must be finite and >= 0.')
    if any(flag not in (0, 1) for flag in ome_flags) or native not in (0, 1):
        raise ValueError('save_ome and load_native_resolution must contain only 0 or 1.')
    if len({folder.casefold() for folder in folders}) != len(folders):
        raise ValueError('Output subfolder names must be unique.')
    source_folder = source if source.is_dir() else source.parent
    output = Path(output_path).resolve() if output_path is not None else source_folder
    for folder in folders:
        if not folder or '/' in folder or '\\' in folder or ':' in folder or folder in ('.', '..'):
            raise ValueError('Each folder must be a single directory name.')
        if (output / folder).resolve() == source_folder:
            raise ValueError('Output directory must differ from the input directory.')
    extensions = {'.vsi'} if image_format == 'vsi' else {'.czi'} if image_format == 'czi' else {
        '.vsi', '.czi', '.ndpi', '.ndp', '.svs', '.scn', '.mrxs', '.dcm', '.qptiff',
        '.tif', '.tiff', '.isyntax', '.i2syntax'}
    candidates = [source] if source.is_file() else list(source.iterdir())
    if not any(f.is_file() and f.suffix.lower() in extensions for f in candidates):
        raise ValueError('No supported input images found.')
    modules = {'vsi': ('vsi2ometif', 'VSI2tif'), 'czi': ('CZI2OMEtif', 'CZI2tif'),
               'other': ('WSI2OMEtif_All_file_types', 'WSI2tif')}
    name, function = modules[image_format]
    convert = getattr(importlib.import_module(name), function)
    convert(str(source), list(folders), list(resolutions), list(ome_flags),
            native, outpth=str(output))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        run_conversion(pth0, outpth, file_format, folder_names, pixel_resolutions,
                       save_ome, load_native_resolution)
        return
    p = argparse.ArgumentParser(description='Convert and downsample whole-slide images.')
    p.add_argument('--format', choices=['vsi', 'czi', 'other'], required=True)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--folder', nargs='+', required=True, help='Output subfolders, e.g. 2x 10x 20x 40x')
    p.add_argument('--mpp', nargs='+', type=float, required=True, help='MPP for each folder; 0 retains native resolution')
    formats = p.add_mutually_exclusive_group()
    formats.add_argument('--plain-tif', action='store_true', help='Write plain TIFF for every output')
    formats.add_argument('--save-ome', nargs='+', type=int, choices=[0, 1], help='Per folder: 0 = TIFF, 1 = OME-TIFF')
    p.add_argument('--fast-pyramid', action='store_true')
    args = p.parse_args(argv)
    flags = args.save_ome if args.save_ome is not None else [int(not args.plain_tif)] * len(args.folder)
    try:
        run_conversion(args.input, args.output, args.format, args.folder, args.mpp,
                       flags, int(not args.fast_pyramid))
    except ValueError as exc:
        p.error(str(exc))


if __name__ == '__main__':
    main()
