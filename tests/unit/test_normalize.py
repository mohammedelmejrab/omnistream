from omnistream.ingest.normalize import (
    content_hash,
    normalize_relation,
    normalize_text,
    normalize_url,
)


def test_hash_ignores_whitespace_and_case():
    assert content_hash("https://a.com/x", "Hello World\n") == content_hash(
        "https://a.com/x", "hello world"
    )


def test_hash_ignores_tracking_params_and_fragment():
    t = "some text"
    assert content_hash("https://A.com/x/?utm_source=t#top", t) == content_hash(
        "https://a.com/x", t
    )


def test_hash_differs_for_different_text():
    assert content_hash("https://a.com/x", "hello world") != content_hash(
        "https://a.com/x", "hello there"
    )


def test_hash_is_sha256_hex():
    h = content_hash("https://a.com/x", "t")
    assert len(h) == 64
    int(h, 16)
    assert h == h.lower()


def test_nfkc_normalization():
    assert normalize_text("ﬁnance") == "finance"


def test_doc_scheme_keeps_fragment():
    assert normalize_url("doc://abc#chunk-2") == "doc://abc#chunk-2"


def test_url_params_ports_and_root():
    assert (
        normalize_url("HTTP://A.com:80/p/?b=2&a=1&gclid=x&fbclid=y&utm_medium=z")
        == "http://a.com/p?a=1&b=2"
    )
    assert normalize_url("https://a.com:443/") == "https://a.com/"
    assert normalize_url("https://a.com:8443/x") == "https://a.com:8443/x"


def test_normalize_relation():
    assert normalize_relation("works for") == "WORKS_FOR"
    assert normalize_relation("is CEO of") == "IS_CEO_OF"
    assert normalize_relation("acquired-by") == "ACQUIRED_BY"
