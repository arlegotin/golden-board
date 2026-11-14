"""Current grammar: one checked copy per complete section, exact direct byte mapping."""
import struct,unittest
from golden_board import clean_carrier as c
from golden_board.checksum import crc32c
from golden_board.document import encode_document

def miniature():return c.raw.miniature()

class DirectStreamTests(unittest.TestCase):
    def assemble(self,sections,*,extra=b''):
        stream=b''.join(sections)+extra;route=c.raw.make_route(len(stream),*c._mini())
        symbols=bytearray(c.SIDE*c.SIDE)
        for y in range(c.raw.HEIGHT):symbols[y*c.SIDE:y*c.SIDE+c.raw.WIDTH]=route[y*c.raw.WIDTH:(y+1)*c.raw.WIDTH]
        start=c.START*c.SIDE;symbols[start:start+len(stream)*8]=c.unpack_bits(stream)
        return bytes(symbols)

    def test_literal_checked_envelope_and_bounded_length(self):
        section=c.encode_section(7,1,b'abc')
        self.assertEqual(section[:9].hex(),'000700000003616263')
        self.assertEqual(len(section),13)
        self.assertEqual(c.decode_section(section)['payload'],b'abc')
        body=struct.pack('>HI',7,0xffffffff)+b'abc';body+=crc32c(body).to_bytes(4,'big')
        with self.assertRaises(ValueError):c.decode_section(body)

    def test_direct_midrow_sections_exact_ledger_and_one_placement(self):
        docs={1:miniature()};symbols,layout=c.make_carrier(docs);packed=c.pack_bits(symbols)
        inventory=c.encode_section(0,0,c.inventory_for(docs));document=c.encode_section(1,1,docs[1])
        self.assertEqual(layout['wire_version'],8)
        self.assertEqual((layout['stored_sections'],layout['logical_sections']),(2,2))
        self.assertEqual(layout['used_payload_bytes'],364);self.assertEqual(layout['payload_capacity_bytes'],507904)
        self.assertEqual(packed[16384:16384+364],inventory+document)
        self.assertEqual([layout['sections'][str(i)]['byte_offset'] for i in (0,1)],[0,28])
        self.assertEqual(c.payload_cell(255,7),64*2048+2047)
        self.assertEqual(c.payload_cell(256,0),65*2048)
        self.assertEqual(c.payload_cell(369,7),65*2048+911)
        self.assertEqual(c.payload_cell(507903,7),4194303)
        with self.assertRaises(ValueError):c.payload_cell(507904,0)
        self.assertEqual(sum(layout['cell_ledger'].values()),4194304)
        self.assertEqual(layout['cell_ledger']['discovery_calibration'],131072)
        self.assertEqual(layout['cell_ledger']['integrity_framing'],2*10*8)
        self.assertEqual(c.decode_symbols(symbols)['documents'],docs)

    def test_all16_clean_transforms_and_serial(self):
        docs={1:miniature()};symbols,_=c.make_carrier(docs)
        for turn in range(4):
            for mirror in (False,True):
                for inverse in (False,True):
                    r=c.decode_symbols(c.transform(symbols,turn,mirror,inverse))
                    self.assertEqual(r['documents'],docs);self.assertEqual(r['valid_orientations'],1)
        serial=symbols.translate(bytes.maketrans(b'\0\1',b'01'))
        self.assertEqual(c.decode_serial(serial)['documents'],docs)
        self.assertEqual(c.decode_serial(serial+b'\n')['documents'],docs)
        for bad in (serial[:-1],serial+b'\n\n',b'?'+serial[1:],b' '+serial):
            with self.assertRaises(ValueError):c.decode_serial(bad)

    def test_section_set_order_count_and_extra_used_bytes_reject(self):
        body=miniature();docs={1:body,2:body};inv=c.encode_section(0,0,c.inventory_for(docs))
        a=c.encode_section(1,1,body);b=c.encode_section(2,1,body);extra=c.encode_section(3,1,body)
        for sections,tail in (([inv,a],b''),([inv,b,a],b''),([inv,a,a,b],b''),([inv,a,b,extra],b''),([inv,a,b],b'\0')):
            with self.assertRaises(ValueError):c.decode_symbols(self.assemble(sections,extra=tail))

    def test_bad_checks_oversized_lengths_identity_and_reserve_reject(self):
        docs={1:miniature()};symbols,layout=c.make_carrier(docs)
        for where in (c.START*c.SIDE+90,c.START*c.SIDE+layout['used_payload_bytes']*8,1024):
            bad=bytearray(symbols);bad[where]^=1
            with self.assertRaises(ValueError):c.decode_symbols(bytes(bad))
        for length in (0xffffffff,507905):
            header=struct.pack('>HI',0,length);section=header+crc32c(header).to_bytes(4,'big')
            with self.assertRaisesRegex(ValueError,'length'):c.decode_symbols(self.assemble([section]))
        section=bytearray(c.encode_section(0,0,c.inventory_for(docs)));section[1]=1;section[-4:]=crc32c(section[:-4]).to_bytes(4,'big')
        with self.assertRaises(ValueError):c.decode_symbols(self.assemble([bytes(section),c.encode_section(1,1,docs[1])]))

    def test_valid_checks_do_not_qualify_bad_roots_lengths_or_references(self):
        body=miniature();inventory=c.inventory_for({1:body});doc=c.encode_section(1,1,body)
        for index in (7,11,15):
            bad=bytearray(inventory);bad[index]^=1
            with self.assertRaises(ValueError):c.decode_symbols(self.assemble([c.encode_section(0,0,bytes(bad)),doc]))
        bad=body[:-2]+b'\x12\x34';doc=c.encode_section(1,1,bad)
        inv=b'\0\1'+struct.pack('>HIIH',1,len(bad),int.from_bytes(doc[-4:],'big'),2)+b'\2\0\1\1'
        with self.assertRaises(ValueError):c.decode_symbols(self.assemble([c.encode_section(0,0,inv),doc]))

    def test_raw_teaching_keeps_complete_miniature_and_new_mapping(self):
        mini,inventory,payload=c._mini();route=c.raw.make_route(364,mini,inventory,payload);d=c.raw.d
        self.assertEqual(c.raw.parameters(route),364)
        p=d.panel(route,28,columns=32)
        self.assertEqual(c.pack_bits(p[12*64:12*64+len(mini)*8]),mini)
        p=d.panel(route,19,columns=32)
        self.assertEqual(c.pack_bits(p[31*64:31*64+len(inventory)*8]),inventory)
        p=d.panel(route,15,columns=32)
        self.assertEqual((d._read_number(p,9,38,16),d._read_number(p,39,38,16)),(65,0))
        self.assertEqual((d._read_number(p,9,52,16),d._read_number(p,39,52,16)),(2047,2047))
        p=d.panel(route,18,columns=32)
        self.assertEqual(d._read_number(p,21,8,16),1);self.assertEqual(d._read_number(p,21,15,32),326)
        self.assertEqual([d._read_number(p,x,33,16) for x in (8,24,40)],[0,332,332])
        with self.assertRaises(ValueError):c.raw.make_route(507905,mini,inventory,payload)

    def test_actual_large_inert_fixture_uses_reclaimed_framing_space(self):
        records=[{'kind':1,'id':0,'rows':1,'cols':1,'mask':[0]}]
        for i in range(7):records.append({'kind':2,'id':256+i,'rows':255,'cols':255,'cells':[0]*65025,'regions':[]})
        records += [{'kind':2,'id':263,'rows':220,'cols':220,'cells':[0]*48400,'regions':[]},
                    {'kind':3,'id':264,'initial':256,'data':[],'steps':[]}]
        docs={1:encode_document([264],records)};symbols,layout=c.make_carrier(docs)
        self.assertGreater(layout['used_payload_bytes'],1984*241)
        self.assertLessEqual(layout['used_payload_bytes'],507904)
        self.assertEqual(c.decode_symbols(symbols)['documents'],docs)

if __name__=='__main__':unittest.main()
