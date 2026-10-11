#!/usr/bin/env python3
"""Guard regression: legacy preparation must not erase ciphertext part maps."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import prepare_delivery


class PrepareDeliveryGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='shuttl-prepare-guard-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.delivery = self.base / 'delivery'
        self.delivery.mkdir()
        payload = bytes(range(79))
        asset = {'name': 'manifest.sqlite3.age', 'bytes': len(payload),
                 'sha256': hashlib.sha256(payload).hexdigest(),
                 'plaintext_sha256': '1' * 64, 'restore_path': 'manifest.sqlite3', 'parts': []}
        # Model an already-reclaimed parent with real byte/hash part metadata.
        for ordinal, offset in enumerate(range(0, len(payload), 31), 1):
            name = 'manifest.sqlite3.part-' + f'{ordinal:06d}' + '.age'
            data = payload[offset:offset + 31]
            (self.delivery / name).write_bytes(data)
            asset['parts'].append({'name': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        self.index = {'format': 'shuttl-delivery-v1', 'private_key_included': False,
                      'transport': 'ciphertext-parts-v1', 'complete': True,
                      'recipient': 'synthetic-test-recipient', 'assets': [asset]}
        (self.delivery / 'SHA256SUMS').write_bytes(b'existing checksum bytes must not change\n')

    def snapshot(self):
        return {str(p.relative_to(self.base)): p.read_bytes()
                for p in self.base.rglob('*') if p.is_file()}

    def assert_guard_leaves_every_byte(self, index):
        (self.delivery / 'payload-index.json').write_text(json.dumps(index, indent=2) + '\n')
        before = self.snapshot()
        # No archive or recovery identity exists: the rejection must occur before
        # either is needed, and before any encryption or persistent index write.
        with mock.patch.object(prepare_delivery.subprocess, 'check_output', side_effect=AssertionError('key access')), \
                mock.patch.object(prepare_delivery, 'durable_json', side_effect=AssertionError('index mutation')), \
                mock.patch.object(prepare_delivery, 'digest', side_effect=AssertionError('source access')):
            with self.assertRaisesRegex(RuntimeError, 'continue with fragment_delivery.py.*new base directory'):
                prepare_delivery.prepare(self.base, self.base.parent / 'nonexistent-identity', reclaim=True)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(sorted(p.name for p in self.base.iterdir()), ['delivery'])
        self.assertFalse((self.delivery / 'manifest.sqlite3.age').exists())

    def test_completed_fragmented_delivery_is_refused_without_any_byte_changes(self):
        self.assert_guard_leaves_every_byte(self.index)

    def test_transport_marker_blocks_interrupted_conversion_before_first_part(self):
        index = copy.deepcopy(self.index)
        index['complete'] = False
        index['assets'][0].pop('parts')
        self.assert_guard_leaves_every_byte(index)

    def test_parts_metadata_without_transport_marker_is_also_protected(self):
        index = copy.deepcopy(self.index)
        index.pop('transport')
        self.assert_guard_leaves_every_byte(index)

    def test_even_empty_parts_metadata_blocks_legacy_preparation(self):
        index = copy.deepcopy(self.index)
        index.pop('transport')
        index['complete'] = False
        index['assets'][0]['parts'] = []
        self.assert_guard_leaves_every_byte(index)

    def test_legacy_unsplit_index_continues_to_existing_archive_validation(self):
        index = copy.deepcopy(self.index)
        index.pop('transport')
        index['assets'][0].pop('parts')
        (self.delivery / 'payload-index.json').write_text(json.dumps(index))
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, 'Expected a generated archive directory'):
            prepare_delivery.prepare(self.base, self.base.parent / 'nonexistent-identity')
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main(verbosity=2)
