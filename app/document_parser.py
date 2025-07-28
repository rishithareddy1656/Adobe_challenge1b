# app/document_parser.py
import fitz  # PyMuPDF
import json
import os
import re
from collections import Counter

class DocumentParser:
    def __init__(self):
        pass

    def extract_text_with_metadata(self, pdf_path):
        """
        Extracts text blocks with their font size, bold status, and position from a PDF.
        Page numbers are 0-indexed.
        Includes x0, y0, x1, y1 from bbox for more detailed positional analysis.
        """
        document = fitz.open(pdf_path)
        pages_data = []

        for page_num in range(document.page_count):
            page = document.load_page(page_num)
            blocks = page.get_text("dict")["blocks"] 
            
            page_texts = []
            for b in blocks:
                if b["type"] == 0:  # 0 means it's a text block
                    for line in b["lines"]:
                        for span in line["spans"]:
                            text = span["text"].strip()
                            if text: # Only process non-empty text
                                is_bold = bool(span['flags'] & 2) # Check if bold flag (0x02) is set
                                
                                if not is_bold: # Fallback/additional check if font name indicates bold
                                    font_name = span["font"].lower()
                                    if "bold" in font_name or "black" in font_name or "demi" in font_name or "extrab" in font_name:
                                        is_bold = True

                                x0, y0, x1, y1 = span["bbox"]
                                page_texts.append({
                                    "text": text,
                                    "font_size": round(span["size"], 2),
                                    "is_bold": is_bold,
                                    "page": page_num, # 0-indexed page number
                                    "bbox": (x0, y0, x1, y1),
                                    "line_height": y1 - y0,
                                    "x0": x0,
                                    "y0": y0,
                                    "x1": x1, 
                                    "y1": y1  
                                })
            pages_data.append(page_texts)
            # DEBUG PRINT: Check what text spans are extracted per page
            # print(f"DEBUG (metadata): Page {page_num} in {os.path.basename(pdf_path)} has {len(page_texts)} text spans.")
            # if not page_texts:
            #     print(f"DEBUG (metadata): No text extracted for page {page_num}. This page might be blank or image-only.")

        document.close() # Close the document after processing all pages
        # print(f"DEBUG (metadata): Finished extraction for {os.path.basename(pdf_path)}. Total pages processed: {len(pages_data)}")
        return pages_data

    def merge_heading_spans(self, page_data):
        """
        Merges text spans that belong to the same logical line/heading based on spatial proximity
        and font characteristics, allowing for multi-line headings.
        More stringent merging criteria.
        """
        merged_texts = []
        i = 0
        while i < len(page_data):
            current = page_data[i]
            merged_text = current["text"]
            merged_bbox = list(current["bbox"])
            merged_font_size = current["font_size"]
            merged_is_bold = current["is_bold"]
            
            initial_x0 = current["x0"] 

            j = i + 1
            while j < len(page_data):
                next_span = page_data[j]
                
                # Critical check: Don't merge if the current line ends with sentence-ending punctuation
                # unless the next line is a clear continuation (e.g., proper noun or strong context)
                if re.search(r'[.!?]$', merged_text.strip()):
                    break

                # Criteria for merging:
                # 1. Very similar font size (minor rendering diffs allowed)
                is_font_size_match = abs(next_span["font_size"] - merged_font_size) < 0.5 

                # 2. Vertical proximity: next line starts close below current, within a typical line spacing
                vertical_gap = next_span["y0"] - current["y1"]
                is_vertical_proximity = 0 < vertical_gap < (current["line_height"] * 1.5)

                # 3. Horizontal alignment: The next line either starts at a similar x0
                #    or is slightly indented (common for multi-line headings)
                is_horizontal_alignment = abs(next_span["x0"] - initial_x0) < 15 or \
                                          (next_span["x0"] > initial_x0 and (next_span["x0"] - initial_x0) < 50 and merged_is_bold)
                
                # 4. Both current and next are bold, or current is bold and next is similar size and not plain body text.
                is_bold_consistent = (merged_is_bold and next_span["is_bold"]) or \
                                     (merged_is_bold and is_font_size_match and len(next_span["text"].split()) < 25) # Don't merge bold with long non-bold text unless it's a clear continuation

                # 5. Prevent merging if the next span looks like a new paragraph (e.g., clear indent, very short start)
                is_new_paragraph_start = (next_span["x0"] - initial_x0 > 30) and len(next_span["text"].split()) < 4

                if is_vertical_proximity and is_font_size_match and is_horizontal_alignment and is_bold_consistent and not is_new_paragraph_start:
                    merged_text += " " + next_span["text"]
                    merged_bbox[2] = max(merged_bbox[2], next_span["bbox"][2])
                    merged_bbox[3] = max(merged_bbox[3], next_span["bbox"][3])
                    merged_is_bold = merged_is_bold or next_span["is_bold"] # If any part is bold, mark as bold
                    current = next_span # Update 'current' to the last merged span for next iteration's relative position calculation
                    j += 1
                else:
                    break

            merged_texts.append({
                "text": merged_text.strip(),
                "font_size": merged_font_size,
                "is_bold": merged_is_bold,
                "page": current["page"],
                "bbox": tuple(merged_bbox),
                "x0": merged_bbox[0], 
                "y0": merged_bbox[1],
                "x1": merged_bbox[2],
                "y1": merged_bbox[3]
            })
            i = j
        return merged_texts

    def identify_headings(self, pages_data):
        """
        Identifies Title, H1, H2, H3 based on font size, bolding, numbering patterns, and hierarchy.
        Applies strict filtering to exclude subheadings beyond H3, table content, and other non-heading text.
        """
        if not pages_data:
            return "", []

        # Merge spans within each page first
        merged_pages_data = [self.merge_heading_spans(page_data) for page_data in pages_data]

        # DEBUG PRINT: Show merged data sample
        # print(f"\nDEBUG (headings): After merging spans (first few from page 0):")
        # if merged_pages_data and merged_pages_data[0]:
        #     for i, item in enumerate(merged_pages_data[0][:5]): # Print first 5 merged items from the first page
        #         print(f"  [{i}] Text: '{item['text'][:100]}...', Size: {item['font_size']}, Bold: {item['is_bold']}")
        # else:
        #     print("  No merged data found for page 0.")


        # Collect all font sizes from merged texts
        all_font_sizes = []
        for page_data in merged_pages_data:
            for text_info in page_data:
                all_font_sizes.append(text_info["font_size"])
        
        if not all_font_sizes:
            return "", []

        # Dynamically determine approximate font size thresholds for Title, H1, H2, H3
        font_size_counts = Counter([round(size, 1) for size in all_font_sizes])
        # Filter out very small sizes and infrequent sizes (likely noise)
        relevant_sizes = sorted([s for s, count in font_size_counts.items() if s >= 10 and count > 1], reverse=True)

        # Assign initial thresholds based on sorted unique sizes
        title_size = relevant_sizes[0] if relevant_sizes else 24 
        h1_size = relevant_sizes[1] if len(relevant_sizes) > 1 else (title_size * 0.9 if title_size else 18)
        h2_size = relevant_sizes[2] if len(relevant_sizes) > 2 else (h1_size * 0.9 if h1_size else 14)
        h3_size = relevant_sizes[3] if len(relevant_sizes) > 3 else (h2_size * 0.9 if h2_size else 12)

        # Enforce minimums and strict hierarchy, adjust dynamically if sizes are too close
        title_size = max(title_size, 20.0) 
        h1_size = max(h1_size, 16.0)
        h2_size = max(h2_size, 13.0) 
        h3_size = max(h3_size, 11.0) 

        # Dynamic adjustments to ensure proper hierarchy spacing
        if title_size <= h1_size + 2.0: title_size = h1_size + 2.5
        if h1_size <= h2_size + 1.0: h1_size = h2_size + 1.5
        if h2_size <= h3_size + 1.0: h2_size = h3_size + 1.5
        
        # Title detection: Look for largest bold text near the top of the first page
        title_text = ""
        if merged_pages_data and merged_pages_data[0]:
            for text_info in merged_pages_data[0]:
                text = text_info["text"].strip()
                size = text_info["font_size"]
                is_bold = text_info["is_bold"]
                y0 = text_info["y0"]
                
                page_width = text_info["x1"] if text_info["x1"] > 0 else 600 
                text_center = (text_info["x0"] + text_info["x1"]) / 2
                page_center = page_width / 2
                is_roughly_centered = abs(text_center - page_center) < 100 
                
                # A stricter condition for main title: very large, bold, and early on the first page
                if y0 < 250 and is_bold and size >= (title_size * 0.9) and is_roughly_centered and len(text.split()) > 5:
                    title_text = text.replace('\\', '').strip()
                    # Clean specific known patterns if they are not part of the core title
                    title_text = re.sub(r'RFP: To Develop the Ontario Digital Library Business Plan March \d{4}', '', title_text, flags=re.IGNORECASE)
                    
                    # More robust check for "Introduction" or similar phrases at the end of the supposed title
                    intro_match = re.search(r'\s*(?:Introduction|Overview|Summary|A Comprehensive Guide|Ultimate Guide|A Culinary Journey|A Historical Journey)(?:.*)', title_text, re.IGNORECASE | re.DOTALL)
                    if intro_match:
                        # If "Introduction" is found, try to strip it and whatever follows
                        title_text = title_text[:intro_match.start()].strip()
                    
                    if len(title_text.split()) < 3: # If after cleaning, title is too short, discard it
                        title_text = ""
                    break 

        # --- Heuristic for identifying potential table content and other non-heading elements ---
        def is_likely_non_heading(text_info, page_data_list, current_text_index, h1_s, h2_s, h3_s):
            text = text_info["text"].strip()
            size = text_info["font_size"]
            is_bold = text_info["is_bold"]
            x0 = text_info["x0"]
            y0 = text_info["y0"]
            
            # 1. Very short lines that are not clearly a numbered/bullet point.
            if len(text) < 4 and not re.match(r"^\d+\.", text): 
                return True

            # 2. Lines that are excessively long for a heading (likely body text)
            if len(text.split()) > 30: 
                return True

            # 3. Text that looks like common page headers/footers (page numbers, running titles)
            if re.match(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", text, re.IGNORECASE) or \
               re.match(r"^\s*\d+\s*$", text) or \
               re.match(r"^\s*[A-Za-z\s]+\s+\|\s+[A-Za-z\s]+\s*$", text) or \
               re.match(r"^\s*-\s*\d+\s*-\s*$", text): # e.g., "- 1 -" page numbers
                return True

            # 4. Content that is part of a list or bullet points (often indented, small font)
            # This needs to be carefully distinguished from valid numbered headings
            if re.match(r"^\s*[-•–—]\s+.", text) or \
               (re.match(r"^\s*\d+\.\s+.*", text) and size < h3_s and not is_bold): # Numbered lists below H3 size, not bold
                return True
            
            # 5. Text that starts with common non-heading prefixes/punctuations indicative of body text
            if text.startswith((':', '—', '–', '-', ';', 'and', 'or', 'the', 'a ', 'an ')) or \
               re.match(r"^\(.+\)$", text): 
                return True
            
            # 6. If the current text is bold but its font size is much smaller than H3
            if is_bold and size < h3_s - 2.0:
                return True

            # 7. Check if the line is clearly a continuation of a previous paragraph, not a new heading
            # This is key for avoiding bolded text within paragraphs being identified.
            if current_text_index > 0:
                prev_text_info = page_data_list[current_text_index - 1]
                prev_text = prev_text_info["text"].strip()
                # If previous line ends with sentence-ending punctuation AND this line is not significantly larger/bolder
                if re.search(r'[.!?]$', prev_text) and not (is_bold and size > prev_text_info["font_size"] + 0.5):
                    # And if current line's indentation is very similar to the previous, and vertical gap is small
                    if abs(x0 - prev_text_info["x0"]) < 10 and abs(text_info["y0"] - prev_text_info["y1"]) < (prev_text_info.get("line_height", 12) * 1.0):
                        return True

            # 8. Content that looks like tabular data (multiple columns of short text or numbers)
            # If a span is not bold and its font size is close to body text, and it's surrounded by other similar spans
            # with similar x-coordinates, it's probably table/list data.
            if not is_bold and size < h3_s + 1.0: 
                column_like_count = 0
                for offset in [-1, 1]: 
                    neighbor_index = current_text_index + offset
                    if 0 <= neighbor_index < len(page_data_list):
                        neighbor = page_data_list[neighbor_index]
                        if abs(neighbor["x0"] - x0) < 15 and abs(neighbor["font_size"] - size) < 1.0 and not neighbor["is_bold"]:
                            column_like_count += 1
                if column_like_count >= 1 and len(text.split()) < 10: 
                    return True

            return False


        raw_detected_headings = [] 
        seen_headings_set = set() 

        for page_num_idx, page_data in enumerate(merged_pages_data):
            for i, text_info in enumerate(page_data):
                text = text_info["text"].strip()
                size = text_info["font_size"]
                is_bold = text_info["is_bold"]
                page = text_info["page"] 
                y0 = text_info["y0"]
                x0 = text_info["x0"]
                
                if not text:
                    continue

                # Skip if it's the title we already extracted (or part of it)
                if title_text and (text == title_text or (len(text) > 10 and text in title_text)):
                    continue
                    
                # Filter out likely non-headings early
                if is_likely_non_heading(text_info, page_data, i, h1_size, h2_size, h3_size):
                    continue
                
                potential_level = None

                # --- Primary Classification: H1, H2, H3 ---
                numbered_heading_match = re.match(r"^(\d+(?:\.\d+)*)\s+(.+)", text) 
                if numbered_heading_match:
                    number_prefix = numbered_heading_match.group(1)
                    heading_text_part = numbered_heading_match.group(2).strip()
                    dot_count = number_prefix.count('.')

                    is_numbered_heading_prominent = is_bold or (size >= h3_size - 1.0 and dot_count <= 2) # Allow non-bold numbered if large enough
                    
                    if is_numbered_heading_prominent:
                        if dot_count == 0: 
                            if abs(size - h1_size) < 1.5: potential_level = "H1"
                            elif abs(size - h2_size) < 1.0 and size > h3_size: potential_level = "H2" 
                        elif dot_count == 1: 
                            if abs(size - h2_size) < 1.5: potential_level = "H2"
                            elif abs(size - h3_size) < 1.0: potential_level = "H3" 
                        elif dot_count >= 2: 
                            if abs(size - h3_size) < 1.5: potential_level = "H3"
                        
                        if potential_level:
                            text = f"{number_prefix} {heading_text_part}" 

                # Non-numbered heading classification based on size and bolding (if not already classified)
                if not potential_level:
                    if is_bold and abs(size - h1_size) < 1.0: 
                        potential_level = "H1"
                    elif is_bold and abs(size - h2_size) < 1.0:
                        potential_level = "H2"
                    elif is_bold and abs(size - h3_size) < 1.0:
                        potential_level = "H3"
                    # Allow slightly smaller if bold, but not too small, and ensure decreasing size
                    elif is_bold and size >= h1_size - 1.5 and size > h2_size + 0.5:
                        potential_level = "H1"
                    elif is_bold and size >= h2_size - 1.5 and size > h3_size + 0.5:
                        potential_level = "H2"
                    elif is_bold and size >= h3_size - 1.5:
                        potential_level = "H3"

                if potential_level:
                    item_tuple = (text, page, potential_level)
                    if item_tuple not in seen_headings_set:
                        raw_detected_headings.append({
                            "level": potential_level, 
                            "text": text, 
                            "page": page,
                            "y0": y0, 
                            "x0": x0 
                        })
                        seen_headings_set.add(item_tuple)
                        
        # Sort all detected headings by page, then by vertical position (y0), then horizontal (x0)
        raw_detected_headings.sort(key=lambda x: (x["page"], x["y0"], x["x0"]))

        # Final pass to enforce hierarchy and remove strict duplicates
        final_structured_outline = []
        
        last_h1 = {"page": -1, "y0": -1} 
        last_h2 = {"page": -1, "y0": -1}
        last_h3 = {"page": -1, "y0": -1} 

        for h in raw_detected_headings:
            level = h["level"]
            text = h["text"]
            page = h["page"]
            y0 = h["y0"]

            entry = {"level": level, "text": text, "page": page}

            # Basic immediate duplicate check (same text on same page, same level)
            if final_structured_outline and \
               final_structured_outline[-1]["text"] == text and \
               final_structured_outline[-1]["page"] == page and \
               final_structured_outline[-1]["level"] == level:
                continue

            add_current = False

            if level == "H1":
                if page > last_h1["page"] or (page == last_h1["page"] and y0 > last_h1["y0"]):
                    add_current = True
                    last_h1 = h
                    last_h2 = {"page": -1, "y0": -1} 
                    last_h3 = {"page": -1, "y0": -1}
            elif level == "H2":
                if (last_h1["page"] != -1 and (page > last_h1["page"] or (page == last_h1["page"] and y0 > last_h1["y0"]))) and \
                   (page > last_h2["page"] or (page == last_h2["page"] and y0 > last_h2["y0"])):
                    add_current = True
                    last_h2 = h
                    last_h3 = {"page": -1, "y0": -1}
                elif not final_structured_outline and (page > last_h2["page"] or (page == last_h2["page"] and y0 > last_h2["y0"])): # Promote first H2 if no H1 exists yet
                    entry["level"] = "H1"
                    add_current = True
                    last_h1 = h
            elif level == "H3":
                if (last_h2["page"] != -1 and (page > last_h2["page"] or (page == last_h2["page"] and y0 > last_h2["y0"]))) and \
                   (page > last_h3["page"] or (page == last_h3["page"] and y0 > last_h3["y0"])):
                    add_current = True
                    last_h3 = h
                elif (last_h1["page"] != -1 and last_h2["page"] == -1 and (page > last_h1["page"] or (page == last_h1["page"] and y0 > last_h1["y0"]))) and \
                     (page > last_h3["page"] or (page == last_h3["page"] and y0 > last_h3["y0"])): 
                    entry["level"] = "H2"
                    add_current = True
                    last_h2 = h
                    last_h3 = {"page": -1, "y0": -1} 
                elif not final_structured_outline and (page > last_h3["page"] or (page == last_h3["page"] and y0 > last_h3["y0"])): 
                    entry["level"] = "H1"
                    add_current = True
                    last_h1 = h
            
            if add_current:
                final_structured_outline.append(entry)
        
        deduplicated_outline = []
        seen_final_entries = set()
        for item in final_structured_outline:
            item_tuple = (item["text"], item["page"], item["level"])
            if item_tuple not in seen_final_entries:
                deduplicated_outline.append(item)
                seen_final_entries.add(item_tuple)
                
        # print(f"\nDEBUG (headings): Identified Title: '{title_text.strip()}'")
        # print(f"DEBUG (headings): Identified Outline ({len(deduplicated_outline)} headings found):")
        # for i, h in enumerate(deduplicated_outline[:15]): 
        #     print(f"  [{i}] Level: {h['level']}, Text: '{h['text'][:100]}...', Page: {h['page']+1}")
        # if not deduplicated_outline and not title_text:
        #     print("DEBUG (headings): NO TITLE OR OUTLINE IDENTIFIED! Heading detection rules might be too strict or content is unsuitable.")

        return title_text.strip(), deduplicated_outline

    def extract_structured_sections(self, pdf_path):
        """
        Main function to extract structured sections with their text content
        from a PDF, intended for use by PersonaAnalyzer.
        """
        try:
            pages_data = self.extract_text_with_metadata(pdf_path)
            title, outline = self.identify_headings(pages_data)

            structured_sections = []
            
            doc = fitz.open(pdf_path)

            section_markers = []
            if title:
                title_info_found = False
                for page_spans in pages_data:
                    for span in page_spans:
                        # Match the title text (can be partial match for long titles)
                        if span["text"].strip() == title or \
                           (len(title) > 20 and title in span["text"].strip() and span["is_bold"] and span["font_size"] >= 18): 
                            section_markers.append({
                                "text": title,
                                "page": span["page"],
                                "y0": span["y0"],
                                "level": "H0" 
                            })
                            title_info_found = True
                            break
                    if title_info_found:
                        break
                if not title_info_found: 
                     section_markers.append({
                        "text": title, "page": 0, "y0": 0, "level": "H0"
                     })


            for item in outline:
                found_y0 = None
                for p_data in pages_data: 
                    for span_info in p_data:
                        # Match the exact heading text and page, and also ensure it's bold or large enough
                        if span_info["page"] == item["page"] and \
                           span_info["text"].strip() == item["text"].strip() and \
                           (span_info["is_bold"] or span_info["font_size"] >= 12): 
                            found_y0 = span_info["y0"]
                            break
                    if found_y0 is not None:
                        break 
                
                if found_y0 is not None:
                     section_markers.append({
                        "text": item["text"],
                        "page": item["page"],
                        "y0": found_y0,
                        "level": item["level"]
                     })
                else: 
                    # print(f"DEBUG (section_extraction): Warning: Could not find precise y0 for heading '{item['text']}' on page {item['page']+1}. Using y0=0.")
                    section_markers.append({
                        "text": item["text"],
                        "page": item["page"],
                        "y0": 0, 
                        "level": item["level"]
                     })

            section_markers.sort(key=lambda x: (x["page"], x["y0"]))

            deduplicated_section_markers = []
            seen_texts = set()
            for marker in section_markers:
                if marker["text"] not in seen_texts:
                    deduplicated_section_markers.append(marker)
                    seen_texts.add(marker["text"])
            section_markers = deduplicated_section_markers
            
            # --- Extract content for each section ---
            for i, current_marker in enumerate(section_markers):
                start_page = current_marker["page"]
                start_y = current_marker["y0"]
                
                # Corrected line: Use doc.load_page() to get the page object
                current_page_obj = doc.load_page(start_page) 
                end_page_for_content = doc.page_count - 1
                end_y_for_content = float('inf') 
                
                if i + 1 < len(section_markers):
                    next_marker = section_markers[i+1]
                    if next_marker["page"] == start_page:
                        end_page_for_content = start_page
                        end_y_for_content = next_marker["y0"]
                    else:
                        end_page_for_content = start_page 
                        # Corrected line: Use current_page_obj.rect.y1
                        end_y_for_content = current_page_obj.rect.y1 # End of the current page

                section_text_content = []
                # print(f"DEBUG (section_extraction): Processing section: '{current_marker['text']}' (Page: {start_page+1}, Y-start: {start_y})")
                
                for page_num_iter in range(start_page, end_page_for_content + 1):
                    if page_num_iter >= len(pages_data): 
                        continue

                    page_texts_on_this_page = pages_data[page_num_iter]
                    
                    for text_info in page_texts_on_this_page:
                        is_after_start = text_info["y0"] >= start_y
                        is_before_end = (page_num_iter < end_page_for_content) or \
                                        (page_num_iter == end_page_for_content and text_info["y0"] < end_y_for_content)
                        
                        is_not_heading_text = text_info["text"].strip() != current_marker["text"].strip()
                        # Also check if it's one of the *other* identified headings
                        if is_not_heading_text:
                            for h_marker in outline: # Check against all outline headings
                                if text_info["text"].strip() == h_marker["text"].strip():
                                    is_not_heading_text = False
                                    break
                            
                        is_not_footer_header = not (re.match(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", text_info["text"], re.IGNORECASE) or 
                                                    re.match(r"^\s*\d+\s*$", text_info["text"].strip()) or
                                                    re.match(r"^\s*[A-Za-z\s]+\s+\|\s+[A-Za-z\s]+\s*$", text_info["text"]) or
                                                    re.match(r"^\s*-\s*\d+\s*-\s*$", text_info["text"])) 

                        is_not_fragment = len(text_info["text"].strip().split()) > 1 or len(text_info["text"].strip()) > 5

                        if is_after_start and is_before_end and is_not_heading_text and is_not_footer_header and is_not_fragment:
                            section_text_content.append(text_info["text"].strip())
                            # print(f"  DEBUG (content_added): Added: '{text_info['text'][:50]}...' (Page: {text_info['page']+1}, Y: {text_info['y0']})")
                        # else:
                        #     print(f"  DEBUG (content_filtered): Filtered: '{text_info['text'][:50]}...' (AfterStart: {is_after_start}, BeforeEnd: {is_before_end}, NotHeading: {is_not_heading_text}, NotFooter: {is_not_footer_header}, NotFrag: {is_not_fragment})")
                
                full_section_content_string = "\n".join(section_text_content).strip()

                if current_marker["level"] == "H0" or len(full_section_content_string.split()) >= 10: 
                    structured_sections.append({
                        "document_filename": os.path.basename(pdf_path),
                        "section_title": current_marker["text"],
                        "page_number": current_marker["page"] + 1, 
                        "text_content": full_section_content_string,
                        "level": current_marker["level"]
                    })
                # else:
                    # print(f"DEBUG (section_skipped): Skipping section '{current_marker['text']}' due to insufficient content length ({len(full_section_content_string.split())} words).")

            doc.close() 
            # print(f"\nDEBUG (sections): Final structured sections count for {os.path.basename(pdf_path)}: {len(structured_sections)}")
            # if not structured_sections:
            #     print(f"DEBUG (sections): No structured sections were ultimately created. Check if filter conditions are too restrictive.")
            return structured_sections

        except fitz.FileNotFoundError:
            print(f"Error: PDF file not found at {pdf_path}")
            return []
        except Exception as e:
            print(f"An error occurred while processing {pdf_path}: {e}")
            raise