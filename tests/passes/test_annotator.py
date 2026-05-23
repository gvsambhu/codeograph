import pytest
from codeograph.passes.pass1.annotator import NodeAnnotator

def test_annotator_normal_nodes(mock_llm_provider, mock_prompt_loader, tmp_path):
    # TODO(learner): Provide a mock graph.json node, run annotator, assert output
    pass

def test_annotator_degraded_nodes(mock_llm_provider, mock_prompt_loader, tmp_path):
    # TODO(learner): Provide a node > max size, assert it's marked degraded and skipped
    pass