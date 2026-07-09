from langchain_core.prompts import PromptTemplate
from langchain_openai import AzureChatOpenAI, ChatOpenAI
import os
import sys
import requests

rephrase_prompt = PromptTemplate(
    input_variables=["question"],
    template="""You are a spiritual assistant specialized in traditional Indian scriptures, Hinduism, and Guru-Shishya dialogue.

Your task is to rephrase the user's question according to these rules:
1. If the question is not written in English, first translate it into clean, grammatically correct English.
2. If the question is already in English (or after you translate it), rephrase it into a traditional Guru-Shishya style conversation. 
   - The tone must be that of a humble, sincere student (Shishya) asking a spiritual question to their Guru.
   - Address the Guru respectfully as "Namskaram Guruji".
   - The language should be polite, respectful, and spiritual in nature.
   - Keep it concise and under 150 words.
   - Keep the original meaning, details, and questions completely intact. Do not lose any semantic meaning or context.
   - Do not write any dialog tags (like "Student:" or "Guru:") or conversational replies from the Guru. Just output the Shishya's question.
   - Output ONLY the rephrased question. Do not include any quotes, introductions, notes, or explanations.

Original Question:
"{question}"

Rephrased Question:"""
)

def local_mock_rephrase(question: str) -> str:
    print("[*] Using local mock rephraser fallback.")
    lower_q = question.lower()
    mock_rephrased = question
    
    # Simple translation mapping for demo
    translations = [
        ("agar ", "if "),
        ("mandala sadhana", "Mandala Sadhana"),
        (" sādhanā", " Sadhana"),
        ("sadhna", "Sadhana"),
        ("ke dauran ", "during "),
        ("light chali jaye", "electricity goes out"),
        ("to kya kare", "what should one do"),
        ("namaskaram", ""),
        ("namaskar", ""),
        ("swami,", ""),
        ("guruji,", ""),
    ]
    
    for hindi, eng in translations:
        mock_rephrased = mock_rephrased.replace(hindi, eng).replace(hindi.capitalize(), eng.capitalize())
        
    mock_rephrased = mock_rephrased.strip()
    
    # Capitalize first letter of question
    if mock_rephrased:
        mock_rephrased = mock_rephrased[0].upper() + mock_rephrased[1:]
        
    # Format as Guru-Shishya query
    if not mock_rephrased.startswith("Guruji") and not mock_rephrased.startswith("Swamiji"):
        mock_rephrased = f"Guruji, {mock_rephrased[0].lower() + mock_rephrased[1:] if len(mock_rephrased) > 1 else mock_rephrased}"
        
    if not mock_rephrased.endswith("?"):
        mock_rephrased = mock_rephrased.rstrip(".! ") + "?"
        
    return mock_rephrased

GEMINI_NETWORK_BLOCKED = False

def rephrase_question(question: str) -> str:
    global GEMINI_NETWORK_BLOCKED
    # Setup LLM based on environment variables
    gemini_key = os.environ.get("GEMINI_API_KEY")
    gemini_backup_key = os.environ.get("GEMINI_API_KEY_BACKUP")
    azure_key = os.environ.get("AZURE_OPENAI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    gemini_failed = False
    
    # Helper to call Gemini API with a specific key
    def try_gemini_request(api_key: str) -> str:
        prompt_text = rephrase_prompt.format(question=question)
        model_name = os.environ.get("GEMINI_MODEL_NAME", "gemini-flash-latest")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": api_key
        }
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt_text
                        }
                    ]
                }
            ]
        }
        response = requests.post(url, headers=headers, json=payload, timeout=3)
        if response.status_code == 200:
            data = response.json()
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            raise Exception(f"API returned status code {response.status_code}: {response.text}")

    # 1. Hitting Gemini endpoint if GEMINI_API_KEY is configured
    if gemini_key and not GEMINI_NETWORK_BLOCKED:
        print("[*] Hitting Primary Gemini API for rephrasing...")
        try:
            return try_gemini_request(gemini_key)
        except Exception as e:
            print(f"[-] Primary Gemini API request failed: {e}")
            # Try backup key if available
            if gemini_backup_key:
                print("[*] Hitting Backup Gemini API...")
                try:
                    return try_gemini_request(gemini_backup_key)
                except Exception as e_backup:
                    print(f"[-] Backup Gemini API request also failed: {e_backup}")
            
            gemini_failed = True
            GEMINI_NETWORK_BLOCKED = True
            print("[-] Gemini API network blocked/timed out; disabling future attempts for this process session.")

    # 2. Check if API keys are set; if not, use mock translator
    if not azure_key and not openai_key:
        return local_mock_rephrase(question)
        
    if gemini_failed:
        return local_mock_rephrase(question)

    # 3. Using LangChain as second fallback
    try:
        if azure_key:
            deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
            api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-05-01-preview")
            azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
            
            llm = AzureChatOpenAI(
                deployment_name=deployment_name,
                api_version=api_version,
                azure_endpoint=azure_endpoint,
                api_key=azure_key,
                temperature=0.1,
                timeout=5
            )
        else:
            model_name = os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini")
            llm = ChatOpenAI(
                model=model_name,
                api_key=openai_key,
                temperature=0.1,
                timeout=5
            )
            
        chain = rephrase_prompt | llm
        result = chain.invoke({"question": question})
        return result.content.strip()
    except Exception as e:
        print(f"[-] LangChain LLM execution failed or timed out: {e}")
        return local_mock_rephrase(question)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        test_q = " ".join(sys.argv[1:])
    else:
        test_q = "agar mandala sadhana ke dauran light chali jaye to kya kare?"
    print(f"Original: {test_q}")
    try:
        rephrased = rephrase_question(test_q)
        print(f"Rephrased: {rephrased}")
    except Exception as e:
        print(f"Error during rephrasing: {e}")
