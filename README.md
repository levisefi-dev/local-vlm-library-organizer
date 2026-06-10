# Local VLM Academic Library Organizer

A production-grade, 100% offline, privacy-first pipeline designed to automatically parse, index, categorize, and organize highly specialized academic literature (PDFs and EPUBs). By leveraging a layered architecture that transitions from deterministic API lookups to local Small Language Models (SLMs) and Vision-Language Models (VLMs), this system eliminates cloud dependencies, rate-limiting constraints, and data leakage risks.

---

## Technical Architecture & Inference Pipeline

The core philosophy of this system is **resource optimization via hierarchical fallbacks**. High-compute visual inference is treated as a final resort, ensuring maximum execution speed and minimum VRAM usage across large batches of documents.

```text
[ Raw Document (PDF/EPUB) ]
           │
           ▼
┌────────────────────────────────────────┐
│  Phase 1: Deterministic Parsing        │ ──► Success ──► [ Rename & Categorize ]
│  (Regex ISBN/arXiv ID -> API Lookup)   │
└────────────────────────────────────────┘
           │
           ▼ Failure
┌────────────────────────────────────────┐
│  Phase 2: Local SLM Text Inference     │ ──► Success ──► [ Rename & Categorize ]
│  (Gemma via Ollama over text stream)   │
└────────────────────────────────────────┘
           │
           ▼ Failure
┌────────────────────────────────────────┐
│  Phase 3: Local VLM Spatial Inference  │ ──► Success ──► [ Rename & Categorize ]
│  (LLaVA via Ollama over Cover Pixels)  │
└────────────────────────────────────────┘
           │
           ▼ Failure
┌────────────────────────────────────────┐
│  Phase 4: Graceful Degradation         │ ──► Standardized Manual Review Directory
│  (Failsafe Preservation)               │
└────────────────────────────────────────┘
```

##1. Phase 1 & 1.5: Deterministic Extraction (Metadata Sourcing)
Regex Engine: Scans the raw text extraction layer (PyMuPDF for PDFs, BeautifulSoup & ebooklib for EPUBs) utilizing regular expressions to capture standard formatting for international identifiers (ISBN-10, ISBN-13) and pre-print handles (arXiv ID).

Upstream Resolution: If an identifier is found, the system queries the OpenLibrary or arXiv public web APIs. This provides an instant, zero-compute, mathematically exact match for authors, titles, and standard scientific classifications.

##2. Phase 2: Local SLM Inference (Textual Context Semantics)
Context Stream Extraction: If public records are unavailable, the script streams the first 4,000 characters of the document text into an isolated context buffer.

SLM Execution: A local instance of Gemma via the Ollama API processes the context slice with a zero-shot prompt engineered to output strict JSON schemas specifying title, author, and broad academic taxonomies.

##3. Phase 3: Local VLM Vision Processing (Pixel-Level OCR)
Rasterization Engine: For legacy files, scanned papers, or heavily stylized books where structural text layers are unreadable, the script extracts the first two pages and rasterizes them into standard PNG bytes via fitz.Matrix(2.5, 2.5) scaling.

VLM Visual Inference: The rasterized matrix is base64-encoded and transmitted directly to a local deployment of LLaVA (Vision-Language Model). The model runs deep spatial analysis and optical character recognition (OCR) over the structural elements of the cover page to resolve titles, primary contributors, and thematic domains.

##4. Phase 4: Graceful Degradation & Failsafe Guard
To prevent destructive updates or silent failures, any document failing all three classification layers defaults to a standardized fallback state (Manual Review), preserving the original file integrity and its original operating system name string.

Core Systems Design Features
Memory-Cached Categorization Engine
To mitigate the problem of thematic folder explosion (e.g., an LLM generating separate physical directories for "Mathematics", "Math", and "Maths"), the pipeline implements a lightweight data ledger (memoria_categorias.json).

Every suggested category is checked against known categories using Gestalt Pattern Matching via difflib.get_close_matches with a strict similarity index threshold (cutoff = 0.8).

Lexically close categories are automatically compressed into existing directory names. New archetypes are learned dynamically and appended to the local knowledge base.

Operational Visibility & Observability
Real-time Logging: The architecture utilizes continuous standard output streaming, displaying explicit step indicators ([Phase 1], [Phase 2], [Phase 3]).

Deterministic Verification Tagging: Immediately prior to physical file manipulation, the system outputs an explicit verification tag ([ETIQUETA FINAL] -> Title - Author.pdf), enabling safe standard-error monitoring and deterministic behavior debugging.

Systems Engineering Polish
Context Lock Prevention: Rather than leaving file system handles hanging open during slow local LLM inference windows, the system utilizes Python context managers (with fitz.open(...) as doc:). This guarantees that OS file streams are cleanly flushed and closed, preventing read/write concurrency blocks on host filesystems.

Resource Safety & Rate-Limiting Overrides: Built-in sleep steps protect the local execution loops from thrashing the host system's GPU/VRAM scheduling queue during heavy batch routines.

Repository & Project Structure
Organizar.py: The core orchestrator managing the multi-tier extraction pipeline, file system transformations, and inference execution loops.

memoria_categorias.json: Local JSON tracking array storing previously discovered categorization archetypes to prevent folder fragmentation (Ignored via .gitignore in production).

.gitignore: Configured to shield private corporate or academic literature (*.pdf, *.epub) and dynamic data frames from leaking into public commits.

##Requirements & Local Deployment
#1. Prerequisites
Ensure you have Python 3.10+ and a functional local deployment of Ollama running on your host machine.

#2. Dependencies
Install the required system libraries:

pip install pymupdf ebooklib beautifulsoup4 requests
#3. Model Dependencies
Pull the necessary language and vision model tags to your local machine:

ollama pull gemma
ollama pull llava
#4. Execution
Place your unorganized academic documents in the project directory and execute the organizator:

python Organizar.py
