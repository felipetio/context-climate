import { useState, useRef, useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function Document() {
  const { content, version, phase, html_content } = props;
  const [isEditing, setIsEditing] = useState(false);
  const [viewMode, setViewMode] = useState("preview");
  const [editContent, setEditContent] = useState(content ?? "");
  const debounceRef = useRef(null);

  // Exiting Edit mode always returns to Preview, never Raw (Story 14.2 AC4).
  const toggleEdit = () => {
    if (isEditing) setViewMode("preview");
    setIsEditing((v) => !v);
  };

  // Client-side download of the raw Markdown (Story 14.3). Uses a Blob + synthetic
  // anchor click so it bypasses the Chainlit message/attachment system entirely
  // (no chat bubble). Always downloads props.content, so it reflects current edits.
  const handleDownloadMd = () => {
    const blob = new Blob([content ?? ""], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "dossier.md";
    a.click();
    URL.revokeObjectURL(url);
  };

  useEffect(() => {
    if (!isEditing) {
      setEditContent(content ?? "");
    }
  }, [content, isEditing]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  // Expose a header toggle bridge so login-customize.js can call back into Python.
  // callAction is a stable Chainlit-injected global, so binding it once per mount
  // is fine; the cleanup clears the global on unmount so the persisted header
  // button can never call into an unmounted element (a stale closure).
  useEffect(() => {
    window.__cc_toggle_dossier = () => callAction({ name: "toggle_dossier", payload: {} });
    document.dispatchEvent(new CustomEvent("cc:dossier-active"));
    return () => {
      delete window.__cc_toggle_dossier;
    };
  }, []);

  const handleChange = (e) => {
    const val = e.target.value;
    setEditContent(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      updateElement({ ...props, content: val, version: (props.version ?? 0) + 1 });
    }, 400);
  };

  if (phase === "investigating") {
    return (
      <Card className="dossier-card flex h-full flex-col">
        <div className="dossier-card-head">
          <span className="title">Dossier</span>
          <span className="v">v{version ?? 0}</span>
        </div>
        <div className="dossier-card-body flex-1">
          <p className="empty-state">
            Investigation in progress. The dossier will appear here when we have enough context.
          </p>
        </div>
      </Card>
    );
  }

  return (
    <Card className="dossier-card flex h-full flex-col">
      <div className="dossier-card-head">
        <span className="title">Dossier</span>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span className="v">v{version ?? 0}</span>
          {!isEditing && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setViewMode((v) => (v === "preview" ? "raw" : "preview"))}
            >
              {viewMode === "preview" ? "Raw" : "Preview"}
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={handleDownloadMd}>
            ⬇ MD
          </Button>
          <Button size="sm" variant="outline" onClick={toggleEdit}>
            {isEditing ? "View" : "Edit"}
          </Button>
        </div>
      </div>
      <div className="dossier-card-body flex-1">
        {isEditing ? (
          <textarea
            className="h-full w-full resize-none border-none bg-transparent font-mono text-sm outline-none"
            value={editContent}
            onChange={handleChange}
            autoFocus
          />
        ) : viewMode === "raw" ? (
          <pre className="whitespace-pre-wrap font-mono text-sm">{content ?? ""}</pre>
        ) : html_content ? (
          <div dangerouslySetInnerHTML={{ __html: html_content }} className="prose prose-sm max-w-none" />
        ) : (
          <pre className="whitespace-pre-wrap font-sans text-sm">{content ?? ""}</pre>
        )}
      </div>
    </Card>
  );
}
