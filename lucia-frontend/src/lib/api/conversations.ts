import { apiFetch } from "./client";
import { mockConversations } from "../mock/data";
import type { Conversation } from "@/types";

export async function getConversations(): Promise<Conversation[]> {
  try {
    return await apiFetch<Conversation[]>("/conversations");
  } catch {
    return mockConversations;
  }
}

export async function createConversation(title?: string): Promise<Conversation> {
  try {
    return await apiFetch<Conversation>("/conversations", {
      method: "POST",
      body: JSON.stringify({ title: title || "New Conversation" }),
    });
  } catch {
    return {
      id: crypto.randomUUID(),
      title: title || "New Conversation",
      updatedAt: new Date().toISOString(),
    };
  }
}

export async function deleteConversation(id: string): Promise<void> {
  try {
    await apiFetch(`/conversations/${id}`, { method: "DELETE" });
  } catch {
    // Silent fail for mock
  }
}