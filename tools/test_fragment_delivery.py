#!/usr/bin/env python3
"""Small offline durability, interruption, integrity and safety checks."""
import contextlib
import copy
import fcntl
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import fragment_delivery as fragment


def sha(data):
    return hashlib.sha256(data).hexdigest()


class FragmentDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='shuttl-fragment-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.delivery = self.base / 'delivery'
        self.delivery.mkdir()
        self.index_path = self.delivery / 'payload-index.json'
        self.part_size = 31
        # No encryption/decryption involved: these bytes model already-encrypted
        # files, and the test independently checks byte-exact reconstruction.
        self.data = bytes(range(173))
        self.assets = [
            {'name': 'manifest.sqlite3.age', 'bytes': len(self.data), 'sha256': sha(self.data),
             'plaintext_sha256': '1' * 64, 'restore_path': 'manifest.sqlite3'},
            {'name': 'volume-000001.bin.age', 'bytes': 31, 'sha256': sha(b'x' * 31),
             'plaintext_sha256': '2' * 64, 'restore_path': 'volumes/volume-000001.bin'},
            {'name': 'Shuttl-promo-v1.mp4', 'bytes': 1024, 'sha256': sha(b'v' * 1024),
             'standalone_video': True},
        ]
        self.original = {'format': 'shuttl-delivery-v1', 'private_key_included': False,
                         'recipient': 'synthetic-test-recipient', 'archive_format': 'shuttl-preservation-v1',
                         'complete': True, 'custom_preserved': {'value': 9}, 'assets': self.assets}
        self.write_index(self.original)
        for asset, data in zip(self.assets, [self.data, b'x' * 31, b'v' * 1024]):
            (self.delivery / asset['name']).write_bytes(data)
        self.parent = self.delivery / self.assets[0]['name']

    def read_index(self):
        return json.loads(self.index_path.read_text())

    def write_index(self, index):
        self.index_path.write_bytes(fragment.json_bytes(index))

    def run_conversion(self, reclaim=False):
        with contextlib.redirect_stdout(io.StringIO()):
            return fragment.fragment_delivery(self.base, reclaim=reclaim, part_size=self.part_size)

    def check_final(self, reclaimed):
        index = self.read_index()
        self.assertTrue(index['complete'])
        self.assertEqual(index['transport'], fragment.TRANSPORT)
        self.assertEqual(index['custom_preserved'], self.original['custom_preserved'])
        for original, asset in zip(self.assets, index['assets']):
            self.assertEqual({k: v for k, v in asset.items() if k != 'parts'}, original)
        parts = index['assets'][0]['parts']
        joined = b''.join((self.delivery / part['name']).read_bytes() for part in parts)
        self.assertEqual(joined, self.data)
        self.assertEqual(sha(joined), self.assets[0]['sha256'])
        self.assertEqual([part['name'] for part in parts], [
            'manifest.sqlite3.part-' + f'{n:06d}' + '.age' for n in range(1, 7)])
        self.assertEqual([part['bytes'] for part in parts], [31, 31, 31, 31, 31, 18])
        self.assertEqual(self.parent.exists(), not reclaimed)
        expected = {part['name']: part['sha256'] for part in parts}
        expected.update({a['name']: a['sha256'] for a in self.assets[1:]})
        expected['payload-index.json'] = sha(self.index_path.read_bytes())
        actual = {}
        for line in (self.delivery / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ')
            self.assertNotIn(name, actual)
            actual[name] = digest
            self.assertEqual(sha((self.delivery / name).read_bytes()), digest)
        self.assertEqual(actual, expected)
        self.assertNotIn(self.parent.name, actual)
        self.assertNotIn('parts', index['assets'][1])
        self.assertNotIn('parts', index['assets'][2])

    def test_concatenation_metadata_checksums_and_small_video_untouched(self):
        result = self.run_conversion()
        self.assertEqual(result['transport_assets'], 8)
        self.assertEqual(result['fragmented_assets'], 1)
        self.assertEqual(result['reclaimed_parent_ciphertexts'], 0)
        self.check_final(False)

    def test_interrupted_after_durable_part_before_index_save_resumes(self):
        original_save = fragment.save_index

        def interrupt(path, index):
            if len(index['assets'][0].get('parts', [])) == 3:
                raise OSError('simulated process interruption')
            original_save(path, index)

        with mock.patch.object(fragment, 'save_index', side_effect=interrupt):
            with self.assertRaisesRegex(OSError, 'simulated'):
                self.run_conversion(reclaim=True)
        interrupted = self.read_index()
        self.assertFalse(interrupted['complete'])
        self.assertEqual(len(interrupted['assets'][0]['parts']), 2)
        self.assertTrue((self.delivery / 'manifest.sqlite3.part-000003.age').exists())
        self.assertTrue(self.parent.exists())
        self.run_conversion(reclaim=True)
        self.check_final(True)

    def test_interrupted_after_reclaim_before_checksums_resumes_without_parent(self):
        original_write = fragment.durable_bytes

        def interrupt(path, data, replace=True):
            if path.name == 'SHA256SUMS':
                raise OSError('simulated final checksum interruption')
            original_write(path, data, replace=replace)

        with mock.patch.object(fragment, 'durable_bytes', side_effect=interrupt):
            with self.assertRaisesRegex(OSError, 'simulated'):
                self.run_conversion(reclaim=True)
        self.assertFalse(self.parent.exists())
        self.assertFalse(self.read_index()['complete'])
        self.assertEqual(len(self.read_index()['assets'][0]['parts']), 6)
        self.run_conversion(reclaim=True)
        self.check_final(True)

    def test_committed_part_corruption_is_refused_even_with_good_parent(self):
        self.run_conversion()
        target = self.delivery / self.read_index()['assets'][0]['parts'][1]['name']
        target.write_bytes(b'!' * 31)
        with self.assertRaisesRegex(RuntimeError, 'mismatch'):
            self.run_conversion(reclaim=True)
        self.assertTrue(self.parent.exists())
        self.assertEqual(target.read_bytes(), b'!' * 31)
        self.assertFalse(self.read_index()['complete'])

    def test_unknown_existing_part_is_verified_and_never_overwritten(self):
        target = self.delivery / 'manifest.sqlite3.part-000001.age'
        target.write_bytes(b'?' * 31)
        with self.assertRaisesRegex(RuntimeError, 'mismatch'):
            self.run_conversion(reclaim=True)
        self.assertEqual(target.read_bytes(), b'?' * 31)
        self.assertTrue(self.parent.exists())

    def test_reclaim_occurs_only_after_complete_durable_metadata_and_stored_hash(self):
        original_unlink = Path.unlink
        original_save = fragment.save_index
        durable_full_metadata = []
        reclaimed = []

        def record_save(path, index):
            original_save(path, index)
            if len(index['assets'][0].get('parts', [])) == 6:
                durable_full_metadata.append(True)

        def record_unlink(path, *args, **kwargs):
            if path == self.parent:
                self.assertTrue(durable_full_metadata)
                disk = self.read_index()
                self.assertFalse(disk['complete'])
                self.assertEqual(len(disk['assets'][0]['parts']), 6)
                joined = b''.join((self.delivery / p['name']).read_bytes() for p in disk['assets'][0]['parts'])
                self.assertEqual(sha(joined), self.assets[0]['sha256'])
                reclaimed.append(path.name)
            return original_unlink(path, *args, **kwargs)

        with mock.patch.object(fragment, 'save_index', side_effect=record_save), mock.patch.object(Path, 'unlink', record_unlink):
            self.run_conversion(reclaim=True)
        self.assertEqual(reclaimed, [self.parent.name])
        self.check_final(True)

    def test_failed_full_metadata_write_keeps_parent(self):
        original_save = fragment.save_index

        def fail_full_metadata(path, index):
            if len(index['assets'][0].get('parts', [])) == 6:
                raise OSError('full metadata not durable')
            original_save(path, index)

        with mock.patch.object(fragment, 'save_index', side_effect=fail_full_metadata):
            with self.assertRaisesRegex(OSError, 'not durable'):
                self.run_conversion(reclaim=True)
        self.assertTrue(self.parent.exists())
        self.assertFalse(self.read_index()['complete'])
        self.assertEqual(len(self.read_index()['assets'][0]['parts']), 5)
        self.run_conversion(reclaim=True)
        self.check_final(True)

    def test_corrupt_parent_never_reclaimed(self):
        self.parent.write_bytes(b'z' * len(self.data))
        with self.assertRaisesRegex(RuntimeError, 'Original ciphertext hash'):
            self.run_conversion(reclaim=True)
        self.assertTrue(self.parent.exists())
        self.assertFalse(self.read_index()['complete'])

    def test_individual_valid_parts_with_wrong_concatenation_are_refused(self):
        self.run_conversion(reclaim=True)
        index = self.read_index()
        part = index['assets'][0]['parts'][1]
        data = b'r' * part['bytes']
        (self.delivery / part['name']).write_bytes(data)
        part['sha256'] = sha(data)
        self.write_index(index)
        with self.assertRaisesRegex(RuntimeError, 'Concatenated ciphertext hash'):
            self.run_conversion(reclaim=True)
        self.assertFalse(self.read_index()['complete'])

    def test_missing_parent_with_incomplete_metadata_is_refused(self):
        self.run_conversion(reclaim=True)
        index = self.read_index()
        index['complete'] = False
        index['assets'][0]['parts'].pop()
        self.write_index(index)
        with self.assertRaisesRegex(RuntimeError, 'incomplete parts'):
            self.run_conversion(reclaim=True)

    def test_completed_conversion_is_idempotent_after_parent_reclaimed(self):
        self.run_conversion(reclaim=True)
        first_index = self.index_path.read_bytes()
        first_sums = (self.delivery / 'SHA256SUMS').read_bytes()
        result = self.run_conversion(reclaim=True)
        self.assertEqual(result['reclaimed_parent_ciphertexts'], 0)
        self.assertEqual(first_index, self.index_path.read_bytes())
        self.assertEqual(first_sums, (self.delivery / 'SHA256SUMS').read_bytes())
        self.check_final(True)

    def test_complete_true_is_published_only_after_durable_checksums(self):
        original_write = fragment.durable_bytes
        final_writes = []

        def record_write(path, data, replace=True):
            if path == self.index_path and json.loads(data)['complete']:
                self.assertFalse(self.read_index()['complete'])
                sums = (self.delivery / 'SHA256SUMS').read_text()
                self.assertIn(sha(data) + '  payload-index.json\n', sums)
                final_writes.append(path.name)
            original_write(path, data, replace=replace)

        with mock.patch.object(fragment, 'durable_bytes', side_effect=record_write):
            self.run_conversion(reclaim=True)
        self.assertEqual(final_writes, ['payload-index.json'])

    def test_symlink_part_refused_without_touching_target(self):
        outside = self.base / 'outside'
        outside.write_bytes(self.data[:31])
        (self.delivery / 'manifest.sqlite3.part-000001.age').symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError, 'regular file'):
            self.run_conversion(reclaim=True)
        self.assertEqual(outside.read_bytes(), self.data[:31])
        self.assertTrue(self.parent.exists())

    def test_symlink_delivery_index_and_lock_are_refused(self):
        real_index = self.base / 'index-real.json'
        self.index_path.rename(real_index)
        self.index_path.symlink_to(real_index)
        with self.assertRaisesRegex(RuntimeError, 'regular file'):
            self.run_conversion()
        self.index_path.unlink()
        real_index.rename(self.index_path)
        lock = self.base / '.prepare.lock'
        lock.unlink()
        lock.symlink_to(self.index_path)
        with self.assertRaisesRegex(RuntimeError, 'regular file'):
            self.run_conversion()
        self.assertEqual(self.read_index(), self.original)

    def test_symlink_directory_refused(self):
        real_delivery = self.base / 'real-delivery'
        self.delivery.rename(real_delivery)
        self.delivery.symlink_to(real_delivery, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'real directory'):
            self.run_conversion()

    def test_both_existing_backup_locks_block_without_index_mutation(self):
        for name in ('.prepare.lock', '.upload.lock'):
            with self.subTest(lock=name):
                with (self.base / name).open('a+b') as locked:
                    fcntl.flock(locked.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    with self.assertRaisesRegex(RuntimeError, 'holds'):
                        self.run_conversion(reclaim=True)
                self.assertEqual(self.read_index(), self.original)
        # A failed second lock acquisition did not leave the first lock held.
        self.run_conversion(reclaim=True)
        self.check_final(True)

    def test_partial_file_from_interrupted_own_write_is_safely_recreated(self):
        target = self.delivery / 'manifest.sqlite3.part-000001.age'
        partial = fragment.temporary_path(target)
        partial.write_bytes(b'incomplete')
        self.run_conversion(reclaim=True)
        self.assertFalse(partial.exists())
        self.check_final(True)

    def test_part_name_collision_and_unsafe_names_rejected_before_mutation(self):
        collision = dict(self.assets[1], name='manifest.sqlite3.part-000001.age')
        for extra in (collision, dict(collision, name='../escape.age')):
            with self.subTest(name=extra['name']):
                index = copy.deepcopy(self.original)
                index['assets'].append(extra)
                self.write_index(index)
                before = self.index_path.read_bytes()
                with self.assertRaises(RuntimeError):
                    self.run_conversion(reclaim=True)
                self.assertEqual(self.index_path.read_bytes(), before)
                self.assertTrue(self.parent.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
