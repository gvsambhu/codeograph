import asyncio
import tempfile
from pathlib import Path, PurePosixPath
from typing import cast

from codeograph.graph.models.graph_schema import ClassNode
from codeograph.llm.prompts.loader import PromptLoader
from codeograph.llm.provider import LlmProvider
from codeograph.renderers.typescript_nestjs.config import TypeScriptConfig
from codeograph.renderers.typescript_nestjs.renderer import TypeScriptRenderer
from codeograph.rendering.class_selector import SelectionResult


def test_render_group_basic(mocker):
    # 1. Build a minimal ClassNode + graph
    class_node = ClassNode(
        id="com.example.orders.OrderService",
        name="OrderService",
        kind="class",
        modifiers=["public"],
        source_file="src/main/java/com/example/orders/OrderService.java",
        line_range=[1, 40],
        extraction_mode="ast",
        annotations=[],
    )

    # 2. Build a minimal SelectionResult
    result = SelectionResult(
        selected=("com.example.orders.OrderService",),
        excluded=(),
        strategy="take_all",
        group_name="orders",
        cap=50,
        total_in_group=1,
        metrics_missing_count=0,
        high_count=0,
    )

    # 3. Build a mock node_map
    node_map = {"com.example.orders.OrderService": class_node}

    # 4. Build TypeScriptRenderer with a mock/null provider
    config = TypeScriptConfig()
    provider = cast(LlmProvider, None)
    prompt_loader = PromptLoader(Path(tempfile.mkdtemp()))

    renderer = TypeScriptRenderer(
        config=config,
        provider=provider,
        prompt_loader=prompt_loader,
    )

    # 5. Patch renderer._call_llm
    canned_ts = "// canned\nexport class OrderService {}\n"
    mocker.patch.object(renderer, "_call_llm", return_value=canned_ts)

    # 6. Call _render_group
    semaphore = asyncio.Semaphore(5)
    file_map = asyncio.run(renderer._render_group(result, {}, node_map, semaphore))

    # 7. Assert
    has_ts = any(path.name.endswith(".ts") and not path.name.endswith(".module.ts") for path in file_map.keys())
    assert has_ts

    module_path = PurePosixPath("src/orders/orders.module.ts")
    assert module_path in file_map

    module_content = file_map[module_path].decode("utf-8")
    assert module_content.startswith("/**")
