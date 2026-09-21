"""Explicit development profile8 observation receiver.

No builder/catalog/clean carrier is accepted. Promotion stays fail-closed in
m2_policy_v2. DEFINE knowledge-use and complete resource/damage projections are
separate required evidence; this implementation does not award those gates.
"""
from dataclasses import replace
from hashlib import sha256

from . import bootstrap, bootstrap_v2, body_codec_v1, canonical_manifest, content
from . import m2_codec, m2_decoder as old, recipe_wire_v1
from .m2_route_receiver_v2 import decode_observed_route_v2
from .m2_program_refinement_v2 import body_program_refined
from .m2_resources_v2 import (ResourceMeterV2, add, multiply, content_shape, content_workspace,
                             recipe_storage, recipe_workspace, render_resource_projection_v2)


class ObservationDecoderV2(old.ObservationDecoder):
    def __init__(self, profile_policy_raw, profile_limits_raw, damage_policy_raw, *, require_promoted=False):
        from .m2_policy_v2 import load_decoder_policy_v2
        self.policy = load_decoder_policy_v2(profile_policy_raw,profile_limits_raw,damage_policy_raw,
                                             require_promoted=require_promoted)
        self.maximum_units = self.policy.maximum_units
        self.profiles = self.policy.profiles_for_units(self.maximum_units)
        self.profile_by_version = {p.profile_version:p for p in self.profiles}
        self.profile_order = {p.profile_id:i for i,p in enumerate(self.profiles)}
        self.transport_resources = {v:(steps,scratch) for v,_id,_sha,steps,scratch
                                    in self.policy.obs_units_resource_profiles}
        self.repetition_resource = (self.policy.repetition_primitive_steps,self.policy.repetition_peak_scratch_bytes)
        self.result_schema_version = 2
        self.establishing_profile_versions = frozenset((8,))
        self._initialize_caches()
        self._observed_mappings = {}
        self._observed_packages = {}
        self.observed_context_commitments = {}
        self._body_cache = {}
        self._route_failure_resources = {}
        self._rejected_route_steps = 0
        self._rejected_route_scratch = 0
        self._current_package = None
        self._meter = ResourceMeterV2()
        self._path_groups = set()
        self.last_rejection = ''
        self._resource_projection = None
        self._observation_sha256 = None

    @staticmethod
    def _hierarchical_profile(profile):
        return profile.profile_version in (7,8) and profile.transport_id == m2_codec.HIER_TRANSPORT

    @staticmethod
    def _diagnostic_raw_section_allowed(block):
        # Foreign legacy inventory copies remain diagnostics in the final
        # registry-wide fallback; hierarchical section1 still requires REP.
        return block.section_id != 1 or block.profile_version in (2,3,4,5,6)

    @staticmethod
    def _inventory_version(profile):
        return 2 if profile.profile_version == 8 else old.ObservationDecoder._inventory_version(profile)

    def _decode_inventory_payload(self, profile, raw):
        self._meter.adapter('inventory',len(raw),16*len(raw))
        self._meter.retain('path-inventory',16*len(raw))
        return bootstrap_v2.decode_inventory(raw) if profile.profile_version == 8 else bootstrap.decode_inventory(raw)

    @staticmethod
    def _route_version(profile):
        return 2 if profile.profile_version == 8 else old.ObservationDecoder._route_version(profile)

    @staticmethod
    def _inventory_bootstrap_profile(profiles):
        active = tuple(p for p in profiles if p.profile_version == 8)
        if len(active) == 1:
            return active[0]
        return old.ObservationDecoder._inventory_bootstrap_profile(profiles)

    def _mapping_projection(self, version, profile, mapping):
        if version != 2:
            return super()._mapping_projection(version,profile,mapping)
        key = (profile.profile_version,*mapping)
        projection = self._observed_mappings.get(key)
        if projection is None or projection['unit_population'] != profile.protected_units:
            old._fail('route-mapping')
        return dict(projection)

    @staticmethod
    def _mapping_digest(version, projection):
        if version != 2:
            return old._mapping_sha256(version,projection)
        if (type(projection) is not dict or set(projection) != old._HIERARCHICAL_MAPPING_KEYS
                or projection['id'] != 'affine-slot-then-interior-v2'):
            old._fail('route-mapping')
        return sha256(canonical_manifest.serialize_manifest(projection)).hexdigest()

    def _parse_route(self, cells, width, sector):
        self._meter.adapter('shell-read',512,64)
        header = old._sector_bytes(cells,width,sector,64)
        if header is None:
            return None
        with self._meter.hold(64):
            try:
                return self._parse_route_prefix(cells,width,sector,header)
            finally:
                self._meter.retain('active-route-prefix',0)

    def _read_route_prefix(self, cells, width, sector, length):
        self._meter.adapter('shell-read',8*length,length)
        prefix = super()._read_route_prefix(cells,width,sector,length)
        if prefix is not None:
            self._meter.retain('active-route-prefix',length)
        return prefix

    def _parse_route_record_frames(self, raw, count, package_bytes):
        self._meter.adapter('route-frame',64+len(raw),8*count)
        return super()._parse_route_record_frames(raw,count,package_bytes)

    def _parse_route_prefix(self, cells, width, sector, header):
        if header[40:42] != b'\0\2':
            # Re-run the logical route procedure. Fine-grained package/VM
            # caches may still share computation; whole-route caching would
            # obscure partial adapter charges at a stable rejection.
            self._route_cache.clear()
            self._validated_route_cache.clear()
            before = self._meter.usage.primitive_steps
            route = super()._parse_route(cells,width,sector)
            if route is not None:
                # Replayed validation cache receives its complete logical cost.
                spent = self._meter.usage.primitive_steps-before
                if spent < route.route_primitive_steps:
                    self._meter.invoke(route.route_primitive_steps-spent,route.route_peak_scratch)
            return route
        end = 64+int.from_bytes(header[48:52],'big')
        if end > 32768 or end*8 > width*(cells.side-width):
            return None
        prefix = self._read_route_prefix(cells,width,sector,end)
        if prefix is None:
            return None
        key = (cells.side,width,sector,prefix)
        result = None
        try:
            parsed = decode_observed_route_v2(prefix,cells.side,width,sector,
                charge=self._meter.invoke,adapter=self._meter.adapter,retain=self._meter.retain)
            projection = parsed.mapping
            self.observed_context_commitments[parsed.definitions] = parsed.commitments
            profile = self.policy.candidate_profile(projection['unit_population'])
            mapping = (projection['interior_side'],projection['cell_multiplier'],projection['offset'])
            mapping_key = (8,*mapping)
            previous = self._observed_mappings.get(mapping_key)
            if previous is not None and previous != projection:
                old._fail('route-mapping')
            self._observed_mappings[mapping_key] = projection
            self._observed_packages[parsed.package.encoded] = parsed.package
            self._meter.retain(('package',parsed.package.encoded),
                               recipe_storage(parsed.package.encoded))
            self._meter.retain(('definitions',parsed.definitions),
                               sum(map(len,parsed.definitions))+16*len(parsed.definitions))
            recipes = {r.recipe_id:r for r in parsed.package.logical.recipes}
            result = old._Route(profile,width,(parsed.package.encoded,),b'GBROUTE\0',2,mapping,1,sector,
                parsed.primitive_steps,parsed.peak_scratch_bytes,
                recipes[30].primitive_steps,recipes[30].peak_live_scratch_bytes,
                recipes[113].primitive_steps,recipes[113].peak_live_scratch_bytes,parsed.definitions)
        except old.DecoderError as error:
            steps = getattr(error,'primitive_steps',0)
            scratch = getattr(error,'peak_scratch_bytes',0)
            self._route_failure_resources[key] = (steps,scratch)
            self._rejected_route_steps = add(self._rejected_route_steps,steps)
            self._rejected_route_scratch = max(self._rejected_route_scratch,scratch)
            if error.reason == 'resource-limit':
                raise
        return result

    def _decode_route_package(self, raw, profile_version):
        self._meter.adapter('recipe-parse',len(raw),recipe_workspace(raw))
        package = super()._decode_route_package(raw,profile_version)
        self._meter.retain(('package',raw),recipe_storage(raw))
        return package

    def _evaluate_route_recipe(self, package, recipe_id, values):
        size = sum(map(len,values))
        program = next(row for row in package.recipes if row.recipe_id == recipe_id)
        outputs = sum(d.width if d.value_type == bootstrap.BYTES else (d.width+7)//8 for d in program.outputs)
        self._meter.adapter('route-example',size,size+outputs+8*(len(program.inputs)+len(program.outputs)))
        return super()._evaluate_route_recipe(package,recipe_id,values)

    def _extract_units(self, cells, profile, width, mapping):
        count = min(profile.protected_units,mapping[0]**2//(8*profile.protected_unit_bytes))
        self._meter.adapter('unit-extraction',count*profile.protected_unit_bytes*8,
                            count*(8+2*profile.protected_unit_bytes))
        return super()._extract_units(cells,profile,width,mapping)

    def _expected_units(self, profile, inventory):
        count = sum(((18+4*len(e.dependencies)+e.logical_payload_length+(4 if e.check_id == 1 else 8)+156)//157)
                    *(e.physical_replica_count if inventory.version >= 1 else e.copy_count)
                    for e in inventory.entries)
        edges = sum(len(e.dependencies) for e in inventory.entries)
        self._meter.adapter('group-layout',count,128*count+64*len(inventory.entries))
        self._meter.retain('path-layout',128*count+64*len(inventory.entries)+8*edges)
        self._meter.adapter('dependency-closure',edges,24*len(inventory.entries)+8*edges)
        return super()._expected_units(profile,inventory)

    @staticmethod
    def _route_group_key(route):
        inherited = old.ObservationDecoder._route_group_key(route)
        return (*inherited,route.packages,route.definition_values) if route.route_version == 2 else inherited

    def _recover_route_sections(self, route, observations):
        # Bind decoding to this observed route. Multiple hypotheses cannot use
        # the program of whichever route happened to be parsed last.
        previous = self._current_package
        self._current_package = self._observed_packages[route.packages[0]] if route.route_version == 2 else None
        try:
            return super()._recover_route_sections(route,observations)
        finally:
            self._current_package = previous

    def _recover_inventory_v7(self, profile, observations):
        recovered = super()._recover_inventory_v7(profile,observations)
        if recovered is None or profile.profile_version != 8:
            return recovered
        inventory,_ = recovered
        count = sum(((22+4*len(e.dependencies)+e.logical_payload_length+156)//157)
                    * e.physical_replica_count for e in inventory.entries)
        if count > self.maximum_units:
            old._fail('resource-limit')
        if self._current_package is not None and count != profile.protected_units:
            return None
        return recovered

    def _decode_body(self, version, raw):
        if version == 0:
            return body_codec_v1.decode_body(version,raw),0,0
        if version != 1 or type(raw) is not bytes or not 3 <= len(raw) <= 16384:
            raise ValueError('body-bound')
        package = self._current_package
        if package is None:
            # OBS_UNITS supplies registered known transforms, not a route.
            steps = self.policy.decompression_primitive_steps
            scratch = self.policy.decompression_peak_scratch_bytes
            return body_codec_v1.decode_body(version,raw),steps,scratch
        recipe = next(r for r in package.logical.recipes if r.recipe_id == 202)
        self._meter.adapter('program-refinement',package.logical.total_node_count,
            32*package.logical.total_node_count+8*package.logical.total_edge_count+8*len(package.logical.tables))
        if body_program_refined(package):
            return body_codec_v1.decode_body(version,raw),recipe.primitive_steps,recipe.peak_live_scratch_bytes
        key = (package.encoded,raw)
        result = self._body_cache.get(key)
        if result is None:
            result = recipe_wire_v1.evaluate_recipe_v1(package,202,
                        (raw+bytes(16384-len(raw)),len(raw).to_bytes(2,'big')))
            self._cache_store(self._body_cache,key,result,4096)
        if result.status or len(result.outputs) != 2 or len(result.outputs[0]) != 2 or len(result.outputs[1]) != 16384:
            raise ValueError('body-program')
        length = int.from_bytes(result.outputs[0],'big')
        if not 0 <= length <= 16384 or any(result.outputs[1][length:]):
            raise ValueError('body-program-output')
        return result.outputs[1][:length],recipe.primitive_steps,recipe.peak_live_scratch_bytes

    def _recover_content_tiers(self, profile, inventory, unique_envelopes):
        if profile.profile_version != 8:
            return super()._recover_content_tiers(profile,inventory,unique_envelopes)
        try:
            return self._content_tiers_v2(profile,inventory,unique_envelopes)
        finally:
            self._meter.retain('path-decoded-bodies',0)

    def _content_tiers_v2(self, profile, inventory, unique_envelopes):
        streams,steps,scratch = [],0,0
        decoded_bodies = {}
        for frame_id in (2,3):
            if frame_id == 3 and streams[0] is None:
                streams.append(None)
                break
            try:
                envelope = bootstrap.decode_section_envelope(unique_envelopes[frame_id])
                frame = bootstrap.decode_tier_frame(envelope.payload,frame_id)
                bootstrap.validate_tier_against_inventory(frame,envelope,inventory)
                bodies = {}
                for section_id in frame.body_section_ids:
                    body = bootstrap.decode_section_envelope(unique_envelopes[section_id])
                    bootstrap.validate_envelope_against_inventory(body,inventory)
                    # Charge the declared invocation even when it fails. Caches
                    # avoid repeated computation, never logical resource charge.
                    if section_id in decoded_bodies:
                        bodies[section_id] = decoded_bodies[section_id]
                        continue
                    if body.section_version == 1:
                        if self._current_package is None:
                            steps += self.policy.decompression_primitive_steps
                            scratch = max(scratch,self.policy.decompression_peak_scratch_bytes)
                        else:
                            program = next(r for r in self._current_package.logical.recipes if r.recipe_id == 202)
                            steps += program.primitive_steps
                            scratch = max(scratch,program.peak_live_scratch_bytes)
                    if body.section_version == 1:
                        self._meter.invoke(
                            self.policy.decompression_primitive_steps if self._current_package is None else program.primitive_steps,
                            self.policy.decompression_peak_scratch_bytes if self._current_package is None else program.peak_live_scratch_bytes)
                    self._meter.adapter('body-adapter',len(body.payload),len(body.payload)+32768)
                    decoded_bodies[section_id] = self._decode_body(body.section_version,body.payload)[0]
                    bodies[section_id] = decoded_bodies[section_id]
                    self._meter.retain('path-decoded-bodies',sum(len(raw)+8 for raw in decoded_bodies.values()))
                stream = self._assemble_content_stream(frame,bodies)
            except old.DecoderError:
                raise
            except (KeyError,ValueError):
                stream = None
            streams.append(stream)
            self._meter.retain('path-assembled-streams',sum(len(raw or b'') for raw in streams))
        return *streams,steps,scratch

    @staticmethod
    def _cache_store(cache, key, value, maximum):
        # Caches are optional and must never turn valid input into exhaustion.
        if key in cache or len(cache) < maximum:
            cache[key] = value

    def _charge_route_invocation(self, primitive_steps, peak_scratch):
        self._meter.invoke(primitive_steps,peak_scratch)

    def _charge_mapping_invocation(self, primitive_steps, peak_scratch):
        self._meter.invoke(primitive_steps,peak_scratch)
        return True

    def _assemble_content_stream(self, frame, bodies):
        size,records = frame.assembled_stream_byte_length,frame.assembled_record_count
        workspace = content_workspace(size,records)
        self._meter.adapter('content-validation',size,workspace)
        raw = bootstrap.assemble_tier_bytes(frame,bodies)
        _,_,region_rows = content_shape(raw)
        self._meter.adapter_workspace('content-validation',content_workspace(size,records,region_rows))
        try:
            content.stream_validation(raw)
        except content.ContentReject as error:
            raise bootstrap.BootstrapReject(bootstrap.CONTENT_STREAM,'content_stream') from error
        return raw

    def _assemble_semantic_copy(self, blocks, profile_version):
        blocks = tuple(blocks)
        candidate = b''
        try:
            by_index,identity = {},None
            for raw in blocks:
                block = bootstrap.decode_common_block(raw,profile_version)
                current = (block.section_id,block.semantic_copy_id,block.section_type,
                           block.section_version,block.fragment_count,block.section_envelope_length)
                if identity is not None and current != identity:
                    break
                identity = current
                previous = by_index.get(block.fragment_index)
                if previous is not None and previous != block:
                    break
                by_index[block.fragment_index] = block
            else:
                if identity is not None and set(by_index) == set(range(identity[4])):
                    candidate = b''.join(by_index[i].payload for i in range(identity[4]))
                    if len(candidate) != identity[5]:
                        candidate = b''
        except bootstrap.BootstrapReject:
            pass
        self._meter.adapter('section-assembly',sum(map(len,blocks)),len(candidate)+24*len(blocks))
        self._meter.section(candidate)
        return bootstrap.assemble_semantic_copy(blocks,profile_version)

    def _aggregate_v7_group(self, profile, observations):
        lanes = tuple(observations)
        key = (profile.profile_version,tuple(None if row is None else row.unit_id for row in lanes))
        if len(lanes) > 1 and any(row is not None for row in lanes) and key not in self._path_groups:
            steps,scratch = self.repetition_resource
            transport_steps,transport_scratch = self.transport_resources[profile.profile_version]
            if self._current_package is not None:
                programs = {r.recipe_id:r for r in self._current_package.logical.recipes}
                steps,scratch = programs[113].primitive_steps,programs[113].peak_live_scratch_bytes
                transport_steps,transport_scratch = programs[30].primitive_steps,programs[30].peak_live_scratch_bytes
            self._meter.invoke(steps,scratch,1728)
            self._meter.invoke(transport_steps,transport_scratch,24)
            self._meter.adapter('repetition-adapter',1728*len(lanes),216+2*1728)
            self._meter.adapter('common-frame',191,191)
            self._path_groups.add(key)
        return super()._aggregate_v7_group(profile,lanes)

    def _lane(self, profile, observation, steps, scratch):
        count = 24 if profile.transport_id in (m2_codec.EH_TRANSPORT,m2_codec.HIER_TRANSPORT) else 1
        self._meter.invoke(steps,scratch,count)
        self._meter.adapter('lane-adapter',len(observation.encoded),len(observation.encoded)+191)
        if len(observation.encoded) == profile.protected_unit_bytes:
            self._meter.adapter('common-frame',191,191)
            self._decode_unit(profile,observation.encoded,observation.erasures)

    @staticmethod
    def _result_workspace(result):
        return (48*len(result.section_results)+40*len(result.fragment_diagnostics)
                +48*len(result.accepted_hypotheses)
                +sum(len(row.envelope or b'') for row in result.section_results)
                +sum(len(row.common_block or b'') for row in result.fragment_diagnostics)
                +len(result.m2_required_stream or b'')+len(result.m2_all_stream or b''))

    def _result_candidate(self, result, prior):
        size = self._result_workspace(result)
        self._meter.adapter('result-selection',size*max(1,len(prior)),size)
        normalized = replace(result,resource=old.ResourceUsage(),accepted_hypotheses=())
        self._meter.retain('path-assembled-streams',0)
        self._meter.retain(('result',normalized),size)
        return normalized

    def _clear_path_storage(self):
        for key in ('path-layout','path-inventory','path-assembled-streams','path-decoded-bodies'):
            self._meter.retain(key,0)

    def _closed(self, state):
        return old.DecodeResult(state,None,(),(),False,resource=self._meter.usage)

    def _decode_units_v2(self, raw):
        if len(raw) > 4194306:
            old._fail('resource-limit')
        if type(raw) is bytes and len(raw) >= 4 and int.from_bytes(raw[:4],'big') > self.maximum_units:
            old._fail('resource-limit')
        observations = old._parse_units(raw,self.maximum_units)
        workspace = sum(8+2*len(row.encoded)+7*(191+8) for row in observations)
        with self._meter.hold(workspace):
            return self._recover_unit_inputs(observations)

    def _recover_unit_inputs(self, observations):
        # The specified ID-major registry schedule charges even wrong-width inputs.
        for observation in sorted(observations,key=lambda row:row.unit_id):
            for profile in self.profiles:
                self._lane(profile,observation,*self.transport_resources[profile.profile_version])
        results = []
        for profile in self.profiles:
            steps,scratch = self.transport_resources[profile.profile_version]
            rep_steps,rep_scratch = self.repetition_resource if self._hierarchical_profile(profile) else (0,0)
            result = self._recover_sections(profile,observations,retain_extra_inputs=True,
                transport_primitive_steps=steps,transport_peak_scratch=scratch,
                repetition_primitive_steps=rep_steps,repetition_peak_scratch=rep_scratch)
            if result.artifact_state == 'resource-limit':
                old._fail('resource-limit')
            if result.inventory_available and profile.profile_version in self.establishing_profile_versions:
                self._result_candidate(result,results)
                results.append(result)
            self._clear_path_storage()
        if not results:
            result = self._without_inventory(self.profiles,observations)
            if result.artifact_state == 'resource-limit':
                old._fail('resource-limit')
            self._result_candidate(result,())
            return replace(result,resource=self._meter.usage)
        unique = {(r.profile_id,self._semantic_key(r)):r for r in results}
        return self._closed('ambiguous') if len(unique) != 1 else replace(next(iter(unique.values())),resource=self._meter.usage)

    def _decode_square(self, side, raw_cells):
        results,eligible,accepted,route_profiles = [],[],{},set()
        paths = 0
        for transform in range(8):
            for polarity in range(2):
                cells = old._Cells(raw_cells,side,transform,polarity)
                self._meter.adapter('square-view',side*side,0)
                routes = self._discover_routes(cells)
                self._meter.retain('view-routes',128*len(routes))
                for route in routes:
                    if paths >= 64:
                        old._fail('resource-limit')
                    paths += 1
                    route_profiles.add(route.profile.profile_id)
                    mapping_sha = self._mapping_digest(route.route_version,
                        self._mapping_projection(route.route_version,route.profile,route.mapping))
                    row = old.AcceptedHypothesis(transform,polarity,route.sector_id,route.profile.profile_id,mapping_sha)
                    accepted[(transform,polarity,route.sector_id,self.profile_order[row.profile_id],mapping_sha)] = row
                    self._meter.retain('accepted-hypotheses',48*len(accepted))
                    observations = self._extract_units(cells,route.profile,route.shell_width,route.mapping)
                    self._path_groups = set()
                    workspace = sum(8+2*len(row.encoded)+191+8 for row in observations)
                    with self._meter.hold(workspace):
                        for observation in observations:
                            self._lane(route.profile,observation,route.transport_primitive_steps,route.transport_peak_scratch)
                        result = self._recover_route_sections(route,observations)
                        if result.artifact_state == 'resource-limit':
                            old._fail('resource-limit')
                        if route.profile.profile_version in self.establishing_profile_versions:
                            normalized = self._result_candidate(result,eligible)
                            if normalized not in eligible:
                                eligible.append(normalized)
                            if result.inventory_available and normalized not in results:
                                results.append(normalized)
                        self._clear_path_storage()
                self._meter.retain('view-routes',0)
        rows = tuple(accepted[key] for key in sorted(accepted))
        profiles = tuple(sorted(route_profiles,key=self.profile_order.__getitem__))
        if len(results) > 1:
            result = self._closed('ambiguous')
        elif results:
            result = results[0]
        elif len(eligible) == 1:
            result = replace(eligible[0],profile_id=None,inventory_available=False)
        else:
            result = self._closed('failure')
        return replace(result,route_profile_ids=profiles,accepted_hypotheses=rows,resource=self._meter.usage)

    def decode(self, channel, raw):
        # Optional computation caches have bounded skip-insertion semantics.
        # They cannot alter availability; semantic state is always per-request.
        self._route_cache.clear()
        self._validated_route_cache.clear()
        self._observed_mappings.clear()
        self._observed_packages.clear()
        self.observed_context_commitments.clear()
        self._route_failure_resources.clear()
        self._current_package = None
        self._path_groups = set()
        self._meter = ResourceMeterV2()
        self._rejected_route_steps = self._rejected_route_scratch = 0
        self.last_rejection = ''
        self._resource_projection = None
        self._observation_sha256 = None
        try:
            if type(raw) is not bytes:
                old._fail('length')
            self._observation_sha256 = sha256(raw).hexdigest()
            self._meter.adapter('observation',len(raw),0)
            if channel == old.OBS_UNITS:
                result = self._decode_units_v2(raw)
            elif channel in (old.OBS_BITS,old.OBS_MATRIX):
                side,cells = old._parse_bits(raw) if channel == old.OBS_BITS else old._parse_matrix(raw)
                with self._meter.hold(len(cells)):
                    result = self._decode_square(side,cells)
            else:
                old._fail('channel')
        except old.DecoderError as error:
            self.last_rejection = error.reason
            result = self._closed('resource-limit' if error.reason == 'resource-limit' else 'failure')
        self._clear_path_storage()
        self._meter.retain('view-routes',0)
        return self._finish_result(channel,result)

    def _finish_result(self, channel, result):
        if channel not in (old.OBS_UNITS,old.OBS_BITS,old.OBS_MATRIX):
            return replace(result,resource=self._meter.usage)
        self._meter.adapter('result-render',0,1048576+256)
        result = replace(result,resource=self._meter.usage)
        render = lambda value: old._render_decoder_result(channel,value,2,
            tuple(p.profile_id for p in self.profiles),
            render_charge=lambda size: self._meter.adapter_work('result-render',size))
        try:
            wire = render(result)
        except old.DecoderError as error:
            if error.reason != 'resource-limit':
                raise
            # The reference writer stops at the first byte outside its slot.
            # Discard partial bytes; the closed result uses the same slot.
            self.last_rejection = error.reason
            result = self._closed('resource-limit')
            self._meter.adapter('result-render',0,1048576+256)
            result = replace(result,resource=self._meter.usage)
            wire = render(result)
        if self._observation_sha256 is not None:
            self._resource_projection = render_resource_projection_v2(channel,self._observation_sha256,
                wire,self._meter.usage,self._meter.adapter_rows,self.policy)
        return result

    def render_resources(self):
        if self._resource_projection is None:
            raise ValueError('resource-observation-absent')
        return self._resource_projection

    def render_result(self, channel, result):
        return old._render_decoder_result(channel,result,2,tuple(p.profile_id for p in self.profiles))
