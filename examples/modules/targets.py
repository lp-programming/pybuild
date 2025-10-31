from pybuild import target, cpp, cppm, find_cppms, system_headers, write_module_map

target.module_maps[0] = target.build / "modules.map"

target.common_args = [
    "clang++",
    "-D_LIBCPP_DISABLE_DEPRECATION_WARNINGS=true",
    "-march=native",
    "-std=c++26",
    "-stdlib=libc++",
    "-fPIC",
    "-fimplicit-modules",
    "-fbuiltin-module-map",
    "-fimplicit-module-maps",
    "-fmodule-map-file=/usr/include/c++/v1/module.modulemap",
    *[f"-fmodule-map-file={i}" for i in target.module_maps],
    f"-fmodules-cache-path={target.build}/modules",
    "-flto",
    "-Wold-style-cast",
    "-Wall",
    "-Wextra",
    "-Wfloat-conversion",
    "-Wsign-conversion",
    "-Wsign-compare",
    "-Wpedantic",
]



targets = find_cppms(__file__) | {
    "all": target({
        "doc": "hello modules",
        "deps": ["modulemap", "bin/hello"],
        "virtual": True
    }),
    "bin/hello": cpp(
        doc="Hello from clang++",
        path="hello.cpp",
        out="bin/hello",
        deps=["modulemap"]
    ),
    "setup": target({
        "doc": "A virtual target that runs every time before any other targets",
        "deps": ["modulemap"],
        "virtual": True
    }),
    "modulemap": target({
        "doc": "Rebuild the module map for the local system",
        "hash": str.join(" ", sorted(system_headers)),
        "function": write_module_map        
    }),
}
