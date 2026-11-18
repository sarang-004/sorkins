from collections.abc import AsyncIterator, Callable
from typing import Protocol


JSONSchema = dict[str, object]
Message = dict[str, str]
StreamEvent = dict[str, str]
GenerateJSON = Callable[[list[Message], JSONSchema, int | None], dict[str, object]]
StreamText = Callable[[list[Message], str, int], AsyncIterator[StreamEvent]]


class AIProvider(Protocol):
    def generate_json(
        self,
        messages: list[Message],
        schema: JSONSchema,
        num_predict: int | None = None,
    ) -> dict[str, object]: ...

    def stream_text(
        self,
        messages: list[Message],
        model: str,
        num_gpu: int,
    ) -> AsyncIterator[StreamEvent]: ...


class OllamaProvider:
    """Provider adapter; service logic depends on this contract, not Ollama HTTP details."""

    def __init__(self, generate_json: GenerateJSON, stream_text: StreamText) -> None:
        self._generate_json = generate_json
        self._stream_text = stream_text

    def generate_json(
        self,
        messages: list[Message],
        schema: JSONSchema,
        num_predict: int | None = None,
    ) -> dict[str, object]:
        return self._generate_json(messages, schema, num_predict)

    def stream_text(
        self,
        messages: list[Message],
        model: str,
        num_gpu: int,
    ) -> AsyncIterator[StreamEvent]:
        return self._stream_text(messages, model, num_gpu)
