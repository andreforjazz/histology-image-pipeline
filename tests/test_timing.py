"""Timing integration checks use generated data and deterministic fake clocks."""
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'01_conversion_downsampling'), str(ROOT/'tools')]
from pipeline_timing import TimingLog, timing_settings, FIELDS
from summarize_timings import build_report, selected_measurements, summarize
import run_conversion
import numpy as np
import tifffile


def rows(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


class TimingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_nested_phases_use_wall_clock_and_keep_scanner_identity(self):
        manifest = self.folder/'scanners.csv'
        manifest.write_text('image,scanner\nslide.01.vsi,"Olympus, VS200"\n', encoding='utf-8')
        with timing_settings('fallback', manifest):
            log = TimingLog(self.folder, 'conversion')
            with patch('pipeline_timing.time.perf_counter', side_effect=[10,11,14,20]):
                with log.measure('slide.01.ome.tif'):
                    with log.measure('slide.01.ome.tif', 'read'):
                        pass
        data = rows(log.path)
        self.assertEqual([float(r['seconds']) for r in data], [3,10])
        self.assertEqual({r['scanner'] for r in data}, {'Olympus, VS200'})
        self.assertEqual({r['image'] for r in data}, {'slide.01'})

    def test_error_is_persisted_and_propagated(self):
        log = TimingLog(self.folder, 'conversion')
        with self.assertRaisesRegex(ValueError, 'broken'):
            with log.measure('bad.tif'):
                with log.measure('bad.tif', 'read'):
                    raise ValueError('broken')
        self.assertEqual([r['status'] for r in rows(log.path)], ['error','error'])
        self.assertIn('broken', rows(log.path)[-1]['detail'])

    def test_multi_resolution_timings_skips_and_summary(self):
        source = self.folder/'slide.tif'
        tifffile.imwrite(source, np.zeros((80,160,3),np.uint8),
                         resolution=(40000,40000), resolutionunit='CENTIMETER')
        output = self.folder/'converted'
        for _ in range(2):
            run_conversion.run_conversion(source, output, 'other', ['2x','40x'],
                                          [5,.25],[0,1],scanner='Synthetic scanner')
        data = [r for f in (output/'timings').glob('*.csv') for r in rows(f)]
        self.assertEqual(sum(r['phase']=='read' for r in data),1)
        self.assertEqual({r['resolution'] for r in data if r['phase']=='resolution_total'}, {'2x','40x'})
        self.assertEqual(sum(r['status']=='skipped_existing' for r in data),1)
        total = next(float(r['seconds']) for r in data if r['phase']=='image_total' and r['status']=='ok')
        parts = sum(float(r['seconds']) for r in data if r['phase'] in {'read','resolution_total'})
        self.assertGreaterEqual(total+0.000002,parts)
        report = self.folder/'report'
        inventory = self.folder/'inventory.csv'
        inventory.write_text('image,scanner\nslide,Synthetic scanner\nold,Synthetic scanner\n')
        build_report([output,output/'timings'],report,inventory)
        self.assertEqual(len(rows(report/'image_totals.csv')),1)
        summary = [r for r in rows(report/'summary.csv') if r['scope']=='dataset' and
                   r['phase']=='image_total' and r['role']=='all']
        self.assertEqual(len(summary),1)
        self.assertEqual(float(summary[0]['mean_seconds']),total)
        self.assertEqual(summary[0]['n_images'],'1')
        self.assertTrue(all(r['measurement_type']=='unmeasured' for r in rows(report/'coverage.csv') if r['image']=='old'))

    def test_latest_complete_run_wins_but_failed_retry_does_not_erase_measurement(self):
        data=[]
        for run,status,seconds in [('1','ok',10),('2','ok',20),('3','error',2),('4','skipped_existing',.1)]:
            base={k:'' for k in FIELDS}
            base.update(run_id=run, pipeline='conversion', source='a.vsi', image='a',
                        scanner='scanner', computer='pc', phase='image_total', status=status,
                        seconds=str(seconds), started_utc=f'2026-10-02T12:00:0{run}+00:00')
            data.append(base)
        selected,totals=selected_measurements(data)
        self.assertEqual([r['run_id'] for r in totals],['2'])
        selected,totals=selected_measurements(data,True)
        self.assertEqual(len(totals),2)
        summary = [r for r in summarize(selected) if r['scope']=='dataset' and r['role']=='all'][0]
        self.assertEqual(summary['mean_seconds'],15)
        self.assertEqual(summary['n_images'],1)
        self.assertEqual(summary['n_measurements'],2)

    def test_alignment_adds_external_masks_and_export_once(self):
        base={k:'' for k in FIELDS}
        base.update(run_id='r',pipeline='calculate_registration',source='b.tif',image='b',
                    scanner='S',computer='PC',status='ok',started_utc='2026-10-02T12:00:00Z')
        data=[dict(base,phase=phase,seconds=str(seconds)) for phase,seconds in
              [('image_total',10),('mask',2),('export_transform',1),('batch_total',15)]]
        selected,totals=selected_measurements(data)
        self.assertEqual(float(totals[0]['seconds']),13)
        self.assertEqual(float(next(r['seconds'] for r in selected if r['phase']=='image_total')),13)
        self.assertFalse(any(r['phase']=='batch_total' for r in selected))

    def test_incomplete_matlab_retry_keeps_previous_complete_run(self):
        base={k:'' for k in FIELDS}
        base.update(pipeline='calculate_registration',source='a.tif',image='a',
                    scanner='S',status='ok',seconds='10',phase='image_total')
        first=dict(base,run_id='1',started_utc='2026-10-02T12:00:00Z')
        later=dict(base,run_id='2',started_utc='2026-10-02T13:00:00Z')
        export=dict(first,phase='export_transform',seconds='1')
        for phases in [[first,export,later],
                       [first,export,later,dict(later,phase='export_transform',status='error')]]:
            _,totals=selected_measurements(phases)
            self.assertEqual([r['run_id'] for r in totals],['1'])
            self.assertEqual(float(totals[0]['seconds']),11)

    def test_failed_second_output_is_logged_and_excluded_from_averages(self):
        source=self.folder/'broken.tif'
        tifffile.imwrite(source,np.zeros((16,16,3),np.uint8),
                         resolution=(40000,40000),resolutionunit='CENTIMETER')
        output=self.folder/'out'
        with patch('WSI2OMEtif_All_file_types.save_ome_tif',side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError,'disk full'):
                run_conversion.run_conversion(source,output,'other',['2x','40x'],[5,.25],[0,1])
        records=rows(next((output/'timings').glob('*.csv')))
        self.assertTrue(any(r['status']=='ok' and r['resolution']=='2x' for r in records))
        self.assertEqual(next(r['status'] for r in records if r['phase']=='image_total'),'error')
        self.assertEqual(selected_measurements(records),([],[]))

    def test_invalid_manifest_is_rejected_before_creating_log(self):
        manifest=self.folder/'scanners.csv'
        manifest.write_text('image,scanner\na.tif,S1\na.vsi,S2\n')
        with timing_settings('unknown',manifest), self.assertRaisesRegex(ValueError,'unique'):
            TimingLog(self.folder,'conversion')
        self.assertFalse((self.folder/'timings').exists())


if __name__ == '__main__':
    unittest.main()
