"""三态情感语义测试：resolve_emotion_mode 判定规则。

规则必须与 D:/index-tts/indextts_server.py 的实现保持一致（两处同步修改）。
"""

import pytest

from tools.audio.indextts_tts import CALM_EMO_VECTOR, resolve_emotion_mode

CALM = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
ANGRY = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_omitted_emo_vector_defaults_to_auto_detect():
    mode = resolve_emotion_mode(None, None, 0.6)
    assert mode == {"mode": "auto", "emo_vector": None, "emo_alpha": 0.6}


def test_explicit_emo_vector_disables_auto_detect():
    mode = resolve_emotion_mode(CALM, None, 0.6)
    assert mode == {"mode": "fixed", "emo_vector": CALM, "emo_alpha": 1.0}


def test_explicit_use_emo_text_true_overrides_vector():
    mode = resolve_emotion_mode(CALM, True, 0.6)
    assert mode == {"mode": "auto", "emo_vector": None, "emo_alpha": 0.6}


def test_explicit_use_emo_text_false_without_vector_falls_back_to_calm():
    mode = resolve_emotion_mode(None, False, 0.6)
    assert mode == {"mode": "fixed", "emo_vector": CALM, "emo_alpha": 1.0}


def test_explicit_use_emo_text_false_keeps_vector():
    mode = resolve_emotion_mode(ANGRY, False, 0.6)
    assert mode == {"mode": "fixed", "emo_vector": ANGRY, "emo_alpha": 1.0}


def test_alpha_is_passthrough_only_in_auto_mode():
    for alpha in (0.0, 0.3, 1.0):
        mode = resolve_emotion_mode(None, True, alpha)
        assert mode["emo_alpha"] == alpha


def test_calm_constant_shape():
    assert len(CALM_EMO_VECTOR) == 8
    assert CALM_EMO_VECTOR[-1] == 1.0
