import type { Conversation, Provider, SystemStatus } from "@/types";

export const mockConversations: Conversation[] = [
  { id: "1", title: "Build LUCIA API", updatedAt: new Date().toISOString() },
  { id: "2", title: "Rehu architecture", updatedAt: new Date(Date.now() - 3 * 3600000).toISOString() },
  { id: "3", title: "Python OOP concepts", updatedAt: new Date(Date.now() - 5 * 3600000).toISOString() },
  { id: "4", title: "Multi-provider LLM fallback", updatedAt: new Date(Date.now() - 86400000).toISOString() },
  { id: "5", title: "Gmail integration debug", updatedAt: new Date(Date.now() - 2 * 86400000).toISOString() },
];

export const mockProviders: Provider[] = [
  { id: "groq_primary", name: "Groq Primary", status: "healthy", model: "openai/gpt-oss-120b" },
  { id: "groq_mdi", name: "Groq MDI", status: "healthy", model: "openai/gpt-oss-120b" },
  { id: "groq_uni", name: "Groq UNI", status: "cooldown", model: "openai/gpt-oss-120b" },
  { id: "huggingface", name: "Hugging Face", status: "available", model: "Qwen/Qwen3.5-9B" },
  { id: "gemini", name: "Gemini", status: "available", model: "gemini-2.0-flash" },
];

export const mockSystemStatus: SystemStatus = {
  online: true,
  aiGateway: "operational",
  tools: "operational",
  gmail: "connected",
  memory: "operational",
};