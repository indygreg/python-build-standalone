import codecs
import importlib.machinery
import importlib.util
import json
import os
import sys
import sysconfig

metadata = {
    # sys.abiflags not available on Windows.
    "python_abi_tag": None,
    "python_implementation_cache_tag": sys.implementation.cache_tag,
    "python_implementation_hex_version": sys.implementation.hexversion,
    "python_implementation_name": sys.implementation.name,
    "python_implementation_version": [str(x) for x in sys.implementation.version],
    "python_platform_tag": sysconfig.get_platform(),
    "python_suffixes": {
        "bytecode": importlib.machinery.BYTECODE_SUFFIXES,
        "debug_bytecode": importlib.machinery.DEBUG_BYTECODE_SUFFIXES,
        "extension": importlib.machinery.EXTENSION_SUFFIXES,
        "optimized_bytecode": importlib.machinery.OPTIMIZED_BYTECODE_SUFFIXES,
        "source": importlib.machinery.SOURCE_SUFFIXES,
    },
    "python_bytecode_magic_number": codecs.encode(
        importlib.util.MAGIC_NUMBER, "hex"
    ).decode("ascii"),
    "python_paths": {},
    "python_paths_abstract": sysconfig.get_paths(expand=False),
    "python_exe": f"install/{os.path.basename(sys.executable)}",
    "python_major_minor_version": sysconfig.get_python_version(),
    "python_config_vars": {k: str(v) for k, v in sysconfig.get_config_vars().items()},
}

root = os.environ["ROOT"]
for name, path in sysconfig.get_paths().items():
    rel = os.path.relpath(path, root).replace("\\", "/")

    # sysconfig on Windows reports the include path as "Include" but
    # in reality it is "include." See https://bugs.python.org/issue41669.
    # So we normalize accordingly.
    rel = rel.replace("install/Include", "install/include")

    metadata["python_paths"][name] = rel

with open(sys.argv[1], "w") as fh:
    json.dump(metadata, fh, sort_keys=True, indent=4)
