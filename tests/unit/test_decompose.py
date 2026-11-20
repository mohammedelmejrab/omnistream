from omnistream.retrieval.own_algorithm.decompose import parse_subquestions


def test_parse_subquestions_rejects_non_list_fields():
    for bad in ('{"subquestions": null}', '{"subquestions": 3}',
                '{"subquestions": "abc"}', '{"subquestions": {"a": 1}}', "no json"):
        assert parse_subquestions(bad, "q") == []


def test_parse_subquestions_keeps_distinct_strings():
    text = '{"subquestions": ["Who directed F?", "Who directed F?", "q", "Where was D born?"]}'
    assert parse_subquestions(text, "q") == ["Who directed F?", "Where was D born?"]
