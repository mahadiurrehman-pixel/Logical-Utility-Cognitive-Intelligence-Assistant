import { apiFetch } from "./client";
import { mockProviders, mockSystemStatus } from "../mock/data";
import type { Provider, SystemStatus } from "@/types";

export async function getProviders(): Promise<Provider[]> {
  try {
    return await apiFetch<Provider[]>("/providers/status");
  } catch {
    return mockProviders;
  }
}

export async function getSystemStatus(): Promise<SystemStatus> {
  try {
    return await apiFetch<SystemStatus>("/system/status");
  } catch {
    return mockSystemStatus;
  }
}