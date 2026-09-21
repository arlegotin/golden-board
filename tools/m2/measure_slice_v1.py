#!/usr/bin/env python3
"""Private bounded sizing experiment: no carrier, proof, promotion or pass receipt.

Recompile both logical slices; use the hash-checked v0 capacity-policy loader
for historical role multiplicities. All geometry and placement arithmetic here
is local sizing code. No retained carrier or capacity ledger is an input.
"""
from __future__ import annotations

import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
from math import gcd
from pathlib import Path
import tomllib
import unittest

from golden_board import capacity, curriculum, m2_policy
from golden_board.m2_capacity_v1 import derive_capacity_inputs_v1
from golden_board.m2_slice import compile_slice_v0
from golden_board.m2_slice_v1 import compile_slice_v1

ROOT = Path(__file__).resolve().parents[2]
MAX_SECTION = 16384
FRAGMENT_PAYLOAD = 157
UNIT_BITS = 1728
ROUTE_PREFIX_BYTES = 29091
SOURCE_PATHS = (
    'studies/m2/slice-v0.json', 'conformance/content-v0.json',
    'conformance/chess-v0.json', 'reports/game-set-v0.bin',
    'spec/content-v0.md', 'spec/constants-v0.toml', 'spec/curriculum-v0.toml',
)


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _read(root, path):
    with (root/path).open('rb') as stream:
        raw=stream.read(2_097_153)
    _need(len(raw)<=2_097_152,'bounded sizing input: '+path)
    return raw


def _inputs(root):
    paths=(*SOURCE_PATHS,'studies/m2/slice-v1.json','spec/profile-policy-v0.toml',
           'spec/profile-policy-v1.toml','spec/route-data-v1.json','spec/slice-v1.md',
           'python/golden_board/capacity.py','python/golden_board/m2_capacity_v1.py',
           'python/golden_board/m2_slice.py','python/golden_board/m2_slice_v1.py',
           'tools/m2/measure_slice_v1.py')
    raws={path:_read(root,path) for path in paths}
    sources=tuple(raws[path] for path in SOURCE_PATHS)
    legacy=compile_slice_v0(*sources)
    revised=compile_slice_v1(raws['studies/m2/slice-v1.json'],*sources)
    blueprint=curriculum.load_blueprint(sources[-1])
    # The explicit v0 loader validates the production multiplicity owner; the
    # v1 overlay has no independent role-bundle policy to substitute here.
    policy=m2_policy.load_profile_policy(raws['spec/profile-policy-v0.toml'])
    _need(policy.section_payload_max==MAX_SECTION and policy.fragment_payload_bytes==FRAGMENT_PAYLOAD,
          'unexpected section or fragment bound')
    overlay=tomllib.loads(raws['spec/profile-policy-v1.toml'].decode())
    route=json.loads(raws['spec/route-data-v1.json'])
    _need(route['generated']['route_prefix_cells_by_sector']==[ROUTE_PREFIX_BYTES*8]*4,
          'old route prefix size changed')
    _need(overlay['transport']['physical_unit_bits']==UNIT_BITS
          and overlay['check']['check_id']==1
          and overlay['protection_class']['spine_physical_replica_count']==5
          and overlay['protection_class']['replicated_physical_replica_count']==2
          and overlay['protection_class']['nonreplicated_physical_replica_count']==1,
          'physical cost owner changed')
    _need(hashlib.sha256(bytes(_table(256))).hexdigest()==overlay['mapping']['unit_multiplier_table_sha256'],
          'historical mapping table disagrees with owner')
    identities=[{'path':path,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
                for path,raw in sorted(raws.items())]
    return {'legacy':legacy,'revised':revised,'policy':policy,
            'legacy_inputs':capacity.derive_capacity_inputs(legacy,blueprint),
            'revised_inputs':derive_capacity_inputs_v1(revised,legacy,blueprint),
            'input_identities':identities}


def _fragments(payload, dependencies=0):
    _need(type(payload) is int and 0<=payload<=MAX_SECTION,'section payload bound')
    _need(type(dependencies) is int and 0<=dependencies<=4095,'dependency bound')
    return (18+4*dependencies+payload+4+FRAGMENT_PAYLOAD-1)//FRAGMENT_PAYLOAD


def _model(inputs, policy):
    envelope=capacity.derive_capacity_envelope(inputs,policy.capacity_policy)
    _need(envelope.authoring_payload_bytes==105277,'historical authoring allowance drift')
    real=[]
    for item in inputs.real_content_sections:
        _need(item.closure in ('m2_required','m2_all_only'),'real section closure')
        factor=5 if item.closure=='m2_required' else 1
        fragments=_fragments(item.payload_length)
        real.append({'section_id':item.section_id,'closure':item.closure,'payload_bytes':item.payload_length,
                     'record_ids':list(item.record_ids),'factor':factor,'fragments':fragments,
                     'physical_units':factor*fragments})
    tiers=[]
    for item in inputs.tier_frames:
        fragments=_fragments(item.logical_payload_length,len(item.body_section_ids))
        tiers.append({'section_id':item.section_id,'payload_bytes':item.logical_payload_length,
                      'body_section_ids':list(item.body_section_ids),'factor':5,'fragments':fragments,
                      'physical_units':5*fragments,'root_frame_bytes':item.root_record_frame_length,
                      'assembled_stream_bytes':item.assembled_stream_length,
                      'assembled_record_count':item.assembled_record_count})
    future=[]
    factors={'replicated-core0-2':2,'nonreplicated-core3-4':1}
    for bucket in envelope.buckets:
        for item in bucket.sections:
            _need(item.protection_class in factors,'capacity protection class')
            factor=factors[item.protection_class]
            fragments=_fragments(item.payload_length)
            future.append({'bucket_id':item.bucket_id,'section_ordinal':item.section_ordinal,
                           'protection_class':item.protection_class,'payload_bytes':item.payload_length,
                           'factor':factor,'fragments':fragments,'physical_units':factor*fragments})
    real_slice=sum(r['payload_bytes'] for r in real+tiers)
    before_reserve=real_slice+envelope.authoring_payload_bytes+MAX_SECTION
    reserve=max(382,(before_reserve+18)//19)
    _need(reserve==capacity.reserve_requirement(real_slice+MAX_SECTION,envelope.authoring_payload_bytes),
          'reserve arithmetic disagreement')
    reserve_rows=[{'payload_bytes':value,'factor':2,'fragments':_fragments(value),
                   'physical_units':2*_fragments(value)}
                  for value in capacity.partition_probe_payload(reserve,MAX_SECTION)]
    entries=1+len(real)+len(tiers)+len(future)+len(reserve_rows)
    dependencies=sum(len(row['body_section_ids']) for row in tiers)
    groups={factor:sum(row['fragments'] for row in real+tiers+future+reserve_rows if row['factor']==factor)
            for factor in (1,2,5)}
    return {'real_sections':real,'tier_frames':tiers,'capacity_sections':future,'reserve_sections':reserve_rows,
            'authoring_payload_bytes':envelope.authoring_payload_bytes,'inventory_allowance_bytes':MAX_SECTION,
            'real_slice_payload_excluding_inventory':real_slice,'content_before_reserve_bytes':before_reserve,
            'reserve_payload_bytes':reserve,'protected_logical_capacity_bytes':before_reserve+reserve,
            'base_entry_count':entries,'dependency_count':dependencies,
            'noninventory_logical_groups':groups,
            'noninventory_physical_units':sum(factor*count for factor,count in groups.items())}


def _inventory(model, load_count):
    entries=model['base_entry_count']+load_count
    payload=8+20*entries+4*model['dependency_count']
    _need(0<=load_count and entries<=4096 and payload<=MAX_SECTION,'inventory bounds')
    fragments=_fragments(payload)
    return {'inventory_entry_count':entries,'inventory_payload_bytes':payload,
            'inventory_fragment_count':fragments,'mandatory_units':model['noninventory_physical_units']+5*fragments}


def _layout(model, side, width):
    """Smallest valid load-count/inventory fixed point, exactly filling Q."""
    interior=side-2*width
    _need(interior>0,'interior bound')
    population=interior*interior
    units=population//UNIT_BITS
    minimum=_inventory(model,0)
    if minimum['mandatory_units']>units:
        return None
    maximum_count=min(4096-model['base_entry_count'],
                      (MAX_SECTION-8-20*model['base_entry_count']-4*model['dependency_count'])//20)
    maximum_fragments=_fragments(MAX_SECTION)
    for count in range(maximum_count+1):
        inventory=_inventory(model,count)
        available=units-inventory['mandatory_units']
        if available<0:
            break
        required=(available+maximum_fragments-1)//maximum_fragments
        if (count==0 and available==0) or (count>0 and available>=count>=required):
            fragments=[]
            remaining=available
            for ordinal in range(count):
                value=min(maximum_fragments,remaining-(count-ordinal-1))
                _need(value>0,'load fragment bound')
                fragments.append(value)
                remaining-=value
            _need(remaining==0,'unassigned residual load')
            payloads=[min(MAX_SECTION,f*FRAGMENT_PAYLOAD-22) for f in fragments]
            _need(all(_fragments(p)==f for p,f in zip(payloads,fragments,strict=True)),
                  'load payload fragmentation')
            return dict(inventory,side=side,width=width,interior_side=interior,
                        population=population,unit_population=units,load_section_count=count,
                        load_units=available,load_fragment_counts=fragments,load_payload_bytes=payloads,
                        load_payload_total=sum(payloads),fixed_pad_cells=population-units*UNIT_BITS,
                        carrier_bytes=side*side//8)
    return None


@lru_cache(maxsize=320)
def _smallest_multiplier(interior):
    population=interior*interior
    units=population//UNIT_BITS
    multiplier=2*interior-1
    window=max(32,interior//8)
    for candidate in range(1,units):
        if gcd(candidate,units)!=1:
            continue
        valid=True
        for distance in range(1,5):
            residue=candidate*distance%units
            for delta in (residue,residue-units):
                row,column=divmod((multiplier*UNIT_BITS*delta)%population,interior)
                column_gap=min(column,interior-column)
                for row_delta in ((row,) if column==0 else (row,(row+1)%interior)):
                    if max(min(row_delta,interior-row_delta),column_gap)<window:
                        valid=False
                        break
                if not valid:
                    break
            if not valid:
                break
        if valid:
            _need(candidate<=255,'UINT8 mapping table cannot carry selected multiplier')
            return candidate
    return 0


@lru_cache(maxsize=2)
def _table(entries):
    _need(entries in (256,320),'bounded mapping sensitivity')
    # Keep zero at each table endpoint. Under the larger candidate, index 255
    # is an ordinary interior index; its old endpoint sentinel is not retained.
    return (0,)+tuple(_smallest_multiplier(8*i) for i in range(1,entries-1))+(0,)


def _pairs(cap):
    _need(cap in (2048,2560),'bounded side sensitivity')
    for side in range(64,cap+1,8):
        for width in range(8,min(128,(side-8)//2)+1,8):
            yield side,width


def _headrooms(prefix_bytes):
    instruction_cells=4*prefix_bytes*8
    total=max((instruction_cells+19)//20,4*256)
    quotient,remainder=divmod(total-4*256,4)
    return [256+quotient+int(sector<remainder) for sector in range(4)]


def _search(model,cap,route_extra_bytes):
    table=_table(cap//8)
    prefix=ROUTE_PREFIX_BYTES+route_extra_bytes
    headrooms=_headrooms(prefix)
    minimum=_inventory(model,0)['mandatory_units']
    rows=[]
    first=None
    best=None
    counts=Counter()
    for side,width in _pairs(cap):
        interior=side-2*width
        units=interior*interior//UNIT_BITS
        index=interior//8
        failure=''
        if any(prefix*8+h>width*(side-width) for h in headrooms):
            failure='route-headroom'
        elif not 0<index<len(table)-1 or table[index]==0:
            failure='mapping-table'
        else:
            _need(gcd(table[index],units)==1,'mapping inverse absent')
            _need(gcd(2*interior-1,interior*interior)==1,'cell inverse absent')
            if best is None or units>best['unit_population']:
                best={'side':side,'width':width,'unit_population':units,
                      'minimum_mandatory_units':minimum,'minimum_deficit_units':max(0,minimum-units)}
            layout=_layout(model,side,width)
            if layout is None:
                failure='inventory-load-fixed-point'
            elif first is None:
                first=dict(layout,slot_multiplier=table[index],slot_inverse=pow(table[index],-1,units),
                           sector_capacity_cells=width*(side-width),
                           route_prefix_bytes_per_sector=prefix,headroom_cells_by_sector=headrooms,
                           maximum_equal_route_prefix_bytes_per_sector=5*width*(side-width)//42,
                           unencoded_route_growth_budget_bytes_per_sector=5*width*(side-width)//42-prefix)
        result=failure or 'fit'
        counts[result]+=1
        rows.append([side,width,result,units])
    return {'side_cap':cap,'search_complete':True,'route_prefix_bytes_per_sector':prefix,
            'conditional_route_growth_bytes_per_sector':route_extra_bytes,
            'headroom_cells_by_sector':headrooms,'pair_count':len(rows),'result_counts':dict(sorted(counts.items())),
            'first_fit':first,'most_available_admissible_pair':best,
            'mapping_table':{'entries':len(table),'sha256':hashlib.sha256(bytes(table)).hexdigest(),
                'maximum':max(table),'zero_indices':[i for i,v in enumerate(table) if v==0]},
            'row_fields':['side','shell_width','first_failed_constraint_or_fit','unit_population'],
            'rows':rows}


def _lower_bound(model,cap,prefix_bytes):
    inventory=_inventory(model,0)
    categories=[{'category':'inventory','payload_bytes':inventory['inventory_payload_bytes'],
                 'physical_units':5*inventory['inventory_fragment_count']}]
    for category,key in (('tier-frames','tier_frames'),('real-content','real_sections'),
                         ('capacity','capacity_sections'),('reserve','reserve_sections')):
        categories.append({'category':category,'payload_bytes':sum(r['payload_bytes'] for r in model[key]),
                           'physical_units':sum(r['physical_units'] for r in model[key])})
    _need(sum(row['physical_units'] for row in categories)==inventory['mandatory_units'],
          'lower-bound reconciliation')
    protected=inventory['mandatory_units']*UNIT_BITS
    route=4*prefix_bytes*8
    return {'categories':categories,'minimum_mandatory_units':inventory['mandatory_units'],
            'protected_cells':protected,'route_prefix_cells':route,'lower_bound_cells':protected+route,
            'ceiling_cells':cap*cap,'excess_cells':max(0,protected+route-cap*cap),
            'eliminates':protected+route>cap*cap,
            'omits_only':['route-headroom','shell-alignment-pad','interior-tail-pad','load-probes']}


def _encoded(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()


def _measure(root,output):
    inputs=_inputs(root)
    old=_model(inputs['legacy_inputs'],inputs['policy'])
    new=_model(inputs['revised_inputs'],inputs['policy'])
    baseline=_layout(old,2040,128)
    _need(baseline is not None and (baseline['mandatory_units'],baseline['unit_population'])==(1465,1841),
          'historical baseline verification failed')
    old_search=_search(new,2048,0)
    enlarged=_search(new,2560,2*(320-256))
    lower=_lower_bound(new,2048,ROUTE_PREFIX_BYTES)
    compiled=inputs['revised']
    streams={'required':{'bytes':len(compiled.required_content_bytes),'sha256':compiled.required_content_sha256},
             'all':{'bytes':len(compiled.content_bytes),'sha256':compiled.content_sha256}}
    report={'schema':'golden-board.private-slice-fit-measurement/v1',
            'status':'private-sizing-only-no-carrier-proof-promotion-or-pass-receipt',
            'conditional_route_warning':'technical-route repairs remain unencoded; only two extra table payloads are charged',
            'input_identities':inputs['input_identities'],'streams':streams,'baseline_2040_128':baseline,
            'revised_cost_model':new,'failed_2048_lower_bound':lower,
            'search_2048_summary':{k:v for k,v in old_search.items() if k!='rows'},
            'conditional_2560_summary':{k:v for k,v in enlarged.items() if k!='rows'}}
    output.mkdir(parents=True,exist_ok=True)
    artifacts={
        'fit-measurement.json':_encoded(report),
        'fit-search-2048.json':_encoded(old_search),
        'fit-search-2560.json':_encoded(enlarged),
    }
    first=enlarged['first_fit']
    best=old_search['most_available_admissible_pair']
    required=[r for r in new['real_sections'] if r['closure']=='m2_required']
    if old_search['first_fit'] is not None or first is None or not lower['eliminates']:
        # Preserve measured outcomes even when a future reviewed declaration no
        # longer has the outcome motivating this experiment. Never suppress a
        # valid measurement merely because it differs from the expected result.
        summary=('# Revised slice: bounded fit measurement\n\n'
                 'Private arithmetic only; technical-route repairs remain unencoded.\n\n'
                 f"Current 2048 first fit: {old_search['first_fit']}.\n\n"
                 f'Conditional 2560 first fit: {first}.\n\n'
                 f'2048 lower bound: {lower}.\n\n'
                 'Full section costs, input identities and exhaustive geometry rows are in the accompanying JSON.\n')
        artifacts['fit-summary.md']=summary.encode()
        for name,raw in artifacts.items():
            (output/name).write_bytes(raw)
        print(json.dumps({'status':report['status'],'no_fit_2048':old_search['first_fit'] is None,
                          'lower_bound_cells':lower['lower_bound_cells'],'conditional_first_fit':first},sort_keys=True))
        return
    summary=f'''# Revised slice: bounded fit measurement

The revised slice cannot fit the existing 2048-side envelope. A complete
{old_search['pair_count']}-pair search admits no geometry. Its candidate-favorable
lower bound is {lower['lower_bound_cells']:,} cells, exceeding the {lower['ceiling_cells']:,}-cell
ceiling by {lower['excess_cells']:,} cells before headroom, pad or load probes.

The separate 2560 sensitivity first fits at side **{first['side']}**, shell width
**{first['width']}** ({first['carrier_bytes']:,} carrier bytes), conditional on the old
route plus exactly 128 extra bytes per sector for the expanded mapping table.
Technical-route repairs remain unencoded. This is no carrier, damage proof,
promotion, release or human-evidence pass, and it does not alter any current
owner or historical failed fit.

## Exact logical and physical costs

- Required stream: {streams['required']['bytes']:,} bytes,
  SHA-256 `{streams['required']['sha256']}`.
- All stream: {streams['all']['bytes']:,} bytes,
  SHA-256 `{streams['all']['sha256']}`.
- Required whole-record sections: {', '.join(str(r['section_id'])+': '+str(r['payload_bytes']) for r in required)} bytes.
  Every required section has factor 5, as do inventory and both tier frames.
- {len(new['real_sections'])} real body sections, including all 64 complete games;
  tier payloads are {', '.join(str(r['payload_bytes']) for r in new['tier_frames'])} bytes.
- The unchanged historical prototypes and production v0 role multiplicities
  produce {new['authoring_payload_bytes']:,} allowance bytes in {len(new['capacity_sections'])} sections.
  Replicated capacity uses factor 2, all-only capacity and bodies factor 1.
- Real body plus tier payload is {new['real_slice_payload_excluding_inventory']:,} bytes.
  C adds the complete {new['inventory_allowance_bytes']:,}-byte inventory allowance and
  {new['authoring_payload_bytes']:,}-byte authoring allowance, yielding {new['content_before_reserve_bytes']:,}.
  R=max(382,ceil(C/19)) is **{new['reserve_payload_bytes']:,} bytes**, protected at factor 2.
- Reserve uses its full application payload and additionally pays section,
  fragment, check, parity and replication overhead. Actual inventory size
  never reduces the frozen 16,384-byte allowance.

The lower bound contains {lower['minimum_mandatory_units']:,} mandatory physical units
({lower['protected_cells']:,} protected cells) plus all four old route prefixes
({lower['route_prefix_cells']:,} cells). The most capacious route-admissible geometry
inside the current cap is {best['side']}/{best['width']} with {best['unit_population']:,} units;
even its minimum deficit is {best['minimum_deficit_units']:,} units.

## Conditional first fit

| Quantity | Value |
|---|---:|
| Side / width / interior | {first['side']} / {first['width']} / {first['interior_side']} |
| Unit population Q | {first['unit_population']} |
| Mandatory units | {first['mandatory_units']} |
| Load units / sections | {first['load_units']} / {first['load_section_count']} |
| Load payload bytes | {first['load_payload_total']} |
| Inventory entries / payload bytes / fragments | {first['inventory_entry_count']} / {first['inventory_payload_bytes']} / {first['inventory_fragment_count']} |
| Fixed interior pad cells | {first['fixed_pad_cells']} |
| Route prefix bytes per sector | {first['route_prefix_bytes_per_sector']} |
| Sector capacity cells | {first['sector_capacity_cells']} |
| Mapping B / inverse | {first['slot_multiplier']} / {first['slot_inverse']} |
| Additional unencoded route bytes this geometry could hold per sector | {first['unencoded_route_growth_budget_bytes_per_sector']} |

Headroom is derived over all four prefixes as H=max(ceil(I/20),4*256), then
distributed in sector order. At the conditional fit its sector charges are
{first['headroom_cells_by_sector']}. The 320-entry UINT8 mapping table is freshly
computed with the complete four-distance row-carry separation predicate;
index 255 becomes an ordinary entry and index 319 is the new endpoint sentinel.
The 128-byte route increment charges its 64 additional payload entries once
in the recipe package and once in the route TABLE. No other route growth is
assumed. New route bytes, examples, types, work limits and damage populations
must be independently encoded and verified before this geometry is admissible.
The arithmetic route-growth budget above includes preserving five-percent
headroom; it is a space limit, not evidence that those repairs fit or suffice.

Both searches enumerate every legal side/width pair in canonical order, without
stopping after the first fit. Every row records the first failed constraint:
route/headroom, mapping admission, or the complete inventory/load fixed point.
The old search has {old_search['pair_count']} rows; the conditional search has
{enlarged['pair_count']}. Full rows and input hashes accompany this report.

## Reproduction and validation

```sh
PYTHONPATH=python:. .venv/bin/python tools/m2/measure_slice_v1.py --self-test
PYTHONPATH=python:. .venv/bin/python tools/m2/measure_slice_v1.py --output-dir artifacts/work/participant-revision
```

The baseline is freshly compiled from slice-v0 and exactly reproduces 1465
mandatory / 1841 total units at 2040/128, inventory 3080 bytes, load fragments
[105,105,105,61] and 1408 pad cells. The script also checks whole-record v1 costs,
the unchanged allowance and derived reserve, exact fragment boundaries, both
headroom calculations, all 3815 old geometry pairs and the old mapping-table
SHA-256. No retained carrier or ledger is consumed. Only the explicit v0 policy
loader supplies capacity multiplicities; the revised slice uses its separate
verified historical prototype source.
'''
    summary+='\nArtifact digests:\n\n'+''.join(
        f'- `{name}`: {len(raw):,} bytes, SHA-256 `{hashlib.sha256(raw).hexdigest()}`.\n'
        for name,raw in sorted(artifacts.items()))
    artifacts['fit-summary.md']=summary.encode()
    for name,raw in artifacts.items():
        _need(name.startswith('fit-'),'output ownership')
        (output/name).write_bytes(raw)
    print(json.dumps({'status':report['status'],'no_fit_2048':True,
                      'lower_bound_cells':lower['lower_bound_cells'],'reserve_payload_bytes':new['reserve_payload_bytes'],
                      'conditional_first_fit':first},sort_keys=True))


class _ArithmeticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = _inputs(ROOT)

    def test_baseline_known_geometry_and_fixed_point(self):
        old = _model(self.inputs['legacy_inputs'], self.inputs['policy'])
        layout = _layout(old, 2040, 128)
        self.assertEqual(old['authoring_payload_bytes'], 105277)
        self.assertEqual(old['reserve_payload_bytes'], 7141)
        self.assertEqual(layout['mandatory_units'], 1465)
        self.assertEqual(layout['unit_population'], 1841)
        self.assertEqual(layout['inventory_payload_bytes'], 3080)
        self.assertEqual(layout['load_fragment_counts'], [105, 105, 105, 61])
        self.assertEqual(layout['load_payload_bytes'], [16384, 16384, 16384, 9555])
        self.assertEqual(layout['fixed_pad_cells'], 1408)

    def test_revised_whole_record_sections_and_full_allowance(self):
        new = _model(self.inputs['revised_inputs'], self.inputs['policy'])
        self.assertEqual([r['payload_bytes'] for r in new['real_sections'] if r['closure'] == 'm2_required'],
                         [16273, 15067, 11076])
        self.assertEqual(new['authoring_payload_bytes'], 105277)
        self.assertEqual(new['inventory_allowance_bytes'], 16384)
        self.assertEqual(new['reserve_payload_bytes'], 9353)
        self.assertEqual([r['payload_bytes'] for r in new['tier_frames']], [46, 346])
        self.assertTrue(all(r['factor'] == 5 for r in new['real_sections'] if r['closure'] == 'm2_required'))
        self.assertTrue(all(r['factor'] == 1 for r in new['real_sections'] if r['closure'] == 'm2_all_only'))

    def test_revised_complete_search_and_failed_fit_lower_bound(self):
        new=_model(self.inputs['revised_inputs'],self.inputs['policy'])
        old=_search(new,2048,0)
        extended=_search(new,2560,128)
        lower=_lower_bound(new,2048,ROUTE_PREFIX_BYTES)
        self.assertEqual(len(old['rows']),3815)
        self.assertIsNone(old['first_fit'])
        self.assertEqual(old['result_counts'],{'inventory-load-fixed-point':2,'route-headroom':3813})
        self.assertEqual((lower['minimum_mandatory_units'],lower['lower_bound_cells'],lower['excess_cells']),
                         (2833,5826336,1632032))
        self.assertTrue(lower['eliminates'])
        self.assertEqual(len(extended['rows']),4839)
        first=extended['first_fit']
        self.assertEqual((first['side'],first['width'],first['mandatory_units'],first['unit_population']),
                         (2440,112,2833,2841))
        self.assertEqual(first['load_payload_bytes'],[1234])
        self.assertEqual(first['inventory_payload_bytes'],3052)
        self.assertEqual(first['fixed_pad_cells'],1408)

    def test_exact_mapping_table_and_geometry_domain(self):
        old = _table(256)
        self.assertEqual(hashlib.sha256(bytes(old)).hexdigest(),
                         '835717bf400c597a3a9e1b59747f23d93047b6cfab462756fa07d96c5f3eba3f')
        pairs = list(_pairs(2048))
        self.assertEqual(len(pairs), 3815)
        self.assertEqual(sum(bool(old[(side-2*width)//8]) for side,width in pairs),3536)
        new = _table(320)
        self.assertEqual(len(new), 320)
        self.assertNotEqual(new[255], 0)
        self.assertTrue(all(0 <= value <= 255 for value in new))
        self.assertEqual(len(list(_pairs(2560))), 4839)

    def test_route_headroom_and_charge_boundaries(self):
        self.assertEqual(_headrooms(ROUTE_PREFIX_BYTES), [11637,11637,11636,11636])
        self.assertEqual(_headrooms(ROUTE_PREFIX_BYTES+128), [11688,11688,11688,11687])
        for payload in (0,1,135,136,16384):
            for deps in (0,1,78):
                self.assertEqual(_fragments(payload,deps),capacity.section_charge(payload,deps,1,1).common_blocks)

    def test_inventory_growth_can_consume_the_apparent_load_room(self):
        # The first load entry crosses an inventory fragment boundary. It adds
        # five physical replicas, so Q=12 cannot simply keep its two apparent
        # spare units as an uncharged load or as arbitrary extra tail padding.
        model={'base_entry_count':14,'dependency_count':1,'noninventory_physical_units':0}
        self.assertEqual(_inventory(model,0)['mandatory_units'],10)
        self.assertEqual(_inventory(model,1)['mandatory_units'],15)
        self.assertEqual(_layout(model,152,8)['load_units'],0)
        self.assertIsNone(_layout(model,160,8))
        filled=_layout(model,184,8)
        self.assertEqual((filled['mandatory_units'],filled['unit_population'],filled['load_units']),(15,16,1))
        self.assertEqual(filled['load_payload_bytes'],[135])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args()
    if args.self_test:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(_ArithmeticTests)
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        if not result.wasSuccessful():
            raise SystemExit(1)
        return
    if args.output_dir is None:
        parser.error('--output-dir is required unless --self-test')
    _measure(ROOT,args.output_dir)


if __name__ == '__main__':
    main()
