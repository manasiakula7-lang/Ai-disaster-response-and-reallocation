import pdfplumber
from pathlib import Path

PDF_FILE = Path("data/raw/population/259.pdf")

search_terms = [
    "District-wise Mid-Year Population",
    "Mid-Year Population",
    "Mid Year Population"
]

print("Searching population report...\n")

with pdfplumber.open(PDF_FILE) as pdf:

    print("Total PDF pages:", len(pdf.pages))

    found = False

    for page_number, page in enumerate(pdf.pages, start=1):

        text = page.extract_text() or ""

        if any(term.lower() in text.lower() for term in search_terms):

            print(f"\nPossible table found on PDF page {page_number}")
            print("-" * 60)

            print(text[:5000])

            found = True

    if not found:
        print("Population table heading was not found automatically.")