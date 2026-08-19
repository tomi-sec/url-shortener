import shortcode


def test_encode_zero_is_the_alphabets_first_digit():
    assert shortcode.encode(0) == "0"


def test_encode_decode_roundtrips():
    for n in [0, 1, 61, 62, 1000, 123456789, 999999999999]:
        assert shortcode.decode(shortcode.encode(n)) == n


def test_encode_is_injective_over_a_large_range():
    """No two different ids should ever produce the same short code."""
    codes = {shortcode.encode(n) for n in range(100000)}
    assert len(codes) == 100000


def test_encode_uses_only_the_base62_alphabet():
    code = shortcode.encode(999999999)
    assert all(c in shortcode.ALPHABET for c in code)


def test_encode_is_deterministic():
    assert shortcode.encode(424242) == shortcode.encode(424242)
