import os
from dotenv import load_dotenv
from langchain_core.messages import RemoveMessage, SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.types import interrupt, Command
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver

load_dotenv()
DB_URI = os.getenv("POSTGRES_URI", "postgresql://postgres:1234@localhost:5432/langgraph_db?sslmode=disable")

print("Testing minimal loop with LangGraph interrupt and Command...")
