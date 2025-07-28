# Adobe India Hackathon - Round 1B: Persona-Driven Document Intelligence

## Solution Overview

This solution addresses the "Persona-Driven Document Intelligence" challenge by building a system that extracts and prioritizes relevant sections from PDF documents based on a given persona and job-to-be-done.

The system follows a modular pipeline:

1.  **Document Ingestion & Parsing:** Leverages a custom PDF parsing module (derived from Round 1A) to extract raw text content along with a structured outline (Title, H1, H2, H3) and per-page text spans. This provides the foundational data for analysis.
2.  **Persona & Job-to-be-Done Analysis:** Processes the persona description and the specific task to derive key terms or concepts relevant to the user's intent.
3.  **Section Relevance Scoring & Ranking:** Each extracted section from the documents is evaluated for its relevance to the persona's needs and the job task. This is currently implemented using a keyword-matching approach for simplicity and to adhere to constraints, but can be extended with more advanced techniques (e.g., TF-IDF). Sections are then ranked by their relevance.
4.  **Sub-Section Analysis (Refinement):** For the most relevant sections, the system performs a more granular analysis, extracting "refined text" which typically includes key sentences or snippets directly addressing the persona's task.
5.  **Output Generation:** The processed and ranked information is formatted into a JSON file, conforming to the specified output structure.

## Models or Libraries Used

* **PyMuPDF (`pymupdf`):** Used for robust PDF parsing and text extraction. It's efficient and allows for detailed access to text block metadata (font size, position, bold status).
* **Python's `re` module:** For regular expression-based text processing and pattern matching (e.g., identifying numbered headings, filtering out footers).
* **Python's `json` module:** For handling JSON input/output.
* **Python's `datetime` module:** For generating timestamps in the output.

**Note:** No external machine learning models (e.g., large language models for embeddings) are used to comply with the `<1GB model size` and `no internet access` constraints. The relevance scoring relies on keyword-based heuristics.

## How to Build and Run Your Solution

This solution is designed to run within a Docker container, adhering to the specified execution environment.

### Prerequisites

* Docker installed on your system.

### Build the Docker Image

Navigate to the `your_project_root` directory (where `Dockerfile` is located) in your terminal and run the following command:

```bash
docker build --platform linux/amd64 -t mysolutionname:somerandomidentifier .