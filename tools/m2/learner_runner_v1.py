#!/usr/bin/env python3
"""Explicit revised-stream offline entry; old sibling admission is unchanged."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

if __package__:
    from . import learner_runner as core
else:
    # Python -I excludes the script directory from module search. Load exactly
    # the packaged sibling, without importing anything from the repository.
    specification = importlib.util.spec_from_file_location(
        '_golden_board_learner_core',Path(__file__).with_name('learner_runner.py'))
    if specification is None or specification.loader is None:
        raise RuntimeError('runner core unavailable')
    core = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = core
    specification.loader.exec_module(core)

CONTENT_BYTES = 42432
CONTENT_SHA256 = '141168a051b44f978667f7c562070300d79368ace3fee47f5d19082de7642c17'
CONTENT_ROOT_ID = 588
COMMAND_SCHEMA = 'golden-board.learner-runner-commands/v0'
TRANSCRIPT_SCHEMA = 'golden-board.learner-runner-transcript/v1'
RunnerError = core.RunnerError


def _json(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),sort_keys=True).encode('utf-8')


def _checked(value):
    if type(value) is not int or not 0 <= value <= 0xffffffff:
        raise RunnerError('resource_limit')
    return value


def _add(*values):
    result = 0
    for value in values:
        result = _checked(result+_checked(value))
    return result


def _mul(left,right):
    return _checked(_checked(left)*_checked(right))


@dataclass(frozen=True,slots=True)
class RunnerLimits:
    events: int
    commands: int
    command_bytes: int
    output_bytes: int
    frame_bytes: int
    event_bytes: int


def _parse(raw):
    if len(raw) != CONTENT_BYTES or hashlib.sha256(raw).hexdigest() != CONTENT_SHA256:
        raise RunnerError('content_stream_identity')
    if core._u16(raw,0) != 0:
        raise RunnerError('invalid_content')
    count,cursor,previous,records = core._u16(raw,2),4,0,{}
    for _ in range(count):
        record_id,kind,length = core._u16(raw,cursor),core._u16(raw,cursor+2),core._u32(raw,cursor+4)
        start,end = cursor+8,cursor+8+length
        if record_id <= previous or end > len(raw) or kind not in range(1,15):
            raise RunnerError('invalid_content')
        value = core._parse_payload(record_id,kind,memoryview(raw)[start:end],records)
        records[record_id] = core._Record(record_id,kind,value)
        previous,cursor = record_id,end
    if cursor != len(raw) or previous != CONTENT_ROOT_ID:
        raise RunnerError('invalid_content')
    core._record(records,CONTENT_ROOT_ID,core.KIND_ROOT)
    return records


def _derive_limits(records):
    root = core._record(records,CONTENT_ROOT_ID,core.KIND_ROOT).value
    budget = root['global_event_budget']
    nodes = tuple(record for record in records.values() if record.kind == core.KIND_LESSON_NODE)
    if budget != 4160 or len(nodes) != 65:
        raise RunnerError('source_limits')
    probe = object.__new__(core.StandaloneRunner)
    probe._records = records
    frame_size,event_size = 0,0
    for record in nodes:
        node = record.value
        if node['max_selections'] != 1 or node['response_shape'] != 1 or node['item_event_budget'] != 16:
            raise RunnerError('source_limits')
        regions = core._record(records,node['region_set_ref'],core.KIND_REGION_SET).value['regions']
        selections = ((),) + tuple((r['region_id'],) for r in regions if r['flags'] & 1)
        if len(selections) != 3:
            raise RunnerError('source_limits')
        possibilities = [(phase,0,selection,b'',0,0) for phase in (1,3) for selection in selections]
        longest_response = bytes((1,0,1))+max(s[0] for s in selections if s).to_bytes(2,'big')
        destinations = [(node['default_feedback_ref'],node['default_next_node_ref'])]
        destinations.extend((row['feedback_ref'],row['next_node_ref']) for row in node['cases'])
        possibilities.extend((2,3,(),longest_response,feedback,next_node) for feedback,next_node in destinations)
        for suppressed in (False,True):
            probe._suppressed = suppressed
            for phase,outcome,selection,response,feedback,next_node in possibilities:
                probe._state = core._State(record.record_id,budget,node['item_event_budget'],phase,
                    outcome,selection,response,feedback,next_node,[])
                frame = probe.frame()
                # Both Boolean spellings are reachable; false is one byte longer.
                frame['can_advance'] = False
                frame_size = max(frame_size,len(_json(frame)))
        event_size = max(event_size,len(_json({'action_hex':'01000002','node_id':record.record_id,'result':3})))
    command_count = _mul(2,budget)
    command_shell = len(_json({'schema':COMMAND_SCHEMA,'commands':[]}))+1
    row_sizes = len(_json({'action_hex':'01000002'}))+len(_json({'advance':True}))
    command_bytes = _add(command_shell,_mul(budget,row_sizes),command_count-1)
    wrapper = len(_json({'content_stream_sha256':CONTENT_SHA256,'final_frame':{},
                         'results':[],'schema':TRANSCRIPT_SCHEMA}))+1-2
    output_bytes = _add(wrapper,frame_size,_mul(budget,event_size+1)-1,_mul(13,budget)-1)
    return RunnerLimits(budget,command_count,command_bytes,output_bytes,frame_size,event_size)


class StandaloneRunner(core.StandaloneRunner):
    """The revised identity with the unchanged generic participant runtime."""
    __slots__ = ('_limits',)

    def __init__(self,raw_content: bytes,*,label_suppressed: bool):
        if type(raw_content) is not bytes or type(label_suppressed) is not bool:
            raise TypeError('invalid runner input')
        self._records = _parse(raw_content)
        self._limits = _derive_limits(self._records)
        root = core._record(self._records,CONTENT_ROOT_ID,core.KIND_ROOT).value
        node_id = root['entry_node_ref']
        self._state = core._State(node_id,root['global_event_budget'],self._node(node_id)['item_event_budget'],
                                 1,0,(),b'',0,0,[])
        self._suppressed = label_suppressed

    @property
    def limits(self):
        return self._limits


def _commands(raw,limits):
    if type(raw) is not bytes:
        raise TypeError('commands must be bytes')
    if len(raw) > limits.command_bytes:
        raise RunnerError('commands_limit')
    def unique(pairs):
        result = {}
        for key,value in pairs:
            if key in result:
                raise RunnerError('commands')
            result[key] = value
        return result
    try:
        value = json.loads(raw,object_pairs_hook=unique)
    except (UnicodeDecodeError,json.JSONDecodeError,RecursionError) as error:
        raise RunnerError('commands') from error
    if type(value) is not dict or set(value) != {'schema','commands'} or value['schema'] != COMMAND_SCHEMA:
        raise RunnerError('commands')
    rows = value['commands']
    if type(rows) is not list or len(rows) > limits.commands:
        raise RunnerError('commands_limit')
    actions,advances = 0,0
    for row in rows:
        if type(row) is not dict:
            raise RunnerError('commands')
        if set(row) == {'action_hex'}:
            action = row['action_hex']
            if type(action) is not str or len(action) != 8 or any(c not in '0123456789abcdef' for c in action):
                raise RunnerError('commands')
            actions += 1
        elif set(row) == {'advance'} and row['advance'] is True:
            advances += 1
        else:
            raise RunnerError('commands')
    if actions > limits.events or advances > limits.events:
        raise RunnerError('commands_limit')
    return tuple(rows)


def _run(runner,commands_raw):
    results = []
    for command in _commands(commands_raw,runner.limits):
        if 'action_hex' in command:
            results.append(runner.perform(bytes.fromhex(command['action_hex'])))
        else:
            runner.advance()
            results.append('advanced')
    raw = _json({'content_stream_sha256':CONTENT_SHA256,'final_frame':runner.frame(),
                 'results':results,'schema':TRANSCRIPT_SCHEMA})+b'\n'
    if len(raw) > runner.limits.output_bytes:
        raise RunnerError('output_limit')
    return raw


def run_commands(raw_content: bytes,commands_raw: bytes,*,label_suppressed: bool) -> bytes:
    return _run(StandaloneRunner(raw_content,label_suppressed=label_suppressed),commands_raw)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='m2-learner-runner-v1',allow_abbrev=False)
    parser.add_argument('--content-stream',required=True)
    parser.add_argument('--commands',required=True)
    parser.add_argument('--label-suppressed',action='store_true')
    arguments = parser.parse_args(argv)
    try:
        raw = core._read_regular(arguments.content_stream,CONTENT_BYTES)
        runner = StandaloneRunner(raw,label_suppressed=arguments.label_suppressed)
        commands = core._read_regular(arguments.commands,runner.limits.command_bytes)
        output = _run(runner,commands)
    except RunnerError as error:
        print(f'm2-learner-runner-v1: {error}',file=sys.stderr)
        return 3
    sys.stdout.buffer.write(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
