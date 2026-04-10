# 📧 eml2pdf

Converts `.eml` files into PDFs organised by date, preserving all original email formatting — including **tables**, **bold**, *italic*, **inline images**, and **attachments**.

Ideal for legal proceedings, audits, and formal archiving of electronic correspondence.

---

## ✨ Features

- 📅 Output filename prefixed with date for automatic chronological sorting (`YYYY-MM-DD_HHMMSS_subject.pdf`)
- 📊 HTML tables rendered as real tables in the PDF
- **Bold**, *italic*, <u>underline</u> and lists preserved
- 🖼️ Inline images from the email body displayed in the correct position
- 📎 PDF and image attachments embedded in the same output file
- 🌐 Full support for special characters (UTF-8)
- Processes multiple `.eml` files at once

---

## 📋 Requirements

- **Python 3.9 or higher** — [python.org/downloads](https://www.python.org/downloads/)
- Python libraries (installed via `pip`):

| Library | Purpose |
|---|---|
| `reportlab` | PDF generation |
| `pypdf` | PDF manipulation and merging |
| `pillow` | Image processing |
| `beautifulsoup4` | HTML parsing |

---

## 🚀 Installation

### 1. Install Python

Go to [python.org/downloads](https://www.python.org/downloads/) and download the latest version.

> ⚠️ **Windows:** during installation, check the **"Add Python to PATH"** option.

Verify the installation:
```bash
python --version
```

### 2. Download the script

Click **Code → Download ZIP** on this page, extract it, and open the folder. Or, if you have Git installed:

```bash
git clone https://github.com/your-username/eml2pdf.git
cd eml2pdf
```

### 3. Install dependencies

```bash
pip install reportlab pypdf pillow beautifulsoup4
```

---

## 🖥️ How to use

### Step 1 — Organise your files

Place the script `eml_to_pdf.py` and your `.eml` files in the same folder. For example:

```
C:\legal_emails\
├── eml_to_pdf.py
├── contract_email.eml
├── notification_email.eml
└── ...
```

### Step 2 — Open a terminal in that folder

On Windows: in the Explorer address bar, type `cmd` and press Enter.

### Step 3 — Run

```bash
python eml_to_pdf.py --input . --output ./generated_pdfs
```

The PDFs will be created in the `generated_pdfs/` subfolder.

---

## ⚙️ Options

| Argument | Description | Default |
|---|---|---|
| `--input` or `-i` | Folder containing the `.eml` files | current directory (`.`) |
| `--output` or `-o` | Folder where PDFs will be saved | `./generated_pdfs` |

**Examples:**

```bash
# Specific input and output folders
python eml_to_pdf.py --input C:\emails --output C:\pdfs

# Short form
python eml_to_pdf.py -i ./emails -o ./output
```

---

## 📂 Generated PDF structure

Each PDF contains:

1. **Header** with From, To, CC, Date and Subject
2. **Email body** with preserved formatting (tables, bold, images, etc.)
3. **Attachment pages** — each PDF or image attachment is embedded after a separator page

---

## 🗂️ File naming

PDFs are named with the email's date and time at the beginning:

```
2024-01-15_093000_Service_Contract.pdf
2024-02-07_141500_Legal_Notice.pdf
2024-02-23_164500_Pending_Items_Reply.pdf
```

This allows files to be **automatically sorted by date** in any file explorer.

---

## 🔧 Troubleshooting

**`pip` is not recognised on Windows**
> Close and reopen the terminal after installing Python. If the problem persists, reinstall Python and check "Add Python to PATH".

**`ModuleNotFoundError`**
> A library was not installed. Run again:
> ```bash
> pip install reportlab pypdf pillow beautifulsoup4
> ```

**No `.eml` files found**
> Confirm that the `.eml` files are in the folder specified with `--input` and that the extension is exactly `.eml` (not `.EML` or `.txt`).

**Strange characters in the PDF**
> The script automatically tries to use the DejaVu font on Linux/Mac for better Unicode support. On Windows it falls back to Helvetica — special characters are still supported.

---

## 📄 License

MIT License — feel free to use, modify and distribute.

---

## 🤝 Contributing

Pull requests are welcome! If you find a bug or have a suggestion, open an [issue](../../issues).
