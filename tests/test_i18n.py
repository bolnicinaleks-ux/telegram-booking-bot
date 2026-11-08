"""Проверка локализации без запуска бота.

- каждая русская строка в коде либо обёрнута в _(), либо это лог, текст исключения или docstring;
- у каждого ключа _() есть английский перевод с теми же {плейсхолдерами};
- аргументы _() совпадают с плейсхолдерами ключа; лишних переводов нет.

Запуск: python -m tests.test_i18n
"""
import ast
import pathlib
import re
import string
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent / "bot"
CYR = re.compile(r"[А-Яа-яЁё]")
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}
ERRORS = {"RuntimeError", "ValueError", "FormError"}
SKIP = {ROOT / "i18n.py", ROOT / "locales" / "en.py"}


def placeholders(s: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(s) if name}


def nearest_call(node, parents):
    p = parents.get(node)
    while p is not None and not isinstance(p, ast.Call):
        if isinstance(p, ast.Raise):
            return p
        p = parents.get(p)
    return p


def call_kind(call) -> str:
    if isinstance(call, ast.Raise):
        return "error"
    f = call.func
    if isinstance(f, ast.Name) and f.id == "_":
        return "key"
    if isinstance(f, ast.Attribute) and f.attr in LOG_METHODS:
        return "log"
    if isinstance(f, ast.Name) and f.id in ERRORS:
        return "error"
    return "other"


def main() -> None:
    sys.path.insert(0, str(ROOT.parent))
    from bot.locales.en import EN

    problems, keys = [], {}
    for path in sorted(ROOT.rglob("*.py")):
        if path in SKIP:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        rel = path.relative_to(ROOT.parent)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_":
                arg = node.args[0] if node.args else None
                if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                    problems.append(f"{rel}:{node.lineno}: первый аргумент _() должен быть строковой константой")
                    continue
                kwargs = {k.arg for k in node.keywords}
                if placeholders(arg.value) != kwargs:
                    problems.append(f"{rel}:{node.lineno}: плейсхолдеры {placeholders(arg.value)} ≠ аргументы {kwargs}")
                keys.setdefault(arg.value, f"{rel}:{node.lineno}")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and CYR.search(node.value):
                parent = parents.get(node)
                if isinstance(parent, ast.Expr):  # docstring
                    continue
                call = nearest_call(node, parents)
                if call is None or call_kind(call) == "other":
                    problems.append(f"{rel}:{node.lineno}: русская строка без _(): {node.value[:50]!r}")

    for key, where in keys.items():
        if key not in EN:
            problems.append(f"{where}: нет перевода: {key[:60]!r}")
        elif placeholders(EN[key]) != placeholders(key):
            problems.append(f"{where}: плейсхолдеры перевода не совпадают: {key[:60]!r}")
        elif CYR.search(EN[key]):
            problems.append(f"{where}: в переводе остались русские буквы: {EN[key][:60]!r}")
    for key in EN.keys() - keys.keys():
        problems.append(f"лишний перевод (ключа нет в коде): {key[:60]!r}")

    if problems:
        print("\n".join(problems))
        print(f"\nПроблем: {len(problems)}")
        sys.exit(1)
    print(f"✔ локализация: {len(keys)} строк, все переведены\n\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
