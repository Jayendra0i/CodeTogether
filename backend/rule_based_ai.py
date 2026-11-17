
import re


def explain_code(code, language):
    if not code.strip():
        return "Please provide code to explain."

    lines = code.splitlines()
    result = [
        f"# {language} Code Explanation\n",
        f"Your code contains {len(lines)} lines.\n"
    ]

    for number, line in enumerate(lines, 1):
        clean = line.strip()

        if not clean:
            continue

        if clean.startswith("#") or clean.startswith("//"):
            explanation = "This is a comment."
        elif re.search(r"\b(print|console\.log|System\.out\.println)\b", clean):
            explanation = "This statement displays output."
        elif re.search(r"\b(if|else|elif|switch|case)\b", clean):
            explanation = "This is a conditional statement."
        elif re.search(r"\b(for|while)\b", clean):
            explanation = "This is a loop used for repetition."
        elif re.search(r"\b(def|function|class)\b", clean):
            explanation = "This defines a function or class."
        elif "=" in clean:
            explanation = "This statement assigns or updates a value."
        else:
            explanation = "This statement performs an operation."

        result.append(f"Line {number}: `{clean}`\n{explanation}\n")

    return "\n".join(result)


def fix_code(code, language):
    if not code.strip():
        return "Please provide code to check."

    suggestions = []

    if code.count("(") != code.count(")"):
        suggestions.append("Check your parentheses: opening and closing counts do not match.")

    if code.count("[") != code.count("]"):
        suggestions.append("Check your square brackets.")

    if code.count("{") != code.count("}"):
        suggestions.append("Check your curly braces.")

    if language.lower() == "python":
        for number, line in enumerate(code.splitlines(), 1):
            if line.rstrip().endswith(":"):
                continue

            if re.match(r"^\s*(if|elif|else|for|while|def|class|try|except)\b", line):
                suggestions.append(
                    f"Line {number}: Check whether this statement needs a colon (:)."
                )

    if not suggestions:
        return "No common syntax issues were detected by the basic checker. This does not guarantee that the code is error-free."

    return "Possible issues found:\n\n" + "\n".join(
        f"- {item}" for item in suggestions
    )


def generate_code(message, language):
    request = message.lower()

    templates = {
        "python": {
            "hello": 'print("Hello, World!")',
            "sum": "a = 10\nb = 20\nprint('Sum:', a + b)",
            "factorial": "n = 5\nresult = 1\nfor i in range(1, n + 1):\n    result *= i\nprint(result)",
            "even": "num = 10\nif num % 2 == 0:\n    print('Even')\nelse:\n    print('Odd')",
        },
        "java": {
            "hello": 'public class Main {\n    public static void main(String[] args) {\n        System.out.println("Hello, World!");\n    }\n}',
            "sum": "public class Main {\n    public static void main(String[] args) {\n        int a = 10, b = 20;\n        System.out.println(a + b);\n    }\n}",
        },
        "javascript": {
            "hello": 'console.log("Hello, World!");',
            "sum": "let a = 10;\nlet b = 20;\nconsole.log(a + b);",
        },
        "c": {
            "hello": '#include <stdio.h>\nint main() {\n    printf("Hello, World!");\n    return 0;\n}',
        },
        "c++": {
            "hello": '#include <iostream>\nusing namespace std;\nint main() {\n    cout << "Hello, World!";\n    return 0;\n}',
        },
    }

    lang = language.lower()
    examples = templates.get(lang, templates["python"])

    for keyword, template in examples.items():
        if keyword in request:
            return f"Here is a {language} example:\n\n```{lang}\n{template}\n```"

    return (
        f"I can generate basic {language} examples for Hello World, "
        "sum, factorial and even/odd programs. Please specify one of these."
    )


def optimize_code(code, language):
    if not code.strip():
        return "Please provide code to optimize."

    lines = code.splitlines()
    non_empty = [line for line in lines if line.strip()]

    return (
        f"Basic Code Review ({language})\n\n"
        f"- Total lines: {len(lines)}\n"
        f"- Non-empty lines: {len(non_empty)}\n"
        "- Remove unnecessary blank lines.\n"
        "- Use meaningful variable names.\n"
        "- Avoid repeating the same logic.\n"
        "- Break large functions into smaller functions.\n"
        "- Add comments where logic is difficult to understand.\n\n"
        "Note: These are general suggestions, not automatic code optimization."
    )


def ask_question(message, code, language):
    question = message.lower()

    answers = {
        "loop": "A loop repeats a block of code. Common types are for and while loops.",
        "function": "A function is a reusable block of code that performs a particular task.",
        "array": "An array stores multiple values in an indexed collection.",
        "variable": "A variable is a named storage location used to hold data.",
        "class": "A class is a blueprint used to create objects.",
        "oops": "OOP is based on four main concepts: Encapsulation, Inheritance, Polymorphism and Abstraction.",
        "recursion": "Recursion is a technique in which a function calls itself.",
        "error": "An error is a problem that prevents a program from working as expected.",
    }

    for keyword, answer in answers.items():
        if keyword in question:
            return answer

    if code.strip():
        return (
            f"You are working with {language} code.\n"
            "I can help explain the code, check common syntax issues, "
            "or suggest basic improvements. Please ask a specific question."
        )

    return (
        "I am CodeTogether's basic coding assistant. "
        "Ask me about variables, loops, functions, arrays, classes, OOP or recursion."
    )


def process_ai_request(task, language, code, message):
    if task == "explain":
        return explain_code(code, language)

    if task == "fix":
        return fix_code(code, language)

    if task == "generate":
        return generate_code(message, language)

    if task == "optimize":
        return optimize_code(code, language)

    if task == "ask":
        return ask_question(message, code, language)

    return "Unsupported AI task."
