"""生成 T012/NEXT-04 旧式 DOC/XLS 固定样本（真实 OLE2 二进制格式）。

与 SDD 文档生成脚本无关，也不在 tools/make_fixture_binaries.py 内实现：本脚本需要
系统 LibreOffice（soffice/libreoffice），而那个脚本只依赖项目依赖并保证任何环境下
确定性生成。

生成对象（均来自同目录的 OOXML 夹具，内容已知）：

    tests/fixtures/office/notice.doc   MS Word 97（OLE2 复合文档）
    tests/fixtures/office/notice.xls   MS Excel 97-2003（OLE2 复合文档）

生成路线：

    notice.docx --soffice--> notice.odt --soffice--> notice.doc
    notice.xlsx --soffice--> notice.xls

DOC 走 ODT 中转不是形式要求。实测 LibreOffice 24.2.7.2 对 python-docx 写出的
DOCX 直接 `--convert-to doc` 时，导出结果虽含单元格标记（0x07），再读回却把表格
拉平成普通段落（含边框/无边框、auto/dxa 宽度均复现）；换成 LibreOffice 自己写出的
DOCX 或 ODT 作为输入则表格保留。本项目只做 .doc/.xls → docx/xlsx 方向的转换，
不产出 .doc，故该导出缺陷不影响解析链路；夹具经 ODT 中转以保证 .doc 内确有表格，
使“表格结构保留”这一验收项有真实对象可验。

用法：

    # 需要系统组件，先确认：command -v soffice
    uv run --locked --no-python-downloads python tools/make_legacy_fixtures.py
    uv run --locked --no-python-downloads python tools/make_legacy_fixtures.py --force

输出为固定样本：同版本 LibreOffice 下重复运行字节一致（脚本会与记录值比对，
不一致时不覆盖已提交夹具，只打印实际哈希并给出同步提示；确认更新时用 --force）。
自产样本只用于离线结构验证，不代表真实站点验收，也不得改扩展名冒充：脚本会校验
输出为 OLE2 复合文档。
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "office"

OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
CONVERT_TIMEOUT_SECONDS = 120

# 记录值对应 LibreOffice 24.2.7.2 420(Build:2)（Ubuntu 24.04），用于判断本次运行
# 是否复现同一批字节；不一致时不删除已生成文件，只提示需同步证据与哈希。
RECORDED_SHA256 = {
    "notice.doc": "71dd62f6c722ce3f65d17c1ad83ba070171a63d22c9f930e9c740a4f7f2aa765",
    "notice.xls": "aa8bbcb06f7d8b0a07468ae0f48326e54616aa6142c47b03e7972420c7a8e069",
}


def find_soffice() -> str:
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return path
    raise SystemExit("未找到 LibreOffice（soffice/libreoffice），无法生成旧式样本")


def convert(soffice: str, profile: Path, source: Path, target: str, outdir: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    command = [
        soffice,
        f"-env:UserInstallation=file://{profile}",
        "--headless",
        "--norestore",
        "--nologo",
        "--convert-to",
        target,
        "--outdir",
        str(outdir),
        str(source),
    ]
    result = subprocess.run(
        command, capture_output=True, timeout=CONVERT_TIMEOUT_SECONDS, check=False
    )
    output = outdir / f"{source.stem}.{target}"
    if result.returncode != 0 or not output.is_file():
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise SystemExit(f"转换失败 {source.name} -> {target}（code={result.returncode}）：{message}")
    return output


def build(soffice: str, work: Path, docx: Path, xlsx: Path) -> list[Path]:
    profile = work / "profile"
    odt = convert(soffice, profile, docx, "odt", work / "odt")
    doc = convert(soffice, profile, odt, "doc", work / "doc")
    xls = convert(soffice, profile, xlsx, "xls", work / "xls")
    return [doc, xls]


def install(generated: list[Path]) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for path in generated:
        if not path.read_bytes().startswith(OLE2_MAGIC):
            raise SystemExit(f"{path.name} 不是 OLE2 复合文档，拒绝写入夹具目录")
        shutil.copyfile(path, FIXTURES / path.name)


def report(generated: list[Path]) -> bool:
    """打印生成结果与记录值的比对；返回是否与记录完全一致。"""
    mismatched = []
    for path in generated:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        recorded = RECORDED_SHA256.get(path.name)
        state = "与记录一致" if recorded == digest else f"与记录不一致（记录值 {recorded}）"
        if recorded != digest:
            mismatched.append(path.name)
        print(f"notice{path.suffix}  {path.stat().st_size} bytes  sha256={digest}  {state}")
    return not mismatched


def main(argv: list) -> int:
    force = "--force" in argv
    soffice = find_soffice()
    docx = FIXTURES / "notice.docx"
    xlsx = FIXTURES / "notice.xlsx"
    for source in (docx, xlsx):
        if not source.is_file():
            raise SystemExit(f"缺少源夹具 {source}；先运行 tools/make_fixture_binaries.py")
    with tempfile.TemporaryDirectory(prefix="crawl-legacy-fixtures-") as tmp:
        generated = build(soffice, Path(tmp), docx, xlsx)
        if report(generated) or force:
            install(generated)
            return 0
        print(
            "提示：字节与记录不同（可能换了 LibreOffice 版本或系统字体），本次未覆盖"
            "已提交夹具。若确认更新，请先核对结构用例，再用 --force 写入，并同步"
            "evidence/T010-T013-parsers.md、夹具 README 与本脚本的记录值。"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
