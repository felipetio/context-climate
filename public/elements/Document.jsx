import { useState, useRef, useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function Document() {
  const { content, version, phase } = props;
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(content ?? "");
  const debounceRef = useRef(null);

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
          <Button size="sm" variant="outline" onClick={() => setIsEditing((v) => !v)}>
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
        ) : (
          <pre className="prose prose-sm max-w-none whitespace-pre-wrap font-sans text-sm">{content ?? ""}</pre>
        )}
      </div>
    </Card>
  );
}
