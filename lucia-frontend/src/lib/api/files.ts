import { API_URL } from "./client";
import type { Attachment } from "@/types/attachments";

export async function uploadFile(
  file: File,
  onProgress?: (percent: number) => void
): Promise<Attachment> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append("file", file);
    
    const xhr = new XMLHttpRequest();
    
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress((e.loaded / e.total) * 100);
      }
    });
    
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new Error("Invalid response"));
        }
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || "Upload failed"));
        } catch {
          reject(new Error(`Upload failed: ${xhr.status}`));
        }
      }
    });
    
    xhr.addEventListener("error", () => reject(new Error("Network error")));
    xhr.addEventListener("abort", () => reject(new Error("Upload cancelled")));
    
    xhr.open("POST", `${API_URL}/api/files/upload`);
    xhr.send(formData);
  });
}

export async function deleteFile(fileId: string): Promise<void> {
  await fetch(`${API_URL}/api/files/${fileId}`, { method: "DELETE" });
}