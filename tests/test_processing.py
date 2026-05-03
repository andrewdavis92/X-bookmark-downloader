"""Tests for processing module."""

from bookmark_downloader.processing.quote_resolver import extract_quoted_tweet_id


def test_returns_quoted_id_when_present():
    tweet = {"id": "111", "text": "hello", "author_id": "222", "quoted_tweet_id": "9876543210"}
    assert extract_quoted_tweet_id(tweet) == "9876543210"


def test_returns_none_when_quoted_tweet_id_absent():
    tweet = {"id": "111", "text": "hello", "author_id": "222"}
    assert extract_quoted_tweet_id(tweet) is None


def test_returns_none_for_empty_string():
    tweet = {"id": "111", "text": "hello", "author_id": "222", "quoted_tweet_id": ""}
    assert extract_quoted_tweet_id(tweet) is None


def test_ignores_raw_referenced_tweets():
    # quote_resolver reads quoted_tweet_id only (already mapped by client);
    # it does NOT re-parse referenced_tweets itself
    tweet = {
        "id": "111",
        "text": "hello",
        "author_id": "222",
        "referenced_tweets": [{"type": "replied_to", "id": "9876543210"}],
    }
    assert extract_quoted_tweet_id(tweet) is None
