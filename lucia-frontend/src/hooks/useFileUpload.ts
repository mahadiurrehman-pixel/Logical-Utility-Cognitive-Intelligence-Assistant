"use client";

import { useState, useCallback } from "react";
import { uploadFile, deleteFile } from "@/lib/api/files";
import { detectAttachmentType, SUPPORTED_EXTENSIONS } from "@/types/attachments";
import type { PendingUpload, Attachment } from "@/types/attachments";

const MAX_FILE_SIZE = 25 * 1024 * 1024;  // 25 MB
const MAX_ATTACHMENTS = 5;

export function useFileUpload() {
  const [uploads, setUploads] = useState<PendingUpload[]>([]);
  
  const validateFile = (file: File): string | null => {
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!SUPPORTED_EXTENSIONS.includes(ext)) {
      return `Unsupported file type: ${ext}`;
    }
    if (file.size > MAX_FILE_SIZE) {
      return `File too large (max ${MAX_FILE_SIZE / (1024 * 1024)} MB)`;
    }
    if (!detectAttachmentType(file)) {
      return "Unrecognized file format";
    }
    return null;
  };
  
  const addFiles = useCallback(async (files: FileList | File[]) => {
    const fileList = Array.from(files);
    
    if (uploads.length + fileList.length > MAX_ATTACHMENTS) {
      alert(`Maximum ${MAX_ATTACHMENTS} attachments allowed`);
      return;
    }
    
    for (const file of fileList) {
      const error = validateFile(file);
      const localId = crypto.randomUUID();
      
      if (error) {
        setUploads((prev) => [...prev, {
          localId, file, status: "error", progress: 0, error,
        }]);
        continue;
      }
      
      const pending: PendingUpload = {
        localId, file, status: "uploading", progress: 0,
      };
      setUploads((prev) => [...prev, pending]);
      
      try {
        const attachment = await uploadFile(file, (progress) => {
          setUploads((prev) =>
            prev.map((u) => u.localId === localId ? { ...u, progress } : u)
          );
        });
        
        setUploads((prev) =>
          prev.map((u) =>
            u.localId === localId
              ? { ...u, status: "ready", progress: 100, attachment }
              : u
          )
        );
      } catch (err: any) {
        setUploads((prev) =>
          prev.map((u) =>
            u.localId === localId
              ? { ...u, status: "error", error: err.message }
              : u
          )
        );
      }
    }
  }, [uploads.length]);
  
  const removeUpload = useCallback(async (localId: string) => {
    const upload = uploads.find((u) => u.localId === localId);
    if (upload?.attachment?.id) {
      try {
        await deleteFile(upload.attachment.id);
      } catch {}
    }
    setUploads((prev) => prev.filter((u) => u.localId !== localId));
  }, [uploads]);
  
  const clearAll = useCallback(() => {
    uploads.forEach((u) => {
      if (u.attachment?.id) deleteFile(u.attachment.id).catch(() => {});
    });
    setUploads([]);
  }, [uploads]);
  
  const getReadyAttachmentIds = useCallback(() => {
    return uploads
      .filter((u) => u.status === "ready" && u.attachment)
      .map((u) => u.attachment!.id);
  }, [uploads]);
  
  return {
    uploads, addFiles, removeUpload, clearAll, getReadyAttachmentIds,
  };
}