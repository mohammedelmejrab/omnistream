"""Deterministic file-store tests for spec C5 original-text access."""

from __future__ import annotations

from pathlib import Path

import pytest

from omnistream.items import FileItemStore, ItemUnavailableError
from omnistream.retrieval import ItemPart, ItemStore


@pytest.fixture
def store(tmp_path: Path) -> FileItemStore:
    (tmp_path / "news-1.v2.txt").write_text(
        "one  two\nthree\tfour five six seven", encoding="utf-8"
    )
    return FileItemStore(tmp_path, tokens_per_part=3)


def test_file_store_parts_and_protocol(store):
    assert isinstance(store, ItemStore)
    assert store.read_item("news-1.v2") == ItemPart("news-1.v2", 1, 3, "one two three")
    assert store.read_item("news-1.v2", 2) == ItemPart(
        "news-1.v2", 2, 3, "four five six"
    )
    assert store.read_item("news-1.v2", 3) == ItemPart("news-1.v2", 3, 3, "seven")


def test_default_limits(tmp_path):
    words = [str(i) for i in range(4001)]
    (tmp_path / "item.txt").write_text(" ".join(words), encoding="utf-8")
    store = FileItemStore(tmp_path)
    assert store.read_item("item").text.split() == words[:2000]
    assert store.read_item("item", 3).text == "4000"
    assert store.item_text("item").split() == words[:4000]


def test_item_text_truncates(store):
    assert store.item_text("news-1.v2", 4) == "one two three four"
    assert store.item_text("news-1.v2", 0) == ""
    assert store.item_text("news-1.v2", 20) == "one two three four five six seven"


def test_read_parts_preserves_order_and_caps_requests(store):
    assert [p.part for p in store.read_parts("news-1.v2", [3, 1, 2])] == [3, 1, 2]
    assert [p.part for p in store.read_parts("news-1.v2", [1, 1, 1])] == [1, 1, 1]
    assert store.read_parts("news-1.v2", []) == []
    with pytest.raises(ValueError, match="at most 3"):
        store.read_parts("news-1.v2", [1, 1, 1, 1])
    with pytest.raises(ValueError, match="part"):
        store.read_parts("news-1.v2", [1, 4])


@pytest.mark.parametrize("part", [0, -1, 4, 1.5, True])
def test_invalid_part(store, part):
    with pytest.raises(ValueError, match="part"):
        store.read_item("news-1.v2", part)


@pytest.mark.parametrize(
    "method,args", [("read_item", ()), ("item_text", ()), ("read_parts", ([1],))]
)
def test_unknown_items(store, method, args):
    with pytest.raises(KeyError) as error:
        getattr(store, method)("unknown", *args)
    assert error.value.args == ("unknown",)
    assert isinstance(error.value, ItemUnavailableError)


@pytest.mark.parametrize(
    "item_id",
    [
        "",
        ".",
        "..",
        "../outside",
        "..\\outside",
        "a/b",
        "a\\b",
        "/absolute",
        "C:\\absolute",
        "a:b",
        "bad id",
        "item\n",
        "x\x00y",
        "é",
    ],
)
@pytest.mark.parametrize(
    "method,args", [("read_item", ()), ("item_text", ()), ("read_parts", ([1],))]
)
def test_rejects_unsafe_ids(store, item_id, method, args):
    with pytest.raises(ValueError):
        getattr(store, method)(item_id, *args)


def test_rejects_symlink_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    try:
        (root / "link.txt").symlink_to(outside)
    except OSError:
        pytest.skip("OS does not permit creating symlinks")
    store = FileItemStore(root)
    for method, args in [
        (store.read_item, ()),
        (store.item_text, ()),
        (store.read_parts, ([1],)),
    ]:
        with pytest.raises(ValueError, match="escapes root"):
            method("link", *args)


def test_empty_and_exact_multiple_items(tmp_path):
    (tmp_path / "empty.txt").write_text(" \n\t", encoding="utf-8")
    (tmp_path / "exact.txt").write_text("a b c d", encoding="utf-8")
    store = FileItemStore(tmp_path, tokens_per_part=2)
    assert store.read_item("empty") == ItemPart("empty", 1, 1, "")
    assert store.item_text("empty") == ""
    assert store.read_item("exact", 2).total_parts == 2
    with pytest.raises(ValueError):
        store.read_item("empty", 2)
    with pytest.raises(ValueError):
        store.read_item("exact", 3)


@pytest.mark.parametrize("limit", [0, -1, 1.5, True])
def test_invalid_part_size(tmp_path, limit):
    with pytest.raises(ValueError, match="tokens_per_part"):
        FileItemStore(tmp_path, tokens_per_part=limit)


@pytest.mark.parametrize("limit", [-1, 1.5, True])
def test_invalid_text_limit(store, limit):
    with pytest.raises(ValueError, match="max_tokens"):
        store.item_text("news-1.v2", limit)
