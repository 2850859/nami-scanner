"""
Markdown → PDF 変換スクリプト
fpdf2 + 游明朝フォントで日本語 PDF を生成する。
"""
import argparse
import pathlib
import re
import markdown
from fpdf import FPDF

# ─── フォントパス ─────────────────────────────────────────────────
FONT_REGULAR = r"C:\Windows\Fonts\yumin.ttf"
FONT_BOLD    = r"C:\Windows\Fonts\yumindb.ttf"

# ─── カラー定義 ────────────────────────────────────────────────────
C_TEXT      = (26,  26,  26)
C_HEADING   = (26,  58, 107)
C_SUB       = (42,  90, 155)
C_BG_TH     = (232, 238, 248)
C_BORDER    = (192, 208, 224)
C_BG_CODE   = (240, 242, 248)
C_BORDER_PRE= (26,  58, 107)
C_RULE      = (204, 204, 221)


class MdPDF(FPDF):
    """Markdown パース結果を描画する FPDF サブクラス。"""

    def header(self):
        pass  # ヘッダーなし

    def footer(self):
        self.set_y(-12)
        self.set_font("YuMincho", size=8)
        self.set_text_color(*C_TEXT)
        self.cell(0, 6, f"{self.page_no()}", align="C")

    # ── 行区切り線 ──────────────────────────────────────────────────
    def hr(self):
        self.set_draw_color(*C_RULE)
        self.line(self.get_x(), self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)

    # ── 見出し ──────────────────────────────────────────────────────
    def heading(self, text: str, level: int):
        sizes  = {1: 18, 2: 14, 3: 12, 4: 11}
        colors = {1: C_HEADING, 2: C_HEADING, 3: C_SUB, 4: C_SUB}
        sz = sizes.get(level, 11)
        cl = colors.get(level, C_TEXT)

        if level >= 2:
            self.ln(4)

        self.set_font("YuMinchoB", size=sz)
        self.set_text_color(*cl)
        self.multi_cell(0, sz * 0.45, text, new_x="LMARGIN", new_y="NEXT")

        if level in (1, 2):
            lw = 0.5 if level == 1 else 0.3
            self.set_draw_color(*C_HEADING)
            self.set_line_width(lw)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(2)

        self.set_font("YuMincho", size=11)
        self.set_text_color(*C_TEXT)
        self.ln(1)

    # ── 本文段落 ────────────────────────────────────────────────────
    def paragraph(self, text: str):
        self.set_font("YuMincho", size=11)
        self.set_text_color(*C_TEXT)
        self.multi_cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    # ── リスト行 ────────────────────────────────────────────────────
    def list_item(self, text: str, indent: int = 0):
        self.set_font("YuMincho", size=10.5)
        self.set_text_color(*C_TEXT)
        x_orig = self.l_margin
        indent_px = indent * 5 + 4
        bullet = "• " if indent == 0 else "◦ "
        self.set_left_margin(x_orig + indent_px)
        self.set_x(x_orig + indent_px)
        self.multi_cell(0, 5.5, bullet + text, new_x="LMARGIN", new_y="NEXT")
        self.set_left_margin(x_orig)
        self.ln(0.5)

    # ── コードブロック ──────────────────────────────────────────────
    def code_block(self, lines: list[str]):
        self.set_font("YuMincho", size=9)
        self.set_fill_color(*C_BG_CODE)
        self.set_draw_color(*C_BORDER_PRE)
        self.set_line_width(0.5)
        lh = 4.5
        total_h = lh * len(lines) + 6
        # 塗り背景
        x0, y0 = self.l_margin, self.get_y()
        w0 = self.w - self.l_margin - self.r_margin
        self.set_fill_color(*C_BG_CODE)
        self.rect(x0, y0, w0, total_h, "F")
        # 左ボーダー
        self.set_draw_color(*C_BORDER_PRE)
        self.set_line_width(1.5)
        self.line(x0, y0, x0, y0 + total_h)
        self.set_line_width(0.2)
        # テキスト
        self.set_xy(x0 + 4, y0 + 3)
        self.set_text_color(*C_TEXT)
        for line in lines:
            self.set_x(x0 + 4)
            self.multi_cell(w0 - 6, lh, line, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    # ── テーブル ────────────────────────────────────────────────────
    def table(self, rows: list[list[str]], has_header: bool = True):
        if not rows:
            return
        col_n = max(len(r) for r in rows)
        avail = self.w - self.l_margin - self.r_margin
        col_w = avail / col_n

        lh = 5.5
        self.set_font("YuMincho", size=9.5)
        self.set_line_width(0.2)

        for ri, row in enumerate(rows):
            is_hdr = (ri == 0 and has_header)
            row_h = lh

            if is_hdr:
                self.set_fill_color(*C_BG_TH)
                self.set_text_color(*C_HEADING)
                self.set_font("YuMinchoB", size=9.5)
            else:
                fill = (247, 249, 252) if ri % 2 == 0 else (255, 255, 255)
                self.set_fill_color(*fill)
                self.set_text_color(*C_TEXT)
                self.set_font("YuMincho", size=9.5)

            self.set_draw_color(*C_BORDER)
            x_start = self.l_margin
            y_start = self.get_y()

            # 各セルの実際の高さを計測して最大を取得
            max_h = row_h
            for ci in range(col_n):
                cell_text = row[ci] if ci < len(row) else ""
                lines = self.multi_cell(col_w, row_h, cell_text, border=0,
                                        dry_run=True, output="LINES")
                h = len(lines) * row_h
                max_h = max(max_h, h)

            # 描画
            for ci in range(col_n):
                cell_text = row[ci] if ci < len(row) else ""
                self.set_xy(x_start + ci * col_w, y_start)
                self.set_fill_color(*(C_BG_TH if is_hdr else ((247, 249, 252) if ri % 2 == 0 else (255, 255, 255))))
                self.multi_cell(col_w, row_h, cell_text, border=1,
                                fill=True, new_x="RIGHT", new_y="TOP",
                                max_line_height=row_h)

            self.set_xy(self.l_margin, y_start + max_h)

        self.ln(3)


# ─── Markdown → 描画コマンドに変換 ─────────────────────────────────────
def _strip_inline(text: str) -> str:
    """インラインマークダウン（**bold**, `code`, [link]()）を除去してプレーンテキスト化。"""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*",   r"\1", text)
    text = re.sub(r"`(.+?)`",     r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    return text.strip()


def render_md(pdf: MdPDF, md_text: str):
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        # 見出し
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            level = len(m.group(1))
            pdf.heading(_strip_inline(m.group(2)), level)
            i += 1
            continue

        # 水平線
        if re.match(r"^---+\s*$", line):
            pdf.hr()
            i += 1
            continue

        # コードブロック
        if line.startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            pdf.code_block(code_lines)
            i += 1  # 閉じる ```
            continue

        # テーブル
        if "|" in line:
            table_rows = []
            while i < len(lines) and "|" in lines[i]:
                row_text = lines[i]
                # セパレータ行 (|---|---) をスキップ
                if re.match(r"^\|?[\s\-\|:]+\|?\s*$", row_text):
                    i += 1
                    continue
                cells = [_strip_inline(c) for c in row_text.strip().strip("|").split("|")]
                table_rows.append(cells)
                i += 1
            if table_rows:
                pdf.table(table_rows, has_header=True)
            continue

        # リスト
        m_li = re.match(r"^(\s*)[-*]\s+(.*)", line)
        if m_li:
            indent = len(m_li.group(1)) // 2
            pdf.list_item(_strip_inline(m_li.group(2)), indent)
            i += 1
            continue

        # 空行
        if line.strip() == "":
            pdf.ln(2)
            i += 1
            continue

        # 通常テキスト
        pdf.paragraph(_strip_inline(line))
        i += 1


def convert(md_path: str, pdf_path: str) -> None:
    src = pathlib.Path(md_path)
    dst = pathlib.Path(pdf_path)

    md_text = src.read_text(encoding="utf-8")

    pdf = MdPDF(format="A4")
    pdf.set_margins(left=18, top=18, right=18)
    pdf.add_font("YuMincho",  fname=FONT_REGULAR)
    pdf.add_font("YuMinchoB", fname=FONT_BOLD)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_font("YuMincho", size=11)

    render_md(pdf, md_text)

    pdf.output(str(dst))
    size_kb = dst.stat().st_size // 1024
    print(f"PDF生成完了: {dst}  ({size_kb} KB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("md", help="入力 Markdown ファイル")
    ap.add_argument("pdf", nargs="?", help="出力 PDF ファイル（省略時は同名.pdf）")
    args = ap.parse_args()
    pdf_file = args.pdf or str(pathlib.Path(args.md).with_suffix(".pdf"))
    convert(args.md, pdf_file)
