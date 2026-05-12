# Story 10.1: Document.jsx Custom Element

Status: ready

## Story

As a journalist,
I want a live document panel on the right side of the screen,
So that I can see the dossier take shape as I investigate.

---

## Acceptance Criteria

**AC1:** Given the Chainlit app is running and the Document component is loaded, when `props.phase === "investigating"`, then the panel shows: "Investigation in progress. The dossier will appear here when we have enough context." No edit toggle is visible in this state.

**AC2:** Given the document is in `"dossier"` phase, when the component renders, then `props.content` is rendered as formatted markdown using `react-markdown` (fall back to `<pre>` if react-markdown is unavailable in the Chainlit bundle).

**AC3:** Given the document is in `"dossier"` phase, when the user clicks the Edit button, then the view switches to an editable `<textarea>` containing the raw markdown content.

**AC4:** Given the user edits the textarea, when 400ms have passed since the last keystroke (debounce), then `updateElement({...props, content: newContent, version: props.version + 1})` is called to sync the edit back to Python.

**AC5:** Given the user is in edit mode, when they click the View button, then the markdown view is restored, re-rendering the current textarea content.

**AC6:** Given the component is rendering, when any phase, then `v{props.version}` is displayed as a small muted label in the top-right corner of the panel for developer debugging.

---

## Tasks / Subtasks

### Task 1: Create `public/elements/Document.jsx` (AC: #1, #2, #3, #4, #5, #6)

- [ ] Create `public/elements/` directory if it does not exist
- [ ] Create `public/elements/Document.jsx` with:
  - `const { content, version, phase } = props` (global props, NOT function parameters)
  - `useState` for `isEditing` (bool) and `editContent` (string, synced from `props.content`)
  - Investigating state: render placeholder text when `phase === "investigating"`, no edit button
  - Dossier read state: render `<ReactMarkdown>` (or `<pre>` fallback) for `content`; show Edit button
  - Dossier edit state: render `<textarea>` with `editContent`; show View button; debounce `updateElement` call on change
  - Version indicator: small `v{version}` label, `text-xs text-muted-foreground`, top-right corner
- [ ] Use shadcn `Card`, `Button` from `@/components/ui/card` and `@/components/ui/button`
- [ ] Use Tailwind `prose prose-sm max-w-none` classes for markdown styling
- [ ] Debounce: use `useRef` for timeout; 400ms delay; clear on each keystroke

### Task 2: Verify react-markdown availability (AC: #2)

- [ ] Start `chainlit run app/chat.py -w` and inspect browser console for `react-markdown` import errors
- [ ] If unavailable, implement `<pre className="whitespace-pre-wrap text-sm">{content}</pre>` fallback and add a `# TODO: replace with react-markdown when confirmed available` comment

### Task 3: Manual verification (AC: all)

- [ ] Start the app, confirm the right panel opens (Epic 10.2 canvas must be wired for this; test in isolation by temporarily calling `open_dossier_canvas()` in `on_chat_start`)
- [ ] With `phase="investigating"`: confirm placeholder text, no edit button
- [ ] Flip `phase` to `"dossier"` in Python, confirm markdown renders
- [ ] Click Edit, modify text, wait 400ms, confirm `updateElement` fires (check browser DevTools Network or Python logs)
- [ ] Click View, confirm re-render

---

## Dev Notes

### Project Structure

**Files to create:**
- `public/elements/Document.jsx` (NEW, ~80 lines)

**Files NOT to touch in this story:**
- `app/chat.py` — no Python changes
- `app/prompts.py` — no changes
- `pyproject.toml` — no changes

### JSX Constraints (Critical)

From Chainlit cookbook analysis:
- **Props are global, never function parameters**: Always `const { content, version } = props`, never `function Document(props) {}`
- **`updateElement(newProps)`** is a global function available in JSX — no import needed
- **`callAction({ name, payload })`** is global — no import needed (not used in this story)
- Available imports: `react`, `@/components/ui/button`, `@/components/ui/card`, `lucide-react`, Tailwind classes
- No arbitrary npm packages. No build step.

### Component Sketch

```jsx
import { useState, useRef } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function Document() {
  const { content, version, phase } = props;
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(content);
  const debounceRef = useRef(null);

  // sync if props.content changes from Python
  // (use useEffect pattern when needed)

  const handleChange = (e) => {
    const val = e.target.value;
    setEditContent(val);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      updateElement({ ...props, content: val, version: props.version + 1 });
    }, 400);
  };

  if (phase === "investigating") {
    return (
      <Card className="h-full p-6 text-muted-foreground text-sm">
        Investigation in progress. The dossier will appear here when we have enough context.
      </Card>
    );
  }

  return (
    <Card className="h-full flex flex-col">
      <div className="flex justify-between items-center p-2 border-b">
        <span className="text-xs text-muted-foreground">v{version}</span>
        <Button size="sm" variant="outline" onClick={() => setIsEditing(!isEditing)}>
          {isEditing ? "View" : "Edit"}
        </Button>
      </div>
      <div className="flex-1 overflow-auto p-4">
        {isEditing ? (
          <textarea
            className="w-full h-full font-mono text-sm resize-none border-none outline-none"
            value={editContent}
            onChange={handleChange}
          />
        ) : (
          <div className="prose prose-sm max-w-none">
            {/* react-markdown or pre fallback */}
            <pre className="whitespace-pre-wrap">{content}</pre>
          </div>
        )}
      </div>
    </Card>
  );
}
```

### Anti-Patterns

- **DON'T** pass props as function parameters: `export default function Document(props)` — Chainlit injects props globally
- **DON'T** import react-markdown without verifying it's in Chainlit's bundle
- **DON'T** call `updateElement` on every keystroke — debounce is required to avoid flooding the WebSocket
- **DON'T** use `useEffect` to watch `props.content` changes without careful dependency management (can cause loops)
- **DON'T** add emoji to the component UI
- **DON'T** add comments explaining what the code does — names should be self-explanatory

### References

- [Chainlit cookbook custom-element](https://github.com/Chainlit/cookbook/tree/main/custom-element) — props pattern, updateElement usage
- [Chainlit cookbook map-canvas](https://github.com/Chainlit/cookbook/tree/main/map-canvas) — ElementSidebar pattern (needed for Story 10.2)
- `_bmad-output/planning-artifacts/epics.md#Story 10.1` — acceptance criteria
- Story 10.2 — canvas integration (must be done to test this component end-to-end)

---

## Dev Agent Record

### Agent Model Used

_To be filled on implementation_

### Completion Notes

_To be filled on implementation_

### File List

_To be filled on implementation_
