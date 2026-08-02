#![forbid(unsafe_code)]

use golden_board_core::{canonical_manifest_hash, list_preimage, scalar_preimage, sha256_hex};
use std::ffi::OsString;
use std::io::{self, Read, Write};

const IDENTITY_A: &[u8] = b"GB-IDENTITY-TEST-A-v0\0";
const IDENTITY_B: &[u8] = b"GB-IDENTITY-TEST-B-v0\0";
const MAX_INPUT: usize = 1 << 24;
const BODY_CAP: usize = MAX_INPUT + 1;
const MAX_OUTPUT: usize = 128;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum AdapterError {
    Usage,
    Framing,
    Limit,
    Io,
    Internal,
}

impl AdapterError {
    fn message(self) -> &'static [u8] {
        match self {
            Self::Usage => b"adapter.usage\n",
            Self::Framing => b"adapter.framing\n",
            Self::Limit => b"adapter.limit\n",
            Self::Io => b"adapter.io\n",
            Self::Internal => b"adapter.internal\n",
        }
    }
}

#[derive(Clone, Copy)]
enum Operation {
    IdentityAScalar,
    IdentityBScalar,
    IdentityAList,
    Manifest,
}

fn main() {
    if let Err(error) = run(std::env::args_os()) {
        let mut stderr = io::stderr().lock();
        let _ = stderr.write_all(error.message());
        let _ = stderr.flush();
        std::process::exit(2);
    }
}

fn run(arguments: impl Iterator<Item = OsString>) -> Result<(), AdapterError> {
    let operation = parse_operation(arguments)?;
    let mut stdin = io::stdin().lock();
    let body = read_body(&mut stdin)?;
    let output = execute(operation, &body)?;
    write_bounded(&mut io::stdout().lock(), &output)
}

fn parse_operation(
    mut arguments: impl Iterator<Item = OsString>,
) -> Result<Operation, AdapterError> {
    arguments.next().ok_or(AdapterError::Usage)?;
    let operation = arguments.next().ok_or(AdapterError::Usage)?;
    if arguments.next().is_some() {
        return Err(AdapterError::Usage);
    }
    match operation.to_str() {
        Some("identity-a-scalar") => Ok(Operation::IdentityAScalar),
        Some("identity-b-scalar") => Ok(Operation::IdentityBScalar),
        Some("identity-a-list") => Ok(Operation::IdentityAList),
        Some("manifest") => Ok(Operation::Manifest),
        _ => Err(AdapterError::Usage),
    }
}

fn read_body(reader: &mut impl Read) -> Result<Vec<u8>, AdapterError> {
    read_bounded(reader, BODY_CAP)
}

fn read_bounded(reader: &mut impl Read, body_cap: usize) -> Result<Vec<u8>, AdapterError> {
    let mut body = Vec::new();
    let mut chunk = [0_u8; 8192];
    while body.len() < body_cap {
        let remaining = body_cap - body.len();
        let chunk_length = remaining.min(chunk.len());
        let read = reader
            .read(&mut chunk[..chunk_length])
            .map_err(|_| AdapterError::Io)?;
        if read == 0 {
            return Ok(body);
        }
        body.try_reserve_exact(read)
            .map_err(|_| AdapterError::Internal)?;
        body.extend_from_slice(&chunk[..read]);
    }
    let mut sentinel = [0_u8; 1];
    match reader.read(&mut sentinel).map_err(|_| AdapterError::Io)? {
        0 => Ok(body),
        _ => Err(AdapterError::Limit),
    }
}

fn execute(operation: Operation, body: &[u8]) -> Result<Vec<u8>, AdapterError> {
    match operation {
        Operation::IdentityAScalar => identity_scalar(IDENTITY_A, body),
        Operation::IdentityBScalar => identity_scalar(IDENTITY_B, body),
        Operation::IdentityAList => identity_list(body),
        Operation::Manifest => match canonical_manifest_hash(body) {
            Ok(digest) => success(&digest),
            Err(error) => rejection(error.code()),
        },
    }
}

fn identity_scalar(prefix: &[u8], body: &[u8]) -> Result<Vec<u8>, AdapterError> {
    let preimage = scalar_preimage(prefix, body).map_err(|_| AdapterError::Internal)?;
    success(&sha256_hex(&preimage))
}

fn identity_list(body: &[u8]) -> Result<Vec<u8>, AdapterError> {
    let mut remaining = body;
    let count = u16::from_be_bytes(take_array(&mut remaining)?);
    let mut items = Vec::with_capacity(usize::from(count));
    for _ in 0..count {
        let length = usize::try_from(u32::from_be_bytes(take_array(&mut remaining)?))
            .map_err(|_| AdapterError::Framing)?;
        items.push(take(&mut remaining, length)?);
    }
    if !remaining.is_empty() {
        return Err(AdapterError::Framing);
    }
    let preimage = list_preimage(IDENTITY_A, &items).map_err(|_| AdapterError::Internal)?;
    success(&sha256_hex(&preimage))
}

fn take_array<const N: usize>(remaining: &mut &[u8]) -> Result<[u8; N], AdapterError> {
    take(remaining, N)?
        .try_into()
        .map_err(|_| AdapterError::Framing)
}

fn take<'a>(remaining: &mut &'a [u8], length: usize) -> Result<&'a [u8], AdapterError> {
    let (value, tail) = remaining
        .split_at_checked(length)
        .ok_or(AdapterError::Framing)?;
    *remaining = tail;
    Ok(value)
}

fn success(digest: &str) -> Result<Vec<u8>, AdapterError> {
    if digest.len() != 64
        || !digest
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(AdapterError::Internal);
    }
    bounded_output(&[b"ok\t", digest.as_bytes(), b"\n"])
}

fn rejection(code: &str) -> Result<Vec<u8>, AdapterError> {
    bounded_output(&[b"err\t", code.as_bytes(), b"\n"])
}

fn bounded_output(parts: &[&[u8]]) -> Result<Vec<u8>, AdapterError> {
    let length = parts.iter().try_fold(0_usize, |total, part| {
        total.checked_add(part.len()).ok_or(AdapterError::Internal)
    })?;
    if length > MAX_OUTPUT {
        return Err(AdapterError::Internal);
    }
    let mut output = Vec::with_capacity(length);
    for part in parts {
        output.extend_from_slice(part);
    }
    Ok(output)
}

fn write_bounded(writer: &mut impl Write, output: &[u8]) -> Result<(), AdapterError> {
    if output.len() > MAX_OUTPUT {
        return Err(AdapterError::Internal);
    }
    writer.write_all(output).map_err(|_| AdapterError::Io)?;
    writer.flush().map_err(|_| AdapterError::Io)
}

#[cfg(test)]
mod tests {
    use super::{AdapterError, identity_list, read_body, read_bounded, write_bounded};
    use std::io::{self, Read, Write};

    struct FailingReader;

    impl Read for FailingReader {
        fn read(&mut self, _: &mut [u8]) -> io::Result<usize> {
            Err(io::Error::other("injected"))
        }
    }

    struct CountingReader {
        remaining: usize,
        read: usize,
    }

    impl Read for CountingReader {
        fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
            let amount = buffer.len().min(self.remaining);
            buffer[..amount].fill(0);
            self.remaining -= amount;
            self.read += amount;
            Ok(amount)
        }
    }

    struct FailingWriter;

    impl Write for FailingWriter {
        fn write(&mut self, _: &[u8]) -> io::Result<usize> {
            Err(io::Error::other("injected"))
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    #[test]
    fn read_errors_are_adapter_errors() {
        assert_eq!(Err(AdapterError::Io), read_body(&mut FailingReader));
    }

    #[test]
    fn overflow_reads_exactly_one_sentinel_byte() {
        let mut reader = CountingReader {
            remaining: 10,
            read: 0,
        };
        assert_eq!(Err(AdapterError::Limit), read_bounded(&mut reader, 3));
        assert_eq!(4, reader.read);
    }

    #[test]
    fn output_errors_are_adapter_errors() {
        assert_eq!(
            Err(AdapterError::Io),
            write_bounded(&mut FailingWriter, b"ok\n")
        );
    }

    #[test]
    fn list_framing_requires_exact_exhaustion() {
        for raw in [
            &b""[..],
            &b"\0"[..],
            &b"\0\0x"[..],
            &b"\0\x01\0\0\0\x02x"[..],
        ] {
            assert_eq!(Err(AdapterError::Framing), identity_list(raw));
        }
    }
}
