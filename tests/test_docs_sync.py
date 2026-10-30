"""Docs stay in sync with the code: generated files, op coverage, TL;DRs, links, skills, CLI examples."""
import importlib.util
import re
from pathlib import Path

import pytest

import eightbit_studio as bms

ROOT = Path(__file__).resolve().parent.parent
MD_FILES = sorted({*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md"), *(ROOT / "skills").rglob("*.md"),
                   *(ROOT / "examples").rglob("*.md"), *(ROOT / "samples").rglob("*.md")})
DOC_PAGES = sorted((ROOT / "docs").rglob("*.md")) + [ROOT / "samples/README.md", ROOT / "examples/README.md", ROOT / "AGENTS.md"]
FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.S)
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)|!\[[^\]]*\]\(([^)\s]+)\)")


def _read(p):
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


def _gen_docs():
    spec = importlib.util.spec_from_file_location("gen_docs", ROOT / "scripts/gen_docs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def core_ops():
    return [n for n, o in bms.OPS.items() if o.owner == "core"]


def test_generated_files_are_up_to_date():
    stale = [rel for rel, txt in _gen_docs().generate().items() if _read(ROOT / rel) != txt]
    assert not stale, f"run `python scripts/gen_docs.py` (stale: {stale})"


@pytest.mark.parametrize("doc", ["AGENTS.md", "docs/cli-reference.md"])
def test_every_op_is_documented(doc):
    text = _read(ROOT / doc)
    missing = [n for n in core_ops() if f"`{n}`" not in text]
    assert not missing, f"{doc} lacks ops {missing}"


def test_intent_ops_present():
    want = {"compose", "variation", "extend", "remix", "loopify", "soundpack", "stems", "master", "describe", "diff", "critique", "suggest", "intent"}
    assert want <= set(core_ops())


@pytest.mark.parametrize("page", DOC_PAGES, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_page_has_tldr(page):
    head = "\n".join(_read(page).splitlines()[:8])
    assert "**TL;DR**" in head, f"{page.relative_to(ROOT)}: add a '> **TL;DR** …' line under the title"


def test_skills_have_frontmatter():
    skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
    assert len(skills) >= 8
    for s in skills:
        text = _read(s)
        m = re.match(r"---\n(.*?)\n---\n", text, re.S)
        assert m, f"{s}: missing frontmatter"
        meta = dict(re.findall(r"^(\w+):\s*(.+)$", m.group(1), re.M))
        assert meta.get("name") == s.parent.name, f"{s}: name must match folder"
        assert len(meta.get("description", "")) > 20, f"{s}: description too short"


def _links(text):
    text = FENCE.sub("", text)
    text = re.sub(r"`[^`\n]*`", "", text)
    for a, b in LINK.findall(text):
        yield a or b


def test_relative_links_resolve():
    bad = []
    for md in MD_FILES + [ROOT / "llms.txt"]:
        for link in _links(_read(md)):
            if re.match(r"^[a-z]+:", link) or link.startswith("#"):
                continue
            target = (md.parent / link.split("#")[0]).resolve()
            if not target.exists():
                bad.append(f"{md.relative_to(ROOT)} -> {link}")
    assert not bad, "broken links:\n" + "\n".join(bad)


def _subcommands():
    ap = bms.build_parser()
    for a in ap._actions:
        if a.__class__.__name__ == "_SubParsersAction":
            return set(a.choices)
    raise AssertionError("no subparsers")


def test_cli_examples_use_real_subcommands():
    subs = _subcommands()
    files = MD_FILES + sorted((ROOT / "examples").glob("*.sh")) + sorted((ROOT / "examples").glob("*.ps1"))
    bad = []
    for f in files:
        text = _read(f)
        blocks = FENCE.findall(text) if f.suffix == ".md" else [text]
        for block in blocks:
            for line in block.splitlines():
                for sub in re.findall(r"(?<![\w/.\-\"'])8bms\s+([a-z][\w-]*)", line):
                    if sub not in subs:
                        bad.append(f"{f.relative_to(ROOT)}: 8bms {sub}  ({line.strip()[:70]})")
    assert not bad, "unknown subcommands:\n" + "\n".join(bad)


def test_llms_txt_lists_every_skill():
    text = _read(ROOT / "llms.txt")
    for s in (ROOT / "skills").glob("*/SKILL.md"):
        assert f"skills/{s.parent.name}/SKILL.md" in text
