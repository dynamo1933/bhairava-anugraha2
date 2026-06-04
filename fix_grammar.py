#!/usr/bin/env python3
"""
Grammar correction pass for Bhairava Anugraha Q&A CSV files.
Fixes both the `question` and `answer` columns.
"""

import csv
import re
import sys

def clean_punctuation_spacing(text):
    if not text:
        return text
    # Remove space before punctuation: "word , word" -> "word, word"
    text = re.sub(r'\s+([,\.!\?\:;])', r'\1', text)
    # Ensure space after punctuation: "word,word" -> "word, word" (except in decimals, URLs or specific patterns)
    text = re.sub(r'([,\.!\?\:;])([a-zA-Z])', r'\1 \2', text)
    # Remove double spaces
    text = re.sub(r'  +', ' ', text)
    return text

def capitalize_sentences(text):
    if not text:
        return text
    
    # Capitalize the very start of the text
    def cap_match(m):
        return m.group(1) + m.group(2).upper()
        
    text = re.sub(r'(^|[\.!\?]\s+)([a-z])', cap_match, text)
    return text

def fix_text(text):
    if not text:
        return text

    t = text

    # --- Specific Row/Phrase Corrections (Targeting the questions and answers) ---
    
    # Row 292 (Kirito Kun - Swami, If we perform...)
    t = re.sub(
        r'Swami,\s*If we perform mandala sadhna immediately after nitya puja do we need to offer a different diya, bhog and dhoop or the same would suffice and just re offer them mentally\. Or should another set be kept ready',
        'Swami, if we perform Mandala Sadhana immediately after Nitya Puja, do we need to offer a different diya, bhog, and dhoop, or would the same suffice and we just re-offer them mentally? Or should another set be kept ready?',
        t, flags=re.IGNORECASE
    )
    t = re.sub(
        r'Swami,\s*If we perform mandala sadhana immediately after nitya puja do we need to offer a different diya, bhog and dhoop or the same would suffice and just re-offer them mentally\. Or should another set be kept ready',
        'Swami, if we perform Mandala Sadhana immediately after Nitya Puja, do we need to offer a different diya, bhog, and dhoop, or would the same suffice and we just re-offer them mentally? Or should another set be kept ready?',
        t, flags=re.IGNORECASE
    )
    
    # Answer for Row 292 run-on fix
    t = re.sub(
        r'then in most cases the same diya, dhoop and bhog can continue you may simply re-offer them',
        'then in most cases the same diya, dhoop, and bhog can continue; you may simply re-offer them',
        t
    )
    t = re.sub(
        r'Bhairava looks more into your awareness and sincerity than external repetition alone',
        'Bhairava looks more at your awareness and sincerity than at external repetition alone',
        t
    )

    # Row 275 (pran prashtitapna)
    t = re.sub(r'pran prashtitapna', 'prana pratistha', t, flags=re.IGNORECASE)
    t = re.sub(r'pran pratishtapna', 'prana pratistha', t, flags=re.IGNORECASE)

    # Row 276 (Matsyendranath, Dattatreya, etc.)
    t = re.sub(
        r'Maya matesendranath\.\.\s*Dattatreya swami\.\.\s*Bhairva and shiva\.\.\s*All are one\s*/\s*same tatva',
        'Matsyendranath, Dattatreya Swami, Bhairava, and Shiva — are they all one and the same tatva?',
        t, flags=re.IGNORECASE
    )

    # Row 279 (n started doing, malaas)
    t = re.sub(r'\bn started doing\b', 'and started doing', t)
    t = re.sub(r'\bmalaas\b', 'malas', t, flags=re.IGNORECASE)

    # Row 281 (nyas and viniyog)
    t = re.sub(r'\bnyas and viniyog\b', 'nyasa and viniyoga', t, flags=re.IGNORECASE)

    # Row 286 (why does it happens, fades aw)
    t = re.sub(r'why does it happens', 'why does it happen', t, flags=re.IGNORECASE)
    t = re.sub(r'fades aw\b', 'fades away', t, flags=re.IGNORECASE)

    # Row 247 (Is Hanuman ji a form of Bhairav...)
    t = re.sub(
        r'Is Hanuman ji a form of Bhairav or are they related tantrically\s+Please elaborate',
        'Is Hanuman ji a form of Bhairava, or are they related tantrically? Please elaborate.',
        t, flags=re.IGNORECASE
    )

    # Row 255 (anger resurfacing. how do we get over the)
    t = re.sub(
        r'anger resurfacing\.\s+how do we get over the$',
        'anger resurfacing? How do we get over them?',
        t, flags=re.IGNORECASE
    )

    # Transliteration & spelling standardizations
    t = re.sub(r'\bsadhna\b', 'sadhana', t, flags=re.IGNORECASE)
    t = re.sub(r'\bsadhana\b', 'sadhana', t, flags=re.IGNORECASE)
    t = re.sub(r'\bSadhna\b', 'Sadhana', t)
    t = re.sub(r'\bsadahana\b', 'sadhana', t, flags=re.IGNORECASE)
    t = re.sub(r'\bSadahna\b', 'Sadhana', t)
    t = re.sub(r'\bSadahana\b', 'Sadhana', t)
    
    t = re.sub(r'\bdeeksha\b', 'diksha', t, flags=re.IGNORECASE)
    t = re.sub(r'\bdīkṣā\b', 'diksha', t, flags=re.IGNORECASE)
    t = re.sub(r'\bDeeksha\b', 'Diksha', t)
    
    t = re.sub(r'\bjaap\b', 'japa', t, flags=re.IGNORECASE)
    t = re.sub(r'\bmansik jaap\b', 'manasik japa', t, flags=re.IGNORECASE)
    t = re.sub(r'\bmansik japa\b', 'manasik japa', t, flags=re.IGNORECASE)
    t = re.sub(r'\bmanasik jaap\b', 'manasik japa', t, flags=re.IGNORECASE)
    
    t = re.sub(r'\bpaddati\b', 'paddhati', t, flags=re.IGNORECASE)
    t = re.sub(r'\bpaddathi\b', 'paddhati', t, flags=re.IGNORECASE)
    t = re.sub(r'\bpadhadhi\b', 'paddhati', t, flags=re.IGNORECASE)
    
    t = re.sub(r'\bBhaiarva\b', 'Bhairava', t)
    t = re.sub(r'\bBhaiarava\b', 'Bhairava', t)
    t = re.sub(r'\bBhairav\b', 'Bhairava', t) # standardize to Bhairava (Sanskrit/polite) or keep as user used? Let's check, site uses Bhairava mostly. Let's make sure it's correct.
    t = re.sub(r'\bJaiBhairava\b', 'Jai Bhairava', t)
    t = re.sub(r'Jai Bhaiarava', 'Jai Bhairava', t)
    
    t = re.sub(r"Bhairava' s", "Bhairava's", t)
    t = re.sub(r"Guru' s", "Guru's", t)
    
    t = re.sub(r'\bthinking about office\b', 'thinking about the office', t)
    t = re.sub(r'\bcan there be gap\b', 'can there be a gap', t, flags=re.IGNORECASE)
    t = re.sub(r'\bthere is gap\b', 'there is a gap', t, flags=re.IGNORECASE)
    t = re.sub(r'\bafter couple of\b', 'after a couple of', t, flags=re.IGNORECASE)
    t = re.sub(r'\bwithout gap\b', 'without a gap', t, flags=re.IGNORECASE)
    t = re.sub(r'\bin two sitting\b', 'in two sittings', t, flags=re.IGNORECASE)
    t = re.sub(r'\bfor lifetime\b', 'for a lifetime', t, flags=re.IGNORECASE)
    t = re.sub(r'\bthere is chance\b', 'there is a chance', t, flags=re.IGNORECASE)
    t = re.sub(r'\bdo basic homa\b', 'do a basic homa', t, flags=re.IGNORECASE)
    t = re.sub(r'\bI know how to basic homa vedic way at home can I do homa\b',
               'I know how to perform a basic Vedic homa at home. Can I do homa', t, flags=re.IGNORECASE)

    # Grammatical structure replacements
    t = re.sub(r'\bOr Can\b', 'Can', t)
    t = re.sub(r'\bIf Yes,', 'If yes,', t)
    t = re.sub(r'\bIf Yes\.', 'If yes.', t)
    t = re.sub(r"Don't be hurry", "Don't be in a hurry", t, flags=re.IGNORECASE)
    t = re.sub(r'(how many days of gap is allowed)\.', r'\1?', t, flags=re.IGNORECASE)
    t = re.sub(r'(How to pray in that case)\.', r'\1?', t, flags=re.IGNORECASE)
    t = re.sub(r'(is it a good practice)\?', r'\1?', t, flags=re.IGNORECASE)
    t = re.sub(r'(Can there be a? ?gap between two mandala sadhana)\.', r'\1?', t, flags=re.IGNORECASE)
    t = re.sub(r'(Is that acceptable)\.', r'\1?', t, flags=re.IGNORECASE)

    t = re.sub(r'\bre offer\b', 're-offer', t, flags=re.IGNORECASE)
    t = re.sub(r'\bre offering\b', 're-offering', t, flags=re.IGNORECASE)
    t = re.sub(r'\bsleep like state\b', 'sleep-like state', t, flags=re.IGNORECASE)
    t = re.sub(r'\bdream like state\b', 'dream-like state', t, flags=re.IGNORECASE)
    t = re.sub(r'\bnon-items\b', 'non-vegetarian items', t, flags=re.IGNORECASE)
    t = re.sub(r'\byoutube\b', 'YouTube', t, flags=re.IGNORECASE)
    t = re.sub(r'\bYog Nidra\b', 'Yoga Nidra', t)
    t = re.sub(r'\byog-nidrā\b', 'yoga-nidrā', t)
    t = re.sub(r'\bYog-nidrā\b', 'Yoga-nidrā', t)
    t = re.sub(r'\bPanchopchar\b', 'Panchopachara', t, flags=re.IGNORECASE)
    t = re.sub(r'\b03Mandalas\b', '03 Mandalas', t)

    t = re.sub(r'key, Benefits of Sadhana in Sandhyakala:', 'key benefits of Sadhana in Sandhyakala:', t)
    t = re.sub(r'with clarity\.:', 'with clarity:', t)
    t = re.sub(r'\bfill up and you may\b', 'fill it in, and you may', t)

    # General cleanup
    t = clean_punctuation_spacing(t)
    
    # Capitalize lone "i" -> "I"
    t = re.sub(r'\bi\b', 'I', t)
    
    # Capitalize Swami/Swamiji/Guruji/Gurudev when used as pronouns or titles
    t = re.sub(r'\bswami\b', 'Swami', t, flags=re.IGNORECASE)
    t = re.sub(r'\bswamiji\b', 'Swamiji', t, flags=re.IGNORECASE)
    t = re.sub(r'\bguruji\b', 'Guruji', t, flags=re.IGNORECASE)
    t = re.sub(r'\bgurudev\b', 'Gurudev', t, flags=re.IGNORECASE)
    t = re.sub(r'\bswamy\b', 'Swamy', t, flags=re.IGNORECASE)
    
    # Sentence capitalization
    t = capitalize_sentences(t)

    # If it ends in a letter or space and seems like a question, add question mark.
    # We do a basic heuristic: if it starts with a question word and ends with no punctuation.
    first_word = re.findall(r'\b\w+\b', t.lower())
    if first_word and first_word[0] in {'how', 'what', 'why', 'is', 'can', 'should', 'does', 'do', 'would', 'are', 'am', 'who', 'where', 'when'}:
        if t and t[-1] not in ('.', '?', '!', '"', "'", '”', '’'):
            t += '?'

    return t


def process_csv(input_path, output_path):
    rows_in = []
    used_enc = 'utf-8-sig'
    for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            with open(input_path, newline='', encoding=enc) as f:
                reader = csv.reader(f)
                rows_in = list(reader)
            if len(rows_in) > 1 and len(rows_in[1]) >= 6:
                q_sample = rows_in[1][5]
                if '\ufffd' not in q_sample and '\x00' not in q_sample:
                    used_enc = enc
                    break
            rows_in = []
        except Exception:
            continue
    else:
        print(f"[!] Could not decode {input_path}")
        return

    if not rows_in:
        print(f"[!] Empty file: {input_path}")
        return

    header = rows_in[0]
    try:
        q_idx = header.index('question')
        a_idx = header.index('answer')
    except ValueError:
        print(f"[!] Could not find question/answer columns in {input_path}")
        print(f"    Header: {header}")
        return

    fixed = 0
    out_rows = [header]
    for i, row in enumerate(rows_in[1:], start=2):
        new_row = list(row)
        if len(new_row) <= max(q_idx, a_idx):
            out_rows.append(new_row)
            continue
        orig_q = new_row[q_idx]
        orig_a = new_row[a_idx]
        new_q = fix_text(orig_q)
        new_a = fix_text(orig_a)
        if new_q != orig_q or new_a != orig_a:
            fixed += 1
        new_row[q_idx] = new_q
        new_row[a_idx] = new_a
        out_rows.append(new_row)

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerows(out_rows)

    print(f"[OK] {input_path} -> {output_path}  ({fixed} rows changed)")


if __name__ == '__main__':
    base = r'C:\Users\apgib\.gemini\antigravity-ide\scratch\bhairava-anugraha'
    process_csv(f'{base}\\qna-preview.csv', f'{base}\\qna-preview.csv')
    process_csv(f'{base}\\qna.csv',         f'{base}\\qna.csv')
    print("Done.")
