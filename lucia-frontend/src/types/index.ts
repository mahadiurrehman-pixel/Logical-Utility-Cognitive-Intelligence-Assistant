export type MessageRole = "user" | "assistant" | "system";

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
  metadata?: {
    provider?: string;
    model?: string;
    responseTime?: number;
    tokensIn?: number;
    tokensOut?: number;
  };
  streaming?: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  updatedAt: string;
  messages?: Message[];
}

export type ProviderStatus = "healthy" | "cooldown" | "error" | "available";

export interface Provider {
  id: string;
  name: string;
  status: ProviderStatus;
  model?: string;
}

export interface SystemStatus {
  online: boolean;
  aiGateway: "operational" | "degraded" | "down";
  tools: "operational" | "degraded" | "down";
  gmail: "connected" | "disconnected";
  memory: "operational" | "degraded";
}

export interface ActivityState {
  active: boolean;
  status?: "thinking" | "processing" | "using-tool" | "switching-model";
  detail?: string;
}