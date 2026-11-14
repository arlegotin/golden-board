from pathlib import Path
import hashlib,json,tempfile,unittest
from golden_board.clean_build import build_clean
from golden_board.clean_carrier import decode_serial
ROOT=Path(__file__).resolve().parents[1]

class CleanBuildTests(unittest.TestCase):
    def test_bounded_candidate_preserves_all_frozen_payload_bytes(self):
        from golden_board import bootstrap_boundaries
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            dest=Path(tmp)/'candidate'
            report=build_clean(ROOT,dest,bootstrap=bootstrap_boundaries)
            packed=(dest/'GOLDEN-BOARD.bitplane').read_bytes()
            canonical=(ROOT/'artifacts/GOLDEN-BOARD.bin').read_bytes()
            self.assertNotEqual(packed[:16384],canonical[:16384])
            self.assertEqual(packed[16384:],canonical[16384:])
            self.assertEqual(report['bootstrap_layout'],'bootstrap-field-boundaries-1')
            self.assertFalse(report['canonical_exact'])
            self.assertFalse(report['release_ready'])
            self.assertEqual((report['game_count'],report['authored_strata']),(64,146))
            self.assertIn('src/golden_board/bootstrap_boundaries.py',report['input_files'])
            recovered=decode_serial((dest/'serial.txt').read_bytes(),bootstrap=bootstrap_boundaries)
            expected=json.loads((ROOT/'artifacts/manifest.json').read_bytes())['documents']
            for ident,body in recovered['documents'].items():
                self.assertEqual(hashlib.sha256(body).hexdigest(),expected[str(ident)]['sha256'])

    def test_actual_complete_content_retains146_and64_with_exact_player_routes(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            from golden_board.piece_glyphs import REVISION, PALETTE_SHA256
            dest=Path(tmp)/'candidate';r=build_clean(ROOT,dest,piece_glyph_style=REVISION)
            # The post-transform bytes must be the identity named by EVERY
            # emitted binding, including per-product copies used for routes.
            all_bindings=json.loads((dest/'bindings.json').read_bytes())
            for rows in all_bindings.values():
                for row in rows:
                    self.assertEqual(row['document_sha256'],r['documents'][str(row['section'])]['sha256'])
            for name,section in (('generic',1),('foundation',3),('practical',4),('advanced',5)):
                for rows in json.loads((dest/f'content/{name}/bindings.json').read_bytes()).values():
                    for row in rows:self.assertEqual(row['document_sha256'],r['documents'][str(section)]['sha256'])
            self.assertEqual(r['piece_glyph_style'],REVISION)
            self.assertEqual(r['piece_glyph_palette_sha256'],PALETTE_SHA256)
            self.assertEqual(r['game_count'],64)
            self.assertEqual(r['authored_strata'],146)
            self.assertEqual(r['pending_strata'],0)
            self.assertTrue(r['full_course'] and r['full_product_fit'])
            self.assertFalse(r['release_ready'])
            self.assertEqual((r['wire_version'],r['payload_capacity_bytes']),(7,507904))
            self.assertEqual((r['stored_sections'],r['logical_sections']),(6,6))
            self.assertEqual(r['used_payload_bytes']+r['reserve_bytes'],507904)
            self.assertEqual(r['documents']['2']['bytes'],93017)
            expected={'1': '7daf1b687c18826243ae21772debb863056fa02cda285037ce20cfddac401f4a', '2': '2cfaf5ab439a840be07a52885e37af9fc04ea141877a658495ce31197d1178fd', '3': 'dbef46b9c9032161962a8434e81e327f6e3e30b824cd37b107c83d001bf7615b', '4': '7de2e936af0488a140aa60232e97378e859d529a35f744239d305d4571bb79e4', '5': '333088321041d1b23235c6e7d9ee2d52d9e5b4667fe9cb3a06226a7d4b7f8cab'}
            for ident,digest in expected.items():self.assertEqual(r['documents'][ident]['sha256'],digest)
            self.assertEqual(r['artifact_sha256'],'0116be5b721d72b8aed5f67265b290a506c818354f9f297b0618768db996b479')
            self.assertEqual(r['reserve_bytes'],1395)
            self.assertEqual(sum(r['cell_ledger'].values()),4194304)
            self.assertTrue(r['player']['foundation']['passive_without_response'])
            self.assertTrue(r['player']['practical']['passive_without_response'])
            self.assertNotEqual(r['documents']['5']['sha256'],'0ecc3d2934c710f1a4b8af1100babf11bd0653f26ce9553a922812ec4818a0e3')
            self.assertTrue(r['player']['advanced']['all_actions_exact'])
            recovered=decode_serial((dest/'serial.txt').read_bytes())
            for ident,payload in recovered['documents'].items():self.assertEqual(payload,(dest/f'documents/{ident}.bin').read_bytes())
            with self.assertRaises(ValueError):build_clean(ROOT,dest)
            again=build_clean(ROOT,Path(tmp)/'again')
            self.assertEqual(r['artifact_sha256'],again['artifact_sha256'])
            self.assertEqual((dest/'GOLDEN-BOARD.bitplane').read_bytes(),(Path(tmp)/'again/GOLDEN-BOARD.bitplane').read_bytes())

if __name__=='__main__':unittest.main()
