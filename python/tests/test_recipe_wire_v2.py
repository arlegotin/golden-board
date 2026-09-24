"""Encoding changes storage, never executable meaning or failure boundaries."""
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import unittest

from golden_board import bootstrap, recipe_wire_v1
from golden_board.m2_teaching_recipe_v2 import build_teaching_recipe_package

ROOT = Path(__file__).resolve().parents[2]


class CanonicalRecipeWire(unittest.TestCase):
    def codec(self):
        self.assertIsNotNone(importlib.util.find_spec('golden_board.recipe_wire_v2'),
                             'the bounded encoding-2 codec is not implemented')
        from golden_board import recipe_wire_v2
        return recipe_wire_v2

    def fixture(self):
        fixture = json.loads((ROOT / 'conformance/recipe-v0.json').read_bytes())
        raw = bytearray.fromhex(fixture['package_hex'])
        raw[12:14] = b'\0\10'
        return fixture, bytes(raw)

    def test_complete_package_round_trip_and_logical_resources(self):
        codec = self.codec()
        active = codec.decode_recipe_package_v2(build_teaching_recipe_package(),8)
        old = recipe_wire_v1.decode_recipe_package_v1(
            recipe_wire_v1.encode_recipe_package_v1(active.logical.encoded,8),8)
        encoded = codec.encode_recipe_package_v2(old.logical.encoded, 8)
        actual = codec.decode_recipe_package_v2(encoded, 8)
        self.assertEqual(actual.logical, old.logical)
        self.assertEqual(actual.encoded, encoded)
        self.assertEqual(codec.expand_recipe_package_v2(encoded, 8), old.logical.encoded)
        self.assertLess(len(encoded), len(old.encoded) * 0.65)
        self.assertEqual(encoded[8:14], b'\0\2\0\0\0\10')
        with self.assertRaises(bootstrap.BootstrapReject):
            recipe_wire_v1.decode_recipe_package_v1(encoded, 8)
        for profile in (1, 7, 9, True):
            with self.subTest(profile=profile), self.assertRaises(bootstrap.BootstrapReject):
                codec.decode_recipe_package_v2(encoded, profile)

    def test_every_opcode_results_failures_and_cached_view_are_preserved(self):
        codec = self.codec()
        fixture, raw = self.fixture()
        encoded = codec.encode_recipe_package_v2(raw, 8)
        package = codec.decode_recipe_package_v2(encoded, 8)
        self.assertEqual({n.opcode for r in package.logical.recipes for n in r.nodes}, set(range(1,26)))
        inputs = tuple(bytes.fromhex(value) for value in fixture['inputs_hex'])
        expected = tuple(bytes.fromhex(value) for value in fixture['expected_outputs_hex'])
        self.assertEqual(codec.evaluate_recipe_v2(package, 2, inputs), bootstrap.RecipeResult(0, expected))
        self.assertEqual(codec.evaluate_recipe_v2(package, 3, ()), bootstrap.RecipeResult(4, ()))
        forged = replace(package, logical=replace(package.logical, recipes=()))
        self.assertEqual(codec.evaluate_recipe_v2(forged, 2, inputs), bootstrap.RecipeResult(0, expected))

    def test_canonical_scalar_boundaries_and_malformed_encodings(self):
        codec = self.codec()
        for value, expected in ((0,'00'),(127,'7f'),(128,'8001'),(255,'ff01'),
                                (256,'8002'),(16384,'808001'),(65535,'ffff03'),
                                (2**32-1,'ffffffff0f'),(2**64-1,'ffffffffffffffffff01')):
            raw = bytes.fromhex(expected)
            self.assertEqual(codec._uleb(value), raw)
            self.assertEqual(codec._read_uleb(raw,0,len(raw),64), (value,len(raw)))
        for raw,bits in ((b'\x80',16),(b'\x80\0',16),(b'\x81\0',16),
                         (b'\xff\xff\x04',16),(b'\xff'*4+b'\x10',32),
                         (b'\xff'*9+b'\x02',64),(b'\x80'*10+b'\0',64)):
            with self.subTest(raw=raw,bits=bits), self.assertRaises(bootstrap.BootstrapReject):
                codec._read_uleb(raw,0,len(raw),bits)

    def test_package_lengths_boundaries_and_reserved_fields_fail_closed(self):
        codec = self.codec()
        _, raw = self.fixture()
        encoded = codec.encode_recipe_package_v2(raw,8)
        for at,value in ((8,0),(9,1),(13,7),(48,1),(20,255),(32,255)):
            damaged = bytearray(encoded); damaged[at]=value
            if bytes(damaged)==encoded:
                continue
            with self.subTest(at=at), self.assertRaises(bootstrap.BootstrapReject):
                codec.decode_recipe_package_v2(bytes(damaged),8)
        for changed in (encoded[:-1],encoded+b'\0'):
            with self.assertRaises(bootstrap.BootstrapReject):
                codec.decode_recipe_package_v2(changed,8)
        # Locate the first node without
        # relying on the codec's own parser and make its width noncanonical.
        start=64
        for _ in range(int.from_bytes(encoded[18:20],'big')):
            start+=16+int.from_bytes(encoded[start+12:start+16],'big')
        node=start+32
        for _ in range(int.from_bytes(encoded[start+4:start+6],'big')+
                       int.from_bytes(encoded[start+6:start+8],'big')):
            node+=1
            while encoded[node]&128:
                node+=1
            node+=1
        damaged=bytearray(encoded)
        self.assertLess(damaged[node+1],128)
        damaged[node+1:node+2]=bytes((damaged[node+1]|128,0))
        damaged[32:36]=len(damaged).to_bytes(4,'big')
        size=int.from_bytes(encoded[start+28:start+32],'big')
        damaged[start+28:start+32]=(size+1).to_bytes(4,'big')
        with self.assertRaises(bootstrap.BootstrapReject):
            codec.decode_recipe_package_v2(bytes(damaged),8)

    def test_node_tag_has_exact_opcode_and_type_domains(self):
        codec=self.codec()
        fixture,raw=self.fixture()
        encoded=codec.encode_recipe_package_v2(raw,8)
        start=64
        for _ in range(int.from_bytes(encoded[18:20],'big')):
            start+=16+int.from_bytes(encoded[start+12:start+16],'big')
        node=start+32
        for _ in range(int.from_bytes(encoded[start+4:start+6],'big')+
                       int.from_bytes(encoded[start+6:start+8],'big')):
            node+=1
            while encoded[node]&128:
                node+=1
            node+=1
        first=bootstrap._decode_recipe_package(raw,8,maximum_profile_version=8).recipes[0].nodes[0]
        self.assertEqual(encoded[node],(first.output_type<<5)|first.opcode)
        for tag in (0,26,31,193,225):
            damaged=bytearray(encoded);damaged[node]=tag
            with self.subTest(tag=tag),self.assertRaises(bootstrap.BootstrapReject):
                codec.decode_recipe_package_v2(bytes(damaged),8)

    def test_interface_descriptors_are_canonical_without_redundant_fields(self):
        codec=self.codec()
        _,raw=self.fixture()
        encoded=codec.encode_recipe_package_v2(raw,8)
        start=64
        for _ in range(int.from_bytes(encoded[18:20],'big')):
            start+=16+int.from_bytes(encoded[start+12:start+16],'big')
        logical=bootstrap._decode_recipe_package(raw,8,maximum_profile_version=8)
        first=logical.recipes[0].inputs[0]
        self.assertEqual(encoded[start+32],first.value_type)
        self.assertEqual(codec._read_uleb(encoded,start+33,len(encoded),32)[0],first.width)
        for kind in (4,6,7,255):
            damaged=bytearray(encoded);damaged[start+32]=kind
            with self.subTest(kind=kind),self.assertRaises(bootstrap.BootstrapReject):
                codec.decode_recipe_package_v2(bytes(damaged),8)


if __name__ == '__main__':
    unittest.main()
