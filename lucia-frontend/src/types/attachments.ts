export type AttachmentType = "image" | "document" | "spreadsheet" | "audio";
export type UploadStatus = "idle" | "uploading" | "processing" | "ready" | "error";

export interface Attachment {
  id: string;
  filename: string;
  mimeType: string;
  size: number;
  type: AttachmentType;
  status: UploadStatus;
  preview?: string;
  metadata?: Record<string, any>;
  createdAt?: string;
  errorMessage?: string;
}

export interface PendingUpload {
  localId: string;
  file: File;
  status: UploadStatus;
  progress: number;
  attachment?: Attachment;
  error?: string;
}

export const SUPPORTED_MIMES: Record<string, AttachmentType> = {
  "image/png": "image",
  "image/jpeg": "image",
  "image/jpg": "image",
  "image/webp": "image",
  "application/pdf": "document",
  "application/msword": "document",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
  "text/plain": "document",
  "text/csv": "spreadsheet",
  "application/vnd.ms-excel": "spreadsheet",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "spreadsheet",
  "audio/mpeg": "audio",
  "audio/wav": "audio",
  "audio/x-wav": "audio",
  "audio/mp4": "audio",
  "audio/m4a": "audio",
  "audio/ogg": "audio",
};

export const SUPPORTED_EXTENSIONS = [
  ".png", ".jpg", ".jpeg", ".webp",
  ".pdf", ".doc", ".docx", ".txt",
  ".csv", ".xls", ".xlsx",
  ".mp3", ".wav", ".m4a", ".ogg"
];

export function detectAttachmentType(file: File): AttachmentType | null {
  const mime = SUPPORTED_MIMES[file.type];
  if (mime) return mime;
  
  const ext = "." + file.name.split(".").pop()?.toLowerCase();
  const imgExts = [".png", ".jpg", ".jpeg", ".webp"];
  const docExts = [".pdf", ".doc", ".docx", ".txt"];
  const sheetExts = [".csv", ".xls", ".xlsx"];
  const audioExts = [".mp3", ".wav", ".m4a", ".ogg"];
  
  if (imgExts.includes(ext)) return "image";
  if (docExts.includes(ext)) return "document";
  if (sheetExts.includes(ext)) return "spreadsheet";
  if (audioExts.includes(ext)) return "audio";
  return null;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}