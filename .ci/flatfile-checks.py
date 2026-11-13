"""Validate the isolated flatfile patch and a deliberate narrowing control."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["linux64", "linux32", "windows64", "macos64"], required=True)
    parser.add_argument("--source", default="source")
    parser.add_argument("--build", default="build")
    parser.add_argument("--config", default="Debug")
    parser.add_argument("--output", default="results")
    args = parser.parse_args()
    source = Path(args.source).resolve()
    build = Path(args.build).resolve()
    output = Path(args.output) / args.profile
    output.mkdir(parents=True, exist_ok=True)
    binary = build / "bin" / "test_bitcoin"
    if args.profile == "windows64":
        binary = build / "bin" / args.config / "test_bitcoin.exe"
    report = {
        "profile": args.profile,
        "platform": platform.platform(),
        "source_commit": subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip(),
        "checks": [],
    }

    def run(label, command, expect_failure=False):
        print(label, command, flush=True)
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        (output / f"{label}.log").write_text(result.stdout, encoding="utf-8")
        report["checks"].append({"name": label, "command": command, "exit_code": result.returncode})
        print(result.stdout[-5000:], flush=True)
        if (result.returncode != 0) != expect_failure:
            raise RuntimeError(f"Unexpected exit code for {label}: {result.returncode}")
        return result.stdout

    build_command = ["cmake", "--build", str(build), "--config", args.config, "--target", "test_bitcoin", "--parallel", "2"]
    suite_command = ["ctest", "--test-dir", str(build), "-C", args.config, "--output-on-failure", "--no-tests=error", "-R", "^(flatfile_tests|serialize_tests|streams_tests|blockmanager_tests)$"]
    original = None
    production = source / "src" / "flatfile.cpp"
    try:
        binary_data = binary.read_bytes()
        if args.profile.startswith("linux"):
            expected_class = 1 if args.profile == "linux32" else 2
            assert binary_data[:4] == b"\x7fELF" and binary_data[4] == expected_class
            report["elf_class"] = expected_class
        elif args.profile == "windows64":
            pe_offset = int.from_bytes(binary_data[60:64], "little")
            assert binary_data[pe_offset:pe_offset + 4] == b"PE\x00\x00"
            assert int.from_bytes(binary_data[pe_offset + 4:pe_offset + 6], "little") == 0x8664
            report["pe_machine"] = "AMD64"
        run("current-suites", suite_command)
        detail = run("boundary-details", [str(binary), "--run_test=flatfile_tests/flatfile_pos_serialization,flatfile_large_position", "--log_level=all", "--color_output=no"])
        assert 'Entering test case "flatfile_pos_serialization"' in detail
        assert 'Entering test case "flatfile_large_position"' in detail
        skipped = "Skipping large file seeks" in detail
        assert skipped == (args.profile == "linux32"), "Unexpected large-seek skip state"
        report["large_seek_skipped"] = skipped
        if not skipped:
            original = production.read_bytes()
            needle = b"FileSeek64(file, pos.nPos, SEEK_SET)"
            assert original.count(needle) == 1
            production.write_bytes(original.replace(needle, b"FileSeek64(file, static_cast<uint32_t>(pos.nPos), SEEK_SET)"))
            run("control-build", build_command)
            run("control-existing", [str(binary), "--run_test=flatfile_tests/flatfile_filename,flatfile_open,flatfile_allocate,flatfile_flush", "--log_level=test_suite", "--color_output=no"])
            detail = run("control-new", [str(binary), "--run_test=flatfile_tests/flatfile_large_position", "--log_level=test_suite", "--color_output=no"], expect_failure=True)
            assert "4294967296" in detail and "file.tell() == offset" in detail
            production.write_bytes(original)
            original = None
            run("restored-build", build_command)
            run("restored-suites", suite_command)
        run("clean-source", ["git", "-C", str(source), "diff", "--exit-code"])
        report["binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
        report["cache_sha256"] = hashlib.sha256((build / "CMakeCache.txt").read_bytes()).hexdigest()
        report["success"] = True
    finally:
        if original is not None:
            production.write_bytes(original)
        (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
