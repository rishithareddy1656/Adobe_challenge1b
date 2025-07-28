# app/main.py
import os
import json
import re
import datetime
from document_parser import DocumentParser


class PersonaAnalyzer:
    """
    Analyzes the persona and job-to-be-done to extract relevant keywords
    or generate embeddings for relevance scoring.
    """
    def __init__(self, persona_definition: dict, job_to_be_done: str):
        self.persona_definition = persona_definition
        self.job_to_be_done = job_to_be_done
        self.query_text = f"{persona_definition.get('role', '')} {persona_definition.get('description', '')} {job_to_be_done}"
        self.query_keywords = self._extract_keywords(self.query_text)

    def _extract_keywords(self, text: str) -> list[str]:
        """
        Simple keyword extraction. For better results, consider:
        - Lowercasing and removing punctuation.
        - Removing common stopwords (e.g., 'a', 'the', 'is').
        - Stemming or lemmatization if using a more advanced NLP setup.
        """
        keywords = re.findall(r'\b\w+\b', text.lower())
        stopwords = set(["a", "an", "the", "and", "or", "is", "in", "of", "to", "for", "with", "on", "from", "as", "by", "that", "this", "what", "how"])
        return [word for word in keywords if word not in stopwords and len(word) > 2]


class RelevanceScorer:
    """
    Scores and ranks document sections based on their relevance to the persona's needs.
    """
    def __init__(self, persona_analyzer: PersonaAnalyzer):
        self.persona_analyzer = persona_analyzer

    def calculate_relevance(self, section_text: str) -> float:
        """
        Calculates a relevance score for a given section using simple keyword matching.
        """
        score = 0.0
        section_lower = section_text.lower()
        
        for keyword in self.persona_analyzer.query_keywords:
            score += section_lower.count(keyword)

        return score

    def rank_sections(self, sections: list[dict]) -> list[dict]:
        """
        Calculates and assigns a relevance score to each section, then ranks them globally.
        """
        sections_with_scores = []
        for section in sections:
            score = self.calculate_relevance(section["text_content"])
            sections_with_scores.append({**section, "score": score})

        # Sort by score in descending order
        ranked_sections = sorted(sections_with_scores, key=lambda x: x["score"], reverse=True)

        # Assign importance rank (1-indexed)
        for i, section in enumerate(ranked_sections):
            section["importance_rank"] = i + 1
            # Remove the temporary 'score' key if not needed in final output
            del section["score"] 
        return ranked_sections


class SubSectionAnalyzer:
    """
    Extracts refined text (sub-sections) from highly relevant sections.
    """
    def __init__(self, persona_analyzer: PersonaAnalyzer):
        self.persona_analyzer = persona_analyzer

    def analyze(self, section: dict) -> dict:
        """
        Analyzes a section to extract more granular, refined text based on query keywords.
        """
        section_text = section["text_content"]
        refined_snippets = []
        
        sentences = re.split(r'(?<=[.!?])\s+', section_text) 
        
        for sentence in sentences:
            if any(keyword in sentence.lower() for keyword in self.persona_analyzer.query_keywords):
                refined_snippets.append(sentence.strip())
        
        # Fallback if no specific snippets are found
        refined_text = "\n".join(refined_snippets) if refined_snippets else section_text[:500] + "..." if len(section_text) > 500 else section_text

        return {
            "document": section["document_filename"],
            "page_number": section["page_number"],
            "section_title": section["section_title"], # Include section title for context in sub-section output
            "refined_text": refined_text
        }


def run_solution():
    """
    Main function to run the document intelligence solution.
    It processes all PDFs in the input directory and generates a single JSON output file
    with sections globally ranked and sub-sections extracted from the overall most relevant.
    """
    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.join(current_script_dir, os.pardir)

    INPUT_DIR = os.path.join(PROJECT_ROOT, "input")
    OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    persona_data = {
        "role": "Travel Planner",
        "description": "",
    }
    job_to_be_done = "Plan a trip of 4 days for a group of 10 college friends."


    # --- Configuration for limiting output ---
    MAX_EXTRACTED_SECTIONS_TO_KEEP = 10 # Adjust this number to your desired limit
    MAX_SUB_SECTION_ANALYSIS_TO_KEEP = 5 # Adjust this number for the number of detailed sub-sections
    # --- End Configuration ---


    document_parser = DocumentParser()
    persona_analyzer = PersonaAnalyzer(persona_data, job_to_be_done)
    relevance_scorer = RelevanceScorer(persona_analyzer)
    subsection_analyzer = SubSectionAnalyzer(persona_analyzer)

    input_pdf_files = [f for f in os.listdir(INPUT_DIR) if f.endswith(".pdf")]

    if not input_pdf_files:
        print(f"No PDF files found in {INPUT_DIR}. Please place your PDF documents there.")
        return

    print(f"Starting processing for {len(input_pdf_files)} PDF(s) in {INPUT_DIR}...")

    all_raw_extracted_sections = [] 
    all_input_document_names = []

    # --- Phase 1: Parse all documents and collect all sections ---
    for filename in input_pdf_files:
        pdf_path = os.path.join(INPUT_DIR, filename)
        all_input_document_names.append(filename)

        print(f"\nParsing document: {filename}")
        structured_sections_from_pdf = document_parser.extract_structured_sections(pdf_path)
        
        if not structured_sections_from_pdf:
            print(f"No structured sections extracted from {filename}.")
            continue
        
        all_raw_extracted_sections.extend(structured_sections_from_pdf)

    if not all_raw_extracted_sections:
        print("No sections were extracted from any of the input documents. No output file will be generated.")
        return

    print(f"\nSuccessfully extracted {len(all_raw_extracted_sections)} sections from {len(input_pdf_files)} document(s).")
    print("Beginning global ranking and sub-section analysis...")

    # --- Phase 2: Global Ranking ---
    globally_ranked_sections = relevance_scorer.rank_sections(all_raw_extracted_sections)
    
    # --- Phase 3: Filter Globally Ranked Sections for Output ---
    # Take only the top N sections for the 'extracted_sections' summary
    filtered_output_sections_summary = []
    for i in range(min(MAX_EXTRACTED_SECTIONS_TO_KEEP, len(globally_ranked_sections))):
        section = globally_ranked_sections[i]
        filtered_output_sections_summary.append({
            "document": section["document_filename"],
            "page_number": section["page_number"],
            "section_title": section["section_title"],
            "importance_rank": section["importance_rank"]
        })

    # --- Phase 4: Sub-Section Analysis on Globally Top-Ranked Sections ---
    extracted_sub_sections = []
    # Take the top N sections (potentially a different N than MAX_EXTRACTED_SECTIONS_TO_KEEP)
    # for detailed sub-section analysis.
    num_global_top_sections_for_sub_analysis = min(MAX_SUB_SECTION_ANALYSIS_TO_KEEP, len(globally_ranked_sections)) 
    
    for i in range(num_global_top_sections_for_sub_analysis):
        section_to_analyze = globally_ranked_sections[i]
        sub_analysis_result = subsection_analyzer.analyze(section_to_analyze)
        extracted_sub_sections.append(sub_analysis_result)

    # --- Phase 5: Prepare and Save Single Output JSON ---
    single_output_json_filename = "consolidated_global_analysis_summary.json" # Renamed to reflect summary nature
    single_output_json_path = os.path.join(OUTPUT_DIR, single_output_json_filename)

    output_data = {
        "metadata": {
            "input_documents": all_input_document_names,
            "persona": persona_data,
            "job_to_be_done": job_to_be_done,
            "processing_timestamp": datetime.datetime.now().isoformat()
        },
        "extracted_sections": filtered_output_sections_summary, # Now filtered to MAX_EXTRACTED_SECTIONS_TO_KEEP
        "sub_section_analysis": extracted_sub_sections # Filtered to MAX_SUB_SECTION_ANALYSIS_TO_KEEP
    }
    
    with open(single_output_json_path, "w") as f:
        json.dump(output_data, f, indent=4)
    print(f"\nGenerated consolidated output for all documents at {single_output_json_path}")

    print("\nProcessing complete.")

if __name__ == "__main__":
    run_solution()