import { useState, useRef, useEffect } from "react";
// TODO: replace with react-markdown when confirmed available in Chainlit's JSX bundle
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
      <Card className="h-full p-6 text-sm text-muted-foreground">
        <div className="flex h-full flex-col justify-between">
          <p>Investigation in progress. The dossier will appear here when we have enough context.</p>
          <span className="self-end text-xs text-muted-foreground">v{version ?? 0}</span>
        </div>
      </Card>
    );
  }

  return (
    <Card className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b p-2">
        <span className="text-xs text-muted-foreground">v{version ?? 0}</span>
        <Button size="sm" variant="outline" onClick={() => setIsEditing((v) => !v)}>
          {isEditing ? "View" : "Edit"}
        </Button>
      </div>
      <div className="flex-1 overflow-auto p-4">
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
