#!/usr/bin/env python3
"""前端模块静态检查：python3 tests/test_frontend.py

不起服务、不开浏览器，只读 assets/js/ 下的 ES 模块源码和两个页面，
检查拆分/搬移代码时最容易犯、又只在浏览器里才炸的几类错误：
  1. import 的名字必须真被来源模块导出 —— 否则整页 SyntaxError 白屏
  2. 用到的项目内名字必须在本模块定义或 import —— 否则运行期 ReferenceError
     共享状态 state 的字段（currentUser/myRoom/roomChat…）必须写成 state.xxx，
     漏写前缀会命中这一条
  3. 从 main.js 出发要能走到所有模块 —— 漏 import 会让 registerView 不执行
  4. 页面里引用的本地脚本/样式都存在，且带 ?v= 版本号（避免浏览器缓存旧代码）
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS_DIR = ROOT / "assets" / "js"
ENTRY = "main"  # 模块名（不带扩展名），两个页面的 ES 模块入口
PAGES = ["index.html", "game.html"]

# 服务端注入的全局对象由 deploy/serve.py 提供，前端只能读 window.LIVE_CONFIG
results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


def strip_noise(text):
    """去掉注释与字符串内容，只留下会参与求值的标识符。

    模板字符串只保留 ${...} 里的表达式：里面的标识符是真会求值的。
    """
    text = re.sub(r"^\s*import .*$", "", text, flags=re.M)
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(
        r"`(?:[^`\\]|\\.)*`",
        lambda m: "\n" + "\n".join(re.findall(r"\$\{([^}]*)\}", m.group(0))) + "\n",
        text,
        flags=re.S,
    )
    text = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)
    text = re.sub(r"'(?:[^'\\]|\\.)*'", "''", text)
    # 展开运算符 ...x 的第 3 个点会被当成属性访问的点，抹掉它才好按“点前缀=属性”判断
    text = text.replace("...", " ")
    return text


def top_level(text):
    """模块顶层的函数/常量/类名。"""
    return set(
        re.findall(
            r"(?m)^(?:export )?(?:async )?(?:function|const|let|class) ([A-Za-z_$][\w$]*)",
            text,
        )
    )


def state_fields(core_raw):
    """core.js 里 state 对象的字段名——它们等价于全局共享变量。"""
    block = re.search(r"export const state = \{(.*?)\n\};", core_raw, flags=re.S)
    if not block:
        return set()
    return set(re.findall(r"(?m)^\s*([A-Za-z_$][\w$]*)\s*:", block.group(1)))


def imports_of(raw):
    """{本地模块名: {导入的名字}}，同时保留路径用于导出校验。"""
    named = {}
    sources = []
    for m in re.finditer(r'(?m)^\s*import\s+(.*?)\s+from\s+"([^"]+)"', raw, flags=re.S):
        clause, path = m.group(1), m.group(2)
        sources.append(path)
        local = path.split("/")[-1].removesuffix(".js")
        names = set()
        braces = re.search(r"\{(.*)\}", clause, flags=re.S)
        if braces:
            names |= {n.strip() for n in braces.group(1).split(",") if n.strip()}
        default = clause.split(",")[0].strip()
        if default and not default.startswith("{") and default != "*":
            names.add(default)
        named.setdefault(local, set()).update(names)
    for m in re.finditer(r'(?m)^\s*import\s+"([^"]+)"', raw):
        sources.append(m.group(1))
    return named, sources


def main():
    files = sorted(p for p in JS_DIR.rglob("*.js"))
    rel = {p.stem: p.relative_to(JS_DIR).as_posix() for p in files}
    raw = {p.stem: p.read_text(encoding="utf-8") for p in files}
    code = {name: strip_noise(text) for name, text in raw.items()}

    # 1. 导出校验
    exported = {
        name: set(re.findall(r"(?m)^export (?:async )?(?:function|const|let|class) ([A-Za-z_$][\w$]*)", text))
        for name, text in raw.items()
    }
    bad = []
    for name, text in raw.items():
        for m in re.finditer(r'(?m)^\s*import\s+\{(.*?)\}\s+from\s+"([^"]+)"', text, flags=re.S):
            target = m.group(2).split("/")[-1].removesuffix(".js")
            if target not in exported:
                bad.append(f"{rel[name]} 引用了不存在的模块 {m.group(2)}")
                continue
            for imported in {n.strip() for n in m.group(1).split(",") if n.strip()}:
                if imported not in exported[target]:
                    bad.append(f"{rel[name]} 从 {rel[target]} 导入 {imported}，但后者没有导出它")
    check("import 的名字都有对应导出", not bad, "; ".join(bad))

    # 2. 名字缺失（含 state 字段漏写前缀）
    fields = state_fields(raw.get("core", ""))
    owner = {}
    for name in code:
        for symbol in top_level(code[name]):
            owner.setdefault(symbol, name)
    for field in fields:
        owner[field] = "core"
    imported = {name: set() for name in code}
    for name, text in raw.items():
        named, _ = imports_of(text)
        for names in named.values():
            imported[name] |= names

    missing_report = []
    for name in sorted(code):
        body = code[name]
        missing = []
        for symbol, src in owner.items():
            if src == name or symbol in top_level(code[name]) or symbol in imported[name]:
                continue
            if re.search(r"(?<![\w.$])" + re.escape(symbol) + r"\b", body):
                hint = " 应写作 state." + symbol if symbol in fields else f"（定义在 {rel[src]}）"
                missing.append(symbol + hint)
        if missing:
            missing_report.append(f"{rel[name]}: " + ", ".join(sorted(missing)))
    check("模块内引用的名字都有来源", not missing_report, "; ".join(missing_report))

    # 3. 从入口可达
    reachable = {ENTRY}
    queue = [ENTRY]
    while queue:
        name = queue.pop()
        _, sources = imports_of(raw[name])
        for path in sources:
            target = path.split("/")[-1].removesuffix(".js")
            if target in code and target not in reachable:
                reachable.add(target)
                queue.append(target)
    unreachable = sorted(set(code) - reachable)
    check(f"{ENTRY} 可达全部模块", not unreachable, "未加载: " + ", ".join(rel[n] for n in unreachable))

    # 4. 页面引用的本地资源存在且带版本号
    problems = []
    for page in PAGES:
        html = (ROOT / page).read_text(encoding="utf-8")
        refs = re.findall(r'(?:src|href)="(assets/[^"]+)"', html)
        if not refs:
            problems.append(f"{page} 没有引用任何 assets 资源")
        for ref in refs:
            if "?" not in ref:
                problems.append(f"{page} 的 {ref} 没有 ?v= 版本号")
            if not (ROOT / ref.split("?")[0]).exists():
                problems.append(f"{page} 引用的 {ref} 不存在")
    check("页面资源存在且带版本号", not problems, "; ".join(problems))

    failed = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
