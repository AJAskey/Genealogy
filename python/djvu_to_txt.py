import os
import re


def beautify_djvu_text(input_path, output_format='md'):
    """
    Cleans and structures raw text extracted from DjVu layers.
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        raw_text = f.read()

    # 1. Normalize line endings and whitespace
    text = raw_text.replace('\r\n', '\n')

    # 2. Fix broken words (common in DjVu OCR: 'soft- \nware' -> 'software')
    text = re.sub(r'(\w+)-\n\s*(\w+)', r'\1\2', text)

    # 3. Join lines that don't end in punctuation (reconstructing paragraphs)
    # This assumes a new paragraph is marked by a double newline or a period.
    lines = text.split('\n')
    cleaned_paragraphs = []
    current_para = []

    for line in lines:
        line = line.strip()
        if not line:
            if current_para:
                cleaned_paragraphs.append(" ".join(current_para))
                current_para = []
            continue

        current_para.append(line)
        # If line ends in terminal punctuation, treat as end of a thought/block
        if line.endswith(('.', '!', '?', ':')):
            cleaned_paragraphs.append(" ".join(current_para))
            current_para = []

    # 4. Format for readability
    if output_format == 'html':
        formatted_output = "\n\n".join(cleaned_paragraphs)
        # Add a basic header based on filename
        title = os.path.basename(input_path).replace('.txt', '').replace('_', ' ').title()
        formatted_output = f"# {title}\n\n{formatted_output}"
        ext = ".html"
    else:
        # Simple HTML wrapper
        body = "".join([f"<p>{p}</p>" for p in cleaned_paragraphs])
        formatted_output = f"<html><body style='font-family: sans-serif; max-width: 800px; margin: 40px auto; line-height: 1.6;'>{body}</body></html>"
        ext = ".html"

    output_path = input_path.replace('.txt', ext)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(formatted_output)

    return output_path


if __name__ == '__main__':
    # Usage
    beautify_djvu_text(
        r"E:\Users\Andy\PycharmProjects\Genealogy\data\Reclaim_The_Records_-_New_Jersey_Death_Index_-_1980_-_Surnames_L-Q_djvu.txt",
        output_format='html')
