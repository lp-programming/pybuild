targets = {
    "all": {
        "doc": "hello world",
        "deps": ["hello", "world"],
        "targets": ["hola"],
        "virtual": True
    },
    "hello": {
        "virtual": True,
        "doc": "I say hello",
        "cmd": ["echo", "hello"]
    },
    "world": {
        "virtual": True,
        "doc": "I say world",
        "deps": ["hello"],
        "cmd": ["echo", "world"],
    },
    "hola": {
        "virtual": True,
        "doc": "I say hello differently",
        "function": (lambda _: print("hola") or True)
    }
}
