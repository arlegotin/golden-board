"""Assemble all authored clean content; fit/evidence/release remain distinct."""
from copy import deepcopy
import hashlib,json,subprocess,tomllib
from pathlib import Path

from .clean_carrier import make_carrier,pack_bits,unpack_bits,decode_symbols,decode_serial,encode_section,inventory_for,VERSION,CAPACITY_BYTES,START,SIDE
from .course_generic import build_generic
from .course_foundation import build_foundation
from .course_practical import build_practical
from .course_advanced import build_advanced
from .anthology_input import load_anthology
from .document import decode_document
from .message_cleanup import clean_document
from .qualified_inputs import HISTORICAL_CODECS,presentation_source
from .raster import write_binary_png
from .piece_glyphs import apply_piece_glyphs,REVISION as PIECE_STYLE,PALETTE_SHA256
from . import direct_bootstrap


def sha(data):return hashlib.sha256(data).hexdigest()
def write_json(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')


def _audit(root,tool,request,destination):
    run=subprocess.run(['node',str(root/'tools'/tool)],input=json.dumps(request),capture_output=True,text=True)
    destination.with_suffix('.stdout.txt').write_text(run.stdout);destination.with_suffix('.stderr.txt').write_text(run.stderr)
    if run.returncode:raise ValueError('Actual generic Player audit failed: '+tool)
    return json.loads(run.stdout)


def build_clean(root:Path,destination:Path,*,piece_glyph_style=PIECE_STYLE,bootstrap=direct_bootstrap):
    if piece_glyph_style not in (None,PIECE_STYLE):
        raise ValueError('Unknown piece glyph style.')
    root,destination=root.resolve(),destination.resolve()
    if destination.exists():raise ValueError('Choose a fresh clean candidate destination; existing evidence is preserved.')
    destination.mkdir(parents=True)
    try:
        generic=build_generic();foundation=build_foundation(root);practical=build_practical(root);advanced=build_advanced(root)
        _,anthology=load_anthology(root)
        anthology_fingerprint=hashlib.sha256(anthology).digest()
        if piece_glyph_style is not None:
            for product in (generic,foundation,practical,advanced):
                product['document']=apply_piece_glyphs(product['document'])
            anthology=apply_piece_glyphs(anthology)
        cleanup={}
        for name,product in (('generic',generic),('foundation',foundation),('practical',practical),('advanced',advanced)):
            product['document'],cleanup[name]=clean_document(product['document'],advanced=name=='advanced',fingerprint=anthology_fingerprint)
            for rows in product['bindings'].values():
                for row in rows:row['document_sha256']=sha(product['document'])
        anthology,cleanup['anthology']=clean_document(anthology)
        write_json(destination/'message-cleanup.json',cleanup)
        coverage=tomllib.loads((root/'content/coverage.toml').read_text());families=coverage['family']
        expected={s for f in families for s in f['critical_strata']}
        products=(generic,foundation,practical,advanced);sets=[set(p['bindings']) for p in products]
        if sum(map(len,sets))!=len(set.union(*sets)) or set.union(*sets)!=expected:
            raise ValueError('Current authored bindings do not match the retained coverage inventory.')
        documents={1:generic['document'],2:anthology,3:foundation['document'],4:practical['document'],5:advanced['document']}
        # Lean loader verifies exact qualified source/presentation identities.
        if len(decode_document(documents[2])['entries'])!=64:raise ValueError('Every selected complete game is required.')
        (destination/'documents').mkdir();(destination/'content').mkdir()
        for i,data in documents.items():(destination/f'documents/{i}.bin').write_bytes(data)
        for name,product in (('generic',generic),('foundation',foundation),('practical',practical),('advanced',advanced)):
            folder=destination/'content'/name;folder.mkdir()
            (folder/'document.bin').write_bytes(product['document'])
            for field in ('groups','cases','bindings','truth'):write_json(folder/(field+'.json'),product[field])
        cases=generic['cases']+foundation['cases']
        player={'foundation':_audit(root,'audit-course.mjs',{'documents':{str(i):documents[i].hex() for i in (1,3)},'cases':cases},destination/'player-foundation'),
            'practical':_audit(root,'audit-course.mjs',{'documents':{'4':documents[4].hex()},'cases':practical['cases']},destination/'player-practical'),
            'advanced':_audit(root,'audit-course.mjs',{'documents':{'5':documents[5].hex()},'cases':advanced['cases']},destination/'player-advanced')}
        sections={0:encode_section(0,0,inventory_for(documents)),**{i:encode_section(i,1,b) for i,b in documents.items()}}
        required_bytes=sum(map(len,sections.values()));cursor=0;section_ledger={}
        for i,s in sections.items():
            section_ledger[str(i)]={'byte_offset':cursor,'bytes':len(s),'framing_bytes':10,'padding_bytes':0};cursor+=len(s)
        write_json(destination/'content-ledger.json',{'scope':'Actual complete146-stratum content, not recipient/release qualification.',
            'documents':{str(i):{'bytes':len(b),'sha256':sha(b)} for i,b in documents.items()},
            'total_document_bytes':sum(map(len,documents.values())),'sections':section_ledger,
            'required_payload_bytes':required_bytes,'payload_capacity_bytes':CAPACITY_BYTES,'fit':required_bytes<=CAPACITY_BYTES,
            'required_cells':SIDE*START+required_bytes*8,'available_cells':SIDE*SIDE,
            'excess_cells':max(0,required_bytes-CAPACITY_BYTES)*8,'game_count':64,'authored_strata':len(expected)})
        symbols,layout=make_carrier(documents,bootstrap=bootstrap);artifact=pack_bits(symbols)
        serial=symbols.translate(bytes.maketrans(b'\0\1',b'01'))+b'\n'
        (destination/'GOLDEN-BOARD.bitplane').write_bytes(artifact);(destination/'serial.txt').write_bytes(serial)
        write_binary_png(destination/'GOLDEN-BOARD.png',SIDE,SIDE,unpack_bits(artifact))
        write_json(destination/'layout.json',layout)
        for condition,result in (('physical',decode_symbols(symbols,bootstrap=bootstrap)),
                                 ('serial',decode_serial(serial,bootstrap=bootstrap))):
            if result['documents']!=documents:raise ValueError('Connected '+condition+' bytes differ.')
        digest=sha(artifact);bindings={}
        for product,section in ((generic,1),(foundation,3),(practical,4),(advanced,5)):
            case_map={c['id']:c for c in product['cases']}
            for stratum,rows in product['bindings'].items():
                for row in rows:
                    bound=deepcopy(row);case=case_map[row['case']];query=next((q for q in case['queries'] if q['id']==row['query']),None)
                    if query:
                        for key in ('worked_steps','contrast_steps','practice_steps','passive_steps'):bound[key]=query[key]
                    else:
                        for role in ('worked','contrast','practice','passive'):bound[role+'_steps']=[0,len(case['frames'][str(case[role])])-1]
                    bound.update(section=section,candidate_sha256=digest,state='carried_developmental',recipient_demonstrated=False)
                    bindings.setdefault(stratum,[]).append(bound)
        write_json(destination/'bindings.json',bindings)
        pending=sum(len(f['critical_strata']) for f in families)-len(bindings)
        active=['clean_build','clean_carrier','direct_bootstrap','bootstrap_clarity','raw_draw','checksum','document','course_author','course_generic','course_foundation','course_practical','practical_cases','practical_state','course_advanced','advanced_cases','advanced_state','advanced_fixtures','history_segments','anthology_input','move_packing','course_move_packing','rehearsal_predicates','anthology_playback','authoring','rules','source','source_game','raster','piece_glyphs','message_cleanup','qualified_inputs','anthology','shared_anthology']
        paths=[root/'src/golden_board'/f'{n}.py' for n in active]+[root/'mechanism/player.mjs',root/'tools/audit-course.mjs',root/'content/coverage.toml',root/'inputs/lock.json',root/'inputs/dependencies/lock.json']
        if bootstrap is not direct_bootstrap:
            paths.append(root/'src/golden_board'/f'{bootstrap.__name__.rsplit(".",1)[-1]}.py')
        paths.append(root/'artifacts/manifest.json')
        paths += [presentation_source(root,name) for name in HISTORICAL_CODECS]
        paths += [root/'inputs/qualified/manifest.json']
        paths += [root/name for name in ('inputs/anthology.pgn','tests/reference-anthology.mjs',
            'evidence/S03-selective-carrier/actual-rehearsal/documents/3.bin',
            'evidence/S03-shared-anthology/actual-document.bin','evidence/S03-shared-anthology/actual-summary.json',
            'evidence/S04-rules/actual-source.json.gz')]
        report={'scope':'All146 authored T0–T16strata and all64 complete games assembled; native authorship/fit, not recipient or release qualification.',
            'wire_version':VERSION,'bootstrap_layout':layout['bootstrap_layout'],'side':2048,'artifact_bytes':len(artifact),'artifact_sha256':digest,'serial_sha256':sha(serial),
            'documents':{str(i):{'bytes':len(b),'sha256':sha(b),'entries':decode_document(b)['entries']} for i,b in documents.items()},
            'game_count':64,'authored_strata':len(bindings),'pending_strata':pending,'required_strata':pending+len(bindings),
            'full_course':pending==0,'full_product_fit':pending==0,'release_ready':False,'recovery':'unsupported',
            'logical_sections':layout['logical_sections'],'stored_sections':layout['stored_sections'],
            'payload_capacity_bytes':CAPACITY_BYTES,'used_payload_bytes':layout['used_payload_bytes'],
            'reserve_bytes':layout['reserve_bytes'],'cell_ledger':layout['cell_ledger'],'unfinished_content_estimate':None,
            'message_cleanup':cleanup,
            'canonical_exact':digest==json.loads((root/'artifacts/manifest.json').read_bytes())['forms']['bin']['sha256'],
            'serial_exact':True,'player':player,
            'piece_glyph_style':piece_glyph_style or 'baseline',
            'piece_glyph_palette_sha256':PALETTE_SHA256 if piece_glyph_style is not None else None,
            'inherited_evidence':{'anthology':'evidence/S03-shared-anthology/actual-summary.json','source':'evidence/S04-rules/actual-source.json.gz',
                'reason':('Qualified baseline anthology imported through SHA-pinned header conversion; final palette retained, unused glyph definitions removed. Every surviving record, move tuple, frame and patch stays exact. Current grammar needs new raw evidence; retained teaching requires checked rendering/input/prerequisite parity.' if piece_glyph_style is not None else 'All6890packed moves checked against qualified tuples; glyphs/initials/patches/scores retained exactly, data packets changed. Source/SAN/Player unchanged; independent packed-field/playback checks replace no old legal qualification.'),
                'anthology_sha256':sha(documents[2])},
            'input_files':{str(p.relative_to(root)):sha(p.read_bytes()) for p in paths},
            'pending':['Native build alone does not establish recipient or assembled-release qualification; consult current status and candidate-bound evidence.']}
        write_json(destination/'report.json',report)
        write_json(destination/'COMPLETE.json',{'artifact_sha256':digest,'files':{str(p.relative_to(destination)):sha(p.read_bytes()) for p in sorted(destination.rglob('*')) if p.is_file()}})
        return report
    except BaseException as error:
        write_json(destination/'FAILED.json',{'error':repr(error),'scope':'Incomplete; diagnostics retained, no completion claim'});raise
