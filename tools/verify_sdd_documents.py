"""Read-only structural validation for the SDD document set and demo data."""
from pathlib import Path
from hashlib import sha256
from collections import Counter
from urllib.parse import unquote
import json
import re
import sys

if sys.version_info < (3, 9):
    raise RuntimeError("Python 3.9 or later is required for SDD document validation.")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "specs/001-public-knowledge-collection"

def check(condition, message):
    if not condition:
        raise AssertionError(message)

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def read_jsonl(path):
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        check(bool(line.strip()), f"blank JSONL line: {path}:{i}")
        row = json.loads(line)
        check(isinstance(row, dict), f"JSONL line is not an object: {path}:{i}")
        rows.append(row)
    return rows

def main():
    matrix = read_json(OUT / "traceability.json")
    reqs = matrix["requirements"]
    req_ids = {r["id"] for r in reqs}
    test_ids = {r["test"] for r in reqs}
    task_ids = {t["id"] for t in matrix["tasks"]}
    q_ids = {q["id"] for q in matrix["issues"]}
    check(len(req_ids) == len(reqs), "duplicate requirement ID")
    check(len(test_ids) == len(reqs), "acceptance IDs not one per requirement")
    check(len(task_ids) == len(matrix["tasks"]), "duplicate task ID")
    check(len(q_ids) == len(matrix["issues"]), "duplicate question ID")
    check(set(matrix["common_requirement_mapping"]) == {f"C{i:02d}" for i in range(1,18)}, "C01-C17 not complete")
    for key, values in matrix["common_requirement_mapping"].items():
        check(set(values.split()) <= req_ids, f"unknown requirement in {key}")
    spec = (OUT / "spec.md").read_text(encoding="utf-8")
    acceptance = (OUT / "acceptance.md").read_text(encoding="utf-8")
    tasks = (OUT / "tasks.md").read_text(encoding="utf-8")
    issues = (OUT / "clarifications.md").read_text(encoding="utf-8")
    trace = (OUT / "traceability.md").read_text(encoding="utf-8")
    for r in reqs:
        check(spec.count(f"### {r['id']} ") == 1, f"spec ID: {r['id']}")
        check(acceptance.count(f"### {r['test']} ") == 1, f"acceptance ID: {r['test']}")
        check(f"| {r['id']} " in trace, f"trace missing: {r['id']}")
        check(r["task"] in task_ids, f"task not found: {r['id']}")
        check(set(r["issues"].split()) <= q_ids, f"issue not found: {r['id']}")
        check(bool(r["source"]) and bool(r["action"]) and bool(r["expected"]), f"incomplete scenario: {r['id']}")
    for tid in task_ids:
        check(tasks.count(f"- [ ] {tid} ") == 1, f"task missing, duplicate or marked completed: {tid}")
    for qid in q_ids:
        check(issues.count(f"## {qid} ") == 1, f"question missing: {qid}")
    # Planned numeric dependencies form a DAG. Textual decision gates remain prose.
    dependencies = {t["id"]:set(re.findall(r"\bT\d{3}\b",t["dependencies"])) for t in matrix["tasks"]}
    def visit(tid, stack):
        check(tid not in stack, f"cyclic task dependency: {tid}")
        for dep in dependencies[tid]:
            check(dep in task_ids, f"unknown dependency: {dep}")
            visit(dep, stack | {tid})
    for tid in task_ids: visit(tid,set())
    for item in read_json(OUT / "sources/source-register.json"):
        p = (ROOT / item["path"]).resolve()
        check(p.is_relative_to((ROOT / "docs").resolve()), "source must be inside docs/")
        check(p.stat().st_size == item["bytes"], f"source size changed: {p.name}")
        check(sha256(p.read_bytes()).hexdigest() == item["sha256"], f"source hash changed: {p.name}")
    mds = [ROOT / "AGENTS.md", ROOT / "SDD文档说明.md", ROOT / ".specify/memory/constitution.md"] + list(OUT.rglob("*.md")) + list((ROOT / "docs").glob("*.md"))
    links = 0
    for p in mds:
        text = p.read_text(encoding="utf-8")
        check("\ufffd" not in text, f"replacement character: {p}")
        check(text.count("```") % 2 == 0, f"unclosed code fence: {p}")
        if p.name not in ("S1-transcript.md","S2-transcript.md"):
            check(not re.search(r"\[(?:FEATURE NAME|DATE|TODO|TBD)\]",text), f"unfilled template: {p}")
            used = set(re.findall(r"\b(?:FR|NFR|KR)-\d{3}\b",text))
            check(used <= req_ids, f"unknown requirement references in {p}: {used-req_ids}")
        for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)",text):
            target = match.group(1).strip().strip("<>")
            if re.match(r"^(https?://|mailto:)",target): continue
            pathpart, _, fragment = target.partition("#")
            resolved = (p.parent / unquote(pathpart)).resolve() if pathpart else p
            check(resolved.exists(), f"broken link in {p.name}: {target}")
            if fragment and resolved.suffix == ".md":
                headings = re.findall(r"^#+\s+(.+)$",resolved.read_text(encoding="utf-8"),flags=re.M)
                slugs = {re.sub(r"[^\w\s-]", "", h.lower()).replace(" ","-") for h in headings}
                check(unquote(fragment) in slugs, f"missing anchor: {p.name}: {target}")
            links += 1
    base=OUT / "examples/data"
    manifest=read_jsonl(base / "manifests/crawl_manifest.jsonl")
    documents=read_jsonl(base / "normalized/documents.jsonl")
    blocks=read_jsonl(base / "normalized/blocks.jsonl")
    failures=read_jsonl(base / "manifests/failed_records.jsonl")
    for rows,key in [(manifest,"crawl_id"),(documents,"doc_id"),(blocks,"block_id")]:
        check(len({x[key] for x in rows})==len(rows),f"duplicate {key}")
    crawls={m["crawl_id"]:m for m in manifest}
    docs={d["doc_id"]:d for d in documents}
    for m in manifest:
        p=(base/m["raw_path"]).resolve()
        check(p.is_relative_to(base.resolve()),"raw path escapes example data")
        check(p.is_file(),"missing raw file")
        check(sha256(p.read_bytes()).hexdigest()==m["sha256"],"raw hash mismatch")
    for d in documents:
        check(d["crawl_ids"] and set(d["crawl_ids"]) <= set(crawls),"missing crawl reference")
        check(any(crawls[c]["raw_path"]==d["raw_path"] for c in d["crawl_ids"]),"document raw not in crawls")
        check(sha256((base/d["raw_path"]).read_bytes()).hexdigest()==d["sha256"],"document raw hash mismatch")
        check(sha256(d["full_text"].encode()).hexdigest()==d["content_hash"],"content hash mismatch")
        for a in d.get("attachments",[]):
            check(a["crawl_id"] in crawls and a["doc_id"] in docs,"attachment reference mismatch")
            check(a["raw_path"]==crawls[a["crawl_id"]]["raw_path"],"attachment raw mismatch")
            check(a["sha256"]==crawls[a["crawl_id"]]["sha256"],"attachment hash mismatch")
    for b in blocks: check(b["doc_id"] in docs,"dangling block")
    for did,d in docs.items():
        bs=[b for b in blocks if b["doc_id"]==did]
        check([b["order"] for b in bs]==list(range(len(bs))),"example block order not contiguous from zero")
        check("\n".join(b["text"] for b in bs)==d["full_text"],"example full text differs from blocks")
    # Independently guard original table required levels against accidental promotion.
    expected = {
        "manifest":"crawl_id source_id requested_url final_url crawl_time http_status content_type raw_path sha256 discovery_method",
        "document":"doc_id source_id source_name source_url title full_text language document_type raw_path sha256 crawl_time extraction_method parse_status",
        "block":"block_id doc_id order block_type extraction_method",
        "failure":"source_id url time stage error_type message retry_count final_action",
    }
    for name,required in expected.items():
        sch=read_json(OUT/f"contracts/{name}.schema.json")
        check(set(sch["required"])==set(required.split()),f"required levels changed: {name}")
    # Standalone source registry is a disabled demo, never a live configuration.
    check(read_json(OUT/"examples/source-registry.json")["enabled"] is False,"demo source enabled")
    for p in OUT.rglob("*.json"): read_json(p)
    print(json.dumps({"status":"PASS","requirements":len(reqs),"tasks":len(task_ids),"acceptance_cases":len(test_ids),
        "open_decisions":len(q_ids),"common_requirements":17,"markdown_files":len(mds),"local_links_checked":links,
        "source_hashes_verified":4,"demo_manifests":len(manifest),"demo_documents":len(documents),
        "demo_blocks":len(blocks),"demo_failures":len(failures),"scope":"documentation and fictional fixtures only"},ensure_ascii=False))

if __name__=="__main__": main()
