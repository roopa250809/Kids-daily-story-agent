import os

from dotenv import load_dotenv


load_dotenv(override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "nebius").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen/Qwen3-30B-A3B")
NEBIUS_API_KEY = os.getenv("NEBIUS_API_KEY")
NEBIUS_BASE_URL = os.getenv("NEBIUS_BASE_URL", "https://api.studio.nebius.com/v1")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "kids-daily-story-history")
PINECONE_DIMENSION = int(os.getenv("PINECONE_DIMENSION", "384"))
PINECONE_AUTO_CREATE_INDEX = os.getenv("PINECONE_AUTO_CREATE_INDEX", "false").lower() == "true"
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")
