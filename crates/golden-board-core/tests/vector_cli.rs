use std::io::Write;
use std::process::{Command, Output, Stdio};

const MAX_INPUT: usize = 1 << 24;

fn run(arguments: &[&str], input: &[u8]) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_gb-vector"));
    command
        .args(arguments)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = command.spawn().unwrap();
    child.stdin.take().unwrap().write_all(input).unwrap();
    child.wait_with_output().unwrap()
}

fn assert_success(operation: &str, input: &[u8], digest: &str) {
    let output = run(&[operation], input);
    assert!(output.status.success());
    assert_eq!(format!("ok\t{digest}\n").as_bytes(), output.stdout);
    assert!(output.stderr.is_empty());
}

#[test]
fn exact_operations_route_to_independent_core_functions() {
    assert_success(
        "identity-a-scalar",
        b"",
        "d884e5911a8a923feb85ae9c2b8066eb982234dfe6c6e7f34900988e6dc27a14",
    );
    assert_success(
        "identity-b-scalar",
        b"\0",
        "bd9a12341ac48f633c769140093675496d828dfa9ed21874b725acf3b8870c0e",
    );
    assert_success(
        "identity-a-list",
        b"\0\x02\0\0\0\x01\0\0\0\0\x02\x01\x02",
        "ba34053b678a144a645eb524bca6f464ee1923fe5d12f5d32dc29ab80d8a218f",
    );
    assert_success(
        "identity-a-list",
        b"\0\0",
        "ce8a5a8230d526db58192616683de0a728d0f6f9198b3ee5ebe55f2fa767a2da",
    );
    assert_success(
        "identity-a-list",
        b"\0\x01\0\0\0\0",
        "c475f1fbfda9eae9b0ad3e71603bdd6d45ebf545c866bb50f79170bc8895d72c",
    );
    assert_success(
        "manifest",
        b"{}\n",
        "836b1e2073681781d86862b6135f26e66db2c15cc73080d01815930aefbc4a4a",
    );
}

#[test]
fn manifest_rejection_is_a_stable_success_result() {
    let output = run(&["manifest"], b"null\n");
    assert!(output.status.success());
    assert_eq!(
        b"err\tmanifest.unsupported_type\n",
        output.stdout.as_slice()
    );
    assert!(output.stderr.is_empty());
}

#[test]
fn usage_and_malformed_list_framing_exit_two_without_stdout() {
    for (arguments, input) in [
        (vec![], &b""[..]),
        (vec!["unknown"], &b""[..]),
        (vec!["manifest", "extra"], &b"{}\n"[..]),
        (vec!["identity-a-scalar", "payload"], &b""[..]),
        (vec!["identity-a-list"], &b"\0"[..]),
        (vec!["identity-a-list"], &b"\0\x01\0\0\0"[..]),
        (vec!["identity-a-list"], &b"\0\x01\0\0\0\x02\x01"[..]),
        (vec!["identity-a-list"], &b"\0\0\x01"[..]),
    ] {
        let output = run(&arguments, input);
        assert_eq!(Some(2), output.status.code());
        assert!(output.stdout.is_empty());
        assert!(!output.stderr.is_empty());
        assert!(output.stderr.len() <= 1024);
        assert!(!String::from_utf8_lossy(&output.stderr).contains("panicked"));
    }
}

#[test]
fn adapter_boundary_reaches_core_and_sentinel_overflow_exits_two() {
    let at_core_limit = vec![b' '; MAX_INPUT + 1];
    let output = run(&["manifest"], &at_core_limit);
    assert!(output.status.success());
    assert_eq!(b"err\tmanifest.limit\n", output.stdout.as_slice());
    assert!(output.stderr.is_empty());

    let overflow = vec![b' '; MAX_INPUT + 2];
    let output = run(&["manifest"], &overflow);
    assert_eq!(Some(2), output.status.code());
    assert!(output.stdout.is_empty());
    assert!(!output.stderr.is_empty());
    assert!(output.stderr.len() <= 1024);
}

#[cfg(unix)]
#[test]
fn stdin_io_error_exits_two_without_stdout_or_panic_text() {
    let directory = std::fs::File::open(".").unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_gb-vector"))
        .arg("manifest")
        .stdin(Stdio::from(directory))
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .unwrap();
    assert_eq!(Some(2), output.status.code());
    assert!(output.stdout.is_empty());
    assert!(!output.stderr.is_empty());
    assert!(output.stderr.len() <= 1024);
    assert!(!String::from_utf8_lossy(&output.stderr).contains("panicked"));
}
