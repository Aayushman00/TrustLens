"""Closed denylist for the pickle opcode scan (ADR 0014). Ported verbatim from docs/v2/spikes/s7_pickle_scan.py."""
DENYLIST_VERSION = "integrity/denylist-v1"

ALLOW = {
    ("collections", "OrderedDict"), ("torch._utils", "_rebuild_tensor_v2"), ("torch._utils", "_rebuild_tensor"),
    ("torch._utils", "_rebuild_parameter"), ("torch._utils", "_rebuild_parameter_with_state"),
    ("torch._tensor", "_rebuild_from_type_v2"), ("torch", "Size"), ("torch", "device"), ("torch", "dtype"),
    ("torch.serialization", "_get_layout"), ("builtins", "set"), ("builtins", "dict"), ("builtins", "list"),
    ("builtins", "tuple"), ("builtins", "slice"), ("_codecs", "encode"), ("numpy.core.multiarray", "_reconstruct"),
    ("numpy", "ndarray"), ("numpy", "dtype"), ("torch._utils", "_rebuild_qtensor"),
} | {("torch", f"{t}Storage") for t in ("Float", "Half", "BFloat16", "Double", "Long", "Int", "Short", "Char",
                                          "Byte", "Bool", "ComplexFloat", "ComplexDouble", "Untyped")} | \
    {("torch", d) for d in ("float32", "float16", "bfloat16", "int64", "int32", "uint8", "bool")}
DENY_MODULES = {"os", "posix", "nt", "subprocess", "sys", "socket", "shutil", "runpy", "webbrowser", "pty",
                "importlib", "ctypes", "multiprocessing", "asyncio", "pickle", "marshal", "code", "httplib",
                "requests", "urllib", "http", "ftplib", "telnetlib", "platform", "commands", "pip", "torch.hub"}
DENY_NAMES = {("builtins", n) for n in ("eval", "exec", "compile", "open", "getattr", "setattr", "__import__",
                                        "globals", "locals", "breakpoint", "input")} | \
             {("__builtin__", n) for n in ("eval", "exec", "getattr", "__import__", "open")}
