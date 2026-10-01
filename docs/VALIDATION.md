# Validation

Validation performed on 1 October 2026. Tests use synthetic data; no research images or patient data are included.

## Completed locally

All 18 Python tests passed in a newly created, isolated environment. Dependency imports and `pip check` passed. Exact installed versions are recorded in `requirements/validated-windows-py311.txt`.

- Python regression tests: TIFF calibration; missing-calibration rejection; OME metadata, pyramid structure and pixel round trip; calibrated downsampling; no upsampling; affine identity, translation, flip and rotation centre; elastic identity, translation and outside fill; padding; dotted names; reference-first MAT metadata; reference inclusion without a D file; failed-read exit status; scale factors 5, 10 and 20.
- An actual CZI file generated with pylibCZIrw was decoded and downsampled with the dedicated CZI reader, including a negative stage origin and BGR-to-RGB conversion.
- VSI native downsampling was tested with a simulated SlideIO scene. This is an adapter test, not validation of a real VSI decoder or scanner file.
- MATLAB R2024a with Image Processing Toolbox ran the full selected CODA calculation on two generated tissue-like images and exported the numeric affine matrix.
- Python applied the resulting real CODA output files and wrote registered OME-TIFFs and overlays.
- A 17-degree affine rotation with translation and a constant elastic displacement matched MATLAB's generated reference images exactly in the tested fixtures.

The tests are reproducible using `tests/test_pipeline.py`, `tests/validate_matlab.m`, and `tests/check_matlab_results.py`. GitHub Actions runs the Python suite on Windows and Linux; MATLAB execution remains a separate licensed integration check.

## What remains unverified

- Real VSI slides and representative large files from every scanner backend, including SVS/NDPI, MRXS, Ventana, DICOM and iSyntax.
- Registration quality for real tissue, folds, tears, staining differences, or IHC; the synthetic integration case is deliberately simple.
- Exact MATLAB parity for arbitrary spatially varying displacement fields. Python retains linear field resizing from the original applicator, whereas CODA's MATLAB path uses its default `imresize` interpolation. Constant fields and the tested affine case are verified; this is not a claim of complete numerical equivalence.
- General MATLAB object graphs in v7.3/HDF5 files; the fallback targets numeric arrays used by this workflow. Historical affine objects may still require MATLAB Engine.
- Peak memory and performance on gigapixel slides. The pipeline retains full output images and displacement arrays in RAM; tiled sampling does not make the whole workflow out-of-core.
- Scientific equivalence of JPEG-compressed OME outputs to lossless source pixels, or of source-pyramid sampling to native nearest-neighbour sampling.

The application rejects anisotropic input pixel spacing. Inspect calibration, output dimensions, image counts, and overlays for each real dataset. Existing output files are reused; use a fresh output folder after changing parameters.

## Original local environment

The first local functional run used Python 3.11 with NumPy 1.26.4, Pillow 12.3.0, tifffile 2022.8.12, imagecodecs 2026.1.14, OpenCV 5.0.0.93, SciPy 1.15.3, OpenSlide Python 1.4.6, SlideIO 2.9.0 and pylibCZIrw 6.1.0. These are an environment record, not a cross-platform dependency lock. MATLAB was R2024a. The published requirements are checked separately by CI.
