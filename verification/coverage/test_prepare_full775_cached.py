import unittest
from pathlib import Path
from unittest.mock import patch

import prepare_full775_cached as p


class CachedPrepareTests(unittest.TestCase):
    def test_different_complete_text_not_reused(self):
        calls = []
        def parser(text):
            calls.append(text)
            return {('scope', text)}
        cache = p.ExactOwnersCache(parser)
        self.assertNotEqual(cache('a'), cache('a\n'))
        self.assertEqual(cache('a'), {('scope', 'a')})
        self.assertEqual(calls, ['a', 'a\n'])
        self.assertEqual(cache.hits, 1)

    def test_caller_cannot_modify_saved_result(self):
        cache = p.ExactOwnersCache(lambda text: {('s', 'x')})
        cache('text').clear()
        self.assertEqual(cache('text'), {('s', 'x')})

    def test_real_old_el_original_and_cached_equal(self):
        text = (p.original.PREP773 / 'combined.el').read_text()
        expected = p.original.owners(text)
        cache = p.ExactOwnersCache(p.original.owners)
        self.assertEqual(cache(text), expected)
        self.assertEqual(cache((' ' + text)[1:]), expected)
        self.assertEqual(cache.evidence()['successful_parses'], 1)
        self.assertEqual(cache.hits, 1)

    def test_real_parser_failure_not_cached(self):
        cache = p.ExactOwnersCache(p.original.owners)
        for _ in range(2):
            with self.assertRaises(ValueError):
                cache('CHECKSUM: "1"\nINSTANCE: s\nUnknown directive\n')
        self.assertEqual(cache.values, {})
        self.assertEqual(cache.failures, 2)

    def test_bad_return_not_cached(self):
        cache = p.ExactOwnersCache(lambda text: [('s', 'x')])
        with self.assertRaises(ValueError):
            cache('text')
        self.assertEqual(cache.values, {})

    def test_full_text_key_even_if_receipt_digest_collides(self):
        cache = p.ExactOwnersCache(lambda text: {('s', text)})
        with patch.object(p.hashlib, 'sha256') as digest:
            digest.return_value.hexdigest.return_value = 'same'
            self.assertNotEqual(cache('left'), cache('right'))
            self.assertEqual(len(cache.evidence()['entries']), 2)

    def test_clone_private_globals_and_original_entry(self):
        cache = p.ExactOwnersCache(p.original.owners)
        clone = p.clone_prepare(cache, p.original.life)
        self.assertIs(clone.__code__, p.original.prepare.__code__)
        self.assertIs(clone.__globals__['owners'], cache)
        self.assertIs(p.original.prepare.__globals__['owners'], p.original.owners)
        self.assertEqual(clone.__globals__['__file__'], p.original.__file__)
        self.assertIs(clone.__globals__['records'], p.original.records)

    def test_first_save_pins_and_conflicts_fail(self):
        class Backend:
            def __init__(self): self.saved = []
            def check(self, pins): self.checked = dict(pins)
            def save(self, path, data): self.saved.append((path, data))
        backend = Backend()
        proxy = p.PinnedSave(backend, {'helper': 'sha'}, Path('/out'))
        with self.assertRaises(ValueError):
            proxy.save(Path('/out/config.json'), {'pins': {'helper': 'bad'}})
        self.assertFalse(proxy.saved)
        proxy.save(Path('/out/config.json'), {'pins': {'old': 'oldsha'}, 'successor_entry': 'original'})
        self.assertEqual(backend.saved[0][1]['pins'], {'old': 'oldsha', 'helper': 'sha'})
        self.assertEqual(backend.saved[0][1]['successor_entry'], 'original')
        with self.assertRaises(ValueError):
            proxy.save(Path('/out/config.json'), {'pins': {}})


if __name__ == '__main__':
    unittest.main()
