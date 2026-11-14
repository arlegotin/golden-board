"""Inert numeric document codec. No subject rules or external resources."""
NONE = 65535


class Reader:
    def __init__(self, data):
        self.data = data
        self.offset = 0

    def take(self, count):
        if count < 0 or count > len(self.data) - self.offset:
            raise ValueError(f'Truncated length at byte {self.offset}: need {count}.')
        result = self.data[self.offset:self.offset + count]
        self.offset += count
        return result

    def uint(self, width):
        return int.from_bytes(self.take(width), 'big')

    def integers(self, count, width=2):
        raw = self.take(count * width)
        return [int.from_bytes(raw[i:i + width], 'big') for i in range(0, len(raw), width)]

    def end(self):
        if self.offset != len(self.data):
            raise ValueError(f'Trailing bytes at {self.offset}.')


def _uint(value, width):
    if type(value) is not int or not 0 <= value < 1 << (8 * width):
        raise ValueError(f'Invalid unsigned {width}-byte integer: {value!r}.')
    return value.to_bytes(width, 'big')


def _integers(values, width=2):
    return b''.join(_uint(value, width) for value in values)


def _payload(record):
    kind = record['kind']
    if kind == 1:
        return _integers([record['rows'], record['cols']], 1) + _integers(record['mask'], 1)
    if kind == 2:
        return (_integers([record['rows'], record['cols']], 1) + _integers(record['cells'], 1)
                + _uint(len(record['regions']), 2)
                + b''.join(_integers(region) for region in record['regions']))
    if kind == 3:
        return (_uint(record['initial'], 2) + _uint(len(record['data']), 1)
                + _integers(record['data']) + _uint(len(record['steps']), 4)
                + b''.join(_uint(len(step), 2) + b''.join(
                    _uint(index, 2) + _uint(glyph, 1) for index, glyph in step)
                           for step in record['steps']))
    if kind == 4:
        return (_uint(record['display_kind'], 1) + _uint(record['display'], 2)
                + _uint(record['shape'], 1) + _uint(len(record['choices']), 2)
                + _integers(record['choices']) + _uint(len(record['accepted']), 2)
                + b''.join(_uint(len(response), 2) + _integers(response)
                           for response in record['accepted'])
                + _integers([record['success'], record['failure'], record['passive']])
                + _uint(len(record['links']), 2) + _integers(record['links']))
    if kind == 5:
        return (_uint(record['rows'], 4) + _uint(record['cols'], 1)
                + _integers(record['values']))
    raise ValueError(f'Unknown record kind {kind}.')


def encode_document(entries: list[int], records: list[dict]) -> bytes:
    records = sorted(records, key=lambda record: record['id'])
    if len({record['id'] for record in records}) != len(records):
        raise ValueError('Duplicate record ID.')
    parts = [b'\xd6\x39', _uint(len(entries), 2), _uint(len(records), 2), _integers(entries)]
    for record in records:
        payload = _payload(record)
        parts.extend([_uint(record['kind'], 1), _uint(record['id'], 2),
                      _uint(len(payload), 4), payload])
    result = b''.join(parts)
    decode_document(result)
    return result


def _read_record(kind, ident, data):
    reader = Reader(data)
    record = {'kind': kind, 'id': ident}
    if kind in (1, 2):
        rows, cols = reader.uint(1), reader.uint(1)
        if not rows or not cols:
            raise ValueError('Zero matrix dimension.')
        record.update(rows=rows, cols=cols)
        if kind == 1:
            record['mask'] = list(reader.take((rows * cols + 7) // 8))
            padding = -rows * cols % 8
            if padding and record['mask'][-1] & ((1 << padding) - 1):
                raise ValueError('Nonzero glyph padding.')
        else:
            record['cells'] = list(reader.take(rows * cols))
            count = reader.uint(2)
            raw = Reader(reader.take(count * 4))
            record['regions'] = [[raw.uint(2), raw.uint(2)] for _ in range(count)]
    elif kind == 3:
        record['initial'] = reader.uint(2)
        record['data'] = reader.integers(reader.uint(1))
        count = reader.uint(4)
        if count > (len(data) - reader.offset) // 2:
            raise ValueError('Truncated trace length.')
        steps = []
        for _ in range(count):
            changes = reader.uint(2)
            raw = Reader(reader.take(changes * 3))
            steps.append([[raw.uint(2), raw.uint(1)] for _ in range(changes)])
        record['steps'] = steps
    elif kind == 4:
        record.update(display_kind=reader.uint(1), display=reader.uint(2), shape=reader.uint(1))
        record['choices'] = reader.integers(reader.uint(2))
        count = reader.uint(2)
        if count > (len(data) - reader.offset) // 2:
            raise ValueError('Truncated response count.')
        record['accepted'] = [reader.integers(reader.uint(2)) for _ in range(count)]
        record.update(success=reader.uint(2), failure=reader.uint(2), passive=reader.uint(2))
        record['links'] = reader.integers(reader.uint(2))
    elif kind == 5:
        rows, cols = reader.uint(4), reader.uint(1)
        if not rows or not cols:
            raise ValueError('Zero table dimension.')
        record.update(rows=rows, cols=cols, values=reader.integers(rows * cols))
    else:
        raise ValueError(f'Unknown required record kind {kind}.')
    reader.end()
    return record


def _sorted_unique(values):
    return all(left < right for left, right in zip(values, values[1:]))


def validate_document(document):
    records = document['records']

    def reference(ident, kind):
        if ident not in records or records[ident]['kind'] != kind:
            raise ValueError(f'Dangling/wrong-kind reference {ident}, expected {kind}.')
        return records[ident]

    for record in records.values():
        kind, ident = record['kind'], record['id']
        if ident == NONE:
            raise ValueError('Reserved record ID.')
        if kind == 1 and ident > 255:
            raise ValueError('Glyph ID exceeds octet range.')
        if kind == 2:
            for token in record['cells']:
                reference(token, 1)
            ids = [region[0] for region in record['regions']]
            indices = [region[1] for region in record['regions']]
            if (not _sorted_unique(ids) or NONE in ids or len(set(indices)) != len(indices)
                    or any(index >= len(record['cells']) for index in indices)):
                raise ValueError(f'Invalid selection regions in frame {ident}.')
        if kind == 3:
            initial = reference(record['initial'], 2)
            for ref in record['data']:
                reference(ref, 5)
            for step in record['steps']:
                if not _sorted_unique([change[0] for change in step]):
                    raise ValueError('Noncanonical/duplicate trace change index.')
                for index, token in step:
                    if index >= len(initial['cells']):
                        raise ValueError(f'Trace index {index} outside initial frame.')
                    reference(token, 1)
        if kind == 4:
            if record['display_kind'] not in (0, 1) or record['shape'] not in (0, 1, 2, 3):
                raise ValueError('Unknown display/response shape.')
            display = reference(record['display'], 2 + record['display_kind'])
            frame = display if display['kind'] == 2 else reference(display['initial'], 2)
            region_ids = {region[0] for region in frame['regions']}
            choices = record['choices']
            if not _sorted_unique(choices) or not set(choices) <= region_ids:
                raise ValueError('Choice references invalid region.')
            for ref in record['links']:
                reference(ref, 4)
            if record['shape'] == 0:
                if choices or record['accepted'] or any(record[key] != NONE
                        for key in ('success', 'failure', 'passive')):
                    raise ValueError('Passive page contains practice fields.')
            else:
                if not choices or not record['accepted']:
                    raise ValueError('Practice needs choices and explicit accepted responses.')
                for key in ('success', 'failure', 'passive'):
                    reference(record[key], 4)
                if len({tuple(response) for response in record['accepted']}) != len(record['accepted']):
                    raise ValueError('Duplicate accepted response.')
                for response in record['accepted']:
                    if not set(response) <= set(choices) or len(response) > len(choices):
                        raise ValueError('Accepted response outside choices/shape.')
                    if record['shape'] == 1 and len(response) > 1:
                        raise ValueError('Single response has multiple items.')
                    if record['shape'] == 2 and not _sorted_unique(response):
                        raise ValueError('Set response must be sorted and unique.')
    if not document['entries'] or len(set(document['entries'])) != len(document['entries']):
        raise ValueError('Missing/duplicate entries.')
    for ident in document['entries']:
        if ident not in records or records[ident]['kind'] not in (3, 4):
            raise ValueError(f'Invalid document entry {ident}.')


def decode_document(data: bytes) -> dict:
    reader = Reader(data)
    if reader.take(2) != b'\xd6\x39':
        raise ValueError('Unknown document marker.')
    entry_count, count = reader.uint(2), reader.uint(2)
    entries = reader.integers(entry_count)
    if count > (len(data) - reader.offset) // 7:
        raise ValueError('Truncated record count.')
    records = {}
    last = -1
    for _ in range(count):
        kind, ident, size = reader.uint(1), reader.uint(2), reader.uint(4)
        if ident <= last:
            raise ValueError('Record IDs not unique/increasing.')
        last = ident
        records[ident] = _read_record(kind, ident, reader.take(size))
    reader.end()
    document = {'version': 1, 'entries': entries, 'records': records}
    validate_document(document)
    return document
