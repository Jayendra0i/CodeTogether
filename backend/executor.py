
import os
import time
import tempfile
import subprocess
from pathlib import Path


LANGUAGE_CONFIG = {
    "python": {
        "image": "python:3.12-slim",
        "filename": "main.py",
        "command": "python -I /workspace/main.py",
    },
    "javascript": {
        "image": "node:22-slim",
        "filename": "main.js",
        "command": "node /workspace/main.js",
    },
    "java": {
        "image": "eclipse-temurin:21-jdk",
        "filename": "Main.java",
        "command": "javac -d /tmp /workspace/Main.java && java -cp /tmp Main",
    },
    "c": {
        "image": "gcc:14",
        "filename": "main.c",
        "command": "gcc -O0 /workspace/main.c -o /tmp/program && /tmp/program",
    },
    "cpp": {
        "image": "gcc:14",
        "filename": "main.cpp",
        "command": "g++ -O0 /workspace/main.cpp -o /tmp/program && /tmp/program",
    },
}


def execute_code(language: str, code: str, stdin: str = ""):
    language = language.lower().strip()

    if language not in LANGUAGE_CONFIG:
        raise ValueError("Unsupported programming language")

    if not isinstance(code, str) or not code.strip():
        raise ValueError("Code cannot be empty")

    if len(code) > 50000:
        raise ValueError("Code size cannot exceed 50 KB")

    if len(stdin) > 10000:
        raise ValueError("Input size cannot exceed 10 KB")

    config = LANGUAGE_CONFIG[language]
    start_time = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory(prefix="codetogether_") as temp_dir:
            source_path = Path(temp_dir) / config["filename"]
            source_path.write_text(code, encoding="utf-8")

            command = [
                "docker", "run", "--rm", "-i",
                "--network", "none",
                "--memory", "128m",
                "--memory-swap", "128m",
                "--cpus", "0.5",
                "--pids-limit", "64",
                "--read-only",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges",
                "--mount",
                f"type=bind,source={temp_dir},target=/workspace,readonly",
                "--workdir", "/workspace",
                "--entrypoint", "/bin/sh",
                config["image"],
                "-c", config["command"],
            ]

            try:
                result = subprocess.run(
                    command,
                    input=stdin,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                    check=False,
                )

                elapsed = round(time.perf_counter() - start_time, 3)

                output = result.stdout[-20000:]
                error = result.stderr[-20000:]

                return {
                    "success": result.returncode == 0,
                    "output": output,
                    "error": error,
                    "execution_time": elapsed,
                    "exit_code": result.returncode,
                }

            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "output": "",
                    "error": "Execution timed out (5 seconds limit).",
                    "execution_time": 5,
                    "exit_code": None,
                }

    except FileNotFoundError:
        raise RuntimeError("Docker CLI was not found. Check Docker Desktop.")

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "error": "Execution timed out.",
            "execution_time": 5,
            "exit_code": None,
        }

    except Exception as error:
        raise RuntimeError(f"Code execution failed: {str(error)}")
