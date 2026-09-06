from tools.file_tools import write_file

def generate_code_file(path: str, code: str, language: str = "python") -> dict:
    """
    Save generated code to a file.
    Note: The LLM itself generates the code; this tool just saves it.
    """
    try:
        result = write_file(path, code)
        if result["success"]:
            return {
                "success": True,
                "message": f"{language.title()} code file mein likh diya: {path}",
                "data": code
            }
        return result
    except Exception as e:
        return {"success": False, "message": f"Code save nahi hua: {e}"}