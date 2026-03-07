import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, Loader2, X } from "lucide-react";
import { useTranslation } from "@/components/Layout";

interface ConfirmDeleteModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title?: string;
  message?: string;
  loading?: boolean;
}

export default function ConfirmDeleteModal({
  open,
  onClose,
  onConfirm,
  title,
  message,
  loading = false,
}: ConfirmDeleteModalProps) {
  const { t } = useTranslation();
  const [inputValue, setInputValue] = useState("");

  const confirmPhrase = "confirm delete";
  const isMatch = inputValue.trim().toLowerCase() === confirmPhrase;

  useEffect(() => {
    if (!open) setInputValue("");
  }, [open]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            className="bg-card rounded-xl border border-border shadow-xl w-full max-w-md"
            onClick={(e) => e.stopPropagation()}
            data-testid="modal-confirm-delete"
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-destructive" />
                <h3 className="font-semibold text-sm">
                  {title || t("common.confirm_delete_title")}
                </h3>
              </div>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg hover:bg-muted transition-colors"
                data-testid="button-close-delete-modal"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="px-5 py-4 space-y-4">
              <p className="text-sm text-muted-foreground">
                {message || t("common.confirm_delete_msg")}
              </p>

              <div className="space-y-2">
                <label className="text-xs font-medium text-muted-foreground">
                  {t("common.confirm_delete_type")}{" "}
                  <span className="font-mono font-bold text-foreground">confirm delete</span>
                </label>
                <input
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder={t("common.confirm_delete_placeholder")}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-destructive/30"
                  autoFocus
                  data-testid="input-confirm-delete"
                />
              </div>

              <div className="flex items-center gap-2 justify-end pt-1">
                <button
                  onClick={onClose}
                  className="px-3 py-2 text-sm rounded-lg border border-border hover:bg-muted transition-colors"
                  data-testid="button-cancel-delete"
                >
                  {t("common.cancel")}
                </button>
                <button
                  onClick={onConfirm}
                  disabled={!isMatch || loading}
                  className="px-3 py-2 text-sm rounded-lg bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
                  data-testid="button-execute-delete"
                >
                  {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  {t("common.delete")}
                </button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
