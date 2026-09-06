from datetime import datetime

def web_search(query: str, max_results: int = 5) -> dict:
    """Search the live web using DuckDuckGo"""
    try:
        from duckduckgo_search import DDGS
        current_year = datetime.now().year
        
        results = []
        with DDGS() as ddgs:
            # Live search fetch
            search_query = f"{query}"
            for r in ddgs.text(search_query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", "")
                })
        
        if not results:
            return {"success": False, "message": "Web par koi fresh information nahi mili.", "data": []}
        
        summary = f"Fresh Web Search Results (Current Year {current_year}):\n\n"
        for i, r in enumerate(results, 1):
            summary += f"{i}. Title: {r['title']}\n   Snippet: {r['snippet']}\n   Source: {r['url']}\n\n"
        
        return {"success": True, "message": summary, "data": results}
    except Exception as e:
        print(f"[Web Search Error]: {e}")
        return {"success": False, "message": f"Web search fail hui: {e}", "data": []}