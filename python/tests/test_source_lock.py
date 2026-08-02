import os
from hashlib import sha256
from pathlib import Path, PurePosixPath
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import golden_board.source_lock as source_lock
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
mounts = ["checkout", "uv-tool"]
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
            ("checkout", "uv-tool"),
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

    def test_clean_linux_mounts_are_the_exact_strict_two_mount_model(self):
        for mounts in (
            '["checkout"]',
            '["checkout", "uv-cache"]',
            '["checkout", "uv-tool", "cargo-home"]',
        ):
            with self.subTest(mounts=mounts), self.assertRaises(SourceLockError):
                self.load(
                    VALID.replace(
                        'mounts = ["checkout", "uv-tool"]',
                        f"mounts = {mounts}",
                    )
                )

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

    def test_anthology_path_is_the_sole_authoritative_source(self):
        bad = VALID.replace(
            'path = "docs/64_games.md"', 'path = "docs/other-games.md"'
        )
        with self.assertRaisesRegex(
            SourceLockError, "source_lock.schema: anthology.path"
        ):
            self.load(bad)

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
            payload = root / "payload"
            payload.write_bytes(b"stable size\n")
            payload_identity = (payload.stat().st_dev, payload.stat().st_ino)
            real_fstat = os.fstat
            real_read = os.read
            content_read = False

            def changed_ctime(descriptor):
                facts = real_fstat(descriptor)
                if not content_read or (facts.st_dev, facts.st_ino) != payload_identity:
                    return facts
                return SimpleNamespace(
                    st_dev=facts.st_dev,
                    st_ino=facts.st_ino,
                    st_mode=facts.st_mode,
                    st_size=facts.st_size,
                    st_mtime_ns=facts.st_mtime_ns,
                    st_ctime_ns=facts.st_ctime_ns + 1,
                )

            def mark_content_read(descriptor, count):
                nonlocal content_read
                facts = real_fstat(descriptor)
                if (facts.st_dev, facts.st_ino) == payload_identity:
                    content_read = True
                return real_read(descriptor, count)

            with (
                patch(
                    "golden_board.source_lock.os.fstat", side_effect=changed_ctime
                ),
                patch("golden_board.source_lock.os.read", side_effect=mark_content_read),
                self.assertRaises(SafeFileError),
            ):
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

    def test_linux_held_mount_identity_is_exact_and_fails_closed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "payload"
            payload.write_bytes(b"payload\n")
            root_descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            payload_descriptor = os.open(payload, os.O_RDONLY)
            self.addCleanup(os.close, payload_descriptor)
            self.addCleanup(os.close, root_descriptor)
            same_mount = getattr(
                source_lock, "same_held_mount", lambda *_arguments: None
            )
            with (
                patch.object(
                    source_lock,
                    "sys",
                    SimpleNamespace(platform="linux"),
                    create=True,
                ),
                patch.object(
                    source_lock,
                    "_linux_mount_id",
                    side_effect=(b"41", b"41"),
                    create=True,
                ),
            ):
                self.assertIs(
                    same_mount(root_descriptor, payload_descriptor, payload),
                    True,
                )
            with (
                patch.object(
                    source_lock,
                    "sys",
                    SimpleNamespace(platform="linux"),
                    create=True,
                ),
                patch.object(
                    source_lock,
                    "_linux_mount_id",
                    side_effect=(b"41", b"42"),
                    create=True,
                ),
            ):
                self.assertIs(
                    same_mount(root_descriptor, payload_descriptor, payload),
                    False,
                )
            with (
                patch.object(
                    source_lock,
                    "sys",
                    SimpleNamespace(platform="linux"),
                    create=True,
                ),
                patch.object(
                    source_lock,
                    "_linux_mount_id",
                    side_effect=OSError("fdinfo unavailable"),
                    create=True,
                ),
            ):
                self.assertIs(
                    same_mount(root_descriptor, payload_descriptor, payload),
                    False,
                )

    def test_linux_mount_id_parser_is_bounded_exact_and_complete(self):
        parse = getattr(source_lock, "_parse_mount_id", lambda _raw: None)
        self.assertEqual(
            b"41",
            parse(b"pos:\t0\nflags:\t0100000\nmnt_id:\t41\nino:\t7\n"),
        )
        for raw in (
            b"mnt_id:\t41",
            b"mnt_id:\t0\n",
            b"mnt_id:\t41\nmnt_id:\t42\n",
            b"mnt_id: 41\n",
            b"x" * (source_lock.FDINFO_MAX_BYTES + 1),
        ):
            with self.subTest(raw=raw[:32]), self.assertRaises(OSError):
                parse(raw)

    def test_shared_reader_caches_linux_repository_mount_identity(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "nested/payload").write_bytes(b"payload\n")
            with (
                patch.object(source_lock.sys, "platform", "linux"),
                patch.object(
                    source_lock,
                    "_linux_mount_id",
                    return_value=b"41",
                ) as mount_id,
            ):
                self.assertEqual(
                    b"payload\n",
                    read_regular_below(
                        root, PurePosixPath("nested/payload"), 1024
                    ),
                )
            self.assertEqual(3, mount_id.call_count)

    @unittest.skipUnless(sys.platform == "linux", "Linux fdinfo required")
    def test_real_linux_fdinfo_accepts_ordinary_same_mount_descriptors(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "payload"
            payload.write_bytes(b"payload\n")
            root_descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            payload_descriptor = os.open(payload, os.O_RDONLY)
            try:
                self.assertTrue(
                    source_lock.same_held_mount(
                        root_descriptor, payload_descriptor, payload
                    )
                )
            finally:
                os.close(payload_descriptor)
                os.close(root_descriptor)

    def test_shared_reader_rejects_mount_identity_before_content_read(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "nested/payload").write_bytes(b"must-not-read")
            real_read = os.read

            def reject_payload_read(descriptor: int, count: int) -> bytes:
                if os.fstat(descriptor).st_size == len(b"must-not-read"):
                    raise AssertionError("mounted payload was read")
                return real_read(descriptor, count)

            with (
                patch.object(
                    source_lock,
                    "same_held_mount",
                    return_value=False,
                    create=True,
                ) as mount_check,
                patch.object(source_lock.os, "read", side_effect=reject_payload_read),
                self.assertRaises(SafeFileError),
            ):
                read_regular_below(root, PurePosixPath("nested/payload"), 1024)
            mount_check.assert_called()

    def test_shared_tree_validator_rejects_mount_before_traversal(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / ".git/objects"
            nested.mkdir(parents=True)
            (nested / "object").write_bytes(b"git object")
            nested_identity = (nested.stat().st_dev, nested.stat().st_ino)
            scandir = os.scandir

            def reject_nested_scan(descriptor: int):
                facts = os.fstat(descriptor)
                if (facts.st_dev, facts.st_ino) == nested_identity:
                    raise AssertionError("mounted Git directory was traversed")
                return scandir(descriptor)

            def mount_check(_repository, _descriptor, path: Path) -> bool:
                return path != nested

            validate = getattr(
                source_lock,
                "validate_same_mount_tree",
                lambda *_args, **_kwargs: None,
            )
            with (
                patch.object(
                    source_lock,
                    "same_held_mount",
                    side_effect=mount_check,
                ) as checked,
                patch.object(
                    source_lock.os,
                    "scandir",
                    side_effect=reject_nested_scan,
                ),
                self.assertRaises(SafeFileError),
            ):
                validate(
                    root,
                    PurePosixPath(".git"),
                    max_entries=100,
                    max_depth=8,
                )
            checked.assert_called()

    def test_shared_tree_validator_enforces_entry_cap_lazily(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()

            class Entries:
                def __init__(self) -> None:
                    self.index = 0

                def __enter__(self):
                    return self

                def __exit__(self, *_arguments):
                    return False

                def __iter__(self):
                    return self

                def __next__(self):
                    self.index += 1
                    if self.index == 1:
                        return SimpleNamespace(name="first")
                    if self.index == 2:
                        return SimpleNamespace(name="sentinel")
                    raise AssertionError("tree validator consumed past its cap")

            entries = Entries()
            with (
                patch.object(source_lock.os, "scandir", return_value=entries),
                self.assertRaisesRegex(SafeFileError, r"^safe_tree\.limit$"),
            ):
                source_lock.validate_same_mount_tree(
                    root,
                    PurePosixPath(".git"),
                    max_entries=1,
                    max_depth=8,
                )
            self.assertEqual(2, entries.index)

    def test_shared_tree_validator_rejects_untrusted_paths_and_leaf_types(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            (root / ".git/target").write_bytes(b"target")
            (root / ".git/link").symlink_to("target")
            for relative in (
                ".git",
                PurePosixPath("git\\metadata"),
                PurePosixPath("git\0metadata"),
            ):
                with (
                    self.subTest(relative=relative),
                    self.assertRaisesRegex(SafeFileError, r"^safe_tree\.path$"),
                ):
                    source_lock.validate_same_mount_tree(
                        root,
                        relative,
                        max_entries=10,
                        max_depth=8,
                    )
            with self.assertRaisesRegex(SafeFileError, r"^safe_tree\.type$"):
                source_lock.validate_same_mount_tree(
                    root,
                    PurePosixPath(".git"),
                    max_entries=10,
                    max_depth=8,
                )

    def test_shared_tree_validator_fails_closed_without_double_close(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / ".git/objects"
            nested.mkdir(parents=True)
            git_identity = ((root / ".git").stat().st_dev, (root / ".git").stat().st_ino)
            real_close = os.close
            closed: set[int] = set()
            injected = False

            def close_after_effect(descriptor: int) -> None:
                nonlocal injected
                if descriptor in closed:
                    raise AssertionError("descriptor was closed twice")
                facts = os.fstat(descriptor)
                closed.add(descriptor)
                real_close(descriptor)
                if not injected and (facts.st_dev, facts.st_ino) == git_identity:
                    injected = True
                    raise OSError("injected close failure")

            with (
                patch.object(source_lock.os, "close", side_effect=close_after_effect),
                self.assertRaisesRegex(SafeFileError, r"^safe_tree\.changed$"),
            ):
                source_lock.validate_same_mount_tree(
                    root,
                    PurePosixPath(".git/objects"),
                    max_entries=10,
                    max_depth=8,
                )
            self.assertTrue(injected)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks required")
    def test_shared_link_resolver_stays_inside_same_mount_boundary(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            python_root = root / "artifacts/uv-python"
            target = python_root / "cpython/bin/python3.14"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"python")
            (python_root / "python-relative").symlink_to(
                "cpython/bin/python3.14"
            )
            (python_root / "python-absolute").symlink_to(target)
            for name in ("python-relative", "python-absolute"):
                with self.subTest(name=name):
                    self.assertEqual(
                        PurePosixPath(
                            "artifacts/uv-python/cpython/bin/python3.14"
                        ),
                        source_lock.resolve_same_mount_path(
                            root,
                            PurePosixPath(f"artifacts/uv-python/{name}"),
                            boundary=PurePosixPath("artifacts/uv-python"),
                            max_symlinks=8,
                        ),
                    )

            directory_alias = python_root / "cpython-current"
            directory_alias.symlink_to(target.parents[1])
            self.assertEqual(
                PurePosixPath("artifacts/uv-python/cpython/bin/python3.14"),
                source_lock.resolve_same_mount_path(
                    root,
                    PurePosixPath(
                        "artifacts/uv-python/cpython-current/bin/python3.14"
                    ),
                    boundary=PurePosixPath("artifacts/uv-python"),
                    max_symlinks=8,
                ),
            )

            venv_bin = root / ".venv/bin"
            venv_bin.mkdir(parents=True)
            (venv_bin / "python").symlink_to(directory_alias / "bin/python3.14")
            (venv_bin / "python3").symlink_to("python")
            (venv_bin / "python-relative").symlink_to(
                "../../artifacts/uv-python/cpython-current/bin/python3.14"
            )
            for name in ("python3", "python-relative"):
                with self.subTest(venv_alias=name):
                    self.assertEqual(
                        PurePosixPath(
                            "artifacts/uv-python/cpython/bin/python3.14"
                        ),
                        source_lock.resolve_same_mount_path(
                            root,
                            PurePosixPath(f".venv/bin/{name}"),
                            boundary=PurePosixPath("artifacts/uv-python"),
                            source_boundary=PurePosixPath(".venv/bin"),
                            max_symlinks=8,
                        ),
                    )

            outside = root / "outside"
            outside.write_bytes(b"outside")
            (python_root / "outside-absolute").symlink_to(outside)
            (python_root / "outside-relative").symlink_to("../../outside")
            for name in ("outside-absolute", "outside-relative"):
                with (
                    self.subTest(name=name),
                    self.assertRaisesRegex(SafeFileError, r"^safe_link\.escape$"),
                ):
                    source_lock.resolve_same_mount_path(
                        root,
                        PurePosixPath(f"artifacts/uv-python/{name}"),
                        boundary=PurePosixPath("artifacts/uv-python"),
                        max_symlinks=8,
                    )

            alias = python_root / "oversized"
            alias.symlink_to("cpython")
            boundary_text = "artifacts/uv-python/"
            target_text = "a" * (
                source_lock.SAFE_LINK_PATH_BYTES - len(os.fsencode(boundary_text))
            )
            with (
                patch.object(source_lock.os, "readlink", return_value=target_text),
                self.assertRaisesRegex(SafeFileError, r"^safe_link\.escape$"),
            ):
                source_lock.resolve_same_mount_path(
                    root,
                    PurePosixPath("artifacts/uv-python/oversized/suffix"),
                    boundary=PurePosixPath("artifacts/uv-python"),
                    max_symlinks=8,
                )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks required")
    def test_shared_link_resolver_rejects_chained_mount_before_use(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            python_root = root / "artifacts/uv-python"
            python_root.mkdir(parents=True)
            target = python_root / "target"
            target.write_bytes(b"python")
            alias = python_root / "alias"
            alias.symlink_to("target")

            def mount_check(_repository, _descriptor, path: Path) -> bool:
                return path != target

            with (
                patch.object(
                    source_lock,
                    "same_held_mount",
                    side_effect=mount_check,
                ),
                self.assertRaisesRegex(SafeFileError, r"^safe_link\.mount$"),
            ):
                source_lock.resolve_same_mount_path(
                    root,
                    PurePosixPath("artifacts/uv-python/alias"),
                    boundary=PurePosixPath("artifacts/uv-python"),
                    max_symlinks=8,
                )

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
