# Timing measurements and dataset reports

All three stages now save wall-clock timings automatically. **CSV is the primary format**: it opens in Excel and imports directly into pandas, R, or plotting software without extra spreadsheet dependencies. Measurements are saved after each phase; every run gets a separate file so previous measurements survive reruns. Times are in **seconds**.

## 1. Identify the scanner

Set the actual scanner/model; the code does not guess it from the file extension. For a single-scanner conversion batch, edit these settings in `01_conversion_downsampling/run_conversion.py` along with your usual input path, folders and resolutions:

```python
scanner_name = 'Olympus VS200'  # Replace with the actual scanner/model
scanner_manifest = None
```

For mixed-scanner batches, make a local `scanners.csv`:

```csv
image,scanner
section_001,Olympus VS200
section_002,Zeiss Axio Scan.Z1
```

Use your real scanner names, consistently across stages. The `image` value is the source filename without its extension; `section_001.vsi`, `section_001.tif`, and `section_001.ome.tif` all match `section_001`. Names containing dots are supported. Each image ID must be unique within a manifest. If different datasets reuse image IDs, keep separate manifests and reports for those datasets. Avoid renaming images between stages.

Set `scanner_manifest = r'D:\dataset\scanners.csv'` to use this CSV. Entries override the batch scanner; unmatched images use the batch scanner, or `unknown` if none is supplied. Review `unknown` rows before comparing scanners. Use separate scanner-labelled batches when images with identical names came from different scanners.

The same CSV can be used for MATLAB calculation, Python application and report coverage. It stays local and is ignored by Git when named `scanners.csv`.

## 2. Conversion and downsampling

Run the editable conversion script as usual. CLI example:

```powershell
python 01_conversion_downsampling/run_conversion.py --format vsi --input "D:\dataset\raw" --output "D:\dataset\converted" --folder 2x 40x --mpp 5 0.25 --save-ome 0 1 --scanner "Olympus VS200"
```

The log is saved under `<conversion output>/timings/conversion_<run ID>.csv`.

Each image has:

- `read`: opening, decoding and preparing the shared image buffer. Reader-side sampling, calibration and colour handling are included. This is more than merely opening a file handle.
- `resize`: resizing the loaded image for one requested output.
- `save`: writing that output, including OME pyramids and compression when enabled.
- `resolution_total`: complete resize-and-save time for that output, identified by folder label (for example `2x` or `40x`) and actual MPP.
- `image_total`: complete time for the image, with its one shared read and every requested output.
- `batch_total`: elapsed processing time across the batch, including loop/logging overhead.

**Do not add all phase rows together.** `resolution_total` contains `resize` and `save`; `image_total` contains the shared `read` and all resolutions. The source is decoded once for all requested outputs. Thus the 2x-only cost cannot be inferred by adding the shared read from a 2x+40x run: that read was prepared for the finest requested resolution.

The requested folder names are labels. MPP records the physical resolution actually produced, including clamping when a request is finer than the source. The image-total `detail` field records the requested outputs, output formats and decoding mode.

## 3. Calculate alignment in MATLAB

Use the supported wrapper, rather than calling the original CODA function directly:

```matlab
addpath('D:\code\histology-image-pipeline\02_calculate_registration');
run_registration('D:\dataset\converted\2x', 0, [], 1, ...
    'Olympus VS200', '', 5);
```

The last three arguments are the batch scanner, optional scanner-manifest path, and actual registration MPP. For a mixed batch:

```matlab
run_registration('D:\dataset\converted\2x', 0, [], 1, ...
    'unknown', 'D:\dataset\scanners.csv', 5);
```

The log is saved under `<2x input>/timings/calculate_registration_<run ID>.csv`.

- `image_total`: the reference preparation or the moving image's CODA calculation, including its reading, preprocessing, global/elastic registration and output saving.
- `mask`: separate per-image mask preparation when `mask_style` is explicitly provided. With `mask_style=[]`, automatic mask creation is already inside CODA's image time.
- `export_transform`: loading and exporting the image's numeric transform data for Python. For the reference this only checks its MAT file.
- `batch_total`: the whole calculation, masks and numeric exports, including shared setup and image-size inspection.

The report's `image_totals.csv` adds **separate successful mask and numeric-export time** to the raw CODA `image_total`, giving the measured per-image alignment-calculation total. It never adds automatic masks twice. Shared batch setup is not arbitrarily assigned to images; use `batch_totals.csv` for the actual elapsed batch time.

The reference image is marked `reference`; a moving image with an existing transform is marked `reused`. Reused transforms are excluded from fresh-computation averages. Timers are inserted into temporary copies of the supported CODA functions; the installed originals are unchanged. An incompatible CODA revision fails explicitly if the required timing anchors differ.

## 4. Apply alignment at 40x, 20x or 10x

```powershell
python 03_apply_registration/run_apply_registration.py --input "D:\dataset\converted\40x" --warps "D:\dataset\converted\2x\registered\elastic registration\save_warps" --output "D:\dataset\registered40x" --registration-mpp 5 --scanner "Olympus VS200"
```

Alternatively supply `--scanner-manifest "D:\dataset\scanners.csv"`. Use the same original scanner identity even though the inputs are now TIFF files.

The log is saved under `<registered output>/timings/apply_registration_<run ID>.csv`. It records `read`, `apply`, `save`, `image_total` and `batch_total`. `apply` includes loading transforms, padding, warping and producing the validation overlay; `save` includes the overlay and the output image. Historical MATLAB objects may incur MATLAB Engine startup during `apply`. Use consistent transform formats for comparisons. Avoid `--view` for benchmarking, because interactive viewing can add human waiting time.

The reference is marked separately because it needs padding and export but no moving-image warp. The image total records the input folder label and actual MPP, so 10x, 20x and 40x applications can be compared separately.

## 5. Build the dataset report

You can edit `input_folders`, `output_folder` and `inventory_csv` at the top of `tools/summarize_timings.py` and click Run, or use:

```powershell
python tools/summarize_timings.py --input "D:\dataset" --output "D:\dataset\timing_report" --inventory "D:\dataset\scanners.csv"
```

You can pass multiple dataset roots after `--input`, or specific raw timing CSV files. The command recursively finds the three stages' logs. `--inventory` is optional; supply a complete list of dataset images to see which still lack measurements. Output CSVs use UTF-8 with a BOM for Excel compatibility:

- **`all_measurements.csv`**: raw phase measurements, including failed, skipped and reused work. Exact copied log rows are deduplicated.
- **`image_totals.csv`**: selected successful per-image totals, ready for distributions, box plots and image-level analysis. MATLAB totals include separate masks and export, as described above.
- **`summary.csv`**: dataset-wide and per-scanner means, medians, sample standard deviations, minima, maxima, counts and summed measured seconds, split by stage, phase, resolution and reference role. It includes `mean_minutes` as a convenience.
- **`batch_totals.csv`**: all observed batch durations and statuses. This includes shared overhead and reused work, so it is not a fresh-computation benchmark.
- **`coverage.csv`**: when an inventory is supplied, one row per image/scanner/stage identifying whether a successful timing exists. This checks stage-level coverage, not whether every planned high-resolution output exists.

By default, the report selects the **latest successful complete observation per source path, stage and resolution**. A later skipped or failed retry does not erase a previous valid measurement. Other runs stay in the raw CSV. `--all-runs` includes all successful repeated measurements; then `n_measurements` may exceed `n_images`. Incomplete image observations are excluded from averages even when an earlier subphase succeeded. A failed batch can still contribute images that finished successfully before the failure.

For plotting average total downsampling time, filter `summary.csv` to:

```text
phase = image_total
pipeline = conversion
role = all
scope = scanner       # One mean per scanner; use dataset for the overall mean
```

Plot `scanner` on the horizontal axis and `mean_seconds` (or `mean_minutes`) on the vertical axis. For alignment, use `pipeline = calculate_registration` or `pipeline = apply_registration`; keep each application MPP/resolution separate. For per-output downsampling plots, use `phase = resolution_total` and group by `resolution`. For moving-image-only alignment plots, use `role = moving_or_source`; `role = all` includes the reference-image overhead in the dataset average. These role rows overlap; do not add them together.

`std_seconds` is the sample standard deviation, not a confidence interval. It is blank with one observation. Show `n_images` alongside means. Dataset means weight each selected image equally; they are not the unweighted mean of scanner means. `sum_seconds` sums per-image/phase measurements, not the elapsed wall time of a whole dataset run.

For richer plots, import `image_totals.csv` in Python:

```python
import pandas as pd
import matplotlib.pyplot as plt

measurements = pd.read_csv(r'D:\dataset\timing_report\image_totals.csv')
conversion = measurements[measurements['pipeline'].eq('conversion')]
conversion.boxplot(column='seconds', by='scanner')
plt.ylabel('Total downsampling time per image (seconds)')
plt.suptitle('')
plt.tight_layout()
plt.show()
```

This optional example requires pandas and matplotlib; the report generator itself uses only the Python standard library.

## 6. Old images and later estimates

Existing outputs are not rerun just to populate timings. `skipped_existing` and `reused` durations describe checking/loading old results, **not** their original processing cost, and are excluded from fresh-work averages. Previously processed images with no valid timing remain `unmeasured` in coverage. All report measurements are explicitly marked `measured`; no estimates are invented.

Until coverage is complete, dataset averages refer to the **measured subset**. Later, estimates for old images should be stored separately with their method, scanner, stage, resolution and sample size, and labelled `estimated`. Keep measured and estimated values distinguishable in plots. Do not extrapolate from a mean across mixed resolutions or computers without reviewing the underlying groups.

Scanner comparisons also depend on image dimensions, tissue size, file compression, storage/network speed, native versus pyramid decoding, cache state, output settings and computer hardware. These timers measure processing elapsed time, not scanner acquisition speed. Raw logs preserve computer name, settings and timestamps; `n_computers` and `n_configurations` reveal mixed groups in summaries. Filter the raw measurements or analyze separate folders/runs when a controlled comparison is needed. Log writing adds small overhead, and completed measurements survive ordinary failures; a hard process termination can lose the phase in progress.

Timing logs contain local image names and paths. Keep raw logs and generated reports with the dataset; the standard `timings/` and `timing_report/` locations and report filenames are ignored by Git.
