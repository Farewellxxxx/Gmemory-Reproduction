import gzip


def test_secret_scan_checks_compressed_artifacts_and_ignores_named_dummy():
    from repro.check_publish import contains_secret
    artificial=b'sk-'+b'A'*32
    assert contains_secret(artificial)
    assert contains_secret(gzip.compress(b'prefix '+artificial+b' suffix'))
    assert not contains_secret(b'sk-secret-that-must-never-be-published')
    assert not contains_secret(b'OPENAI_API_KEY=replace-locally')
