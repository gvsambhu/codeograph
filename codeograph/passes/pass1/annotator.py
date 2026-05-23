import json
from pathlib import Path
from codeograph.llm.provider import LlmProvider
from codeograph.llm.prompts.loader import PromptLoader
from codeograph.llm._prompts_generated import PromptId
from codeograph.passes.pass1.schemas import NodeAnnotation

class NodeAnnotator:
    def __init__(self, provider: LlmProvider, prompt_loader: PromptLoader, output_dir: Path):
        self.provider = provider
        self.prompt_loader = prompt_loader
        self.output_dir = output_dir

    def annotate(self, nodes: list[dict]) -> None:
        prompt = self.prompt_loader.get(PromptId.ANNOTATE_NODE)
        
        # TODO(learner): Setup per-node call concurrency via complete_structured_many
        # TODO(learner): Aggregate results into out/llm-annotations.json
        pass
