from titanbox.auth import secure_equal


def test_secure_equal():
    assert secure_equal("abc", "abc") is True
    assert secure_equal("abc", "abd") is False
    assert secure_equal(None, "abc") is False
