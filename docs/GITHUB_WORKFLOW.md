# Working across computers and presenting the project

## Start on another computer

```bash
git clone https://github.com/martaforjaz/histology-image-pipeline.git
cd histology-image-pipeline
```

Follow the user guide to create a local Python environment and install CODA where needed. Git synchronizes source code and documentation. It does not synchronize the ignored image data, virtual environment, installed MATLAB, or local CODA directory.

Before editing an existing clone:

```bash
git pull --ff-only
```

After making changes:

```bash
python -m unittest discover -s tests -v
git status
git add <the-files-you-changed>
git commit -m "Describe the specific change"
git push
```

Use GitHub Desktop instead of terminal Git commands if preferred. Keep data paths local and avoid embedding network locations or credentials in scripts.

## Portfolio presentation

The repository's README describes the problem, workflow, technical components, tests, and limitations. It distinguishes the image-preparation and integration work from the external CODA algorithm. This is more informative to reviewers than an unstructured collection of scripts or a claim of universal scanner support.

You can link this repository from a CV or application and pin it on your GitHub profile. A concise description is:

> Python/MATLAB workflow for multi-scanner histology image preparation and resolution-aware registration, integrating CODA with synthetic regression tests and reproducible command-line tools.

Keep future thesis analyses in separate repositories when they are independently useful, with their own setup steps and validation results. No other projects or profile settings are changed by this repository.
