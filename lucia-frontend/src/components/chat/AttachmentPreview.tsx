"use client";

import { X, FileText, Image as ImageIcon, FileSpreadsheet, Music, AlertCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils/cn";
import type { PendingUpload } from "@/types/attachments";
import { formatFileSize } from "@/types/attachments";

interface Props {
  uploads: PendingUpload[];
  onRemove: (localId: string) => void;
}

const typeIcons = {
  image: ImageIcon,
  document: FileText,
  spreadsheet: FileSpreadsheet,
  audio: Music,
};

export function AttachmentPreview({ uploads, onRemove }: Props) {
  if (uploads.length === 0) return null;
  
  return (
    <div className="flex flex-wrap gap-2 px-3 pt-3 pb-1">
      {uploads.map((upload) => {
        const type = upload.attachment?.type || "document";
        const Icon = typeIcons[type] || FileText;
        const isImage = type === "image";
        const previewUrl = isImage ? URL.createObjectURL(upload.file) : null;
        
        return (
          <div
            key={upload.localId}
            className={cn(
              "group relative flex items-center gap-2.5 px-2.5 py-2 rounded-lg border transition-all max-w-xs",
              upload.status === "error"
                ? "bg-status-error/10 border-status-error/30"
                : "bg-background border-border hover:border-border-strong"
            )}
          >
            {/* Icon / Thumbnail */}
            {isImage && previewUrl ? (
              <img
                src={previewUrl}
                alt={upload.file.name}
                className="h-8 w-8 rounded object-cover flex-shrink-0"
              />
            ) : (
              <div className="p-1.5 rounded bg-background-panel text-accent flex-shrink-0">
                <Icon className="h-4 w-4" />
              </div>
            )}
            
            {/* Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-medium text-foreground truncate">
                  {upload.file.name}
                </span>
                {upload.status === "uploading" && (
                  <Loader2 className="h-3 w-3 text-accent animate-spin flex-shrink-0" />
                )}
                {upload.status === "error" && (
                  <AlertCircle className="h-3 w-3 text-status-error flex-shrink-0" />
                )}
              </div>
              <div className="text-2xs font-mono text-foreground-subtle mt-0.5">
                {upload.status === "uploading" && (
                  <span>{Math.round(upload.progress)}% · {formatFileSize(upload.file.size)}</span>
                )}
                {upload.status === "ready" && (
                  <span>{formatFileSize(upload.file.size)} · ready</span>
                )}
                {upload.status === "error" && (
                  <span className="text-status-error">{upload.error}</span>
                )}
              </div>
              
              {upload.status === "uploading" && (
                <div className="mt-1 h-0.5 bg-background-panel rounded overflow-hidden">
                  <div
                    className="h-full bg-accent transition-all duration-200"
                    style={{ width: `${upload.progress}%` }}
                  />
                </div>
              )}
            </div>
            
            {/* Remove button */}
            <button
              type="button"
              onClick={() => onRemove(upload.localId)}
              className="opacity-60 hover:opacity-100 p-1 rounded text-foreground-subtle hover:text-foreground hover:bg-background-panel transition-all flex-shrink-0"
              aria-label="Remove attachment"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        );
      })}
    </div>
  );
}