# Flatfile boundary validation

This branch runs focused checks for commit
`1d11bd83d892d5bdac759e98321899d60f7c84e8` in a separate source checkout.
The contribution branch is `pr/flatfile-boundaries`; it contains only the test
change. This CI branch is not intended for an upstream pull request.

The jobs build and run flatfile, serialization, streams and blockmanager tests
on Linux x86_64, Linux i386 and native Windows x86_64. Linux i386 verifies that
the serialization test runs and the large-seek test warns and returns. The
64-bit jobs also verify that narrowing the seek offset to uint32_t leaves
the existing flatfile tests passing but makes the new positioning test fail.
They restore source, rebuild, and repeat the relevant suites afterward.

Artifacts contain commands, exit codes, detailed boundary logs, CMake settings,
the source commit and binary hash. This is focused validation, not a run of
Bitcoin Core's complete CI matrix.
