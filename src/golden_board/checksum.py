"""The explicitly selected CRC-32C convention, with observable bit intermediates."""
MASK = 0x82f63b78


def _entry(value):
    for _ in range(8):
        value = (value >> 1) ^ (MASK if value & 1 else 0)
    return value


TABLE = tuple(_entry(value) for value in range(256))


def crc32c(data: bytes) -> int:
    state = 0xffffffff
    for byte in data:
        state = (state >> 8) ^ TABLE[(state ^ byte) & 255]
    return state ^ 0xffffffff


def byte_trace(byte: int, initial: int = 0xffffffff) -> list[int]:
    if type(byte) is not int or not 0 <= byte <= 255:
        raise ValueError('CRC byte outside octet range.')
    state = initial ^ byte
    states = [initial, state]
    for _ in range(8):
        state = (state >> 1) ^ (MASK if state & 1 else 0)
        states.append(state)
    return states
