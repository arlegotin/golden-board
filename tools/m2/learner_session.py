"""Replay an exported learner session as data, with separate owner scoring."""
import hashlib
import json
from pathlib import Path

from golden_board import canonical_manifest, content, m2_runner
from tools.m2.learner_compile import _wire


def read_session(path: Path):
    with path.open('rb') as source:
        raw = source.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('session too large')
    text = raw.decode('utf-8')
    canonical_manifest._check_input_depth(text)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate session key')
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique)


def review_session(session, raw, owner):
    identity = hashlib.sha256(raw).hexdigest()
    keys = {'schema', 'content_stream_sha256', 'attempt', 'commands', 'events',
            'commitments', 'final_state', 'examples_seen'}
    if type(session) is not dict or set(session) != keys:
        raise ValueError('session shape')
    if (session['schema'] != 'golden-board.learner-prototype-session/v0'
            or session['content_stream_sha256'] != identity
            or owner['content_sha256'] != identity):
        raise ValueError('session content identity')
    if type(session['attempt']) is not int or not 1 <= session['attempt'] <= 65535:
        raise ValueError('attempt')
    commands = session['commands']
    if type(commands) is not list:
        raise ValueError('command count')
    runner = m2_runner.GenericRunner(raw, label_suppressed=True)
    records = {r.record_id:r.payload for r in runner.projection_view.records}
    root = records[runner.projection_view.root_record_id]
    # Each action spends one admitted ROOT event; at most one advance can
    # follow a commit. Derive this limit from the stream, never owner claims.
    if len(commands) > 2 * root.global_event_budget:
        raise ValueError('command count')
    commits = []
    responses = {}
    for command in commands:
        if type(command) is not dict:
            raise ValueError('command shape')
        if set(command) == {'advance'} and command['advance'] is True:
            runner.advance()
        elif set(command) == {'action_hex'}:
            action = command['action_hex']
            if type(action) is not str or len(action) != 8 or any(c not in '0123456789abcdef' for c in action):
                raise ValueError('action shape')
            runner.perform(bytes.fromhex(action))
            if action == '03000000':
                frame = _wire(runner.frame())
                commits.append({key:frame['current_node_id' if key == 'node_id' else key]
                    for key in ('node_id', 'committed_response_hex', 'outcome', 'feedback_ref', 'next_node_ref')})
                encoded = bytes.fromhex(frame['committed_response_hex'])
                responses[frame['current_node_id']] = [int.from_bytes(encoded[i:i+2], 'big')
                                                       for i in range(3, len(encoded), 2)]
        else:
            raise ValueError('command shape')
    frame = _wire(runner.frame())
    state_keys = ('current_node_id', 'global_remaining', 'local_remaining', 'phase',
                  'outcome', 'selection_buffer', 'committed_response_hex',
                  'feedback_ref', 'next_node_ref', 'events')
    def exact(left, right):
        # Python equality equates True/1 and 1.0/1; exported typed values do not.
        return json.dumps(left, sort_keys=True, separators=(',', ':'), allow_nan=False) == json.dumps(
            right, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if (not exact(session['events'], frame['events']) or not exact(session['commitments'], commits)
            or not exact(session['final_state'], {key:frame[key] for key in state_keys})):
        raise ValueError('claimed session state differs from command replay')
    examples = session['examples_seen']
    if type(examples) is not list or len(examples) > 8192:
        raise ValueError('example count')
    for example in examples:
        if type(example) is not dict or set(example) != {'node_id', 'actions_hex'} or type(example['node_id']) is not int:
            raise ValueError('example shape')
        node = records.get(example['node_id'])
        if not isinstance(node, content.ContentLessonNode) or not node.passive_trace_ref:
            raise ValueError('example node')
        if example['actions_hex'] != [action.hex() for action in records[node.passive_trace_ref].actions]:
            raise ValueError('example actions')
    questions = []
    for page in owner['pages']:
        if page['phase'] == 'heldout':
            response = responses.get(page['node_id'])
            questions.append(dict(id=page['id'], family=page['family'],
                answered=response is not None, response_ids=response,
                matches=response is not None and len(response) == 1 and response[0] in page['correct']))
    return dict(schema='golden-board.m2-learner-review/v1', content_stream_sha256=identity,
        complete=frame['phase'] == 2 and frame['next_node_ref'] == 0 and all(q['answered'] for q in questions),
        exhausted=frame['phase'] == 3, command_count=len(commands), commitment_count=len(commits),
        questions=questions, matching_answers=sum(q['matches'] for q in questions),
        question_count=len(questions), examples_reported=len(examples),
        basis='Commands and state replay exactly. Example metadata does not prove viewing order or duration; scoring alone does not establish independent artifact acquisition.')
