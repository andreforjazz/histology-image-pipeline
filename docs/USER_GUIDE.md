# User guide

## 1. Set up a new computer

Clone this repository, create a Python 3.11 virtual environment, and install the requirements as shown in the main README. In PyCharm, open the repository folder and select that environment as the interpreter.

`requirements/conversion.txt` installs the core image libraries and VSI/CZI readers. `requirements/registration.txt` installs the transform-application dependencies. DICOM and iSyntax have optional backends (`wsidicom` and `pyisyntax`); install and validate those separately when needed. The code's recognition of a file extension does not guarantee that every vendor variant can be decoded.

The calculation stage requires MATLAB with Image Processing Toolbox. MATLAB Engine for Python is only required when applying older CODA MAT files that lack the numeric `tform_python` export. Match the Engine version to your installed MATLAB release. New registrations calculated through `run_registration.m` export numeric matrices, so their application does not start MATLAB.

Run `python tools/check_environment.py` to check imports. Optional missing readers do not prevent workflows using other scanners.

For the exact Windows/Python 3.11 dependency snapshot used during validation, install `requirements/validated-windows-py311.txt` instead of the unpinned requirement lists. It does not include MATLAB or MATLAB Engine.

### Install CODA locally

The original MATLAB algorithms are maintained in [ashleylk/CODA](https://github.com/ashleylk/CODA). They are kept outside this repository's tracked files, with their authorship preserved. On the original workstation the required files are already installed locally.

On another computer, obtain CODA from the authors or clone the upstream repository:

```bash
git clone https://github.com/ashleylk/CODA.git external/CODA
python tools/setup_coda.py --source "external/CODA/update 12-13-2023"
```

Alternatively, point `--source` at your existing `update 12-13-2023` folder. The setup tool copies only the 19 selected MATLAB files and reports any differences from the validated snapshot. It refuses to overwrite a different local file. Review the upstream terms and attribution before redistribution; this project does not assign a new licence to CODA.

## 2. Choose physical resolution and file names

Use **micrometres per pixel (MPP)** to define resolution. Folder names such as `20x` are descriptive labels. The examples in this workflow use:

- `2x`: 5 µm/pixel, used to calculate registration.
- `10x`: 1 µm/pixel.
- `20x`: 0.5 µm/pixel.
- `40x`: 0.25 µm/pixel.

These are project conventions, not universal scanner calibration. Verify the actual acquisition resolution. A request finer than the available source does not add real detail; the supported converters retain the available resolution instead of upsampling.

Keep names consistent across resolutions: `slide.01.tif`, `slide.01.ome.tif`, and `slide.01.mat` refer to the same image. Within one batch, give images unique stems: `sample.vsi` and `sample.czi` would otherwise target the same output name.

Keep scanner companion directories beside their parent files, including the VSI data directory and MRXS companion directory. Do not mix unrelated tissue series in one registration folder.

## 3. Convert and downsample

### Recommended: edit the settings in the script

Open `01_conversion_downsampling/run_conversion.py` and edit the block at the top:

```python
pth0 = r'D:\data\raw'
outpth = None
file_format = 'vsi'
folder_names = ['2x', '10x', '20x', '40x']
pixel_resolutions = [5, 1, 0.5, 0.25]
save_ome = [0, 1, 1, 1]
load_native_resolution = 1
```

Click **Run** in PyCharm without command-line arguments. Alternatively, run `python 01_conversion_downsampling/run_conversion.py` from the repository root.

`pth0` selects the input directory. `outpth = None` creates the output subfolders inside that directory; set another path to keep outputs elsewhere. For `file_format = 'other'`, `pth0` can also select a single image; with `outpth = None`, outputs go beside it.

The three lists correspond by position and must have the same length. You can request any subset or other resolutions, for example `folder_names = ['2x', '20x']`, `pixel_resolutions = [5, 0.5]`, and `save_ome = [0, 1]`. Use unique subfolder names. Each image is decoded once at the finest resolution needed, and all outputs are derived from that loaded image. A resolution of `0` requests native data even when other outputs are downsampled. Requesting a finer output may increase the memory needed for that shared image.

Choose `file_format = 'vsi'` for Olympus/Evident, `'czi'` for Zeiss, or `'other'` for the shared converter. The dedicated VSI/CZI readers accept a directory. Set `load_native_resolution = 0` to allow source-pyramid reads where supported.

### Optional command-line usage

You can also request all resolutions in one command:

```bash
python 01_conversion_downsampling/run_conversion.py --format vsi --input "D:/data/raw" --output "D:/data/processed" --folder 2x 10x 20x 40x --mpp 5 1 0.5 0.25 --save-ome 0 1 1 1
```

Command-line arguments replace the settings block for that run. Previous single-resolution commands still work.

For a mixed-format folder, selecting individual files prevents accidental duplicate-stem outputs. The shared converter also routes VSI/CZI to their dedicated readers.

Options:

- `--save-ome 0 1 1 1`: select TIFF/OME-TIFF for each folder in order.
- `--plain-tif`: plain TIFF for every output, recommended for low-resolution CODA input. Cannot be combined with `--save-ome`. Without either option, every output is pyramidal OME-TIFF.
- `--mpp 0`: retain native resolution.
- `--fast-pyramid`: allow the source pyramid where supported. The default OpenSlide/VSI/CZI route starts with native-resolution data. iSyntax uses a suitable available pyramid level regardless of this flag.

The source pyramid was generated by the scanner and may differ from nearest-neighbour downsampling of native pixels. Use the same mode consistently in quantitative comparisons. Exported OME-TIFF pyramid levels use Lanczos resampling and JPEG compression; these exports are not lossless pixel archives.

Readers retain the existing display-gamma and ICC behaviour. VSI/CZI may apply scanner display settings, and SVS/WSI TIFF may apply embedded ICC profiles. Document these choices when studying scanner colour differences.

Plain TIFF input must carry physical resolution tags; OME-TIFF may carry OME PhysicalSize metadata. Missing calibration now causes an error instead of an assumed 1 µm/pixel. Uncalibrated PNG/JPEG conversion is not supported by the main CLI.

## 4. Calculate alignment in MATLAB

In MATLAB, open `02_calculate_registration` and run:

```matlab
run_registration('D:\data\processed\2x', 0, [], 1)
```

Arguments are the image folder, IHC flag (`0` for H&E; `1` for IHC), reference-image index, and tissue-mask method (`1` or `2`). Reference index `[]` selects the middle image in MATLAB `dir` order. Inspect `dir('D:\data\processed\2x\*.tif')` before choosing a reference by index.

Omit the fourth argument, or use `[]`, to let CODA generate missing masks automatically. Explicit mask calculation writes masks to `TA`. Existing masks and registration outputs are reused; changing a parameter does not automatically invalidate earlier outputs. Use a separate working copy for a new parameter experiment.

Outputs under the low-resolution folder:

```text
TA/                                      Tissue masks
registered/                              Global-registration previews
registered/elastic registration/         Elastic-registration previews
registered/elastic registration/check/   Reduced previews
registered/elastic registration/save_warps/
    image_name.mat                       Global transform and metadata
    D/image_name.mat                     Elastic displacement field
```

There is a **directory** called `save_warps`, not one `savewraps.mat` file. The wrapper appends `tform_python` to moving-image MAT files for portable numeric loading. The original CODA code remains unchanged.

## 5. Apply registration at another resolution

Convert VSI/CZI images to calibrated TIFF/OME-TIFF first. Then:

```bash
python 03_apply_registration/run_apply_registration.py --input "D:/data/processed/20x" --warps "D:/data/processed/2x/registered/elastic registration/save_warps" --output "D:/data/processed/20x/registered_ome" --registration-mpp 5
```

Repeat with the 10x or 40x image folder. `--registration-mpp` is always the MPP of the images used to **calculate** the transforms. It remains 5 in all three examples. The scale is:

```text
scale = registration MPP / input-image MPP
```

For the example resolutions, this is 5 for 10x, 10 for 20x, and 20 for 40x. The application currently requires square pixels. Anisotropic images are rejected rather than scaled incorrectly.

Keep the elastic JPG previews one directory above `save_warps`; the Python code uses these for overlays. The revised applicator no longer opens the unused original low-resolution and global-preview images, but preserving the complete registration directory is recommended for reproducibility.

Outputs are registered OME-TIFF files and a `validation_overlay` directory. Add `--view` for interactive overlay windows. Inspect overlays and verify that all expected images were produced before downstream analysis.

## 6. Test and validate

```bash
python -m unittest discover -s tests -v
```

Optional MATLAB integration, from the repository root in MATLAB:

```matlab
addpath('tests');
validate_matlab(fullfile(pwd, 'outputs', 'validation'));
```

Then:

```bash
python tests/check_matlab_results.py outputs/validation/matlab_reference.mat
```

The automated examples do not replace validation with representative real slides. Large native reads, full displacement arrays, and high-resolution outputs can require substantial RAM. See [validation limits](VALIDATION.md).


## Timing and dataset performance reports

All supported entry points now save per-image CSV timing logs automatically. Set `scanner_name` / `scanner_manifest` in the conversion script, use `--scanner` / `--scanner-manifest` for Python application, and pass scanner metadata to MATLAB `run_registration`. The [timing guide](TIMING_GUIDE.md) explains setup, the exact read/resize/save/alignment boundaries, mean-time reports and plotting examples. CSV reports open in Excel; old images without timings remain explicitly unmeasured.
