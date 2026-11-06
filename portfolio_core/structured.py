"""Bounded structured local-model calls shared by new portfolio applications."""
import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langsmith import tracing_context

from .ollama import ModelServiceError, OllamaClient


class StructuredLocalModel:
    def __init__(self, model: str, base_url: str | None = None):
        endpoint = base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11435")
        OllamaClient(endpoint)
        settings = dict(model=model, base_url=endpoint, temperature=0, num_ctx=4096,
                        num_gpu=int(os.getenv("LOCAL_AI_NUM_GPU", "0")), num_predict=512,
                        keep_alive="5m", client_kwargs={"timeout": 120, "trust_env": False})
        if model.startswith("qwen3"):
            settings["reasoning"] = False
        self.model = ChatOllama(**settings)

    def chain(self, system: str, human: str, schema):
        return (ChatPromptTemplate.from_messages([("system", system), ("human", human)])
                | self.model.with_structured_output(schema, method="json_schema", include_raw=True))

    async def invoke(self, chain, values):
        try:
            with tracing_context(enabled=False):
                output = await chain.ainvoke(values, config={"callbacks": []})
            if output.get("parsing_error") or output.get("parsed") is None:
                raise ModelServiceError("The local model did not return a valid structured response.")
            usage = getattr(output.get("raw"), "usage_metadata", None) or {}
            return output["parsed"], {"input_tokens": usage.get("input_tokens"),
                                      "output_tokens": usage.get("output_tokens")}
        except ModelServiceError:
            raise
        except Exception as exc:
            raise ModelServiceError("The local model is unavailable or returned invalid output. Check Ollama and try again.") from exc
