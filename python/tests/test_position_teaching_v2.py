"""Source-backed canonical Position boundaries and Move16 wire admission."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from pathlib import Path
import re
import unittest

from golden_board import chess, constants, content
from golden_board.m2_slice_v1 import compile_slice_v1
from golden_board.position_teaching_v2 import build_position_teaching_v2

ROOT = Path(__file__).resolve().parents[2]


class PositionTeaching(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiled = compile_slice_v1(*((ROOT / p).read_bytes() for p in (
            'studies/m2/slice-v1.json', 'studies/m2/slice-v0.json',
            'conformance/content-v0.json', 'conformance/chess-v0.json',
            'reports/game-set-v0.bin', 'spec/content-v0.md',
            'spec/constants-v0.toml', 'spec/curriculum-v0.toml')))
        cls.result = build_position_teaching_v2(cls.compiled)

    def rewrite(self, required, replacements):
        view = self.compiled.required_projection if required else self.compiled.projection
        records = tuple(replace(r,payload=replacements.get(r.record_id,r.payload)) for r in view.records)
        raw = content.encode_content_v0(content.ContentAuthoringProjection(0,records))
        projected = content.projection_view(content.stream_validation(raw))
        fields = dict(required_content_bytes=raw,required_content_sha256=sha256(raw).hexdigest(),
                      required_projection=projected) if required else dict(
            content_bytes=raw,content_sha256=sha256(raw).hexdigest(),projection=projected)
        return replace(self.compiled,**fields)

    def test_exact_shape_fresh_immutable_and_unchanged_lesson(self):
        self.assertEqual(len(self.result.value),408)
        self.assertEqual(self.result.value[:2],b'\0\2')
        self.assertEqual(build_position_teaching_v2(self.compiled),self.result)
        self.assertIsNot(build_position_teaching_v2(self.compiled),self.result)
        with self.assertRaises(FrozenInstanceError):
            self.result.value = b''
        self.assertEqual(len(self.compiled.required_content_bytes),42432)
        self.assertEqual(self.compiled.required_content_sha256,
            '141168a051b44f978667f7c562070300d79368ace3fee47f5d19082de7642c17')

    def test_both_positions_are_pure67_and_match_public_replay(self):
        raw = self.result.value
        first = raw[82:149]
        self.assertEqual(first[-3:],bytes((1,15,21)))
        state = chess.replay_from_start((chess.decode_move(bytes.fromhex('31c0')),))
        self.assertEqual(first,chess.encode_position(state.position))
        owner = (ROOT / 'spec/position-teaching-v2.md').read_text()
        vector, = (block for block in re.findall(r'```text\n(.*?)\n```',owner,re.S)
                   if block.startswith('040203'))
        self.assertEqual(bytes.fromhex(vector),first)
        matrix = {r.record_id:r.payload for r in self.compiled.required_projection.records}[43]
        decoded = bytearray(67)
        for start in range(28,82,6):
            source,target,count = (int.from_bytes(raw[i:i+2],'big') for i in range(start,start+6,2))
            decoded[target:target+count] = bytes(matrix.cells[source:source+count])
        self.assertEqual(bytes(decoded),first)
        tagged,pure = raw[161:229],raw[229:296]
        self.assertEqual(tagged,b'\x01'+pure)
        self.assertEqual(pure,self.compiled.fixture_payloads[0][23:90])
        for position in (first,pure):
            self.assertEqual(chess.encode_position(chess.decode_position(position)),position)
        for wrapper in (tagged,b'\0\0'+first,first[:-1]):
            with self.assertRaises(chess.ChessReject):
                chess.decode_position(wrapper)

    def test_wire_fields_and_rejects_are_not_legal_move_admission(self):
        raw = self.result.value
        self.assertEqual(raw[296:314].hex(),'0004000a0006000400060001000300000001')
        rows = [raw[i:i+6] for i in range(316,388,6)]
        self.assertEqual([row[-1] for row in rows],[1,1,1,1,1,0,0,0,1,1,0,0])
        for row in rows:
            encoded,origin,destination,promotion,admitted = row[:2],*row[2:]
            if admitted:
                move = chess.decode_move(encoded)
                self.assertEqual((move.origin,move.destination,move.promotion),(origin,destination,promotion))
                self.assertEqual(chess.encode_move(move),encoded)
            else:
                with self.assertRaises(chess.ChessReject):
                    chess.decode_move(encoded)
        packet = self.compiled.fixture_payloads[3]
        count = int.from_bytes(packet[2:4],'big')
        prestate = chess.replay_from_start(tuple(chess.decode_move(packet[i:i+2]) for i in range(4,4+count,2)))
        with self.assertRaises(chess.ChessReject) as rejected:
            chess.apply_move(prestate,chess.decode_move(rows[0][:2]))
        self.assertEqual(rejected.exception.code,constants.CHESS_MOVE_PROMOTION_MISSING)
        chess.apply_move(prestate,chess.decode_move(rows[1][:2]))

    def test_fresh_valid_content_with_wrong_footer_or_orientation_rejects(self):
        original = {r.record_id:r.payload for r in self.compiled.required_projection.records}[43]
        for offset,value in ((260,20),(258,0),(259,14),(204,0)):
            cells = list(original.cells)
            cells[offset] = value
            candidate = self.rewrite(True,{43:replace(original,cells=tuple(cells))})
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                build_position_teaching_v2(candidate)

    def test_fresh_valid_opaque_content_does_not_hide_malformed_fixture(self):
        records = {r.record_id:r.payload for r in self.compiled.projection.records}
        original = self.compiled.fixture_payloads[0]
        mutants = []
        for offset,value in ((3,11),(21,67),(22,0),(23,3)):
            mutant = bytearray(original)
            mutant[offset] = value
            mutants.append(bytes(mutant))
        mutants.extend((original[:-1],original+b'\0'))
        for packet in mutants:
            candidate = self.rewrite(False,{
                716:replace(records[716],auxiliary=len(packet)),
                717:replace(records[717],data=tuple(packet))})
            candidate = replace(candidate,fixture_payloads=(packet,*candidate.fixture_payloads[1:]))
            with self.subTest(packet=packet.hex()), self.assertRaises(ValueError):
                build_position_teaching_v2(candidate)

    def test_types_digests_and_projection_mismatch_fail_closed(self):
        with self.assertRaises(ValueError):
            build_position_teaching_v2(None)
        for field,value in (('required_content_sha256','0'*64),
                            ('required_content_bytes',bytearray(self.compiled.required_content_bytes)),
                            ('required_projection',self.compiled.projection),
                            ('fixture_payloads',tuple(bytearray(x) for x in self.compiled.fixture_payloads))):
            with self.subTest(field=field), self.assertRaises(ValueError):
                build_position_teaching_v2(replace(self.compiled,**{field:value}))


if __name__ == '__main__':
    unittest.main()
