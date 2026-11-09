"""Ask a local code model for a source fragment and retain its token usage."""
import json
import re

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langsmith import tracing_context

from portfolio_core.ollama import ModelServiceError
from portfolio_core.structured import StructuredLocalModel

from .contracts import Source


class CodeRole:
    def __init__(self, model, instructions, token_limit, note):
        adapter = StructuredLocalModel(model)
        adapter.model.num_ctx = 4096
        adapter.model.num_predict = token_limit
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=instructions),
            ('human', 'Build context: {context}\nReturn the source code only.'),
        ])
        self.chain = prompt | adapter.model
        self.note = note

    async def generate(self, context):
        try:
            with tracing_context(enabled=False):
                reply = await self.chain.ainvoke({'context': json.dumps(context)}, config={'callbacks': []})
            if not isinstance(reply.content, str):
                raise ValueError('Expected source text from the local model.')
            code = reply.content.strip()
            blocks = re.findall(r'```(?:python|py|jsx|javascript|js)?[^\S\n]*\n(.*?)\n```', code, re.DOTALL | re.IGNORECASE)
            if len(blocks) == 1:
                code = blocks[0].strip()
            usage = reply.usage_metadata or {}
            return Source(code=code, note=self.note), {
                'input_tokens': usage.get('input_tokens'), 'output_tokens': usage.get('output_tokens'),
            }
        except (ValueError, TypeError) as error:
            raise ModelServiceError('The local model returned invalid source text.') from error
        except Exception as error:
            raise ModelServiceError('The local model could not generate source text.') from error
