import { API_URL } from "./client";

export interface ChatStreamOptions {
  message: string;
  conversationId?: string | null;
  attachmentIds?: string[];
  onToken: (token: string) => void;
  onActivity?: (activity: any) => void;
  onMetadata?: (metadata: any) => void;
  onComplete?: () => void;
  onError?: (error: Error) => void;
}

function processSSEEvent(
  event: string,
  options: {
    onToken: (token: string) => void;
    onActivity?: (activity: any) => void;
    onMetadata?: (metadata: any) => void;
  }
) {
  const {
    onToken,
    onActivity,
    onMetadata,
  } = options;

  const lines = event.split(/\r?\n/);

  for (const line of lines) {
    const trimmed = line.trim();

    if (!trimmed.startsWith("data:")) {
      continue;
    }

    const rawData = trimmed
      .slice(5)
      .trim();

    if (!rawData || rawData === "[DONE]") {
      continue;
    }

    try {
      const data = JSON.parse(rawData);

      if (typeof data === "string") {
        onToken(data);
        continue;
      }

      if (data.token !== undefined && data.token !== null) {
        onToken(String(data.token));
      }

      if (data.content !== undefined && data.content !== null) {
        onToken(String(data.content));
      }

      if (data.text !== undefined && data.text !== null) {
        onToken(String(data.text));
      }

      if (data.activity !== undefined) {
        onActivity?.(data.activity);
      }

      if (data.metadata !== undefined) {
        onMetadata?.(data.metadata);
      }

    } catch (error) {
      console.warn(
        "Skipping invalid SSE payload:",
        rawData
      );
    }
  }
}

export async function streamChat(
  options: ChatStreamOptions
): Promise<void> {
  const {
    message,
    conversationId,
    attachmentIds = [],
    onToken,
    onActivity,
    onMetadata,
    onComplete,
    onError,
  } = options;

  let completed = false;

  const completeOnce = () => {
    if (completed) return;

    completed = true;
    onComplete?.();
  };

  try {
    const response = await fetch(
      `${API_URL}/chat/stream`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
          "Cache-Control": "no-cache",
        },
        body: JSON.stringify({
          message,
          conversationId,
          attachmentIds,
        }),
      }
    );

    if (!response.ok) {
      throw new Error(
        `Server returned status ${response.status}`
      );
    }

    if (!response.body) {
      throw new Error(
        "Streaming response body is unavailable."
      );
    }

    const reader = response.body.getReader();

    const decoder = new TextDecoder("utf-8");

    let buffer = "";

    while (true) {
      const {
        done,
        value,
      } = await reader.read();

      if (done) {
        break;
      }

      if (!value) {
        continue;
      }

      buffer += decoder.decode(
        value,
        {
          stream: true,
        }
      );

      // Handle both LF and CRLF SSE separators.
      const events = buffer.split(
        /\r?\n\r?\n/
      );

      // Keep incomplete event for next chunk.
      buffer = events.pop() || "";

      for (const event of events) {
        if (!event.trim()) {
          continue;
        }

        processSSEEvent(
          event,
          {
            onToken,
            onActivity,
            onMetadata,
          }
        );
      }
    }

    // Flush decoder's remaining bytes.
    buffer += decoder.decode();

    // Process final incomplete event, if any.
    if (buffer.trim()) {
      processSSEEvent(
        buffer,
        {
          onToken,
          onActivity,
          onMetadata,
        }
      );
    }

    completeOnce();

  } catch (err) {
    const error =
      err instanceof Error
        ? err
        : new Error(
            String(err)
          );

    console.error(
      "Chat streaming error:",
      error
    );

    onError?.(error);

    onToken(
      "\n\n⚠️ Connection to LUCIA API failed. Is api_server.py running?"
    );

    completeOnce();
  }
}