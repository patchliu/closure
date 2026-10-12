from closure.hashing import sha256, sha256_bytes, canonical_json


def test_canonical_stable_across_key_order():
    a = {"b": 1, "a": [2, 3]}
    b = {"a": [2, 3], "b": 1}
    assert canonical_json(a) == canonical_json(b)


def test_sha256_known_vector():
    assert sha256({"a": 1}) == sha256({"a": 1})
    assert sha256({"a": 1}) != sha256({"a": 2})
    assert len(sha256({"a": 1})) == 64


def test_sha256_bytes_vector():
    # sha256 of empty string
    assert (
        sha256_bytes(b"")
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )