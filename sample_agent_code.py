from langchain.prompts import PromptTemplate
from langchain_openai import AzureChatOpenAI
import json
from typing import Any, Dict, List
from .fingerprint import DataFingerprint

chart_prompt = PromptTemplate(
    input_variables=["schema", "insights_json"],
    template="""
You are a visualization assistant.
Dataset schema: {schema}
Insights: {insights_json}

---
Recommend up to 3 interactive charts in Chart.js.
Rules:
- Output must be valid HTML with embedded <script> using Chart.js from CDN.
- Each chart must have a <canvas id="chart_X"> block and a corresponding new Chart(...) config.
- Choose chart types (line, bar, pie, histogram, etc.) that best fit the data and insights.
- Do not include explanations — only return raw HTML+JS.
"""
)

def chart_recommender_agent(fp: DataFingerprint, insights: List[Dict[str, Any]]) -> str:
    llm = AzureChatOpenAI(
        deployment_name="gpt-4o-mini",   # change to your Azure deployment
        api_version="2024-05-01-preview",
        temperature=0
    )
    chain = chart_prompt | llm
    result = chain.invoke({
        "schema": fp.schema,
        "insights_json": json.dumps(insights, indent=2),
    })
    return result.content