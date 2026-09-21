"""Preview staging must not reveal answers or silently reuse historical kits."""
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import unittest

from golden_board import canonical_manifest
from golden_board.m2_slice_v1 import compile_slice_v1
from tools.m2.package_technical_preview_v2 import participant_files, content_query, bind_recovery

ROOT=Path(__file__).resolve().parents[2]


class TechnicalPreview(unittest.TestCase):
    def test_initial_share_contains_only_neutral_work_and_bit_storage(self):
        cases=tuple(SimpleNamespace(channel=channel,observation=bytes((i,)))
                    for i,channel in enumerate(('OBS_MATRIX','OBS_MATRIX','OBS_UNITS','OBS_UNITS')))
        files=participant_files(ROOT,b'actual carrier',cases)
        initial={name:raw for name,raw in files.items() if name.startswith('recipient/01-clean/')}
        self.assertEqual(set(initial),{f'recipient/01-clean/{name}' for name in (
            'READ-ME.txt','opening.md','allowed-tools.md','storage.txt','observation.bits')})
        self.assertEqual(initial['recipient/01-clean/observation.bits'],b'actual carrier')
        text=b'\n'.join(raw.lower() for name,raw in initial.items() if not name.endswith('.bits'))
        for word in (b'square',b'sector',b'chess',b'castling',b'67-byte',b'protected unit',b'2040',b'112',b'crc',b'ecc'):
            self.assertNotIn(word,text)
        self.assertFalse(any('runner' in name or 'decoder' in name for name in files))
        for i,letter in enumerate('abcd'):
            self.assertEqual(files[f'recipient/03-heldouts/observation-{letter}.bin'],bytes((i,)))
        channels=canonical_manifest.validate_canonical_manifest(files['recipient/03-heldouts/channels.json'])
        self.assertEqual(channels,{'observations':[{'channel':channel,'file':f'observation-{letter}.bin'}
            for channel,letter in zip(('OBS_MATRIX','OBS_MATRIX','OBS_UNITS','OBS_UNITS'),'abcd',strict=True)]})

    def test_query_uses_current_typed_frames_and_game_references(self):
        compiled=compile_slice_v1(*((ROOT/p).read_bytes() for p in (
            'studies/m2/slice-v1.json','studies/m2/slice-v0.json','conformance/content-v0.json',
            'conformance/chess-v0.json','reports/game-set-v0.bin','spec/content-v0.md',
            'spec/constants-v0.toml','spec/curriculum-v0.toml')))
        request,result,position=content_query(compiled.content_bytes)
        query=canonical_manifest.validate_canonical_manifest(request)
        answer=canonical_manifest.validate_canonical_manifest(result)
        self.assertEqual(query['generic_record'],{'record_id':12})
        self.assertEqual(query['chess_transition'],{'game_ordinal':0,'ply_ordinal':0})
        self.assertEqual(answer['chess_transition']['move_hex'],'31c0')
        self.assertEqual(len(position),67)
        self.assertEqual(position[-1],21)
        self.assertEqual(answer['generic_record']['record_id'],12)
        for bad in (b'',compiled.content_bytes+b'\0',compiled.required_content_bytes):
            with self.subTest(length=len(bad)),self.assertRaises(ValueError):content_query(bad)

    def test_recovery_binding_rejects_missing_files_drift_or_extra_roles(self):
        carrier=b'wire'
        names=('all.content-v0.bin','body-100.bin','body-200.bin','decoder-resources.json',
               'decoder-result.json','knowledge-use.json','required.content-v0.bin',
               'route-0.bin','route-1.bin','route-2.bin','route-3.bin')
        files={name:name.encode() for name in names}
        doc={'schema':'golden-board.m2-knowledge-recovery-development/v2',
             'scope':'local-observation-recovery-and-finite-knowledge-evidence-only',
             'carrier_bytes':len(carrier),'carrier_sha256':sha256(carrier).hexdigest(),
             'files':[{'path':name,'bytes':len(files[name]),'sha256':sha256(files[name]).hexdigest()}
                      for name in sorted(files)]}
        files['recovery-provenance.json']=canonical_manifest.serialize_manifest(doc)
        bind_recovery(carrier,files)
        for changed in (files|{'body-100.bin':b'changed'},files|{'unowned':b'x'},
                        {k:v for k,v in files.items() if k!='knowledge-use.json'}):
            with self.assertRaises(ValueError):bind_recovery(carrier,changed)
        with self.assertRaises(ValueError):bind_recovery(carrier+b'x',files)


if __name__=='__main__':unittest.main()
