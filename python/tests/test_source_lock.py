import os
from hashlib import sha256
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from golden_board.source_lock import (
    MAX_SOURCE_LOCK_BYTES,
    SafeFileError,
    SourceLockError,
    load_source_lock,
    read_regular_below,
)


VALID = """\
[schema]
version = 0

[anthology]
path = "docs/64_games.md"
file_type = "regular"
byte_length = 165145
sha256 = "33d44f7167ab190cc793e3fdfd8190d89ed13c1dc507c20854cf64751c7be7da"
encoding = "UTF-8"
bom = "absent"
newlines = "LF"
final_lf = "present"

[toolchains]
python = "3.14.6"
uv = "0.11.29"
rust = "1.94.0"
cargo = "1.94.0"
git = "2.49.0"
shell = "GNU bash 3.2.57(1)-release as /bin/sh"
host = "Darwin 25.5.0 arm64"
generic_sha256 = "shasum 6.02"
cc = "Apple clang 17.0.0 (clang-1700.0.13.5) at /usr/bin/cc"
ld = "ld-1167.5 selected by /usr/bin/cc"
sdk = "macOS SDK 15.5 selected by /usr/bin/cc"

[[references.reference]]
id = "fips-180-4"
title = "Secure Hash Standard (SHS)"
authority = "NIST"
edition = "FIPS PUB 180-4, August 2015"
locator = "https://doi.org/10.6028/NIST.FIPS.180-4"
role = "normative"
required_at_m0 = true
immutable_id = "doi:10.6028/NIST.FIPS.180-4"
acquired_sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
local_path = "inputs/references/fips-180-4.pdf"

[clean_linux]
mechanism = "docker"
image = "rust:1.94.0-bookworm"
digest = "sha256:365468470075493dc4583f47387001854321c5a8583ea9604b297e67f01c5a4f"
platform_digest = "sha256:94aaa0b45f4d185294474343d9034f829969f6c9ff8101f348b526d105860818"
config_digest = "sha256:4019a0c031b04dec0649a4e4af542125d94d2c9467e19ea6fd4d9e53510fd5e9"
platform = "linux/arm64/v8"
uv_archive = "https://github.com/astral-sh/uv/releases/download/0.11.29/uv-aarch64-unknown-linux-gnu.tar.gz"
uv_archive_sha256 = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
docker_client = "25.0.3"
observed_daemon_state = "unavailable: permission denied for fixed unix:///var/run/docker.sock"
acquisition_protocol = "docker-acquire-v0"
offline_protocol = "docker-offline-v0"
mounts = ["checkout", "uv-cache", "uv-python", "cargo-home", "cargo-target"]
state = "planned"
blocker = "Fixed Docker daemon socket unix:///var/run/docker.sock is not accessible on the primary host"
deadline = "M2"
"""


class SourceLockTests(unittest.TestCase):
    def load(self, text: str = VALID):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "inputs/source-lock.toml"
            path.parent.mkdir()
            path.write_text(text, encoding="utf-8")
            return load_source_lock(root)

    def test_loads_closed_typed_lock(self):
        value = self.load()
        self.assertEqual(0, value.schema_version)
        self.assertEqual("docs/64_games.md", value.anthology.path.as_posix())
        self.assertEqual(165145, value.anthology.byte_length)
        self.assertEqual(
            ("checkout", "uv-cache", "uv-python", "cargo-home", "cargo-target"),
            value.clean_linux.mounts,
        )
        self.assertEqual("fips-180-4", value.references[0].id)
        self.assertEqual(
            "sha256:94aaa0b45f4d185294474343d9034f829969f6c9ff8101f348b526d105860818",
            value.clean_linux.platform_digest,
        )
        self.assertEqual(
            "sha256:4019a0c031b04dec0649a4e4af542125d94d2c9467e19ea6fd4d9e53510fd5e9",
            value.clean_linux.config_digest,
        )

    def test_clean_linux_requires_platform_digest(self):
        bad = VALID.replace(
            'platform_digest = "sha256:94aaa0b45f4d185294474343d9034f829969f6c9ff8101f348b526d105860818"\n',
            "",
        )
        with self.assertRaisesRegex(SourceLockError, "source_lock.schema"):
            self.load(bad)

    def test_rejects_malformed_platform_digest(self):
        bad = VALID.replace(
            'platform_digest = "sha256:94', 'platform_digest = "sha256:GG', 1
        )
        with self.assertRaisesRegex(SourceLockError, "source_lock.clean_linux"):
            self.load(bad)

    def test_clean_linux_requires_valid_config_digest(self):
        missing = VALID.replace(
            'config_digest = "sha256:4019a0c031b04dec0649a4e4af542125d94d2c9467e19ea6fd4d9e53510fd5e9"\n',
            "",
        )
        malformed = VALID.replace(
            'config_digest = "sha256:40', 'config_digest = "sha256:GG', 1
        )
        for bad in (missing, malformed):
            with self.subTest(bad=bad), self.assertRaises(SourceLockError):
                self.load(bad)

    def test_repository_lock_freezes_all_m0_reference_hashes(self):
        from golden_board.reference_acquisition import (
            ARTIFACTS,
            RUST_CONFIG,
            RUST_INDEX,
            RUST_PLATFORM,
        )

        root = Path(__file__).resolve().parents[2]
        value = load_source_lock(root)
        expected = {
            "fide-laws-2023": "e0c8bee28c2dee07b724357b9802fee8591e9d11efd2a910b38e9bd21d3c7643",
            "fide-handbook-index": "ad9367f4bbf2c225eeabbc301a0f016710c69fd24c3cd4aac7db34c747ee8eab",
            "pgn-guide-1994": "2c2445a8c2118a5603610364f8055b31db388e2f4cbc6bb70815bf38ee45de3f",
            "fips-180-4": "0455b406d89648d20cbde375561e19c245b9815e894164c2670772e3d54deb82",
            "nist-sha-byte-kat": "929ef80b7b3418aca026643f6f248815913b60e01741a44bba9e118067f4c9b8",
            "rfc-9260": "04bdd3255e9e5ddf1e401e9d5d726ec2750e5269cb52485db3f7f4fe77500354",
            "ecma-182": "95e5a266a0d96697a05be9b55a141180330dfe94a450b39ffb8b002fbb085366",
            "hamming-1950": "9c7456e29f9550e7e8eb52855632fecadb56506b06e59d9088d988ef75a75cb3",
            "reed-solomon-1960": "86cc4d5ca423a8fe0087446235df29e9a2b273f8488471262a0578a7b999b8c6",
            "voyager-cover": "eac79258cc229db4de1234afa4c8d64a158d287f8c6ee59e175535f0e86b5502",
            "lincos-1960": "a023757ecf16cf41691959243201903c3a7648401896148436b4e1afd827d56d",
            "cosmicos-67e80da": "bd1b07ccb09630202e28ba99311b63befee48cfb96390f727e0eb5ae60070b43",
            "seti-busch-reddick": "0c462605022ee8d9246a42c74046b4760f08d69bdd16189ac85aee57f5f73a5f",
            "seti-heller": "d86d9f4c63e36b70e1992789b58ff57a11e9132238f96fb8c94dc6ecec82b54e",
            "reproducible-builds-definition": "f063776583fae80f7b285b8b3a40829ab25f602c25c07e28e914853f10993a66",
        }
        self.assertEqual(
            expected, {item.id: item.acquired_sha256 for item in value.references}
        )
        artifacts = {item.id: item for item in ARTIFACTS}
        self.assertEqual(
            expected,
            {identifier: artifacts[identifier].sha256 for identifier in expected},
        )
        self.assertTrue(all(item.required_at_m0 for item in value.references))
        self.assertEqual(
            [("fips-180-4", "inputs/references/fips-180-4.pdf")],
            [
                (item.id, item.local_path.as_posix())
                for item in value.references
                if item.local_path is not None
            ],
        )
        self.assertEqual(
            "sha256:365468470075493dc4583f47387001854321c5a8583ea9604b297e67f01c5a4f",
            value.clean_linux.digest,
        )
        self.assertEqual(
            "sha256:94aaa0b45f4d185294474343d9034f829969f6c9ff8101f348b526d105860818",
            value.clean_linux.platform_digest,
        )
        self.assertEqual(
            "sha256:4019a0c031b04dec0649a4e4af542125d94d2c9467e19ea6fd4d9e53510fd5e9",
            value.clean_linux.config_digest,
        )
        self.assertEqual(f"sha256:{RUST_INDEX.sha256}", value.clean_linux.digest)
        self.assertEqual(
            f"sha256:{RUST_PLATFORM.sha256}", value.clean_linux.platform_digest
        )
        self.assertEqual(
            f"sha256:{RUST_CONFIG.sha256}", value.clean_linux.config_digest
        )
        self.assertEqual(
            artifacts["uv-linux-arm64-archive"].url,
            value.clean_linux.uv_archive,
        )
        self.assertEqual(
            artifacts["uv-linux-arm64-archive"].sha256,
            value.clean_linux.uv_archive_sha256,
        )

    def test_repository_fips_snapshot_matches_lock(self):
        root = Path(__file__).resolve().parents[2]
        value = load_source_lock(root)
        reference = next(
            item for item in value.references if item.id == "fips-180-4"
        )
        self.assertIsNotNone(reference.local_path)
        raw = read_regular_below(root, reference.local_path, 1_000_000)
        self.assertEqual(833315, len(raw))
        self.assertEqual(reference.acquired_sha256, sha256(raw).hexdigest())

    def test_rejects_unknown_top_level_key(self):
        with self.assertRaisesRegex(SourceLockError, "source_lock.schema"):
            self.load(VALID + "\n[unexpected]\nvalue = 1\n")

    def test_rejects_parent_traversal(self):
        bad = VALID.replace('path = "docs/64_games.md"', 'path = "../64_games.md"')
        with self.assertRaisesRegex(SourceLockError, "source_lock.path"):
            self.load(bad)

    def test_rejects_noncanonical_repository_path(self):
        for path in ("docs\\\\64_games.md", "docs/\\u000064_games.md"):
            with self.subTest(path=path), self.assertRaisesRegex(
                SourceLockError, "source_lock.path"
            ):
                self.load(
                    VALID.replace('path = "docs/64_games.md"', f'path = "{path}"')
                )

    def test_rejects_nonlowercase_or_malformed_hash(self):
        bad = VALID.replace("33d44f", "33D44f", 1)
        with self.assertRaisesRegex(SourceLockError, "source_lock.sha256"):
            self.load(bad)

    def test_required_reference_needs_frozen_identity_and_hash(self):
        bad = VALID.replace(
            'immutable_id = "doi:10.6028/NIST.FIPS.180-4"', 'immutable_id = ""'
        )
        with self.assertRaisesRegex(SourceLockError, "source_lock.reference"):
            self.load(bad)

    def test_planned_linux_requires_specific_blocker(self):
        bad = VALID.replace(
            'blocker = "Fixed Docker daemon socket unix:///var/run/docker.sock is not accessible on the primary host"',
            'blocker = ""',
        )
        with self.assertRaisesRegex(SourceLockError, "source_lock.clean_linux"):
            self.load(bad)

    def test_verified_linux_forbids_blocker(self):
        bad = VALID.replace('state = "planned"', 'state = "verified"')
        with self.assertRaisesRegex(SourceLockError, "source_lock.clean_linux"):
            self.load(bad)

    def test_rejects_duplicate_reference_id(self):
        reference = VALID.split("[[references.reference]]", 1)[1].split(
            "[clean_linux]", 1
        )[0]
        bad = VALID.replace(
            "[clean_linux]", "[[references.reference]]" + reference + "[clean_linux]"
        )
        with self.assertRaisesRegex(SourceLockError, "source_lock.reference"):
            self.load(bad)

    def test_loader_rejects_symlinked_parent_and_leaf(self):
        for symlink_parent in (False, True):
            with self.subTest(
                symlink_parent=symlink_parent
            ), TemporaryDirectory() as directory:
                root = Path(directory)
                actual = root / "actual-inputs"
                actual.mkdir()
                (actual / "source-lock.toml").write_text(VALID, encoding="utf-8")
                if symlink_parent:
                    (root / "inputs").symlink_to(actual, target_is_directory=True)
                else:
                    (root / "inputs").mkdir()
                    (root / "inputs/source-lock.toml").symlink_to(
                        actual / "source-lock.toml"
                    )
                with self.assertRaises(SourceLockError):
                    load_source_lock(root)

    def test_loader_rejects_fifo_and_oversize_without_blocking(self):
        for kind in ("fifo", "oversize"):
            with self.subTest(kind=kind), TemporaryDirectory() as directory:
                root = Path(directory)
                path = root / "inputs/source-lock.toml"
                path.parent.mkdir()
                if kind == "fifo":
                    os.mkfifo(path)
                else:
                    with path.open("wb") as stream:
                        stream.truncate(MAX_SOURCE_LOCK_BYTES + 1)
                with self.assertRaises(SourceLockError):
                    load_source_lock(root)

    def test_loader_maps_unbounded_integer_to_syntax_error(self):
        bad = VALID.replace("version = 0", "version = " + "9" * 5_000, 1)
        with self.assertRaisesRegex(SourceLockError, "source_lock.syntax"):
            self.load(bad)

    def test_loader_maps_deep_toml_to_syntax_error(self):
        bad = "[schema]\nversion = " + "[" * 2_000 + "0" + "]" * 2_000 + "\n"
        with self.assertRaisesRegex(SourceLockError, "source_lock.syntax"):
            self.load(bad)

    def test_shared_reader_detects_ctime_change_when_mtime_is_restored(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payload").write_bytes(b"stable size\n")
            real_fstat = os.fstat
            calls = 0

            def changed_ctime(descriptor):
                nonlocal calls
                calls += 1
                facts = real_fstat(descriptor)
                if calls == 1:
                    return facts
                return SimpleNamespace(
                    st_dev=facts.st_dev,
                    st_ino=facts.st_ino,
                    st_mode=facts.st_mode,
                    st_size=facts.st_size,
                    st_mtime_ns=facts.st_mtime_ns,
                    st_ctime_ns=facts.st_ctime_ns + 1,
                )

            with patch(
                "golden_board.source_lock.os.fstat", side_effect=changed_ctime
            ), self.assertRaises(SafeFileError):
                read_regular_below(root, PurePosixPath("payload"), 1024)

    def test_shared_reader_handles_short_reads(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            expected = b"short reads still complete\n"
            (root / "payload").write_bytes(expected)
            real_read = os.read

            def one_byte(descriptor, count):
                return real_read(descriptor, min(count, 1))

            with patch("golden_board.source_lock.os.read", side_effect=one_byte):
                self.assertEqual(
                    expected,
                    read_regular_below(root, PurePosixPath("payload"), 1024),
                )

    def test_shared_reader_detects_inode_change(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payload").write_bytes(b"stable size\n")
            real_fstat = os.fstat
            calls = 0

            def changed_inode(descriptor):
                nonlocal calls
                calls += 1
                facts = real_fstat(descriptor)
                if calls == 1:
                    return facts
                return SimpleNamespace(
                    st_dev=facts.st_dev,
                    st_ino=facts.st_ino + 1,
                    st_mode=facts.st_mode,
                    st_size=facts.st_size,
                    st_mtime_ns=facts.st_mtime_ns,
                    st_ctime_ns=facts.st_ctime_ns,
                )

            with patch(
                "golden_board.source_lock.os.fstat", side_effect=changed_inode
            ), self.assertRaises(SafeFileError):
                read_regular_below(root, PurePosixPath("payload"), 1024)

    def test_shared_reader_rejects_directory_and_missing_capability(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "directory").mkdir()
            with self.assertRaises(SafeFileError):
                read_regular_below(root, PurePosixPath("directory"), 1024)
            (root / "payload").write_bytes(b"payload\n")
            with patch(
                "golden_board.source_lock.os.O_NOFOLLOW", None
            ), self.assertRaises(SafeFileError):
                read_regular_below(root, PurePosixPath("payload"), 1024)

    def test_shared_reader_rejects_non_posix_and_backslash_paths(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "payload",
                PurePosixPath("folder\\payload"),
                PurePosixPath("nul\0payload"),
            ):
                with self.subTest(relative=relative), self.assertRaises(SafeFileError):
                    read_regular_below(root, relative, 1024)

    def test_shared_reader_closes_each_descriptor_once_after_close_error(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "nested/payload").write_bytes(b"payload\n")
            real_open = os.open
            real_close = os.close
            opened = []
            closed = []

            def record_open(*args, **kwargs):
                descriptor = real_open(*args, **kwargs)
                opened.append(descriptor)
                return descriptor

            def fail_first_close(descriptor):
                closed.append(descriptor)
                real_close(descriptor)
                if len(closed) == 1:
                    raise OSError("injected close failure")

            with (
                patch("golden_board.source_lock.os.open", side_effect=record_open),
                patch("golden_board.source_lock.os.close", side_effect=fail_first_close),
                self.assertRaises(SafeFileError),
            ):
                read_regular_below(root, PurePosixPath("nested/payload"), 1024)
            self.assertEqual(list(reversed(opened)), closed)
            self.assertEqual(len(closed), len(set(closed)))

    def test_shared_reader_closes_every_descriptor_after_read_error(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payload").write_bytes(b"payload\n")
            real_open = os.open
            real_close = os.close
            opened = []
            closed = []

            def record_open(*args, **kwargs):
                descriptor = real_open(*args, **kwargs)
                opened.append(descriptor)
                return descriptor

            def record_close(descriptor):
                closed.append(descriptor)
                return real_close(descriptor)

            with (
                patch("golden_board.source_lock.os.open", side_effect=record_open),
                patch("golden_board.source_lock.os.close", side_effect=record_close),
                patch(
                    "golden_board.source_lock.os.read",
                    side_effect=OSError("injected read failure"),
                ),
                self.assertRaises(SafeFileError),
            ):
                read_regular_below(root, PurePosixPath("payload"), 1024)
            self.assertLessEqual(set(opened), set(closed))


if __name__ == "__main__":
    unittest.main()
