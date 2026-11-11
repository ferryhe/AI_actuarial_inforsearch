import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

const preloadReloadKey = "vite:preload-error-entry";
const preloadChatDraftKey = "vite:preload-error-chat-draft";
const entryScript = document.querySelector<HTMLScriptElement>('script[type="module"][src]')?.src ?? window.location.pathname;
window.addEventListener("vite:preloadError", (event) => {
  try {
    if (window.sessionStorage.getItem(preloadReloadKey) === entryScript) return;
    const chatDraft = document.querySelector<HTMLTextAreaElement>('[data-testid="input-chat-message"]')?.value ?? "";
    if (chatDraft) window.sessionStorage.setItem(preloadChatDraftKey, chatDraft);
    else window.sessionStorage.removeItem(preloadChatDraftKey);
    window.sessionStorage.setItem(preloadReloadKey, entryScript);
  } catch {
    return;
  }
  event.preventDefault();
  window.location.reload();
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
