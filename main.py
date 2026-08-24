import openai
import supabase
import os

# Initialize clients
openai.api_key = os.getenv("OPENAI_API_KEY")
supabase_client = supabase.create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

def get_expert_knowledge(user_query: str, user_cvj_stage: str) -> str:
    """
    THE TRILLION-LEVEL SEARCH ENGINE
    1. Converts user question to vector
    2. Searches Supabase for matching frameworks
    3. Returns the exact expert text needed
    """
    # Step 1: Create embedding for the user's query
    response = openai.Embedding.create(
        input=user_query,
        model="text-embedding-ada-002"
    )
    query_embedding = response['data'][0]['embedding']

    # Step 2: Search the Vector Database (Semantic Search + Metadata Filter)
    matches = supabase_client.rpc('match_frameworks', {
        'query_embedding': query_embedding,
        'match_threshold': 0.75, # Only return highly relevant matches
        'match_count': 3,        # Pull the top 3 frameworks
        'filter_stage': user_cvj_stage # Filter by their current business stage
    }).execute()

    # Step 3: Format the retrieved knowledge
    context = ""
    for match in matches.data:
        context += f"\n--- EXPERT: {match['expert_name']} | FRAMEWORK: {match['framework_name']} ---\n{match['content']}\n"
    
    return context

# --- HOW THE AI USES IT ---
def chat_with_ai(user_message, user_profile):
    # 1. Retrieve the exact expert knowledge needed for THIS specific question
    expert_context = get_expert_knowledge(user_message, user_profile['cvj_stage'])
    
    # 2. Build a lean, highly focused system prompt
    system_prompt = f"""
    You are an elite AI Business Coach. 
    Use ONLY the following expert frameworks to answer the user. 
    Do not make up advice. Anchor your response to these specific experts.
    
    USER CONTEXT:
    Niche: {user_profile['niche']}
    Bottleneck: {user_profile['bottleneck']}
    
    EXPERT KNOWLEDGE RETRIEVED:
    {expert_context}
    """
    
    # 3. Send to LLM (Groq/Gemini)
    # ... (LLM call happens here)
