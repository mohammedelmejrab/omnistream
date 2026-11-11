class SourceFetchError(Exception):
    """A source could not be fetched or parsed."""


class UnsupportedDocumentError(Exception):
    """The uploaded document type is not supported."""
