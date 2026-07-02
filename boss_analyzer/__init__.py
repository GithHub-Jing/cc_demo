__version__ = "1.0.0"
__all__ = ["analyze"]


def __getattr__(name):
    if name == "analyze":
        from boss_analyzer.main import analyze
        return analyze
    raise AttributeError(f"module 'boss_analyzer' has no attribute {name!r}")
