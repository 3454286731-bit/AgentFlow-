"""
软著源代码文档生成器。

登记要求（中国版权保护中心）：
- 提交源代码前后各连续 30 页，合计 60 页；不足 60 页的全部提交
- 每页不少于 50 行
- 页眉标注软件名称与版本号
- 首页应为程序入口

本脚本按上述要求排版并输出 PDF，中文字体使用 reportlab 内置的 CID 字体，
无需额外下载字体文件。

用法：
    python scripts/gen_source_doc.py frontend
    python scripts/gen_source_doc.py backend
    python scripts/gen_source_doc.py all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
FONT = 'STSong-Light'
FONT_SIZE = 8.5
LINE_HEIGHT = 13.2
LINES_PER_PAGE = 50
FRONT_PAGES = 30
BACK_PAGES = 30

MARGIN_X = 46
MARGIN_TOP = 62
MARGIN_BOTTOM = 46

CONFIGS: dict[str, dict] = {
    'frontend': {
        'name': 'AI 教学场景智能体工作流可视化编排系统',
        'version': 'V1.0',
        'root': ROOT / 'frontend' / 'src',
        'out': ROOT / 'docs' / '软著材料' / '软著一_教学场景可视化编排系统_源代码.pdf',
        # 入口文件放最前，符合「首页为程序入口」的要求
        'files': [
            'main.tsx',
            'App.tsx',
            'store.ts',
            'types.ts',
            'api/client.ts',
            'components/Canvas.tsx',
            'components/SchemaForm.tsx',
            'components/ConfigPanel.tsx',
            'components/RunPanel.tsx',
            'components/HistoryPanel.tsx',
            'components/WorkflowPicker.tsx',
            'components/ExecutionResult.tsx',
            'components/NodePalette.tsx',
            'components/Toolbar.tsx',
            'nodes/WorkflowNodeCard.tsx',
            'styles.css',
        ],
    },
    'backend': {
        'name': '智能体工作流调度引擎系统',
        'version': 'V1.0',
        'root': ROOT / 'backend',
        'out': ROOT / 'docs' / '软著材料' / '软著二_调度引擎系统_源代码.pdf',
        'files': [
            'api/main.py',
            'api/routes.py',
            'engine/executor.py',
            'core/models.py',
            'core/graph.py',
            'core/expr.py',
            'core/providers.py',
            'nodes/base.py',
            'nodes/builtins.py',
            'db/database.py',
            'db/orm.py',
            'db/repository.py',
            'api/schemas.py',
            'api/deps.py',
        ],
    },
}


def collect_lines(root: Path, files: list[str]) -> list[str]:
    """按给定顺序拼接源码，文件之间插入分隔注释行。"""
    lines: list[str] = []
    for rel in files:
        path = root / rel
        if not path.exists():
            print(f'  跳过（不存在）: {rel}')
            continue
        # 文件标题直接接在上一份文件后面，保证首页第一行就是入口文件
        lines.append(f'/* ==================== {rel} ==================== */')
        for raw in path.read_text(encoding='utf-8').splitlines():
            lines.append(raw.rstrip())
        lines.append('')
    return lines


def paginate(lines: list[str]) -> list[list[str]]:
    return [
        lines[i:i + LINES_PER_PAGE]
        for i in range(0, len(lines), LINES_PER_PAGE)
    ]


def select_pages(pages: list[list[str]]) -> list[list[str]]:
    """前后各 30 页；不足 60 页则全部保留。"""
    if len(pages) <= FRONT_PAGES + BACK_PAGES:
        return pages
    return pages[:FRONT_PAGES] + pages[-BACK_PAGES:]


def fit(text: str, max_width: float) -> str:
    """按实际字宽截断，避免超出行宽。"""
    if not text:
        return ''
    if pdfmetrics.stringWidth(text, FONT, FONT_SIZE) <= max_width:
        return text

    # 先按字符估算截断点，再回退到刚好放得下
    approx = max(1, int(len(text) * max_width / pdfmetrics.stringWidth(text, FONT, FONT_SIZE)))
    while approx > 1 and pdfmetrics.stringWidth(text[:approx] + '…', FONT, FONT_SIZE) > max_width:
        approx -= 1
    return text[:approx] + '…'


def render(config: dict) -> Path:
    pdfmetrics.registerFont(UnicodeCIDFont(FONT))

    lines = collect_lines(config['root'], config['files'])
    pages = select_pages(paginate(lines))

    out: Path = config['out']
    out.parent.mkdir(parents=True, exist_ok=True)

    width, height = A4
    max_width = width - MARGIN_X * 2 - 34  # 左侧留出打印行号的位置

    pdf = canvas.Canvas(str(out), pagesize=A4)
    pdf.setTitle(f"{config['name']} {config['version']} 源代码")

    for index, page_lines in enumerate(pages, start=1):
        # 页眉
        pdf.setFont(FONT, 9)
        pdf.drawString(MARGIN_X, height - 34, f"{config['name']} {config['version']}")
        pdf.drawRightString(width - MARGIN_X, height - 34, f'第 {index} 页 / 共 {len(pages)} 页')
        pdf.setLineWidth(0.4)
        pdf.line(MARGIN_X, height - 40, width - MARGIN_X, height - 40)

        # 正文：带行号
        pdf.setFont(FONT, FONT_SIZE)
        y = height - MARGIN_TOP
        for offset, line in enumerate(page_lines):
            line_no = (index - 1) * LINES_PER_PAGE + offset + 1
            pdf.setFillColorRGB(0.55, 0.55, 0.55)
            pdf.drawRightString(MARGIN_X + 28, y, str(line_no))
            pdf.setFillColorRGB(0, 0, 0)
            pdf.drawString(MARGIN_X + 34, y, fit(line, max_width))
            y -= LINE_HEIGHT

        # 页脚
        pdf.setFont(FONT, 8)
        pdf.setFillColorRGB(0.5, 0.5, 0.5)
        pdf.drawCentredString(width / 2, MARGIN_BOTTOM - 14, f"{config['name']} {config['version']}")

        pdf.showPage()

    pdf.save()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description='生成软著源代码文档 PDF')
    parser.add_argument('target', choices=[*CONFIGS, 'all'], help='生成哪一份')
    args = parser.parse_args()

    targets = list(CONFIGS) if args.target == 'all' else [args.target]

    for key in targets:
        config = CONFIGS[key]
        out = render(config)
        size_kb = out.stat().st_size / 1024
        print(f'已生成：{out.relative_to(ROOT)}  ({size_kb:.0f} KB)')

    return 0


if __name__ == '__main__':
    sys.exit(main())
