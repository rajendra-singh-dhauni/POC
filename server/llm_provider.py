import os
import requests
import json
from typing import Optional

# Lightweight Gemini client wrapper using REST calls.
# This module expects GEMINI_API_KEY and GEMINI_MODEL to be available in env.

class GeminiClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.environ.get('GEMINI_API_KEY')
        self.model = model or os.environ.get('GEMINI_MODEL', 'gemini-flash-lite-latest')
        self.base = 'https://generativelanguage.googleapis.com/v1beta2'

    def generate_text(self, prompt: str, temperature: float = 0.2, max_tokens: int = 800) -> str:
        if not self.api_key:
            raise RuntimeError('No GEMINI_API_KEY set for Gemini')
        url = f"{self.base}/models/{self.model}:generate"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }
        body = {
            'prompt': {
                'text': prompt
            },
            'temperature': temperature,
            'maxOutputTokens': max_tokens,
        }
        r = requests.post(url, headers=headers, json=body, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f'Gemini error: {r.status_code} {r.text}')
        data = r.json()
        candidates = data.get('candidates') or []
        if candidates:
            return candidates[0].get('content', '')
        return json.dumps(data)
