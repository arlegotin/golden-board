use sha2::{Digest, Sha256};
use std::fmt;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum IdentityError {
    Prefix,
    Length,
}

impl fmt::Display for IdentityError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::Prefix => "identity.prefix",
            Self::Length => "identity.length",
        })
    }
}

impl std::error::Error for IdentityError {}

fn encode_u16(value: u128) -> Result<[u8; 2], IdentityError> {
    u16::try_from(value)
        .map(u16::to_be_bytes)
        .map_err(|_| IdentityError::Length)
}

fn encode_u32(value: u128) -> Result<[u8; 4], IdentityError> {
    u32::try_from(value)
        .map(u32::to_be_bytes)
        .map_err(|_| IdentityError::Length)
}

pub fn validate_prefix(prefix: &[u8]) -> Result<(), IdentityError> {
    if !(2..=63).contains(&prefix.len())
        || prefix.last() != Some(&0)
        || prefix[..prefix.len() - 1]
            .iter()
            .any(|byte| !(0x20..=0x7e).contains(byte))
    {
        return Err(IdentityError::Prefix);
    }
    Ok(())
}

pub fn scalar_preimage(prefix: &[u8], payload: &[u8]) -> Result<Vec<u8>, IdentityError> {
    validate_prefix(prefix)?;
    let mut result = prefix.to_vec();
    result.extend_from_slice(&encode_u32(payload.len() as u128)?);
    result.extend_from_slice(payload);
    Ok(result)
}

pub fn list_preimage(prefix: &[u8], items: &[&[u8]]) -> Result<Vec<u8>, IdentityError> {
    validate_prefix(prefix)?;
    let mut result = prefix.to_vec();
    result.extend_from_slice(&encode_u16(items.len() as u128)?);
    for item in items {
        result.extend_from_slice(&encode_u32(item.len() as u128)?);
        result.extend_from_slice(item);
    }
    Ok(result)
}

pub fn sha256_hex(preimage: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut result = String::with_capacity(64);
    for byte in Sha256::digest(preimage) {
        result.push(HEX[(byte >> 4) as usize] as char);
        result.push(HEX[(byte & 0x0f) as usize] as char);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::{
        IdentityError, encode_u16, encode_u32, list_preimage, scalar_preimage, sha256_hex,
        validate_prefix,
    };
    use crate::constants::{IDENTITY_TEST_A as A, IDENTITY_TEST_B as B};

    #[test]
    fn known_answers_are_independent_and_lowercase() {
        let cases = [
            (
                scalar_preimage(A, b"").unwrap(),
                "d884e5911a8a923feb85ae9c2b8066eb982234dfe6c6e7f34900988e6dc27a14",
            ),
            (
                scalar_preimage(A, b"\0").unwrap(),
                "788f75a4aec50bc39d44796a9c335e36343c690363de84db24972be2bad5eda1",
            ),
            (
                scalar_preimage(B, b"\0").unwrap(),
                "bd9a12341ac48f633c769140093675496d828dfa9ed21874b725acf3b8870c0e",
            ),
            (
                list_preimage(A, &[]).unwrap(),
                "ce8a5a8230d526db58192616683de0a728d0f6f9198b3ee5ebe55f2fa767a2da",
            ),
            (
                list_preimage(A, &[&b""[..]]).unwrap(),
                "c475f1fbfda9eae9b0ad3e71603bdd6d45ebf545c866bb50f79170bc8895d72c",
            ),
            (
                list_preimage(A, &[&b"\0"[..], &b"\x01\x02"[..]]).unwrap(),
                "ba34053b678a144a645eb524bca6f464ee1923fe5d12f5d32dc29ab80d8a218f",
            ),
            (
                list_preimage(A, &[&b"\x01\x02"[..], &b"\0"[..]]).unwrap(),
                "67b715044915a1337625e8002b7745c620fbf187c68882cef25c163b949125e9",
            ),
        ];
        for (preimage, expected) in cases {
            let actual = sha256_hex(&preimage);
            assert_eq!(expected, actual);
            assert_eq!(64, actual.len());
            assert!(
                actual
                    .bytes()
                    .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            );
        }
    }

    #[test]
    fn preimages_use_exact_big_endian_fields_and_order() {
        assert_eq!(
            [A, &b"\0\0\0\x01\0"[..]].concat(),
            scalar_preimage(A, b"\0").unwrap(),
        );
        assert_eq!(
            [A, &b"\0\x02\0\0\0\x01\0\0\0\0\x02\x01\x02"[..]].concat(),
            list_preimage(A, &[&b"\0"[..], &b"\x01\x02"[..]]).unwrap(),
        );
    }

    #[test]
    fn prefixes_follow_the_frozen_registry_shape() {
        let mut too_long = [b'a'; 64];
        too_long[63] = 0;
        for prefix in [
            &b"missing-nul"[..],
            &b"early\0nul\0"[..],
            &b"\x7f\0"[..],
            &b"\xc3\xa9\0"[..],
            &too_long[..],
            &b"\0"[..],
        ] {
            assert_eq!(Err(IdentityError::Prefix), validate_prefix(prefix));
        }
        assert_eq!(Ok(()), validate_prefix(b" \0"));
        assert_eq!(Ok(()), validate_prefix(b"~\0"));
        let mut maximum = [b'a'; 63];
        maximum[62] = 0;
        assert_eq!(Ok(()), validate_prefix(&maximum));
    }

    #[test]
    fn integer_boundaries_need_no_large_allocations() {
        assert_eq!([0xff; 2], encode_u16(u16::MAX.into()).unwrap());
        assert_eq!([0xff; 4], encode_u32(u32::MAX.into()).unwrap());
        assert_eq!(
            Err(IdentityError::Length),
            encode_u16(u128::from(u16::MAX) + 1)
        );
        assert_eq!(
            Err(IdentityError::Length),
            encode_u32(u128::from(u32::MAX) + 1)
        );
    }
}
