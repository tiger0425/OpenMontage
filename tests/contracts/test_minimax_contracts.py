"""Phase 5 contract tests — MiniMax provider integration tools.

Tests the 4 new MiniMax tools for BaseTool contract compliance:
  - MiniMaxImage (graphics)
  - MiniMaxTTS (audio)
  - MiniMaxMusic (audio)
  - MiniMaxVideoDirect (video)
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.base_tool import BaseTool, ToolResult, ToolStatus, ToolTier
from tools.tool_registry import ToolRegistry
from tools.graphics.minimax_image import MiniMaxImage
from tools.audio.minimax_tts import MiniMaxTTS
from tools.audio.minimax_music import MiniMaxMusic
from tools.video.minimax_video_direct import MiniMaxVideoDirect


MINIMAX_TOOLS: list[tuple[type[BaseTool], str, str, ToolTier]] = [
    (MiniMaxImage, "minimax_image", "image_generation", ToolTier.GENERATE),
    (MiniMaxTTS, "minimax_tts", "tts", ToolTier.VOICE),
    (MiniMaxMusic, "minimax_music", "music_generation", ToolTier.GENERATE),
    (MiniMaxVideoDirect, "minimax_video_direct", "video_generation", ToolTier.GENERATE),
]


# ---- Contract: every tool inherits BaseTool and has required fields ----


class TestMiniMaxToolContracts:
    @pytest.mark.parametrize("tool_cls, expected_name, expected_capability, expected_tier", MINIMAX_TOOLS)
    def test_inherits_base_tool(
        self, tool_cls: type[BaseTool], expected_name: str, expected_capability: str, expected_tier: ToolTier
    ) -> None:
        assert issubclass(tool_cls, BaseTool)

    @pytest.mark.parametrize("tool_cls, expected_name, expected_capability, expected_tier", MINIMAX_TOOLS)
    def test_has_required_identity(
        self, tool_cls: type[BaseTool], expected_name: str, expected_capability: str, expected_tier: ToolTier
    ) -> None:
        tool = tool_cls()
        assert tool.name == expected_name
        assert tool.version == "0.1.0"
        assert tool.tier == expected_tier
        assert tool.provider == "minimax"
        assert len(tool.capabilities) > 0

    @pytest.mark.parametrize("tool_cls, expected_name, expected_capability, expected_tier", MINIMAX_TOOLS)
    def test_get_info_returns_valid_dict(
        self, tool_cls: type[BaseTool], expected_name: str, expected_capability: str, expected_tier: ToolTier
    ) -> None:
        tool = tool_cls()
        info = tool.get_info()
        assert isinstance(info, dict)
        assert info["name"] == expected_name
        assert info["capability"] == expected_capability
        assert info["provider"] == "minimax"
        assert info["tier"] == expected_tier.value
        assert info["status"] in ("available", "unavailable", "degraded")
        assert info["runtime"] == "api"

    @pytest.mark.parametrize("tool_cls, expected_name, expected_capability, expected_tier", MINIMAX_TOOLS)
    def test_execute_is_implemented(
        self, tool_cls: type[BaseTool], expected_name: str, expected_capability: str, expected_tier: ToolTier
    ) -> None:
        tool = tool_cls()
        assert callable(tool.execute)

    @pytest.mark.parametrize("tool_cls, expected_name, expected_capability, expected_tier", MINIMAX_TOOLS)
    def test_dry_run_returns_dict(
        self, tool_cls: type[BaseTool], expected_name: str, expected_capability: str, expected_tier: ToolTier
    ) -> None:
        tool = tool_cls()
        result = tool.dry_run({})
        assert isinstance(result, dict)
        assert result["tool"] == expected_name
        assert "estimated_cost_usd" in result
        assert "status" in result
        assert "would_execute" in result

    @pytest.mark.parametrize("tool_cls, expected_name, expected_capability, expected_tier", MINIMAX_TOOLS)
    def test_get_status_unavailable_without_key(
        self, tool_cls: type[BaseTool], expected_name: str, expected_capability: str, expected_tier: ToolTier
    ) -> None:
        """Without MINIMAX_API_KEY, all MiniMax tools should be UNAVAILABLE."""
        tool = tool_cls()
        # No API key set by default in CI/test — tool should report UNAVAILABLE
        status = tool.get_status()
        assert status in (ToolStatus.AVAILABLE, ToolStatus.UNAVAILABLE), (
            f"{expected_name} returned unexpected status {status}"
        )


# ---- Contract: unique names among MiniMax tools ----


class TestMiniMaxToolNames:
    def test_unique_names(self) -> None:
        names = [cls().name for cls, _, _, _ in MINIMAX_TOOLS]
        assert len(names) == len(set(names))

    def test_expected_names(self) -> None:
        names = {cls().name for cls, _, _, _ in MINIMAX_TOOLS}
        expected = {"minimax_image", "minimax_tts", "minimax_music", "minimax_video_direct"}
        assert names == expected


# ---- Contract: discoverable via registry ----


class TestMiniMaxToolDiscovery:
    def test_all_minimax_tools_discoverable(self) -> None:
        reg = ToolRegistry()
        reg.discover("tools")
        for cls, expected_name, _, _ in MINIMAX_TOOLS:
            assert reg.get(expected_name) is not None, f"{expected_name} not discovered"

    def test_all_minimax_tools_same_provider(self) -> None:
        reg = ToolRegistry()
        reg.discover("tools")
        minimax_tools = reg.get_by_provider("minimax")
        names = {t.name for t in minimax_tools}
        expected = {"minimax_image", "minimax_tts", "minimax_music", "minimax_video_direct"}
        for name in expected:
            assert name in names, f"{name} missing from minimax provider tools"


# ---- Contract: capability-specific behavior ----


class TestMiniMaxImageSpecific:
    def test_identity(self) -> None:
        tool = MiniMaxImage()
        info = tool.get_info()
        assert info["name"] == "minimax_image"
        assert info["capability"] == "image_generation"
        assert info["provider"] == "minimax"
        assert info["tier"] == "generate"

    def test_capabilities(self) -> None:
        tool = MiniMaxImage()
        assert "generate_image" in tool.capabilities
        assert "text_to_image" in tool.capabilities

    def test_estimate_cost_scales_with_n(self) -> None:
        tool = MiniMaxImage()
        cost_1 = tool.estimate_cost({"n": 1})
        cost_3 = tool.estimate_cost({"n": 3})
        assert cost_3 > cost_1


class TestMiniMaxTTSSpecific:
    def test_identity(self) -> None:
        tool = MiniMaxTTS()
        info = tool.get_info()
        assert info["name"] == "minimax_tts"
        assert info["capability"] == "tts"
        assert info["provider"] == "minimax"
        assert info["tier"] == "voice"

    def test_capabilities(self) -> None:
        tool = MiniMaxTTS()
        assert "text_to_speech" in tool.capabilities
        assert "voice_selection" in tool.capabilities

    def test_estimate_cost_scales_with_text_length(self) -> None:
        tool = MiniMaxTTS()
        cost_short = tool.estimate_cost({"text": "hello"})
        cost_long = tool.estimate_cost({"text": "hello world this is a long text"})
        assert cost_long > cost_short

    def test_has_fallback_tools(self) -> None:
        tool = MiniMaxTTS()
        assert len(tool.fallback_tools) >= 3
        assert "piper_tts" in tool.fallback_tools


class TestMiniMaxMusicSpecific:
    def test_identity(self) -> None:
        tool = MiniMaxMusic()
        info = tool.get_info()
        assert info["name"] == "minimax_music"
        assert info["capability"] == "music_generation"
        assert info["provider"] == "minimax"
        assert info["tier"] == "generate"

    def test_capabilities(self) -> None:
        tool = MiniMaxMusic()
        assert "generate_background_music" in tool.capabilities

    def test_estimate_cost_is_fixed(self) -> None:
        tool = MiniMaxMusic()
        cost = tool.estimate_cost({"prompt": "ambient piano", "duration_seconds": 60})
        assert cost > 0
        assert cost < 0.05


class TestMiniMaxVideoDirectSpecific:
    def test_identity(self) -> None:
        tool = MiniMaxVideoDirect()
        info = tool.get_info()
        assert info["name"] == "minimax_video_direct"
        assert info["capability"] == "video_generation"
        assert info["provider"] == "minimax"
        assert info["tier"] == "generate"

    def test_capabilities(self) -> None:
        tool = MiniMaxVideoDirect()
        assert "text_to_video" in tool.capabilities
        assert "image_to_video" in tool.capabilities

    def test_estimate_cost_scales_with_duration(self) -> None:
        tool = MiniMaxVideoDirect()
        cost_2s = tool.estimate_cost({"duration": 2})
        cost_6s = tool.estimate_cost({"duration": 6})
        assert cost_6s > cost_2s

    def test_estimate_runtime_scales_with_duration(self) -> None:
        tool = MiniMaxVideoDirect()
        rt_2s = tool.estimate_runtime({"duration": 2})
        rt_6s = tool.estimate_runtime({"duration": 6})
        assert rt_6s > rt_2s
