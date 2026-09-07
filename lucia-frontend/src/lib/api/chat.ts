import { API_URL } from "./client";

export interface ChatStreamOptions {
  message: string;
  conversationId?: string | null;
  onToken: (token: string) => void;
  onActivity?: (activity: any) => void;
  onMetadata?: (metadata: any) => void;
  onComplete?: () => void;
  onError?: (error: Error) => void;
}

export async function streamChat(options: ChatStreamOptions): Promise<void> {
  const { message, conversationId, onToken, onActivity, onMetadata, onComplete, onError } = options;

  try {
    const response = await fetch(`${API_URL}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, conversationId }),
    });

    if (!response.ok || !response.body) {
      throw new Error(`Server returned status ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith("data:")) {
          try {
            const data = JSON.parse(trimmed.slice(5).trim());
            if (data.token) onToken(data.token);
            if (data.activity) onActivity?.(data.activity);
            if (data.metadata) onMetadata?.(data.metadata);
          } catch (e) {
            console.error("SSE parse error", e);
          }
        }
      }
    }

    onComplete?.();
  } catch (err: any) {
    console.error("Chat streaming error:", err);
    onError?.(err);
    onToken(`\n\n⚠️ Connection to LUCIA API failed. Is api_server.py running?`);
    onComplete?.();
  }
}