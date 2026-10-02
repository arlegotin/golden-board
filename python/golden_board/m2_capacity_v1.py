"""Actual revised-slice costs with independently verified historical prototypes."""
from dataclasses import replace
import hashlib

from . import capacity, content, m2_slice


def derive_capacity_inputs_v1(compiled, prototype_source, blueprint):
    """Keep the old allowance while charging every new real body frame."""
    if type(compiled) is not m2_slice.SliceCompilation:
        raise TypeError('expected SliceCompilation')
    base = capacity.derive_capacity_inputs(prototype_source, blueprint)
    if (prototype_source.content_sha256 != 'de7e22f0aa4316d9f32d9435287dd19bd6c04519aae1dc9bd816613f26929671'
            or compiled.capacity_prototypes != prototype_source.capacity_prototypes):
        raise capacity.CapacityError('prototype_source', 'slice-v0')
    for raw, digest, projection in (
        (compiled.content_bytes, compiled.content_sha256, compiled.projection),
        (compiled.required_content_bytes, compiled.required_content_sha256, compiled.required_projection),
    ):
        if hashlib.sha256(raw).hexdigest() != digest or content.projection_view(content.stream_validation(raw)) != projection:
            raise capacity.CapacityError('invalid_slice', 'content')
    all_frames = capacity._frames(compiled.content_bytes, 'all')
    required_frames = capacity._frames(compiled.required_content_bytes, 'required')
    sections, assigned, required_ids = [], [], []
    for assignment in compiled.atomic_assignments:
        if assignment.closure not in ('m2_required', 'm2_all_only') or assignment.semantic_copy_id != 0:
            raise capacity.CapacityError('invalid_slice', 'assignment')
        try:
            size = sum(len(all_frames[rid]) for rid in assignment.record_ids)
        except KeyError as error:
            raise capacity.CapacityError('section_reference', 'assignment') from error
        if not assignment.record_ids or not 0 < size <= 16384:
            raise capacity.CapacityError('section_length', 'assignment')
        assigned.extend(assignment.record_ids)
        if assignment.closure == 'm2_required':
            required_ids.extend(assignment.record_ids)
        sections.append(capacity.RealSliceSection(assignment.section_id,
            assignment.closure, size, assignment.record_ids))
    if (assigned != list(all_frames)[:-1] or required_ids != list(required_frames)[:-1]
            or any(all_frames[rid] != required_frames[rid] for rid in required_ids)
            or len({section.section_id for section in sections}) != len(sections)):
        raise capacity.CapacityError('section_coverage', 'assignment')
    tiers = []
    if tuple((item.section_id, item.closure, item.semantic_copy_id) for item in compiled.tier_roots) != (
        (2, 'm2_required', 0), (3, 'm2_all', 0)
    ):
        raise capacity.CapacityError('tier_coverage', 'roots')
    for item in compiled.tier_roots:
        raw = compiled.required_content_bytes if item.section_id == 2 else compiled.content_bytes
        frames = required_frames if item.section_id == 2 else all_frames
        if item.record_id != list(frames)[-1]:
            raise capacity.CapacityError('tier_reference', 'roots')
        body = tuple(section.section_id for section in sections
                     if item.section_id == 3 or section.closure == 'm2_required')
        length = len(frames[item.record_id])
        tiers.append(capacity.TierFrameInput(item.section_id, item.closure,
            22 + 4 * len(body) + length, len(raw), len(frames), body, length))
    return replace(base, slice_semantic_sha256=compiled.content_sha256,
                   real_content_sections=tuple(sections), tier_frames=tuple(tiers))
