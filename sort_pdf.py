import subprocess
import sys
import os

req_file = os.path.join(os.path.dirname(__file__), "requirements_sort.txt")
if os.path.exists(req_file):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file, "-q"])

import re
import io
import pdfplumber
import pandas as pd
import streamlit as st
from pypdf import PdfReader, PdfWriter

EXCEL_EMP_COLUMN = "customEEID"
EMP_CODE_PATTERN = r"Ref:\s*\(per\)\s*/\s*file\s+(\d+)"

def extract_emp_code(text):
    match = re.search(EMP_CODE_PATTERN, text, re.IGNORECASE)
    return match.group(1).strip() if match else None

def get_emp_code_order(excel_bytes):
    df = pd.read_excel(io.BytesIO(excel_bytes))
    if EXCEL_EMP_COLUMN not in df.columns:
        return None, list(df.columns)
    codes = df[EXCEL_EMP_COLUMN].dropna().astype(str).str.strip().tolist()
    return codes

def reorder_pdf(pdf_bytes, ordered_codes):
    page_map = {}
    skipped = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        total = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            code = extract_emp_code(text)
            if code:
                page_map[code] = i
            else:
                skipped.append(i + 1)

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()

    matched = []
    not_in_pdf = []

    for code in ordered_codes:
        if code in page_map:
            writer.add_page(reader.pages[page_map[code]])
            matched.append(code)
        else:
            not_in_pdf.append(code)

    output_buffer = io.BytesIO()
    writer.write(output_buffer)
    output_buffer.seek(0)

    return output_buffer, total, len(matched), not_in_pdf, skipped

# ── STREAMLIT UI ────────────────────────────────────────────────
st.set_page_config(page_title="PDF Sorter", page_icon="🔀", layout="centered")

st.title("🔀 PDF Letter Sorter")
st.markdown("Upload the **Excel file** and the **multi-page PDF**. Pages will be reordered to match the Excel employee code order.")

col1, col2 = st.columns(2)
with col1:
    excel_file = st.file_uploader("Upload Excel File", type=["xlsx", "xls"])
with col2:
    pdf_file = st.file_uploader("Upload Multi-page PDF", type=["pdf"])

if excel_file and pdf_file:
    if st.button("Sort PDF", type="primary"):

        with st.spinner("Reading Excel..."):
            result = get_emp_code_order(excel_file.read())

        if result is None:
            st.error(f"Column **'{EXCEL_EMP_COLUMN}'** not found in Excel. Columns available: {result}")
        else:
            ordered_codes = result
            st.info(f"Found **{len(ordered_codes)}** employee codes in Excel.")

            with st.spinner("Reading PDF and sorting pages..."):
                output_buffer, total_pages, matched_count, not_in_pdf, skipped_pages = reorder_pdf(
                    pdf_file.read(), ordered_codes
                )

            col1, col2, col3 = st.columns(3)
            col1.metric("PDF Pages", total_pages)
            col2.metric("Matched & Sorted", matched_count)
            col3.metric("Skipped", len(skipped_pages) + len(not_in_pdf))

            if skipped_pages:
                st.warning(f"⚠️ {len(skipped_pages)} page(s) had no employee code detected — pages: {skipped_pages}")
            if not_in_pdf:
                st.warning(f"⚠️ {len(not_in_pdf)} code(s) from Excel had no matching letter in PDF: {not_in_pdf}")

            base_name = os.path.splitext(pdf_file.name)[0]
            output_name = f"Sorted-{base_name}.pdf"

            st.download_button(
                label="⬇️ Download Sorted PDF",
                data=output_buffer,
                file_name=output_name,
                mime="application/pdf"
            )
