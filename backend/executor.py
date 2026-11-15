
import os
import time
import requests


LANGUAGE_CONFIG = {
    "python": {
        "language": "python",
        "filename": "main.py",
    },
    "javascript": {
        "language": "javascript",
        "filename": "main.js",
    },
    "java": {
        "language": "java",
        "filename": "Main.java",
    },
    "c": {
        "language": "c",
        "filename": "main.c",
    },
    "cpp": {
        "language": "c++",
        "filename": "main.cpp",
    },
}


ONLINE_COMPILER_URL = (
    "https://api.onlinecompiler.io/api/v2/piston/execute"
)


def execute_online(language: str, code: str, stdin: str = ""):
    api_key = os.getenv("ONLINECOMPILER_API_KEY")

    if not api_key:
        raise RuntimeError(
            "ONLINECOMPILER_API_KEY is missing in server environment."
        )

    config = LANGUAGE_CONFIG[language]

    payload = {
        "language": config["language"],
        "version": "*",
        "files": [
            {
                "name": config["filename"],
                "content": code,
            }
        ],
        "stdin": stdin,
        "run_timeout": 10000,
    }

    start_time = time.perf_counter()

    try:
        response = requests.post(
            ONLINE_COMPILER_URL,
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=40,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"OnlineCompiler API error "
                f"({response.status_code}): {response.text[:1000]}"
            )

        data = response.json()

        compile_result = data.get("compile") or {}
        run_result = data.get("run") or {}

        # Compilation error
        if compile_result.get("code", 0) != 0:
            return {
                "success": False,
                "output": compile_result.get("stdout", "")[-20000:],
                "error": compile_result.get("stderr", "")[-20000:],
                "execution_time": round(
                    time.perf_counter() - start_time, 3
                ),
                "exit_code": compile_result.get("code", 1),
            }

        if not run_result:
            raise RuntimeError(
                data.get("message", "Invalid execution response.")
            )

        output = run_result.get("stdout", "")
        error = run_result.get("stderr", "")
        exit_code = run_result.get("code")

        if exit_code is None:
            exit_code = 1

        if run_result.get("status") == "TO" and not error:
            error = "Execution timed out."

        wall_time = run_result.get("wall_time")

        if wall_time is not None:
            execution_time = round(wall_time / 1000, 3)
        else:
            execution_time = round(
                time.perf_counter() - start_time, 3
            )

        return {
            "success": exit_code == 0 and not error,
            "output": output[-20000:],
            "error": error[-20000:],
            "execution_time": execution_time,
            "exit_code": exit_code,
        }

    except requests.Timeout:
        raise RuntimeError(
            "Online execution request timed out."
        )

    except requests.RequestException as error:
        raise RuntimeError(
            f"OnlineCompiler connection failed: {error}"
        )

    except ValueError:
        raise RuntimeError(
            "OnlineCompiler returned an invalid response."
        )


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

    # Hosted execution through OnlineCompiler
    return execute_online(language, code, stdin)
