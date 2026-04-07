#!/usr/bin/env python3
"""Test Azure OpenAI connection."""

import asyncio
import sys
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv()

from src.infra.model_adapter import init_models, ModelAdapter

async def main():
    print("Initializing models...")
    init_models()
    
    print("\nTesting Azure OpenAI (gpt-5.3-chat)...")
    try:
        response = await ModelAdapter.invoke(
            "gpt-5.3-chat",
            "Say 'Hello from Azure OpenAI!' in exactly 5 words.",
            temperature=0.3,
            max_tokens=50,
        )
        print(f"✅ Response: {response}")
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    print("\nTesting gpt-4o alias (should route to Azure)...")
    try:
        response = await ModelAdapter.invoke(
            "gpt-4o",
            "What is 2+2? Answer with just the number.",
            temperature=0.1,
            max_tokens=10,
        )
        print(f"✅ Response: {response}")
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    print("\n🎉 All tests passed!")
    return 0

if __name__ == "__main__":
    exit(asyncio.run(main()))
