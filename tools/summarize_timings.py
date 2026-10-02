"""Create plotting-ready CSV reports from Python and MATLAB timing logs (stdlib only)."""
import argparse
from collections import defaultdict
import csv
from datetime import datetime
import math
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '01_conversion_downsampling'))
from pipeline_timing import FIELDS, image_id

# Edit these settings to run directly in PyCharm, or use command-line arguments.
input_folders = [r'D:\data']
output_folder = r'D:\data\timing_report'
inventory_csv = None  # Optional image,scanner CSV listing the complete dataset

SUCCESS = {'ok', 'reference'}
PIPELINES = ('conversion', 'calculate_registration', 'apply_registration')


def write_csv(path, fields, rows):
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def read_logs(inputs):
    paths = set()
    for item in inputs:
        item = Path(item)
        if not item.exists():
            raise ValueError(f'Timing input does not exist: {item}')
        if item.is_file():
            paths.add(item.resolve())
        else:
            for pipeline in PIPELINES:
                paths.update(p.resolve() for p in item.rglob(pipeline + '_*.csv'))
    records = {}
    for path in sorted(paths):
        with path.open(newline='', encoding='utf-8-sig') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != FIELDS:
                raise ValueError(f'Unexpected timing CSV columns: {path}')
            for row in reader:
                try:
                    seconds = float(row['seconds'])
                    datetime.fromisoformat(row['started_utc'].replace('Z', '+00:00'))
                    if not math.isfinite(seconds) or seconds < 0:
                        raise ValueError('invalid duration')
                except (TypeError, ValueError) as exc:
                    raise ValueError(f'Invalid timing row in {path}: {row}') from exc
                # Copied logs and overlapping input directories must not multiply measurements.
                key = tuple(row[field] for field in FIELDS)
                records[key] = row
    return list(records.values())


def observation_key(row):
    return row['run_id'], row['pipeline'], row['source']


def selected_measurements(rows, all_runs=False):
    by_observation = defaultdict(list)
    for row in rows:
        by_observation[observation_key(row)].append(row)
    totals = []
    for row in rows:
        if row['phase'] != 'image_total' or row['status'] not in SUCCESS:
            continue
        phases = by_observation[observation_key(row)]
        if any(phase['status']=='error' for phase in phases):
            continue
        if row['pipeline']=='calculate_registration' and not any(
                phase['phase']=='export_transform' and phase['status']=='ok' for phase in phases):
            continue  # Numeric export has not finished for this image.
        totals.append(row)
    if not all_runs:
        latest = {}
        for row in totals:
            # An ID is not globally unique across folders. Preserve full source paths.
            key = (row['pipeline'], row['source'], row['resolution'], row['mpp'])
            timestamp = datetime.fromisoformat(row['started_utc'].replace('Z', '+00:00'))
            if key not in latest or timestamp > latest[key][0]:
                latest[key] = (timestamp, row)
        totals = [value[1] for value in latest.values()]
    selected, image_totals = [], []
    for total in totals:
        phases = by_observation[observation_key(total)]
        corrected = dict(total)
        # Explicit masks and numeric export happen outside CODA's per-image loop.
        # Automatic masks are already inside image_total, so never add them twice.
        extra = sum(float(row['seconds']) for row in phases
                    if row['phase'] in {'mask', 'export_transform'} and row['status'] == 'ok')
        corrected['seconds'] = f"{float(total['seconds']) + extra:.6f}"
        image_totals.append(dict(corrected, measurement_type='measured'))
        for row in phases:
            if row['status'] not in SUCCESS or row['phase'] == 'batch_total':
                continue
            value = dict(corrected if row is total else row)
            value['role'] = 'reference' if total['status'] == 'reference' else 'moving_or_source'
            value['configuration'] = total['detail']
            selected.append(value)
    return selected, image_totals


SUMMARY_FIELDS = ['scope', 'scanner', 'pipeline', 'phase', 'resolution', 'mpp', 'role',
                  'measurement_type', 'n_measurements', 'n_images', 'n_runs', 'n_computers',
                  'n_configurations', 'sum_seconds', 'mean_seconds', 'mean_minutes',
                  'median_seconds', 'std_seconds', 'min_seconds', 'max_seconds']


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        for scope, scanner in [('dataset', 'ALL'), ('scanner', row['scanner'])]:
            roles = ['all', row['role']]
            for role in roles:
                key = (scope, scanner, row['pipeline'], row['phase'], row['resolution'], row['mpp'], role)
                groups[key].append(row)
    result = []
    for key, values in sorted(groups.items()):
        seconds = [float(row['seconds']) for row in values]
        row = dict(zip(SUMMARY_FIELDS[:7], key))
        row.update(measurement_type='measured', n_measurements=len(seconds),
                   n_images=len({r['source'] for r in values}),
                   n_runs=len({r['run_id'] for r in values}),
                   n_computers=len({r['computer'] for r in values}),
                   n_configurations=len({r['configuration'] for r in values}),
                   sum_seconds=sum(seconds), mean_seconds=statistics.mean(seconds),
                   mean_minutes=statistics.mean(seconds)/60,
                   median_seconds=statistics.median(seconds),
                   std_seconds=statistics.stdev(seconds) if len(seconds)>1 else '',
                   min_seconds=min(seconds), max_seconds=max(seconds))
        result.append(row)
    return result


def coverage(inventory, totals):
    with Path(inventory).open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        if not {'image', 'scanner'} <= set(reader.fieldnames or []):
            raise ValueError('Inventory requires image,scanner columns.')
        images = list(reader)
    present = {(row['image'], row['scanner'], row['pipeline']) for row in totals}
    seen, result = set(), []
    for row in images:
        key = image_id(row['image']), row['scanner'].strip()
        if not all(key) or key in seen:
            raise ValueError('Inventory needs unique image/scanner pairs and nonempty values.')
        seen.add(key)
        for pipeline in PIPELINES:
            result.append(dict(image=key[0], scanner=key[1], pipeline=pipeline,
                timing_available=int((*key, pipeline) in present),
                measurement_type='measured' if (*key, pipeline) in present else 'unmeasured'))
    return result


def build_report(inputs, output, inventory=None, all_runs=False):
    rows = read_logs(inputs)
    if not rows:
        raise ValueError('No timing measurements found.')
    selected, totals = selected_measurements(rows, all_runs)
    inventory_rows = coverage(inventory, totals) if inventory else None
    output = Path(output)
    if inventory_rows is None and (output / 'coverage.csv').exists():
        raise ValueError('Choose a fresh output folder or provide the inventory used for coverage.csv.')
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / 'all_measurements.csv', FIELDS, rows)
    write_csv(output / 'image_totals.csv', FIELDS + ['measurement_type'], totals)
    write_csv(output / 'summary.csv', SUMMARY_FIELDS, summarize(selected))
    write_csv(output / 'batch_totals.csv', FIELDS, [r for r in rows if r['phase']=='batch_total'])
    if inventory_rows is not None:
        write_csv(output / 'coverage.csv', ['image','scanner','pipeline','timing_available','measurement_type'], inventory_rows)
    print(f'Report: {output.resolve()} ({len(totals)} measured image-stage observations)')
    print('Skipped/reused/failed images excluded; no estimates created. Durations are seconds.')
    return totals


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        build_report(input_folders, output_folder, inventory_csv)
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', nargs='+', type=Path, required=True, help='Dataset folders or raw timing CSV files')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, help='Complete dataset CSV with image,scanner columns')
    parser.add_argument('--all-runs', action='store_true', help='Include repeated measured runs (default: latest successful run per source/stage/resolution)')
    args = parser.parse_args(argv)
    try:
        build_report(args.input, args.output, args.inventory, args.all_runs)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
