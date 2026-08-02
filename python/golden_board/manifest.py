from dataclasses import dataclass
from io import StringIO

from golden_board.identity import scalar_preimage, sha256_hex


MAX_INPUT = 1 << 24
MAX_DEPTH = 64
MAX_COLLECTION = 65_535
MAX_NODES = 1_000_000
MAX_STRING_BYTES = 1 << 24
MAX_U64 = 2**64 - 1
MAX_U64_TEXT = str(MAX_U64)
MANIFEST_PREFIX = b"GB-MANIFEST-v0\x00"
DIAGNOSTICS = (
    "manifest.limit",
    "manifest.utf8",
    "manifest.syntax",
    "manifest.trailing_data",
    "manifest.duplicate_key",
    "manifest.unsupported_type",
    "manifest.integer_range",
    "manifest.invalid_key",
    "manifest.invalid_unicode",
    "manifest.noncanonical",
)
_WHITESPACE = " \t\r\n"
_HEX = frozenset("0123456789abcdefABCDEF")


class ManifestError(ValueError):
    def __init__(self, code: str):
        if code not in DIAGNOSTICS:
            raise ValueError("unknown manifest diagnostic")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class _Number:
    lexeme: str


@dataclass(frozen=True)
class _Array:
    items: list[object]


@dataclass(frozen=True)
class _Object:
    pairs: list[tuple[str, object]]


@dataclass
class _ScanFrame:
    commas: int = 0


def _utf8_width(codepoint: int) -> int:
    if codepoint <= 0x7F:
        return 1
    if codepoint <= 0x7FF:
        return 2
    if codepoint <= 0xFFFF:
        return 3
    return 4


def _scan_string(raw: bytes, start: int) -> int:
    index = start + 1
    decoded_bytes = 0
    while index < len(raw):
        byte = raw[index]
        index += 1
        if byte == 0x22:
            return index
        width = 1
        if byte == 0x5C and index < len(raw):
            escape = raw[index]
            index += 1
            if escape == ord("u"):
                digits = raw[index : index + 4]
                if len(digits) == 4 and all(chr(digit) in _HEX for digit in digits):
                    codepoint = int(digits.decode("ascii"), 16)
                    index += 4
                    if 0xD800 <= codepoint <= 0xDBFF and raw.startswith(b"\\u", index):
                        low_digits = raw[index + 2 : index + 6]
                        if len(low_digits) == 4 and all(chr(digit) in _HEX for digit in low_digits):
                            low = int(low_digits.decode("ascii"), 16)
                            if 0xDC00 <= low <= 0xDFFF:
                                codepoint = 0x10000 + ((codepoint - 0xD800) << 10) + low - 0xDC00
                                index += 6
                    width = _utf8_width(codepoint)
                else:
                    width = 1
        decoded_bytes += width
        if decoded_bytes > MAX_STRING_BYTES:
            raise ManifestError("manifest.limit")
    return index


def _scan_structural_limits(raw: bytes) -> None:
    frames: list[_ScanFrame] = []
    nodes = 0
    index = 0

    def begin_value() -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES:
            raise ManifestError("manifest.limit")

    while index < len(raw):
        byte = raw[index]
        if byte in b" \t\r\n":
            index += 1
            continue
        if byte == 0x22:
            end = _scan_string(raw, index)
            following = end
            while following < len(raw) and raw[following] in b" \t\r\n":
                following += 1
            if following >= len(raw) or raw[following] != 0x3A:
                begin_value()
            index = end
            continue
        if byte in b"[{":
            begin_value()
            frames.append(_ScanFrame())
            if len(frames) > MAX_DEPTH:
                raise ManifestError("manifest.limit")
            index += 1
            continue
        if byte in b"]}":
            if frames:
                frames.pop()
            index += 1
            continue
        if byte == 0x2C:
            if frames:
                frame = frames[-1]
                frame.commas += 1
                if frame.commas >= MAX_COLLECTION:
                    raise ManifestError("manifest.limit")
            index += 1
            continue
        if byte == 0x3A:
            index += 1
            continue
        begin_value()
        index += 1
        while index < len(raw) and raw[index] not in b" \t\r\n[]{}:,\"":
            index += 1


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.index = 0
        self.nodes = 0

    def parse(self) -> object:
        self._skip_whitespace()
        value = self._parse_value(0)
        tail = self.text[self.index :]
        if any(character not in _WHITESPACE for character in tail):
            raise ManifestError("manifest.trailing_data")
        if tail.startswith("\n") and tail != "\n":
            raise ManifestError("manifest.trailing_data")
        return value

    def _skip_whitespace(self) -> None:
        while self.index < len(self.text) and self.text[self.index] in _WHITESPACE:
            self.index += 1

    def _bump_node(self) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise ManifestError("manifest.limit")

    def _parse_value(self, depth: int) -> object:
        self._skip_whitespace()
        if self.index >= len(self.text):
            raise ManifestError("manifest.syntax")
        self._bump_node()
        character = self.text[self.index]
        if character == '"':
            return self._parse_string()
        if character == "{":
            return self._parse_object(depth + 1)
        if character == "[":
            return self._parse_array(depth + 1)
        if character == "t":
            self._consume_literal("true")
            return True
        if character == "f":
            self._consume_literal("false")
            return False
        if character == "n":
            self._consume_literal("null")
            return None
        if character == "-" or "0" <= character <= "9":
            return _Number(self._parse_number())
        raise ManifestError("manifest.syntax")

    def _consume_literal(self, literal: str) -> None:
        if not self.text.startswith(literal, self.index):
            raise ManifestError("manifest.syntax")
        self.index += len(literal)

    def _parse_array(self, depth: int) -> _Array:
        if depth > MAX_DEPTH:
            raise ManifestError("manifest.limit")
        self.index += 1
        self._skip_whitespace()
        items: list[object] = []
        if self._take("]"):
            return _Array(items)
        while True:
            if len(items) >= MAX_COLLECTION:
                raise ManifestError("manifest.limit")
            items.append(self._parse_value(depth))
            self._skip_whitespace()
            if self._take("]"):
                return _Array(items)
            if not self._take(","):
                raise ManifestError("manifest.syntax")

    def _parse_object(self, depth: int) -> _Object:
        if depth > MAX_DEPTH:
            raise ManifestError("manifest.limit")
        self.index += 1
        self._skip_whitespace()
        pairs: list[tuple[str, object]] = []
        if self._take("}"):
            return _Object(pairs)
        while True:
            if len(pairs) >= MAX_COLLECTION:
                raise ManifestError("manifest.limit")
            self._skip_whitespace()
            if self.index >= len(self.text) or self.text[self.index] != '"':
                raise ManifestError("manifest.syntax")
            key = self._parse_string()
            self._skip_whitespace()
            if not self._take(":"):
                raise ManifestError("manifest.syntax")
            pairs.append((key, self._parse_value(depth)))
            self._skip_whitespace()
            if self._take("}"):
                return _Object(pairs)
            if not self._take(","):
                raise ManifestError("manifest.syntax")

    def _take(self, character: str) -> bool:
        if self.index < len(self.text) and self.text[self.index] == character:
            self.index += 1
            return True
        return False

    def _parse_string(self) -> str:
        self.index += 1
        decoded = StringIO()
        decoded_bytes = 0

        def append_decoded(value: str) -> None:
            nonlocal decoded_bytes
            width = _utf8_width(ord(value))
            if decoded_bytes + width > MAX_STRING_BYTES:
                raise ManifestError("manifest.limit")
            decoded_bytes += width
            decoded.write(value)

        while self.index < len(self.text):
            character = self.text[self.index]
            self.index += 1
            if character == '"':
                return decoded.getvalue()
            if character == "\\":
                if self.index >= len(self.text):
                    raise ManifestError("manifest.syntax")
                escape = self.text[self.index]
                self.index += 1
                simple = {
                    '"': '"',
                    "\\": "\\",
                    "/": "/",
                    "b": "\b",
                    "f": "\f",
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                }
                if escape in simple:
                    append_decoded(simple[escape])
                    continue
                if escape != "u":
                    raise ManifestError("manifest.syntax")
                first = self._parse_hex_quad()
                if 0xD800 <= first <= 0xDBFF and self.text.startswith("\\u", self.index):
                    candidate = self.text[self.index + 2 : self.index + 6]
                    if len(candidate) == 4 and all(character in _HEX for character in candidate):
                        second = int(candidate, 16)
                        if 0xDC00 <= second <= 0xDFFF:
                            self.index += 6
                            append_decoded(chr(0x10000 + ((first - 0xD800) << 10) + second - 0xDC00))
                            continue
                append_decoded(chr(first))
                continue
            if ord(character) < 0x20:
                raise ManifestError("manifest.syntax")
            append_decoded(character)
        raise ManifestError("manifest.syntax")

    def _parse_hex_quad(self) -> int:
        digits = self.text[self.index : self.index + 4]
        if len(digits) != 4 or any(character not in _HEX for character in digits):
            raise ManifestError("manifest.syntax")
        self.index += 4
        return int(digits, 16)

    def _parse_number(self) -> str:
        start = self.index
        if self._take("-") and self.index >= len(self.text):
            raise ManifestError("manifest.syntax")
        if self.index >= len(self.text):
            raise ManifestError("manifest.syntax")
        if self.text[self.index] == "0":
            self.index += 1
            if self.index < len(self.text) and "0" <= self.text[self.index] <= "9":
                raise ManifestError("manifest.syntax")
        elif "1" <= self.text[self.index] <= "9":
            while self.index < len(self.text) and "0" <= self.text[self.index] <= "9":
                self.index += 1
        else:
            raise ManifestError("manifest.syntax")
        if self._take("."):
            digit_start = self.index
            while self.index < len(self.text) and "0" <= self.text[self.index] <= "9":
                self.index += 1
            if self.index == digit_start:
                raise ManifestError("manifest.syntax")
        if self.index < len(self.text) and self.text[self.index] in "eE":
            self.index += 1
            if self.index < len(self.text) and self.text[self.index] in "+-":
                self.index += 1
            digit_start = self.index
            while self.index < len(self.text) and "0" <= self.text[self.index] <= "9":
                self.index += 1
            if self.index == digit_start:
                raise ManifestError("manifest.syntax")
        return self.text[start : self.index]


def _decoded_utf8_size(value: str) -> int:
    size = 0
    for character in value:
        size += _utf8_width(ord(character))
        if size > MAX_STRING_BYTES:
            raise ManifestError("manifest.limit")
    return size


def _walk(value: object):
    yield value
    if isinstance(value, _Array):
        for item in value.items:
            yield from _walk(item)
    elif isinstance(value, _Object):
        for _, item in value.pairs:
            yield from _walk(item)


def _validate_semantics(value: object) -> None:
    for node in _walk(value):
        if isinstance(node, _Object):
            seen: set[str] = set()
            for key, _ in node.pairs:
                if key in seen:
                    raise ManifestError("manifest.duplicate_key")
                seen.add(key)
    for node in _walk(value):
        if node is None or isinstance(node, _Number) and any(marker in node.lexeme for marker in ".eE"):
            raise ManifestError("manifest.unsupported_type")
    for node in _walk(value):
        if isinstance(node, _Number):
            digits = node.lexeme.lstrip("-")
            if (
                node.lexeme.startswith("-")
                or len(digits) > len(MAX_U64_TEXT)
                or len(digits) == len(MAX_U64_TEXT) and digits > MAX_U64_TEXT
            ):
                raise ManifestError("manifest.integer_range")
    for node in _walk(value):
        if isinstance(node, _Object):
            for key, _ in node.pairs:
                if any(ord(character) > 0x7F for character in key):
                    raise ManifestError("manifest.invalid_key")
    for node in _walk(value):
        strings: list[str] = []
        if isinstance(node, str):
            strings.append(node)
        elif isinstance(node, _Object):
            strings.extend(key for key, _ in node.pairs)
        if any(0xD800 <= ord(character) <= 0xDFFF for text in strings for character in text):
            raise ManifestError("manifest.invalid_unicode")


def _plain(value: object) -> object:
    if isinstance(value, _Number):
        return int(value.lexeme)
    if isinstance(value, _Array):
        return [_plain(item) for item in value.items]
    if isinstance(value, _Object):
        return {key: _plain(item) for key, item in value.pairs}
    return value


class _Writer:
    def __init__(self):
        self.data = bytearray()

    def add(self, chunk: bytes) -> None:
        if len(self.data) + len(chunk) > MAX_INPUT:
            raise ManifestError("manifest.limit")
        self.data.extend(chunk)


def _escaped_string(value: str) -> bytes:
    _decoded_utf8_size(value)
    output = bytearray(b'"')
    short = {
        '"': b'\\"',
        "\\": b"\\\\",
        "\b": b"\\b",
        "\t": b"\\t",
        "\n": b"\\n",
        "\f": b"\\f",
        "\r": b"\\r",
    }
    for character in value:
        codepoint = ord(character)
        if 0xD800 <= codepoint <= 0xDFFF:
            raise ManifestError("manifest.invalid_unicode")
        if character in short:
            chunk = short[character]
        elif codepoint < 0x20:
            chunk = f"\\u00{codepoint:02x}".encode("ascii")
        else:
            chunk = character.encode("utf-8")
        if len(output) + len(chunk) + 1 > MAX_INPUT:
            raise ManifestError("manifest.limit")
        output.extend(chunk)
    output.extend(b'"')
    return bytes(output)


class _Encoder:
    def __init__(self):
        self.writer = _Writer()
        self.nodes = 0

    def encode(self, value: object) -> bytes:
        self._value(value, 0)
        self.writer.add(b"\n")
        return bytes(self.writer.data)

    def _bump_node(self) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise ManifestError("manifest.limit")

    def _value(self, value: object, depth: int) -> None:
        self._bump_node()
        value_type = type(value)
        if value_type is bool:
            self.writer.add(b"true" if value else b"false")
            return
        if value_type is int:
            if not 0 <= value <= MAX_U64:
                raise ManifestError("manifest.integer_range")
            self.writer.add(str(value).encode("ascii"))
            return
        if value_type is str:
            self.writer.add(_escaped_string(value))
            return
        if value_type is list:
            self._array(value, depth + 1)
            return
        if value_type is dict:
            self._object(value, depth + 1)
            return
        raise ManifestError("manifest.unsupported_type")

    def _array(self, value: list[object], depth: int) -> None:
        if depth > MAX_DEPTH or len(value) > MAX_COLLECTION:
            raise ManifestError("manifest.limit")
        self.writer.add(b"[")
        for index, item in enumerate(value):
            if index:
                self.writer.add(b",")
            self._value(item, depth)
        self.writer.add(b"]")

    def _object(self, value: dict[object, object], depth: int) -> None:
        if depth > MAX_DEPTH or len(value) > MAX_COLLECTION:
            raise ManifestError("manifest.limit")
        for key in value:
            if type(key) is not str:
                raise ManifestError("manifest.invalid_key")
            _decoded_utf8_size(key)
            if any(ord(character) > 0x7F for character in key):
                raise ManifestError("manifest.invalid_key")
            if any(0xD800 <= ord(character) <= 0xDFFF for character in key):
                raise ManifestError("manifest.invalid_unicode")
        self.writer.add(b"{")
        for index, key in enumerate(sorted(value)):
            if index:
                self.writer.add(b",")
            self.writer.add(_escaped_string(key))
            self.writer.add(b":")
            self._value(value[key], depth)
        self.writer.add(b"}")


def decode_canonical_manifest(raw: bytes) -> object:
    if not isinstance(raw, bytes):
        raise ManifestError("manifest.syntax")
    if len(raw) > MAX_INPUT:
        raise ManifestError("manifest.limit")
    _scan_structural_limits(raw)
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise ManifestError("manifest.utf8") from error
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ManifestError("manifest.utf8")
    parsed = _Parser(text).parse()
    _validate_semantics(parsed)
    value = _plain(parsed)
    if encode_canonical_value(value) != raw:
        raise ManifestError("manifest.noncanonical")
    return value


def encode_canonical_value(value: object) -> bytes:
    return _Encoder().encode(value)


def canonical_manifest_hash(raw: bytes) -> str:
    decode_canonical_manifest(raw)
    return sha256_hex(scalar_preimage(MANIFEST_PREFIX, raw))
