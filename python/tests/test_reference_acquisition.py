from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch
from urllib.request import ProxyHandler

from golden_board import reference_acquisition

from golden_board.reference_acquisition import (
    ARTIFACTS,
    AcquisitionError,
    Artifact,
    RUST_CONFIG,
    RUST_INDEX,
    RUST_PLATFORM,
    acquire_all,
    select_image_config,
    select_linux_arm64_manifest,
    validate_image_config,
    verify_bytes,
    write_exact,
)


class ReferenceAcquisitionTests(unittest.TestCase):
    def test_artifact_table_is_closed_unique_and_pinned(self):
        expected_ids = (
            "fide-laws-2023",
            "fide-handbook-index",
            "pgn-guide-1994",
            "fips-180-4",
            "nist-sha-byte-kat",
            "rfc-9260",
            "ecma-182",
            "hamming-1950",
            "reed-solomon-1960",
            "voyager-cover",
            "lincos-1960",
            "cosmicos-67e80da",
            "seti-busch-reddick",
            "seti-heller",
            "reproducible-builds-definition",
            "uv-linux-arm64-archive",
            "uv-linux-arm64-checksum",
        )
        self.assertEqual(expected_ids, tuple(item.id for item in ARTIFACTS))
        self.assertEqual(len(ARTIFACTS), len({item.filename for item in ARTIFACTS}))
        self.assertTrue(all(item.url.startswith("https://") for item in ARTIFACTS))
        self.assertTrue(
            all(
                len(item.sha256) == 64
                and set(item.sha256) <= set("0123456789abcdef")
                and item.byte_length > 0
                for item in ARTIFACTS
            )
        )
        by_id = {item.id: item for item in ARTIFACTS}
        self.assertEqual(833315, by_id["fips-180-4"].byte_length)
        self.assertEqual(
            "94500fb064ae3c971a873cba64d94694c50677e0a4dbf78735c80509e7429919",
            by_id["uv-linux-arm64-archive"].sha256,
        )
        self.assertEqual(
            "ea4b3b400502856fae8d8504649e32f9a2faba2f871a235b99c4935cfb2a51cf",
            by_id["uv-linux-arm64-checksum"].sha256,
        )
        pinned_rows = [
            "|".join(
                (
                    item.id,
                    item.filename,
                    item.url,
                    item.sha256,
                    str(item.byte_length),
                    item.accept,
                )
            )
            for item in (*ARTIFACTS, RUST_INDEX, RUST_PLATFORM, RUST_CONFIG)
        ]
        pinned_rows.extend(
            (
                f"TOKEN_URL|{reference_acquisition.TOKEN_URL}",
                f"USER_AGENT|{reference_acquisition.USER_AGENT}",
                "NETWORK_DEADLINE_SECONDS|"
                f"{reference_acquisition.NETWORK_DEADLINE_SECONDS}",
            )
        )
        pinned = "\n".join(pinned_rows).encode("utf-8")
        self.assertEqual(
            "86a8b348a405fdec66b5cc20c92fe2efd6197eaf051b81347084d248285b99f6",
            sha256(pinned).hexdigest(),
        )
        checksum_line = (
            f'{by_id["uv-linux-arm64-archive"].sha256}  '
            f'{by_id["uv-linux-arm64-archive"].filename}\n'
        ).encode("ascii")
        checksum = by_id["uv-linux-arm64-checksum"]
        self.assertEqual(checksum.byte_length, len(checksum_line))
        self.assertEqual(checksum.sha256, sha256(checksum_line).hexdigest())

    def test_verify_bytes_rejects_length_and_hash_drift(self):
        good = Artifact(
            id="fixture",
            filename="fixture.bin",
            url="https://example.invalid/fixture.bin",
            sha256=sha256(b"ok").hexdigest(),
            byte_length=2,
        )
        verify_bytes(good, b"ok")
        with self.assertRaisesRegex(AcquisitionError, "byte_length"):
            verify_bytes(good, b"bad")
        with self.assertRaisesRegex(AcquisitionError, "sha256"):
            verify_bytes(replace(good, sha256="0" * 64), b"ok")

    def test_selects_unique_linux_arm64_v8_manifest(self):
        raw = json.dumps(
            {
                "manifests": [
                    {
                        "digest": "sha256:" + "1" * 64,
                        "size": 100,
                        "platform": {"os": "linux", "architecture": "amd64"},
                    },
                    {
                        "digest": "sha256:" + "2" * 64,
                        "mediaType": reference_acquisition.OCI_MANIFEST,
                        "size": 1942,
                        "platform": {
                            "os": "linux",
                            "architecture": "arm64",
                            "variant": "v8",
                        },
                    },
                ]
            },
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(
            ("sha256:" + "2" * 64, 1942),
            select_linux_arm64_manifest(raw),
        )

    def test_rejects_ambiguous_linux_arm64_v8_manifest(self):
        descriptor = {
            "digest": "sha256:" + "2" * 64,
            "mediaType": reference_acquisition.OCI_MANIFEST,
            "size": 1942,
            "platform": {"os": "linux", "architecture": "arm64", "variant": "v8"},
        }
        raw = json.dumps({"manifests": [descriptor, descriptor]}).encode("utf-8")
        with self.assertRaisesRegex(AcquisitionError, "unique linux/arm64/v8"):
            select_linux_arm64_manifest(raw)

    def test_rejects_linux_arm64_v8_manifest_with_unknown_media_type(self):
        descriptor = {
            "digest": "sha256:" + "2" * 64,
            "mediaType": "application/x-untrusted-manifest",
            "size": 1942,
            "platform": {"os": "linux", "architecture": "arm64", "variant": "v8"},
        }
        raw = json.dumps({"manifests": [descriptor]}).encode("utf-8")
        with self.assertRaisesRegex(AcquisitionError, "unique linux/arm64/v8"):
            select_linux_arm64_manifest(raw)

    def test_rejects_malformed_oci_descriptor_digests_and_sizes(self):
        index_descriptor = {
            "digest": "sha256:" + "2" * 64,
            "mediaType": reference_acquisition.OCI_MANIFEST,
            "size": 1942,
            "platform": {"os": "linux", "architecture": "arm64", "variant": "v8"},
        }
        config_descriptor = {
            "mediaType": reference_acquisition.OCI_CONFIG,
            "digest": "sha256:" + "4" * 64,
            "size": 4734,
        }
        for field, value in (("digest", "sha256:GG"), ("size", 0), ("size", -1)):
            with self.subTest(adapter="index", field=field, value=value):
                descriptor = index_descriptor | {field: value}
                raw = json.dumps({"manifests": [descriptor]}).encode("utf-8")
                with self.assertRaises(AcquisitionError):
                    select_linux_arm64_manifest(raw)
            with self.subTest(adapter="config", field=field, value=value):
                descriptor = config_descriptor | {field: value}
                raw = json.dumps({"config": descriptor}).encode("utf-8")
                with self.assertRaises(AcquisitionError):
                    select_image_config(raw)

    def test_acquisition_verifies_each_download_before_the_next_request(self):
        with patch.object(
            reference_acquisition, "_get", return_value=b""
        ) as request, self.assertRaisesRegex(AcquisitionError, "byte_length"):
            acquire_all()
        self.assertEqual(1, request.call_count)

    def test_acquisition_requires_exact_uv_checksum_line(self):
        with (
            patch.object(reference_acquisition, "_get", return_value=b"wrong"),
            patch.object(reference_acquisition, "verify_bytes"),
            self.assertRaisesRegex(AcquisitionError, "uv checksum"),
        ):
            acquire_all()

    def test_json_adapters_normalize_resource_errors(self):
        huge_integer = b"9" * 5_000
        cases = (
            (select_linux_arm64_manifest, b'{"manifests":[' + huge_integer + b"]}"),
            (select_image_config, b'{"config":' + huge_integer + b"}"),
            (validate_image_config, b'{"config":' + huge_integer + b"}"),
        )
        for function, raw in cases:
            with self.subTest(function=function.__name__), self.assertRaises(
                AcquisitionError
            ):
                function(raw)
        with patch.object(
            reference_acquisition, "_get", return_value=b'{"token":' + huge_integer + b"}"
        ), self.assertRaises(AcquisitionError):
            reference_acquisition._token()

    def test_acquisition_opener_ignores_ambient_proxies(self):
        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://127.0.0.1:9",
                "HTTPS_PROXY": "http://127.0.0.1:9",
            },
            clear=True,
        ):
            ambient = reference_acquisition.build_opener()
            direct = reference_acquisition._direct_opener()
        self.assertTrue(any(isinstance(item, ProxyHandler) for item in ambient.handlers))
        self.assertFalse(any(isinstance(item, ProxyHandler) for item in direct.handlers))

    def test_network_read_uses_exclusive_wall_deadline(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"ok"
        with (
            patch.object(
                reference_acquisition.signal, "getitimer", return_value=(0.0, 0.0)
            ),
            patch.object(
                reference_acquisition.signal,
                "signal",
                return_value=reference_acquisition.signal.SIG_DFL,
            ) as signal_handler,
            patch.object(reference_acquisition.signal, "setitimer") as timer,
            patch.object(reference_acquisition._OPENER, "open", return_value=response),
        ):
            self.assertEqual(
                b"ok",
                reference_acquisition._get(
                    "https://example.invalid/reference", "*/*", 2
                ),
            )
        self.assertEqual(
            [
                (
                    reference_acquisition.signal.ITIMER_REAL,
                    reference_acquisition.NETWORK_DEADLINE_SECONDS,
                ),
                (reference_acquisition.signal.ITIMER_REAL, 0.0),
            ],
            [call.args for call in timer.call_args_list],
        )
        self.assertEqual(2, signal_handler.call_count)
        self.assertEqual(
            (
                reference_acquisition.signal.SIGALRM,
                reference_acquisition.signal.SIG_DFL,
            ),
            signal_handler.call_args_list[-1].args,
        )

        with (
            patch.object(
                reference_acquisition.signal, "getitimer", return_value=(1.0, 0.0)
            ),
            patch.object(reference_acquisition._OPENER, "open") as request,
            self.assertRaisesRegex(AcquisitionError, "deadline"),
        ):
            reference_acquisition._get(
                "https://example.invalid/reference", "*/*", 2
            )
        request.assert_not_called()

    def test_network_deadline_restores_handler_when_timer_cancel_fails(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"ok"
        with (
            patch.object(
                reference_acquisition.signal, "getitimer", return_value=(0.0, 0.0)
            ),
            patch.object(
                reference_acquisition.signal,
                "signal",
                return_value=reference_acquisition.signal.SIG_DFL,
            ) as signal_handler,
            patch.object(
                reference_acquisition.signal,
                "setitimer",
                side_effect=(None, OSError("injected timer cancellation failure")),
            ),
            patch.object(reference_acquisition._OPENER, "open", return_value=response),
            self.assertRaisesRegex(AcquisitionError, "cleanup"),
        ):
            reference_acquisition._get(
                "https://example.invalid/reference", "*/*", 2
            )
        self.assertEqual(2, signal_handler.call_count)
        self.assertEqual(
            (
                reference_acquisition.signal.SIGALRM,
                reference_acquisition.signal.SIG_DFL,
            ),
            signal_handler.call_args_list[-1].args,
        )

    def test_network_deadline_fails_closed_and_cleans_up_after_read_error(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.side_effect = TimeoutError("injected read timeout")
        with (
            patch.object(
                reference_acquisition.signal, "getitimer", return_value=(0.0, 0.0)
            ),
            patch.object(
                reference_acquisition.signal,
                "signal",
                return_value=reference_acquisition.signal.SIG_DFL,
            ) as signal_handler,
            patch.object(reference_acquisition.signal, "setitimer") as timer,
            patch.object(reference_acquisition._OPENER, "open", return_value=response),
            self.assertRaisesRegex(AcquisitionError, "network"),
        ):
            reference_acquisition._get(
                "https://example.invalid/reference", "*/*", 2
            )
        self.assertEqual(2, timer.call_count)
        self.assertEqual(2, signal_handler.call_count)

        with (
            patch.object(
                reference_acquisition.signal,
                "getitimer",
                side_effect=AttributeError("unavailable"),
            ),
            patch.object(reference_acquisition._OPENER, "open") as request,
            self.assertRaisesRegex(AcquisitionError, "capability"),
        ):
            reference_acquisition._get(
                "https://example.invalid/reference", "*/*", 2
            )
        request.assert_not_called()

    def test_selects_and_validates_pinned_image_config(self):
        digest = "sha256:" + "4" * 64
        manifest = json.dumps(
            {
                "config": {
                    "mediaType": "application/vnd.oci.image.config.v1+json",
                    "digest": digest,
                    "size": 4734,
                }
            }
        ).encode("utf-8")
        self.assertEqual((digest, 4734), select_image_config(manifest))
        config = json.dumps(
            {
                "architecture": "arm64",
                "os": "linux",
                "config": {
                    "Env": list(reference_acquisition.IMAGE_ENV),
                    "Entrypoint": None,
                    "Cmd": ["bash"],
                },
            }
        ).encode("utf-8")
        validate_image_config(config)
        drifted = json.loads(config)
        drifted["config"]["Env"].append("UNEXPECTED=1")
        with self.assertRaisesRegex(AcquisitionError, "rust config"):
            validate_image_config(json.dumps(drifted).encode("utf-8"))

    def test_write_exact_rejects_symlinked_parent_and_leaf(self):
        for symlink_parent in (False, True):
            with self.subTest(
                symlink_parent=symlink_parent
            ), TemporaryDirectory() as directory:
                root = Path(directory)
                actual = root / "actual"
                actual.mkdir()
                destination = root / "inputs/reference.bin"
                if symlink_parent:
                    (root / "inputs").symlink_to(actual, target_is_directory=True)
                else:
                    destination.parent.mkdir()
                    destination.symlink_to(actual / "outside.bin")
                with patch.object(
                    reference_acquisition, "ROOT", root
                ), self.assertRaises(AcquisitionError):
                    write_exact(destination, b"reference bytes\n")

    def test_write_exact_handles_short_writes_atomically(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "inputs/reference.bin"
            real_write = reference_acquisition.os.write

            def one_byte(descriptor, raw):
                return real_write(descriptor, raw[:1])

            with (
                patch.object(reference_acquisition, "ROOT", root),
                patch.object(reference_acquisition.os, "write", side_effect=one_byte),
            ):
                write_exact(destination, b"reference bytes\n")
            self.assertEqual(b"reference bytes\n", destination.read_bytes())

    def test_write_exact_rejects_noncanonical_materialization_paths(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in ("inputs\\reference.bin", "inputs/nul\0reference.bin"):
                with self.subTest(relative=relative), patch.object(
                    reference_acquisition, "ROOT", root
                ), self.assertRaises(AcquisitionError):
                    write_exact(root / relative, b"reference bytes\n")
            self.assertEqual([], list(root.iterdir()))

    def test_write_exact_never_clobbers_racing_destination(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "inputs/reference.bin"
            sentinel = b"racing sentinel\n"
            real_link = reference_acquisition.os.link

            def create_destination_then_link(*args, **kwargs):
                destination.write_bytes(sentinel)
                return real_link(*args, **kwargs)

            with (
                patch.object(reference_acquisition, "ROOT", root),
                patch.object(
                    reference_acquisition.os,
                    "link",
                    side_effect=create_destination_then_link,
                ),
                self.assertRaises(AcquisitionError),
            ):
                write_exact(destination, b"reference bytes\n")
            self.assertEqual(sentinel, destination.read_bytes())
            self.assertEqual([], list(destination.parent.glob(".*.tmp")))

    def test_write_exact_reads_existing_leaf_through_held_parent(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "inputs/reference.bin"
            destination.parent.mkdir()
            destination.write_bytes(b"mismatched held leaf\n")
            replacement = root / "replacement"
            replacement.mkdir()
            (replacement / "reference.bin").write_bytes(b"reference bytes\n")
            real_stat = reference_acquisition.os.stat
            exchanged = False

            def exchange_parent_after_stat(path, *args, **kwargs):
                nonlocal exchanged
                facts = real_stat(path, *args, **kwargs)
                if path == "reference.bin" and kwargs.get("dir_fd") is not None:
                    self.assertFalse(exchanged)
                    exchanged = True
                    (root / "inputs").rename(root / "held-inputs")
                    replacement.rename(root / "inputs")
                return facts

            with (
                patch.object(reference_acquisition, "ROOT", root),
                patch.object(
                    reference_acquisition.os,
                    "stat",
                    side_effect=exchange_parent_after_stat,
                ),
                self.assertRaises(AcquisitionError),
            ):
                write_exact(destination, b"reference bytes\n")
            self.assertTrue(exchanged)

    def test_write_exact_accepts_an_existing_exact_regular_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "inputs/reference.bin"
            destination.parent.mkdir()
            destination.write_bytes(b"reference bytes\n")
            with patch.object(reference_acquisition, "ROOT", root):
                write_exact(destination, b"reference bytes\n")
            self.assertEqual(b"reference bytes\n", destination.read_bytes())

    def test_write_exact_closes_each_descriptor_once_after_close_error(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "one/two/reference.bin"
            real_open = reference_acquisition.os.open
            real_close = reference_acquisition.os.close
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
                patch.object(reference_acquisition, "ROOT", root),
                patch.object(reference_acquisition.os, "open", side_effect=record_open),
                patch.object(
                    reference_acquisition.os, "close", side_effect=fail_first_close
                ),
                self.assertRaises(AcquisitionError),
            ):
                write_exact(destination, b"reference bytes\n")
            self.assertEqual(set(opened), set(closed))
            self.assertEqual(len(closed), len(set(closed)))

    def test_write_failure_preserves_existing_or_absent_destination(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "inputs/reference.bin"
            with (
                patch.object(reference_acquisition, "ROOT", root),
                patch.object(
                    reference_acquisition.os,
                    "write",
                    side_effect=OSError("injected write failure"),
                ),
                self.assertRaises(AcquisitionError),
            ):
                write_exact(destination, b"reference bytes\n")
            self.assertFalse(destination.exists())
            self.assertEqual([], list((root / "inputs").glob(".*.tmp")))

            destination.write_bytes(b"existing sentinel\n")
            with patch.object(reference_acquisition, "ROOT", root), self.assertRaises(
                AcquisitionError
            ):
                write_exact(destination, b"different bytes\n")
            self.assertEqual(b"existing sentinel\n", destination.read_bytes())


if __name__ == "__main__":
    unittest.main()
