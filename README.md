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
4. ExecutionPlace your unorganized academic documents in the project directory and execute the orchestrator:Bashpython organizador.py
