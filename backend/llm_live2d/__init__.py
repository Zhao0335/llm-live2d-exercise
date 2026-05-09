"""llm_live2d: 大模型驱动 Live2D 的可复用框架。"""
from .core import (
    Pipeline,
    PipelineConfig,
)
from .core import providers as _providers_abc

__version__ = "0.1.0"

__all__ = ["Pipeline", "PipelineConfig", "__version__"]
