from pathlib import Path
from codeograph.llm.provider import LlmProvider
from codeograph.llm.prompts.loader import PromptLoader
from codeograph.llm._prompts_generated import PromptId
from codeograph.passes.pass2.schemas import SynthesisResult

class CorpusSynthesizer:
    def __init__(self, provider: LlmProvider, prompt_loader: PromptLoader, output_dir: Path):
        self.provider = provider
        self.prompt_loader = prompt_loader
        self.output_dir = output_dir

    def synthesize(self, annotations: list[dict], graph: dict) -> None:
        prompt = self.prompt_loader.get(PromptId.SYNTHESIZE_CORPUS)
        
        # TODO(learner): Read Pass 1 annotations and graph.json
        # TODO(learner): Aggregate into compact_summary
        # TODO(learner): Single LLM call using complete_structured
        pass
