"""Short code generation: a Postgres sequence + base62, no collisions possible.

A DB sequence guarantees every id is unique across however many app
instances are running, with zero collision handling needed - no retries,
no locks. The honest tradeoff (documented in the README) is enumeration
risk: codes are sequential under the base62 encoding, so anyone can walk
the URL space by incrementing a code. That's an acceptable tradeoff for
this project since the point is measuring the request path, not building
an anti-enumeration scheme, but it's a real production concern a
hash-based or random-with-retry scheme would avoid.
"""

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
BASE = len(ALPHABET)


def encode(number):
    """Encodes a non-negative integer as a base62 string.

    Args:
        number: A non-negative integer - a links_id_seq value in
            practice.

    Returns:
        The base62 encoding, using 0-9, then A-Z, then a-z as digits.
    """
    if number == 0:
        return ALPHABET[0]
    digits = []
    while number > 0:
        number, remainder = divmod(number, BASE)
        digits.append(ALPHABET[remainder])
    return "".join(reversed(digits))


def decode(code):
    """Decodes a base62 string back to its integer value.

    Not used on the app's actual request path (the redirect handler
    looks a short code up by string, it never needs the id back) - this
    exists so tests can prove encode() is a true bijection.

    Args:
        code: A base62 string, as produced by encode().

    Returns:
        The original integer.
    """
    number = 0
    for char in code:
        number = number * BASE + ALPHABET.index(char)
    return number
