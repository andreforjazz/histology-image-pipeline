# Histology Image Pipeline

[![Synthetic image tests](https://github.com/martaforjaz/histology-image-pipeline/actions/workflows/tests.yml/badge.svg)](https://github.com/martaforjaz/histology-image-pipeline/actions/workflows/tests.yml)

A Python and MATLAB workflow for preparing multi-scanner histology images, calculating alignment at low resolution, and applying the resulting transforms to higher-resolution images.

This project organizes a research workflow into three explicit stages, with calibrated pixel spacing, command-line entry points, synthetic regression tests, and documented dependencies. It integrates **CODA**, developed by Ashley L. Kiemen and collaborators; the CODA registration algorithm is an external dependency, not an original contribution of this repository.

## Workflow

```mermaid
flowchart LR
    A[Scanner images] --> B[Convert and downsample]
    B --> C[Low-resolution TIFF]
    B --> D[High-resolution OME-TIFF]
    C --> E[MATLAB CODA registration]
    E --> F[Global and elastic transforms]
    D --> G[Apply transforms in Python]
    F --> G
    G --> H[Registered OME-TIFF and overlays]
```

## What it does

- Converts Olympus/Evident VSI and Zeiss CZI through dedicated readers, with a shared entry point for other scanner formats.
- Generates plain TIFF or tiled, pyramidal OME-TIFF at a requested physical resolution.
- Runs CODA global and elastic registration on low-resolution images in MATLAB.
- Applies those transforms at other resolutions, using micrometres per pixel rather than relying on magnification labels.
- Exports visual registration overlays and provides tests using generated images only.

## Repository layout

```text
01_conversion_downsampling/   Scanner readers, conversion CLI, pixel-size metadata
02_calculate_registration/   MATLAB entry point; local CODA installation goes here
03_apply_registration/       Python transform application and CLI
docs/                        User guide, converter comparison, provenance, validation
requirements/                Python dependencies by stage
tests/                       Synthetic Python tests and optional MATLAB checks
tools/                       Environment check and local CODA setup
```

## Quick start

Python 3.11 is the tested interpreter. The MATLAB calculation stage was tested on Windows with MATLAB R2024a and Image Processing Toolbox.

```bash
git clone https://github.com/martaforjaz/histology-image-pipeline.git
cd histology-image-pipeline
python -m venv .venv
```

Activate the environment with `.venv\Scripts\activate` on Windows, or `source .venv/bin/activate` on macOS/Linux. Then:

```bash
python -m pip install -r requirements/conversion.txt -r requirements/registration.txt
python tools/check_environment.py
python -m unittest discover -s tests -v
```

Install the external CODA dependency before calculating new registration transforms; follow the [English user guide](docs/USER_GUIDE.md). Scanner library availability varies by operating system. The original CODA scripts use Windows path conventions, so the supported MATLAB workflow is Windows.

To generate several resolutions from each source in one run, edit the settings at the top of `01_conversion_downsampling/run_conversion.py` and click **Run** in PyCharm:

```python
pth0 = r'D:\data\raw'
outpth = None  # Save the output subfolders inside pth0
file_format = 'vsi'  # 'vsi', 'czi', or 'other'
folder_names = ['2x', '10x', '20x', '40x']
pixel_resolutions = [5, 1, 0.5, 0.25]  # Micrometres/pixel
save_ome = [0, 1, 1, 1]  # 0 = TIFF, 1 = OME-TIFF, in the same order
load_native_resolution = 1
```

The reader loads each source once at the finest resolution needed, then creates every requested output from that loaded image. You may choose any number of resolutions. Set an MPP to `0` to include native resolution. Command-line usage remains available, including multiple folders and MPP values in one command; see the guide.

## Validation status

Local checks cover TIFF/OME metadata and export, a generated CZI file read by the actual CZI backend, simulated VSI input, affine and elastic transforms, boundary filling, dotted filenames, reference-image handling, and scale factors corresponding to the example 10x/20x/40x workflow.

An optional MATLAB integration check runs CODA on generated images and compares a Python affine warp and constant-displacement warp against MATLAB outputs. See [validation results and limits](docs/VALIDATION.md). These checks do **not** establish accuracy on every scanner or on research datasets; inspect overlays for each dataset.

## Documentation

- [Step-by-step user guide](docs/USER_GUIDE.md)
- [Difference between the two WSI converters](docs/CONVERTER_COMPARISON.md)
- [Selection and change history](docs/SELECTION.md)
- [Testing and known limitations](docs/VALIDATION.md)
- [Using this repository on another computer](docs/GITHUB_WORKFLOW.md)
- [Third-party attribution](THIRD_PARTY_NOTICES.md)

No research images, patient information, network-share paths, MATLAB binaries, or Python virtual environments are included in the repository. Code and documentation are versioned; image data remains in a separately managed location.
