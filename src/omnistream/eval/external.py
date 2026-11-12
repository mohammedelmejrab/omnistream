"""Real LlamaIndex default baseline with the application's local embedding space."""

from llama_index.core import Document, VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.llms.openai_like import OpenAILike
from pydantic import PrivateAttr


class LocalEmbedding(BaseEmbedding):
    _service: object = PrivateAttr()

    def __init__(self, service):
        super().__init__(model_name=service.model_name)
        self._service = service

    def _get_query_embedding(self, query):
        return self._service.embed_query(query).tolist()

    async def _aget_query_embedding(self, query):
        return self._get_query_embedding(query)

    def _get_text_embedding(self, text):
        return self._service.embed_documents([text])[0].tolist()

    def _get_text_embeddings(self, texts):
        return self._service.embed_documents(texts).tolist()


class ExternalBaseline:
    def __init__(self, settings, items, service):
        llm = OpenAILike(
            model=settings.llm_model,
            api_base=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
            is_chat_model=True,
            is_function_calling_model=False,
            context_window=32768,
            max_tokens=1024,
            temperature=0,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
        documents = [
            Document(
                text=i["title"] + "\n\n" + i["text"],
                metadata={"item_id": i["runtime_id"]},
                excluded_llm_metadata_keys=["item_id"],
                excluded_embed_metadata_keys=["item_id"],
            )
            for i in items
        ]
        self.index = VectorStoreIndex.from_documents(
            documents, embed_model=LocalEmbedding(service)
        )
        self.engine = self.index.as_query_engine(llm=llm)

    def answer(self, question):
        result = self.engine.query(question)
        nodes = result.source_nodes
        return (
            str(result),
            [n.node.metadata["item_id"] for n in nodes],
            [(n.node.metadata["item_id"], n.node.get_content()) for n in nodes],
        )
