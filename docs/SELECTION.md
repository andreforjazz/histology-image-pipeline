# Code selection and changes

## Included workflow

- `vsi2ometif.py`: Olympus/Evident VSI reader and export.
- `CZI2OMEtif.py`: Zeiss CZI reader and export.
- `WSI2OMEtif_All_file_types.py`: shared routing for other scanners and calibrated TIFF.
- `apply_registration_to_20x_image.py`: application of CODA transforms at any supported calibrated resolution; historical name retained for continuity.
- `run_conversion.py`, `run_registration.m`, `run_apply_registration.py`: explicit entry points without workstation-specific data paths.
- `image_metadata.py`: physical pixel spacing from OME metadata or TIFF calibration tags.
- Tools, tests, and documentation needed to reproduce the workflow.

The locally installed CODA dependency contains `calculate_image_registration.m`, `calculate_tissue_ws.m`, and 17 transitively required helpers. MATLAB's dependency analysis identified MATLAB and Image Processing Toolbox. The dependency manifest records the original SHA-256 values. CODA is external to the published repository; its algorithms and authorship are not relabelled.

## Excluded from the published workflow

The original projects remain untouched. Alternative `WSI2OMEtif.py` and `WSI2OMEtif_v1.py` versions overlap with the selected conversion workflow. `WSI2OME_dicom.py` only inspects metadata. Embedding extraction, UMAP, colour-analysis scripts, and segmentation previews belong to separate analyses. Virtual environments, IDE settings, caches, images, and transformation data do not belong in the code repository.

CODA cell detection, segmentation training, and volume reconstruction are outside scope. Its MATLAB downsampling and image-application entry points are not required by the selected Python stages. `calculate_global_reg_IHC.m`, `invert_D.m`, and `im2mat.p` are not dependencies of this calculation path; the selected `calculate_global_reg` receives the IHC flag directly.

## Changes made during functional validation

The initial organization preserved code byte-for-byte. The GitHub preparation then made targeted fixes, so current files are **adapted versions**, not identical copies. `original_sha256` values identify the starting snapshots only.

- Removed workstation data paths and the fixed MATLAB DLL path; imported Engine only for historical object-based transforms.
- Added numeric affine export after CODA calculation, so new transforms can be applied without starting MATLAB.
- Read physical TIFF/OME calibration and fail clearly when it is absent; preserve calibration in plain TIFF exports.
- Select padding metadata from a MAT file that actually contains `szz` and `padall`.
- Include the reference image even when it has no displacement MAT file.
- Preserve dots within image names and remove only recognized image suffixes.
- Correct MATLAB's one-based affine pixel-centre convention and match its outside-image fill in the tested fixture.
- Use explicit tiled nearest-neighbour array sampling to avoid empty source regions and OpenCV source-dimension limits.
- Use RGB-to-grey conversion for validation overlays.
- Route VSI/CZI through the dedicated readers, honour native/pyramid mode in OpenSlide branches, and handle native output requests when combined with downsampled requests.
- Reject invalid resolution lists and propagate image-read errors to the command-line exit status.

No source file in the original PythonProject2 or the network CODA installation was edited.
