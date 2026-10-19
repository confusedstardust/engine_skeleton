import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from webgal_backend.pipeline import WebGALPipeline
from webgal_backend.storage import JobStore


class AutoJobSyncTests(unittest.TestCase):
    def test_auto_completion_publishes_before_done(self):
        with tempfile.TemporaryDirectory() as root:
            store = JobStore(Path(root))
            job = store.create('test')
            pipeline = WebGALPipeline(store=store)
            events = []
            with patch('webgal_backend.pipeline.validate_generation_options'), \
                 patch('webgal_backend.pipeline.RUN_ALL_PHASE_ORDER', ('validation',)), \
                 patch.object(pipeline, '_sync_auto_job_status') as sync, \
                 patch.object(pipeline, '_phase_handler', return_value=lambda job: events.append('validated')), \
                 patch.object(pipeline, '_rewrite_runtime_asset_urls', side_effect=lambda job: events.append('urls')), \
                 patch.object(pipeline, '_publish_asset_version', side_effect=lambda job: events.append(store.get(job['id'])['status'])):
                result = pipeline.run_all(job['id'])
            self.assertEqual(events, ['validated', 'urls', 'CREATED'])
            self.assertEqual(result['status'], 'DONE')
            self.assertEqual(result['build_state'], 'CURRENT')
            self.assertEqual(sync.call_count, 1)
            self.assertEqual(sync.call_args.args[0]['id'], job['id'])
            self.assertEqual(sync.call_args.args[1:], ('RUNNING', 'validation'))

    def test_publication_failure_fails_auto_job(self):
        with tempfile.TemporaryDirectory() as root:
            store = JobStore(Path(root))
            job = store.create('test')
            pipeline = WebGALPipeline(store=store)
            with patch('webgal_backend.pipeline.validate_generation_options'), \
                 patch('webgal_backend.pipeline.RUN_ALL_PHASE_ORDER', ()), \
                 patch.object(pipeline, '_sync_auto_job_status') as sync, \
                 patch.object(pipeline, '_rewrite_runtime_asset_urls'), \
                 patch.object(pipeline, '_publish_asset_version', side_effect=RuntimeError('database unavailable')):
                with self.assertRaisesRegex(RuntimeError, 'database unavailable'):
                    pipeline.run_all(job['id'])
            self.assertEqual(store.get(job['id'])['status'], 'FAILED')
            self.assertEqual(sync.call_args.args[1], 'FAILED')
